"""Materials: raw material and vector lots. Did a parameter move when a lot changed?"""

from __future__ import annotations

import re

import pandas as pd
import streamlit as st

from .. import monitor as M
from .. import stats as S
from ..monitor_plots import lot_figure
from . import common as C

_LOT = re.compile(r"\b(lot|batch)\b", re.IGNORECASE)
MAX_LOTS = 400  # more categories than this is an id per batch, not a lot


def material_names(ctx: C.Ctx) -> list[str]:
    """The lot columns: categorical parameters of a material variation source (else named lot or batch), used in at least two lots."""
    source = ctx.meta(ctx.s.variation_source)
    batch_col = ctx.cfg.col("batch_id")
    out = []
    for name, vtype in zip(ctx.params["name"], ctx.params["type"]):
        if name == batch_col or name in ctx.values or vtype.strip().lower() != "categorical":
            continue
        is_material = source.get(name, "") in ctx.s.material_sources if ctx.s.variation_source else bool(_LOT.search(name))
        if is_material and 2 <= ctx.df.loc[ctx.period, name].nunique() <= MAX_LOTS:
            out.append(name)
    return out


@st.cache_data(show_spinner="Comparing lots…")
def _screen(key: tuple, filters: tuple, parameter: str, materials: tuple, _values, _frame, _dates, _rows):
    return M.material_screen(_values, _frame, _dates, _rows)


def render() -> None:
    ctx = C.context("Materials", "Raw material and vector lots over the whole period.")
    s = ctx.s
    materials = material_names(ctx)
    if not materials:
        st.info("No lot columns found: categorical parameters with variation source "
                f"{', '.join(s.material_sources)} (`monitor.material_sources` in the config).")
        return
    numeric = list(ctx.values.columns)
    default = next((c for c in s.key_cqas if c in ctx.values), numeric[0])
    if st.session_state.get("mon_material_parameter") not in numeric:
        st.session_state["mon_material_parameter"] = default
    day = ctx.meta(s.process_day)
    parameter = st.selectbox(
        "Parameter", numeric, key="mon_material_parameter", format_func=lambda n: f"{n}  ({day.get(n, '') or 'no day'})",
        help="The lots of every material are checked against this parameter: each lot is compared with the lot used before it.",
    )
    y = ctx.values[parameter]
    summary, changes = _screen(ctx.key, ctx.filters, parameter, tuple(materials), y, ctx.df[materials], ctx.dates, ctx.period)

    tested, moved = int(summary["tested"].sum()), int(summary["moved"].sum())
    left, right = st.columns([5, 2], vertical_alignment="center")
    left.markdown(
        f"{len(summary)} materials · {tested:,} lot changes tested · **{moved} at which the value moved** (q < {M.ALPHA}), "
        f"in {int((summary['moved'] > 0).sum())} materials"
    )
    shown = summary
    if right.toggle("Only materials with a move", key="mon_material_only") and moved:
        shown = summary[summary["moved"] > 0].reset_index(drop=True)
    table = pd.DataFrame({
        "Material": shown["material"], "Process day": shown["material"].map(day).fillna(""), "Lots": shown["lots"],
        "Changes tested": shown["tested"], "Moved": shown["moved"], "Largest shift (SD)": shown["shift"], "Smallest q": shown["q"],
    })
    names = shown["material"].tolist()
    remembered = st.session_state.get("mon_pick_material")
    pick = names.index(remembered) if remembered in names else 0
    event = st.dataframe(
        table, key=f"tbl_material_{hash(tuple(names)) & 0xFFFFFF}_{pick}", hide_index=True, width="stretch",
        height=C.table_height(len(table), 280), on_select="rerun", selection_mode="single-row",
        selection_default={"selection": {"rows": [pick]}},
        column_config={
            "Material": st.column_config.TextColumn(width="large"),
            "Lots": st.column_config.NumberColumn(help="Lots used in the period."),
            "Changes tested": st.column_config.NumberColumn(help=f"Lot changes where both lots have at least {S.MIN_BATCHES} values."),
            "Moved": st.column_config.NumberColumn(help="Lot changes at which the parameter differs between the two lots (q < 0.05)."),
            "Largest shift (SD)": st.column_config.NumberColumn(format="%+.2f", help="The largest difference between two consecutive lots' medians, in within-lot standard deviations (robust); among the changes that moved, if any."),
            "Smallest q": st.column_config.NumberColumn(format="%.3f", help="Mann-Whitney p-value of a lot against the lot before it, corrected for every lot change of every material (Benjamini-Hochberg)."),
        },
    )
    picked = event.selection.rows if event and event.selection else []
    material = names[picked[0]] if picked and picked[0] < len(names) else names[pick]
    st.session_state["mon_pick_material"] = material

    mine = changes[changes["material"] == material].reset_index(drop=True) if len(changes) else changes
    head, button = st.columns([6, 1.6], vertical_alignment="bottom")
    head.markdown(
        f"<div style='font-size:1.15rem;font-weight:600;margin-top:.6rem'>{ctx.label(parameter)} by {material}</div>",
        unsafe_allow_html=True,
    )
    if button.button("Investigate", icon=":material/query_stats:", key="mon_inv_material", width="stretch",
                     help="Open the investigation page on this parameter; colour the points by the material there."):
        st.session_state["timeline_color"] = material
        C.investigate(ctx, parameter)
    st.plotly_chart(
        lot_figure(ctx.dates[ctx.period], y[ctx.period], ctx.df.loc[ctx.period, material], mine, ctx.label(parameter)),
        width="stretch", theme="streamlit", config=C.PLOT_CONFIG,
    )
    if mine.empty:
        st.caption(f"No two consecutive lots with at least {S.MIN_BATCHES} values each.")
        return
    st.dataframe(
        pd.DataFrame({
            "": ["●" if q < M.ALPHA else "" for q in mine["q"]],
            "From lot": mine["before"], "To lot": mine["after"], "First use": pd.to_datetime(mine["date"]).dt.date,
            "n before": mine["n_before"], "n after": mine["n_after"], "Median before": mine["median_before"],
            "Median after": mine["median_after"], "Shift (SD)": mine["shift"], "q": mine["q"],
        }),
        hide_index=True, width="stretch", height=C.table_height(len(mine), 300),
        column_config={
            "": st.column_config.TextColumn(width="small", help="The value moved at this lot change (q < 0.05)."),
            "Median before": st.column_config.NumberColumn(format="%.4g"), "Median after": st.column_config.NumberColumn(format="%.4g"),
            "Shift (SD)": st.column_config.NumberColumn(format="%+.2f"), "q": st.column_config.NumberColumn(format="%.3f"),
        },
    )
    st.caption(
        "Dashed lines: lot changes at which the value moved, labelled with the new lot. A lot change shows when the value "
        "moved, not why: another material's lot, a site or a procedure may have changed on the same days. Check the other "
        "materials in the table above."
    )
