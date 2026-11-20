"""The dashboard's main view: plot controls in the sidebar; summary tiles, plot and context table in the page."""

from __future__ import annotations

import html
from dataclasses import dataclass, field

import pandas as pd
import streamlit as st

from ..config import DashboardConfig
from ..glassbox import ModelRun
from ..context import DEVIATION, PERCENTILE, SAME_VALUE, SEGMENT, context_table
from ..plots import (
    BACKGROUND_LABEL,
    CATEGORY_COLORS,
    MAX_LEGEND_CATEGORIES,
    SET_COLUMN,
    color_groups,
    combine_sets,
    fold_categories,
    plot_values,
    timeline_scatter,
)
from ..search import highlight
from ..spc import control_charts, episodes
from ..transform import TRANSFORMS, apply_transform, percent_scale, suggest_transform
from ..trend import MODELS, TrendFit, fit_trend
from . import messages


@st.cache_data(show_spinner="Fitting trend…")
def _fit(dates: pd.Series, values: pd.Series, settings: dict) -> TrendFit | None:
    return fit_trend(dates, values, **settings)


def _is_categorical(value_type: str) -> bool:
    return value_type.lower() == "categorical" or value_type.startswith("[")


def short_text(text: str, query: str = "", limit: int = 120, title: str | None = None) -> None:
    """A small grey text, shortened to ``limit`` characters; hovering it shows the full text.

    ``title``, when given, is drawn above it in small bold type, in the same
    element so the two cannot overlap.
    """
    short = text if len(text) <= limit else text[: limit - 3].rsplit(" ", 1)[0] + "…"
    head = (
        f"<div style='font-size:.85rem;font-weight:600;line-height:1.3;margin-bottom:.15rem'>"
        f"{html.escape(title)}</div>" if title else ""
    )
    body = (
        f"<div title=\"{html.escape(text, quote=True)}\" style='font-size:.8rem;opacity:.65;"
        f"line-height:1.4;cursor:help'>{highlight(short, query)}</div>" if text else ""
    )
    st.markdown(f"<div style='margin-bottom:.4rem'>{head}{body}</div>", unsafe_allow_html=True)


def _choose_parameter(available: pd.DataFrame, cfg: DashboardConfig) -> str | None:
    """Filter the parameter list by catalogue columns, then pick one (the list itself is searchable)."""
    filters = cfg.parameters_filter_columns
    keep = pd.Series(True, index=available.index)
    if filters:
        active = sum(bool(st.session_state.get(f"timeline_filter_{c}")) for c in filters)
        with st.expander("Filter by catalogue" + (f" ({active} active)" if active else "")):
            for column in filters:
                values = available[column].fillna("(empty)").astype(str)
                picked = st.multiselect(
                    column, values.unique().tolist(), placeholder="All", key=f"timeline_filter_{column}"
                )
                if picked:
                    keep &= values.isin(picked)
    matching = available[keep]

    if matching.empty:
        st.info("No parameters match the catalogue filters.")
        return None
    types = dict(zip(matching["name"], matching["type"]))
    if st.session_state.get("timeline_parameter") not in types:
        st.session_state["timeline_parameter"] = next(iter(types))
    parameter = st.selectbox(
        f"Parameter ({len(types)} of {len(available)})",
        list(types),
        format_func=lambda p: f"{p}  ({types[p] or 'no type'})",
        key="timeline_parameter",
    )
    return parameter


def _reference_period(df: pd.DataFrame, cfg: DashboardConfig) -> tuple[pd.Timestamp, pd.Timestamp] | None:
    """The date range the control charts' normal batches come from; all dates by default."""
    dates = df[cfg.col("manufacturing_date")].dropna()
    if dates.empty:
        return None
    first, last = dates.min().date(), dates.max().date()
    key = "timeline_reference"
    kept = st.session_state.get(key)
    if not (isinstance(kept, (list, tuple)) and kept and all(first <= d <= last for d in kept)):
        st.session_state[key] = (first, last)
    picked = st.date_input(
        "Reference period (normal batches)", key=key, min_value=first, max_value=last,
        help="EWMA and CUSUM measure normal (target and spread) from the background batches made in this period, "
             "and judge every batch against it. Pick a stable period you trust; by default all dates.",
    )
    start, end = picked if isinstance(picked, (list, tuple)) and len(picked) == 2 else (first, last)
    return pd.Timestamp(start), pd.Timestamp(end)


