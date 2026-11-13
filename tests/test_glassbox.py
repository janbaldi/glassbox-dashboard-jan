"""Reading a glassbox run (cart_dashboard.glassbox) and the selection modes it adds."""

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from cart_dashboard.config import load_config
from cart_dashboard.data import load_batches
from cart_dashboard.glassbox import (
    GlassboxError,
    batch_drivers,
    driver_summary,
    load_run,
    read_folder,
    refitted_among,
)
from cart_dashboard.selection import BatchSelection, SelectionMode, select_batches

ID = "Patient Lot/Batch #"
FEATURES = ["Vector hold time (min)", "Thaw Duration (min)", "not a dashboard parameter"]


def _hashes(root, paths):
    return [{"file": p, "sha256": hashlib.sha256((root / p).read_bytes()).hexdigest()} for p in paths]


def _write_run(root, investigation=True, models=("xgboost", "ebm"), named=True, scales=None, oof=None):
    """A small glassbox run: batches B0-B9, B7-B9 out of spec, B8-B9 with a dossier.

    Written the way glassbox writes one: the manifest last, naming the
    investigation (unless ``named`` is False) and recording each file's SHA-256.
    ``scales`` puts a contribution_scale per model in investigation.json;
    ``oof`` gives a model its own out-of-fold probability per batch of interest.
    """
    ids = [f"B{i}" for i in range(10)]
    y = [0] * 7 + [1] * 3
    root.mkdir(parents=True, exist_ok=True)
    for k, m in enumerate(models):
        (root / m).mkdir()
        pd.DataFrame({ID: ids, "true_y": y, "pred_y": y, "prob_class_1": [i / 10 for i in range(10)]}).to_csv(
            root / m / "predictions.csv", index=False
        )
        expl = {ID: ids, "oos": y}
        for j, f in enumerate(FEATURES):
            expl[f"{f}_value"] = range(10)
            expl[f"{f}_contribution"] = [(j + 1) * (i - 5) / 10 + k for i in range(10)]
        pd.DataFrame(expl).to_csv(root / m / "local_explanations.csv", index=False)
        (root / m / "model_x.joblib").write_bytes(b"not read")
    inv_files = ["investigation/investigation.json", "investigation/batches.csv", "investigation/drivers.csv"]
    if investigation:
        inv = root / "investigation"
        inv.mkdir()
        (inv / "investigation.json").write_text(json.dumps({
            "schema": "glassbox/investigation/1", "id_col": ID, "target_col": "oos", "positive_label": 1,
            "models": [
                {"model_name": m, "pr_auc": 0.9 - 0.1 * i, **({"contribution_scale": scales[m]} if scales else {})}
                for i, m in enumerate(models)
            ],
            "trust": {"prevalence": 0.3, "baseline_pr_auc": 0.3, "usable": True},
            "files": {"batches": "batches.csv", "drivers": "drivers.csv"},
        }))
        pd.DataFrame([
            {"model": m, "batch_id": b, "risk_rank": r, "oof_prob": ((oof or {}).get(m) or {}).get(b, p),
             "in_sample_prob": p, "loo_prob": p - 0.1, "threshold": 0.5, "detailed": b != "B7",
             "top_driver": FEATURES[2], "drivers_reproduced": None}
            for m in models for r, (b, p) in enumerate([("B9", 0.9), ("B8", 0.8), ("B7", 0.7)], start=1)
        ]).to_csv(inv / "batches.csv", index=False)
        pd.DataFrame([
            {"model": m, "batch_id": b, "rank": 1, "feature": f, "value": 1, "in_spec_typical": 0,
             "percentile": 90, "z": 2.0, "in_sample_contribution": 0.4, "loo_contribution": -0.2 if b == "B8" else 0.3,
             "agree": b != "B8", "imputed": False, "term_stable": "unknown"}
            for m in models for b in ("B8", "B9") for f in FEATURES
        ]).to_csv(inv / "drivers.csv", index=False)
    run = {"task": "classification", "mode": "train", "id_col": ID, "target": "oos", "positive_label": 1}
    if investigation and named:
        run["investigation"] = "investigation/investigation.json"
    manifest = {
        "schema": "glassbox/run-manifest/1",
        "run": run,
        "models": [
            {
                "model_name": m,
                "metrics": {"pr_auc": 0.5 + 0.1 * i},
                "artefacts": _hashes(root, [f"{m}/predictions.csv", f"{m}/local_explanations.csv"]),
            }
            for i, m in enumerate(models)
        ],
        "investigation": _hashes(root, inv_files) if investigation and named else [],
        "config": {"report": {"title": "CAR OOS", "description": " Why lots failed in Q3. "}},
    }
    (root / "run_manifest.json").write_text(json.dumps(manifest))
    return root


