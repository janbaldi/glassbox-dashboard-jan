"""CPV: continued process verification. Is each parameter still in its state of control?"""

from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from .. import cpv_report as R
from .. import monitor as M
from .. import stats as S
from ..report import provenance
from ..monitor_plots import z_heatmap
from . import common as C
from .groups import _product_mask

MAX_ROWS = 40  # heatmap rows; the table has them all


@st.cache_data(show_spinner="Charting every parameter…")
def _monthly_z(key: tuple, filters: tuple, _values, _dates, _period, _baseline) -> pd.DataFrame:
    return M.monthly_z(_values, _dates, _period, _baseline)


def _sets(ctx: C.Ctx) -> dict[str, list[str]]:
    """The parameter sets on offer: key attributes, final product, then one per process day."""
    s = ctx.s
    numeric = set(ctx.values.columns)
    sets: dict[str, list[str]] = {}
    if s.key_cqas:
        sets["Key quality attributes"] = [c for c in s.key_cqas if c in numeric]
    product = [n for n in ctx.names(_product_mask(ctx)) if n in numeric]
    if product:
        sets["Final product"] = product
    if s.process_day:
        day = ctx.meta(s.process_day)
        for d in M.day_order(day[day != ""]):
            names = [n for n in day.index[day == d] if n in numeric and n not in product]
            if names:
                sets[f"Process · {d}"] = names
    sets["All parameters"] = list(ctx.values.columns)
    return sets


def render() -> None:
    ctx = C.context("Continued process verification",
                    "Control limits come from the baseline; the recent window is judged against them.")
    sets = _sets(ctx)
    st.session_state.setdefault("mon_cpv_set", "Final product" if "Final product" in sets else next(iter(sets)))
    if st.session_state["mon_cpv_set"] not in sets:
        st.session_state["mon_cpv_set"] = next(iter(sets))
    choice = st.selectbox("Parameter set", list(sets), format_func=lambda k: f"{k} ({len(sets[k])})", key="mon_cpv_set")
    names = sets[choice]

    z = _monthly_z(ctx.key, ctx.filters, ctx.values, ctx.dates, ctx.period, ctx.baseline)
    z = z.loc[[n for n in names if n in z.index]]
    if z.empty:
        st.info("Too few baseline batches to set control limits.")
        return
    beyond = (z.abs() > 3).sum(axis=1)
    recent_months = [c for c in z.columns if c >= ctx.recent_start.to_period("M").to_timestamp()]
    beyond_recent = (z[recent_months].abs() > 3).sum(axis=1)

    in_control = int((beyond_recent == 0).sum())
    tiles = st.columns(3)
    tiles[0].metric("Parameters charted", f"{len(z):,}", border=True)
    tiles[1].metric("In control in the recent window", f"{in_control:,}", f"{100 * in_control / len(z):.0f}% of them", delta_color="off",
                    delta_arrow="off", border=True, help="No recent month's mean beyond the 3-sigma limits.")
    tiles[2].metric("With a recent month out of control", f"{len(z) - in_control:,}", border=True)

    order = beyond_recent.sort_values(ascending=False, kind="stable").index
    order = sorted(order, key=lambda n: (-beyond_recent[n], -beyond[n]))
    shown = order[:MAX_ROWS]
    labels = [n if len(n) <= 46 else n[:45] + "…" for n in shown]
    st.plotly_chart(z_heatmap(z.loc[shown], labels), width="stretch", theme="streamlit", config=C.PLOT_CONFIG)
    st.caption(
        "Each cell is one month's mean on that parameter's x-bar chart: centre and sigma (moving range) from the baseline "
        "batches, limits at ±3 standard errors for the month's number of batches. With many parameters and months a few "
        "cells beyond the limits are expected by chance (about 3 in 1,000)."
        + (f" The {MAX_ROWS} parameters with the most months out of control; the table has all {len(order)}." if len(order) > MAX_ROWS else "")
    )

    score = ctx.score.set_index("parameter").reindex(order)
    table = pd.DataFrame({
        "Parameter": order, "Process day": [ctx.meta(ctx.s.process_day).get(n, "") for n in order],
        "Months out, recent": beyond_recent[order].to_numpy(), "Months out, period": beyond[order].to_numpy(),
        "Beyond ±3 SD": score["outside"].to_numpy(), "EWMA signals": score["ewma"].to_numpy(),
        "Shift (SD)": score["shift"].to_numpy(),
        "Status": [C.status_text(a, b) if isinstance(a, str) else "" for a, b in zip(score["status"], score["shift"])],
    })
    _download(ctx, choice, z.loc[order], table, score)
    C.heading("Control charts", "Click a row for the parameter's chart. EWMA and CUSUM are switched on for it.")
    remembered = st.session_state.get("mon_pick_cpv")
    default = order.index(remembered) if remembered in order else 0
    event = st.dataframe(
        table, key=f"tbl_cpv_{hash(tuple(order)) & 0xFFFFFF}_{default}", hide_index=True, width="stretch", height=C.table_height(len(table), 280),
        on_select="rerun", selection_mode="single-row", selection_default={"selection": {"rows": [default]}},
        column_config={
            "Parameter": st.column_config.TextColumn(width="large"),
            "Months out, recent": st.column_config.NumberColumn(help="Months of the recent window whose mean is beyond the 3-sigma limits."),
            "Months out, period": st.column_config.NumberColumn(help="The same over the whole period."),
            "Beyond ±3 SD": st.column_config.NumberColumn(help="Recent batches further than 3 baseline SD from the baseline median."),
            "EWMA signals": st.column_config.NumberColumn(help="Recent batches at which the EWMA is outside its limits."),
            "Shift (SD)": st.column_config.NumberColumn(format="%+.2f"),
        },
    )
    picked = event.selection.rows if event and event.selection else []
    name = order[picked[0]] if picked and picked[0] < len(order) else order[default]
    st.session_state["mon_pick_cpv"] = name
    st.session_state.setdefault("mon_ewma_cpv", True)
    st.session_state.setdefault("mon_cusum_cpv", True)
    C.parameter_detail(ctx, name, "cpv")


