"""What the monitoring pages share: the sidebar filters, the scorecard table and a parameter's trend with its statistics."""

from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd
import streamlit as st

from .. import monitor as M
from .. import stats as S
from ..config import DashboardConfig
from ..data import REMANUFACTURED
from ..monitor_plots import category_share_figure
from ..plots import BACKGROUND_LABEL, SET_COLUMN, rate_figure, timeline_scatter
from ..selection import RemanufactureFilter, SelectionMode
from ..spc import control_charts
from ..trend import MODELS, fit_trend
from . import nav
from .loading import load

PERIODS = {"Last 6 months": 183, "Last 12 months": 365, "Last 24 months": 730, "All data": None, "Custom": 0}
RECENT = [30, 60, 90, 180]
REMAN = ["Include", "Exclude", "Only"]
PLOT_CONFIG = {"displayModeBar": False}
STATUS_TEXT = {M.STATUS_WATCH: "◆ Watch", M.STATUS_STABLE: "Stable", M.STATUS_FEW: "Too few batches"}


@dataclass
class Ctx:
    """The data and the windows a monitoring page works on."""

    cfg: DashboardConfig
    df: pd.DataFrame
    params: pd.DataFrame  # the parameters with a column in the data
    s: M.Settings
    values: pd.DataFrame  # the numerical parameters as floats
    units: dict[str, str]
    key: tuple  # changes when the data files change
    as_of: pd.Timestamp
    start: pd.Timestamp
    end: pd.Timestamp
    recent_start: pd.Timestamp
    rows: pd.Series  # the site and re-manufacture filters
    period: pd.Series  # rows within [start, end]
    recent: pd.Series
    baseline: pd.Series
    score: pd.DataFrame  # monitor.scorecard over every numerical parameter
    filters: tuple  # the filter state, for cache keys

    @property
    def dates(self) -> pd.Series:
        return self.df[self.cfg.col("manufacturing_date")]

    def label(self, name: str) -> str:
        return name + self.units.get(name, "")

    def meta(self, column: str | None) -> pd.Series:
        """A metadata column by parameter name (empty strings when the metadata has no such column)."""
        if column is None or column not in self.params:
            return pd.Series("", index=self.params["name"])
        return self.params.set_index("name")[column].fillna("").astype(str)

    def names(self, mask: pd.Series) -> list[str]:
        return self.params.loc[mask.to_numpy(bool), "name"].tolist()

    def windows_text(self) -> str:
        return (f"Recent: {int(self.recent.sum()):,} batches started {self.recent_start:%Y-%m-%d} to {self.end:%Y-%m-%d} · "
                f"baseline: {int(self.baseline.sum()):,} batches from {self.start:%Y-%m-%d}")


@st.cache_data(show_spinner="Reading the parameter values…")
def _values(key: tuple, _df: pd.DataFrame, _params: pd.DataFrame, _cfg: DashboardConfig):
    return M.numeric_frame(_df, _params, _cfg)


@st.cache_data(show_spinner=False)
def _as_of(key: tuple, _df: pd.DataFrame, _s: M.Settings, _cfg: DashboardConfig) -> pd.Timestamp:
    return M.as_of(_df, _s, _cfg)


@st.cache_data(show_spinner="Comparing the recent window with the baseline…")
def _score(key: tuple, filters: tuple, _values, _dates, _recent, _baseline, _spc, _directions) -> pd.DataFrame:
    return M.scorecard(_values, _dates, _recent, _baseline, _spc, _directions)


@st.cache_data(show_spinner="Fitting trend…")
def _fit(dates: pd.Series, values: pd.Series, settings: dict):
    return fit_trend(dates, values, **settings)


def group(title: str) -> None:
    """A small heading for a group of controls."""
    st.markdown(
        f"<div style='font-size:.75rem;font-weight:600;letter-spacing:.06em;text-transform:uppercase;"
        f"opacity:.6;margin:.6rem 0 .5rem'>{html.escape(title)}</div>",
        unsafe_allow_html=True,
    )


def heading(title: str, caption: str = "") -> None:
    st.markdown(
        f"<div style='font-size:1.05rem;font-weight:600;margin:.9rem 0 0'>{html.escape(title)}</div>"
        + (f"<div style='font-size:.8rem;opacity:.65;margin-bottom:.2rem'>{html.escape(caption)}</div>" if caption else ""),
        unsafe_allow_html=True,
    )


