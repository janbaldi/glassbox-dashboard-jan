"""Reading a glassbox run: which batches are of interest, and what the models say set them apart.

Glassbox is a separate code base. This module never imports it; it reads the
files a run writes, as described in glassbox's ``docs/result_files.md``:

- ``run_manifest.json``: the run's arguments (``id_col``, ``target``,
  ``positive_label``) and the models with their metrics
- ``<model>/predictions.csv``: every batch with its true label and out-of-fold
  probability
- ``<model>/local_explanations.csv``: every batch's in-sample contribution per
  feature
- ``investigation/``: the investigation, with each batch of interest's
  leave-one-out contribution next to the in-sample one (``drivers.csv``), its
  probabilities (``batches.csv``) and the trust gate (``investigation.json``)

A run without ``investigation/`` still loads, with in-sample contributions only.
The investigation is only used when ``run_manifest.json`` names it and its files
still match the SHA-256 the manifest recorded: a folder left by an earlier run
into the same output directory would otherwise pair its leave-one-out values
with this run's in-sample ones. Glassbox features are dashboard parameters, by
name. The run's positive class (usually the minority class: out-of-spec
batches, or one period against another) is the batches of interest; the rest
is the background.

Contributions are on each model's own scale (``ModelRun.scale``): log-odds for
EBM, XGBoost and the GAM, a probability for the decision tree.

No Streamlit here, so it can be unit tested. The files come in as a mapping of
relative path to bytes, from a folder upload or from disk.
"""

from __future__ import annotations

import hashlib
import io
import json
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

import numpy as np
import pandas as pd

MANIFEST = "run_manifest.json"
INVESTIGATION_DIR = "investigation"
INVESTIGATION_SCHEMA = "glassbox/investigation/1"
SUFFIXES = (".csv", ".json")  # all the dashboard reads; models and reports are skipped

# The long contribution table of one model: one row per batch of interest and feature.
CONTRIBUTION_COLUMNS = [
    "batch_id", "feature", "value", "in_sample", "loo", "agree", "imputed",
    "in_spec_typical", "percentile", "z",
]


class GlassboxError(ValueError):
    """The folder is not a glassbox run the dashboard can read."""


@dataclass
class ModelRun:
    name: str
    pr_auc: float | None
    features: list[str]
    # One row per batch of interest and feature: see CONTRIBUTION_COLUMNS. ``loo`` and
    # the flags are empty for batches without a dossier.
    contributions: pd.DataFrame
    # One row per batch of interest: risk_rank, oof_prob, in_sample_prob, loo_prob,
    # threshold, detailed, top_driver, drivers_reproduced. Indexed by batch_id,
    # highest out-of-fold probability (this model's) first.
    batches: pd.DataFrame
    scale: str = "log-odds"  # the units of the contributions: log-odds or probability
    # Every batch's out-of-fold probability: batch_id, interest (bool), prob. None
    # when predictions.csv has no probability column.
    predictions: pd.DataFrame | None = None
    threshold: float | None = None  # the model's decision threshold
    pr_auc_ci: str | None = None  # "lo – hi" when glassbox ran with bootstrap_ci


@dataclass
class GlassboxRun:
    name: str
    id_col: str
    target_col: str
    positive_label: object
    interest_ids: list[str]  # the positive class
    background_ids: list[str]
    models: dict[str, ModelRun]
    has_investigation: bool
    prevalence: float
    usable: bool  # some model beats the PR-AUC of a model that learned nothing
    notes: list[str] = field(default_factory=list)  # for information
    warnings: list[str] = field(default_factory=list)  # files left out or changed after the run
    title: str | None = None  # the glassbox config's report.title and report.description
    description: str | None = None
    manifest_sha256: str = ""  # of run_manifest.json as read, for the audit record
    provenance: dict = field(default_factory=dict)  # glassbox's git commit, data SHA-256, run time

    @property
    def best_model(self) -> str:
        """The model with the highest PR-AUC (the first when none has one)."""
        scored = [m for m in self.models.values() if m.pr_auc is not None]
        return max(scored, key=lambda m: m.pr_auc).name if scored else next(iter(self.models))


