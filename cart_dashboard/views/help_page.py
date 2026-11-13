"""The help page: docs/help.md with a table of contents and a text search."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import streamlit as st

from ..search import contains_all, highlight

HELP_FILE = Path(__file__).resolve().parents[2] / "docs" / "help.md"
_HEADING = re.compile(r"^(##|###) (.+)$")

# The contents as a docs-style navigation list rather than a bulleted list of links.
_TOC_STYLE = """
<style>
.toc-head {font-size: .75rem; font-weight: 600; letter-spacing: .06em; text-transform: uppercase;
           opacity: .6; margin: .9rem 0 .3rem .6rem;}
.toc {display: flex; flex-direction: column; gap: 1px; border-left: 1px solid rgba(44, 62, 80, .15);}
.toc a {display: block; text-decoration: none !important; color: inherit !important;
        padding: .22rem .6rem; border-left: 2px solid transparent; margin-left: -1px;
        border-radius: 0 .25rem .25rem 0; line-height: 1.3;}
.toc a:hover {background: rgba(0, 102, 204, .08); color: #0066cc !important; border-left-color: #0066cc;}
.toc a.toc-l2 {font-size: .85rem; font-weight: 600; margin-top: .45rem;}
.toc a.toc-l2:first-child {margin-top: 0;}
.toc a.toc-l3 {font-size: .8rem; padding-left: 1.3rem; opacity: .8;}
.toc a.toc-l3:hover {opacity: 1;}
.toc-none {font-size: .8rem; opacity: .6; padding-left: .6rem;}
</style>
"""


@dataclass
class Section:
    level: int  # 2 or 3
    title: str
    anchor: str
    parent: str  # title of the enclosing level-2 section, for level 3
    body: str = ""


def parse(text: str) -> tuple[str, list[Section]]:
    """Split the help text into the intro (before the first ## heading) and its sections."""
    intro: list[str] = []
    sections: list[Section] = []
    parent, in_code, used = "", False, set()
    for line in text.splitlines():
        if line.startswith("```"):
            in_code = not in_code
        match = None if in_code else _HEADING.match(line)
        if match:
            level, title = len(match.group(1)), match.group(2).strip()
            parent = title if level == 2 else parent
            anchor = base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
            n = 1
            while anchor in used:
                n += 1
                anchor = f"{base}-{n}"
            used.add(anchor)
            sections.append(Section(level, title, anchor, parent if level == 3 else ""))
        elif sections:
            sections[-1].body += line + "\n"
        elif not line.startswith("# "):
            intro.append(line)
    return "\n".join(intro).strip(), sections


def render(back_to: st.Page) -> None:
    intro, sections = parse(HELP_FILE.read_text(encoding="utf-8"))

    query = st.text_input(
        "Search the help", placeholder="Type words to find, e.g. CUSUM limits", key="help_search",
        icon=":material/search:",
    )
    texts = pd.Series([f"{s.parent} {s.title} {s.body}" for s in sections])
    hits = [s for s, hit in zip(sections, contains_all(texts, query)) if hit]

    with st.sidebar:
        st.page_link(back_to, label="Back to the dashboard", icon=":material/arrow_back:")
        st.html(_TOC_STYLE)
        count = f" · {len(hits)} matching" if query.strip() else ""
        links = "".join(
            f"<a class='toc-l{s.level}' href='#{s.anchor}'>{html.escape(s.title)}</a>" for s in hits
        ) or "<span class='toc-none'>Nothing matches.</span>"
        st.markdown(
            f"<div class='toc-head'>Contents{count}</div><nav class='toc'>{links}</nav>",
            unsafe_allow_html=True,
        )

    if not query.strip():
        st.title("Help")
        st.markdown(intro)
    elif hits:
        st.caption(f"{len(hits)} of {len(sections)} sections contain every word of the search.")
    else:
        st.info("No section contains all these words. Try fewer or shorter words.")

    for s in hits:
        if s.level == 2:
            st.header(s.title, anchor=s.anchor, divider="gray")
        else:
            if query.strip():
                st.caption(s.parent)
            st.subheader(s.title, anchor=s.anchor)
        st.markdown(highlight(s.body, query), unsafe_allow_html=True)
