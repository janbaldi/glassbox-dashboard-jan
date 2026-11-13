"""Warnings and notes collected during a page run, shown together, folded, at the bottom of the page.

Views call ``add`` instead of drawing an alert where they are; ``app.py``
calls ``reset`` at the start of the page and ``render`` at its end.
"""

from __future__ import annotations

import streamlit as st

_KEY = "_page_messages"
_ICONS = {"warning": ":material/warning:", "info": ":material/info:", "error": ":material/error:"}


def reset() -> None:
    st.session_state[_KEY] = []


def add(text: str, kind: str = "warning") -> None:
    """Queue a message; ``kind`` is warning, info or error."""
    st.session_state.setdefault(_KEY, []).append((kind, text))


def render() -> None:
    messages = st.session_state.get(_KEY) or []
    if not messages:
        return
    kinds = {k for k, _ in messages}
    icon = _ICONS["error" if "error" in kinds else "warning" if "warning" in kinds else "info"]
    with st.expander(f"Warnings and messages ({len(messages)})", icon=icon, expanded=False):
        for kind, text in messages:
            getattr(st, kind)(text)