def _display_options(df: pd.DataFrame, cfg: DashboardConfig) -> dict:
    """Site, transform and overlays. Returns the choices and a slot for the transform hint."""
    site = None
    if cfg.has("site"):
        sites = sorted(df[cfg.col("site")].dropna().astype(str).unique())
        site = st.selectbox("Manufacturing site", sites, index=None, placeholder="All sites", key="timeline_site")
    transform = st.selectbox("Transform", TRANSFORMS, key="timeline_transform")
    hint = st.container()
    row = st.container(horizontal=True, gap="small")
    checks = {}
    for key, label, default in (("trend", "Trend", True), ("ewma", "EWMA", False), ("cusum", "CUSUM", False)):
        st.session_state.setdefault(f"timeline_{key}", default)  # a default, without clashing with kept state
        checks[key] = row.checkbox(label, key=f"timeline_{key}")
    reference = _reference_period(df, cfg) if checks["ewma"] or checks["cusum"] else None
    return dict(site=site, transform=transform, hint=hint, reference=reference, **checks)


def _group(title: str) -> None:
    """A small heading for a group of sidebar controls."""
    st.markdown(
        f"<div style='font-size:.75rem;font-weight:600;letter-spacing:.06em;text-transform:uppercase;"
        f"opacity:.6;margin:.6rem 0 .5rem'>{title}</div>",
        unsafe_allow_html=True,
    )


IN_SAMPLE = "In-sample contribution"
LOO = "Leave-one-out contribution"
PROBABILITY = "Model probability (out-of-fold)"

# The batch picked in the table, kept by id. Streamlit keeps a keyed table's row
# selection when its data changes, and a row position then points at another
# batch; so the pick is stored as an id when the click happens, and the table
# gets a new key whenever its rows change.
PICKED_KEY = "timeline_picked"  # batch id, or None; read by views.drivers
_TABLE_REV_KEY = "timeline_table_rev"
_TABLE_IDS_KEY = "context_ids"  # the table's batch ids as last drawn


def _table_clicked(key: str) -> None:
    """The table's on_select callback: remember the clicked batch by its id."""
    rows = st.session_state[key]["selection"]["rows"]
    ids = st.session_state.get(_TABLE_IDS_KEY) or []
    st.session_state[PICKED_KEY] = ids[rows[0]] if rows and rows[0] < len(ids) else None


def _with_contributions(table: pd.DataFrame, cfg: DashboardConfig, model: ModelRun, parameter: str) -> pd.DataFrame:
    """Add the glassbox model's reading of each batch of interest: its probability and the parameter's contributions."""
    ids = table[cfg.col("batch_id")]
    if "oof_prob" in model.batches:
        table[PROBABILITY] = ids.map(model.batches["oof_prob"]).astype(float)
    if parameter in model.features:
        c = model.contributions[model.contributions["feature"] == parameter].set_index("batch_id")
        table[IN_SAMPLE] = ids.map(c["in_sample"]).astype(float)
        table[LOO] = ids.map(pd.to_numeric(c["loo"], errors="coerce")).astype(float)
    return table


