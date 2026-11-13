"""EWMA and tabular CUSUM control charts over batches in manufacturing-date order.

Both charts use the same target and sigma, estimated from the reference
batches: the batches that stand for normal production (in the dashboard, the
background batches of the reference period). Without a reference, the earliest
``baseline`` charted batches. The target is their mean, sigma is their average
moving range between consecutive batches (in date order) divided by 1.128 (the
usual estimate for individual values, which a shift or trend inflates much
less than the standard deviation does). Every charted batch, the batches
of interest included, is judged against that reference, so the shifts being
looked for do not widen the limits.

``direction`` ("low", "high" or "both") says which side matters: signals are
only raised on that side.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class ControlCharts:
    dates: pd.Series  # charted batches, in date order
    index: pd.Index  # their index labels in the input
    target: float
    sigma: float
    baseline: int  # number of batches the target and sigma come from
    lam: float
    L: float
    k: float
    h: float
    ewma: np.ndarray
    ewma_lower: np.ndarray
    ewma_upper: np.ndarray
    cusum_upper: np.ndarray  # C+, in sigma units
    cusum_lower: np.ndarray  # C-, in sigma units (positive)
    direction: str = "both"  # the side that matters: low, high or both
    from_reference: bool = False  # target and sigma from the given reference batches (else the earliest ones)

    @property
    def watch_high(self) -> bool:
        return self.direction != "low"

    @property
    def watch_low(self) -> bool:
        return self.direction != "high"

    @property
    def ewma_high(self) -> np.ndarray:
        return (self.ewma > self.ewma_upper) & self.watch_high

    @property
    def ewma_low(self) -> np.ndarray:
        return (self.ewma < self.ewma_lower) & self.watch_low

    @property
    def ewma_signal(self) -> np.ndarray:
        return self.ewma_high | self.ewma_low

    @property
    def cusum_high(self) -> np.ndarray:
        return (self.cusum_upper > self.h) & self.watch_high

    @property
    def cusum_low(self) -> np.ndarray:
        return (self.cusum_lower > self.h) & self.watch_low

    @property
    def cusum_signal(self) -> np.ndarray:
        return self.cusum_high | self.cusum_low


@dataclass
class Episode:
    """A stretch of consecutive signals of one chart on one side."""

    chart: str  # "EWMA" or "CUSUM"
    direction: str  # "up" or "down"
    start: pd.Timestamp  # when the shift began: CUSUM, the batch after its sum was last zero; EWMA, the first signal
    first_signal: pd.Timestamp
    last_signal: pd.Timestamp
    signals: int  # batches signalling


def _runs(flags: np.ndarray) -> list[tuple[int, int]]:
    """(first, last) index of each run of True."""
    idx = np.flatnonzero(flags)
    if not len(idx):
        return []
    breaks = np.flatnonzero(np.diff(idx) > 1)
    starts = np.concatenate([[idx[0]], idx[breaks + 1]])
    ends = np.concatenate([idx[breaks], [idx[-1]]])
    return list(zip(starts.tolist(), ends.tolist()))


def episodes(c: ControlCharts) -> list[Episode]:
    """Every signal episode of both charts, on the sides that matter, oldest first."""
    out = []
    d = c.dates
    for flags, sums, direction in ((c.cusum_high, c.cusum_upper, "up"), (c.cusum_low, c.cusum_lower, "down")):
        previous = None
        for a, b in _runs(flags):
            zero = np.flatnonzero(sums[:a] == 0)
            start = zero[-1] + 1 if len(zero) else 0  # the CUSUM's estimate of when the shift began
            if previous is not None and previous.start == d[min(start, a)]:
                # The sum dipped under the limit without returning to zero: the same shift.
                previous.last_signal, previous.signals = d[b], previous.signals + b - a + 1
                continue
            previous = Episode("CUSUM", direction, d[min(start, a)], d[a], d[b], b - a + 1)
            out.append(previous)
    for flags, direction in ((c.ewma_high, "up"), (c.ewma_low, "down")):
        for a, b in _runs(flags):
            out.append(Episode("EWMA", direction, d[a], d[a], d[b], b - a + 1))
    return sorted(out, key=lambda e: (e.first_signal, e.chart))


def control_charts(
    dates: pd.Series,
    values: pd.Series,
    lam: float = 0.2,
    L: float = 3.0,
    k: float = 0.5,
    h: float = 5.0,
    baseline: int = 100,
    reference: pd.Series | None = None,
    direction: str = "both",
) -> ControlCharts | None:
    """EWMA (weight ``lam``, limits at ``L`` sigma) and CUSUM (slack ``k``, decision interval ``h``, in sigma).

    ``reference`` (bool, aligned with ``values``) marks the batches target and
    sigma come from; with fewer than 3 of them, or none given, the earliest
    ``baseline`` batches. Returns None with fewer than 3 batches or no variation.
    """
    ok = pd.Series(values).notna() & pd.Series(dates).notna()
    frame = pd.DataFrame({"d": dates[ok], "y": values[ok].astype(float)}).sort_values("d", kind="stable")
    y = frame["y"].to_numpy()
    if len(y) < 3:
        return None
    ref = None
    if reference is not None:
        ref = pd.Series(reference, index=values.index).reindex(frame.index).fillna(False).astype(bool).to_numpy()
        if ref.sum() < 3:
            ref = None
    base = y[ref] if ref is not None else y[: max(int(baseline), 3)]
    target = base.mean()
    sigma = np.abs(np.diff(base)).mean() / 1.128 or base.std()
    if not sigma:
        return None

    n = len(y)
    ewma = np.empty(n)
    prev = target
    for i, v in enumerate(y):
        prev = lam * v + (1 - lam) * prev
        ewma[i] = prev
    i = np.arange(1, n + 1)
    width = L * sigma * np.sqrt(lam / (2 - lam) * (1 - (1 - lam) ** (2 * i)))

    z = (y - target) / sigma
    upper, lower = np.empty(n), np.empty(n)
    cu = cl = 0.0
    for j, v in enumerate(z):
        cu, cl = max(0.0, cu + v - k), max(0.0, cl - v - k)
        upper[j], lower[j] = cu, cl

    return ControlCharts(
        frame["d"].reset_index(drop=True), frame.index, target, sigma, len(base), lam, L, k, h,
        ewma, target - width, target + width, upper, lower,
        direction if direction in ("low", "high") else "both", ref is not None,
    )
