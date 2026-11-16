# trendshift

The trend fit of the glassbox dashboard as a small Python package.

Two kinds of fit compete: flat segments (level shifts) and sloped segments
(trends, which can also jump at a breakpoint).

1. Points beyond `outlier_iqr` (3) IQR below Q1 or above Q3 are left out of the fit.
2. For each kind and for 0 to `max_breaks` (10) breakpoints, dynamic programming
   finds the exact best segmentation (least squares, at least
   `min_segment_size` (15) points per segment).
3. BIC = n ln(RSS/n) + k ln(n), with k the per-segment parameters plus one per
   breakpoint. Of the fits whose BIC is within `bic_margin` (2) of the lowest,
   the one with the fewest parameters wins.

Breakpoints are only considered between at most `max_candidates` (2000) blocks
of consecutive points.

## Install

```bash
pip install .
```

## Use

```python
import pandas as pd
from trendshift import trend_means

df = pd.read_csv("batches.csv")
df["trend_mean"] = trend_means(df["date"], df["value"])
```

With a third column the trend is fitted separately for each group:

```python
df["trend_mean"] = trend_means(df["date"], df["value"], df["site"])
```

`trend_means` returns, for every row, the mean value of the trend segment the
row's date falls in (within its own group, if groups are given; a missing
group value is a group of its own). Outliers and rows without a value get the mean of their
segment; rows without a date get NaN, and every row gets NaN when there are too
few points to fit.

`fit_trend` gives the full fit (model, segments with start/end, intercept,
slope per year, sd and mean, breakpoints, outlier mask and the BIC table).

## Test

```bash
pip install -e ".[test]"
pytest
```
