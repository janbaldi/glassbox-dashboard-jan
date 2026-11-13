"""The glassbox run: model picker in the sidebar, the feature relevance charts below the plot.

Only drawn while a run is open (see ``views.selection``). A click on a feature
in either chart makes it the plotted parameter.
"""

from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from ..config import DashboardConfig
from ..evidence import model_summary
from ..glassbox import GlassboxRun, ModelRun, batch_drivers, driver_summary, refitted_among
from ..plots import batch_drivers_figure, drivers_figure
from ..search import search_parameters
from . import messages
from .timeline import PICKED_KEY, _group, short_text

MODEL_KEY = "run_model"
BATCH_KEY = "run_batch"
AVERAGE_KEY = "run_average_over"  # "refit": the batches with a leave-one-out refit; "all"
REV_KEY = "run_chart_rev"  # bumped after each click so the chart forgets its selection
MESSAGE_KEY = "run_message"
LAST_PICK_KEY = "run_table_pick"  # the table pick the batch chart last followed
TOP_FEATURES = 15
TOP_BATCH_FEATURES = 12


PLOT_REQUEST_KEY = "run_plot_request"  # a feature to plot on the next run, set when a run opens


def select_parameter(feature: str | None, available: pd.DataFrame, cfg: DashboardConfig) -> None:
    """Make ``feature`` the plotted parameter.

    Must run before the parameter widget is drawn. Search text and metadata
    filters that would hide the parameter are cleared, or the parameter list
    would fall back to its best match.
    """
    if feature not in set(available["name"]):
        st.session_state[MESSAGE_KEY] = f"`{feature}` is not a parameter in the dashboard data."
        return
    query = st.session_state.get("timeline_param_search") or ""
    if query.strip() and feature not in set(search_parameters(available, query)["name"]):
        st.session_state["timeline_param_search"] = ""
    row = available.set_index("name").loc[feature]
    for column in cfg.parameters_filter_columns:
        key = f"timeline_filter_{column}"
        picked = st.session_state.get(key)
        value = "(empty)" if pd.isna(row[column]) else str(row[column])
        if picked and value not in picked:
            st.session_state[key] = []
    st.session_state["timeline_parameter"] = feature


def _plot_feature(chart_key: str, available: pd.DataFrame, cfg: DashboardConfig) -> None:
    """The charts' on_select callback: plot the clicked feature.

    Runs before the page reruns, so it can still set the parameter widget.
    """
    points = ((st.session_state.get(chart_key) or {}).get("selection") or {}).get("points") or []
    if not points:
        return
    feature = points[0].get("customdata")
    if isinstance(feature, list):
        feature = feature[0] if feature else None
    st.session_state[REV_KEY] = st.session_state.get(REV_KEY, 0) + 1
    select_parameter(feature or points[0].get("y"), available, cfg)


def _format_prob(p) -> str:
    return "—" if p is None or pd.isna(p) else f"{float(p):.2f}"


