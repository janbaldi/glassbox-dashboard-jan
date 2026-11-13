"""The batch(es) of interest and the background: a summary bar with an edit dialog.

The selection lives in session state under keys starting with ``interest_`` and
``background_``. The dialog's widgets are bound to those keys, and the
selection is computed from the state on every run, so it holds while the
dialog is closed (app.py keeps those keys when their widgets are not drawn).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from ..config import DashboardConfig
from ..data import REMANUFACTURED
from ..glassbox import SUFFIXES, GlassboxError, GlassboxRun, driver_summary, load_run, read_folder, refitted_among
from . import messages
from .timeline import PICKED_KEY
from ..selection import (
    RUN_MODES,
    BatchSelection,
    RemanufactureFilter,
    SelectionMode,
    current_week,
    filter_pool,
    past_year,
    select_batches,
)

INTEREST = "interest"
BACKGROUND = "background"
MODES = {
    INTEREST: [SelectionMode.SINGLE, SelectionMode.MANUAL, SelectionMode.TIME_FRAME],
    BACKGROUND: [SelectionMode.SINGLE, SelectionMode.MANUAL, SelectionMode.TIME_FRAME, SelectionMode.ALL],
}
RUN_EXTRA = {INTEREST: SelectionMode.RUN_INTEREST, BACKGROUND: SelectionMode.RUN_BACKGROUND}
EXCLUDE_KEY = f"{BACKGROUND}_exclude_interest"
RUN_KEY = "run_open"  # the open glassbox run (glassbox.GlassboxRun), if any


def open_run() -> GlassboxRun | None:
    return st.session_state.get(RUN_KEY)


def _modes(prefix: str) -> list[SelectionMode]:
    """The selection modes of one set: the run's set only while a run is open."""
    return MODES[prefix] + ([RUN_EXTRA[prefix]] if open_run() else [])


def _sites(df: pd.DataFrame, cfg: DashboardConfig) -> list[str] | None:
    return sorted(df[cfg.col("site")].dropna().astype(str).unique()) if cfg.has("site") else None


def _set_defaults(sites: list[str] | None) -> None:
    """Interest: this week's batches. Background: the past year's, without the batches of interest."""
    today = date.today()
    for prefix, dates in ((INTEREST, current_week(today)), (BACKGROUND, past_year(today))):
        st.session_state[f"{prefix}_mode"] = SelectionMode.TIME_FRAME
        st.session_state[f"{prefix}_dates"] = dates
        st.session_state[f"{prefix}_reman"] = RemanufactureFilter.ALL
        if sites is not None:
            st.session_state[f"{prefix}_sites"] = sites
    st.session_state[EXCLUDE_KEY] = True


def _clear() -> None:
    """Empty both sets: manual selection with nothing picked."""
    for prefix in (INTEREST, BACKGROUND):
        st.session_state[f"{prefix}_mode"] = SelectionMode.MANUAL
        st.session_state[f"{prefix}_manual"] = []


def _read(prefix: str) -> BatchSelection:
    """The selection of one set, from session state."""
    ss = st.session_state
    selection = BatchSelection(
        mode=ss.get(f"{prefix}_mode", SelectionMode.MANUAL),
        sites=ss.get(f"{prefix}_sites"),
        remanufacture=ss.get(f"{prefix}_reman", RemanufactureFilter.ALL),
    )
    if selection.mode == SelectionMode.SINGLE:
        batch = ss.get(f"{prefix}_single")
        selection.batch_ids = [batch] if batch else []
    elif selection.mode == SelectionMode.MANUAL:
        selection.batch_ids = list(ss.get(f"{prefix}_manual") or [])
    elif selection.mode in RUN_MODES:
        run = open_run()
        if run is not None:
            selection.batch_ids = (
                run.interest_ids if selection.mode == SelectionMode.RUN_INTEREST else run.background_ids
            )
    elif selection.mode == SelectionMode.TIME_FRAME:
        picked = ss.get(f"{prefix}_dates")
        # While the user is picking, Streamlit briefly holds a 1-tuple.
        if isinstance(picked, (list, tuple)) and len(picked) == 2:
            selection.date_range = (picked[0], picked[1])
    return selection