def context(title: str, caption: str = "") -> Ctx:
    """Load the data, draw the page title and the sidebar filters, and return what the page works on."""
    cfg, df, params, key = load()
    available = params[params["name"].isin(df.columns)].reset_index(drop=True)
    s = M.settings(cfg, df, available)
    values, units = _values(key, df, available, cfg)
    as_of = _as_of(key, df, s, cfg)
    dates = df[cfg.col("manufacturing_date")]
    first = dates.min() if dates.notna().any() else as_of

    ss = st.session_state
    ss.setdefault("mon_period", "Last 12 months")
    ss.setdefault("mon_recent", min(RECENT, key=lambda d: abs(d - s.recent_days)))
    with st.sidebar:
        group("Period")
        choice = st.selectbox("Period", list(PERIODS), key="mon_period",
                              help="The batches the page looks at, by manufacturing start. It ends at the data's last date.")
        start, end = (as_of - pd.Timedelta(days=PERIODS[choice] - 1) if PERIODS[choice] else first), as_of
        if choice == "Custom":
            kept = ss.get("mon_dates")
            if not (isinstance(kept, (list, tuple)) and len(kept) == 2):
                ss["mon_dates"] = ((as_of - pd.Timedelta(days=364)).date(), as_of.date())
            picked = st.date_input("Manufacturing dates", key="mon_dates", min_value=first.date(), max_value=as_of.date())
            if isinstance(picked, (list, tuple)) and len(picked) == 2:
                start, end = pd.Timestamp(picked[0]), pd.Timestamp(picked[1])
            else:
                start = as_of - pd.Timedelta(days=364)
        recent_days = st.selectbox(
            "Recent window", RECENT, format_func=lambda d: f"Last {d} days", key="mon_recent",
            help="The newest part of the period. Everything is compared with the baseline: the rest of the period, before it.",
        )
        group("Batches")
        sites: list[str] = []
        if cfg.has("site"):
            options = sorted(df[cfg.col("site")].dropna().astype(str).unique())
            ss["mon_sites"] = [x for x in ss.get("mon_sites", []) if x in options]
            sites = st.multiselect("Manufacturing sites", options, placeholder="All sites", key="mon_sites")
        reman = "Include"
        if cfg.has("remanufacture"):
            reman = st.selectbox("Re-manufactured batches", REMAN, key="mon_reman")

    rows = pd.Series(True, index=df.index)
    if sites:
        rows &= df[cfg.col("site")].astype("string").isin(sites)
    if reman != "Include":
        rows &= df[REMANUFACTURED] == (reman == "Only")
    recent, baseline = M.windows(dates, start, end, recent_days)
    recent, baseline = recent & rows, baseline & rows
    recent_start = pd.Timestamp(end).normalize() + pd.Timedelta(days=1 - recent_days)
    filters = (str(pd.Timestamp(start).date()), str(pd.Timestamp(end).date()), recent_days, tuple(sites), reman)
    directions = dict(zip(available["name"], available["direction"])) if "direction" in available else None
    score = _score(key, filters, values, dates, recent, baseline, cfg.spc, directions)
    ctx = Ctx(cfg, df, available, s, values, units, key, as_of, pd.Timestamp(start), pd.Timestamp(end), recent_start,
              rows, recent | baseline, recent, baseline, score, filters)

    with st.sidebar:
        st.divider()
        st.caption(
            f"Data as of {as_of:%Y-%m-%d}  \n{df[cfg.col('batch_id')].nunique():,} batches in {cfg.csv_path.name}  \n"
            f"Config: {cfg.source_path.name}"
        )
    st.markdown(
        f"<div style='font-size:1.4rem;font-weight:600;line-height:1.3'>{html.escape(title)}</div>"
        f"<div style='font-size:.85rem;opacity:.7;margin-bottom:.3rem'>{html.escape(caption + ' ' if caption else '')}"
        f"{html.escape(ctx.windows_text())}.</div>",
        unsafe_allow_html=True,
    )
    return ctx


# --------------------------------------------------------------------------- scorecard


def status_text(status: str, shift: float) -> str:
    if status == M.STATUS_SHIFTED:
        return "▲ Shifted up" if shift > 0 else "▼ Shifted down"
    return STATUS_TEXT.get(status, status)


def status_counts(rows: pd.DataFrame) -> str:
    counts = rows["status"].value_counts()
    parts = [f"{len(rows)} numerical parameters"]
    parts += [f"**{counts[k]} {k.lower()}**" if k != M.STATUS_STABLE else f"{counts[k]} stable"
              for k in (M.STATUS_SHIFTED, M.STATUS_WATCH, M.STATUS_STABLE) if counts.get(k)]
    if counts.get(M.STATUS_FEW):
        parts.append(f"{counts[M.STATUS_FEW]} with too few batches")
    return " · ".join(parts)