def test_interest_batches_are_the_positive_class(tmp_path):
    run = load_run(read_folder(_write_run(tmp_path / "run")), name="run")
    assert run.interest_ids == ["B7", "B8", "B9"]
    assert run.background_ids == [f"B{i}" for i in range(7)]
    assert run.has_investigation and run.usable and run.prevalence == 0.3
    assert (run.title, run.description) == ("CAR OOS", "Why lots failed in Q3.")
    # PR-AUC from investigation.json wins over the manifest's.
    assert run.best_model == "xgboost"


def test_contributions_put_in_sample_next_to_leave_one_out(tmp_path):
    run = load_run(read_folder(_write_run(tmp_path / "run")))
    model = run.models["xgboost"]
    c = model.contributions
    assert set(c["batch_id"]) == {"B7", "B8", "B9"}  # batches of interest only
    b8 = c[(c["batch_id"] == "B8") & (c["feature"] == FEATURES[0])].iloc[0]
    assert b8["in_sample"] == pytest.approx(0.3) and b8["loo"] == pytest.approx(-0.2)
    assert not bool(b8["agree"])
    # B7 has no dossier: in-sample only.
    assert c.loc[c["batch_id"] == "B7", "loo"].isna().all()
    assert model.batches.index.tolist() == ["B9", "B8", "B7"]  # by risk
    assert not model.batches.loc["B7", "detailed"]

    assert batch_drivers(model, "B9", top=1)["feature"].tolist() == [FEATURES[2]]
    assert run.warnings == []  # every file matches the manifest


def test_batches_are_in_each_models_own_risk_order(tmp_path):
    """Glassbox ranks by the highest risk over all models; each model lists by its own."""
    run = load_run(read_folder(_write_run(tmp_path / "run", oof={"ebm": {"B7": 0.95}})))
    assert run.models["xgboost"].batches.index.tolist() == ["B9", "B8", "B7"]
    ebm = run.models["ebm"].batches
    assert ebm.index.tolist() == ["B7", "B9", "B8"]  # B7 is ebm's riskiest, though ranked 3rd overall
    assert ebm["risk_rank"].tolist() == [3, 1, 2]


def test_both_means_cover_the_same_batches(tmp_path):
    """The leave-one-out mean exists only over the refitted batches, so both means are over those.

    Over all batches of interest the leave-one-out mean would cover only the refitted,
    highest-risk ones, beside an in-sample mean over all of them.
    """
    c = load_run(read_folder(_write_run(tmp_path / "run"))).models["xgboost"].contributions
    assert refitted_among(c, ["B7", "B8", "B9"]) == ["B8", "B9"]  # B7 has no dossier

    everything = driver_summary(c).set_index("feature")
    assert everything["loo"].isna().all()  # B7 has none, so no leave-one-out mean
    assert everything["n"].tolist() == [3, 3, 3]
    assert everything.loc[FEATURES[0], "in_sample"] == pytest.approx((0.2 + 0.3 + 0.4) / 3)

    refit = driver_summary(c[c["batch_id"].isin(["B8", "B9"])])
    assert refit["feature"].iloc[0] == FEATURES[2]  # largest mean |in-sample| first
    row = refit.set_index("feature").loc[FEATURES[0]]
    assert row["in_sample"] == pytest.approx((0.3 + 0.4) / 2)  # B8 and B9
    assert row["loo"] == pytest.approx((-0.2 + 0.3) / 2)  # the same two batches
    assert row["n"] == 2