def _compute(df: pd.DataFrame, cfg: DashboardConfig) -> tuple[list[str], list[str]]:
    interest_ids = select_batches(df, cfg, _read(INTEREST))
    background_ids = select_batches(df, cfg, _read(BACKGROUND))
    if st.session_state.get(EXCLUDE_KEY, True):
        interest_set = set(interest_ids)
        background_ids = [b for b in background_ids if b not in interest_set]
    return interest_ids, background_ids


def _span(start: date, end: date) -> str:
    """'21–27 Sep 2026', '28 Sep – 4 Oct 2026' or '24 Sep 2025 – 24 Sep 2026'."""
    if (start.year, start.month) == (end.year, end.month):
        return f"{start.day}–{end.day} {end:%b %Y}"
    if start.year == end.year:
        return f"{start.day} {start:%b} – {end.day} {end:%b %Y}"
    return f"{start.day} {start:%b %Y} – {end.day} {end:%b %Y}"


def _describe(selection: BatchSelection, all_sites: list[str] | None) -> str:
    if selection.mode == SelectionMode.TIME_FRAME:
        if selection.date_range is None:
            text = "no date range"
        else:
            text = _span(*selection.date_range)
    elif selection.mode == SelectionMode.ALL:
        text = "all batches"
    elif selection.mode == SelectionMode.RUN_INTEREST:
        text = "glassbox run interest"
    elif selection.mode == SelectionMode.RUN_BACKGROUND:
        text = "glassbox run background"
    elif selection.mode == SelectionMode.SINGLE:
        text = selection.batch_ids[0] if selection.batch_ids else "no batch picked"
    else:
        text = f"{len(selection.batch_ids)} picked" if selection.batch_ids else "none picked"
    if selection.sites is not None and all_sites is not None and set(selection.sites) != set(all_sites):
        text += f" · {', '.join(selection.sites) or 'no site'}"
    if selection.remanufacture != RemanufactureFilter.ALL:
        text += f" · {selection.remanufacture.value.lower()}"
    return text


def _batch_labels(df: pd.DataFrame, cfg: DashboardConfig) -> dict[str, str]:
    """Human readable label per batch id: 'id · date · site'."""
    batch_col, date_col = cfg.col("batch_id"), cfg.col("manufacturing_date")
    parts = [df[batch_col], df[date_col].dt.strftime("%Y-%m-%d").fillna("no date")]
    if cfg.has("site"):
        parts.append(df[cfg.col("site")].astype(str))
    labels = parts[0].str.cat(parts[1:], sep=" · ")
    return dict(zip(df[batch_col], labels))


def _prune_state(key: str, allowed: list[str]) -> None:
    """Drop previously picked batches that the current filters no longer allow."""
    if key not in st.session_state:
        return
    value = st.session_state[key]
    if isinstance(value, list):
        st.session_state[key] = [v for v in value if v in allowed]
    elif value is not None and value not in allowed:
        st.session_state[key] = None


