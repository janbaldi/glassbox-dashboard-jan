"""The statistics layer against published values, SciPy, brute force and known identities.

See docs/statistics_validation.md for what each check establishes.
"""

from __future__ import annotations

import itertools
import math

import numpy as np
import pandas as pd
import pytest
from scipy import stats as sps

from cart_dashboard import evidence as E
from cart_dashboard import report as R
from cart_dashboard import stats as S
from cart_dashboard.plots import BACKGROUND_LABEL, INTEREST_LABEL, SET_COLUMN

RNG = np.random.default_rng(7)


# --------------------------------------------------------------------------- rates


@pytest.mark.parametrize(
    "k, n, lo, hi",
    [  # Newcombe (1998), Statistics in Medicine 17:857–872, table I, method 3 (Wilson, no continuity correction)
        (81, 263, 0.2553, 0.3662),
        (15, 148, 0.0624, 0.1605),
        (0, 20, 0.0, 0.1611),
        (1, 29, 0.0061, 0.1718),
    ],
)
def test_wilson_matches_newcombe(k, n, lo, hi):
    r = S.wilson(k, n)
    assert r.lo == pytest.approx(lo, abs=6e-5)
    assert r.hi == pytest.approx(hi, abs=6e-5)


@pytest.mark.parametrize("k, n", [(0, 10), (3, 10), (10, 10), (7, 250), (1234, 2000)])
def test_wilson_matches_scipy(k, n):
    ci = sps.binomtest(k, n).proportion_ci(confidence_level=0.95, method="wilson")
    r = S.wilson(k, n)
    assert (r.lo, r.hi) == pytest.approx((ci.low, ci.high), abs=1e-12)


def test_fisher_tea_tasting():
    # Fisher's lady tasting tea: 3 of 4 right each way, two-sided p = 34/70
    r1, r2, p = S.missing_comparison(pd.Series([1, 1, 1, 0], dtype=bool), pd.Series([1, 0, 0, 0], dtype=bool))
    assert p == pytest.approx(34 / 70, abs=1e-12)
    assert (r1.k, r2.k) == (3, 1)


# --------------------------------------------------------------------------- numbers


def _pairs(a, b):
    return np.array([x - y for x, y in itertools.product(a, b)])


@pytest.mark.parametrize("n1, n2, ties", [(12, 15, False), (13, 11, True), (40, 25, True)])
def test_hodges_lehmann_matches_brute_force(n1, n2, ties):
    a, b = RNG.normal(1, 1, n1), RNG.normal(0, 1, n2)
    if ties:
        a, b = np.round(a, 1), np.round(b, 1)
    shift, lo, hi = S.hodges_lehmann(a, b)
    d = np.sort(_pairs(a, b))
    assert shift == pytest.approx(np.median(d), abs=1e-12)
    c = max(1, math.floor(n1 * n2 / 2 - S.Z95 * math.sqrt(n1 * n2 * (n1 + n2 + 1) / 12)))
    assert lo == pytest.approx(d[c - 1], abs=1e-12)
    assert hi == pytest.approx(d[n1 * n2 - c], abs=1e-12)


def test_auc_and_delong_match_brute_force():
    a, b = np.round(RNG.normal(0.5, 1, 30), 1), np.round(RNG.normal(0, 1, 22), 1)
    auc, se = S.auc_delong(a, b)
    psi = np.array([[1.0 if x > y else 0.5 if x == y else 0.0 for y in b] for x in a])
    assert auc == pytest.approx(psi.mean(), abs=1e-12)
    u = sps.mannwhitneyu(a, b).statistic
    assert auc == pytest.approx(u / (len(a) * len(b)), abs=1e-12)  # AUC = U / (n1 n2)
    v10, v01 = psi.mean(axis=1), psi.mean(axis=0)  # DeLong et al. (1988) placement values
    var = v10.var(ddof=1) / len(a) + v01.var(ddof=1) / len(b)
    assert se == pytest.approx(math.sqrt(var), abs=1e-12)


def test_compare_numeric_uses_scipy_mann_whitney_and_needs_ten():
    a, b = RNG.normal(1, 1, 25), RNG.normal(0, 1, 30)
    c = S.compare_numeric(a, b)
    assert c.p == pytest.approx(sps.mannwhitneyu(a, b, alternative="two-sided").pvalue)
    assert c.direction == "higher"
    assert not S.compare_numeric(a[:9], b).tested
    assert S.compare_numeric(a[:10], b).tested


