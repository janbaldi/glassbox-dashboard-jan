"""The statistics layer's content: what the card says, and the numbers behind it.

Builds, for the plotted parameter and batches, the plain-language sentences,
the rows for the export (every estimate with its interval, p-value, counts and
method) and the data for the charts. No Streamlit, so it can be tested; the
view (``views.statistics``) and the export (``report``) only present it.

The two groups are the plotted batches of interest and the plotted background
batches. When they are a glassbox run's own sets, the model's statistics are
added.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

import numpy as np
import pandas as pd

from . import stats as S
from .plots import BACKGROUND_LABEL, SET_COLUMN, plot_values


@dataclass
class Groups:
    first: str  # plural: "batches of interest"
    second: str
    first_one: str  # singular: "batch of interest"
    second_one: str
    rate: str  # "share of batches of interest"
    run: bool = False  # the groups are a glassbox run's: the model statistics apply


GENERIC_GROUPS = Groups(
    "batches of interest", "background batches", "batch of interest", "background batch",
    "share of batches of interest",
)
RUN_GROUPS = replace(GENERIC_GROUPS, run=True)


def groups_for(data: pd.DataFrame, batch_col: str, interest_ids: set[str] | None,
               background_ids: set[str] | None) -> Groups:
    """RUN_GROUPS when every plotted batch of interest is in the run's interest set and every background batch in its background."""
    if interest_ids is None or background_ids is None:
        return GENERIC_GROUPS
    first = data[SET_COLUMN] != BACKGROUND_LABEL
    ids = data[batch_col]
    if ids[first].isin(interest_ids).all() and ids[~first].isin(background_ids).all() and first.any():
        return RUN_GROUPS
    return GENERIC_GROUPS


def _cap(text: str) -> str:
    """First letter upper case, the rest as written ("PR-AUC" stays "PR-AUC")."""
    return text[:1].upper() + text[1:]


def _row(section, parameter, statistic, estimate=math.nan, lo=math.nan, hi=math.nan, p=math.nan,
         n1=None, n2=None, method="", note="") -> dict:
    return {
        "section": section, "parameter": parameter, "statistic": statistic, "estimate": estimate,
        "ci_low": lo, "ci_high": hi, "p": p, "n_first": n1, "n_second": n2,
        "method": S.METHODS.get(method, method), "note": note,
    }


@dataclass
class Evidence:
    parameter: str
    groups: Groups
    kind: str  # "number", "category" or "none"
    headline: str
    tested: bool = False  # enough batches in both groups for the comparison (and so for the charts)
    lines: list[str] = field(default_factory=list)
    rows: list[dict] = field(default_factory=list)
    first_values: np.ndarray | None = None
    second_values: np.ndarray | None = None
    by_value: pd.DataFrame | None = None
    categories: pd.DataFrame | None = None
    overall: S.Rate | None = None
    consistency: pd.DataFrame | None = None
    unit: str = ""


def build(
    data: pd.DataFrame,
    parameter: str,
    value_type: str,
    date_col: str,
    groups: Groups,
    dayfirst: bool = False,
    site_col: str | None = None,
    model=None,
    batch_col: str | None = None,
) -> Evidence:
    """The evidence card for ``parameter`` over the plotted rows ``data``.

    ``model`` (a ``glassbox.ModelRun``) adds the model's reading of the
    batches of interest, for a run's own groups only.
    """
    first = (data[SET_COLUMN] != BACKGROUND_LABEL).to_numpy()
    y, order, unit = plot_values(data[parameter], value_type, data[date_col], dayfirst)
    ev = Evidence(parameter, groups, "none", "", unit=unit)
    missing = y.isna().to_numpy()
    if order is None:
        _numeric(ev, pd.to_numeric(y, errors="coerce").astype(float), first, data, date_col, site_col)
    else:
        _categorical(ev, y, first, data[date_col])
    _missing(ev, missing, first)
    if model is not None and groups.run and batch_col:
        _model(ev, model, data.loc[first, batch_col].tolist())
    return ev