def _panel(df: pd.DataFrame, cfg: DashboardConfig, prefix: str) -> None:
    """The filter and selection widgets of one set, bound to its session state keys."""
    all_sites = _sites(df, cfg)
    if all_sites is not None:
        st.session_state.setdefault(f"{prefix}_sites", all_sites)
        st.multiselect("Manufacturing site", all_sites, key=f"{prefix}_sites")
    if cfg.has("remanufacture"):
        st.radio(
            "Re-manufacture", list(RemanufactureFilter), format_func=lambda o: o.value,
            horizontal=True, key=f"{prefix}_reman",
        )
    mode = st.radio(
        "Select by", _modes(prefix), format_func=lambda m: m.value, horizontal=True, key=f"{prefix}_mode"
    )

    selection = _read(prefix)
    pool = filter_pool(df, cfg, selection.sites, selection.remanufacture).sort_values(
        cfg.col("manufacturing_date"), ascending=False, na_position="last"
    )
    pool_ids = list(dict.fromkeys(pool[cfg.col("batch_id")]))
    labels = _batch_labels(pool, cfg)

    if mode == SelectionMode.SINGLE:
        _prune_state(f"{prefix}_single", pool_ids)
        st.selectbox(
            f"Batch ({len(pool_ids)} available)", pool_ids, index=None,
            placeholder="Type or pick a batch id", format_func=labels.get, key=f"{prefix}_single",
        )
    elif mode == SelectionMode.MANUAL:
        _prune_state(f"{prefix}_manual", pool_ids)
        st.multiselect(
            f"Batches ({len(pool_ids)} available)", pool_ids,
            placeholder="Type or pick batch ids", format_func=labels.get, key=f"{prefix}_manual",
        )
    elif mode == SelectionMode.TIME_FRAME:
        dates = pool[cfg.col("manufacturing_date")].dropna()
        if dates.empty:
            st.info("No batches with a manufacturing date match the filters.")
        else:
            key = f"{prefix}_dates"
            if not st.session_state.get(key):
                st.session_state[key] = (dates.min().date(), dates.max().date())
            st.date_input("Manufacturing date range (inclusive)", key=key)


def _summary(df: pd.DataFrame, cfg: DashboardConfig, ids: list[str], empty_msg: str) -> None:
    if not ids:
        st.warning(empty_msg)
        return
    st.success(f"**{len(ids)}** batch{'es' if len(ids) != 1 else ''} selected")
    with st.expander("Show selected batches"):
        cols = [cfg.col("batch_id"), cfg.col("manufacturing_date")]
        if cfg.has("site"):
            cols.append(cfg.col("site"))
        rows = df[df[cfg.col("batch_id")].isin(ids)]
        table = rows[cols].copy()
        if cfg.has("remanufacture"):
            table["Re-manufactured"] = rows[REMANUFACTURED]
        st.dataframe(table, hide_index=True, width="stretch")


@st.dialog("Batch selection", width="large", on_dismiss="rerun")
def _edit(df: pd.DataFrame, cfg: DashboardConfig) -> None:
    sites = _sites(df, cfg)
    buttons = st.container(horizontal=True)
    buttons.button("Clear both", on_click=_clear)
    buttons.button("Default selection", on_click=_set_defaults, args=(sites,))
    left, right = st.columns(2, gap="large")
    with left:
        st.subheader("Batch(es) of interest")
        _panel(df, cfg, INTEREST)
    with right:
        st.subheader("Background batches")
        _panel(df, cfg, BACKGROUND)
        st.checkbox("Exclude the batch(es) of interest from the background", key=EXCLUDE_KEY)

    interest_ids, background_ids = _compute(df, cfg)
    with left:
        _summary(df, cfg, interest_ids, "No batch of interest selected.")
    with right:
        _summary(df, cfg, background_ids, "No background batches selected.")
    if st.button("Done", type="primary"):
        st.rerun()


def _use_run(run: GlassboxRun, sites: list[str] | None) -> None:
    """Open ``run``: its positive class is the interest set, the rest the background."""
    for key in [k for k in st.session_state if k.startswith("run_")]:
        del st.session_state[key]  # the previous run's model and batch picks
    st.session_state.pop(PICKED_KEY, None)  # a batch picked in the table before: other batches now
    st.session_state[RUN_KEY] = run
    st.session_state["run_model"] = run.best_model
    # The top driver as the chart first shows it: over the refitted batches when there are any.
    contrib = run.models[run.best_model].contributions
    refit = refitted_among(contrib, run.interest_ids)
    top = driver_summary(contrib[contrib["batch_id"].isin(refit)] if refit else contrib, 1)
    if not top.empty:
        st.session_state["run_plot_request"] = top["feature"].iloc[0]  # plotted by views.drivers
    for prefix, mode in RUN_EXTRA.items():
        st.session_state[f"{prefix}_mode"] = mode
        st.session_state[f"{prefix}_reman"] = RemanufactureFilter.ALL
        if sites is not None:
            st.session_state[f"{prefix}_sites"] = sites
    st.session_state[EXCLUDE_KEY] = True


