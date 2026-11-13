"""Statistics comparing the batches of interest with the background.

Plain calculations with no Streamlit, so each can be checked against reference
values (tests/test_stats.py, docs/statistics_validation.md). The views turn the
results into sentences, charts and the export.

The first group is the batches of interest, the second the background.
Every test is two-sided and every interval 95%. A comparison needs at least
MIN_BATCHES batches with a value in each group; with fewer, only counts are
given.

Methods (see ``METHODS`` for the wording used in the app and the export):

- difference in a numerical value: Mann–Whitney test; the typical difference
  is the Hodges–Lehmann shift with its distribution-free interval; the AUC
  (the chance that a batch of the first group has the higher value) with a
  DeLong standard error
- a rate: Wilson interval
- rates across categories: Fisher's exact test for two categories, otherwise a
  chi-square statistic with a Monte Carlo p-value from tables with the same
  totals (exact in the limit; no large-count assumption)
- many parameters at once: Benjamini–Hochberg adjusted p-values (q)
- rates over time: p-chart with 3-sigma binomial limits
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats as sps

MIN_BATCHES = 10  # per group, for a test; also the smallest category shown on its own
Z95 = 1.959963984540054  # two-sided 95% normal quantile
MC_TABLES = 20_000  # simulated tables for the Monte Carlo chi-square p-value
SEED = 12345  # fixed, so every p-value can be reproduced; recorded in the export
TOP_SHARE = 0.10  # the model check's "highest-risk 10%"

METHODS = {
    "rank_test": "Mann–Whitney U test, two-sided (SciPy mannwhitneyu, exact for small samples without ties, "
    "otherwise normal approximation with tie correction)",
    "shift": "Hodges–Lehmann estimate (median of all pairwise differences) with its distribution-free 95% "
    "interval from the Mann–Whitney distribution (normal approximation, rounded to the conservative side)",
    "auc": "AUC = P(first group higher) + ½·P(tie) = U / (n1·n2); 95% interval from the DeLong standard "
    "error (normal approximation, truncated to [0, 1])",
    "rate": "Proportion with a Wilson score 95% interval (no continuity correction)",
    "two_categories": "Fisher's exact test, two-sided",
    "categories": f"Chi-square statistic with a Monte Carlo p-value: {MC_TABLES:,} random tables with the same "
    f"row and column totals (seed {SEED}); p = (1 + tables at least as extreme) / ({MC_TABLES:,} + 1)",
    "fdr": "Benjamini–Hochberg adjusted p-values (q), over every parameter tested in the screen",
    "within_numbers": "Comparison within calendar quarters (batches made in the same quarter only): "
    "van Elteren stratified Wilcoxon test (weights 1/(n+1), normal approximation with tie correction); "
    "the AUC within quarters is the matching weighted average of the per-quarter AUCs",
    "within_categories": "Comparison within calendar quarters: generalized Cochran–Mantel–Haenszel test "
    "of general association (chi-square with categories − 1 degrees of freedom)",
    "p_chart": "p-chart: monthly rate, centre line at the overall rate, limits at ±3 binomial standard "
    f"errors for that month's number of batches; months with fewer than {MIN_BATCHES} batches are not flagged",
    "model": "Out-of-fold probabilities from glassbox (each batch scored by a model that never saw it); "
    "a batch is flagged when its probability is at least the model's decision threshold",
    "spearman": "Spearman rank correlation over the batches that have both values",
}


# --------------------------------------------------------------------------- formatting


def fmt_num(x: float | None) -> str:
    """A value for a sentence: about three significant digits, thousands separated."""
    if x is None or not np.isfinite(x):
        return "—"
    a = abs(x)
    if a >= 100:
        return f"{x:,.0f}"
    if a >= 10:
        return f"{x:.1f}"
    if a >= 1:
        return f"{x:.2f}"
    return f"{x:.3g}"


def fmt_p(p: float | None) -> str:
    if p is None or not np.isfinite(p):
        return "p = —"
    return "p < 0.001" if p < 0.001 else f"p = {p:.2g}"


def fmt_pct(x: float | None) -> str:
    if x is None or not np.isfinite(x):
        return "—"
    return f"{100 * x:.1f}%" if 0 < abs(x) < 0.1 else f"{100 * x:.0f}%"


# --------------------------------------------------------------------------- rates


@dataclass
class Rate:
    k: int
    n: int
    p: float
    lo: float
    hi: float

    def pct_ci(self) -> str:
        """'42%, 95% CI 19%–68%'."""
        return f"{fmt_pct(self.p)}, 95% CI {fmt_pct(self.lo)}–{fmt_pct(self.hi)}"

    def text(self) -> str:
        """'5 of 12 (42%, 95% CI 19%–68%)'."""
        return f"{self.k:,} of {self.n:,} ({self.pct_ci()})"


def wilson(k: int, n: int) -> Rate:
    """k of n with its Wilson score 95% interval (closed form; checked against SciPy and Newcombe 1998)."""
    if n == 0:
        return Rate(0, 0, math.nan, math.nan, math.nan)
    p, z2 = k / n, Z95**2
    centre = (p + z2 / (2 * n)) / (1 + z2 / n)
    half = Z95 * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / (1 + z2 / n)
    return Rate(int(k), int(n), p, max(0.0, centre - half), min(1.0, centre + half))


# --------------------------------------------------------------------------- numerical values


@dataclass
class NumericComparison:
    n1: int
    n2: int
    median1: float
    median2: float
    tested: bool = False
    p: float = math.nan
    auc: float = math.nan
    auc_lo: float = math.nan
    auc_hi: float = math.nan
    shift: float = math.nan  # first group minus second, Hodges–Lehmann
    shift_lo: float = math.nan
    shift_hi: float = math.nan

    @property
    def direction(self) -> str | None:
        """'higher' or 'lower' in the first group when the test says so (p < 0.05), else None."""
        if not self.tested or not self.p < 0.05 or self.auc == 0.5:
            return None
        return "higher" if self.auc > 0.5 else "lower"


def _finite(x) -> np.ndarray:
    a = pd.to_numeric(pd.Series(x), errors="coerce").to_numpy(dtype=float, na_value=np.nan)
    return a[np.isfinite(a)]


def auc_delong(a: np.ndarray, b: np.ndarray) -> tuple[float, float]:
    """AUC = P(a > b) + ½·P(a = b), and its DeLong standard error.

    From the placement values: for each value of ``a`` the share of ``b`` below
    it (ties half), and for each value of ``b`` the share of ``a`` above it.
    """
    bs, as_ = np.sort(b), np.sort(a)
    v10 = (np.searchsorted(bs, a, "left") + np.searchsorted(bs, a, "right")) / 2 / len(b)
    v01 = (len(a) - (np.searchsorted(as_, b, "left") + np.searchsorted(as_, b, "right")) / 2) / len(a)
    auc = float(v10.mean())
    var = v10.var(ddof=1) / len(a) + v01.var(ddof=1) / len(b)
    return auc, float(math.sqrt(max(var, 0.0)))


def _count_at_most(a_sorted: np.ndarray, b_sorted: np.ndarray, d: float) -> int:
    """Number of pairs with a_i − b_j ≤ d."""
    return int((len(b_sorted) - np.searchsorted(b_sorted, a_sorted - d, "left")).sum())


def _kth_difference(a_sorted: np.ndarray, b_sorted: np.ndarray, k: int) -> float:
    """The k-th smallest of all n1·n2 differences a_i − b_j (1-based), without building them.

    Bisection on the value, then the largest actual difference at or below it:
    exact, and O(n log n) per step, so it scales to tens of thousands of batches.
    """
    lo, hi = a_sorted[0] - b_sorted[-1], a_sorted[-1] - b_sorted[0]
    if _count_at_most(a_sorted, b_sorted, lo) >= k:
        return float(lo)
    for _ in range(200):
        mid = lo + (hi - lo) / 2
        if mid <= lo or mid >= hi:
            break
        if _count_at_most(a_sorted, b_sorted, mid) >= k:
            hi = mid
        else:
            lo = mid
    j = np.searchsorted(b_sorted, a_sorted - hi, "left")
    ok = j < len(b_sorted)
    return float((a_sorted[ok] - b_sorted[j[ok]]).max())


def hodges_lehmann(a: np.ndarray, b: np.ndarray) -> tuple[float, float, float]:
    """Hodges–Lehmann shift (median of all a_i − b_j) and its 95% interval.

    The interval runs from the C-th smallest to the C-th largest difference,
    C = floor(n1·n2/2 − z·sqrt(n1·n2·(n1+n2+1)/12)) (Hollander & Wolfe), at least 1.
    """
    a_s, b_s = np.sort(a), np.sort(b)
    n = len(a) * len(b)
    if n % 2:
        shift = _kth_difference(a_s, b_s, (n + 1) // 2)
    else:
        shift = (_kth_difference(a_s, b_s, n // 2) + _kth_difference(a_s, b_s, n // 2 + 1)) / 2
    c = max(1, math.floor(n / 2 - Z95 * math.sqrt(len(a) * len(b) * (len(a) + len(b) + 1) / 12)))
    return shift, _kth_difference(a_s, b_s, c), _kth_difference(a_s, b_s, n - c + 1)


def compare_numeric(first, second, shift: bool = True) -> NumericComparison:
    """The first group against the second, for a numerical value. ``shift=False`` skips Hodges–Lehmann."""
    a, b = _finite(first), _finite(second)
    out = NumericComparison(
        len(a), len(b),
        float(np.median(a)) if len(a) else math.nan, float(np.median(b)) if len(b) else math.nan,
    )
    if len(a) < MIN_BATCHES or len(b) < MIN_BATCHES:
        return out
    out.tested = True
    if np.ptp(np.concatenate([a, b])) == 0:  # one value everywhere: nothing to compare
        out.p, out.auc, out.auc_lo, out.auc_hi = 1.0, 0.5, 0.5, 0.5
        out.shift = out.shift_lo = out.shift_hi = 0.0
        return out
    out.p = float(sps.mannwhitneyu(a, b, alternative="two-sided").pvalue)
    out.auc, se = auc_delong(a, b)
    out.auc_lo, out.auc_hi = max(0.0, out.auc - Z95 * se), min(1.0, out.auc + Z95 * se)
    if shift:
        out.shift, out.shift_lo, out.shift_hi = hodges_lehmann(a, b)
    return out


def rate_by_value(values: pd.Series, in_first: pd.Series, groups: int = 4) -> pd.DataFrame | None:
    """The first group's share in (about) equal-sized groups of the value, lowest values first.

    Groups are cut at the quartiles, so equal values stay in one group. ``None``
    when the values do not split into at least two groups.
    """
    v = pd.to_numeric(values, errors="coerce").astype(float)
    ok = v.notna() & np.isfinite(v)
    v, g = v[ok], in_first[ok].astype(bool)
    if len(v) < 2 * MIN_BATCHES:
        return None
    bins = pd.qcut(v, groups, duplicates="drop")
    if len(bins.cat.categories) < 2:
        return None
    rows = []
    last = len(bins.cat.categories) - 1
    for i, interval in enumerate(bins.cat.categories):
        members = bins == interval
        rate = wilson(int(g[members].sum()), int(members.sum()))
        label = (
            f"≤ {fmt_num(interval.right)}" if i == 0
            else f"> {fmt_num(interval.left)}" if i == last
            else f"{fmt_num(interval.left)} to {fmt_num(interval.right)}"
        )
        rows.append({"group": label, "n": rate.n, "k": rate.k, "rate": rate.p, "lo": rate.lo, "hi": rate.hi})
    return pd.DataFrame(rows)


def consistency(values: pd.Series, in_first: pd.Series, strata: pd.Series) -> pd.DataFrame:
    """The AUC within each stratum (site, year), where both groups have enough batches."""
    rows = []
    for stratum, idx in strata.groupby(strata, sort=True).groups.items():
        v, g = values.loc[idx], in_first.loc[idx].astype(bool)
        c = compare_numeric(v[g], v[~g], shift=False)
        rows.append({"stratum": str(stratum), "n1": c.n1, "n2": c.n2, "auc": c.auc if c.tested else math.nan,
                     "lo": c.auc_lo, "hi": c.auc_hi})
    return pd.DataFrame(rows, columns=["stratum", "n1", "n2", "auc", "lo", "hi"])


# --------------------------------------------------------------------------- categories


@dataclass
class CategoricalComparison:
    rows: pd.DataFrame  # category, n, k, rate, lo, hi; highest rate first
    overall: Rate
    n1: int
    n2: int
    tested: bool = False
    p: float = math.nan
    method: str = ""


def chi_square(k: np.ndarray, n: np.ndarray) -> float:
    """Chi-square statistic of a categories × 2 table: ``k`` of ``n`` batches per category in the first group."""
    k, n = np.asarray(k, float), np.asarray(n, float)
    total, first = n.sum(), k.sum()
    e1 = n * first / total
    e2 = n - e1
    with np.errstate(divide="ignore", invalid="ignore"):
        terms = np.where(e1 > 0, (k - e1) ** 2 / e1, 0) + np.where(e2 > 0, ((n - k) - e2) ** 2 / e2, 0)
    return float(terms.sum(axis=-1))


def chi_square_monte_carlo(k: np.ndarray, n: np.ndarray, tables: int = MC_TABLES, seed: int = SEED) -> float:
    """Monte Carlo p-value of the chi-square statistic, over tables with the same totals.

    Under no association, the first group's batches are a random draw from all
    batches: a multivariate hypergeometric draw of ``sum(k)`` from categories of
    size ``n``.
    """
    k, n = np.asarray(k, int), np.asarray(n, int)
    observed = chi_square(k, n)
    sims = np.random.default_rng(seed).multivariate_hypergeometric(n, int(k.sum()), size=tables)
    first = k.sum()
    total = n.sum()
    e1 = n * first / total
    e2 = n - e1
    with np.errstate(divide="ignore", invalid="ignore"):
        stat = (np.where(e1 > 0, (sims - e1) ** 2 / e1, 0) + np.where(e2 > 0, ((n - sims) - e2) ** 2 / e2, 0)).sum(axis=1)
    extreme = int((stat >= observed * (1 - 1e-12)).sum())
    return (1 + extreme) / (tables + 1)


def group_rare(values: pd.Series) -> pd.Series:
    """Categories as text, those with fewer than MIN_BATCHES batches grouped as "Other" (when more than one)."""
    v = values.dropna().astype(str)
    sizes = v.value_counts()
    small = sizes[sizes < MIN_BATCHES].index
    return v.where(~v.isin(small), "Other") if len(small) > 1 else v


def compare_categorical(values: pd.Series, in_first: pd.Series, test: bool = True) -> CategoricalComparison:
    """The first group's share per category, and whether it differs between categories.

    Categories with fewer than MIN_BATCHES batches are grouped as "Other". ``test=False``
    skips the test (``tested`` then only says whether there is enough to test).
    """
    v = group_rare(values)
    g = in_first[v.index].astype(bool)
    table = pd.DataFrame({"n": v.value_counts(), "k": g.groupby(v).sum()}).fillna(0).astype(int)
    rows = []
    for category, r in table.iterrows():
        rate = wilson(int(r["k"]), int(r["n"]))
        rows.append({"category": category, "n": rate.n, "k": rate.k, "rate": rate.p, "lo": rate.lo, "hi": rate.hi})
    rows = pd.DataFrame(rows, columns=["category", "n", "k", "rate", "lo", "hi"]).sort_values(
        ["rate", "n"], ascending=[False, False], kind="stable"
    ).reset_index(drop=True)
    out = CategoricalComparison(rows, wilson(int(g.sum()), len(g)), int(g.sum()), int((~g).sum()))
    if out.n1 < MIN_BATCHES or out.n2 < MIN_BATCHES or len(table) < 2:
        return out
    out.tested = True
    if not test:
        return out
    if len(table) == 2:
        a, b = table.iloc[0], table.iloc[1]
        out.p = float(sps.fisher_exact([[a["k"], a["n"] - a["k"]], [b["k"], b["n"] - b["k"]]]).pvalue)
        out.method = "two_categories"
    else:
        out.p = chi_square_monte_carlo(table["k"].to_numpy(), table["n"].to_numpy())
        out.method = "categories"
    return out


def missing_comparison(missing_first: pd.Series, missing_second: pd.Series) -> tuple[Rate, Rate, float]:
    """Share of missing values per group, and Fisher's exact p for a difference."""
    m1, m2 = missing_first.astype(bool), missing_second.astype(bool)
    r1, r2 = wilson(int(m1.sum()), len(m1)), wilson(int(m2.sum()), len(m2))
    if not len(m1) or not len(m2):
        return r1, r2, math.nan
    p = sps.fisher_exact([[r1.k, r1.n - r1.k], [r2.k, r2.n - r2.k]]).pvalue
    return r1, r2, float(p)


