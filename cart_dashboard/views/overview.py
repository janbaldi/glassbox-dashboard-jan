"""Overview: the state of manufacturing at a glance, and where to look next."""

from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from .. import monitor as M
from .. import stats as S
from ..monitor_plots import oos_type_figure, stage_figure, volume_figure
from ..plots import p_chart_figure
from . import common as C
from .pipeline import pipeline_table


def _pp(x: float) -> str:
    return f"{100 * x:+.1f} pp"


def render() -> None:
    ctx = C.context("Overview")
    cfg, s, df = ctx.cfg, ctx.s, ctx.df
    pipe = pipeline_table(ctx)
    oos = M.flag(df[s.oos_flag], s.truthy) if s.oos_flag else None
    leads = M.lead_times(df, s, cfg)

    tiles = st.columns(5)
    days = (ctx.end - ctx.recent_start).days + 1
    before = ctx.rows & (ctx.dates >= ctx.recent_start - pd.Timedelta(days=days)) & (ctx.dates < ctx.recent_start)
    tiles[0].metric(f"Batches started, last {days} days", f"{int(ctx.recent.sum()):,}",
                    f"{int(ctx.recent.sum()) - int(before.sum()):+,} vs the {days} days before", delta_color="off", border=True)
    in_process = (pipe["state"] == "in process") & ctx.rows
    tiles[1].metric("In process now", f"{int(in_process.sum()):,}",
                    f"as of {ctx.as_of:%Y-%m-%d}", delta_color="off", delta_arrow="off", border=True)
    if oos is not None:
        r, b = oos[ctx.recent].dropna().astype(bool), oos[ctx.baseline].dropna().astype(bool)
        rr, rb = S.wilson(int(r.sum()), len(r)), S.wilson(int(b.sum()), len(b))
        delta = _pp(rr.p - rb.p) + " vs baseline" if len(r) and len(b) else None
        tiles[2].metric("OOS rate, recent", S.fmt_pct(rr.p) if len(r) else "–", delta, delta_color="inverse", border=True,
                        help=f"{rr.text()} in the recent window; baseline {rb.text()}. Batches without a result yet are left out.")
    counts = ctx.score["status"].value_counts()
    tiles[3].metric("Parameters shifted", f"{counts.get(M.STATUS_SHIFTED, 0):,}",
                    f"{counts.get(M.STATUS_WATCH, 0):,} on watch · of {len(ctx.score):,}", delta_color="off", delta_arrow="off", border=True,
                    help="Numerical parameters whose recent median differs from the baseline. See the Process, Patient and Final product tabs.")
    if leads.shape[1]:
        total = leads.columns[-1]
        r, b = leads.loc[ctx.recent, total].median(), leads.loc[ctx.baseline, total].median()
        delta = f"{r - b:+.1f} days vs baseline" if np.isfinite(r) and np.isfinite(b) and abs(r - b) >= 0.05 else None
        tiles[4].metric(total, f"{r:.1f} days" if np.isfinite(r) else "–", delta, delta_color="inverse", border=True,
                        help="Median over the batches that have both dates. Recent batches that are not through yet are left out, "
                             "so the recent median leans to the fast ones.")

    left, right = st.columns(2, gap="medium")
    with left:
        sites = df.loc[ctx.period, cfg.col("site")] if cfg.has("site") else None
        st.plotly_chart(volume_figure(ctx.dates[ctx.period], sites), width="stretch", theme="streamlit", config=C.PLOT_CONFIG)
    with right:
        if oos is not None:
            known = ctx.period & oos.notna()
            table = S.monthly_rate(ctx.dates[known], oos[known].astype(bool))
            st.plotly_chart(p_chart_figure(table, "OOS rate"), width="stretch", theme="streamlit", config=C.PLOT_CONFIG)
            flagged = table[table["flagged"]]
            if len(flagged):
                st.caption("Above the upper limit: " + ", ".join(
                    f"{r.month:%b %Y} ({r.k} of {r.n})" for r in flagged.itertuples()) + ".")
        else:
            st.info("No OOS column in the data (`monitor.oos.flag` in the config).")

    left, right = st.columns(2, gap="medium")
    with left:
        types = M.oos_by_type(df, s, ctx.recent, ctx.baseline)
        if len(types):
            st.plotly_chart(oos_type_figure(types, [M.oos_label(t) for t in types["type"]], "recent", "baseline"),
                            width="stretch", theme="streamlit", config=C.PLOT_CONFIG)
            worse = types[(types["p"] < M.ALPHA) & (types["recent"] > types["baseline"])]
            if len(worse):
                st.caption("Higher than the baseline (Fisher's exact test, p < 0.05): "
                           + ", ".join(M.oos_label(t) for t in worse["type"]) + ".")
    with right:
        open_ = pipe[in_process]
        if len(open_):
            group = df.loc[open_.index, cfg.col("site")].astype(str) if cfg.has("site") else pd.Series("Batches", index=open_.index)
            table = open_.assign(group=group).groupby(["stage", "group"]).size().rename("n").reset_index()
            stages = [st_.label for st_ in s.stages if st_.label in set(open_["stage"])]
            st.plotly_chart(stage_figure(stages, table, "Batches in process, by the last stage with data"),
                            width="stretch", theme="streamlit", config=C.PLOT_CONFIG)
        else:
            st.info("No batches in process.")

    C.heading("What moved", "The parameters whose recent batches differ most from the baseline. Open a tab to see their trends.")
    moved = ctx.score[ctx.score["status"] == M.STATUS_SHIFTED].head(12)
    if moved.empty:
        st.success("No parameter shifted.")
        return
    day, kind = ctx.meta(s.process_day), ctx.meta(s.functional_type)
    st.dataframe(
        pd.DataFrame({
            "Status": [C.status_text(a, b) for a, b in zip(moved["status"], moved["shift"])],
            "Parameter": moved["parameter"], "Process day": moved["parameter"].map(day),
            "Functional type": moved["parameter"].map(kind),
            "Recent": moved["recent"], "Baseline": moved["baseline"], "Shift (SD)": moved["shift"], "Trend": moved["trend"],
        }),
        hide_index=True, width="stretch",
        column_config={
            "Recent": st.column_config.NumberColumn(format="%.4g"), "Baseline": st.column_config.NumberColumn(format="%.4g"),
            "Shift (SD)": st.column_config.NumberColumn(format="%+.2f"),
            "Trend": st.column_config.LineChartColumn(width="small"),
        },
    )
