"""Plot builders. They return Plotly figures and do not depend on Streamlit."""

from __future__ import annotations

import re

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from .config import DashboardConfig
from .spc import ControlCharts
from .trend import MODELS, TrendFit

INTEREST_LABEL = "Batch(es) of interest"
BACKGROUND_LABEL = "Background"
SET_COLUMN = "Set"
OTHER_LABEL = "Other"

NO_VALUE_LABEL = "(no value)"

# Points are grey unless coloured by a column. Batches of interest get a dark
# blue ring, the trend is orange, so no dark blue, red, pink or orange is in the
# category palette.
POINT_COLOR = "#9c9b95"
NO_VALUE_COLOR = "#d3d2cc"
INTEREST_COLOR = "#0047ab"
TREND_COLOR = "#eb6834"
SPC_COLOR = "#2c3e50"
REFERENCE_FILL = "rgba(42, 120, 214, 0.07)"  # the reference period


CATEGORY_COLORS = ["#7a8b00", "#35a02c", "#e5b400", "#12a4b6", "#6a3fb5", "#8c6239"]
MAX_LEGEND_CATEGORIES = 12
# A batch of interest's ring hugs the outside of its point: the stroke's inner
# edge sits on the point's edge (a ring's size is the diameter of its stroke's centre).
POINT_SIZE = 6
RING_WIDTH = 1.5
RING_SIZE = POINT_SIZE + RING_WIDTH

_ORDERED = re.compile(r"^\[(.*)\]$")
_CLOCK = re.compile(r"^\d{1,2}:\d{2}(:\d{2})?$")
_RATIO = re.compile(r"^\s*([\d.]+)\s*:\s*([\d.]+)\s*$")
# A datetime column is read as clock times when at least this share of its
# values are hh:mm[:ss], the same tolerance as numbers in an untyped column.
_CLOCK_SHARE = 0.8


def combine_sets(
    df: pd.DataFrame, cfg: DashboardConfig, interest_ids: list[str], background_ids: list[str]
) -> pd.DataFrame:
    """Rows of both sets with a ``Set`` column. Interest wins if a batch is in both."""
    batch_col = cfg.col("batch_id")
    interest = df[df[batch_col].isin(interest_ids)].assign(**{SET_COLUMN: INTEREST_LABEL})
    background = df[
        df[batch_col].isin(background_ids) & ~df[batch_col].isin(interest_ids)
    ].assign(**{SET_COLUMN: BACKGROUND_LABEL})
    return pd.concat([background, interest], ignore_index=True)


def _is_clock(s: pd.Series) -> pd.Series:
    """True where a string is an 'hh:mm[:ss]' clock time."""
    return s.str.match(_CLOCK).fillna(False).astype(bool)


def _clock_hours(s: pd.Series) -> pd.Series:
    """'hh:mm[:ss]' strings to decimal hours; anything else becomes NaN.

    Seconds count as zero where they are left out, so 'hh:mm' and 'hh:mm:ss'
    can share a column.
    """
    clock = s.where(_is_clock(s))
    if clock.isna().all():
        return pd.Series(float("nan"), index=s.index)
    parts = clock.str.split(":", expand=True).apply(pd.to_numeric, errors="coerce")
    hours = parts[0] + parts[1] / 60
    return hours + parts[2].fillna(0) / 3600 if 2 in parts else hours


def _ratio(s: pd.Series) -> pd.Series:
    """'a:b' strings to a / b."""
    parts = s.str.extract(_RATIO).apply(pd.to_numeric, errors="coerce")
    return parts[0] / parts[1]