def _signal_summary(charts, ewma: bool, cusum: bool, most: int = 3) -> None:
    """When the shown charts signalled, newest first: when the shift began and which way."""
    shown = [e for e in episodes(charts) if (e.chart == "EWMA" and ewma) or (e.chart == "CUSUM" and cusum)]
    if not shown:
        st.caption("No EWMA or CUSUM signal." if ewma and cusum else f"No {'EWMA' if ewma else 'CUSUM'} signal.")
        return
    words = {"up": "upward", "down": "downward"}
    parts = []
    for e in shown[::-1][:most]:
        when = (f"from {e.start:%Y-%m-%d} (signal {e.first_signal:%Y-%m-%d})" if e.chart == "CUSUM" and e.start < e.first_signal
                else f"from {e.first_signal:%Y-%m-%d}")
        parts.append(f"{e.chart}: {words[e.direction]} shift {when}, {e.signals} batch{'es' if e.signals != 1 else ''} signalling")
    more = f" · and {len(shown) - most} earlier" if len(shown) > most else ""
    st.caption("Signals, newest first: " + " · ".join(parts) + more)


def _use_transform(kind: str) -> None:
    st.session_state["timeline_transform"] = kind


@dataclass
class Plotted:
    """What the plot shows, for the sections below it.

    ``interest_ids``: the batches of interest its site and category filters keep
    (all of them when it draws no plot). ``data``: the plotted rows (batch id,
    date, site, the parameter and the set column), or None without a plot.
    """

    interest_ids: list[str] = field(default_factory=list)
    parameter: str | None = None
    value_type: str = ""
    data: pd.DataFrame | None = None
    filters: list[str] = field(default_factory=list)  # the site and category filters, in words


