# Validation of the statistics

How the numbers in the dashboard's *Statistics* section and its CSV/PDF
record were checked. The calculations are in `cart_dashboard/stats.py`; the
checks are in `tests/test_stats.py` and run with `pytest`. Each check is one
of four kinds:

- **Published**: reproduces values printed in a peer-reviewed paper.
- **SciPy**: agrees with the SciPy implementation of the same method.
- **Definition**: agrees with a brute-force computation straight from the
  method's definition (all pairs, all tables).
- **Identity**: agrees with a mathematical identity that links it to another,
  already checked, method.
- **Behaviour**: does what it is for on a constructed example.

No other statistics package (R, SAS, JMP) was used for the checks.

| What | Method | Check | Kind |
|---|---|---|---|
| Interval of a rate | Wilson score interval, no continuity correction | Newcombe (1998), *Stat Med* 17:857–872, table I, method 3: 81/263, 15/148, 0/20, 1/29 to 4 decimals | Published |
| | | `scipy.stats.binomtest(...).proportion_ci(method="wilson")` to 1e-12 | SciPy |
| Two groups, two categories (missing values) | Fisher's exact test, two-sided | Fisher's tea-tasting table [[3,1],[1,3]]: p = 34/70 | Published |
| Difference in a number | Mann–Whitney U test | computed by `scipy.stats.mannwhitneyu` | SciPy |
| Typical difference | Hodges–Lehmann shift, interval from the C-th smallest/largest pairwise difference (Hollander & Wolfe) | all n1·n2 differences sorted, with and without ties | Definition |
| AUC | P(first higher) + ½·P(tie) | all pairs; equals U/(n1·n2) from SciPy | Definition, Identity |
| AUC interval | DeLong standard error | placement values from all pairs (DeLong et al. 1988) | Definition |
| Difference within quarters, numbers | van Elteren stratified Wilcoxon test | one stratum: equals SciPy Mann–Whitney (asymptotic, no continuity correction), p to 1e-10 | Identity, SciPy |
| | | a difference caused only by a drift over time disappears | Behaviour |
| Difference within quarters, categories | generalized Cochran–Mantel–Haenszel test | one stratum: equals (N−1)/N × Pearson chi-square (SciPy); two categories, three strata: equals the classic Mantel–Haenszel statistic computed by hand | Identity, SciPy |
| Rates across categories | chi-square statistic with a Monte Carlo p-value (20,000 tables with the same totals, seed 12345) | statistic equals SciPy's; with large counts the p-value is within 0.01 of the asymptotic one; same seed, same p-value | SciPy, Behaviour |
| Many parameters | Benjamini–Hochberg q-values (`scipy.stats.false_discovery_control`) | worked example by hand | Definition |
| Share of batches of interest per month | p-chart, 3-sigma binomial limits | two months by hand | Definition |
| Model check | flagged at the decision threshold; share in the top 10% | ten batches by hand | Definition |
| "Moves with" | Spearman rank correlation | equals `scipy.stats.spearmanr` | SciPy |

The evidence card and the export are also tested end to end
(`test_evidence_card_*`, `test_screen_finds_the_driver_and_exports`): a
planted driver is found first by the screen, its AUC in the export equals the
direct calculation, and the CSV and PDF are produced.

## Choices worth knowing

- **At least 10 batches per group** for any test; below that only counts are
  shown. Categories with fewer than 10 batches are pooled as "Other" (when
  there are at least two of them), both in the overall test and within
  quarters.
- **Within quarters**: the comparisons that the screen ranks on, and that the
  card reports as "comparing only batches made in the same quarter", use
  calendar quarters of the manufacturing date as strata. Batches without a
  date are left out of these, and only quarters that have both groups count.
- **Monte Carlo p-values** are reproducible (fixed seed) and never zero:
  p = (1 + tables at least as extreme) / (20,000 + 1), so the smallest
  possible value is about 0.00005.
- **Normal approximations**: the AUC interval, the Hodges–Lehmann interval
  and the van Elteren test use normal approximations, which are accurate with
  10 or more batches per group.
- **The model check** uses glassbox's out-of-fold predictions and decision
  threshold as recorded in the run; it does not refit anything.
