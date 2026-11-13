"""The monitoring pages' calculations: periods, scorecards, pipeline, OOS, sites. No Streamlit.

Everything compares a **recent window** (the last ``recent_days`` of the
chosen period) with the **baseline** (the rest of the period, before it). The
same scorecard serves every page, so a status means the same thing everywhere.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy import stats as sps

from . import stats as S
from .config import DashboardConfig
from .plots import plot_values
from .spc import control_charts

# Process days in process order; days the catalogue adds are appended as they come.
PROCESS_DAYS = [
    "Apheresis", "Planning", "Context", "Vector CoA", "D0", "D0-D3", "D1", "D3", "D3-D10", "D6", "D6-D8",
    "D6-D10", "D8", "D8-D10", "D10", "Cryopreservation", "Final Product", "Post-Thaw", "Post-Release",
]
DEFAULT_STAGES = [
    {"label": "Apheresis", "column": "Date of Apheresis Collection"},
    {"label": "Day 0 · selection", "process_day": "D0"},
    {"label": "Day 1 · activation", "process_day": "D1"},
    {"label": "Day 3 · transduction", "process_day": "D3"},
    {"label": "Day 6 · expansion", "process_day": "D6"},
    {"label": "Day 8 · expansion", "process_day": "D8"},
    {"label": "Day 10 · harvest", "process_day": "D10"},
    {"label": "Cryopreserved", "column": "Date of Cryopreservation"},
    {"label": "Final product tested", "process_day": "Final Product"},
    {"label": "Shipped", "column": "Date of Product Shipment"},
    {"label": "Infused", "column": "Date of Infusion"},
]
DEFAULT_KEY_CQAS = [
    "FP Flow CAR+ (%)", "FP Flow CD3+ Viability (%)", "FP Flow CD3+ (%)",
    "Provirus Vector Copy Number (copies/transduced cell)", "Dose (CAR+ viable cells/kg)",
    "FP Post-Thaw Viability (%)", "Endotoxin (EU/mL)", "IFN Gamma",
]
STAGE_SHARE = 0.5  # a process-day stage is reached when this share of its parameters has a value
SHIFT_SD = 0.5  # "Shifted": the recent median moved at least this many baseline SD (and q < ALPHA)
ALPHA = 0.05
OUTSIDE_SD = 3.0  # "outside": beyond the baseline median by this many robust SD
UNUSUAL = (0.01, 0.99)  # a value is unusual outside these quantiles of the completed batches

STATUS_SHIFTED, STATUS_WATCH, STATUS_STABLE, STATUS_FEW = "Shifted", "Watch", "Stable", "Too few batches"
STATUS_ORDER = [STATUS_SHIFTED, STATUS_WATCH, STATUS_STABLE, STATUS_FEW]


# --------------------------------------------------------------------------- settings


@dataclass
class Stage:
    label: str
    column: str | None = None  # a date column: reached when it has a date
    process_day: str | None = None  # or a process day: reached when its parameters have values


@dataclass
class Settings:
    """The ``monitor`` section of the config, with defaults, kept to what the data has."""

    recent_days: int = 90
    pipeline_days: int = 45  # an unfinished batch older than this is no longer counted as in process
    truthy: set[str] = field(default_factory=lambda: {"y", "yes", "true", "1"})
    oos_flag: str | None = None
    oos_types: list[str] = field(default_factory=list)
    stages: list[Stage] = field(default_factory=list)
    closed_from: str | None = None  # the stage from which a batch has left the pipeline
    functional_type: str | None = None  # metadata columns the pages group parameters by
    process_day: str | None = None
    variation_source: str | None = None
    key_cqas: list[str] = field(default_factory=list)
    baseline: tuple[pd.Timestamp, pd.Timestamp] | None = None  # a fixed baseline period, when the config sets one
    material_sources: tuple[str, ...] = ("Raw material / vector",)  # variation sources whose categories are lots


def settings(cfg: DashboardConfig, df: pd.DataFrame, params: pd.DataFrame) -> Settings:
    raw = cfg.monitor
    s = Settings(recent_days=int(raw.get("recent_days", 90)), pipeline_days=int(raw.get("pipeline_days", 45)))
    if raw.get("true_values"):
        s.truthy = {str(v).strip().lower() for v in raw["true_values"]}
    for key, default in (("functional_type", "Functional Type"), ("process_day", "Process Day"),
                         ("variation_source", "Variation Source")):
        column = (raw.get("group_columns") or {}).get(key, default)
        setattr(s, key, column if column in params.columns else None)

    oos = raw.get("oos") or {}
    flag = oos.get("flag", "OOS? (Y/N)")
    s.oos_flag = flag if flag in df.columns else None
    types = oos.get("types")
    if types is None:  # every "<attribute> OOS (Y/N)" column
        types = [c for c in df.columns if re.search(r"\bOOS\s*\(Y/N\)\s*$", str(c)) and c != flag]
    s.oos_types = [c for c in types if c in df.columns]

    days = set(params[s.process_day].dropna().astype(str)) if s.process_day else set()
    for item in raw.get("stages") or DEFAULT_STAGES:
        stage = Stage(str(item["label"]), item.get("column"), item.get("process_day"))
        if (stage.column and stage.column in df.columns) or (stage.process_day and stage.process_day in days):
            s.stages.append(stage)
    labels = [st.label for st in s.stages]
    closed = raw.get("closed_from", "Shipped")
    s.closed_from = closed if closed in labels else (labels[-1] if labels else None)
    s.key_cqas = [c for c in raw.get("key_cqas") or DEFAULT_KEY_CQAS if c in df.columns]
    fixed = raw.get("baseline") or {}
    if fixed.get("start") and fixed.get("end"):
        s.baseline = (pd.Timestamp(str(fixed["start"])), pd.Timestamp(str(fixed["end"])))
    if raw.get("material_sources"):
        s.material_sources = tuple(str(x) for x in raw["material_sources"])
    return s


def flag(series: pd.Series, truthy: set[str]) -> pd.Series:
    """A Y/N column as booleans; missing stays missing (nullable boolean)."""
    text = series.astype("string").str.strip().str.lower()
    return text.isin(truthy).astype("boolean").mask(text.isna() | (text == ""))


def day_order(days) -> list[str]:
    """Process days in process order."""
    present = [str(d) for d in pd.unique(pd.Series(days).dropna())]
    return [d for d in PROCESS_DAYS if d in present] + sorted(d for d in present if d not in PROCESS_DAYS)


# --------------------------------------------------------------------------- values


def numeric_frame(df: pd.DataFrame, params: pd.DataFrame, cfg: DashboardConfig) -> tuple[pd.DataFrame, dict[str, str]]:
    """Every parameter that plots as a number, as floats, and each one's unit suffix.

    Follows the plot: numbers, ratios, durations in minutes, datetimes as days
    from manufacturing start (or hour of day), untyped columns that hold numbers.
    Categorical parameters are left out.
    """
    dates = df[cfg.col("manufacturing_date")]
    columns, units = {}, {}
    for name, vtype in zip(params["name"], params["type"]):
        if name not in df.columns or name == cfg.col("manufacturing_date"):
            continue
        kind = vtype.strip().lower()
        if kind == "categorical" or kind.startswith("["):
            continue
        if kind == "numeric" and pd.api.types.is_numeric_dtype(df[name]):
            y, unit = df[name].astype(float), ""
        else:
            y, order, unit = plot_values(df[name], vtype, dates, cfg.dayfirst)
            if order is not None:
                continue
        if y.notna().any():
            columns[name], units[name] = y.astype(float), unit
    return pd.DataFrame(columns, index=df.index), units


def windows(dates: pd.Series, start, end, recent_days: int, fixed: tuple | None = None) -> tuple[pd.Series, pd.Series]:
    """(recent, baseline) masks: the last ``recent_days`` of [start, end], and the days of the period before them.

    With ``fixed`` (start, end; inclusive) the baseline is that date range
    instead, wherever it lies, less any day of the recent window.
    """
    d = pd.to_datetime(dates)
    end = pd.Timestamp(end).normalize() + pd.Timedelta(days=1)
    inside = (d >= pd.Timestamp(start)) & (d < end)
    cut = end - pd.Timedelta(days=recent_days)
    recent = inside & (d >= cut)
    if fixed is None:
        return recent, inside & (d < cut)
    in_fixed = (d >= pd.Timestamp(fixed[0])) & (d < pd.Timestamp(fixed[1]).normalize() + pd.Timedelta(days=1))
    return recent, in_fixed & ~recent


def robust_sd(x: np.ndarray) -> float:
    """1.4826 × MAD; the standard deviation when half the values are equal; NaN without spread."""
    x = x[np.isfinite(x)]
    if len(x) < 2:
        return np.nan
    mad = 1.4826 * np.median(np.abs(x - np.median(x)))
    return float(mad or x.std(ddof=1) or np.nan)


def longest_run(side: np.ndarray) -> int:
    """The longest stretch of equal non-zero values in ``side`` (+1 above the centre, -1 below, 0 on it)."""
    best = run = 0
    prev = 0
    for v in side:
        run = run + 1 if v and v == prev else (1 if v else 0)
        prev, best = v, max(best, run)
    return best


def scorecard(
    values: pd.DataFrame, dates: pd.Series, recent: pd.Series, baseline: pd.Series, spc: dict | None = None,
    directions: dict[str, str] | None = None, period: pd.Series | None = None,
) -> pd.DataFrame:
    """One row per parameter: the recent window against the baseline.

    - ``recent`` / ``baseline``: the two medians; ``shift``: their difference in
      baseline robust SD; ``p``: Mann-Whitney; ``q``: Benjamini-Hochberg over the rows
    - ``outside``: recent batches beyond the baseline median ± OUTSIDE_SD robust SD
    - ``ewma``: recent batches where the EWMA (normal from the baseline) is outside its limits;
      ``ewma_now``: whether it is outside at the latest batch
    - ``run``: the longest recent run on one side of the baseline median
    - ``trend``: the monthly medians over ``period`` (default: both windows), for a sparkline;
      the EWMA runs over the same batches
    - ``status``: Shifted (q < ALPHA and |shift| >= SHIFT_SD), Watch (weaker
      evidence: q < ALPHA with a smaller shift, the EWMA outside its limits at
      the latest batch, or more batches outside than chance explains), Stable,
      or Too few batches (< MIN_BATCHES in a window)
    """
    d = pd.to_datetime(dates)
    both = (recent | baseline if period is None else period | recent | baseline) & d.notna()
    month = d[both].dt.to_period("M")
    months = pd.period_range(month.min(), month.max(), freq="M") if both.any() else []
    rows = []
    for name in values.columns:
        x = values[name]
        r, b = x[recent & x.notna()].to_numpy(float), x[baseline & x.notna()].to_numpy(float)
        row = dict(parameter=name, n_recent=len(r), n_baseline=len(b), recent=np.nan, baseline=np.nan,
                   shift=np.nan, p=np.nan, outside=0, ewma=0, ewma_now=False, run=0, trend=[], status=STATUS_FEW)
        if len(r):
            row["recent"] = float(np.median(r))
        if len(b):
            row["baseline"] = float(np.median(b))
        monthly = x[both].groupby(month).median().reindex(months)
        row["trend"] = monthly.interpolate(limit_direction="both").round(6).tolist() if monthly.notna().any() else []
        if len(r) >= S.MIN_BATCHES and len(b) >= S.MIN_BATCHES:
            sd = robust_sd(b)
            if np.isfinite(sd):
                row["shift"] = (row["recent"] - row["baseline"]) / sd
                row["outside"] = int((np.abs(r - row["baseline"]) > OUTSIDE_SD * sd).sum())
            if np.ptp(np.concatenate([r, b])) > 0:
                row["p"] = float(sps.mannwhitneyu(r, b, alternative="two-sided").pvalue)
            else:
                row["p"] = 1.0
            ordered = x[recent & x.notna()].loc[d[recent & x.notna()].sort_values(kind="stable").index]
            row["run"] = longest_run(np.sign(ordered.to_numpy(float) - row["baseline"]))
            charts = control_charts(d[both], x[both], reference=baseline[both],
                                    direction=(directions or {}).get(name, "both"), **(spc or {}))
            if charts is not None:
                signal = pd.Series(charts.ewma_signal, index=charts.index)
                in_recent = signal[signal.index.isin(recent.index[recent])]
                row["ewma"] = int(in_recent.sum())
                row["ewma_now"] = bool(len(in_recent) and in_recent.iloc[-1])
            row["status"] = STATUS_STABLE
        rows.append(row)
    out = pd.DataFrame(rows)
    if out.empty:
        return out.assign(q=[])
    out["q"] = S.benjamini_hochberg(out["p"])
    tested = out["status"] == STATUS_STABLE
    significant = tested & (out["q"] < ALPHA)
    # More batches beyond 3 SD than a normal process gives: at least 2, and over 2% of the window.
    many_outside = (out["outside"] >= 2) & (out["outside"] > 0.02 * out["n_recent"])
    watch = tested & (significant | out["ewma_now"] | many_outside)
    out.loc[watch, "status"] = STATUS_WATCH
    out.loc[significant & (out["shift"].abs() >= SHIFT_SD), "status"] = STATUS_SHIFTED
    rank = out["status"].map({s: i for i, s in enumerate(STATUS_ORDER)})
    return out.assign(_rank=rank, _abs=out["shift"].abs().fillna(0)).sort_values(
        ["_rank", "_abs"], ascending=[True, False], kind="stable"
    ).drop(columns=["_rank", "_abs"]).reset_index(drop=True)


def monthly_z(values: pd.DataFrame, dates: pd.Series, period: pd.Series, baseline: pd.Series) -> pd.DataFrame:
    """Per parameter (rows) and month (columns): the monthly mean's distance from the baseline mean, in standard errors.

    The x-bar chart of every parameter at once: centre and sigma (mean moving
    range / 1.128, in date order) come from the baseline; a month beyond ±3 is
    outside its control limits. Months with fewer than 3 values stay empty.
    """
    d = pd.to_datetime(dates)
    ok = period & d.notna()
    month = d[ok].dt.to_period("M")
    months = pd.period_range(month.min(), month.max(), freq="M") if ok.any() else []
    order = d[baseline & d.notna()].sort_values(kind="stable").index
    out = {}
    for name in values.columns:
        base = values.loc[order, name].dropna().to_numpy(float)
        if len(base) < S.MIN_BATCHES:
            continue
        sigma = np.abs(np.diff(base)).mean() / 1.128 or base.std()
        if not sigma:
            continue
        g = values.loc[ok, name].groupby(month)
        n, mean = g.count().reindex(months), g.mean().reindex(months)
        out[name] = ((mean - base.mean()) / (sigma / np.sqrt(n))).where(n >= 3)
    frame = pd.DataFrame(out).T
    frame.columns = [m.to_timestamp() for m in months][: frame.shape[1]]
    return frame


def categorical_shift(values: pd.Series, recent: pd.Series, baseline: pd.Series) -> tuple[pd.DataFrame, float]:
    """Each category's share of the recent window and of the baseline, and the p-value that they differ.

    Categories with fewer than MIN_BATCHES batches are grouped as "Other". The
    test (Fisher's exact for two categories, else a Monte Carlo chi-square) is
    NaN when a window has fewer than MIN_BATCHES batches.
    """
    text = values.astype("string").str.strip()
    use = (recent | baseline) & text.notna()
    c = S.compare_categorical(text[use], recent[use])
    rows = c.rows.assign(recent_n=c.rows["k"], baseline_n=c.rows["n"] - c.rows["k"])
    rows["recent"] = rows["recent_n"] / max(c.n1, 1)
    rows["baseline"] = rows["baseline_n"] / max(c.n2, 1)
    rows = rows.sort_values("baseline", ascending=False, kind="stable").reset_index(drop=True)
    return rows[["category", "recent_n", "recent", "baseline_n", "baseline"]], c.p


# --------------------------------------------------------------------------- OOS


def oos_by_type(df: pd.DataFrame, s: Settings, recent: pd.Series, baseline: pd.Series) -> pd.DataFrame:
    """Per OOS type: the rate in the recent window and the baseline, with Wilson intervals and Fisher's exact test."""
    rows = []
    for column in ([s.oos_flag] if s.oos_flag else []) + s.oos_types:
        f = flag(df[column], s.truthy)
        r, b = f[recent].dropna().astype(bool), f[baseline].dropna().astype(bool)
        if not len(r) and not len(b):
            continue
        rr, rb = S.wilson(int(r.sum()), len(r)), S.wilson(int(b.sum()), len(b))
        p = np.nan
        if len(r) and len(b):
            p = float(sps.fisher_exact([[rr.k, rr.n - rr.k], [rb.k, rb.n - rb.k]]).pvalue)
        rows.append(dict(type=column, recent_k=rr.k, recent_n=rr.n, recent=rr.p, recent_lo=rr.lo, recent_hi=rr.hi,
                         baseline_k=rb.k, baseline_n=rb.n, baseline=rb.p, p=p))
    return pd.DataFrame(rows)


def oos_label(column: str) -> str:
    """'CAR% OOS (Y/N)' -> 'CAR%'; the overall flag -> 'Any OOS'."""
    short = re.sub(r"\s*\(Y/N\)\s*$", "", str(column)).strip()
    short = re.sub(r"\s*OOS\??$", "", short).strip()
    return short or "Any OOS"


# --------------------------------------------------------------------------- pipeline


def _stage_reached(df: pd.DataFrame, params: pd.DataFrame, s: Settings) -> pd.DataFrame:
    """Per batch (rows) and stage (columns): whether the stage has data."""
    reached = {}
    for stage in s.stages:
        if stage.column:
            col = df[stage.column]
            reached[stage.label] = col.notna() & (col.astype("string").str.strip() != "")
        else:
            names = params.loc[params[s.process_day].astype(str) == stage.process_day, "name"]
            names = [n for n in names if n in df.columns]
            reached[stage.label] = df[names].notna().mean(axis=1) >= STAGE_SHARE if names else False
    return pd.DataFrame(reached, index=df.index)


def stage_dates(df: pd.DataFrame, s: Settings, cfg: DashboardConfig) -> pd.DataFrame:
    """The date-column stages as datetimes, one column per stage label, plus 'Manufacture start'."""
    out = {"Manufacture start": pd.to_datetime(df[cfg.col("manufacturing_date")])}
    for stage in s.stages:
        if stage.column:
            col = df[stage.column]
            out[stage.label] = col if pd.api.types.is_datetime64_any_dtype(col) else pd.to_datetime(
                col, format="mixed", dayfirst=cfg.dayfirst, errors="coerce")
    return pd.DataFrame(out, index=df.index)


def as_of(df: pd.DataFrame, s: Settings, cfg: DashboardConfig) -> pd.Timestamp:
    """The date the data runs to: the latest date recorded, today at most."""
    latest = stage_dates(df, s, cfg).max().max()
    today = pd.Timestamp.today().normalize()
    return today if pd.isna(latest) else min(latest.normalize(), today)


def pipeline(df: pd.DataFrame, params: pd.DataFrame, s: Settings, cfg: DashboardConfig) -> pd.DataFrame:
    """Per batch: the last stage with data, days since manufacturing start, and whether it is in process.

    ``state``: "closed" from the ``closed_from`` stage on; "in process" before
    it and started at most ``pipeline_days`` before the data's last date;
    "not closed" for older batches without it (terminated, or never recorded).
    """
    reached = _stage_reached(df, params, s)
    labels = list(reached.columns)
    position = np.where(reached.to_numpy(bool), np.arange(len(labels)), -1).max(axis=1) if labels else np.full(len(df), -1)
    closed_at = labels.index(s.closed_from) if s.closed_from in labels else len(labels)
    start = pd.to_datetime(df[cfg.col("manufacturing_date")])
    age = (as_of(df, s, cfg) - start).dt.days
    closed = reached.iloc[:, closed_at:].any(axis=1) if labels else pd.Series(False, index=df.index)
    state = np.where(closed, "closed", np.where(age <= s.pipeline_days, "in process", "not closed"))
    out = pd.DataFrame({
        "stage": [labels[i] if i >= 0 else "Not started" for i in position], "stage_index": position,
        "days": age, "state": state,
    }, index=df.index)
    out.loc[start.isna(), "state"] = "not closed"
    return out


def unusual_values(values: pd.DataFrame, history: pd.Series, rows: pd.Series) -> pd.DataFrame:
    """For the batches in ``rows``: per parameter, the percentile among the ``history`` batches where it is unusual.

    Returns a long table (index label, parameter, value, median, percentile,
    z) of the values outside the UNUSUAL quantiles of the history, most
    extreme first. Parameters with fewer than 30 history values are skipped.
    """
    hist = values[history]
    enough = hist.columns[hist.notna().sum() >= 30]
    hist, current = hist[enough], values.loc[rows, enough]
    lo, hi = hist.quantile(UNUSUAL[0]), hist.quantile(UNUSUAL[1])
    out = (current.lt(lo, axis=1) | current.gt(hi, axis=1)) & current.notna()
    long = current.where(out).stack().dropna().rename("value").reset_index()
    long.columns = ["row", "parameter", "value"]
    if long.empty:
        return long.assign(median=[], percentile=[], z=[])
    med = hist.median()
    sd = hist.apply(lambda c: robust_sd(c.to_numpy(float)))
    long["median"] = long["parameter"].map(med)
    long["z"] = (long["value"] - long["median"]) / long["parameter"].map(sd)
    sorted_hist = {p: np.sort(hist[p].dropna().to_numpy(float)) for p in long["parameter"].unique()}
    long["percentile"] = [
        100 * (np.searchsorted(sorted_hist[p], v, "left") + np.searchsorted(sorted_hist[p], v, "right")) / 2 / len(sorted_hist[p])
        for p, v in zip(long["parameter"], long["value"])
    ]
    return long.assign(_a=long["z"].abs().fillna(np.inf)).sort_values("_a", ascending=False).drop(columns="_a").reset_index(drop=True)


def lead_times(df: pd.DataFrame, s: Settings, cfg: DashboardConfig) -> pd.DataFrame:
    """Days between consecutive dated stages per batch, and from the first to the last (when both exist).

    Negative and absurd (> 2 years) gaps are dropped as recording errors.
    """
    dates = stage_dates(df, s, cfg)
    order = ["Manufacture start"] + [st.label for st in s.stages if st.column]
    # Manufacture start goes after a dated stage that precedes day 0 (apheresis).
    first_day = next((i for i, st in enumerate(s.stages) if st.process_day), len(s.stages))
    before = [st.label for st in s.stages[:first_day] if st.column]
    order = before + ["Manufacture start"] + [c for c in order[1:] if c not in before]
    out = {}
    for a, b in zip(order, order[1:]):
        out[f"{a} → {b}"] = (dates[b] - dates[a]).dt.total_seconds() / 86400
    if len(order) > 2:
        out[f"{order[0]} → {order[-1]}"] = (dates[order[-1]] - dates[order[0]]).dt.total_seconds() / 86400
    frame = pd.DataFrame(out, index=df.index)
    return frame.where((frame >= 0) & (frame < 730))


# --------------------------------------------------------------------------- sites


def site_summary(df: pd.DataFrame, s: Settings, cfg: DashboardConfig, period: pd.Series, leads: pd.DataFrame) -> pd.DataFrame:
    """Per site over the period: batches, OOS rate with its Wilson interval, and the median of each lead time."""
    sites = df.loc[period, cfg.col("site")].astype("string")
    oos = flag(df[s.oos_flag], s.truthy) if s.oos_flag else None
    rows = []
    for site in sorted(sites.dropna().unique()):
        at = period & (df[cfg.col("site")].astype("string") == site)
        row = dict(site=site, batches=int(at.sum()))
        if oos is not None:
            f = oos[at].dropna().astype(bool)
            r = S.wilson(int(f.sum()), len(f))
            row.update(oos_k=r.k, oos_n=r.n, oos=r.p, oos_lo=r.lo, oos_hi=r.hi)
        for column in leads.columns:
            row[column] = leads.loc[at, column].median()
        rows.append(row)
    return pd.DataFrame(rows)


def site_screen(values: pd.DataFrame, sites: pd.Series, period: pd.Series) -> pd.DataFrame:
    """Per parameter: do the sites differ? Kruskal-Wallis with BH q-values, and the largest gap between site medians.

    ``gap``: the distance between the highest and the lowest site median, in
    pooled within-site robust SD; ``low`` / ``high`` name those sites. Sites
    with fewer than MIN_BATCHES values of a parameter are left out of its test.
    """
    site = sites.astype("string")
    rows = []
    for name in values.columns:
        x = values.loc[period, name]
        groups = {k: g.dropna().to_numpy(float) for k, g in x.groupby(site[period])}
        groups = {k: g for k, g in groups.items() if len(g) >= S.MIN_BATCHES}
        if len(groups) < 2:
            continue
        medians = {k: float(np.median(g)) for k, g in groups.items()}
        low, high = min(medians, key=medians.get), max(medians, key=medians.get)
        within = np.concatenate([g - medians[k] for k, g in groups.items()])
        sd = robust_sd(within)
        p = 1.0
        if np.ptp(np.concatenate(list(groups.values()))) > 0:
            p = float(sps.kruskal(*groups.values()).pvalue)
        rows.append(dict(parameter=name, n=int(sum(map(len, groups.values()))), sites=len(groups), p=p,
                         gap=(medians[high] - medians[low]) / sd if np.isfinite(sd) else np.nan,
                         low=low, high=high, **{f"median · {k}": v for k, v in medians.items()}))
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["q"] = S.benjamini_hochberg(out["p"])
    return out.assign(_a=out["gap"].abs().fillna(0)).sort_values(["q", "_a"], ascending=[True, False]).drop(
        columns="_a").reset_index(drop=True)


# --------------------------------------------------------------------------- across process days

_DAY = re.compile(r"\b(?:Day|D)\s?(0|1|3|6|8|10)\b", re.IGNORECASE)


def day_families(names: list[str], least: int = 3) -> dict[str, dict[int, str]]:
    """Parameters measured on several process days: {name without the day: {day: parameter}}.

    'Day 6 Glucose G-Rex A (g/L)' and 'Day 8 Glucose G-Rex A (g/L)' share the
    family 'Glucose G-Rex A (g/L)'. Families with fewer than ``least`` days are dropped.
    """
    families: dict[str, dict[int, str]] = {}
    for name in names:
        found = _DAY.findall(name)
        if len(found) != 1:
            continue
        stem = re.sub(r"\s+", " ", _DAY.sub("", name)).strip(" -_")
        families.setdefault(stem, {})[int(found[0])] = name
    return {k: dict(sorted(v.items())) for k, v in sorted(families.items()) if len(v) >= least}


def family_profile(values: pd.DataFrame, family: dict[int, str], recent: pd.Series, baseline: pd.Series) -> pd.DataFrame:
    """Per process day of a family: the baseline's median and middle half, and the recent median."""
    rows = []
    for day, name in family.items():
        b, r = values.loc[baseline, name].dropna(), values.loc[recent, name].dropna()
        rows.append(dict(day=day, parameter=name, baseline=b.median(), q1=b.quantile(0.25), q3=b.quantile(0.75),
                         recent=r.median(), n_baseline=len(b), n_recent=len(r)))
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- material lots


def lot_table(lots: pd.Series, dates: pd.Series, rows: pd.Series) -> pd.DataFrame:
    """Per lot used in ``rows``: first and last use, the median date of use and the number of batches, in order of use."""
    text = lots.astype("string").str.strip()
    ok = rows & text.notna() & (text != "") & dates.notna()
    d = pd.to_datetime(dates[ok])
    g = d.groupby(text[ok])
    out = pd.DataFrame({"first": g.min(), "last": g.max(), "middle": g.median(), "n": g.size()})
    return out.sort_values(["middle", "first"], kind="stable").rename_axis("lot").reset_index()


def lot_changes(values: pd.Series, lots: pd.Series, dates: pd.Series, rows: pd.Series) -> pd.DataFrame:
    """Each lot against the lot used before it: did the value move at the change?

    Lots are ordered by their median date of use; lots with fewer than
    MIN_BATCHES values are skipped, so a lot is compared with the nearest
    earlier lot that has enough. ``shift``: the difference of the two lot
    medians in within-lot robust SD (pooled over all lots); ``p``: Mann-Whitney.
    """
    text = lots.astype("string").str.strip()
    table = lot_table(lots, dates, rows)
    ok = rows & values.notna()
    groups = {lot: values[ok & (text == lot)].to_numpy(float) for lot in table["lot"]}
    kept = table[[len(groups[lot]) >= S.MIN_BATCHES for lot in table["lot"]]].reset_index(drop=True)
    columns = ["before", "after", "date", "n_before", "n_after", "median_before", "median_after", "shift", "p"]
    if len(kept) < 2:
        return pd.DataFrame(columns=columns)
    sd = robust_sd(np.concatenate([groups[lot] - np.median(groups[lot]) for lot in kept["lot"]]))
    out = []
    for a, b in zip(kept.itertuples(), kept.iloc[1:].itertuples()):
        x, y = groups[a.lot], groups[b.lot]
        p = float(sps.mannwhitneyu(y, x, alternative="two-sided").pvalue) if np.ptp(np.concatenate([x, y])) > 0 else 1.0
        mx, my = float(np.median(x)), float(np.median(y))
        out.append([a.lot, b.lot, b.first, len(x), len(y), mx, my, (my - mx) / sd if np.isfinite(sd) else np.nan, p])
    return pd.DataFrame(out, columns=columns)


def material_screen(values: pd.Series, materials: pd.DataFrame, dates: pd.Series, rows: pd.Series) -> tuple[pd.DataFrame, pd.DataFrame]:
    """For one parameter: every material's lot changes, and a summary per material.

    Returns (summary, changes). ``changes`` is lot_changes for every column of
    ``materials`` with a ``material`` column and ``q``: Benjamini-Hochberg over
    all lot changes of all materials. ``summary`` per material: lots used,
    changes tested, how many moved the value (q < ALPHA), the largest shift
    among those (else among all) and the smallest q; most moved first.
    """
    parts, summary = [], []
    for material in materials.columns:
        changes = lot_changes(values, materials[material], dates, rows)
        used = lot_table(materials[material], dates, rows)
        parts.append(changes.assign(material=material))
        summary.append(dict(material=material, lots=len(used), tested=len(changes)))
    changes = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    summary = pd.DataFrame(summary)
    if changes.empty or summary.empty:
        return summary.assign(moved=0, shift=np.nan, q=np.nan), changes.assign(q=[])
    changes["q"] = S.benjamini_hochberg(changes["p"])
    rows_out = []
    for material, part in changes.groupby("material", sort=False):
        moved = part[part["q"] < ALPHA]
        pool = moved if len(moved) else part
        rows_out.append(dict(material=material, moved=len(moved), q=part["q"].min(),
                             shift=pool["shift"].loc[pool["shift"].abs().idxmax()] if pool["shift"].notna().any() else np.nan))
    summary = summary.merge(pd.DataFrame(rows_out), on="material", how="left").fillna({"moved": 0})
    summary["moved"] = summary["moved"].astype(int)
    return summary.assign(_a=summary["shift"].abs().fillna(0)).sort_values(
        ["moved", "_a"], ascending=[False, False], kind="stable").drop(columns="_a").reset_index(drop=True), changes