def plot_values(
    raw: pd.Series, value_type: str, mfg_dates: pd.Series, dayfirst: bool = False
) -> tuple[pd.Series, list[str] | None, str]:
    """Turn a raw column into something plottable according to its value type.

    Returns ``(y, category_order, unit)``: ``category_order`` is None for a
    numerical y, and ``unit`` is appended to the axis title.
    """
    text = raw.astype("string").str.strip()
    vt = value_type.strip()

    if m := _ORDERED.match(vt):
        order = [c.strip() for c in m.group(1).split(",")]
        extra = sorted(set(text.dropna()) - set(order))
        return text, order + extra, ""

    if vt.lower() == "categorical":
        return text, text.value_counts().index.tolist(), ""

    if vt.lower() == "datetime":
        clock = _is_clock(text)
        given = int(text.notna().sum())
        if given and clock.sum() >= _CLOCK_SHARE * given:
            return _clock_hours(text), None, " (hour of day)"
        # A bare clock time among dates has no date: parsed, it would become
        # today at that time, hundreds of days from its batch's manufacturing.
        dt = pd.to_datetime(text.where(~clock), format="mixed", dayfirst=dayfirst, errors="coerce")
        return (dt - mfg_dates).dt.total_seconds() / 86400, None, " (days from manufacturing start)"

    num = pd.to_numeric(text, errors="coerce")
    if vt.lower() == "duration":
        return num, None, " (min)"
    if vt.lower() == "ratio":
        return num.fillna(_ratio(text)), None, ""
    if vt.lower() == "numeric" or num.notna().sum() >= 0.8 * text.notna().sum():
        return num, None, ""
    return text, text.value_counts().index.tolist(), ""


def fold_categories(
    y: pd.Series, order: list[str], keep: set[str], max_categories: int = 30
) -> tuple[pd.Series, list[str]]:
    """Fold rare categories into 'Other', never folding a category in ``keep``."""
    if len(order) <= max_categories:
        return y, order
    kept = [c for c in order if c in keep]
    kept += [c for c in order if c not in keep][: max(max_categories - len(kept), 0)]
    folded = y.where(y.isin(kept) | y.isna(), OTHER_LABEL)
    return folded, [c for c in order if c in kept] + [OTHER_LABEL]


def color_groups(raw: pd.Series, value_type: str, dates: pd.Series) -> tuple[pd.Series, list[str]]:
    """Categories to colour points by, in colour order; missing values become NO_VALUE_LABEL.

    Ordered types keep their listed order; other categories are ordered by the
    date they first appear, so a colour cycled over the order (see
    category_palette) differs between neighbouring lots.
    """
    text = raw.astype("string").str.strip()
    present = set(text.dropna())
    if m := _ORDERED.match(value_type.strip()):
        order = [c.strip() for c in m.group(1).split(",")]
        order = [c for c in order if c in present] + sorted(present - set(order))
    else:
        first_seen = pd.DataFrame({"c": text, "d": pd.to_datetime(dates)}).dropna().sort_values("d", kind="stable")
        order = first_seen["c"].unique().tolist()
        order += sorted(present - set(order))  # categories only on rows without a date
    if text.isna().any():
        order.append(NO_VALUE_LABEL)
    return text.fillna(NO_VALUE_LABEL), order


def category_palette(order: list[str]) -> dict[str, str]:
    """Colour per category: CATEGORY_COLORS repeated in order, light grey for no value."""
    cats = [c for c in order if c != NO_VALUE_LABEL]
    return {c: CATEGORY_COLORS[i % len(CATEGORY_COLORS)] for i, c in enumerate(cats)} | {NO_VALUE_LABEL: NO_VALUE_COLOR}


