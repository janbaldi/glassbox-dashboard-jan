"""CAR-T manufacturing dashboard.

Run with:  streamlit run app.py
Pick a different config with:  DASHBOARD_CONFIG=path/to/config.yaml streamlit run app.py
"""

from __future__ import annotations

import streamlit as st

from cart_dashboard.views import cpv, groups, help_page, investigation, nav, overview, pipeline, sites

st.set_page_config(page_title="CAR-T manufacturing dashboard", layout="wide", initial_sidebar_state="expanded")

# Dashboard density: less space above the page and the sidebar, smaller controls.
# The header holds the tabs.
_STYLE = """
<style>
[data-testid="stMainBlockContainer"] {padding: 3.75rem 3rem 1.5rem;}
[data-testid="stSidebarHeader"] {height: 1.75rem; margin-bottom: 0; padding-top: 0.25rem;}
[data-testid="stSidebarUserContent"] {padding: 0 1rem 1.5rem;}
[data-testid="stVerticalBlock"] {gap: 0.6rem;}
[data-testid="stSidebarUserContent"] [data-testid="stVerticalBlock"] {gap: 0.45rem;}
[data-testid="stWidgetLabel"] {min-height: 1.1rem; margin-bottom: 0.1rem;}
[data-testid="stWidgetLabel"] p {font-size: 0.85rem;}
[data-testid^="stBaseButton"] {min-height: 1.9rem; padding: 0.1rem 0.7rem;}
</style>
"""


def help_view() -> None:
    help_page.render(back_to=nav.PAGES["overview"])


def _keep_widget_state() -> None:
    # Streamlit drops the state of widgets that are not drawn: the selection
    # dialog's while it is closed, and a page's controls while another page
    # is open. Setting the values ourselves keeps them.
    # (Table keys start with "tbl_" or "context_table_": a table's selection cannot be set this way.)
    for key in list(st.session_state):
        if key.startswith(("interest_", "background_", "timeline_", "run_", "stats_", "mon_")) and not key.startswith("mon_inv_"):
            st.session_state[key] = st.session_state[key]


# The tabs: monitoring first (where are we), then the investigation (why).
nav.PAGES.update(
    overview=st.Page(overview.render, title="Overview", icon=":material/dashboard:", url_path="overview", default=True),
    pipeline=st.Page(pipeline.render, title="Pipeline", icon=":material/conversion_path:", url_path="pipeline"),
    patient=st.Page(groups.patient, title="Patient", icon=":material/bloodtype:", url_path="patient"),
    process=st.Page(groups.process, title="Process", icon=":material/science:", url_path="process"),
    product=st.Page(groups.product, title="Final product", icon=":material/verified:", url_path="product"),
    sites=st.Page(sites.render, title="Sites", icon=":material/factory:", url_path="sites"),
    cpv=st.Page(cpv.render, title="CPV", icon=":material/monitoring:", url_path="cpv"),
    investigation=st.Page(investigation.render, title="Investigation", icon=":material/query_stats:", url_path="investigation"),
    help=st.Page(help_view, title="Help", icon=":material/help:", url_path="help"),
)

page = st.navigation(list(nav.PAGES.values()), position="top")
st.html(_STYLE)
_keep_widget_state()
page.run()