def _numeric(ev: Evidence, y: pd.Series, first: np.ndarray, data, date_col, site_col) -> None:
    g, p = ev.groups, ev.parameter
    ev.kind = "number"
    a, b = y[first].dropna(), y[~first].dropna()
    ev.first_values, ev.second_values = a.to_numpy(), b.to_numpy()
    c = S.compare_numeric(a, b)
    ev.tested = c.tested
    method_rows = [
        _row("parameter", p, f"median, {g.first}", c.median1, n1=c.n1),
        _row("parameter", p, f"median, {g.second}", c.median2, n2=c.n2),
    ]
    if not c.tested:
        ev.headline = (
            f"Too few batches to compare {p}: {c.n1:,} {g.first} and {c.n2:,} {g.second} have a value, "
            f"and at least {S.MIN_BATCHES} of each are needed."
        )
        ev.rows += method_rows
        return
    ev.headline = (
        f"{p} is {c.direction} in {g.first}." if c.direction
        else f"No clear difference in {p} between {g.first} and {g.second}."
    )
    ev.lines.append(
        f"Median {S.fmt_num(c.median1)} in {g.first} and {S.fmt_num(c.median2)} in {g.second}; "
        f"typical difference {c.shift:+.3g} (95% CI {c.shift_lo:+.3g} to {c.shift_hi:+.3g})."
    )
    ev.lines.append(
        f"Comparing a random {g.first_one} with a random {g.second_one}, the {g.first_one} has the higher "
        f"value {S.fmt_pct(c.auc)} of the time (AUC {c.auc:.2f}, 95% CI {c.auc_lo:.2f}–{c.auc_hi:.2f}; "
        f"Mann–Whitney {S.fmt_p(c.p)}; {c.n1:,} vs {c.n2:,} batches)."
    )
    q = S.quarters(data[date_col])
    w = S.van_elteren(y, pd.Series(first, index=y.index), q)
    if w.tested:
        ev.lines.append(_within_sentence(g, c.direction, w, f"AUC {w.auc:.2f}, van Elteren {S.fmt_p(w.p)}",
                                         higher=w.auc > 0.5))
        ev.rows.append(_row("within quarters", p, "AUC within calendar quarters", w.auc, p=w.p, n1=w.n1, n2=w.n2,
                            method="within_numbers", note=f"{w.strata} quarters"))
    ev.rows += method_rows + [
        _row("parameter", p, "typical difference (Hodges–Lehmann)", c.shift, c.shift_lo, c.shift_hi,
             n1=c.n1, n2=c.n2, method="shift"),
        _row("parameter", p, "AUC", c.auc, c.auc_lo, c.auc_hi, n1=c.n1, n2=c.n2, method="auc"),
        _row("parameter", p, "Mann–Whitney test", p=c.p, n1=c.n1, n2=c.n2, method="rank_test"),
    ]

    by_value = S.rate_by_value(y, pd.Series(first, index=y.index))
    if by_value is not None:
        ev.by_value = by_value
        low, high = by_value.iloc[0], by_value.iloc[-1]
        ev.lines.append(
            f"{_cap(g.rate)}: {S.fmt_pct(low['rate'])} in the lowest values ({low['group']}), "
            f"{S.fmt_pct(high['rate'])} in the highest ({high['group']})."
        )
        for r in by_value.itertuples():
            ev.rows.append(_row("parameter", p, f"{g.rate}, values {r.group}", r.rate, r.lo, r.hi,
                                n1=r.k, n2=r.n - r.k, method="rate", note=f"{r.k} of {r.n}"))

    ev.consistency = _consistency(ev, y, first, data, date_col, site_col, c)


def _within_sentence(g: Groups, direction: str | None, w, numbers: str, higher: bool | None = None) -> str:
    """The within-quarter result in words: does the difference survive comparing like with like in time?"""
    lead = f"Comparing only batches made in the same quarter (to rule out changes over time):"
    if not w.p < 0.05:
        return f"{lead} no clear difference ({numbers})." if direction is None else (
            f"{lead} the difference is no longer clear ({numbers}); it may come from changes over time."
        )
    if direction is None:
        return f"{lead} a difference shows ({numbers})."
    same = higher is None or (higher == (direction == "higher"))
    return f"{lead} still {direction} ({numbers})." if same else f"{lead} the other way round ({numbers})."