def test_each_model_carries_the_scale_of_its_contributions(tmp_path):
    run = load_run(read_folder(_write_run(tmp_path / "a", models=("xgboost", "decision_tree"))))
    # Not recorded (a run from before glassbox wrote it): the decision tree is the
    # one family whose SHAP values are a probability.
    assert {m: r.scale for m, r in run.models.items()} == {"xgboost": "log-odds", "decision_tree": "probability"}
    run = load_run(read_folder(_write_run(tmp_path / "b", scales={"xgboost": "log-odds", "ebm": "probability"})))
    assert run.models["ebm"].scale == "probability"  # what glassbox recorded wins


def test_an_investigation_the_manifest_does_not_name_is_left_out(tmp_path):
    """A folder an earlier run left behind must not be paired with this run's numbers."""
    run = load_run(read_folder(_write_run(tmp_path / "run", named=False)))
    assert not run.has_investigation
    assert run.models["xgboost"].contributions["loo"].isna().all()
    assert any("not from this run" in w for w in run.warnings)


def test_an_investigation_changed_after_the_run_is_left_out(tmp_path):
    root = _write_run(tmp_path / "run")
    drivers = root / "investigation" / "drivers.csv"
    drivers.write_text(drivers.read_text().replace("-0.2", "-0.25"))
    run = load_run(read_folder(root))
    assert not run.has_investigation
    assert run.models["xgboost"].contributions["loo"].isna().all()
    assert any("investigation/drivers.csv changed after the run" in w for w in run.warnings)


def test_model_files_changed_after_the_run_are_flagged(tmp_path):
    root = _write_run(tmp_path / "run")
    pred = root / "xgboost" / "predictions.csv"
    pred.write_text(pred.read_text().replace("0.9", "0.95"))
    run = load_run(read_folder(root))
    assert run.has_investigation  # still opens: the files are readable, only flagged
    assert any("xgboost/predictions.csv" in w for w in run.warnings)


def test_a_run_without_investigation_still_opens(tmp_path):
    run = load_run(read_folder(_write_run(tmp_path / "run", investigation=False)))
    assert run.interest_ids == ["B7", "B8", "B9"] and not run.has_investigation
    assert run.models["ebm"].contributions["loo"].isna().all()
    assert run.best_model == "ebm"  # from the manifest metrics
    assert run.notes

    manifest = json.loads((tmp_path / "run" / "run_manifest.json").read_text())
    manifest["config"]["report"] = {"title": None, "description": None}
    (tmp_path / "run" / "run_manifest.json").write_text(json.dumps(manifest))
    run = load_run(read_folder(tmp_path / "run"))
    assert run.title is None and run.description is None  # the sidebar then shows the folder name


def test_a_model_folder_or_a_parent_folder_both_find_the_run(tmp_path):
    root = _write_run(tmp_path / "task" / "glassbox")
    assert load_run(read_folder(root / "xgboost")).interest_ids == ["B7", "B8", "B9"]
    # A folder upload keys files by the picked folder; the run may be below it.
    files = {f"task/glassbox/{k}": v for k, v in read_folder(root).items()}
    assert load_run(files).interest_ids == ["B7", "B8", "B9"]
    assert not any(k.endswith(".joblib") for k in read_folder(root))