def table_height(rows: int, most: int = 320) -> int:
    """The height of a table with ``rows`` rows, capped at ``most`` pixels."""
    return min(most, 39 + 35 * max(rows, 1))


def scorecard(ctx: Ctx, names: list[str], key: str, height: int = 320) -> str | None:
    """The scorecard of ``names`` as a table; returns the parameter picked in it (the first row by default).

    The pick is remembered by name, so it survives a filter change that
    reorders the rows.
    """
    rows = ctx.score[ctx.score["parameter"].isin(set(names))].reset_index(drop=True)
    if rows.empty:
        st.info("No numerical parameters here.")
        return None
    left, right = st.columns([5, 2], vertical_alignment="center")
    left.markdown(status_counts(rows))
    if right.toggle("Only shifted or on watch", key=f"mon_only_{key}"):
        rows = rows[rows["status"].isin([M.STATUS_SHIFTED, M.STATUS_WATCH])].reset_index(drop=True)
        if rows.empty:
            st.success("Nothing shifted or on watch.")
            return None
    day = ctx.meta(ctx.s.process_day)
    table = pd.DataFrame({
        "Status": [status_text(s, x) for s, x in zip(rows["status"], rows["shift"])],
        "Parameter": rows["parameter"],
        "Process day": rows["parameter"].map(day).fillna(""),
        "Recent": rows["recent"], "Baseline": rows["baseline"], "Shift (SD)": rows["shift"], "q": rows["q"],
        "Beyond ±3 SD": rows["outside"], "EWMA signals": rows["ewma"], "Trend": rows["trend"], "n recent": rows["n_recent"],
    })
    names_shown = rows["parameter"].tolist()
    remembered = st.session_state.get(f"mon_pick_{key}")
    default = names_shown.index(remembered) if remembered in names_shown else 0
    table_key = f"tbl_{key}_{hash(tuple(names_shown)) & 0xFFFFFF}_{default}"
    event = st.dataframe(
        table, key=table_key, hide_index=True, width="stretch", height=table_height(len(table), height),
        on_select="rerun", selection_mode="single-row",
        selection_default={"selection": {"rows": [default]}},
        column_config={
            "Status": st.column_config.TextColumn(help=(
                f"Shifted: the recent median differs from the baseline (q < {M.ALPHA}) by at least {M.SHIFT_SD} SD. "
                "Watch: a smaller significant difference, the EWMA outside its limits at the latest batch, or more "
                "batches beyond ±3 SD than chance gives.")),
            "Parameter": st.column_config.TextColumn(width="large"),
            "Recent": st.column_config.NumberColumn(format="%.4g", help="Median of the recent window."),
            "Baseline": st.column_config.NumberColumn(format="%.4g", help="Median of the baseline."),
            "Shift (SD)": st.column_config.NumberColumn(format="%+.2f", help="Recent median minus baseline median, in baseline standard deviations (robust)."),
            "q": st.column_config.NumberColumn(format="%.3f", help="Mann-Whitney p-value, corrected for testing every parameter (Benjamini-Hochberg)."),
            "Beyond ±3 SD": st.column_config.NumberColumn(help="Recent batches further than 3 baseline SD from the baseline median."),
            "EWMA signals": st.column_config.NumberColumn(help="Recent batches at which the EWMA chart (normal from the baseline) is outside its limits."),
            "Trend": st.column_config.LineChartColumn(width="small", help="Monthly medians over the period."),
        },
    )
    picked = event.selection.rows if event and event.selection else []
    name = names_shown[picked[0]] if picked and picked[0] < len(names_shown) else names_shown[default]
    st.session_state[f"mon_pick_{key}"] = name
    return name


# --------------------------------------------------------------------------- one parameter


def investigate(ctx: Ctx, parameter: str | None = None, batch: str | None = None) -> None:
    """Open the investigation page on a parameter (recent window against the baseline) or on one batch."""
    from .drivers import select_parameter  # here: drivers imports timeline, which is heavy

    ss = st.session_state
    if parameter is not None:
        select_parameter(parameter, ctx.params, ctx.cfg)
    sites = sorted(ctx.df[ctx.cfg.col("site")].dropna().astype(str).unique()) if ctx.cfg.has("site") else None
    day = timedelta(days=1)
    if batch is not None:
        ss["interest_mode"], ss["interest_single"] = SelectionMode.SINGLE, batch
        ss["background_dates"] = ((ctx.as_of - pd.Timedelta(days=365)).date(), ctx.as_of.date())
    else:
        ss["interest_mode"] = SelectionMode.TIME_FRAME
        ss["interest_dates"] = (ctx.recent_start.date(), ctx.end.date())
        ss["background_dates"] = (ctx.start.date(), max(ctx.start.date(), ctx.recent_start.date() - day))
    ss["background_mode"] = SelectionMode.TIME_FRAME
    for prefix in ("interest", "background"):
        ss[f"{prefix}_reman"] = RemanufactureFilter.ALL
        if sites is not None:
            ss[f"{prefix}_sites"] = list(ctx.filters[3]) or sites
    ss["background_exclude_interest"] = True
    nav.go("investigation")