def _consistency(ev, y, first, data, date_col, site_col, overall: S.NumericComparison) -> pd.DataFrame | None:
    """The same comparison per site and per year: does the difference hold everywhere?"""
    g, p = ev.groups, ev.parameter
    parts = []
    first_s = pd.Series(first, index=y.index)
    if site_col and site_col in data:
        parts.append(S.consistency(y, first_s, data[site_col].astype("string")).assign(by="site"))
    years = pd.to_datetime(data[date_col]).dt.year.astype("Int64")
    if years.notna().any():
        parts.append(S.consistency(y, first_s, years).assign(by="year"))
    if not parts:
        return None
    table = pd.concat(parts, ignore_index=True)
    for r in table.itertuples():
        ev.rows.append(_row("consistency", p, f"AUC, {r.by} {r.stratum}", r.auc, r.lo, r.hi,
                            n1=r.n1, n2=r.n2, method="auc",
                            note="" if np.isfinite(r.auc) else f"fewer than {S.MIN_BATCHES} batches in a group"))
    if overall.direction is None:
        return table
    judged = table[table["auc"].notna()]
    if judged.empty:
        return table
    same = judged["auc"] > 0.5 if overall.direction == "higher" else judged["auc"] < 0.5
    counts = []
    for by, prep, word in (("site", "at", "sites"), ("year", "in", "years")):
        part = judged[judged["by"] == by]
        if len(part):
            ok = int(same[part.index].sum())
            counts.append(f"{prep} all {len(part)} {word}" if ok == len(part) else f"{prep} {ok} of {len(part)} {word}")
    other = judged[~same]
    if other.empty:
        ev.lines.append(f"Consistent: {overall.direction} in {g.first} " + " and ".join(counts) + ".")
    else:
        exceptions = ", ".join(f"{r.by} {r.stratum} (AUC {r.auc:.2f})" for r in other.itertuples())
        ev.lines.append(
            f"Not consistent everywhere: {overall.direction} in {g.first} " + " and ".join(counts)
            + f"; the other way round in {exceptions}."
        )
    return table


def _categorical(ev: Evidence, y: pd.Series, first: np.ndarray, date_values: pd.Series) -> None:
    g, p = ev.groups, ev.parameter
    ev.kind = "category"
    c = S.compare_categorical(y, pd.Series(first, index=y.index))
    ev.categories, ev.overall, ev.tested = c.rows, c.overall, c.tested
    for r in c.rows.itertuples():
        ev.rows.append(_row("parameter", p, f"{g.rate}, {r.category}", r.rate, r.lo, r.hi,
                            n1=r.k, n2=r.n - r.k, method="rate", note=f"{r.k} of {r.n}"))
    ev.rows.append(_row("parameter", p, f"{g.rate}, all categories", c.overall.p, c.overall.lo, c.overall.hi,
                        n1=c.n1, n2=c.n2, method="rate"))
    if not c.tested:
        ev.headline = (
            f"Too few batches to compare {p}: {c.n1:,} {g.first} and {c.n2:,} {g.second} have a value "
            f"(at least {S.MIN_BATCHES} of each are needed), or it has a single category."
        )
        return
    ev.rows.append(_row("parameter", p, "difference between categories", p=c.p, n1=c.n1, n2=c.n2, method=c.method))
    differs = c.p < 0.05
    ev.headline = (
        f"The {g.rate} differs between the categories of {p} ({S.fmt_p(c.p)})." if differs
        else f"No clear difference in the {g.rate} between the categories of {p} ({S.fmt_p(c.p)})."
    )
    top, low = c.rows.iloc[0], c.rows.iloc[-1]
    w = S.cmh_categories(y, pd.Series(first, index=y.index), S.quarters(date_values))
    ev.lines.append(
        f"Highest: {top['category']}, {S.wilson(int(top['k']), int(top['n'])).text()}. "
        f"Lowest: {low['category']}, {int(low['k'])} of {int(low['n'])} ({S.fmt_pct(low['rate'])}). "
        f"All batches: {c.overall.text()}."
    )
    if w.tested:
        ev.lines.append(_within_sentence(g, "different" if differs else None, w, f"Cochran–Mantel–Haenszel {S.fmt_p(w.p)}"))
        ev.rows.append(_row("within quarters", p, "difference between categories within calendar quarters", p=w.p,
                            n1=w.n1, n2=w.n2, method="within_categories", note=f"{w.strata} quarters"))
    if (c.rows["category"] == "Other").any():
        ev.lines.append(f"Categories with fewer than {S.MIN_BATCHES} batches are grouped as \"Other\".")


