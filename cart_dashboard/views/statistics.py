"""The statistics section below the plot: the evidence in plain words, with the numbers behind it.

Compares the plotted batches of interest with the plotted background batches,
for the plotted parameter. Tabs: the parameter's evidence card; the share of
batches of interest per month (a glassbox run's own groups only); a screen of every parameter (on request: it takes a few seconds); and
the numbers and methods. The whole record downloads as CSV and PDF.
"""

from __future__ import annotations

import html
import re

import pandas as pd
import streamlit as st

from .. import evidence as E
from .. import report as R
from .. import stats as S
from ..config import DashboardConfig
from ..glassbox import GlassboxRun, ModelRun
from ..plots import BACKGROUND_LABEL, SET_COLUMN, combine_sets, group_values_figure, p_chart_figure, rate_figure
from . import selection
from .drivers import select_parameter
from .timeline import Plotted

SCREEN_KEY = "stats_screen_for"  # what the last screen covered (its cache key)
SCREEN_ALL_KEY = "stats_screen_all"
SCREEN_REV_KEY = "stats_screen_rev"  # bumped after a click, so the table forgets its selection
SCREEN_SHOWN = 15  # rows shown before "show all"


def _html(text: str) -> str:
    """Plain text for an HTML block; **bold** kept."""
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", html.escape(text))


def _card(headline: str, lines: list[str]) -> None:
    items = "".join(f"<li>{_html(line)}</li>" for line in lines)
    st.markdown(
        f"<div style='font-size:.9rem;line-height:1.45'><div style='font-weight:600;font-size:1rem;"
        f"margin-bottom:.2rem'>{_html(headline)}</div><ul style='margin:0;padding-left:1.2rem'>{items}</ul></div>",
        unsafe_allow_html=True,
    )


@st.cache_data(show_spinner=False, max_entries=4)
def _screen(key: tuple, _frame: pd.DataFrame, _params: pd.DataFrame, date_col: str, dayfirst: bool,
            features: tuple[str, ...]) -> pd.DataFrame:
    # ``key`` stands for the frame and the parameter list (the data file, its
    # modification time and the batches), so they need not be hashed.
    return E.screen(_frame, _params, _frame[SET_COLUMN] != BACKGROUND_LABEL, date_col, dayfirst, features)


def _screen_clicked(table_key: str, names: list[str], available: pd.DataFrame, cfg: DashboardConfig) -> None:
    rows = ((st.session_state.get(table_key) or {}).get("selection") or {}).get("rows") or []
    if rows:
        st.session_state[SCREEN_REV_KEY] = st.session_state.get(SCREEN_REV_KEY, 0) + 1
        select_parameter(names[rows[0]], available, cfg)


