"""The CPV report: the state of control of a parameter set over a period, as a PDF for the file.

Built on the statistics record's PDF layer and provenance (``report``). No
Streamlit: the CPV page gathers a ``CpvReport`` and hands it here.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import monitor as M
from .report import _PDF, _STYLE, _figure, _figure_png, _fmt
from .spc import control_charts

HEAT_ROWS = 40  # parameters in the heat map and the table; the most out of control first
CHARTS = 12  # control charts drawn
CAVEATS = [
    "Control limits describe the baseline's own variation. They are not specification limits: a parameter can be in "
    "control and out of specification, or the reverse.",
    "A baseline that contains a shift gives a centre between the two levels and limits that are too wide. Use a "
    "baseline period the process is trusted in.",
    "With many parameters and months, a few months beyond the limits are expected by chance (about 3 in 1,000). "
    "A run of months on one side is a shift.",
    "Recent batches that are still in process have no final product results yet; their months hold fewer batches.",
]
METHODS = [
    "Heat map and 'months out': the x-bar chart of each parameter. Centre: the baseline mean. Sigma: the baseline's "
    "mean moving range / 1.128, in date order. A month is out when its mean is beyond ±3 sigma / sqrt(batches in the "
    "month). Months with fewer than 3 values are not charted.",
    "Shift: recent median minus baseline median, in baseline robust SD (1.4826 × MAD). q: Mann-Whitney, recent against "
    "baseline, Benjamini-Hochberg over all numerical parameters.",
    f"Status: Shifted when q < {M.ALPHA} and the shift is at least {M.SHIFT_SD} SD; Watch for a smaller significant "
    "difference, the EWMA outside its limits at the latest batch, or more recent batches beyond ±3 SD than chance gives.",
    "Control charts: individual batches with the baseline centre and ±3 sigma limits, and the EWMA with its limits "
    "(settings under 'spc' in the configuration).",
]


@dataclass
class CpvReport:
    title: str
    scope: list[tuple[str, str]]  # period, recent window, baseline, filters, parameter set
    z: pd.DataFrame  # monitor.monthly_z of the set, the most out of control first
    table: pd.DataFrame  # one row per parameter, the same order: the CPV page's table
    values: pd.DataFrame  # the set's values over the period
    dates: pd.Series  # aligned with values
    baseline: pd.Series  # bool, aligned with values
    recent_start: pd.Timestamp
    units: dict[str, str] = field(default_factory=dict)
    spc: dict = field(default_factory=dict)
    oos: list[str] = field(default_factory=list)  # sentences about the OOS rate
    provenance: list[tuple[str, str]] = field(default_factory=list)


def _heat_map(z: pd.DataFrame) -> io.BytesIO:
    import matplotlib
    from matplotlib.colors import LinearSegmentedColormap

    from .monitor_plots import HIGH_COLOR, LOW_COLOR

    cmap = LinearSegmentedColormap.from_list("cpv", [LOW_COLOR, "#ffffff", HIGH_COLOR])
    cmap = cmap.with_extremes(bad="#eeeeee")
    with matplotlib.rc_context(_STYLE):
        fig = _figure(7.4, 0.9 + 0.17 * len(z))
        ax = fig.subplots()
        image = ax.imshow(np.ma.masked_invalid(z.to_numpy(float)), cmap=cmap, vmin=-6, vmax=6, aspect="auto")
        out_y, out_x = np.where(z.abs().to_numpy(float) > 3)
        ax.scatter(out_x, out_y, s=5, color="#222222")
        ax.set_yticks(range(len(z)), [n if len(n) <= 48 else n[:47] + "…" for n in z.index], fontsize=6)
        step = max(1, z.shape[1] // 12)
        ax.set_xticks(range(0, z.shape[1], step), [f"{m:%b %y}" for m in z.columns[::step]], fontsize=6)
        ax.set_title("Monthly mean against the baseline, in standard errors (dot: beyond the 3-sigma limits; grey: "
                     "fewer than 3 values)", fontsize=8, loc="left")
        bar = fig.colorbar(image, ax=ax, fraction=0.025, pad=0.02, ticks=[-6, -3, 0, 3, 6])
        bar.ax.tick_params(labelsize=6)
        return _figure_png(fig)


def _control_charts(r: CpvReport, names: list[str]) -> io.BytesIO | None:
    import matplotlib

    from .plots import POINT_COLOR, SPC_COLOR, TREND_COLOR

    drawn = []
    for name in names:
        c = control_charts(r.dates, r.values[name], reference=r.baseline, **r.spc)
        if c is not None:
            drawn.append((name, c))
    if not drawn:
        return None
    with matplotlib.rc_context(_STYLE):
        fig = _figure(7.4, 1.75 * len(drawn))
        axes = np.atleast_1d(fig.subplots(len(drawn), 1))
        for ax, (name, c) in zip(axes, drawn):
            y = r.values.loc[c.index, name].to_numpy(float)
            out = np.abs(y - c.target) > 3 * c.sigma
            ax.axvspan(r.recent_start, c.dates.max(), color="#2a78d6", alpha=0.07, lw=0)
            ax.scatter(c.dates[~out], y[~out], s=4, color=POINT_COLOR, lw=0)
            ax.scatter(c.dates[out], y[out], s=9, color=TREND_COLOR, lw=0, zorder=3)
            ax.axhline(c.target, color="#6b6a66", lw=0.8)
            for limit in (c.target - 3 * c.sigma, c.target + 3 * c.sigma):
                ax.axhline(limit, color="#6b6a66", lw=0.8, ls="--")
            ax.plot(c.dates, c.ewma, color=SPC_COLOR, lw=1.1)
            ax.plot(c.dates, c.ewma_upper, color=SPC_COLOR, lw=0.6, ls=":")
            ax.plot(c.dates, c.ewma_lower, color=SPC_COLOR, lw=0.6, ls=":")
            signal = c.ewma_signal
            ax.scatter(c.dates[signal], c.ewma[signal], s=7, marker="D", color="#0047ab", zorder=4, lw=0)
            ax.set_title(f"{name}{r.units.get(name, '')} · centre {_fmt(c.target, 4)}, sigma {_fmt(c.sigma, 3)} "
                         f"({c.baseline} baseline batches)", fontsize=7.5, loc="left")
            ax.tick_params(labelsize=6)
        return _figure_png(fig)


def build_pdf(r: CpvReport) -> bytes:
    doc = _PDF(r.title)
    doc.heading(r.title, 15)
    doc.text(f"Created {dict(r.provenance).get('Created', '')}.", grey=True)
    doc.table(["Scope", ""], [[k, v] for k, v in r.scope], (40, 140), size=7.5)

    t = r.table
    out_recent = t[t["Months out, recent"] > 0]
    doc.heading("Summary")
    lines = [
        f"{len(t)} parameters charted; {len(t) - len(out_recent)} in control in the recent window (no recent month "
        f"beyond the 3-sigma limits), {len(out_recent)} with at least one recent month out of control.",
    ]
    for status in (M.STATUS_SHIFTED, M.STATUS_WATCH):
        names = t.loc[t["status"] == status, "Parameter"].tolist()
        if names:
            lines.append(f"{status} ({len(names)}): " + ", ".join(names[:12]) + (" and others." if len(names) > 12 else "."))
    doc.bullets(lines + r.oos)

    shown = r.z.head(HEAT_ROWS)
    if len(shown):
        doc.heading("State of control per month")
        doc.image(_heat_map(shown))
        if len(r.z) > len(shown):
            doc.text(f"The {len(shown)} parameters with the most months out of control, of {len(r.z)}.", 8, grey=True)

    doc.heading("Parameters")
    rows = [[x["Parameter"], x["Process day"], str(x["Months out, recent"]), str(x["Months out, period"]),
             _fmt(x["Beyond ±3 SD"]), _fmt(x["EWMA signals"]), f"{x['Shift (SD)']:+.2f}" if pd.notna(x["Shift (SD)"]) else "",
             x["status"]] for x in t.head(HEAT_ROWS).to_dict("records")]
    doc.table(["Parameter", "Process day", "Months out, recent", "Months out, period", "Beyond ±3 SD", "EWMA signals",
               "Shift (SD)", "Status"], rows, (62, 22, 18, 18, 16, 16, 14, 14), size=6.5)

    wanted = [n for n in t.loc[(t["Months out, recent"] > 0) | t["status"].isin([M.STATUS_SHIFTED, M.STATUS_WATCH]), "Parameter"]
              if n in r.values][:CHARTS]
    if not wanted:
        wanted = [n for n in t["Parameter"] if n in r.values][:4]
        note = "No parameter is out of control or shifted; the first of the set are shown."
    else:
        note = "The parameters out of control in the recent window, shifted or on watch" + (
            f" (the first {CHARTS})." if len(wanted) == CHARTS else ".")
    doc.pdf.add_page()
    doc.heading("Control charts")
    doc.text(note + " Grey: batches; orange: beyond ±3 sigma; dashed: the 3-sigma limits; dark line: EWMA with its "
             "limits (dotted), diamonds where it signals; blue shade: the recent window.", 8, grey=True)
    for start in range(0, len(wanted), 4):  # four charts to an image, so a page break never cuts one
        doc.image(_control_charts(r, wanted[start:start + 4]))

    doc.heading("Methods")
    doc.bullets(METHODS)
    doc.heading("Read with care")
    doc.bullets(CAVEATS)
    doc.heading("Provenance")
    doc.table(["Item", "Value"], [[k, v] for k, v in r.provenance], (40, 140), size=7)
    return doc.output()