def sidebar(run: GlassboxRun) -> ModelRun:
    """The *Glassbox run* group at the top of the sidebar. Returns the chosen model."""
    _group("Glassbox run")
    short_text(run.description or "", limit=100, title=run.title or run.name)
    models = list(run.models)
    if st.session_state.get(MODEL_KEY) not in models:
        st.session_state[MODEL_KEY] = run.best_model
    st.selectbox(
        "Model", models, key=MODEL_KEY,
        format_func=lambda m: m + (f"  (PR-AUC {run.models[m].pr_auc:.2f})" if run.models[m].pr_auc is not None else ""),
    )
    model = run.models[st.session_state[MODEL_KEY]]
    baseline = f"a model that learned nothing scores about {run.prevalence:.2f}"
    if not run.usable:
        st.caption(":orange[No model beats the PR-AUC baseline.] See the messages at the bottom of the page.")
        messages.add(f"No model beats the PR-AUC baseline ({baseline}). The drivers describe the model, not the process.")
    elif model.pr_auc is not None and model.pr_auc <= run.prevalence:
        st.caption(":orange[This model does not beat the PR-AUC baseline.] See the messages at the bottom of the page.")
        messages.add(f"{model.name} does not beat the PR-AUC baseline ({baseline}).")
    else:
        st.caption(f"{len(run.interest_ids)} of interest of {len(run.interest_ids) + len(run.background_ids)} batches · PR-AUC baseline {run.prevalence:.2f}")
    with st.expander("How good is the model?"):
        lines, _ = model_summary(model)
        items = "".join(f"<li>{html.escape(line)}</li>" for line in lines)
        st.markdown(f"<ul style='font-size:.8rem;line-height:1.4;margin:0;padding-left:1rem'>{items}</ul>",
                    unsafe_allow_html=True)
    for note in run.notes:
        st.caption(note)
    if run.warnings:
        st.caption(":orange[Some files were left out or changed.] See the messages at the bottom of the page.")
        for warning in run.warnings:
            messages.add(warning)
    return model


def prepare(available: pd.DataFrame, cfg: DashboardConfig) -> None:
    """Plot the feature asked for when the run opened. Before the parameter widget is drawn."""
    if request := st.session_state.pop(PLOT_REQUEST_KEY, None):
        select_parameter(request, available, cfg)