def test_van_elteren_one_stratum_is_mann_whitney():
    a, b = np.round(RNG.normal(0.4, 1, 20), 1), np.round(RNG.normal(0, 1, 26), 1)
    values = pd.Series(np.concatenate([a, b]))
    first = pd.Series([True] * len(a) + [False] * len(b))
    w = S.van_elteren(values, first, pd.Series(["2024Q1"] * len(values)))
    ref = sps.mannwhitneyu(a, b, alternative="two-sided", method="asymptotic", use_continuity=False)
    assert w.p == pytest.approx(ref.pvalue, rel=1e-10)
    assert w.auc == pytest.approx(ref.statistic / (len(a) * len(b)), abs=1e-12)


def test_van_elteren_removes_a_difference_that_is_only_time():
    # The value drifts by quarter and the first group sits in the later quarters:
    # overall a clear difference, within quarters none.
    q = np.repeat(np.arange(4), 60)
    values = pd.Series(q * 2.0 + RNG.normal(0, 1, len(q)))
    first = pd.Series(RNG.random(len(q)) < 0.1 + 0.2 * q)
    assert S.compare_numeric(values[first], values[~first]).p < 1e-6
    assert S.van_elteren(values, first, pd.Series(q.astype(str))).p > 0.01


# --------------------------------------------------------------------------- categories


def test_cmh_one_stratum_is_scaled_pearson():
    cats = pd.Series(RNG.choice(list("ABC"), 300, p=[0.5, 0.3, 0.2]))
    first = pd.Series(RNG.random(300) < np.where(cats == "C", 0.3, 0.15))
    w = S.cmh_categories(cats, first, pd.Series(["2024Q1"] * 300))
    table = pd.crosstab(cats, first)
    chi2 = sps.chi2_contingency(table, correction=False).statistic
    assert w.p == pytest.approx(sps.chi2.sf(chi2 * 299 / 300, 2), rel=1e-9)


def test_cmh_two_categories_is_mantel_haenszel():
    strata = pd.Series(np.repeat(["a", "b", "c"], 80))
    cats = pd.Series(RNG.choice(["x", "y"], 240))
    first = pd.Series(RNG.random(240) < np.where(cats == "x", 0.35, 0.2))
    w = S.cmh_categories(cats, first, strata)
    num = var = 0.0
    for s in "abc":  # the classic Mantel–Haenszel statistic, no continuity correction
        m = strata == s
        t = pd.crosstab(cats[m], first[m]).reindex(index=["x", "y"], columns=[True, False], fill_value=0).to_numpy()
        n = t.sum()
        num += t[0, 0] - t[0].sum() * t[:, 0].sum() / n
        var += t[0].sum() * t[1].sum() * t[:, 0].sum() * t[:, 1].sum() / (n * n * (n - 1))
    assert w.p == pytest.approx(sps.chi2.sf(num * num / var, 1), rel=1e-9)


def test_chi_square_statistic_and_monte_carlo():
    k, n = np.array([30, 45, 80]), np.array([200, 250, 300])
    table = np.column_stack([k, n - k])
    assert S.chi_square(k, n) == pytest.approx(sps.chi2_contingency(table, correction=False).statistic)
    asymptotic = sps.chi2_contingency(table, correction=False).pvalue
    mc = S.chi_square_monte_carlo(k, n)
    assert mc == pytest.approx(asymptotic, abs=0.01)  # large counts: the two agree
    assert S.chi_square_monte_carlo(k, n) == mc  # fixed seed: reproducible


def test_compare_categorical_groups_rare_categories():
    values = pd.Series(["A"] * 50 + ["B"] * 40 + ["C"] * 3 + ["D"] * 4)
    first = pd.Series([True] * 10 + [False] * 40 + [True] * 10 + [False] * 30 + [True] * 7)
    c = S.compare_categorical(values, first)
    assert set(c.rows["category"]) == {"A", "B", "Other"}
    other = c.rows.set_index("category").loc["Other"]
    assert (other["k"], other["n"]) == (7, 7)


# --------------------------------------------------------------------------- many parameters, time, model


def test_benjamini_hochberg_by_hand():
    p = pd.Series([0.01, 0.04, 0.03, 0.005, np.nan])
    # sorted 0.005, 0.01, 0.03, 0.04 → ×4/1, ×4/2, ×4/3, ×4/4 = 0.02, 0.02, 0.04, 0.04 (monotone)
    assert S.benjamini_hochberg(p).tolist()[:4] == pytest.approx([0.02, 0.04, 0.04, 0.02])
    assert math.isnan(S.benjamini_hochberg(p).iloc[4])


