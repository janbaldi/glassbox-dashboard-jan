"""CPV: continued process verification. Is each parameter still in its state of control?"""

from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from .. import monitor as M
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