def _missing(ev: Evidence, missing: np.ndarray, first: np.ndarray) -> None:
    g, p = ev.groups, ev.parameter
    r1, r2, pv = S.missing_comparison(pd.Series(missing[first]), pd.Series(missing[~first]))
    ev.rows.append(_row("missing values", p, f"missing, {g.first}", r1.p, r1.lo, r1.hi, n1=r1.n, method="rate",
                        note=f"{r1.k} of {r1.n}"))
    ev.rows.append(_row("missing values", p, f"missing, {g.second}", r2.p, r2.lo, r2.hi, n2=r2.n, method="rate",
                        note=f"{r2.k} of {r2.n}"))
    ev.rows.append(_row("missing values", p, "difference in missing values", p=pv, n1=r1.n, n2=r2.n,
                        method="two_categories"))
    if np.isfinite(pv) and pv < 0.05:
        more = g.first if r1.p > r2.p else g.second
        ev.lines.append(
            f"Missing more often in {more}: {S.fmt_pct(r1.p)} of {g.first} and {S.fmt_pct(r2.p)} of "
            f"{g.second} have no value (Fisher {S.fmt_p(pv)}). Worth checking how the data were recorded."
        )


def _model(ev: Evidence, model, batches: list[str]) -> None:
    p = ev.parameter
    if p not in model.features:
        ev.lines.append(f"Model ({model.name}): not one of its features.")
        return
    d = S.driver_stats(model.contributions, batches, p)
    if not d or not d["n"]:
        return
    top1, top3 = S.wilson(d["top1"], d["n"]), S.wilson(d["top3"], d["n"])
    text = (
        f"Model ({model.name}): pushes the probability up in {d['up']} of {d['n']} batches of interest "
        f"({S.fmt_pct(d['up'] / d['n'])}); the #1 driver in {top1.text()}, a top-3 driver in "
        f"{d['top3']} ({S.fmt_pct(top3.p)})."
    )
    if d["checked"]:
        text += f" The leave-one-out refit reproduces it in {d['reproduced']} of the {d['checked']} batches checked."
    ev.lines.append(text)
    ev.rows += [
        _row("model", p, "pushes the probability up (share of batches of interest)", d["up"] / d["n"], n1=d["n"],
             note=f"{d['up']} of {d['n']}; model {model.name}"),
        _row("model", p, "#1 driver (share of batches of interest)", top1.p, top1.lo, top1.hi, n1=d["n"], method="rate",
             note=f"{d['top1']} of {d['n']}; model {model.name}"),
        _row("model", p, "top-3 driver (share of batches of interest)", top3.p, top3.lo, top3.hi, n1=d["n"], method="rate",
             note=f"{d['top3']} of {d['n']}; model {model.name}"),
        _row("model", p, "reproduced by the leave-one-out refit", d["reproduced"] / d["checked"] if d["checked"] else math.nan,
             n1=d["checked"], note=f"{d['reproduced']} of {d['checked']}; model {model.name}"),
    ]


# --------------------------------------------------------------------------- over time and the model


@dataclass
class OverTime:
    table: pd.DataFrame
    lines: list[str]
    rows: list[dict]