def test_p_chart_by_hand():
    dates = pd.Series(pd.to_datetime(["2024-01-15"] * 20 + ["2024-02-15"] * 20))
    first = pd.Series([True] * 10 + [False] * 10 + [True] * 2 + [False] * 18)
    t = S.monthly_rate(dates, first)
    centre = 12 / 40
    se = math.sqrt(centre * (1 - centre) / 20)
    assert t["centre"].iloc[0] == pytest.approx(centre)
    assert t["ucl"].iloc[0] == pytest.approx(centre + 3 * se)
    assert t["lcl"].iloc[0] == pytest.approx(max(0.0, centre - 3 * se))
    assert t["rate"].tolist() == [0.5, 0.1]
    assert t["flagged"].tolist() == [False, False]  # 0.5 < 0.3 + 0.307


def test_model_check_by_hand():
    is_oos = pd.Series([True, True, True, False, False, False, False, False, False, False])
    prob = pd.Series([0.9, 0.6, 0.2, 0.7, 0.1, 0.1, 0.1, 0.1, 0.1, 0.05])
    m = S.model_check(is_oos, prob, 0.5)
    assert (m.caught.k, m.caught.n) == (2, 3)
    assert (m.false_alarms.k, m.false_alarms.n) == (1, 7)
    assert m.top_n == 1 and m.top_captured.k == 1  # the top 10% of 10 batches: the 0.9
    assert m.lift == pytest.approx((1 / 3) / 0.1)


def test_strongest_partner_is_spearman():
    x = pd.Series(RNG.normal(size=200))
    frame = pd.DataFrame({"t": x + RNG.normal(0, 0.3, 200), "f1": x, "f2": RNG.normal(size=200)})
    partner, rho = S.strongest_partners(frame, ["t"], ["f1", "f2"])["t"]
    assert partner == "f1"
    assert rho == pytest.approx(sps.spearmanr(frame["t"], frame["f1"]).statistic)


# --------------------------------------------------------------------------- the evidence card and the export


def _frame(n=400, seed=3):
    rng = np.random.default_rng(seed)
    dates = pd.Timestamp("2024-01-01") + pd.to_timedelta(rng.integers(0, 720, n), unit="D")
    x = rng.normal(10, 2, n)
    oos = rng.random(n) < 1 / (1 + np.exp(-(x - 13)))
    site = rng.choice(["S1", "S2"], n)
    return pd.DataFrame({
        "id": [f"B{i:04d}" for i in range(n)], "date": dates, "site": site, "x": x,
        "cat": rng.choice(["a", "b", "c"], n), SET_COLUMN: np.where(oos, INTEREST_LABEL, BACKGROUND_LABEL),
    })


def test_evidence_card_numbers():
    f = _frame()
    ev = E.build(f, "x", "numeric", "date", E.RUN_GROUPS, site_col="site", batch_col="id")
    assert ev.tested and ev.kind == "number"
    assert ev.headline == "x is higher in batches of interest."
    assert any(line.startswith("Comparing only batches made in the same quarter") for line in ev.lines)
    first = f[SET_COLUMN] != BACKGROUND_LABEL
    auc = next(r for r in ev.rows if r["statistic"] == "AUC")
    assert auc["estimate"] == pytest.approx(S.auc_delong(f.x[first].to_numpy(), f.x[~first].to_numpy())[0])
    assert auc["n_first"] == first.sum()


def test_evidence_card_too_few():
    f = _frame()
    f[SET_COLUMN] = BACKGROUND_LABEL
    f.loc[:8, SET_COLUMN] = INTEREST_LABEL
    ev = E.build(f, "x", "numeric", "date", E.GENERIC_GROUPS)
    assert not ev.tested and ev.headline.startswith("Too few batches")


def test_screen_finds_the_driver_and_exports():
    f = _frame()
    params = pd.DataFrame({"name": ["x", "cat", "site"], "type": ["numeric", "categorical", "categorical"]})
    out = E.screen(f, params, f[SET_COLUMN] != BACKGROUND_LABEL, "date", model_features=("x",))
    assert out.iloc[0]["parameter"] == "x" and out.iloc[0]["q"] < 0.05 and out.iloc[0]["in_model"] == "yes (#1)"
    assert out["q"].between(0, 1).all()
    ev = E.build(f, "cat", "categorical", "date", E.RUN_GROUPS)
    record = R.Record(E.RUN_GROUPS, [("Created", "now")], "cat", ev, E.over_time(f, "date", E.RUN_GROUPS), screen=out)
    table = pd.read_csv(pd.io.common.BytesIO(R.build_csv(record)), encoding="utf-8-sig")
    assert set(table["section"]) >= {"provenance", "parameter", "over time", "screen"}
    assert R.build_pdf(record).startswith(b"%PDF")
