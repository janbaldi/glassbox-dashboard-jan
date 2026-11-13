"""Figures of the monitoring pages. They return Plotly figures and do not depend on Streamlit."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from .plots import CATEGORY_COLORS, INTEREST_COLOR, POINT_COLOR, REFERENCE_FILL, SPC_COLOR, TREND_COLOR

HEIGHT = 260
LOW_COLOR, HIGH_COLOR = "#2a78d6", "#d1495b"  # below / above the baseline (diverging scale ends)
MUTED = "#6b6a66"


def _layout(fig: go.Figure, title: str = "", height: int = HEIGHT, legend: bool = False) -> go.Figure:
    fig.update_layout(
        title=dict(text=title, font=dict(size=13), x=0, xanchor="left") if title else None,
        height=height, margin=dict(l=10, r=10, t=36 if title else 10, b=10), font=dict(size=11),
        showlegend=legend, legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="right", x=1, font=dict(size=10)),
        hovermode="closest",
    )
    return fig


def palette(names: list[str]) -> dict[str, str]:
    """A colour per name, in order: sites keep their colour on every chart."""
    return {n: CATEGORY_COLORS[i % len(CATEGORY_COLORS)] for i, n in enumerate(names)}


def _month(dates: pd.Series) -> pd.Series:
    return pd.to_datetime(dates).dt.to_period("M").dt.to_timestamp()


def volume_figure(dates: pd.Series, groups: pd.Series | None, title: str = "Batches started per month") -> go.Figure:
    """Batches per month, stacked by ``groups`` (the sites) when given."""
    month = _month(dates)
    fig = go.Figure()
    if groups is None:
        counts = month.value_counts().sort_index()
        fig.add_bar(x=counts.index, y=counts.values, marker_color=POINT_COLOR, hovertemplate="%{x|%b %Y}: %{y}<extra></extra>")
    else:
        table = pd.crosstab(month, groups.astype("string").fillna("(no site)"))
        colors = palette(list(table.columns))
        for name in table.columns:
            fig.add_bar(x=table.index, y=table[name], name=name, marker_color=colors[name],
                        hovertemplate="%{x|%b %Y}: %{y}<extra>" + str(name) + "</extra>")
    fig.update_layout(barmode="stack", bargap=0.25)
    return _layout(fig, title, legend=groups is not None)


def oos_type_figure(table: pd.DataFrame, labels: list[str], recent_name: str, baseline_name: str) -> go.Figure:
    """Per OOS type: the recent rate as a bar with its 95% interval, the baseline rate as a tick."""
    fig = go.Figure()
    fig.add_bar(
        y=labels, x=table["recent"], orientation="h", marker_color=INTEREST_COLOR, opacity=0.75, name=recent_name,
        error_x=dict(type="data", array=table["recent_hi"] - table["recent"], arrayminus=table["recent"] - table["recent_lo"],
                     color="#555", thickness=1.2, width=3),
        customdata=list(zip(table["recent_k"], table["recent_n"])),
        hovertemplate="%{customdata[0]} of %{customdata[1]} (%{x:.1%})<extra>" + recent_name + "</extra>",
    )
    fig.add_scatter(
        y=labels, x=table["baseline"], mode="markers", name=baseline_name,
        marker=dict(symbol="line-ns", size=16, line=dict(width=2.5, color=SPC_COLOR)),
        customdata=list(zip(table["baseline_k"], table["baseline_n"])),
        hovertemplate="%{customdata[0]} of %{customdata[1]} (%{x:.1%})<extra>" + baseline_name + "</extra>",
    )
    fig.update_yaxes(autorange="reversed", type="category")
    fig.update_xaxes(tickformat=".0%", rangemode="tozero")
    return _layout(fig, "OOS rate by type · bar: recent with 95% interval · tick: baseline",
                   max(HEIGHT, 70 + 24 * len(labels)), legend=True)


def stage_figure(stages: list[str], table: pd.DataFrame, title: str) -> go.Figure:
    """Batches in process per stage (rows of ``table``: stage, group, n), in process order."""
    fig = go.Figure()
    groups = list(dict.fromkeys(table["group"]))
    colors = palette(sorted(groups))
    for group in sorted(groups):
        part = table[table["group"] == group].set_index("stage")["n"].reindex(stages).fillna(0)
        fig.add_bar(y=stages, x=part.values, orientation="h", name=str(group), marker_color=colors[group],
                    hovertemplate="%{y}: %{x:.0f}<extra>" + str(group) + "</extra>")
    fig.update_layout(barmode="stack", bargap=0.3)
    fig.update_yaxes(autorange="reversed", type="category")
    fig.update_xaxes(title_text="Batches", dtick=None)
    return _layout(fig, title, max(HEIGHT, 60 + 26 * len(stages)), legend=len(groups) > 1)


def mini_trend_figure(dates: pd.Series, y: pd.Series, recent_start: pd.Timestamp, baseline: pd.Series, title: str) -> go.Figure:
    """A compact trend: the batches, the monthly median, the baseline's median and middle half, the recent window shaded."""
    ok = y.notna() & dates.notna()
    d, v = pd.to_datetime(dates[ok]), y[ok]
    fig = go.Figure()
    base = y[baseline & ok]
    if len(base):
        q1, med, q3 = base.quantile([0.25, 0.5, 0.75])
        fig.add_hrect(y0=q1, y1=q3, fillcolor="rgba(120,120,120,0.10)", line_width=0, layer="below")
        fig.add_hline(y=med, line_width=1, line_dash="dash", line_color=MUTED)
    fig.add_scatter(x=d, y=v, mode="markers", marker=dict(size=4, color=POINT_COLOR, opacity=0.6),
                    hovertemplate="%{x|%Y-%m-%d}: %{y}<extra></extra>")
    monthly = v.groupby(_month(d)).median()
    fig.add_scatter(x=monthly.index + pd.Timedelta(days=14), y=monthly.values, mode="lines", line=dict(width=2, color=TREND_COLOR),
                    hovertemplate="%{x|%b %Y} median: %{y:.4g}<extra></extra>")
    if len(d) and recent_start <= d.max():
        fig.add_vrect(x0=recent_start, x1=d.max(), fillcolor=REFERENCE_FILL, line_width=0, layer="below")
    return _layout(fig, title, 210)