def read_folder(path: str | Path) -> dict[str, bytes]:
    """The CSV and JSON files under ``path``, keyed by path relative to it.

    ``path`` may also be a model folder inside the run: the run folder is then
    the one above it.
    """
    root = Path(path).expanduser()
    if not root.is_dir():
        raise GlassboxError(f"Not a folder: {root}")
    if not (root / MANIFEST).exists() and (root.parent / MANIFEST).exists():
        root = root.parent
    return {
        f.relative_to(root).as_posix(): f.read_bytes()
        for f in sorted(root.rglob("*"))
        if f.is_file() and f.suffix.lower() in SUFFIXES
    }


def _rooted(files: dict[str, bytes]) -> dict[str, bytes]:
    """Re-key ``files`` relative to the folder that holds ``run_manifest.json``.

    A folder upload keys files as ``<picked folder>/…``, and the picked folder
    may sit above the run.
    """
    manifests = sorted(
        (PurePosixPath(p).parent for p in files if PurePosixPath(p).name == MANIFEST),
        key=lambda p: len(p.parts),
    )
    if not manifests:
        raise GlassboxError(
            f"No {MANIFEST} found. Pick the glassbox output folder (the one given as "
            "--output-dir), not a model folder inside it."
        )
    root = manifests[0]
    out = {}
    for p, data in files.items():
        pp = PurePosixPath(p)
        if root == PurePosixPath(".") or pp.is_relative_to(root):
            out[pp.relative_to(root).as_posix() if root != PurePosixPath(".") else p] = data
    return out


def _csv(files: dict[str, bytes], name: str) -> pd.DataFrame | None:
    return pd.read_csv(io.BytesIO(files[name]), low_memory=False) if name in files else None


def _json(files: dict[str, bytes], name: str) -> dict | None:
    if name not in files:
        return None
    try:
        return json.loads(files[name])
    except json.JSONDecodeError as exc:
        raise GlassboxError(f"{name} is not valid JSON: {exc}") from None


def _ids(s: pd.Series) -> pd.Series:
    """Batch ids as the dashboard holds them: stripped strings."""
    return s.astype(str).str.strip()


def _same(a: object, b: object) -> bool:
    """Label equality across the JSON/CSV round trip (1 == '1' == 1.0)."""
    try:
        return float(a) == float(b)
    except (TypeError, ValueError):
        return str(a) == str(b)


def _recorded_hashes(manifest: dict) -> dict[str, str]:
    """The SHA-256 of each file, as glassbox recorded it in the manifest when the run ended."""
    entries = [e for m in manifest.get("models") or [] for e in m.get("artefacts") or []]
    entries += manifest.get("investigation") or []
    # relpath on Windows writes backslashes; the files here are keyed with slashes.
    return {str(e["file"]).replace("\\", "/"): e["sha256"] for e in entries if e.get("file") and e.get("sha256")}


def _changed(files: dict[str, bytes], recorded: dict[str, str], paths: list[str]) -> list[str]:
    """Those of ``paths`` whose bytes no longer match the recorded SHA-256."""
    return [
        p for p in paths
        if p in files and p in recorded and hashlib.sha256(files[p]).hexdigest() != recorded[p]
    ]


def _default_scale(model: str) -> str:
    """The scale of a model's contributions, for runs written before glassbox recorded it.

    SHAP explains a scikit-learn classification tree's probability; the other
    families explain the log-odds.
    """
    return "probability" if model == "decision_tree" else "log-odds"