def timeline_scatter(
    data: pd.DataFrame,
    cfg: DashboardConfig,
    y: pd.Series,
    y_label: str,
    category_order: list[str] | None = None,
    trend: TrendFit | None = None,
    color: pd.Series | None = None,
    color_order: list[str] | None = None,
    color_label: str = "",
    highlight: str | None = None,
    raw: pd.Series | None = None,
    ticks: tuple[list[float], list[str]] | None = None,
    ewma: ControlCharts | None = None,
    cusum: ControlCharts | None = None,
    reference: tuple[pd.Timestamp, pd.Timestamp] | None = None,
) -> go.Figure:
    """Scatter of ``y`` (aligned with ``data``) against manufacturing date.

    Points are grey, or coloured by the categories in ``color`` (aligned with
    ``data``, from color_groups). Colours repeat after len(CATEGORY_COLORS)
    categories; the legend lists the categories only when there are at most
    MAX_LEGEND_CATEGORIES. Batches of interest get a dark blue ring, and the
    ``highlight`` batch id a labelled star.
    With ``trend`` (fitted on the same rows, in the same order) the segment
    lines, excluded outliers and breakpoint dates are drawn as well.
    ``y`` may be transformed: then ``raw`` holds the original values for the
    hover text and ``ticks`` (values, labels) label the y-axis in original units.
    ``ewma`` adds the EWMA with its control limits on the same axes, ``cusum``
    a CUSUM panel below with a shared date axis.
    ``reference`` shades the reference period. A range slider under the
    date axis zooms to a time period.
    """
    batch_col = cfg.col("batch_id")
    date_col = cfg.col("manufacturing_date")
    shown = y.notna() & data[date_col].notna()

    groups: list[tuple[str, str, pd.Series]] = [("Batches", POINT_COLOR, shown)]
    if color is not None:
        palette = category_palette(color_order)  # from the full order, so colours survive filtering
        groups = [(c, palette[c], shown & (color == c)) for c in color_order]
        groups = [g for g in groups if g[2].any()]
    show_legend = len(groups) <= MAX_LEGEND_CATEGORIES

    panels = ["main"] + (["cusum"] if cusum else [])
    heights = {"main": 0.7, "cusum": 0.3}
    row_of = {name: i + 1 for i, name in enumerate(panels)}
    fig = make_subplots(
        rows=len(panels), cols=1, shared_xaxes=True, vertical_spacing=0.05,
        row_heights=[heights[p] for p in panels],
    ) if len(panels) > 1 else make_subplots()
    for label, colour, keep in groups:
        subset, ys = data[keep], y[keep]
        customdata = [subset[batch_col]]
        hover = ["<b>%{customdata[0]}</b>", "%{x|%Y-%m-%d}", f"{y_label}: %{{y}}"]
        if raw is not None:
            customdata.append(raw[keep])
            hover[2] = f"{y_label}: %{{customdata[1]}}"
        if cfg.has("site"):
            customdata.append(subset[cfg.col("site")].astype(str))
            hover.append(f"Site: %{{customdata[{len(customdata) - 1}]}}")
        if color is not None:
            customdata.append(color[keep])
            hover.append(f"{color_label}: %{{customdata[{len(customdata) - 1}]}}")
        fig.add_trace(
            go.Scatter(  # SVG, not WebGL: WebGL points vanished in part when scrolling the page.
                x=subset[date_col],
                y=ys,
                mode="markers",
                name=f"{label} (n={len(subset)})",
                marker=dict(color=colour, size=POINT_SIZE, opacity=0.75, line=dict(width=0)),
                showlegend=show_legend,
                customdata=list(zip(*customdata)) if len(subset) else None,
                hovertemplate="<br>".join(hover) + "<extra></extra>",
            )
        )

    interest = shown & (data[SET_COLUMN] == INTEREST_LABEL)
    fig.add_trace(
        go.Scatter(
            x=data.loc[interest, date_col],
            y=y[interest],
            mode="markers",
            name=f"{INTEREST_LABEL} (n={int(interest.sum())})",
            marker=dict(symbol="circle-open", size=RING_SIZE, color=INTEREST_COLOR, line=dict(width=RING_WIDTH)),
            hoverinfo="skip",
        )
    )

    if trend is not None:
        _add_trend(fig, data, y, trend, date_col)
    if reference is not None:
        fig.add_vrect(
            x0=reference[0], x1=reference[1], fillcolor=REFERENCE_FILL, line_width=0, layer="below", row=1, col=1,
            annotation_text="reference period", annotation_position="top left", annotation_font_size=10,
        )

    picked = shown & (data[batch_col] == highlight) if highlight else None
    if picked is not None and picked.any():
        x0, y0 = data.loc[picked, date_col].iloc[0], y[picked].iloc[0]
        fig.add_trace(
            go.Scatter(
                x=[x0], y=[y0], mode="markers", name=f"Selected: {highlight}",
                marker=dict(symbol="star", size=14, color=INTEREST_COLOR, line=dict(width=1, color="white")),
                hoverinfo="skip",
            )
        )
        fig.add_annotation(
            x=x0, y=y0, text=f"<b>{highlight}</b>", ax=0, ay=-40, arrowcolor=INTEREST_COLOR,
            font=dict(color=INTEREST_COLOR, size=12), bgcolor="rgba(255,255,255,0.85)",
        )

    if ewma is not None:
        _add_ewma(fig, ewma)
    height = 480
    if cusum is not None:
        _add_cusum(fig, cusum, row_of["cusum"])
        height += 200
    if ticks is not None:
        fig.update_yaxes(tickvals=ticks[0], ticktext=ticks[1], row=1, col=1)
    if category_order is not None:
        fig.update_yaxes(type="category", categoryorder="array", categoryarray=category_order[::-1])
        height = max(height, 24 * len(category_order) + 160)
    fig.update_yaxes(title_text=y_label, row=1, col=1)
    fig.update_xaxes(title_text="Manufacturing date", row=len(panels), col=1)
    # Time-period zoom: drag the handles of the slider under the plot.
    fig.update_xaxes(rangeslider=dict(visible=True, thickness=0.08), row=len(panels), col=1)
    height += 60
    fig.update_layout(
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(l=10, r=10, t=90 if ewma or cusum else 35, b=10),  # room for a two-line legend
        hovermode="closest",
        font=dict(size=11),
        height=height,
    )
    return fig


