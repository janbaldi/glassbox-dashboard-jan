import numpy as np
import pandas as pd

from trendshift import fit_trend, trend_means


def _dates(n):
    return pd.Series(pd.date_range("2020-01-01", periods=n, freq="D"))


def test_level_shift_gives_two_means():
    rng = np.random.default_rng(0)
    n = 300
    y = rng.normal(0, 1, n) + np.where(np.arange(n) >= 150, 5.0, 0.0)
    means = trend_means(_dates(n), pd.Series(y))
    assert means.nunique() == 2
    assert np.allclose(means[:150], y[:150].mean())
    assert np.allclose(means[150:], y[150:].mean())


def test_no_shift_gives_overall_mean():
    rng = np.random.default_rng(1)
    y = pd.Series(rng.normal(10, 1, 200))
    means = trend_means(_dates(200), y)
    assert np.allclose(means, y.mean())


def test_sloped_segment_mean_is_mean_of_fitted_points():
    rng = np.random.default_rng(2)
    n = 400
    y = rng.normal(0, 0.2, n) + np.linspace(0, 10, n)
    fit = fit_trend(_dates(n), pd.Series(y))
    means = trend_means(_dates(n), pd.Series(y))
    for seg in fit.segments:
        rows = (_dates(n) >= seg.start) & (_dates(n) <= seg.end)
        assert np.allclose(means[rows], y[rows.to_numpy()].mean())


def test_index_order_outliers_and_missing():
    rng = np.random.default_rng(3)
    n = 200
    df = pd.DataFrame({"date": _dates(n), "value": rng.normal(0, 1, n)})
    df.loc[10, "value"] = 1000.0  # outlier, left out of the fit
    df.loc[20, "value"] = np.nan
    df.loc[30, "date"] = pd.NaT
    df = df.sample(frac=1, random_state=0).set_index(np.arange(1000, 1000 + n))
    means = trend_means(df["date"], df["value"])
    assert means.index.equals(df.index)
    fitted = df["value"].where(df["date"].notna() & (df["value"] < 1000)).dropna()
    has_date = df["date"].notna()
    assert np.allclose(means[has_date], fitted.mean())
    assert means[~has_date].isna().all()


def test_too_few_points_gives_nan():
    means = trend_means(_dates(5), pd.Series(np.arange(5.0)))
    assert means.isna().all()