def _download(ctx: C.Ctx, choice: str, z: pd.DataFrame, table: pd.DataFrame, score: pd.DataFrame) -> None:
    """The report button: the PDF is built when it is clicked."""
    s = ctx.s
    sites, reman = ctx.filters[3], ctx.filters[4]
    scope = [
        ("Parameter set", f"{choice} ({len(table)} parameters charted)"),
        ("Period", f"manufacturing start {ctx.start:%Y-%m-%d} to {ctx.end:%Y-%m-%d}; data as of {ctx.as_of:%Y-%m-%d}"),
        ("Recent window", f"{ctx.recent_start:%Y-%m-%d} to {ctx.end:%Y-%m-%d} ({int(ctx.recent.sum()):,} batches)"),
        ("Baseline", f"{ctx.baseline_text()} ({int(ctx.baseline.sum()):,} batches)"),
        ("Batches", f"sites: {', '.join(sites) or 'all'}; re-manufactured: {reman.lower()}"),
    ]
    oos = []
    if s.oos_flag:
        f = M.flag(ctx.df[s.oos_flag], s.truthy)
        r, b = f[ctx.recent].dropna().astype(bool), f[ctx.baseline].dropna().astype(bool)
        if len(r) and len(b):
            oos.append(f"OOS: {S.wilson(int(r.sum()), len(r)).text()} in the recent window; "
                       f"{S.wilson(int(b.sum()), len(b)).text()} in the baseline. Batches without a result yet are left out.")
    report_table = table.assign(status=[a if isinstance(a, str) else "" for a in score["status"]]).drop(columns="Status")
    names = [n for n in table["Parameter"] if n in ctx.values]

    def build() -> bytes:
        return R.build_pdf(R.CpvReport(
            f"CPV report · {choice} · {ctx.end:%B %Y}", scope, z, report_table,
            ctx.values.loc[ctx.period, names], ctx.dates[ctx.period], ctx.baseline[ctx.period], ctx.recent_start,
            ctx.units, ctx.cfg.spc, oos, provenance(ctx.cfg, selection=dict(scope)),
        ))

    row = st.container(horizontal=True, vertical_alignment="center", gap="small")
    row.caption("This view as a report for the file, with methods and provenance:")
    slug = "".join(ch if ch.isalnum() else "_" for ch in choice).strip("_").lower()
    row.download_button("CPV report (PDF)", build, file_name=f"cpv_report_{slug}_{ctx.end:%Y_%m}.pdf",
                        mime="application/pdf", icon=":material/picture_as_pdf:", on_click="ignore", key="mon_inv_cpv_pdf")