def _add_trend(fig: go.Figure, data: pd.DataFrame, y: pd.Series, trend: TrendFit, date_col: str) -> None:
    model = MODELS[trend.model][1]
    for i, seg in enumerate(trend.segments):
        xs = [seg.start, seg.end]
        fig.add_trace(
            go.Scatter(
                x=xs,
                y=[seg.value_at(x) for x in xs],
                mode="lines",
                line=dict(color=TREND_COLOR, width=2),
                name=f"Trend fit ({model})",
                legendgroup="trend",
                showlegend=i == 0,
                hovertemplate=(
                    f"Segment {i + 1}: {seg.start:%Y-%m-%d} to {seg.end:%Y-%m-%d}, n={seg.n}"
                    f"<br>Level: {seg.intercept:.3g}, slope: {seg.slope_per_year:.3g} per year"
                    f"<br>Model: {model}<extra></extra>"
                ),
            )
        )

    if trend.outlier.any():
        out = data[trend.outlier]
        fig.add_trace(
            go.Scatter(
                x=out[date_col],
                y=y[trend.outlier],
                mode="markers",
                marker=dict(symbol="x-thin", size=5.5, line=dict(width=1.5, color=TREND_COLOR)),
                name=f"Outlier, not in fit (n={len(out)})",
                hoverinfo="skip",
            )
        )

    for bp in trend.breakpoints:
        fig.add_vline(x=bp, line=dict(color=TREND_COLOR, width=1, dash="dash"), row="all", col=1)
        fig.add_annotation(
            x=bp, y=1, yref="paper", xanchor="left", yanchor="top", xshift=3,
            text=f"{bp:%Y-%m-%d}", showarrow=False, font=dict(size=11),
        )


def _add_ewma(fig: go.Figure, c: ControlCharts) -> None:
    fig.add_trace(
        go.Scatter(
            x=c.dates, y=c.ewma, mode="lines", line=dict(color=SPC_COLOR, width=2), name=f"EWMA (λ={c.lam:g})",
            hovertemplate="%{x|%Y-%m-%d}<br>EWMA: %{y:.4g}<extra></extra>",
        ),
        row=1, col=1,
    )
    for i, limit in enumerate((c.ewma_upper, c.ewma_lower)):
        fig.add_trace(
            go.Scatter(
                x=c.dates, y=limit, mode="lines", line=dict(color=SPC_COLOR, width=1, dash="dot"),
                name=f"EWMA limits (±{c.L:g}σ)", legendgroup="ewma_limits", showlegend=i == 0, hoverinfo="skip",
            ),
            row=1, col=1,
        )
    _add_signals(fig, c.dates, c.ewma, c.ewma_signal, "EWMA signal", 1)


def _add_cusum(fig: go.Figure, c: ControlCharts, row: int = 2) -> None:
    for name, ys in (("CUSUM C+", c.cusum_upper), ("CUSUM −C−", -c.cusum_lower)):
        fig.add_trace(
            go.Scatter(
                x=c.dates, y=ys, mode="lines", line=dict(color=SPC_COLOR, width=1.5), name=name,
                legendgroup="cusum", showlegend=name == "CUSUM C+",
                hovertemplate=f"%{{x|%Y-%m-%d}}<br>{name}: %{{y:.2f}} σ<extra></extra>",
            ),
            row=row, col=1,
        )
    for sign, watched in ((1, c.watch_high), (-1, c.watch_low)):
        if watched:
            fig.add_hline(y=sign * c.h, line=dict(color=INTEREST_COLOR, width=1, dash="dash"), row=row, col=1)
    signal_y = pd.Series(c.cusum_upper).where(c.cusum_high, -c.cusum_lower).to_numpy()
    _add_signals(fig, c.dates, signal_y, c.cusum_signal, "CUSUM signal", row)
    fig.update_yaxes(title_text=f"CUSUM (σ), h={c.h:g}", zeroline=True, row=row, col=1)


