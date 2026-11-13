"""The statistics export: a CSV of every number and a PDF record for the file.

Both carry the same provenance (what was compared, from which files, with which
software) so a result can be traced and reproduced. No Streamlit: the view
(``views.statistics``) gathers a ``Record`` and hands it here.
"""

from __future__ import annotations

import hashlib
import io
import math
import platform
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from importlib import metadata
from pathlib import Path

import numpy as np
import pandas as pd

from . import stats as S
from .evidence import Evidence, Groups, OverTime, _row

ROOT = Path(__file__).resolve().parent.parent
FONTS = ROOT / "static"
SCREEN_ROWS = 25  # screen rows in the PDF; the CSV has them all
LIBRARIES = ("streamlit", "pandas", "numpy", "scipy", "plotly", "matplotlib", "fpdf2")

CAVEATS = [
    "These are associations, not proof of cause: a parameter that differs between the groups may only "
    "travel with the real cause.",
    "Comparing batches made in the same calendar quarter removes slow changes over time, not other "
    "differences such as site, material lots or operators.",
    "Batches are treated as independent. Batches that share a donor, a material lot or a run are not.",
    "A parameter chosen because it looked different (or because the model pointed at it) tends to look "
    "more convincing than it is. The screen's q-values correct for testing every parameter; the p-values "
    "for a single parameter do not.",
    "The model's own performance (out-of-fold) is somewhat optimistic: its features and settings were "
    "chosen with every batch in view.",
]


# --------------------------------------------------------------------------- provenance


def sha256(path: Path) -> str:
    """SHA-256 of a file, or "not found"."""
    return _sha256(str(path), path.stat().st_mtime if path.exists() else 0.0) if path.exists() else "not found"


@lru_cache(maxsize=16)
def _sha256(path: str, mtime: float) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def git_version() -> str:
    """The dashboard's git commit, with "(uncommitted changes)" when the working tree differs."""
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                                timeout=5, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT,
                               capture_output=True, text=True, timeout=5, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown (not a git checkout)"
    return commit + (" (uncommitted changes)" if dirty else "")


def library_versions() -> str:
    versions = [f"Python {platform.python_version()}"]
    for name in LIBRARIES:
        try:
            versions.append(f"{name} {metadata.version(name)}")
        except metadata.PackageNotFoundError:
            pass
    return ", ".join(versions)