# --------------------------------------------------------------------------- over time


def monthly_rate(dates: pd.Series, in_first: pd.Series) -> pd.DataFrame:
    """The first group's share per month, with p-chart limits.

    Centre line: the overall share. Limits: ±3 binomial standard errors for
    the month's number of batches (lower limit at least 0). A month is flagged
    when it has at least MIN_BATCHES batches and lies above the upper limit.
    """
    ok = dates.notna()
    month = pd.to_datetime(dates[ok]).dt.to_period("M")
    g = in_first[ok].astype(bool)
    by = pd.DataFrame({"n": g.groupby(month).size(), "k": g.groupby(month).sum()}).sort_index()
    if by.empty:
        return pd.DataFrame(columns=["month", "n", "k", "rate", "centre", "lcl", "ucl", "flagged"])
    centre = by["k"].sum() / by["n"].sum()
    se = np.sqrt(centre * (1 - centre) / by["n"])
    out = pd.DataFrame(
        {
            "month": by.index.to_timestamp(),
            "n": by["n"].to_numpy(),
            "k": by["k"].to_numpy(),
            "rate": (by["k"] / by["n"]).to_numpy(),
            "centre": centre,
            "lcl": np.maximum(0.0, centre - 3 * se).to_numpy(),
            "ucl": np.minimum(1.0, centre + 3 * se).to_numpy(),
        }
    )
    out["flagged"] = (out["n"] >= MIN_BATCHES) & (out["rate"] > out["ucl"])
    return out