def over_time(data: pd.DataFrame, date_col: str, groups: Groups) -> OverTime:
    """The share of batches of interest per month (p-chart), with the months above the upper limit named."""
    first = pd.Series((data[SET_COLUMN] != BACKGROUND_LABEL).to_numpy(), index=data.index)
    t = S.monthly_rate(data[date_col], first)
    rows = [
        _row("over time", "", f"{groups.rate}, {m:%Y-%m}", r, n1=k, n2=n - k, method="p_chart",
             note=f"{k} of {n}; limits {lo:.3f}–{hi:.3f}" + ("; above the upper limit" if f else ""))
        for m, r, lo, hi, k, n, f in zip(t["month"], t["rate"], t["lcl"], t["ucl"], t["k"], t["n"], t["flagged"])
    ]
    if t.empty:
        return OverTime(t, ["No batches with a manufacturing date."], rows)
    centre = t["centre"].iloc[0]
    flagged = t[t["flagged"]]
    lines = [f"Overall {groups.rate}: {S.fmt_pct(centre)} over {len(t)} months ({int(t['k'].sum()):,} of {int(t['n'].sum()):,} batches)."]
    if flagged.empty:
        lines.append(f"No month is above the upper limit (months with at least {S.MIN_BATCHES} batches).")
    else:
        months = "; ".join(
            f"{r.month:%b %Y}: {r.k} of {r.n} ({S.fmt_pct(r.rate)}, limit {S.fmt_pct(r.ucl)})" for r in flagged.itertuples()
        )
        lines.append(f"Above the upper limit in {len(flagged)} of {len(t)} months: {months}.")
    return OverTime(t, lines, rows)


def model_summary(model) -> tuple[list[str], list[dict]]:
    """How good the model is, in plain words, from its out-of-fold predictions."""
    if model.predictions is None or model.threshold is None:
        return ["The run has no out-of-fold predictions or no decision threshold for this model."], []
    pr = model.predictions
    m = S.model_check(pr["interest"], pr["prob"], model.threshold)
    lines = [
        f"At its decision threshold ({m.threshold:.2f}) the model flags {m.caught.k:,} of the {m.caught.n:,} batches "
        f"of interest ({m.caught.pct_ci()}) and {m.false_alarms.k:,} of the {m.false_alarms.n:,} background batches "
        f"({m.false_alarms.pct_ci()}).",
        f"The {S.fmt_pct(S.TOP_SHARE)} highest-probability batches ({m.top_n:,}) contain {m.top_captured.k:,} of the "
        f"{m.top_captured.n:,} batches of interest ({m.top_captured.pct_ci()}): {m.lift:.1f} times what chance would give.",
    ]
    if model.pr_auc is not None:
        ci = f" (95% CI {model.pr_auc_ci})" if model.pr_auc_ci and model.pr_auc_ci != "—" else ""
        lines.append(f"PR-AUC {model.pr_auc:.2f}{ci}; a model that learned nothing scores about the share of batches "
                     f"of interest, {S.fmt_pct(float(pr['interest'].mean()))}.")
    lines.append("Out-of-fold: each batch was scored by a model that never saw it. Features and settings were "
                 "chosen with every batch in view, so these numbers are somewhat optimistic.")
    rows = [
        _row("model check", "", "batches of interest flagged", m.caught.p, m.caught.lo, m.caught.hi, n1=m.caught.n,
             method="model", note=f"{m.caught.k} of {m.caught.n}; threshold {m.threshold:.3f}; model {model.name}"),
        _row("model check", "", "background batches flagged", m.false_alarms.p, m.false_alarms.lo, m.false_alarms.hi,
             n2=m.false_alarms.n, method="model", note=f"{m.false_alarms.k} of {m.false_alarms.n}; model {model.name}"),
        _row("model check", "", f"batches of interest among the highest-probability {S.fmt_pct(S.TOP_SHARE)}", m.top_captured.p,
             m.top_captured.lo, m.top_captured.hi, n1=m.top_captured.n, method="model",
             note=f"{m.top_captured.k} of {m.top_captured.n}; {m.top_n} batches; lift {m.lift:.2f}; model {model.name}"),
    ]
    if model.pr_auc is not None:
        rows.append(_row("model check", "", "PR-AUC (out-of-fold)", model.pr_auc, note=f"95% CI {model.pr_auc_ci or '—'}; model {model.name}"))
    return lines, rows