def _add_signals(fig: go.Figure, dates: pd.Series, ys, signal, name: str, row: int) -> None:
    if not signal.any():
        return
    fig.add_trace(
        go.Scatter(
            x=dates[signal], y=ys[signal], mode="markers", name=f"{name} (n={int(signal.sum())})",
            marker=dict(symbol="diamond", size=7, color=INTEREST_COLOR), hoverinfo="skip",
        ),
        row=row, col=1,
    )


# Contribution charts of a glassbox run. The two readings of every batch
# get their own colour, the same in both charts. Contributions are on the
# model's own scale (``scale``): log-odds, or a probability for a decision tree.
IN_SAMPLE_COLOR = "#9aa5b1"
LOO_COLOR = "#2a78d6"
_MAX_LABEL = 36


def _feature_label(f: str, current: str | None) -> str:
    """A feature's name, shortened; the plotted parameter in bold."""
    label = f if len(f) <= _MAX_LABEL else f[: _MAX_LABEL - 1] + "…"
    if f == current:
        return f"<b>{label}</b>"
    return label


def _contribution_layout(fig: go.Figure, features: list[str], current: str | None, clickable: set[str],
                         x_title: str) -> go.Figure:
    """Shared layout of the contribution charts, with clickable feature names.

    Axis tick labels cannot be clicked, so the names are drawn as the text of
    transparent bars on an axis of their own, left of the data. A click on a
    name selects that bar, whose ``customdata`` is the feature.
    """
    order = features[::-1]  # largest on top
    fig.add_bar(
        y=order, x=[1] * len(order), orientation="h", xaxis="x2", showlegend=False, width=0.9,
        marker=dict(color="rgba(0,0,0,0)"), customdata=order,
        text=[_feature_label(f, current) for f in order],
        textposition="inside", insidetextanchor="end", constraintext="none", cliponaxis=False,
        textfont=dict(color=["#2c3e50" if f in clickable else "#b4b3ad" for f in order], size=11),
        hovertemplate=[
            f"{f}<br>{'click to plot' if f in clickable else 'not a parameter in the dashboard data'}<extra></extra>"
            for f in order
        ],
    )
    fig.update_yaxes(type="category", categoryorder="array", categoryarray=order, showticklabels=False)
    fig.update_layout(
        xaxis=dict(domain=[0.4, 1], title_text=x_title, zeroline=True, zerolinecolor="#6b6a65", zerolinewidth=1),
        xaxis2=dict(domain=[0, 0.39], range=[0, 1], visible=False, fixedrange=True, anchor="y"),
        barmode="group", bargap=0.25, bargroupgap=0.05,
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0.4),
        margin=dict(l=10, r=10, t=30, b=10), hovermode="closest", font=dict(size=11),
        height=24 * len(features) + 110, clickmode="event+select", dragmode=False,
    )
    if current in order:  # a light band across the plotted parameter's row, name included
        i = order.index(current)
        fig.add_shape(type="rect", xref="paper", x0=0, x1=1, yref="y", y0=i - 0.5, y1=i + 0.5,
                      fillcolor=INTEREST_COLOR, opacity=0.12, line_width=0, layer="above")
    return fig


def drivers_figure(
    summary: pd.DataFrame, per_batch: pd.DataFrame, current: str | None, clickable: set[str],
    scale: str = "log-odds",
) -> go.Figure:
    """Mean in-sample and leave-one-out contribution per feature over the same batches of interest.

    ``summary`` comes from ``glassbox.driver_summary`` (its ``loo`` is empty
    when not every batch has a leave-one-out refit); ``per_batch`` holds the
    in-sample contribution of each of those batches (``batch_id``, ``feature``,
    ``in_sample``) and is drawn as dots, so it shows whether a feature drives
    all of them or one. Every mark carries its feature as ``customdata``.
    """
    features = summary["feature"].tolist()
    n = [int(v) for v in summary["n"]]
    fig = go.Figure()
    fig.add_bar(
        y=features, x=summary["in_sample"], orientation="h", name="In-sample (mean)",
        marker=dict(color=IN_SAMPLE_COLOR), customdata=features, text=n, textposition="none",
        hovertemplate="%{customdata}<br>mean in-sample %{x:+.3f} over %{text} batches<extra></extra>",
    )
    if summary["loo"].notna().any():
        fig.add_bar(
            y=features, x=summary["loo"], orientation="h", name="Leave-one-out (mean)",
            marker=dict(color=LOO_COLOR), customdata=features, text=n, textposition="none",
            hovertemplate="%{customdata}<br>mean leave-one-out %{x:+.3f} over the same %{text} batches<extra></extra>",
        )
    dots = per_batch[per_batch["feature"].isin(features)]
    if not dots.empty:
        fig.add_scatter(
            y=dots["feature"], x=dots["in_sample"], mode="markers", name="In-sample, per batch",
            marker=dict(color="#6b6a65", size=4, opacity=0.35), customdata=dots["feature"],
            text=dots["batch_id"], hovertemplate="%{text}<br>%{customdata}<br>in-sample %{x:+.3f}<extra></extra>",
        )
    return _contribution_layout(fig, features, current, clickable, f"Mean contribution ({scale})")