def _card(headline: str, lines: list[str]) -> None:
    items = "".join(f"<li>{html.escape(line)}</li>" for line in lines)
    st.markdown(
        f"<div style='margin:.2rem 0 .6rem'><div style='font-size:1rem;font-weight:600;line-height:1.4;"
        f"margin-bottom:.2rem'>{html.escape(headline)}</div><ul style='margin:0;padding-left:1.2rem;font-size:.9rem'>"
        f"{items}</ul></div>",
        unsafe_allow_html=True,
    )


def comparison_card(ctx: Ctx, name: str) -> None:
    """The recent window against the baseline for one parameter, in sentences."""
    x = ctx.values[name]
    c = S.compare_numeric(x[ctx.recent], x[ctx.baseline])
    row = ctx.score[ctx.score["parameter"] == name]
    if not c.tested:
        _card(f"Too few batches to compare ({c.n1} recent, {c.n2} baseline; {S.MIN_BATCHES} of each are needed).", [])
        return
    word = {"higher": "higher than", "lower": "lower than"}.get(c.direction or "", "not clearly different from")
    q = float(row["q"].iloc[0]) if len(row) else np.nan
    lines = [
        f"Median {S.fmt_num(c.median1)} in the recent window ({c.n1:,} batches) against {S.fmt_num(c.median2)} "
        f"in the baseline ({c.n2:,} batches).",
        f"Typical difference {S.fmt_num(c.shift)} (95% CI {S.fmt_num(c.shift_lo)} to {S.fmt_num(c.shift_hi)}; Hodges-Lehmann).",
        f"A recent batch is higher than a baseline batch {S.fmt_pct(c.auc)} of the time (95% CI {S.fmt_pct(c.auc_lo)}"
        f"–{S.fmt_pct(c.auc_hi)}); Mann-Whitney {S.fmt_p(c.p)}"
        + (f", {S.fmt_p(q).replace('p', 'q', 1)} over all parameters." if np.isfinite(q) else "."),
    ]
    if len(row):
        r = row.iloc[0]
        lines.append(f"{int(r['outside'])} recent batches beyond ±3 SD of the baseline; the EWMA is outside its limits at "
                     f"{int(r['ewma'])} recent batches" + (", the latest included." if r["ewma_now"] else "."))
    _card(f"Recent batches are {word} the baseline.", lines)


def parameter_detail(ctx: Ctx, name: str, key: str) -> None:
    """A parameter's trend plot over the period, with the recent-against-baseline statistics under it."""
    cfg = ctx.cfg
    label = ctx.label(name)
    info = " · ".join(v for v in (ctx.meta(c).get(name, "") for c in (ctx.s.process_day, ctx.s.functional_type,
                                                                       ctx.s.variation_source)) if v)
    head, button = st.columns([6, 1.6], vertical_alignment="bottom")
    head.markdown(
        f"<div style='font-size:1.15rem;font-weight:600;margin-top:.6rem'>{html.escape(label)}</div>"
        f"<div style='font-size:.8rem;opacity:.65'>{html.escape(info)}</div>",
        unsafe_allow_html=True,
    )
    if button.button("Investigate", icon=":material/query_stats:", key=f"mon_inv_{key}", width="stretch",
                     help="Open the investigation page on this parameter: the recent window as the batches of "
                          "interest, the baseline as the background."):
        investigate(ctx, name)
    description = ctx.meta("description").get(name, "")
    if description:
        st.caption(description if len(description) <= 220 else description[:217].rsplit(" ", 1)[0] + "…")

    row = st.container(horizontal=True, gap="small")
    st.session_state.setdefault(f"mon_trend_{key}", True)
    trend_on = row.checkbox("Trend fit", key=f"mon_trend_{key}")
    ewma_on = row.checkbox("EWMA", key=f"mon_ewma_{key}")
    cusum_on = row.checkbox("CUSUM", key=f"mon_cusum_{key}")
    by_site = cfg.has("site") and row.checkbox("Colour by site", key=f"mon_bysite_{key}")

    date_col = cfg.col("manufacturing_date")
    columns = [cfg.col("batch_id"), date_col] + ([cfg.col("site")] if cfg.has("site") else [])
    data = ctx.df.loc[ctx.period, columns].assign(**{SET_COLUMN: BACKGROUND_LABEL})
    y = ctx.values.loc[ctx.period, name]
    if y.notna().sum() == 0:
        st.info("No values in this period.")
        return
    trend = _fit(data[date_col], y, cfg.trend) if trend_on else None
    charts = None
    if ewma_on or cusum_on:
        direction = ctx.meta("direction").get(name, "both") or "both"
        charts = control_charts(data[date_col], y, reference=ctx.baseline[ctx.period], direction=direction, **cfg.spc)
    color = order = None
    if by_site:
        color = data[cfg.col("site")].astype("string").fillna("(no site)")
        order = sorted(color.unique())
    fig = timeline_scatter(
        data, cfg, y, label, None, trend, color, order, "Site",
        ewma=charts if ewma_on else None, cusum=charts if cusum_on else None,
        reference=(ctx.recent_start, ctx.end + pd.Timedelta(days=1)), reference_label="recent window",
        show_interest=False,
    )
    st.plotly_chart(fig, width="stretch", theme="streamlit", key=f"plot_{key}")
    notes = []
    if trend is not None:
        notes.append(f"Trend ({MODELS[trend.model][1]}) breaks: " + (", ".join(f"{b:%Y-%m-%d}" for b in trend.breakpoints) or "none"))
    if charts is not None:
        notes.append(f"EWMA/CUSUM normal from the baseline: target {charts.target:.4g}, σ {charts.sigma:.4g}")
    if notes:
        st.caption(" · ".join(notes))

    left, right = st.columns(2, gap="medium")
    with left:
        comparison_card(ctx, name)
    with right:
        _oos_by_value(ctx, name)


