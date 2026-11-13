"""Sites: how the manufacturing sites compare, in outcome, lead time and every parameter."""

from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from .. import monitor as M
from .. import stats as S
from ..monitor_plots import site_box_figure, site_monthly_figure
from ..plots import rate_figure
from . import common as C


@st.cache_data(show_spinner="Comparing the sites…")
def _screen(key: tuple, filters: tuple, _values, _sites, _period) -> pd.DataFrame:
    return M.site_screen(_values, _sites, _period)


def render() -> None:
    ctx = C.context("Sites", "Differences between manufacturing sites over the whole period (recent window and baseline together).")
    cfg, s, df = ctx.cfg, ctx.s, ctx.df
    if not cfg.has("site"):
        st.info("No site column is configured (`columns.site`).")
        return
    sites = df[cfg.col("site")]
    if sites[ctx.period].nunique() < 2:
        st.info("Only one site in this selection. Clear the site filter in the sidebar to compare sites.")
        return
    leads = M.lead_times(df, s, cfg)
    summary = M.site_summary(df, s, cfg, ctx.period, leads)

    left, right = st.columns([2, 3], gap="medium")
    with left:
        if "oos" in summary:
            table = summary.rename(columns={"oos": "rate", "oos_lo": "lo", "oos_hi": "hi", "oos_k": "k", "oos_n": "n"})
            overall = table["k"].sum() / max(table["n"].sum(), 1)
            st.plotly_chart(rate_figure(table, table["site"], overall, "OOS rate per site · 95% intervals"),
                            width="stretch", theme="streamlit", config=C.PLOT_CONFIG)
            if len(table) >= 2 and table["n"].min() >= S.MIN_BATCHES:
                p = S.chi_square_monte_carlo(table["k"].to_numpy(), table["n"].to_numpy()) if len(table) > 2 else \
                    S.missing_comparison(pd.Series([True] * table["k"][0] + [False] * (table["n"][0] - table["k"][0])),
                                         pd.Series([True] * table["k"][1] + [False] * (table["n"][1] - table["k"][1])))[2]
                verdict = "differs between the sites" if p < M.ALPHA else "does not clearly differ between the sites"
                st.caption(f"The OOS rate {verdict} ({S.fmt_p(p)}).")
    with right:
        shown = pd.DataFrame({"Site": summary["site"], "Batches": summary["batches"]})
        if "oos" in summary:
            shown["OOS"] = [f"{k} of {n}" for k, n in zip(summary["oos_k"], summary["oos_n"])]
            shown["OOS rate"] = summary["oos"]
        config = {"OOS rate": st.column_config.NumberColumn(format="percent")}
        for column in leads.columns:
            shown[column] = summary[column]
            config[column] = st.column_config.NumberColumn(column + " (days)", format="%.1f", help="Median, in days.")
        C.heading("Per site", "Lead times are medians in days.")
        st.dataframe(shown, hide_index=True, width="stretch", column_config=config)

    C.heading("Parameters that differ between sites", "Every numerical parameter, largest difference first. Click a row.")
    screen = _screen(ctx.key, ctx.filters, ctx.values, sites, ctx.period)
    if screen.empty:
        st.info(f"No parameter has at least {S.MIN_BATCHES} values at two sites.")
        return
    differ = screen[screen["q"] < M.ALPHA]
    left, right = st.columns([5, 2], vertical_alignment="center")
    left.markdown(f"{len(screen)} parameters compared · **{len(differ)} differ** (q < {M.ALPHA}) · "
                  f"{int((differ['gap'].abs() >= 1).sum())} by at least 1 SD")
    if right.toggle("Only those that differ", value=True, key="mon_sites_only") and len(differ):
        screen = differ
    screen = screen.sort_values("gap", key=lambda g: g.abs(), ascending=False).reset_index(drop=True)
    medians = [c for c in screen.columns if c.startswith("median · ")]
    table = pd.DataFrame({
        "Parameter": screen["parameter"], "Process day": screen["parameter"].map(ctx.meta(s.process_day)),
        "Gap (SD)": screen["gap"], "Lowest": screen["low"], "Highest": screen["high"], "q": screen["q"],
        **{c.replace("median · ", ""): screen[c] for c in medians}, "n": screen["n"],
    })
    names = screen["parameter"].tolist()
    remembered = st.session_state.get("mon_pick_site")
    default = names.index(remembered) if remembered in names else 0
    event = st.dataframe(
        table, key=f"tbl_sites_{hash(tuple(names)) & 0xFFFFFF}_{default}", hide_index=True, width="stretch", height=C.table_height(len(table), 300),
        on_select="rerun", selection_mode="single-row", selection_default={"selection": {"rows": [default]}},
        column_config={
            "Parameter": st.column_config.TextColumn(width="large"),
            "Gap (SD)": st.column_config.NumberColumn(format="%.2f", help="Highest minus lowest site median, in within-site standard deviations (robust)."),
            "q": st.column_config.NumberColumn(format="%.3f", help="Kruskal-Wallis p-value, corrected for testing every parameter (Benjamini-Hochberg)."),
            **{c.replace("median · ", ""): st.column_config.NumberColumn(format="%.4g", help="Site median.") for c in medians},
        },
    )
    picked = event.selection.rows if event and event.selection else []
    name = names[picked[0]] if picked and picked[0] < len(names) else names[default]
    st.session_state["mon_pick_site"] = name

    label = ctx.label(name)
    left, right = st.columns(2, gap="medium")
    with left:
        st.plotly_chart(site_box_figure(ctx.values.loc[ctx.period, name], sites[ctx.period], label), width="stretch",
                        theme="streamlit", config=C.PLOT_CONFIG)
    with right:
        st.plotly_chart(site_monthly_figure(ctx.dates[ctx.period], ctx.values.loc[ctx.period, name], sites[ctx.period], label),
                        width="stretch", theme="streamlit", config=C.PLOT_CONFIG)
    st.caption("A difference between sites can come from the site, or from what the site received: patients, material lots, "
               "the period it was active. The monthly medians show whether the gap is steady.")
