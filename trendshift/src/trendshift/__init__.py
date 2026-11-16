"""Find trend shifts with the segmented regression of the glassbox dashboard."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .fit import MODELS, Segment, TrendFit, fit_trend, segment_at

__all__ = ["trend_means", "fit_trend", "segment_at", "Segment", "TrendFit", "MODELS"]
__version__ = "0.1.0"


def trend_means(
    dates,
    values,
    max_breaks: int = 10,
    min_segment_size: int = 15,
    bic_margin: float = 2.0,
    outlier_iqr: float = 3.0,
    max_candidates: int = 2000,
) -> pd.Series:
    """For every input row, the mean value of the trend segment it belongs to.

    ``dates`` and ``values`` are aligned sequences (e.g. two DataFrame columns),
    in any order. The fit is exactly the dashboard's ``fit_trend`` with the same
    defaults (see that function for the parameters).

    A row belongs to the segment its date falls in, like in the dashboard:
    outliers and rows without a value also get the mean of their segment.
    Rows without a valid date get NaN, and all rows get NaN when there are too
    few points to fit. The segment mean is the mean of the fitted line over the
    segment's fitted points, which equals the mean of those points' values.

    Returns a float Series with the index of ``values`` (when it has one).
    """
    index = values.index if isinstance(values, pd.Series) else None
    out_dates = pd.to_datetime(pd.Series(dates)).reset_index(drop=True)
    result = np.full(len(out_dates), np.nan)

    fit = fit_trend(
        dates,
        values,
        max_breaks=max_breaks,
        min_segment_size=min_segment_size,
        bic_margin=bic_margin,
        outlier_iqr=outlier_iqr,
        max_candidates=max_candidates,
    )
    if fit is not None:
        for i, d in enumerate(out_dates):
            if pd.notna(d):
                result[i] = segment_at(fit, d).mean

    return pd.Series(result, index=index, name="trend_mean")