def batch_drivers_figure(
    rows: pd.DataFrame, current: str | None, clickable: set[str], scale: str = "log-odds"
) -> go.Figure:
    """One batch of interest: in-sample and leave-one-out contribution per feature, side by side.

    ``rows`` comes from ``glassbox.batch_drivers``. Imputed values are hatched,
    and an ✕ on the zero line marks a feature whose leave-one-out contribution
    does not point the same way as the in-sample one.
    """
    features = rows["feature"].tolist()

    def fmt(v, spec=".4g"):
        try:
            return format(float(v), spec)
        except (TypeError, ValueError):
            return "—" if v is None or pd.isna(v) else str(v)

    hover = [
        f"{r.feature}<br>value {fmt(r.value)} · typical in background {fmt(r.in_spec_typical)}"
        f"<br>percentile {fmt(r.percentile, '.0f')} · z {fmt(r.z, '+.2f')}"
        f"<br>in-sample {fmt(r.in_sample, '+.3f')} · leave-one-out {fmt(r.loo, '+.3f')}"
        + ("<br>value was imputed" if str(r.imputed).lower() == "true" else "")
        for r in rows.itertuples()
    ]
    imputed = ["/" if str(v).lower() == "true" else "" for v in rows["imputed"]]
    fig = go.Figure()
    fig.add_bar(
        y=features, x=rows["in_sample"], orientation="h", name="In-sample",
        marker=dict(color=IN_SAMPLE_COLOR, pattern=dict(shape=imputed)),
        customdata=features, hovertext=hover, hovertemplate="%{hovertext}<extra></extra>",
    )
    fig.add_bar(
        y=features, x=pd.to_numeric(rows["loo"], errors="coerce"), orientation="h", name="Leave-one-out",
        marker=dict(color=LOO_COLOR, pattern=dict(shape=imputed)),
        customdata=features, hovertext=hover, hovertemplate="%{hovertext}<extra></extra>",
    )
    disagree = rows[rows["agree"].astype(str).str.lower() == "false"]
    if not disagree.empty:
        fig.add_scatter(
            y=disagree["feature"], x=[0] * len(disagree), mode="markers", name="Leave-one-out disagrees",
            marker=dict(symbol="x-thin", size=9, line=dict(width=2, color=INTEREST_COLOR)),
            customdata=disagree["feature"], hovertemplate="%{customdata}: the refit without this batch "
            "does not reproduce this driver<extra></extra>",
        )
    return _contribution_layout(fig, features, current, clickable, f"Contribution ({scale})")


# --------------------------------------------------------------------------- statistics

STATS_HEIGHT = 240


def _stats_layout(fig: go.Figure, title: str, height: int = STATS_HEIGHT) -> go.Figure:
    fig.update_layout(
        title=dict(text=title, font=dict(size=13), x=0, xanchor="left"), height=height,
        margin=dict(l=10, r=10, t=36, b=10), showlegend=False, bargap=0.35,
    )
    return fig


def group_values_figure(first, second, first_name: str, second_name: str, label: str) -> go.Figure:
    """Box plots of the two groups' values, the group of interest on top."""
    fig = go.Figure()
    for values, name, color in ((second, second_name, POINT_COLOR), (first, first_name, INTEREST_COLOR)):
        fig.add_box(x=values, name=f"{name} ({len(values):,})", orientation="h", marker_color=color,
                    boxpoints="outliers", marker_size=3, line_width=1.5)
    fig.update_xaxes(title=dict(text=label, font=dict(size=12)))
    return _stats_layout(fig, "Values · box: the middle half, line: the median")


