"""Pipeline: the batches in process now, what stands out in them, and how long each step takes."""

from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st
from scipy import stats as sps

from .. import monitor as M
from ..monitor_plots import batch_profile_figure, lead_time_figure, stage_figure
from . import common as C

MANY_UNUSUAL_P = 0.01  # a batch stands out when this few batches would have as many unusual values by chance


@st.cache_data(show_spinner=False)
def _pipeline(key: tuple, _df, _params, _s, _cfg) -> pd.DataFrame:
    return M.pipeline(_df, _params, _s, _cfg)


def pipeline_table(ctx: C.Ctx) -> pd.DataFrame:
    return _pipeline(ctx.key, ctx.df, ctx.params, ctx.s, ctx.cfg)


@st.cache_data(show_spinner="Checking the batches in process…")
def _unusual(key: tuple, _values, _history, _rows) -> pd.DataFrame:
    return M.unusual_values(_values, _history, _rows)


def render() -> None:
    ctx = C.context("Pipeline", "Batches in process and lead times.")
    cfg, s, df = ctx.cfg, ctx.s, ctx.df
    if not s.stages:
        st.info("No stages found in the data. Set `monitor.stages` in the config.")
        return
    pipe = pipeline_table(ctx)
    open_rows = (pipe["state"] == "in process") & ctx.rows
    history = pipe["state"] == "closed"
    unusual = _unusual(ctx.key, ctx.values, history, pipe["state"] == "in process")
    unusual = unusual[unusual["row"].isin(open_rows.index[open_rows])]

    recorded = ctx.values[open_rows].notna().sum(axis=1)
    n_unusual = unusual.groupby("row").size().reindex(recorded.index).fillna(0).astype(int)
    expected = M.UNUSUAL[0] + 1 - M.UNUSUAL[1]
    chance = pd.Series(sps.binom.sf(n_unusual - 1, recorded, expected), index=recorded.index)
    stands_out = (chance < MANY_UNUSUAL_P) & (n_unusual > 0)

    tiles = st.columns(4)
    tiles[0].metric("In process now", f"{int(open_rows.sum()):,}", f"as of {ctx.as_of:%Y-%m-%d}", delta_color="off", delta_arrow="off", border=True,
                    help=f"Started at most {s.pipeline_days} days before the data's last date and not yet at '{s.closed_from}'.")
    week = open_rows & (ctx.dates > ctx.as_of - pd.Timedelta(days=7))
    tiles[1].metric("Started in the last 7 days", f"{int(week.sum()):,}", border=True)
    tiles[2].metric("Standing out", f"{int(stands_out.sum()):,}", "more unusual values than chance", delta_color="off",
                    delta_arrow="off", border=True, help=f"A value is unusual outside the central {100 * (M.UNUSUAL[1] - M.UNUSUAL[0]):.0f}% of the "
                    f"completed batches. About {100 * expected:.0f}% of a normal batch's values are; a batch stands out when "
                    f"fewer than {100 * MANY_UNUSUAL_P:.0f}% of batches would have as many.")
    stalled = (pipe["state"] == "not closed") & ctx.period
    tiles[3].metric("Not closed, older", f"{int(stalled.sum()):,}", f"no '{s.closed_from}' date",
                    delta_color="off", delta_arrow="off", border=True,
                    help=f"Batches started more than {s.pipeline_days} days ago without the stage '{s.closed_from}': "
                         "terminated, or never recorded.")

    if not open_rows.any():
        st.info("No batches in process.")
    else:
        _open_batches(ctx, pipe, open_rows, recorded, n_unusual, stands_out, unusual)
    _lead_times(ctx)


