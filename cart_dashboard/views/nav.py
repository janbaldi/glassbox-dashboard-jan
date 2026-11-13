"""The app's pages by name, so a view can link or switch to another page. Filled by app.py."""

from __future__ import annotations

import streamlit as st

PAGES: dict[str, st.Page] = {}


def go(name: str) -> None:
    """Switch to a page (no-op when the app did not register it, as in a test of one view)."""
    if name in PAGES:
        st.switch_page(PAGES[name])