# --------------------------------------------------------------------------- the model


@dataclass
class ModelCheck:
    threshold: float
    caught: Rate  # batches of interest flagged
    false_alarms: Rate  # background batches flagged
    top_n: int  # the highest-probability TOP_SHARE of batches
    top_captured: Rate  # batches of interest among them, as a share of all of them
    lift: float  # top_captured.p / TOP_SHARE


def model_check(is_interest: pd.Series, prob: pd.Series, threshold: float) -> ModelCheck:
    """How the model's out-of-fold probabilities separate the batches of interest from the background."""
    ok = prob.notna() & is_interest.notna()
    y, p = is_interest[ok].astype(bool).to_numpy(), prob[ok].astype(float).to_numpy()
    flagged = p >= threshold
    caught = wilson(int((flagged & y).sum()), int(y.sum()))
    false_alarms = wilson(int((flagged & ~y).sum()), int((~y).sum()))
    top_n = max(1, math.ceil(TOP_SHARE * len(p)))
    top = np.argsort(-p, kind="stable")[:top_n]
    captured = wilson(int(y[top].sum()), int(y.sum()))
    lift = captured.p / (top_n / len(p)) if len(p) else math.nan
    return ModelCheck(float(threshold), caught, false_alarms, top_n, captured, lift)


def driver_stats(contributions: pd.DataFrame, batches: list[str], feature: str) -> dict | None:
    """How a feature drives the given batches of interest in the model.

    ``contributions`` is ``glassbox.ModelRun.contributions`` (one row per batch
    and feature). Returns the number of batches, how many it pushed toward interest,
    in how many it was the #1 and a top-3 driver (by absolute in-sample
    contribution), and how often the leave-one-out refit reproduced it.
    """
    c = contributions[contributions["batch_id"].isin(batches)]
    if c.empty or feature not in set(c["feature"]):
        return None
    rank = c["in_sample"].abs().groupby(c["batch_id"]).rank(ascending=False, method="min")
    mine = c["feature"] == feature
    agree = c.loc[mine, "agree"].astype(str).str.lower()
    return {
        "n": int(mine.sum()),
        "up": int((c.loc[mine, "in_sample"] > 0).sum()),
        "top1": int((rank[mine] == 1).sum()),
        "top3": int((rank[mine] <= 3).sum()),
        "reproduced": int((agree == "true").sum()),
        "checked": int(agree.isin(["true", "false"]).sum()),
    }