def z_heatmap(z: pd.DataFrame, labels: list[str], limit: float = 3.0) -> go.Figure:
    """Parameters (rows) by month: the monthly mean's distance from the baseline mean, in standard errors.

    White within the control limits' reach, blue below, red above; the scale
    saturates at twice the limit. Empty cells: fewer than 3 values that month.
    """
    span = 2 * limit
    text = np.where(z.abs().to_numpy() > limit, "●", "")
    fig = go.Figure(go.Heatmap(
        z=z.clip(-span, span).to_numpy(), x=list(z.columns), y=labels, zmin=-span, zmax=span, zmid=0,
        colorscale=[[0, LOW_COLOR], [0.5 - limit / span / 2 * 0.5, "#dfeaf7"], [0.5, "#ffffff"],
                    [0.5 + limit / span / 2 * 0.5, "#f8e1e4"], [1, HIGH_COLOR]],
        customdata=z.round(1).to_numpy(), text=text, texttemplate="%{text}", textfont=dict(size=8, color="#222"),
        hovertemplate="%{y}<br>%{x|%b %Y}: %{customdata} SE from the baseline mean<extra></extra>",
        colorbar=dict(title=dict(text="SE", font=dict(size=10)), thickness=10, len=0.6, tickvals=[-span, -limit, 0, limit, span]),
        xgap=1, ygap=1,
    ))
    fig.update_yaxes(autorange="reversed", type="category", tickfont=dict(size=10))
    fig.update_xaxes(tickformat="%b %y", dtick="M1" if z.shape[1] <= 18 else "M3")
    return _layout(fig, "Monthly mean against the baseline · ● beyond the 3-sigma control limits",
                   max(HEIGHT, 80 + 20 * len(labels)))


def site_box_figure(values: pd.Series, sites: pd.Series, label: str) -> go.Figure:
    fig = go.Figure()
    names = sorted(sites.dropna().astype(str).unique())
    colors = palette(names)
    for name in names:
        x = values[sites.astype("string") == name].dropna()
        fig.add_box(x=x, name=f"{name} ({len(x):,})", orientation="h", marker_color=colors[name], boxpoints="outliers",
                    marker_size=3, line_width=1.5)
    fig.update_yaxes(autorange="reversed")
    fig.update_xaxes(title=dict(text=label, font=dict(size=12)))
    return _layout(fig, "Values per site · box: the middle half, line: the median", max(HEIGHT, 90 + 45 * len(names)))


def site_monthly_figure(dates: pd.Series, values: pd.Series, sites: pd.Series, label: str, least: int = 3) -> go.Figure:
    """The monthly median per site (months with fewer than ``least`` values left out)."""
    fig = go.Figure()
    names = sorted(sites.dropna().astype(str).unique())
    colors = palette(names)
    month = _month(dates)
    for name in names:
        at = (sites.astype("string") == name) & values.notna() & dates.notna()
        g = values[at].groupby(month[at])
        med = g.median()[g.count() >= least]
        fig.add_scatter(x=med.index, y=med.values, mode="lines+markers", name=name, line=dict(width=1.8, color=colors[name]),
                        marker=dict(size=5), hovertemplate="%{x|%b %Y}: %{y:.4g}<extra>" + name + "</extra>")
    fig.update_yaxes(title=dict(text=label, font=dict(size=12)))
    return _layout(fig, "Monthly median per site", 300, legend=True)


