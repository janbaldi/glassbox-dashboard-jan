"""How the batches of interest compare with the background batches."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import DashboardConfig
from .plots import BACKGROUND_LABEL, INTEREST_LABEL, SET_COLUMN
from .spc import ControlCharts
from .trend import TrendFit, segment_at

PERCENTILE = "Background percentile"
SAME_VALUE = "Background with same value (%)"
DEVIATION = "Deviation from trend (SD)"
SEGMENT = "Trend segment"
EWMA_SIGNAL = "EWMA signal"
CUSUM_SIGNAL = "CUSUM signal"


def context_table(
    data: pd.DataFrame,
    cfg: DashboardConfig,
    y: pd.Series,
    trend: TrendFit | None,
    raw: pd.Series | None = None,
    charts: ControlCharts | None = None,
) -> pd.DataFrame:
    """One row per plotted batch of interest.

    Numerical ``y``: the percentile of its value among the background batches
    (ties count half) and, with a trend, its distance from the trend line at
    its date in residual standard deviations of that segment.
    Categorical ``y``: the share of background batches with the same value.
    A transformed ``y`` is compared on the transformed scale; ``raw`` then
    fills the Value column. With ``charts``, whether the EWMA and CUSUM
    signal at the batch.
    """
    date_col = cfg.col("manufacturing_date")
    shown = y.notna() & data[date_col].notna()
    interest = shown & (data[SET_COLUMN] == INTEREST_LABEL)
    background = y[shown & (data[SET_COLUMN] == BACKGROUND_LABEL)]

    cols = [cfg.col("batch_id"), date_col] + ([cfg.col("site")] if cfg.has("site") else [])
    table = data.loc[interest, cols].copy()
    values = y[interest]
    table["Value"] = values if raw is None else raw[interest]

    if pd.api.types.is_numeric_dtype(y):
        bg = np.sort(background.to_numpy(float))
        below = np.searchsorted(bg, values.to_numpy(float), side="left")
        upto = np.searchsorted(bg, values.to_numpy(float), side="right")
        table[PERCENTILE] = 100 * (below + upto) / 2 / len(bg) if len(bg) else np.nan
        if trend is not None:
            segs = [segment_at(trend, d) for d in table[date_col]]
            fitted = np.array([s.value_at(d) for s, d in zip(segs, table[date_col])])
            sd = np.array([s.sd or np.nan for s in segs])
            table[DEVIATION] = (values.to_numpy(float) - fitted) / sd
            table[SEGMENT] = [trend.segments.index(s) + 1 for s in segs]
        if charts is not None:
            table[EWMA_SIGNAL] = pd.Series(charts.ewma_signal, index=charts.index).reindex(table.index)
            table[CUSUM_SIGNAL] = pd.Series(charts.cusum_signal, index=charts.index).reindex(table.index)
    else:
        share = background.value_counts(normalize=True) * 100
        table[SAME_VALUE] = values.map(share).fillna(0.0)

    return table.sort_values(date_col).reset_index(drop=True)
