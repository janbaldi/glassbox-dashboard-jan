"""Log and logit transforms of a numerical parameter, and when to suggest one."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

import numpy as np
import pandas as pd

TRANSFORMS = ["None", "Log", "Logit"]
_PERCENT = re.compile(r"%|percent", re.IGNORECASE)
_LOGIT_TICKS = [
    0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5,
    0.6, 0.7, 0.8, 0.9, 0.95, 0.98, 0.99, 0.995, 0.998, 0.999,
]


@dataclass
class Transformed:
    values: pd.Series  # transformed, NaN where the raw value is outside the domain
    axis_suffix: str  # appended to the y-axis title
    tickvals: list[float] | None  # y-axis ticks at the original values
    ticktext: list[str] | None
    out_of_domain: int  # raw values that could not be transformed
    domain: str  # e.g. "above zero", for messages


def _fmt(v: float) -> str:
    return f"{v:.4g}" if v == 0 or 1e-3 <= abs(v) < 1e6 else f"{v:.2e}"


def percent_scale(raw: pd.Series, name: str) -> float | None:
    """100 for percentages, 1 for fractions, None when logit does not apply."""
    v = raw.dropna()
    if v.empty or v.min() < 0:
        return None
    if _PERCENT.search(name) and v.max() <= 100:
        return 100.0
    if v.max() <= 1:
        return 1.0
    return 100.0 if v.max() <= 100 else None


def _log_ticks(lo: float, hi: float) -> list[float]:
    vals: list[float] = []
    for mantissas in ((1,), (1, 2, 5), range(1, 10)):
        vals = [m * 10.0**e for e in range(math.floor(lo) - 1, math.ceil(hi) + 2) for m in mantissas]
        vals = [v for v in vals if lo <= math.log10(v) <= hi]
        if len(vals) >= 4:
            return vals
    return list(np.linspace(10**lo, 10**hi, 5))


def _logit_ticks(lo: float, hi: float) -> list[float]:
    p = [q for q in _LOGIT_TICKS if lo <= math.log(q / (1 - q)) <= hi]
    if len(p) >= 3:
        return p
    ends = [1 / (1 + math.exp(-x)) for x in (lo, hi)]
    return list(np.linspace(*ends, 5))


def apply_transform(raw: pd.Series, kind: str, name: str = "") -> Transformed:
    """Transform ``raw`` for plotting and fitting. ``kind`` is one of TRANSFORMS."""
    if kind == "Log":
        ok = raw > 0
        values = np.log10(raw.where(ok))
        domain, suffix = "above zero", ", log scale"
    elif kind == "Logit":
        scale = percent_scale(raw, name) or 100.0
        p = raw / scale
        ok = (p > 0) & (p < 1)
        p = p.where(ok)
        values = np.log(p / (1 - p))
        domain, suffix = f"strictly between 0 and {scale:g}", ", logit scale"
    else:
        return Transformed(raw, "", None, None, 0, "")

    finite = values.dropna()
    tickvals = ticktext = None
    if not finite.empty:
        lo, hi = float(finite.min()), float(finite.max())
        pad = (hi - lo) * 0.05 or 0.5
        lo, hi = lo - pad, hi + pad
        if kind == "Log":
            ticks = _log_ticks(lo, hi)
            tickvals, ticktext = [math.log10(v) for v in ticks], [_fmt(v) for v in ticks]
        else:
            ticks = _logit_ticks(lo, hi)
            tickvals, ticktext = [math.log(q / (1 - q)) for q in ticks], [_fmt(q * scale) for q in ticks]
    out = int((raw.notna() & ~ok.fillna(False).astype(bool)).sum())
    return Transformed(values, suffix, tickvals, ticktext, out, domain)


def suggest_transform(raw: pd.Series, name: str = "") -> tuple[str, str] | None:
    """(transform, reason) when a transform looks better than none, else None.

    Logit for percentages (by name) with most values near 0 or 100; log for
    positive values whose skew a log removes.
    """
    v = raw.dropna().astype(float)
    if len(v) < 20 or v.nunique() < 5:
        return None

    scale = percent_scale(v, name)
    if scale == 100 and _PERCENT.search(name):  # only suggest logit for what the name says is a percentage
        p = v / scale
        inside = p[(p > 0) & (p < 1)]
        median = p.median()
        if len(inside) >= 0.9 * len(p) and (median >= 0.85 or median <= 0.15):
            return "Logit", (
                f"percentages near {'100' if median >= 0.85 else '0'}"
            )

    if v.min() > 0:
        skew, log_skew = v.skew(), np.log10(v).skew()
        if skew > 1 and abs(log_skew) < 0.5 * skew:
            return "Log", "right-skewed values"
    return None