# --------------------------------------------------------------------------- many parameters


def benjamini_hochberg(p: pd.Series) -> pd.Series:
    """Benjamini–Hochberg adjusted p-values (q); NaN stays NaN."""
    q = pd.Series(np.nan, index=p.index)
    ok = p.notna()
    if ok.any():
        q[ok] = sps.false_discovery_control(p[ok].to_numpy(dtype=float), method="bh")
    return q


def spearman(x: pd.Series, y: pd.Series) -> float:
    """Spearman rank correlation over the rows where both are present."""
    pair = pd.concat([x, y], axis=1).dropna()
    if len(pair) < MIN_BATCHES or pair.iloc[:, 0].nunique() < 2 or pair.iloc[:, 1].nunique() < 2:
        return math.nan
    return float(sps.spearmanr(pair.iloc[:, 0], pair.iloc[:, 1]).statistic)


def strongest_partners(frame: pd.DataFrame, targets: list[str], candidates: list[str]) -> dict[str, tuple[str, float]]:
    """For each target column, the candidate with the strongest rank correlation, and its Spearman ρ.

    The candidate is found fast on ranks over all rows (pairwise complete), and
    its ρ then computed exactly (``spearman``) over the rows both have.
    """
    cands = [c for c in candidates if c in frame]
    if not cands or not targets:
        return {}
    ranks = frame[list(dict.fromkeys(targets + cands))].rank()
    t = ranks[targets].to_numpy(float)
    out: dict[str, tuple[str, float]] = {}
    best = np.full(len(targets), -1.0)
    who = np.full(len(targets), -1)
    for j, c in enumerate(cands):
        r = ranks[c].to_numpy(float)[:, None]
        m = ~np.isnan(t) & ~np.isnan(r)
        n = m.sum(axis=0)
        tx, rx = np.where(m, t, 0.0), np.where(m, r, 0.0)
        with np.errstate(divide="ignore", invalid="ignore"):
            mt, mr = tx.sum(0) / n, rx.sum(0) / n
            cov = (tx * rx).sum(0) / n - mt * mr
            vt = (tx * tx).sum(0) / n - mt**2
            vr = (rx * rx).sum(0) / n - mr**2
            rho = np.abs(cov / np.sqrt(vt * vr))
        rho[(n < MIN_BATCHES) | ~np.isfinite(rho)] = -1
        rho[[targets[i] == c for i in range(len(targets))]] = -1
        better = rho > best
        best[better], who[better] = rho[better], j
    for i, target in enumerate(targets):
        if who[i] >= 0:
            partner = cands[who[i]]
            out[target] = (partner, spearman(frame[target], frame[partner]))
    return out