def render(
    df: pd.DataFrame,
    cfg: DashboardConfig,
    params: pd.DataFrame,
    interest_ids: list[str],
    background_ids: list[str],
    model: ModelRun | None = None,
    table_area=None,
) -> Plotted:
    """The sidebar controls, the title, plot and notes, and the table (in ``table_area`` when given).

    Returns what the plot shows (see ``Plotted``), for the feature relevance
    and statistics sections, so they never describe other batches than the plot.
    """
    available = params[params["name"].isin(df.columns)]
    if available.empty:
        st.error(f"None of the parameters in `{cfg.parameters_path.name}` are columns in the data.")
        return Plotted(list(interest_ids))
    types = dict(zip(available["name"], available["type"]))

    with st.sidebar:
        _group("Parameter")
        parameter = _choose_parameter(available, cfg)
        _group("Display")
        opts = _display_options(df, cfg)
        _group("Colour")
        color_by = st.selectbox(
            "Colour points by", [p for p, t in types.items() if _is_categorical(t)], index=None,
            placeholder="Nothing (grey points)", key="timeline_color",
        )
        category_box = st.container()

    if parameter is None:
        st.info("Pick a parameter in the sidebar.")
        return Plotted(list(interest_ids))
    if not interest_ids and not background_ids:
        st.info("No batches selected. Use **Edit selection** or **Default** above.")
        return Plotted(list(interest_ids))

    warnings: list[str] = []  # about batches of interest, shown with the messages at the bottom
    filters: list[str] = []
    notes: list[str] = []  # shown under the plot

    date_col = cfg.col("manufacturing_date")
    site = opts["site"]
    needed = [cfg.col(p) for p in ("batch_id", "manufacturing_date", "site") if cfg.has(p)] + [parameter, color_by]
    data = combine_sets(df[list(dict.fromkeys(c for c in needed if c))], cfg, interest_ids, background_ids)
    if site:
        at_site = data[cfg.col("site")].astype(str) == site
        elsewhere = data.loc[~at_site & (data[SET_COLUMN] != BACKGROUND_LABEL), cfg.col("batch_id")]
        if not elsewhere.empty:
            warnings.append(f"Interest batches not made at {site}: {', '.join(elsewhere)}")
        data = data[at_site]
        filters.append(f"site {site}")

    color = color_order = None
    with category_box:
        if color_by:
            color, color_order = color_groups(data[color_by], types[color_by], data[date_col])
            picked = st.multiselect(
                "Categories to show", color_order, placeholder="All categories",
                key=f"timeline_categories_{color_by}",
            )
            if picked:
                in_picked = color.isin(picked)
                dropped = data.loc[~in_picked & (data[SET_COLUMN] != BACKGROUND_LABEL), cfg.col("batch_id")]
                if not dropped.empty:
                    warnings.append(f"Interest batches outside the chosen categories: {', '.join(dropped)}")
                data, color = data[in_picked], color[in_picked]
                filters.append(f"{color_by}: {', '.join(map(str, picked))}")
    is_interest = data[SET_COLUMN] != BACKGROUND_LABEL
    kept = set(data.loc[is_interest, cfg.col("batch_id")])
    shown = [b for b in interest_ids if b in kept]

    def finish(plotted: bool = True) -> Plotted:
        for warning in warnings:
            messages.add(warning)
        if not plotted:
            return Plotted(shown)
        return Plotted(shown, parameter, types[parameter], data, filters)

    y, order, unit = plot_values(data[parameter], types[parameter], data[date_col], cfg.dayfirst)
    if order is not None:
        y, order = fold_categories(y, order, keep=set(y[is_interest].dropna()))
    if y.notna().sum() == 0:
        st.warning(f"`{parameter}` has no plottable values for the selected batches.")
        return finish(plotted=False)

    numeric = order is None
    label, raw, ticks = parameter + unit, None, None
    if numeric:
        kind = opts["transform"]
        suggestion = suggest_transform(y, label)
        if suggestion and suggestion[0] != kind:
            with opts["hint"]:
                st.button(
                    f"Suggested: {suggestion[0]}", help=f"Apply {suggestion[0]}: {suggestion[1]}.",
                    on_click=_use_transform, args=(suggestion[0],),
                    icon=":material/lightbulb:", type="tertiary",
                )
        if kind == "Logit" and percent_scale(y, label) is None:
            opts["hint"].warning("Logit needs fractions or percentages. Not applied.")
        elif kind != "None":
            t = apply_transform(y, kind, label)
            raw, y, label, ticks = y, t.values, label + t.axis_suffix, (t.tickvals, t.ticktext)
            if t.out_of_domain:
                notes.append(f"{t.out_of_domain} not {t.domain}")
            if y.notna().sum() == 0:
                st.warning(f"No `{parameter}` value is {t.domain}, so nothing can be shown on the {kind.lower()} scale.")
                return finish()
    elif opts["transform"] != "None" or opts["ewma"] or opts["cusum"]:
        opts["hint"].caption("Only for numerical parameters.")

    if color is not None and color.nunique() > MAX_LEGEND_CATEGORIES:
        notes.append(f"{color.nunique()} categories, {len(CATEGORY_COLORS)} colours repeat (hover for the category)")

    normal = data[SET_COLUMN] == BACKGROUND_LABEL  # the control charts' normal batches
    trend = _fit(data[date_col], y, cfg.trend) if opts["trend"] and numeric else None

    charts = None
    if (opts["ewma"] or opts["cusum"]) and numeric:
        reference = normal
        if opts["reference"] is not None:
            start, end = opts["reference"]
            reference = normal & (data[date_col] >= start) & (data[date_col] < end + pd.Timedelta(days=1))
        charts = control_charts(data[date_col], y, reference=reference, **cfg.spc)

    table = context_table(data, cfg, y, trend, raw, charts)
    if model is not None:
        table = _with_contributions(table, cfg, model, parameter)
    ids = table[cfg.col("batch_id")].tolist()
    if ids != st.session_state.get(_TABLE_IDS_KEY):
        st.session_state[_TABLE_REV_KEY] = st.session_state.get(_TABLE_REV_KEY, 0) + 1
        st.session_state[_TABLE_IDS_KEY] = ids
    picked = st.session_state.get(PICKED_KEY)
    picked_row = ids.index(picked) if picked in ids else None

    not_shown = (y.isna() if raw is None else raw.isna()) | data[date_col].isna()
    interest_missing = data.loc[not_shown & is_interest, cfg.col("batch_id")]
    if not interest_missing.empty:
        warnings.append(f"Interest batches without a value: {', '.join(interest_missing)}")
    if not_shown.any():
        notes.append(f"{int(not_shown.sum())} without value or date")
    if trend is not None:
        changes = ", ".join(f"{bp:%Y-%m-%d}" for bp in trend.breakpoints) or "none"
        notes.append(f"trend ({MODELS[trend.model][1]}) breaks: {changes}")
    if charts is not None:
        scale = ", transformed" if raw is not None else ""
        if charts.from_reference:
            period = (f" made {opts['reference'][0]:%Y-%m-%d} to {opts['reference'][1]:%Y-%m-%d}"
                      if opts["reference"] is not None else "")
            base = f"{charts.baseline} background batches{period}"
        else:
            base = f"first {charts.baseline} batches (too few background batches in the reference period)"
        notes.append(f"EWMA/CUSUM normal from {base}: target {charts.target:.4g}, σ {charts.sigma:.4g}{scale}")
    elif (opts["ewma"] or opts["cusum"]) and numeric:
        notes.append("too few batches for EWMA/CUSUM")

    # The batch picked in the table (below the plot) is highlighted in the plot.
    highlight = picked if picked_row is not None else None

    st.markdown(
        f"<div style='font-size:1.25rem;font-weight:600;line-height:1.4;margin:.4rem 0 0;padding-bottom:.3rem'>{html.escape(label)}</div>",
        unsafe_allow_html=True,
    )
    shade = None
    if charts is not None and charts.from_reference and opts["reference"] is not None:
        start, end = opts["reference"]
        dates = data[date_col].dropna()
        if not dates.empty and (start > dates.min() or end < dates.max().normalize()):
            shade = (start, end + pd.Timedelta(days=1))
    fig = timeline_scatter(
        data, cfg, y, label, order, trend, color, color_order, color_by or "", highlight, raw, ticks,
        ewma=charts if opts["ewma"] else None, cusum=charts if opts["cusum"] else None,
        reference=shade,
    )
    st.plotly_chart(fig, width="stretch", theme="streamlit")
    if notes:
        text = " · ".join(notes)
        st.caption(text[0].upper() + text[1:])
    if charts is not None:
        _signal_summary(charts, opts["ewma"], opts["cusum"])

    if table.empty:
        return finish()
    # Folded, at the bottom (app.py passes a slot below the statistics). The
    # label stays the same so the section keeps its open/closed state.
    with (table_area if table_area is not None else st.container()), st.expander("Batches of interest · click a row to mark it in the plot"):
        _table(table, date_col, picked_row, model.scale if model is not None else None)
    return finish()


