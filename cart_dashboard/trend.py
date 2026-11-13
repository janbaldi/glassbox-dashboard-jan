"""Exact segmented regression for trends and shifts over time.

Two model families are fitted:

- shifts: flat segments (a mean per segment), for level shifts
- trends: sloped segments (intercept and slope per segment), which can also
  jump at a breakpoint

For every number of breakpoints the optimal segmentation is found exactly
with dynamic programming. BIC then picks both the family and the number of
breakpoints.

Breakpoints are only considered between blocks of consecutive batches, with
at most ``max_candidates`` blocks. Up to that many batches every batch is its
own block; beyond it (e.g. 20000 batches -> blocks of 10) the segment fits
are still exact least squares, only the breakpoint position is rounded to a
block boundary. This keeps memory and time independent of the data size.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

SECONDS_PER_YEAR = 365.25 * 24 * 3600


@dataclass
class Segment:
    start: pd.Timestamp  # date of the first batch in the segment
    end: pd.Timestamp  # date of the last batch in the segment
    n: int
    intercept: float  # fitted value at `start`
    slope_per_year: float
    sd: float  # standard deviation of the residuals in this segment

    def value_at(self, date: pd.Timestamp) -> float:
        return self.intercept + self.slope_per_year * (date - self.start).total_seconds() / SECONDS_PER_YEAR


MODELS = {"shifts": (1, "flat segments"), "trends": (2, "sloped segments")}  # parameters per segment


@dataclass
class TrendFit:
    model: str  # "shifts" or "trends"
    segments: list[Segment]
    breakpoints: list[pd.Timestamp]  # first date of each segment after the first
    outlier: np.ndarray  # bool, aligned with the input
    bic: pd.DataFrame  # one row per model family and number of breakpoints


def _segment_costs(x: np.ndarray, y: np.ndarray, cuts: np.ndarray, min_size: int, flat: bool) -> np.ndarray:
    """cost[a, b] = RSS of a flat or straight-line fit to points cuts[a]..cuts[b]-1.

    inf when that segment has fewer than min_size points or b <= a.
    """
    n = len(x)
    c = [np.concatenate([[0.0], np.cumsum(v)])[cuts] for v in (np.ones(n), x, y, x * x, x * y, y * y)]
    i, j = np.triu_indices(len(cuts), k=1)
    cnt, sx, sy, sxx, sxy, syy = (s[j] - s[i] for s in c)
    big = cnt >= min_size
    i, j, cnt, sx, sy, sxx, sxy, syy = (v[big] for v in (i, j, cnt, sx, sy, sxx, sxy, syy))
    vxx = sxx - sx * sx / cnt
    vxy = sxy - sx * sy / cnt
    vyy = syy - sy * sy / cnt
    if flat:
        rss = vyy
    else:
        rss = np.where(vxx > 1e-12, vyy - vxy * vxy / np.where(vxx > 1e-12, vxx, 1), vyy)
    cost = np.full((len(cuts), len(cuts)), np.inf)
    cost[i, j] = np.maximum(rss, 0)
    return cost


def _best_segmentations(cost: np.ndarray, max_segments: int) -> list[tuple[float, list[int]] | None]:
    """For k = 1..max_segments: (RSS, segment start indices) of the optimal k-segment fit."""
    n = cost.shape[0] - 1
    best = cost[0].copy()  # best[j]: RSS of the best 1-segment fit of points 0..j-1
    back = []
    results = [(best[n], [0]) if np.isfinite(best[n]) else None]
    for _ in range(1, max_segments):
        total = best[:, None] + cost  # total[i, j]: previous segments up to i, new segment i..j-1
        arg = np.argmin(total, axis=0)
        best = total[arg, np.arange(n + 1)]
        back.append(arg)
        if not np.isfinite(best[n]):
            results.append(None)
            continue
        starts, j = [], n
        for b in reversed(back):
            j = b[j]
            starts.append(j)
        results.append((best[n], [0] + starts[::-1]))
    return results


def fit_trend(
    dates: pd.Series,
    values: pd.Series,
    max_breaks: int = 10,
    min_segment_size: int = 15,
    bic_margin: float = 2.0,
    outlier_iqr: float = 3.0,
    max_candidates: int = 2000,
) -> TrendFit | None:
    """Fit a segmented trend to ``values`` over ``dates``.

    Points outside ``outlier_iqr`` x IQR are left out of the fit. Among all
    fits (both families, 0..``max_breaks`` breakpoints), the one with the
    fewest parameters whose BIC is within ``bic_margin`` of the lowest BIC
    wins. Returns None when there are too few points to fit a line.
    """
    dates = pd.to_datetime(pd.Series(dates)).reset_index(drop=True)
    y_all = pd.to_numeric(pd.Series(values), errors="coerce").reset_index(drop=True).to_numpy(float)
    valid = dates.notna().to_numpy() & np.isfinite(y_all)

    # ponytail: IQR over the whole series; a shift covering <25% of the batches
    # and larger than 3 IQR would be cut as outliers. Per-segment residuals if that bites.
    q1, q3 = np.percentile(y_all[valid], [25, 75]) if valid.any() else (0, 0)
    iqr = q3 - q1
    outlier = valid & ((y_all < q1 - outlier_iqr * iqr) | (y_all > q3 + outlier_iqr * iqr))
    use = valid & ~outlier
    if use.sum() < max(min_segment_size, 3):
        return None

    order = np.argsort(dates[use].to_numpy(), kind="stable")
    d = dates[use].to_numpy()[order]
    t0 = d[0]
    x = (d - t0) / np.timedelta64(1, "s") / SECONDS_PER_YEAR
    y = y_all[use][order]
    # Standardise y for numerical stability; the BIC ranking does not change.
    y_mean, y_std = y.mean(), y.std() or 1.0
    ys = (y - y_mean) / y_std

    n = len(x)
    cuts = np.unique(np.linspace(0, n, min(n, max_candidates) + 1).round().astype(int))
    rows = []
    for model, (per_segment, _) in MODELS.items():
        cost = _segment_costs(x, ys, cuts, min_segment_size, model == "shifts")
        fits = _best_segmentations(cost, max_breaks + 1)
        for k, fit in enumerate(fits):
            if fit is None:
                continue
            rss = fit[0] * y_std**2
            n_params = (per_segment + 1) * (k + 1) - 1  # per-segment parameters plus each breakpoint
            bic = n * np.log(max(rss, 1e-300) / n) + n_params * np.log(n)
            starts = [int(cuts[a]) for a in fit[1]]
            rows.append({"model": model, "n_breaks": k, "n_params": n_params, "rss": rss, "bic": bic, "starts": starts})
    bic_df = pd.DataFrame(rows)
    close = bic_df[bic_df["bic"] <= bic_df["bic"].min() + bic_margin]
    chosen = close.sort_values(["n_params", "n_breaks", "bic"]).iloc[0]

    starts = list(chosen["starts"]) + [n]
    segments = []
    for a, b in zip(starts[:-1], starts[1:]):
        xs, yy = x[a:b], y[a:b]
        if chosen["model"] == "shifts" or np.ptp(xs) == 0:
            slope, intercept = 0.0, yy.mean()
        else:
            slope, intercept = np.polyfit(xs - xs[0], yy, 1)
        resid = yy - (intercept + slope * (xs - xs[0]))
        segments.append(Segment(pd.Timestamp(d[a]), pd.Timestamp(d[b - 1]), b - a, intercept, slope, resid.std()))

    return TrendFit(
        model=str(chosen["model"]),
        segments=segments,
        breakpoints=[s.start for s in segments[1:]],
        outlier=outlier,
        bic=bic_df.drop(columns="starts"),
    )


def segment_at(fit: TrendFit, date: pd.Timestamp) -> Segment:
    """The segment a date falls in (the first/last segment for dates outside the fit)."""
    for seg in reversed(fit.segments):
        if date >= seg.start:
            return seg
    return fit.segments[0]