def _oos_by_value(ctx: Ctx, name: str) -> None:
    """The OOS rate in quarters of the parameter's values, over the period."""
    if not ctx.s.oos_flag or name == ctx.s.oos_flag:
        return
    oos = M.flag(ctx.df[ctx.s.oos_flag], ctx.s.truthy)
    use = ctx.period & oos.notna() & ctx.values[name].notna()
    table = S.rate_by_value(ctx.values.loc[use, name], oos[use].astype(bool))
    if table is None or not table["k"].sum():
        return
    overall = S.wilson(int(table["k"].sum()), int(table["n"].sum())).p
    st.plotly_chart(
        rate_figure(table, table["group"], overall, "OOS rate by value (quarters of the batches) · 95% intervals"),
        width="stretch", theme="streamlit", config=PLOT_CONFIG,
    )


# --------------------------------------------------------------------------- categorical parameters


def categorical_names(ctx: Ctx, names: list[str], most: int = 30) -> list[str]:
    """The categorical parameters among ``names`` with 2 to ``most`` categories in the period (ids and lots drop out)."""
    wanted = set(names)
    out = []
    for name, vtype in zip(ctx.params["name"], ctx.params["type"]):
        kind = vtype.strip().lower()
        if name in wanted and name not in ctx.values and (kind == "categorical" or kind.startswith("[")):
            if 2 <= ctx.df.loc[ctx.period, name].nunique() <= most:
                out.append(name)
    return out


def categorical_section(ctx: Ctx, names: list[str], key: str) -> None:
    """Pick a categorical parameter: its categories' share per month, and recent against baseline."""
    options = categorical_names(ctx, names)
    if not options:
        return
    with st.expander(f"Categorical parameters ({len(options)})"):
        name = st.selectbox("Parameter", options, key=f"mon_cat_{key}")
        text = ctx.df[name].astype("string").str.strip()
        table, p = M.categorical_shift(text, ctx.recent, ctx.baseline)
        left, right = st.columns([3, 2], gap="medium")
        with left:
            st.plotly_chart(category_share_figure(ctx.dates[ctx.period], text[ctx.period]), width="stretch",
                            theme="streamlit", config=PLOT_CONFIG)
        with right:
            st.dataframe(
                table.rename(columns={"category": "Category", "recent_n": "Recent n", "recent": "Recent",
                                      "baseline_n": "Baseline n", "baseline": "Baseline"}),
                hide_index=True, width="stretch",
                column_config={"Recent": st.column_config.NumberColumn(format="percent"),
                               "Baseline": st.column_config.NumberColumn(format="percent")},
            )
            if np.isfinite(p):
                verdict = "differs from" if p < M.ALPHA else "is not clearly different from"
                st.caption(f"The mix of categories in the recent window {verdict} the baseline ({S.fmt_p(p)}).")
            else:
                st.caption(f"Too few batches to test (at least {S.MIN_BATCHES} per window).")