def _close_run(sites: list[str] | None) -> None:
    for key in [k for k in st.session_state if k.startswith("run_")]:
        del st.session_state[key]
    st.session_state.pop(PICKED_KEY, None)
    _set_defaults(sites)


@st.dialog("Open glassbox run", width="large")
def _open_dialog(sites: list[str] | None) -> None:
    st.markdown(
        "Pick the folder glassbox wrote its results to (its `--output-dir`, the one with "
        "`run_manifest.json`). The run's positive class becomes the batches of interest "
        "and the other batches the background."
    )
    # No type filter: it would flag every model and report file as an error.
    # Only the CSV and JSON files are read.
    uploaded = st.file_uploader(
        "Browse for the results folder", accept_multiple_files="directory", key="glassbox_upload",
    )
    path = st.text_input(
        "Or type the folder's path on this computer", placeholder="/path/to/task/glassbox",
        key="glassbox_path",
    )
    if not st.button("Open", type="primary", disabled=not (uploaded or path.strip())):
        return
    try:
        if uploaded:
            files = {f.name: f.getvalue() for f in uploaded if f.name.lower().endswith(SUFFIXES)}
            name = uploaded[0].name.split("/")[0]
        else:
            files = read_folder(path.strip())
            name = Path(path.strip()).name
        with st.spinner("Reading the run…"):
            run = load_run(files, name=name)
    except (GlassboxError, OSError, KeyError, ValueError) as exc:
        st.error(f"Could not open the run: {exc}")
        return
    _use_run(run, sites)
    st.rerun()


def describe(df: pd.DataFrame, cfg: DashboardConfig) -> dict[str, str]:
    """The current selection in words, for the statistics record."""
    sites = _sites(df, cfg)
    background = _describe(_read(BACKGROUND), sites)
    if st.session_state.get(EXCLUDE_KEY, True):
        background += ", minus interest"
    return {"Batches of interest": _describe(_read(INTEREST), sites), "Background": background}


def render(df: pd.DataFrame, cfg: DashboardConfig) -> tuple[list[str], list[str]]:
    """Draw the selection bar and return ``(interest_ids, background_ids)``."""
    sites = _sites(df, cfg)
    if f"{INTEREST}_mode" not in st.session_state:
        _set_defaults(sites)
    run = open_run()
    modes = [st.session_state.get(f"{p}_mode") for p in (INTEREST, BACKGROUND)]
    if run is None and any(m in RUN_MODES for m in modes):
        _set_defaults(sites)  # the run was closed, or lost with the session

    interest_ids, background_ids = _compute(df, cfg)
    interest_text = _describe(_read(INTEREST), sites)
    background_text = _describe(_read(BACKGROUND), sites)
    if st.session_state.get(EXCLUDE_KEY, True) and interest_ids:
        background_text += ", minus interest"

    bar = st.container(horizontal=True, vertical_alignment="center", gap="small")
    bar.markdown(
        f"**Interest** {len(interest_ids)} <span style='opacity:.65'>· {interest_text}</span>"
        f"&emsp;**Background** {len(background_ids)} <span style='opacity:.65'>· {background_text}</span>",
        unsafe_allow_html=True,
        width="stretch",
    )
    if bar.button("Edit selection", type="primary"):
        _edit(df, cfg)
    if bar.button("Clear", on_click=_clear):
        _edit(df, cfg)  # straight into the editor to build a new selection
    bar.button("Default", on_click=_set_defaults, args=(sites,))
    if run is None:
        if bar.button("Open glassbox run", icon=":material/folder_open:"):
            _open_dialog(sites)
    else:
        bar.button(f"Close {run.name}", icon=":material/close:", on_click=_close_run, args=(sites,),
                   help="Close the glassbox run and go back to the default selection.")
        known = set(df[cfg.col("batch_id")])
        unknown = [b for b in run.interest_ids + run.background_ids if b not in known]
        if unknown:
            messages.add(
                f"{len(unknown)} batch(es) of the glassbox run are not in the dashboard data: "
                + ", ".join(unknown[:10]) + (" …" if len(unknown) > 10 else "")
            )
    return interest_ids, background_ids
