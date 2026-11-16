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


def test_groups_are_fitted_separately():
    rng = np.random.default_rng(4)
    n = 200
    a = rng.normal(0, 1, n) + np.where(np.arange(n) >= 100, 5.0, 0.0)  # shift in group A
    b = rng.normal(20, 1, n)  # no shift in group B
    df = pd.DataFrame(
        {"date": pd.concat([_dates(n), _dates(n)]), "value": np.r_[a, b], "group": ["A"] * n + ["B"] * n}
    ).sample(frac=1, random_state=1)
    means = trend_means(df["date"], df["value"], df["group"])
    assert means.index.equals(df.index)
    for g, y in (("A", a), ("B", b)):
        sel = df["group"] == g
        expected = trend_means(df.loc[sel, "date"], df.loc[sel, "value"])
        assert np.allclose(means[sel], expected)
    assert means[df["group"] == "A"].nunique() == 2
    assert np.allclose(means[df["group"] == "B"], b.mean())


def test_small_group_gives_nan_and_missing_group_is_own_group():
    rng = np.random.default_rng(5)
    n = 100
    df = pd.DataFrame({"date": _dates(n), "value": rng.normal(0, 1, n), "group": ["A"] * 95 + ["B"] * 5})
    df.loc[0:49, "group"] = None
    means = trend_means(df["date"], df["value"], df["group"])
    assert means[df["group"] == "B"].isna().all()
    assert np.allclose(means[df["group"].isna()], df.loc[df["group"].isna(), "value"].mean())
    assert np.allclose(means[df["group"] == "A"], df.loc[df["group"] == "A", "value"].mean())