def _table(table: pd.DataFrame, date_col: str, picked_row: int | None, scale: str | None) -> None:
    """The table, with the picked batch's row selected; contributions labelled with their scale."""
    key = f"context_table_{st.session_state.get(_TABLE_REV_KEY, 0)}"
    unit = f" ({scale})" if scale else ""
    st.dataframe(
        table,
        key=key,
        on_select=lambda: _table_clicked(key),
        selection_mode="single-row",
        # Applied when a new key starts the table afresh, so the pick survives.
        selection_default={"selection": {"rows": [picked_row]}} if picked_row is not None else None,
        hide_index=True,
        width="stretch",
        column_config={
            date_col: st.column_config.DateColumn(format="YYYY-MM-DD"),
            PERCENTILE: st.column_config.NumberColumn(format="%.0f"),
            SAME_VALUE: st.column_config.NumberColumn(format="%.0f"),
            DEVIATION: st.column_config.NumberColumn(format="%+.2f"),
            SEGMENT: st.column_config.NumberColumn(format="%d"),
            IN_SAMPLE: st.column_config.NumberColumn(IN_SAMPLE + unit, format="%+.3f"),
            LOO: st.column_config.NumberColumn(LOO + unit, format="%+.3f"),
            PROBABILITY: st.column_config.NumberColumn(format="%.2f"),
        },
    )