# --------------------------------------------------------------------------- within calendar quarters


def quarters(dates: pd.Series) -> pd.Series:
    """Calendar quarter of each date ("2024Q1"); missing where the date is."""
    d = pd.to_datetime(dates)
    return d.dt.to_period("Q").astype("string")


def _by_stratum(strata: pd.Series, ok: np.ndarray):
    """Positions of the rows in ``ok``, split by stratum (numpy, no pandas groupby)."""
    codes, _ = pd.factorize(strata.to_numpy()[ok])
    pos = np.flatnonzero(ok)
    order = np.argsort(codes, kind="stable")
    bounds = np.flatnonzero(np.diff(codes[order])) + 1
    return np.split(pos[order], bounds) if len(order) else []


@dataclass
class Within:
    """A comparison made within strata (calendar quarters)."""

    tested: bool
    p: float = math.nan
    auc: float = math.nan  # numbers only: the weighted average of the per-stratum AUCs
    n1: int = 0  # batches in strata that have both groups
    n2: int = 0
    strata: int = 0


def van_elteren(values: pd.Series, in_first: pd.Series, strata: pd.Series) -> Within:
    """Stratified Wilcoxon (van Elteren) test of the first group against the second.

    Within each stratum that has both groups: the rank sum W of the first group
    against its expectation, weighted by 1/(N+1); the variance has the usual tie
    correction. Z = Σ w(W − E) / sqrt(Σ w² Var), two-sided normal p-value. The
    matching AUC is Σ w·U / Σ w·n1·n2 with U = W − n1(n1+1)/2.
    """
    v_all = pd.to_numeric(values, errors="coerce").to_numpy(dtype=float, na_value=np.nan)
    g_all = in_first.astype(bool).to_numpy()
    ok = np.isfinite(v_all) & strata.notna().to_numpy()
    num = var = u_w = uu_w = 0.0
    n1_all = n2_all = used = 0
    for idx in _by_stratum(strata, ok):
        x, g = v_all[idx], g_all[idx]
        n1, n = int(g.sum()), len(x)
        n2 = n - n1
        if n1 == 0 or n2 == 0:
            continue
        ranks = sps.rankdata(x)
        w_sum = ranks[g].sum()
        _, ties = np.unique(x, return_counts=True)
        t = (ties**3 - ties).sum()
        var_s = n1 * n2 * (n + 1) / 12 - n1 * n2 * t / (12 * n * (n - 1)) if n > 1 else 0.0
        w = 1 / (n + 1)
        num += w * (w_sum - n1 * (n + 1) / 2)
        var += w * w * var_s
        u_w += w * (w_sum - n1 * (n1 + 1) / 2)
        uu_w += w * n1 * n2
        n1_all, n2_all, used = n1_all + n1, n2_all + n2, used + 1
    out = Within(False, n1=n1_all, n2=n2_all, strata=used)
    if n1_all < MIN_BATCHES or n2_all < MIN_BATCHES:
        return out
    out.tested = True
    out.auc = u_w / uu_w if uu_w else math.nan
    out.p = float(2 * sps.norm.sf(abs(num) / math.sqrt(var))) if var > 0 else 1.0
    return out