def provenance(cfg, run=None, model=None, selection: dict[str, str] | None = None) -> list[tuple[str, str]]:
    """What the numbers were computed from, as (label, value) pairs."""
    items = [
        ("Created", datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z").strip()),
        ("Dashboard version", git_version()),
        ("Data file", f"{cfg.csv_path.name} (SHA-256 {sha256(cfg.csv_path)})"),
        ("Parameter list", f"{cfg.parameters_path.name} (SHA-256 {sha256(cfg.parameters_path)})"),
        ("Configuration", f"{cfg.source_path.name} (SHA-256 {sha256(cfg.source_path)})"),
    ]
    if run is not None:
        items.append(("Glassbox run", f"{run.title or run.name} (folder {run.name}; run_manifest.json SHA-256 "
                                      f"{run.manifest_sha256 or 'unknown'})"))
        for key, value in (run.provenance or {}).items():
            items.append((f"Glassbox {key.replace('_', ' ')}", str(value)))
        if model is not None:
            items.append(("Model", model.name))
    for key, value in (selection or {}).items():
        items.append((key, value))
    items += [
        ("Settings", f"at least {S.MIN_BATCHES} batches per group for a test; Monte Carlo {S.MC_TABLES:,} tables, "
                     f"seed {S.SEED}; all tests two-sided, all intervals 95%"),
        ("Software", library_versions()),
    ]
    return items


# --------------------------------------------------------------------------- the record


@dataclass
class Record:
    groups: Groups
    provenance: list[tuple[str, str]]
    parameter: str | None = None
    evidence: Evidence | None = None
    over_time: OverTime | None = None
    model_lines: list[str] = field(default_factory=list)
    model_rows: list[dict] = field(default_factory=list)
    screen: pd.DataFrame | None = None


def screen_rows(screen: pd.DataFrame) -> list[dict]:
    rows = []
    for r in screen.itertuples():
        method = "within_numbers" if r.kind == "number" else "within_categories"
        note = "; ".join(x for x in (
            r.effect, r.within and f"within quarters {r.within}", r.in_model and f"model feature {r.in_model}",
            isinstance(r.moves_with, str) and r.moves_with and f"moves with {r.moves_with} (rho {r.rho:+.2f})",
        ) if x)
        row = _row("screen", r.parameter, "AUC" if r.kind == "number" else "highest category rate",
                   r.estimate, r.ci_low, r.ci_high, r.p, r.n_first, r.n_second, method, note)
        row["method"] += "; " + S.METHODS["fdr"]
        row["q"] = r.q
        rows.append(row)
    return rows


def table(record: Record) -> pd.DataFrame:
    """Every number in the record, one row each."""
    rows = [_row("provenance", "", label, note=value) for label, value in record.provenance]
    if record.evidence is not None:
        rows += record.evidence.rows
    if record.over_time is not None:
        rows += record.over_time.rows
    rows += record.model_rows
    if record.screen is not None:
        rows += screen_rows(record.screen)
    cols = ["section", "parameter", "statistic", "estimate", "ci_low", "ci_high", "p", "q",
            "n_first", "n_second", "method", "note"]
    out = pd.DataFrame(rows).reindex(columns=cols)
    for c in ("estimate", "ci_low", "ci_high", "p", "q"):
        out[c] = pd.to_numeric(out[c], errors="coerce").astype(float)
    out["n_first"] = out["n_first"].astype("Int64")
    out["n_second"] = out["n_second"].astype("Int64")
    return out


def build_csv(record: Record) -> bytes:
    """The record as CSV (UTF-8 with a byte-order mark, so spreadsheet programs read the symbols)."""
    t = table(record).rename(columns={
        "n_first": f"n ({record.groups.first})", "n_second": f"n ({record.groups.second})",
    })
    return t.to_csv(index=False, float_format="%.6g").encode("utf-8-sig")


# --------------------------------------------------------------------------- PDF


def _fmt(x, digits: int = 3) -> str:
    if x is None or (isinstance(x, float) and not math.isfinite(x)) or pd.isna(x):
        return ""
    if isinstance(x, (int, np.integer)):
        return f"{x:,}"
    return f"{x:.{digits}g}"


def _ci(lo, hi) -> str:
    return f"{_fmt(lo)} to {_fmt(hi)}" if _fmt(lo) and _fmt(hi) else ""


def _p(p) -> str:
    if p is None or pd.isna(p):
        return ""
    return "< 0.001" if p < 0.001 else f"{p:.3f}"


_STYLE = {"font.size": 8, "axes.spines.top": False, "axes.spines.right": False}


def _figure(width: float, height: float):
    """A matplotlib figure without pyplot: the PDF is built on a download thread, and pyplot is not thread-safe."""
    from matplotlib.figure import Figure

    return Figure(figsize=(width, height))


def _figure_png(fig) -> io.BytesIO:
    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png", dpi=160, bbox_inches="tight")
    buf.seek(0)
    return buf


def _evidence_chart(ev: Evidence) -> io.BytesIO | None:
    import matplotlib

    g = ev.groups
    if not ev.tested:
        return None
    with matplotlib.rc_context(_STYLE):
        return _evidence_png(ev, g)


def _evidence_png(ev: Evidence, g: Groups) -> io.BytesIO | None:
    from .plots import INTEREST_COLOR, POINT_COLOR

    if ev.kind == "number" and ev.first_values is not None and len(ev.first_values) and len(ev.second_values):
        fig = _figure(7.2, 2.2)
        axes = fig.subplots(1, 2 if ev.by_value is not None else 1, squeeze=False)
        ax = axes[0][0]
        box = ax.boxplot([ev.second_values, ev.first_values], vert=False, widths=0.5, patch_artist=True,
                         tick_labels=[g.second, g.first], showfliers=False)
        for patch, color in zip(box["boxes"], (POINT_COLOR, INTEREST_COLOR)):
            patch.set(facecolor=color, alpha=0.35, edgecolor=color)
        for median in box["medians"]:
            median.set(color="black")
        ax.set_xlabel(ev.parameter + ev.unit, fontsize=7)
        ax.set_title("Values (box: middle half, line: median)", fontsize=8)
        if ev.by_value is not None:
            _rate_bars(axes[0][1], ev.by_value["group"], ev.by_value, g, f"{g.rate} by value (quartiles)")
    elif ev.kind == "category" and ev.categories is not None and len(ev.categories):
        fig = _figure(7.2, 0.6 + 0.28 * min(len(ev.categories), 20))
        ax = fig.subplots()
        cats = ev.categories.head(20)
        _rate_bars(ax, cats["category"].astype(str), cats, g, f"{g.rate} per category", horizontal=True,
                   overall=ev.overall.p if ev.overall else None)
    else:
        return None
    return _figure_png(fig)


def _rate_bars(ax, labels, t: pd.DataFrame, g: Groups, title: str, horizontal: bool = False, overall=None) -> None:
    from .plots import INTEREST_COLOR

    rate, lo, hi = t["rate"].to_numpy(float), t["lo"].to_numpy(float), t["hi"].to_numpy(float)
    err = [rate - lo, hi - rate]
    pos = np.arange(len(rate))
    if horizontal:
        ax.barh(pos, rate, xerr=err, color=INTEREST_COLOR, alpha=0.6, capsize=2)
        ax.set_yticks(pos, [str(x)[:40] for x in labels])
        ax.invert_yaxis()
        ax.xaxis.set_major_formatter(_percent())
        if overall is not None:
            ax.axvline(overall, color="black", lw=0.8, ls="--")
    else:
        ax.bar(pos, rate, yerr=err, color=INTEREST_COLOR, alpha=0.6, capsize=2)
        ax.set_xticks(pos, [str(x) for x in labels], fontsize=6)
        ax.yaxis.set_major_formatter(_percent())
    ax.set_title(title + " with 95% intervals", fontsize=8)


def _percent():
    from matplotlib.ticker import PercentFormatter

    return PercentFormatter(1.0, decimals=None)


def _over_time_chart(ot: OverTime) -> io.BytesIO | None:
    import matplotlib

    t = ot.table
    if t.empty:
        return None
    with matplotlib.rc_context(_STYLE):
        fig = _figure(7.2, 2.2)
        ax = fig.subplots()
        _p_chart(ax, t)
        fig.autofmt_xdate()
        return _figure_png(fig)


def _p_chart(ax, t: pd.DataFrame) -> None:
    from .plots import INTEREST_COLOR

    ax.plot(t["month"], t["rate"], marker="o", ms=3, lw=1, color="#2c3e50")
    ax.step(t["month"], t["ucl"], where="mid", color="#9c9b95", lw=0.8, ls="--")
    ax.step(t["month"], t["lcl"], where="mid", color="#9c9b95", lw=0.8, ls="--")
    ax.axhline(t["centre"].iloc[0], color="#9c9b95", lw=0.8)
    flagged = t[t["flagged"]]
    ax.scatter(flagged["month"], flagged["rate"], s=30, facecolors="none", edgecolors=INTEREST_COLOR, lw=1.5, zorder=3)
    ax.yaxis.set_major_formatter(_percent())
    ax.set_title("Monthly rate, overall rate and 3-sigma limits (circled: above the upper limit)", fontsize=8)


class _PDF:
    """A thin layer over fpdf2: fonts, headings, paragraphs, tables."""

    def __init__(self, title: str):
        from fpdf import FPDF

        pdf = FPDF(format="A4")
        pdf.set_margins(15, 14, 15)
        pdf.set_auto_page_break(True, 14)
        pdf.add_font("Plex", "", str(FONTS / "IBMPlexSans-Regular.ttf"))
        pdf.add_font("Plex", "B", str(FONTS / "IBMPlexSans-SemiBold.ttf"))
        pdf.set_title(title)
        pdf.set_creator("CAR-T manufacturing dashboard")
        pdf.alias_nb_pages()
        pdf.footer = lambda: self._footer()
        self.pdf = pdf
        self.title = title
        pdf.add_page()

    def _footer(self) -> None:
        p = self.pdf
        p.set_y(-10)
        p.set_font("Plex", "", 7)
        p.set_text_color(120)
        p.cell(0, 4, f"{self.title}  ·  page {p.page_no()} of {{nb}}", align="C")
        p.set_text_color(0)

    def heading(self, text: str, size: float = 11) -> None:
        p = self.pdf
        p.ln(2)
        p.set_font("Plex", "B", size)
        p.multi_cell(0, size * 0.5, text, new_x="LMARGIN", new_y="NEXT", align="L")
        p.ln(1)

    def text(self, text: str, size: float = 9, bold: bool = False, grey: bool = False) -> None:
        p = self.pdf
        p.set_font("Plex", "B" if bold else "", size)
        if grey:
            p.set_text_color(90)
        p.multi_cell(0, size * 0.48, text, new_x="LMARGIN", new_y="NEXT", align="L")
        p.set_text_color(0)
        p.ln(0.8)

    def bullets(self, lines: list[str]) -> None:
        for line in lines:
            self.text("•  " + line)

    def image(self, png: io.BytesIO | None) -> None:
        if png is not None:
            self.pdf.image(png, w=self.pdf.epw)
            self.pdf.ln(2)

    def table(self, header: list[str], rows: list[list[str]], widths: tuple[float, ...], size: float = 7) -> None:
        p = self.pdf
        p.set_font("Plex", "", size)
        with p.table(col_widths=widths, line_height=size * 0.5, text_align="LEFT", first_row_as_headings=True,
                     headings_style=_heading_style(), borders_layout="HORIZONTAL_LINES") as t:
            t.row(header)
            for r in rows:
                t.row([str(x) for x in r])
        p.ln(2)

    def output(self) -> bytes:
        return bytes(self.pdf.output())


def _heading_style():
    from fpdf.fonts import FontFace

    return FontFace(family="Plex", emphasis="BOLD")


def _number_rows(rows: list[dict]) -> list[list[str]]:
    return [
        [r["section"], r["statistic"], _fmt(r["estimate"]), _ci(r["ci_low"], r["ci_high"]), _p(r["p"]),
         _fmt(r["n_first"]) if r["n_first"] is not None else "", _fmt(r["n_second"]) if r["n_second"] is not None else "",
         r["note"]]
        for r in rows
    ]


def build_pdf(record: Record) -> bytes:
    """A record for the investigation file: findings in words, charts, every number, methods and provenance."""
    g = record.groups
    title = f"Statistics record: {record.parameter}" if record.parameter else "Statistics record"
    doc = _PDF(title)
    doc.heading(title, 15)
    doc.text(f"{_cap(g.first)} compared with {g.second}. Created {dict(record.provenance).get('Created', '')}.",
             grey=True)

    ev = record.evidence
    if ev is not None:
        doc.heading("Findings")
        doc.text(ev.headline, 10, bold=True)
        doc.bullets(ev.lines)
        doc.image(_evidence_chart(ev))
    if record.over_time is not None:
        doc.heading(f"{_cap(g.rate)} per month")
        doc.bullets(record.over_time.lines)
        doc.image(_over_time_chart(record.over_time))
    if record.model_lines:
        doc.heading("How good is the model?")
        doc.bullets(record.model_lines)
    if record.screen is not None and not record.screen.empty:
        s = record.screen
        found = int((s["q"] < 0.05).sum())
        doc.heading("All parameters (screen, exploratory)")
        doc.text(
            f"{len(s)} parameters tested within calendar quarters; {found} with q < 0.05 (Benjamini–Hochberg). "
            f"The {min(SCREEN_ROWS, len(s))} strongest are listed; the CSV has all of them."
        )
        doc.table(
            ["Parameter", "Overall difference", "Within quarters", "p", "q", "Model", "Moves with"],
            [[r.parameter, r.effect, r.within, _p(r.p), _p(r.q), r.in_model,
              f"{r.moves_with} ({r.rho:+.2f})" if isinstance(r.moves_with, str) and r.moves_with else ""]
             for r in s.head(SCREEN_ROWS).itertuples()],
            (46, 44, 18, 12, 12, 16, 32),
        )

    rows = (ev.rows if ev is not None else []) + (record.over_time.rows if record.over_time else []) + record.model_rows
    if rows:
        doc.heading("Numbers")
        doc.text(f"n1: {g.first}; n2: {g.second}. Intervals are 95%; p-values two-sided.", 8, grey=True)
        doc.table(["Section", "Statistic", "Estimate", "95% CI", "p", "n1", "n2", "Note"],
                  _number_rows(rows), (20, 50, 15, 24, 12, 10, 10, 39), size=6.5)

    doc.heading("Methods")
    used = [r["method"] for r in rows if r["method"]]
    if record.screen is not None and not record.screen.empty:
        used += [S.METHODS["within_numbers"], S.METHODS["within_categories"], S.METHODS["fdr"]]
    doc.bullets(list(dict.fromkeys(used)) or ["No statistics were computed."])
    doc.heading("Read with care")
    doc.bullets(CAVEATS)
    doc.heading("Provenance")
    doc.table(["Item", "Value"], [[k, v] for k, v in record.provenance], (40, 140), size=7)
    return doc.output()


def _cap(text: str) -> str:
    return text[:1].upper() + text[1:]