def family_figure(profile: pd.DataFrame, label: str) -> go.Figure:
    """A parameter across process days: the baseline's median and middle half, and the recent median."""
    x = [f"Day {d}" for d in profile["day"]]
    fig = go.Figure()
    fig.add_scatter(x=x, y=profile["q3"], mode="lines", line=dict(width=0), hoverinfo="skip", showlegend=False)
    fig.add_scatter(x=x, y=profile["q1"], mode="lines", line=dict(width=0), fill="tonexty", fillcolor="rgba(120,120,120,0.15)",
                    name="baseline, middle half", hoverinfo="skip")
    fig.add_scatter(x=x, y=profile["baseline"], mode="lines+markers", line=dict(width=1.5, color=MUTED, dash="dash"),
                    name="baseline median", hovertemplate="%{x}: %{y:.4g}<extra>baseline</extra>")
    fig.add_scatter(x=x, y=profile["recent"], mode="lines+markers", line=dict(width=2.2, color=INTEREST_COLOR),
                    name="recent median", hovertemplate="%{x}: %{y:.4g}<extra>recent</extra>")
    fig.update_xaxes(type="category")
    fig.update_yaxes(title=dict(text=label, font=dict(size=12)))
    return _layout(fig, "", 300, legend=True)


def batch_profile_figure(rows: pd.DataFrame, most: float = 8.0) -> go.Figure:
    """A batch's most unusual values: distance from the completed batches' median in robust SD (clipped at ±``most``)."""
    z = rows["z"].clip(-most, most)
    limit = min(most, max(4.0, float(np.ceil(z.abs().max()))))
    fig = go.Figure()
    fig.add_vrect(x0=-3, x1=3, fillcolor="rgba(120,120,120,0.10)", line_width=0, layer="below")
    fig.add_vline(x=0, line_width=1, line_color=MUTED)
    fig.add_scatter(
        x=z, y=rows["parameter"], mode="markers",
        marker=dict(size=9, color=np.where(z >= 0, HIGH_COLOR, LOW_COLOR)),
        customdata=list(zip(rows["value"], rows["median"], rows["percentile"])),
        hovertemplate="%{y}<br>value %{customdata[0]:.4g} · typical %{customdata[1]:.4g}<br>"
                      "percentile %{customdata[2]:.1f} of completed batches<extra></extra>",
    )
    fig.update_yaxes(autorange="reversed", type="category", tickfont=dict(size=10))
    fig.update_xaxes(title=dict(text="Distance from the typical value (robust SD) · grey: within ±3", font=dict(size=11)),
                     range=[-limit - 0.5, limit + 0.5])
    return _layout(fig, "", max(220, 70 + 22 * len(rows)))


def lead_time_figure(dates: pd.Series, leads: pd.DataFrame, least: int = 3) -> go.Figure:
    """The monthly median of each lead time, in days."""
    fig = go.Figure()
    month = _month(dates)
    colors = palette(list(leads.columns))
    for column in leads.columns:
        ok = leads[column].notna() & dates.notna()
        g = leads.loc[ok, column].groupby(month[ok])
        med = g.median()[g.count() >= least]
        fig.add_scatter(x=med.index, y=med.values, mode="lines+markers", name=column, line=dict(width=1.8, color=colors[column]),
                        marker=dict(size=5), hovertemplate="%{x|%b %Y}: %{y:.1f} days<extra>" + column + "</extra>")
    fig.update_yaxes(title=dict(text="Days (monthly median)", font=dict(size=12)), rangemode="tozero")
    return _layout(fig, "", 320, legend=True)


def category_share_figure(dates: pd.Series, text: pd.Series, most: int = 8) -> go.Figure:
    """Each category's share of the batches per month (the ``most`` largest categories, the rest as Other)."""
    ok = text.notna() & dates.notna()
    top = text[ok].value_counts().index[:most]
    folded = text[ok].where(text[ok].isin(top), "Other")
    table = pd.crosstab(_month(dates[ok]), folded, normalize="index")
    order = [c for c in top if c in table.columns] + (["Other"] if "Other" in table.columns else [])
    colors = palette(order)
    fig = go.Figure()
    for name in order:
        fig.add_bar(x=table.index, y=table[name], name=str(name), marker_color=POINT_COLOR if name == "Other" else colors[name],
                    hovertemplate="%{x|%b %Y}: %{y:.0%}<extra>" + str(name) + "</extra>")
    fig.update_layout(barmode="stack", bargap=0.2)
    fig.update_yaxes(tickformat=".0%", range=[0, 1])
    return _layout(fig, "Share of the batches per month", 300, legend=True)