def render(plotted: Plotted, df: pd.DataFrame, cfg: DashboardConfig, available: pd.DataFrame,
           run: GlassboxRun | None, model: ModelRun | None, interest_ids: list[str], background_ids: list[str]) -> None:
    if plotted.data is None or plotted.parameter is None:
        return
    data, parameter = plotted.data, plotted.parameter
    batch_col, date_col = cfg.col("batch_id"), cfg.col("manufacturing_date")
    site_col = cfg.col("site") if cfg.has("site") else None
    groups = E.groups_for(
        data, batch_col, set(run.interest_ids) if run else None, set(run.background_ids) if run else None,
    )
    ev = E.build(data, parameter, plotted.value_type, date_col, groups, cfg.dayfirst, site_col, model, batch_col)
    over_time = E.over_time(data, date_col, groups) if groups.run else None
    model_lines, model_rows = E.model_summary(model) if (model is not None and groups.run) else ([], [])

    # The screen covers the plotted batches: the same as the card.
    ids = set(data[batch_col])
    first_ids = tuple(sorted(data.loc[data[SET_COLUMN] != BACKGROUND_LABEL, batch_col].astype(str)))
    second_ids = tuple(sorted(data.loc[data[SET_COLUMN] == BACKGROUND_LABEL, batch_col].astype(str)))
    mtime = cfg.csv_path.stat().st_mtime if cfg.csv_path.exists() else 0.0
    features = tuple(model.features) if model is not None and groups.run else ()
    screen_key = (str(cfg.csv_path), mtime, len(available), first_ids, second_ids)

    def screen() -> pd.DataFrame:
        frame = combine_sets(df, cfg, interest_ids, background_ids)
        frame = frame[frame[batch_col].isin(ids)].reset_index(drop=True)
        return _screen(screen_key, frame, available, date_col, cfg.dayfirst, features)

    wanted = (screen_key, features)

    with st.expander(f"Statistics · {groups.first} compared with {groups.second}", expanded=True):
        per_month = f"{E._cap(groups.rate)} per month"
        names = ["This parameter"] + ([per_month] if over_time else []) + ["All parameters", "Numbers and methods"]
        tabs = dict(zip(names, st.tabs(names)))
        with tabs["This parameter"]:
            _parameter_tab(ev)
        if over_time:
            with tabs[per_month]:
                _over_time_tab(over_time, groups)
        with tabs["All parameters"]:
            screened = _screen_tab(screen, wanted, groups, available, cfg)
        record = R.Record(
            groups,
            R.provenance(cfg, run, model if groups.run else None, {
                **selection.describe(df, cfg),
                "Plot filters": "; ".join(plotted.filters) or "none",
                "Batches compared": f"{len(first_ids):,} {groups.first}, {len(second_ids):,} {groups.second}",
                "Parameter": parameter,
                **({"Glassbox target": run.target_col} if run else {}),
            }),
            parameter, ev, over_time, model_lines, model_rows, screened,
        )
        with tabs["Numbers and methods"]:
            _numbers_tab(record)
        _downloads(record)


def _parameter_tab(ev: E.Evidence) -> None:
    g = ev.groups
    _card(ev.headline, ev.lines)
    if not ev.tested:
        pass
    elif ev.kind == "number" and ev.first_values is not None and len(ev.first_values) and len(ev.second_values):
        left, right = st.columns(2, gap="medium")
        with left:
            st.plotly_chart(group_values_figure(ev.first_values, ev.second_values, g.first, g.second,
                                                ev.parameter + ev.unit),
                            width="stretch", theme="streamlit", config={"displayModeBar": False})
        if ev.by_value is not None:
            with right:
                overall = S.wilson(int(ev.by_value["k"].sum()), int(ev.by_value["n"].sum())).p
                st.plotly_chart(rate_figure(ev.by_value, ev.by_value["group"], overall,
                                            f"{E._cap(g.rate)} by value (quarters of the batches) · 95% intervals"),
                                width="stretch", theme="streamlit", config={"displayModeBar": False})
    elif ev.kind == "category" and ev.categories is not None and len(ev.categories):
        cats = ev.categories.head(20)
        st.plotly_chart(rate_figure(cats, cats["category"], ev.overall.p if ev.overall else None,
                                    f"{E._cap(g.rate)} per category · 95% intervals", horizontal=True),
                        width="stretch", theme="streamlit", config={"displayModeBar": False})
    st.caption(
        "Statistics describe differences between the groups, not their cause. "
        f"A test needs at least {S.MIN_BATCHES} batches with a value in each group. "
        "All intervals are 95%; see *Numbers and methods*."
    )


def _over_time_tab(ot: E.OverTime, groups: E.Groups) -> None:
    _card(ot.lines[0], ot.lines[1:])
    if not ot.table.empty:
        st.plotly_chart(p_chart_figure(ot.table, groups.rate), width="stretch", theme="streamlit",
                        config={"displayModeBar": False})
    st.caption(
        f"A month above the upper limit has more {groups.first} than chance variation around the overall rate "
        f"explains (p-chart, 3-sigma limits). Months with fewer than {S.MIN_BATCHES} batches are not flagged. "
        "The plotted batches only: the filters in the sidebar apply."
    )


def _want_screen(wanted: tuple) -> None:
    st.session_state[SCREEN_KEY] = wanted