def cmh_categories(values: pd.Series, in_first: pd.Series, strata: pd.Series) -> Within:
    """Generalized Cochran–Mantel–Haenszel test: does the first group's share differ by category within strata?

    For a categories × 2 table per stratum: O = Σ first-group counts per category,
    E = Σ n·K/N, V = Σ K(N−K)/(N²(N−1)) · (N·diag(n) − n·nᵀ); statistic
    (O−E)ᵀ V⁺ (O−E), chi-square with rank(V) degrees of freedom. With one stratum
    it is (N−1)/N times Pearson's chi-square; with two categories, the classic
    Mantel–Haenszel test without continuity correction. Categories with fewer than
    MIN_BATCHES batches are grouped as "Other" first, as on the card.
    """
    v = group_rare(values)  # the categories the card shows
    v = v[strata[v.index].notna()]
    g, st = in_first[v.index].astype(bool), strata[v.index]
    cats = sorted(v.unique())
    if len(cats) < 2:
        return Within(False)
    code = pd.Categorical(v, categories=cats).codes
    g_all = g.to_numpy()
    o = np.zeros(len(cats))
    e = np.zeros(len(cats))
    vmat = np.zeros((len(cats), len(cats)))
    n1_all = n2_all = used = 0
    for idx in _by_stratum(st, np.ones(len(code), dtype=bool)):
        c, gg = code[idx], g_all[idx]
        big_n, k = len(c), int(gg.sum())
        if big_n < 2 or k == 0 or k == big_n:
            continue
        n = np.bincount(c, minlength=len(cats)).astype(float)
        o += np.bincount(c[gg], minlength=len(cats))
        e += n * k / big_n
        vmat += k * (big_n - k) / (big_n**2 * (big_n - 1)) * (big_n * np.diag(n) - np.outer(n, n))
        n1_all, n2_all, used = n1_all + k, n2_all + big_n - k, used + 1
    out = Within(False, n1=n1_all, n2=n2_all, strata=used)
    if n1_all < MIN_BATCHES or n2_all < MIN_BATCHES:
        return out
    # V has rank (categories − 1) when every category occurs in a stratum with
    # both groups; one category (and any without variance) dropped, it is invertible.
    d = o - e
    keep = np.flatnonzero(np.diag(vmat) > 1e-12)[:-1]
    if len(keep) == 0:
        return out
    try:
        stat = float(d[keep] @ np.linalg.solve(vmat[np.ix_(keep, keep)], d[keep]))
        df = len(keep)
    except np.linalg.LinAlgError:
        df = int(np.linalg.matrix_rank(vmat))
        stat = float(d @ np.linalg.pinv(vmat) @ d)
        if df == 0:
            return out
    out.tested, out.p = True, float(sps.chi2.sf(stat, df))
    return out