def load_run(files: dict[str, bytes], name: str = "glassbox run") -> GlassboxRun:
    """Read a glassbox run from its files. Raises GlassboxError with the reason."""
    files = _rooted(files)
    manifest = _json(files, MANIFEST) or {}
    run = manifest.get("run") or {}
    if run.get("task") not in (None, "classification"):
        raise GlassboxError(f"This is a {run.get('task')} run. The dashboard needs a classification run.")
    if run.get("mode") == "predict":
        raise GlassboxError("This is a scoring run (--load-model). Open the training run instead.")

    notes: list[str] = []
    warnings: list[str] = []
    recorded = _recorded_hashes(manifest)

    # The investigation this run wrote, and only that one: glassbox names it in
    # the manifest when it writes it. An investigation/ folder the manifest does
    # not name was left by an earlier run into the same output directory.
    inv_path = run.get("investigation")
    inv = _json(files, inv_path) if inv_path else None
    inv_dir = PurePosixPath(inv_path).parent if inv_path else PurePosixPath(INVESTIGATION_DIR)
    if inv_path and inv is None:
        warnings.append(
            f"run_manifest.json names {inv_path}, but the folder does not have it: "
            "in-sample contributions only."
        )
    elif not inv_path and any(p.startswith(f"{INVESTIGATION_DIR}/") for p in files):
        warnings.append(
            f"The {INVESTIGATION_DIR}/ folder is not from this run (run_manifest.json does not "
            "name it), so it was left out: in-sample contributions only."
        )
    elif not inv_path:
        notes.append(
            "No investigation/ folder: in-sample contributions only. Rerun glassbox with "
            "investigation.batches set for leave-one-out contributions."
        )
    if inv is not None and inv.get("schema") != INVESTIGATION_SCHEMA:
        raise GlassboxError(
            f"{inv_path} has schema {inv.get('schema')!r}; this dashboard reads {INVESTIGATION_SCHEMA!r}."
        )
    inv_files = {
        k: str(inv_dir / name)
        for k, name in {"batches": "batches.csv", "drivers": "drivers.csv", **((inv or {}).get("files") or {})}.items()
    }
    if inv is not None:
        changed = _changed(files, recorded, [inv_path, inv_files["batches"], inv_files["drivers"]])
        if changed:
            warnings.append(
                f"{', '.join(changed)} changed after the run (the SHA-256 no longer matches "
                "run_manifest.json), so the investigation was left out: in-sample contributions only."
            )
            inv = None

    id_col = (inv or {}).get("id_col") or run.get("id_col")
    target_col = (inv or {}).get("target_col") or run.get("target")
    if not id_col:
        raise GlassboxError("The run has no id column (--id-col), so its batches cannot be matched.")

    manifest_models = {m["model_name"]: m for m in manifest.get("models") or []}
    inv_models = {m["model_name"]: m for m in (inv or {}).get("models") or []}
    names = list(manifest_models) or sorted(
        {p.split("/")[0] for p in files if p.endswith("/predictions.csv")}
    )
    if not names:
        raise GlassboxError("No model results (<model>/predictions.csv) in the run.")

    batches_all = _csv(files, inv_files["batches"]) if inv is not None else None
    drivers_all = _csv(files, inv_files["drivers"]) if inv is not None else None

    changed = _changed(
        files, recorded, [f"{m}/{f}" for m in names for f in ("predictions.csv", "local_explanations.csv")]
    )
    if changed:
        warnings.append(
            f"Changed after the run (the SHA-256 no longer matches run_manifest.json): "
            f"{', '.join(changed)}. The numbers shown may not be the ones glassbox wrote."
        )

    # Labels from the first model that has predictions: every model sees the same rows.
    labels = None
    for m in names:
        pred = _csv(files, f"{m}/predictions.csv")
        if pred is not None and id_col in pred and "true_y" in pred:
            labels = pd.DataFrame({"batch_id": _ids(pred[id_col]), "y": pred["true_y"]})
            break
    if labels is None:
        raise GlassboxError(f"No predictions.csv with columns '{id_col}' and 'true_y'.")

    positive = (inv or {}).get("positive_label", run.get("positive_label"))
    classes = labels["y"].dropna().unique()
    if len(classes) != 2:
        raise GlassboxError(f"The target has {len(classes)} classes; the dashboard needs two.")
    if positive is None:
        positive = max(classes)  # glassbox's own rule when it did not write it down
    is_interest = labels["y"].map(lambda v: _same(v, positive))
    interest_ids = labels.loc[is_interest, "batch_id"].tolist()
    background_ids = labels.loc[~is_interest, "batch_id"].tolist()
    interest_set = set(interest_ids)

    models: dict[str, ModelRun] = {}
    for m in names:
        expl = _csv(files, f"{m}/local_explanations.csv")
        if expl is None or id_col not in expl:
            notes.append(f"{m}: no local_explanations.csv, left out.")
            continue
        features = [c[: -len("_contribution")] for c in expl.columns if c.endswith("_contribution")]
        expl = expl[_ids(expl[id_col]).isin(interest_set)]
        ids = _ids(expl[id_col])
        long = pd.concat(
            [
                pd.DataFrame(
                    {
                        "batch_id": ids.values,
                        "feature": f,
                        "value": expl[f"{f}_value"].values if f"{f}_value" in expl else None,
                        "in_sample": expl[f"{f}_contribution"].values,
                    }
                )
                for f in features
            ],
            ignore_index=True,
        ) if features else pd.DataFrame(columns=["batch_id", "feature", "value", "in_sample"])

        if drivers_all is not None:
            d = drivers_all[drivers_all["model"] == m].assign(batch_id=lambda x: _ids(x["batch_id"]))
            d = d.rename(columns={"loo_contribution": "loo"})[
                ["batch_id", "feature", "loo", "agree", "imputed", "in_spec_typical", "percentile", "z"]
            ]
            long = long.merge(d, on=["batch_id", "feature"], how="left")
        for c in CONTRIBUTION_COLUMNS:
            if c not in long:
                long[c] = pd.NA
        long = long[CONTRIBUTION_COLUMNS]

        batches = pd.DataFrame({"batch_id": sorted(set(ids))})
        pred = _csv(files, f"{m}/predictions.csv")
        if batches_all is not None and (batches_all["model"] == m).any():
            b = batches_all[batches_all["model"] == m].drop(columns="model")
            batches = b.assign(batch_id=_ids(b["batch_id"]))
        elif pred is not None and "prob_class_1" in pred:
            p = pd.DataFrame({"batch_id": _ids(pred[id_col]), "oof_prob": pred["prob_class_1"]})
            batches = batches.merge(p, on="batch_id", how="left")
            batches["risk_rank"] = batches["oof_prob"].rank(ascending=False, method="first")
        # Highest risk first by this model's own out-of-fold probability.
        # Glassbox's risk_rank takes the highest over all models (the order it
        # chose dossiers in), so it is not this model's order; it breaks ties.
        if "oof_prob" in batches:
            keys = ["oof_prob"] + (["risk_rank"] if "risk_rank" in batches else [])
            batches = batches.sort_values(
                keys, ascending=[False] + [True] * (len(keys) - 1), na_position="last", kind="stable"
            )
        elif "risk_rank" in batches:
            batches = batches.sort_values("risk_rank")

        pr_auc = (inv_models.get(m) or {}).get("pr_auc")
        if pr_auc is None:
            pr_auc = ((manifest_models.get(m) or {}).get("metrics") or {}).get("pr_auc")
        predictions, threshold = None, (manifest_models.get(m) or {}).get("decision_threshold")
        if pred is not None and {id_col, "true_y", "prob_class_1"} <= set(pred.columns):
            predictions = pd.DataFrame({
                "batch_id": _ids(pred[id_col]),
                "interest": pred["true_y"].map(lambda v: _same(v, positive)),
                "prob": pd.to_numeric(pred["prob_class_1"], errors="coerce"),
            })
        if threshold is None and "threshold" in batches and batches["threshold"].notna().any():
            threshold = float(batches["threshold"].dropna().iloc[0])
        scale = (
            (inv_models.get(m) or {}).get("contribution_scale")
            or (manifest_models.get(m) or {}).get("contribution_scale")
            or _default_scale(m)
        )
        models[m] = ModelRun(
            name=m,
            pr_auc=float(pr_auc) if pr_auc is not None else None,
            features=features,
            contributions=long.reset_index(drop=True),
            batches=batches.set_index("batch_id"),
            scale=scale,
            predictions=predictions,
            threshold=float(threshold) if threshold is not None else None,
            pr_auc_ci=(inv_models.get(m) or {}).get("pr_auc_ci"),
        )
    if not models:
        raise GlassboxError("No model in the run has local_explanations.csv.")

    trust = (inv or {}).get("trust") or {}
    prevalence = trust.get("prevalence", len(interest_ids) / max(len(labels), 1))
    usable = trust.get("usable")
    if usable is None:
        usable = any(m.pr_auc is not None and m.pr_auc > prevalence for m in models.values())

    report = (manifest.get("config") or {}).get("report") or {}
    return GlassboxRun(
        title=(report.get("title") or "").strip() or None,
        description=(report.get("description") or "").strip() or None,
        name=name,
        id_col=id_col,
        target_col=target_col or "",
        positive_label=positive,
        interest_ids=interest_ids,
        background_ids=background_ids,
        models=models,
        has_investigation=inv is not None,
        prevalence=float(prevalence),
        usable=bool(usable),
        notes=notes,
        warnings=warnings,
        manifest_sha256=hashlib.sha256(files[MANIFEST]).hexdigest() if MANIFEST in files else "",
        provenance={k: run[k] for k in ("git_commit", "data_sha256", "data_path", "timestamp") if run.get(k) is not None},
    )