def _screen_tab(screen, wanted: tuple, groups: E.Groups, available: pd.DataFrame,
                cfg: DashboardConfig) -> pd.DataFrame | None:
    st.caption(
        f"Tests every parameter for a difference between {groups.first} and {groups.second}, comparing only "
        "batches made in the same calendar quarter, so parameters that merely drift over time drop out. "
        "**q** corrects for testing hundreds of parameters (Benjamini–Hochberg): below 0.05, expect about 1 in 20 "
        "findings to be false. Exploratory: a lead to check, not a conclusion."
    )
    if st.session_state.get(SCREEN_KEY) != wanted:
        st.button(f"Screen all {len(available)} parameters", icon=":material/manage_search:",
                  on_click=_want_screen, args=(wanted,),
                  help="Takes some seconds; the result is kept until the plotted batches change.")
        return None
    with st.spinner("Screening every parameter…"):
        screened = screen()
    if screened.empty:
        st.info(f"No parameter has at least {S.MIN_BATCHES} batches with a value in each group, in quarters with both.")
        return screened
    found = int((screened["q"] < 0.05).sum())
    show_all = st.toggle(f"Show all {len(screened)} parameters", key=SCREEN_ALL_KEY)
    shown = screened if show_all else screened.head(max(SCREEN_SHOWN, found))
    view = pd.DataFrame({
        "Parameter": shown["parameter"],
        "Difference (all batches)": shown["effect"],
        "Within quarters": shown["within"].replace("", "—"),
        "q": shown["q"].map(lambda q: S.fmt_p(q).removeprefix("p ").replace("= ", "")),
        "Model feature": shown["in_model"],
        "Moves with": [f"{m} (ρ {r:+.2f})" if isinstance(m, str) and m else "" for m, r in zip(shown["moves_with"], shown["rho"])],
    })
    st.markdown(f"**{found} of {len(screened)} parameters** differ with q < 0.05. Click a row to plot the parameter.")
    key = f"screen_table_{st.session_state.get(SCREEN_REV_KEY, 0)}"
    names = shown["parameter"].tolist()
    st.dataframe(
        view, key=key, hide_index=True, width="stretch", height=min(38 + 35 * len(view), 420),
        selection_mode="single-row", on_select=lambda: _screen_clicked(key, names, available, cfg),
        column_config={
            "Difference (all batches)": st.column_config.TextColumn(
                help="Numbers: AUC, the chance that a batch of interest has the higher value (0.5: no difference). "
                "Categories: the category with the highest rate, against the rate over all batches."),
            "Within quarters": st.column_config.TextColumn(
                help="Numbers: the AUC over batches made in the same quarter. Categories: see q."),
            "q": st.column_config.TextColumn(help="Adjusted p-value of the within-quarter test (Benjamini–Hochberg)."),
            "Moves with": st.column_config.TextColumn(
                help="For a finding the model does not use: the model feature it correlates with most (Spearman ρ)."),
        },
    )
    return screened


def _numbers_tab(record: R.Record) -> None:
    t = R.table(record)
    numbers = t[t["section"] != "provenance"].drop(columns=["method"])
    st.dataframe(
        numbers, hide_index=True, width="stretch", height=300,
        column_config={
            "n_first": st.column_config.NumberColumn(f"n ({record.groups.first})"),
            "n_second": st.column_config.NumberColumn(f"n ({record.groups.second})"),
            **{c: st.column_config.NumberColumn(format="%.4g") for c in ("estimate", "ci_low", "ci_high", "p", "q")},
        },
    )
    methods = list(dict.fromkeys(m for m in t["method"].dropna() if m))
    st.markdown("**Methods**\n" + "\n".join(f"- {html.escape(m)}" for m in methods))
    st.markdown("**Read with care**\n" + "\n".join(f"- {c}" for c in R.CAVEATS))


def _downloads(record: R.Record) -> None:
    name = re.sub(r"[^A-Za-z0-9]+", "_", record.parameter or "statistics").strip("_")[:40] or "statistics"
    row = st.container(horizontal=True, vertical_alignment="center", gap="small")
    row.caption("The record, with provenance" + (" and the screen" if record.screen is not None else "") + ":")
    row.download_button("CSV", lambda: R.build_csv(record), file_name=f"statistics_{name}.csv", mime="text/csv",
                        icon=":material/download:", on_click="ignore")
    row.download_button("PDF", lambda: R.build_pdf(record), file_name=f"statistics_{name}.pdf",
                        mime="application/pdf", icon=":material/picture_as_pdf:", on_click="ignore")
