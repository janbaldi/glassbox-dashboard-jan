"""CAR-T manufacturing dashboard.

Run with:  streamlit run app.py
Pick a different config with:  DASHBOARD_CONFIG=path/to/config.yaml streamlit run app.py
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from cart_dashboard.config import ConfigError, DashboardConfig, load_config, resolve_config_path
from cart_dashboard.data import UNREAD_DATES, load_batches, load_parameters
from cart_dashboard.views import drivers, help_page, messages, selection, statistics, timeline

st.set_page_config(page_title="CAR-T manufacturing dashboard", layout="wide", initial_sidebar_state="expanded")

# Dashboard density: less space above the page and the sidebar, smaller controls.
# The header stays (it holds the menu and the sidebar toggle) but no longer
# takes room or blocks clicks on what is under it.
_STYLE = """
<style>
[data-testid="stHeader"] {background: transparent; pointer-events: none;}
[data-testid="stHeader"] button, [data-testid="stHeader"] a {pointer-events: auto;}
[data-testid="stMainBlockContainer"] {padding: 0.75rem 3rem 1.5rem;}
[data-testid="stSidebarHeader"] {height: 1.75rem; margin-bottom: 0; padding-top: 0.25rem;}
[data-testid="stSidebarUserContent"] {padding: 0 1rem 1.5rem;}
[data-testid="stVerticalBlock"] {gap: 0.6rem;}
[data-testid="stSidebarUserContent"] [data-testid="stVerticalBlock"] {gap: 0.45rem;}
[data-testid="stWidgetLabel"] {min-height: 1.1rem; margin-bottom: 0.1rem;}
[data-testid="stWidgetLabel"] p {font-size: 0.85rem;}
[data-testid^="stBaseButton"] {min-height: 1.9rem; padding: 0.1rem 0.7rem;}
</style>
"""


@st.cache_data(show_spinner="Loading batch data…")
def _load(
    config_path: str, mtimes: tuple[float, ...]
) -> tuple[DashboardConfig, pd.DataFrame, pd.DataFrame]:
    # The mtimes are part of the cache key so edits to the files are picked up.
    cfg = load_config(config_path)
    return cfg, load_batches(cfg), load_parameters(cfg)


def dashboard() -> None:
    config_path = resolve_config_path()
    try:
        cfg = load_config(config_path)
        files = (config_path, cfg.csv_path, cfg.parameters_path)
        mtimes = tuple(f.stat().st_mtime if f.exists() else 0.0 for f in files)
        cfg, df, params = _load(str(config_path), mtimes)
    except ConfigError as exc:
        st.error(str(exc))
        st.stop()

    messages.reset()
    if unread := df.attrs.get(UNREAD_DATES):
        examples = ", ".join(f"'{v}'" for v in unread[:3])
        messages.add(
            f"{len(unread)} manufacturing date(s) in {cfg.csv_path.name} could not be read "
            f"(for example {examples}); those batches have no date. Set `data.date_format` in "
            f"{cfg.source_path.name} if the dates use an unusual format."
        )
    run = selection.open_run()
    interest_ids, background_ids = selection.render(df, cfg)
    # Fixed slots, top to bottom: plot, feature relevance, statistics, batches
    # of interest table. The sections are drawn after the plot so they cover
    # the parameter and the batches it shows.
    plot_area, drivers_area, stats_area, table_area = st.container(), st.container(), st.container(), st.container()
    model = None
    available = params[params["name"].isin(df.columns)]
    if run is not None:
        with st.sidebar:
            model = drivers.sidebar(run)
        drivers.prepare(available, cfg)
    with plot_area:
        plotted = timeline.render(df, cfg, params, interest_ids, background_ids, model, table_area)
    if run is not None:
        with drivers_area:
            drivers.render(run, model, available, cfg, interest_ids, plotted.interest_ids)
    with stats_area:
        statistics.render(plotted, df, cfg, available, run, model, interest_ids, background_ids)

    with st.sidebar:
        st.divider()
        if st.button("Help", icon=":material/help:", width="stretch"):
            st.switch_page(HELP)
        st.caption(
            f"{df[cfg.col('batch_id')].nunique()} batches in {cfg.csv_path.name}  \n"
            f"Config: {cfg.source_path.name}"
        )
        duplicated = df[cfg.col("batch_id")].duplicated().sum()
        if duplicated:
            messages.add(f"{duplicated} duplicated batch id row(s) in the data.")
    messages.render()


def help_view() -> None:
    help_page.render(back_to=DASHBOARD)


def _keep_widget_state() -> None:
    # Streamlit drops the state of widgets that are not drawn: the selection
    # dialog's while it is closed, and all dashboard controls while the help
    # page is open. Setting the values ourselves keeps them.
    # (The table's key starts with "context_table_": a table's selection cannot be set this way.)
    for key in list(st.session_state):
        if key.startswith(("interest_", "background_", "timeline_", "run_", "stats_")):
            st.session_state[key] = st.session_state[key]


DASHBOARD = st.Page(dashboard, title="Investigation", icon=":material/monitoring:", default=True)
HELP = st.Page(help_view, title="Help", icon=":material/help:", url_path="help")

page = st.navigation([DASHBOARD, HELP], position="hidden")
st.html(_STYLE)
_keep_widget_state()
page.run()