def test_a_folder_that_is_not_a_run_says_so(tmp_path):
    (tmp_path / "x.csv").write_text("a\n1\n")
    with pytest.raises(GlassboxError, match="run_manifest.json"):
        load_run(read_folder(tmp_path))
    root = _write_run(tmp_path / "reg")
    manifest = json.loads((root / "run_manifest.json").read_text())
    manifest["run"]["task"] = "regression"
    (root / "run_manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(GlassboxError, match="classification"):
        load_run(read_folder(root))


def test_glassbox_selection_modes():
    cfg = load_config()
    batch_col = cfg.col("batch_id")
    df = pd.DataFrame({
        batch_col: ["B1", "B2", "B3", "B4"],
        cfg.col("manufacturing_date"): pd.to_datetime(["2025-01-01", "2025-01-02", "2025-01-03", "2025-01-04"]),
        "__remanufactured": False,
    })
    assert select_batches(df, cfg, BatchSelection(SelectionMode.RUN_INTEREST, batch_ids=["B4", "B2"])) == ["B2", "B4"]
    assert select_batches(df, cfg, BatchSelection(SelectionMode.RUN_BACKGROUND, batch_ids=["B1"])) == ["B1"]


def test_feature_relevance_covers_the_batches_the_plot_shows():
    """The plot's site filter narrows the feature relevance charts too, and they say by how many."""
    from streamlit.testing.v1 import AppTest

    root = Path(__file__).parent.parent
    run = load_run(read_folder(root / "data" / "glassbox_demo" / "run"), name="demo")
    cfg = load_config()
    df = load_batches(cfg)
    at_site_a = df[df[cfg.col("site")] == "SITE-A"][cfg.col("batch_id")]
    n_a = int(at_site_a.isin(run.interest_ids).sum())

    at = AppTest.from_file(str(root / "app.py"), default_timeout=120)
    at.session_state["run_open"] = run
    at.session_state["interest_mode"] = SelectionMode.RUN_INTEREST
    at.session_state["background_mode"] = SelectionMode.RUN_BACKGROUND
    at.session_state["run_average_over"] = "all"
    at.run()
    assert not at.exception

    def drivers_title() -> str:
        return next(m.value for m in at.markdown if m.value.startswith("**Drivers across"))

    assert drivers_title() == f"**Drivers across {len(run.interest_ids)} batches of interest**"
    assert not any("OOS" in e.label for e in at.expander)
    at.selectbox(key="timeline_site").select("SITE-A").run()
    assert not at.exception
    assert 0 < n_a < len(run.interest_ids)
    assert drivers_title() == f"**Drivers across {n_a} batches of interest**"
    left_out = len(run.interest_ids) - n_a
    assert any(f"leaves out {left_out} of the run's {len(run.interest_ids)} batches of interest" in c.value for c in at.caption)


def test_statistics_section_follows_the_plot():
    """The card covers the plotted parameter and batches; the screen runs on request, again when the batches change."""
    from streamlit.testing.v1 import AppTest

    root = Path(__file__).parent.parent
    run = load_run(read_folder(root / "data" / "glassbox_demo" / "run"), name="demo")
    at = AppTest.from_file(str(root / "app.py"), default_timeout=180)
    at.session_state["run_open"] = run
    at.session_state["interest_mode"] = SelectionMode.RUN_INTEREST
    at.session_state["background_mode"] = SelectionMode.RUN_BACKGROUND
    at.session_state["timeline_parameter"] = "Vector hold time (min)"
    at.run()
    assert not at.exception
    assert [e.label for e in at.expander if e.label.startswith("Statistics")] == [
        "Statistics · batches of interest compared with background batches"
    ]
    labels = [e.label for e in at.expander]
    assert labels.index(f"Feature relevance · {run.best_model}") < labels.index(
        "Statistics · batches of interest compared with background batches")  # between the plot and the statistics
    assert [t.label for t in at.tabs] == [
        "This parameter", "Share of batches of interest per month", "All parameters", "Numbers and methods"]
    card = " ".join(m.value for m in at.markdown)
    assert "Vector hold time (min) is higher in batches of interest." in card
    assert "Comparing only batches made in the same quarter" in card
    assert "the model flags" in card  # the sidebar model check

    at.button[[b.label for b in at.button].index("Screen all 619 parameters")].click().run()
    assert not at.exception
    assert any("differ with q < 0.05" in m.value for m in at.markdown)

    at.selectbox(key="timeline_site").select("SITE-A").run()  # other batches: the screen is asked for again
    assert not at.exception
    assert "Screen all 619 parameters" in [b.label for b in at.button]