# --------------------------------------------------------------------------- all parameters


def screen(
    frame: pd.DataFrame,
    params: pd.DataFrame,
    first: pd.Series,
    date_col: str,
    dayfirst: bool = False,
    model_features: tuple[str, ...] = (),
) -> pd.DataFrame:
    """Every parameter's difference between the two groups, strongest evidence first.

    The test compares batches made in the same calendar quarter only (van
    Elteren for numbers, Cochran–Mantel–Haenszel for categories), so a
    parameter that merely drifts over time while the share of batches of interest changes does not
    come out as a finding. q is the Benjamini–Hochberg adjusted p over every
    parameter tested. The effect is shown over all batches: the AUC for numbers,
    the category with the highest rate for categories. For a parameter with
    q < 0.05 that is not a model feature, "moves with" names the model feature
    with the strongest rank correlation.
    """
    first = first.astype(bool)
    strata = S.quarters(frame[date_col])
    rows, numbers = [], {}
    for name, vtype in zip(params["name"], params["type"]):
        if name not in frame:
            continue
        y, order, _ = plot_values(frame[name], vtype, frame[date_col], dayfirst)
        if order is None:
            y = pd.to_numeric(y, errors="coerce").astype(float)
            c = S.compare_numeric(y[first], y[~first], shift=False)
            w = S.van_elteren(y, first, strata)
            if not (c.tested and w.tested):
                continue
            numbers[name] = y
            rows.append({
                "parameter": name, "kind": "number", "n_first": c.n1, "n_second": c.n2,
                "effect": f"AUC {c.auc:.2f} ({c.auc_lo:.2f}–{c.auc_hi:.2f}), "
                          + ("higher" if c.auc > 0.5 else "lower" if c.auc < 0.5 else "no difference"),
                "estimate": c.auc, "ci_low": c.auc_lo, "ci_high": c.auc_hi,
                "within": f"AUC {w.auc:.2f}", "p": w.p, "strength": abs(w.auc - 0.5),
            })
        else:
            c = S.compare_categorical(y, first, test=False)
            w = S.cmh_categories(y, first, strata)
            if not (c.tested and w.tested):
                continue
            top = c.rows.iloc[0]
            rows.append({
                "parameter": name, "kind": "category", "n_first": c.n1, "n_second": c.n2,
                "effect": f"{top['category']}: {S.fmt_pct(top['rate'])} ({S.fmt_pct(top['lo'])}–{S.fmt_pct(top['hi'])})"
                          f" vs {S.fmt_pct(c.overall.p)} overall",
                "estimate": top["rate"], "ci_low": top["lo"], "ci_high": top["hi"],
                "within": "", "p": w.p, "strength": abs(top["rate"] - c.overall.p),
            })
    cols = ["parameter", "kind", "n_first", "n_second", "effect", "estimate", "ci_low", "ci_high", "within",
            "p", "q", "in_model", "moves_with", "rho"]
    if not rows:
        return pd.DataFrame(columns=cols)
    out = pd.DataFrame(rows)
    out["q"] = S.benjamini_hochberg(out["p"])
    ranks = {f: i + 1 for i, f in enumerate(model_features)}
    out["in_model"] = out["parameter"].map(lambda f: f"yes (#{ranks[f]})" if f in ranks else "")
    wanted = out.loc[(out["kind"] == "number") & (out["q"] < 0.05) & (out["in_model"] == ""), "parameter"].tolist()
    partners = S.strongest_partners(pd.DataFrame(numbers), wanted, [f for f in model_features if f in numbers])
    out["moves_with"] = out["parameter"].map(lambda f: partners.get(f, ("", math.nan))[0])
    out["rho"] = out["parameter"].map(lambda f: partners.get(f, ("", math.nan))[1])
    out = out.sort_values(["q", "strength"], ascending=[True, False], kind="stable").reset_index(drop=True)
    return out[cols]