def rate_figure(table: pd.DataFrame, labels: pd.Series, overall: float | None, title: str,
                horizontal: bool = False) -> go.Figure:
    """Rates (``rate``, ``lo``, ``hi``, ``k``, ``n`` per row) as bars with their 95% intervals.

    ``overall``, when given, is drawn as a dashed line: the rate over all batches.
    """
    labels = [str(x) for x in labels]
    err = dict(type="data", array=table["hi"] - table["rate"], arrayminus=table["rate"] - table["lo"],
               color="#555", thickness=1.2, width=3)
    custom = list(zip(table["k"], table["n"], table["lo"], table["hi"]))
    hover = "%{customdata[0]:,} of %{customdata[1]:,} (" + ("%{x:.1%}" if horizontal else "%{y:.1%}") + \
        ")<br>95% CI %{customdata[2]:.1%} to %{customdata[3]:.1%}<extra>%{" + ("y" if horizontal else "x") + "}</extra>"
    fig = go.Figure()
    if horizontal:
        fig.add_bar(y=labels, x=table["rate"], orientation="h", error_x=err, marker_color=INTEREST_COLOR,
                    opacity=0.75, customdata=custom, hovertemplate=hover)
        fig.update_yaxes(autorange="reversed", type="category")
        fig.update_xaxes(tickformat=".0%", rangemode="tozero")
        if overall is not None:
            fig.add_vline(x=overall, line_dash="dash", line_width=1, line_color="#555",
                          annotation_text="all batches", annotation_font_size=10)
        height = max(STATS_HEIGHT, 70 + 26 * len(labels))
    else:
        fig.add_bar(x=labels, y=table["rate"], error_y=err, marker_color=INTEREST_COLOR, opacity=0.75,
                    customdata=custom, hovertemplate=hover)
        fig.update_xaxes(type="category")
        fig.update_yaxes(tickformat=".0%", rangemode="tozero")
        if overall is not None:
            fig.add_hline(y=overall, line_dash="dash", line_width=1, line_color="#555",
                          annotation_text="all batches", annotation_font_size=10, annotation_position="top left")
        height = STATS_HEIGHT
    return _stats_layout(fig, title, height)


def p_chart_figure(table: pd.DataFrame, rate_label: str) -> go.Figure:
    """The monthly rate with the overall rate and its 3-sigma limits; months above the upper limit ringed."""
    fig = go.Figure()
    fig.add_scatter(x=table["month"], y=table["ucl"], mode="lines", line=dict(shape="hvh", dash="dot", width=1,
                    color=POINT_COLOR), name="upper limit", hovertemplate="upper limit %{y:.1%}<extra></extra>")
    fig.add_scatter(x=table["month"], y=table["lcl"], mode="lines", line=dict(shape="hvh", dash="dot", width=1,
                    color=POINT_COLOR), name="lower limit", hoverinfo="skip")
    if len(table):
        fig.add_hline(y=float(table["centre"].iloc[0]), line_width=1, line_color=POINT_COLOR,
                      annotation_text="overall", annotation_font_size=10, annotation_position="top left")
    fig.add_scatter(
        x=table["month"], y=table["rate"], mode="lines+markers", line=dict(width=1.5, color=SPC_COLOR),
        marker=dict(size=POINT_SIZE, color=SPC_COLOR), name=rate_label,
        customdata=list(zip(table["k"], table["n"])),
        hovertemplate="%{x|%b %Y}: %{customdata[0]} of %{customdata[1]} (%{y:.1%})<extra></extra>",
    )
    flagged = table[table["flagged"]]
    fig.add_scatter(
        x=flagged["month"], y=flagged["rate"], mode="markers", name="above the upper limit",
        marker=dict(size=RING_SIZE + 6, color="rgba(0,0,0,0)", line=dict(width=RING_WIDTH + 0.5, color=INTEREST_COLOR)),
        hoverinfo="skip",
    )
    fig.update_yaxes(tickformat=".0%", rangemode="tozero")
    return _stats_layout(fig, f"{rate_label[:1].upper() + rate_label[1:]} per month · dotted: 3-sigma limits · "
                         "ringed: above the upper limit", 260)