def refitted_among(contributions: pd.DataFrame, batch_ids: list[str]) -> list[str]:
    """Those of ``batch_ids`` with a leave-one-out contribution, in the given order.

    Glassbox refits without a batch only for the highest-risk ones (its
    ``max_detail``), and a refit can fail; those batches have no leave-one-out.
    """
    loo = pd.to_numeric(contributions["loo"], errors="coerce")
    with_loo = set(contributions.loc[loo.notna(), "batch_id"])
    return [b for b in batch_ids if b in with_loo]


def driver_summary(contributions: pd.DataFrame, top: int = 15) -> pd.DataFrame:
    """Per feature over the batches in ``contributions``: mean in-sample and leave-one-out contribution.

    The ``top`` features by mean |in-sample contribution|, largest first; ``n``
    is the number of batches both means are over. The leave-one-out mean is only
    given when every batch has a leave-one-out contribution: taken over the
    refitted batches alone, it compared the highest-risk batches with all of
    them and came out larger for that reason only. Pass the rows of
    ``refitted_among`` to compare the two readings.
    """
    c = contributions
    if c.empty:
        return pd.DataFrame(columns=["feature", "in_sample", "loo", "n", "abs_in_sample"])
    loo = pd.to_numeric(c["loo"], errors="coerce")
    out = pd.DataFrame(
        {
            "in_sample": c.groupby("feature", sort=False)["in_sample"].mean(),
            "loo": loo.groupby(c["feature"]).mean() if loo.notna().all() else np.nan,
            "n": c.groupby("feature")["batch_id"].nunique(),
            "abs_in_sample": c["in_sample"].abs().groupby(c["feature"]).mean(),
        }
    )
    return out.sort_values("abs_in_sample", ascending=False).head(top).reset_index(names="feature")


def batch_drivers(model: ModelRun, batch_id: str, top: int = 12) -> pd.DataFrame:
    """One batch's ``top`` features by |in-sample contribution|, largest first."""
    c = model.contributions
    rows = c[c["batch_id"] == batch_id].copy()
    rows["abs"] = rows["in_sample"].abs()
    return rows.sort_values("abs", ascending=False).head(top).drop(columns="abs").reset_index(drop=True)