def render(run: GlassboxRun, model: ModelRun, available: pd.DataFrame, cfg: DashboardConfig,
           interest_ids: list[str], plotted_ids: list[str]) -> None:
    """The *Feature relevance* section, between the plot and the statistics.

    It covers the run's batches of interest among ``plotted_ids``: the batches of interest the
    plot shows after its site and category filters, so the two never describe
    different batches. ``interest_ids`` (before those filters) only serves to say
    how many of the run's batches the filters leave out.
    """
    if message := st.session_state.pop(MESSAGE_KEY, None):
        st.toast(message, icon=":material/info:")

    of_run = set(run.interest_ids)
    plotted = set(plotted_ids)
    shown = [b for b in plotted_ids if b in of_run]
    left_out = sum(1 for b in interest_ids if b in of_run and b not in plotted)
    current = st.session_state.get("timeline_parameter")
    clickable = set(available["name"])
    rev = st.session_state.get(REV_KEY, 0)

    with st.expander(f"Feature relevance · {model.name}", expanded=True):
        if not shown:
            st.info(
                "None of the run's batches of interest passes the site or category filter in the sidebar."
                if left_out else "None of the batches of interest is a batch of interest of the glassbox run."
            )
            return
        st.caption(
            "Contributions push a batch's predicted probability of being of interest up (right) or down (left), on the model's "
            f"own scale, here **{model.scale}**. *In-sample*: the final model, fitted with the batch. "
            "*Leave-one-out*: refitted without it; a driver it reproduces is evidence, one it does "
            "not is a hypothesis. **Click a feature to plot it.**"
            + (
                f" As in the plot, the site or category filter in the sidebar leaves out {left_out} "
                f"of the run's {len(shown) + left_out} batches of interest."
                if left_out else ""
            )
        )
        left, right = st.columns(2, gap="medium")

        with left:
            # Both means over the same batches: glassbox refits only the
            # highest-risk ones, so a leave-one-out mean over those beside an
            # in-sample mean over all of them would compare different batches.
            refit = refitted_among(model.contributions, shown)
            over = "refit" if refit else "all"
            if refit and len(refit) < len(shown):
                st.session_state.setdefault(AVERAGE_KEY, "refit")
                over = st.segmented_control(
                    "Average over", ["refit", "all"], key=AVERAGE_KEY, required=True,
                    format_func=lambda o: (
                        f"{len(refit)} refitted batches (in-sample and leave-one-out)"
                        if o == "refit" else f"all {len(shown)} (in-sample only)"
                    ),
                    label_visibility="collapsed",
                )
            batches = refit if over == "refit" else shown
            contrib = model.contributions[model.contributions["batch_id"].isin(batches)]
            summary = driver_summary(contrib, TOP_FEATURES)
            st.markdown(f"**Drivers across {len(batches)} batch{'es' if len(batches) != 1 else ''} of interest**")
            if not refit:
                st.caption("No leave-one-out refit for these batches: in-sample only.")
            if summary.empty:
                st.info("No contributions for these batches.")
            else:
                key = f"chart_run_drivers_{rev}"
                st.plotly_chart(
                    drivers_figure(summary, contrib, current, clickable, model.scale),
                    key=key, on_select=lambda k=key: _plot_feature(k, available, cfg),
                    selection_mode="points", width="stretch", theme="streamlit",
                    config={"displayModeBar": False},
                )

        with right:
            batches = model.batches
            options = [b for b in batches.index if b in set(shown)] or shown
            with_loo = set(refitted_among(model.contributions, options))
            _follow_table(options)
            if st.session_state.get(BATCH_KEY) not in options:
                st.session_state[BATCH_KEY] = options[0]

            def refit_note(b: str) -> str | None:
                """Why a batch has no leave-one-out: not refitted, or its refit failed."""
                detailed = batches.loc[b].get("detailed") if b in batches.index else None
                if detailed is None or pd.isna(detailed):
                    return None  # a run without an investigation: nothing to explain per batch
                if not bool(detailed):
                    return "no dossier"
                return None if b in with_loo else "refit failed"

            def label(b: str) -> str:
                if b not in batches.index:
                    return b
                r = batches.loc[b]
                risk = f" · probability {_format_prob(r.get('oof_prob'))}" if "oof_prob" in r else ""
                note = refit_note(b)
                return f"{b}{risk}" + (f" · {note}" if note else "")

            batch = st.selectbox("Batch (highest probability first; or click a row in the table below)",
                                 options, key=BATCH_KEY, format_func=label)
            if batch in batches.index:
                r = batches.loc[batch]
                threshold = r.get("threshold")
                st.markdown(
                    f"<span style='font-size:.85rem'>Out-of-fold **{_format_prob(r.get('oof_prob'))}** · "
                    f"in-sample **{_format_prob(r.get('in_sample_prob'))}** · "
                    f"leave-one-out **{_format_prob(r.get('loo_prob'))}**"
                    + (f" · threshold {_format_prob(threshold)}" if threshold is not None and pd.notna(threshold) else "")
                    + "</span>",
                    unsafe_allow_html=True,
                )
                note = refit_note(batch)
                if note == "no dossier":
                    st.caption("No leave-one-out refit for this batch (beyond glassbox's `max_detail`): in-sample only.")
                elif note == "refit failed":
                    st.caption("Glassbox's leave-one-out refit failed for this batch (see its `run.log`): in-sample only.")
            rows = batch_drivers(model, batch, TOP_BATCH_FEATURES)
            if rows.empty:
                st.info("No contributions for this batch.")
            else:
                key = f"chart_run_batch_{rev}"
                st.plotly_chart(
                    batch_drivers_figure(rows, current, clickable, model.scale),
                    key=key, on_select=lambda k=key: _plot_feature(k, available, cfg),
                    selection_mode="points", width="stretch", theme="streamlit",
                    config={"displayModeBar": False},
                )


def _follow_table(options: list[str]) -> None:
    """Show the batch last clicked in the table, once per click.

    The table stores its pick by batch id, and it only changes on a click, so a
    table whose rows changed does not move this chart to another batch.
    """
    picked = st.session_state.get(PICKED_KEY)
    if picked != st.session_state.get(LAST_PICK_KEY):
        st.session_state[LAST_PICK_KEY] = picked
        if picked in options:
            st.session_state[BATCH_KEY] = picked