def _open_batches(ctx, pipe, open_rows, recorded, n_unusual, stands_out, unusual) -> None:
    cfg, s, df = ctx.cfg, ctx.s, ctx.df
    open_ = pipe[open_rows]
    left, right = st.columns([2, 3], gap="medium")
    with left:
        group = df.loc[open_.index, cfg.col("site")].astype(str) if cfg.has("site") else pd.Series("Batches", index=open_.index)
        counts = open_.assign(group=group).groupby(["stage", "group"]).size().rename("n").reset_index()
        stages = [st_.label for st_ in s.stages if st_.label in set(open_["stage"])]
        st.plotly_chart(stage_figure(stages, counts, "By the last stage with data"), width="stretch", theme="streamlit",
                        config=C.PLOT_CONFIG)
    table = pd.DataFrame({
        "Batch": df.loc[open_.index, cfg.col("batch_id")],
        **({"Site": df.loc[open_.index, cfg.col("site")]} if cfg.has("site") else {}),
        "Started": ctx.dates[open_.index].dt.date, "Days": open_["days"], "Stage": open_["stage"],
        "Values": recorded, "Unusual": n_unusual, "Stands out": np.where(stands_out, "●", ""),
    }).sort_values(["Unusual", "Days"], ascending=[False, False])
    with right:
        C.heading("Batches in process", "Click a row to see what is unusual in that batch.")
        ids = table["Batch"].tolist()
        remembered = st.session_state.get("mon_pick_batch")
        default = ids.index(remembered) if remembered in ids else 0
        event = st.dataframe(
            table, key=f"tbl_pipeline_{hash(tuple(ids)) & 0xFFFFFF}_{default}", hide_index=True, width="stretch", height=C.table_height(len(table), 330),
            on_select="rerun", selection_mode="single-row", selection_default={"selection": {"rows": [default]}},
            column_config={
                "Days": st.column_config.NumberColumn(help="Days since manufacturing start, at the data's last date."),
                "Values": st.column_config.NumberColumn(help="Numerical parameters recorded so far."),
                "Unusual": st.column_config.NumberColumn(help="Recorded values outside the central 98% of the completed batches."),
                "Stands out": st.column_config.TextColumn(help="More unusual values than chance gives.", width="small"),
            },
        )
        picked = event.selection.rows if event and event.selection else []
        batch = ids[picked[0]] if picked and picked[0] < len(ids) else ids[default]
        st.session_state["mon_pick_batch"] = batch

    row = table.index[table["Batch"] == batch][0]
    mine = unusual[unusual["row"] == row]
    head, button = st.columns([6, 1.6], vertical_alignment="bottom")
    head.markdown(
        f"**{batch}** · {table.loc[row, 'Stage']} · day {int(table.loc[row, 'Days'])} · "
        f"{int(table.loc[row, 'Unusual'])} of {int(table.loc[row, 'Values'])} values unusual"
    )
    if button.button("Investigate", icon=":material/query_stats:", key="mon_inv_batch", width="stretch",
                     help="Open the investigation page with this batch as the batch of interest."):
        C.investigate(ctx, mine["parameter"].iloc[0] if len(mine) else None, batch)
    if mine.empty:
        st.caption("No unusual values recorded so far.")
        return
    day = ctx.meta(s.process_day)
    top = mine.head(15).assign(parameter=lambda t: [f"{p} · {day.get(p, '')}" if day.get(p, "") else p for p in t["parameter"]])
    st.plotly_chart(batch_profile_figure(top), width="stretch", theme="streamlit", config=C.PLOT_CONFIG)
    if len(mine) > len(top):
        st.caption(f"The {len(top)} most unusual of {len(mine)}. Compared with the completed batches; hover for the values.")


def _lead_times(ctx: C.Ctx) -> None:
    leads = M.lead_times(ctx.df, ctx.s, ctx.cfg)
    if not leads.shape[1]:
        return
    C.heading("Lead times", "Days between the dated stages, by manufacturing start. Batches that are not through a step yet are left out.")
    left, right = st.columns([3, 2], gap="medium")
    with left:
        st.plotly_chart(lead_time_figure(ctx.dates[ctx.period], leads[ctx.period]), width="stretch", theme="streamlit",
                        config=C.PLOT_CONFIG)
    with right:
        rows = []
        for column in leads.columns:
            r, b = leads.loc[ctx.recent, column].dropna(), leads.loc[ctx.baseline, column].dropna()
            p = np.nan
            if len(r) >= 10 and len(b) >= 10 and np.ptp(np.concatenate([r, b])) > 0:
                p = float(sps.mannwhitneyu(r, b).pvalue)
            rows.append({"Step": column, "Recent": r.median(), "Baseline": b.median(), "p": p, "n recent": len(r)})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", column_config={
            "Recent": st.column_config.NumberColumn("Recent (days)", format="%.1f", help="Median of the recent window."),
            "Baseline": st.column_config.NumberColumn("Baseline (days)", format="%.1f"),
            "p": st.column_config.NumberColumn(format="%.3f", help="Mann-Whitney, recent against baseline."),
        })
