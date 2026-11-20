# CAR-T manufacturing dashboard

A Streamlit dashboard that plots the manufacturing data of one or more batches of
interest against a set of background batches.

## Quick start

```bash
pip install -r requirements.txt
streamlit run app.py
```

Out of the box the app uses `config/config.yaml`, which points to a synthetic
dataset of 2000 batches from January 2024 onwards (`data/sample_batches.csv.gz`).
It has one column per parameter in `catalog.xlsx`. Regenerate it with
`python scripts/generate_sample_data.py`.

## Using your own data

1. Copy `config/config.yaml` to `config/config.local.yaml`. This file is
   git-ignored, and so is everything in `data/` except the sample.
2. Set `data.csv_path` to your CSV file.
3. Map your column names onto the dashboard parameters:
   - `columns`: one parameter to one column (`batch_id` and
     `manufacturing_date` are required; `site` and `remanufacture` are
     optional, and their filters are hidden when you leave them out)
   - `column_groups`: one parameter to a list of columns, for features that
     offer a choice of columns
   - `remanufacture.true_values`: the values that mark a batch as re-manufactured
   - `parameters`: the parameter catalogue (`catalog.xlsx`, Excel or CSV) that
     lists the parameters the dashboard can show, which of its columns hold
     the parameter name and value type, which columns (`filter_columns`) can
     be used to filter the parameter list, and which column (`exclude_column`)
     hides parameters

### Hiding parameters

Every parameter in the catalogue that is also a column in the data is shown.
To hide one, put `Y` (or `Yes`, `True`, `1`, `X`; case does not matter) in
its *Exclude* column in `catalog.xlsx`. It then disappears from every page:
the parameter lists, the monitoring tabs and the screens. Leave the cell
empty to show it again. `parameters.exclude_column` and
`parameters.exclude_values` in the config change the column and the values.

The app picks its config in this order: the `DASHBOARD_CONFIG` environment
variable, then `config/config.local.yaml`, then `config/config.yaml`.

## Layout

Tabs along the top. Only the open tab is calculated, and what it calculates
is cached, so switching tabs is quick.

**Monitoring tabs** (where are we). They share the sidebar: period, recent
window (the last 30 to 180 days of the period), baseline, sites,
re-manufactures. Everything compares the recent window with the baseline
(the rest of the period, or fixed dates), live, and the period ends at the
data's last date.

| Tab | Shows |
| --- | --- |
| Overview | Batches started and in process, OOS rate against the baseline, parameters shifted, lead time; volume per site, OOS p-chart, OOS by type, pipeline by stage, what moved |
| Pipeline | Batches in process by stage, the unusual values of each, batches that stand out; lead times between the dated stages |
| Patient | Scorecard and trends of the patient and starting material parameters |
| Process | The same per process day, filtered by functional type and variation source; quantities measured on several days as one profile |
| Final product | OOS per month and by type, small trends of the key quality attributes, scorecard and trends of every final product parameter |
| Materials | For one parameter: every raw material and vector lot against the lot before it, and the lot changes at which the value moved |
| Sites | OOS rate, volume and lead times per site; every parameter tested for a site difference |
| CPV | Heat map of every parameter's monthly mean against its baseline control limits; control charts (EWMA, CUSUM); the view as a PDF report with methods and provenance (`cart_dashboard/cpv_report.py`) |

The **scorecard** has one row per numerical parameter: recent and baseline
median, the shift in baseline SD, a Mann-Whitney q-value (Benjamini-Hochberg
over all parameters), recent batches beyond ±3 SD, EWMA signals, a sparkline
and a status (Shifted / Watch / Stable). Clicking a row draws the parameter's
trend plot with its statistics; *Investigate* opens it in the Investigation
tab. The calculations are in `cart_dashboard/monitor.py`, checked in
`tests/test_monitor.py`.

The tabs group the parameters by the catalogue (`catalog.xlsx`: Functional
Type, Process Day, Variation Source; `parameters` in the config) and find the OOS and date columns by name. The `monitor` section of
the config overrides the defaults; see the help page.

**Investigation tab** (why). One page; the sidebar holds the plot controls.

- **Selection bar** (top): how many batches of interest and background
  batches are selected, and how. *Edit selection* opens the batch selection
  in a pop-up; *Clear* empties both sets and opens it; *Default* brings the
  defaults back.

  Each set has a site filter, a re-manufacture filter (include / exclude /
  only), and a selection mode: single batch, manual selection, or time frame.
  The background set also has *all batches matching filters*. By default,
  batches of interest are left out of the background.

  On opening, the batches of interest are this week's batches (Monday to
  Sunday) and the background is the past year's batches (from the same day
  one year ago up to today).
- **Title**: the plotted parameter as on the y-axis (name, unit, transform).
- **Plot**, with a time-period slider under it to zoom in on a period, and notes under it; with a glassbox run open, the contribution
  charts; then the **context table**, folded.
- **Warnings and messages** (bottom, folded): warnings about the batches
  of interest, batches of a glassbox run missing from the data, duplicated ids.
- **Sidebar**:
  - *Parameter*: the parameter list can be searched by typing in it.
    *Filter by catalogue* narrows the list by the
    catalogue columns in `filter_columns` (Functional Type, Process Day and
    Variation Source in the sample config).
  - *Display*: show only one manufacturing site, pick a transform (none, log
    or logit), and switch the trend fit, the EWMA chart and the CUSUM chart
    on or off. Any combination can be shown together.
  - *Colour*: colour the points by any non-numerical parameter, and keep only
    batches in chosen categories of that column. The trend is fitted again
    on those batches.

If only one of the two sets has batches, the plot shows that set.

**Help tab**: explains every part of the dashboard. It has a table of
contents in the sidebar and a search field that keeps the sections
containing every word typed, with the words highlighted. The text is in
`docs/help.md`; its `##` and `###` headings become the sections. Settings
are kept when you switch tabs.

### Glassbox run

*Open glassbox run* in the selection bar loads the output folder of a
glassbox classification run (its `--output-dir`), either as a
browser folder upload or by typing its path. Everything is read from the
folder, nothing goes into the config: `run_manifest.json` (id column,
target, positive label, models), `<model>/predictions.csv`,
`<model>/local_explanations.csv` and, when the run had
`investigation.batches` set, `investigation/` (leave-one-out contributions,
probabilities, trust gate). The investigation is only used when
`run_manifest.json` names it and its files match the SHA-256 the manifest
recorded; model files that no longer match are flagged. Glassbox features are
dashboard parameters, by name. Contributions are on each model's own scale
(log-odds, or a probability for the decision tree), which the charts and the
table name.

The run's positive class (usually the minority class: out-of-spec batches, or
the batches of one period against another) becomes the batches of interest
and the other batches the background. A sidebar group shows the run's title and
description (glassbox `report.title` / `report.description`) and picks the
model. Between the plot and the statistics, *Feature relevance* shows the in-sample and
leave-one-out contributions across the batches of interest (both means over the same
batches: by default the ones glassbox refitted) and for one batch; clicking
a feature makes it the plotted parameter. The charts cover the batches of interest the
plot shows, after its site and category filters, and list them by the chosen
model's own probability. The context table gets the model's probability
and the plotted parameter's contributions.

The dashboard never imports glassbox; it only reads its files
(`cart_dashboard/glassbox.py`). To try it: `python scripts/make_glassbox_demo.py`
builds an ML dataset from the sample data and prints the glassbox command to
run on it; then open `data/glassbox_demo/run`.

A range slider under the plot zooms to a time period.

### Statistics

Under the plot, *Statistics* compares the plotted batches of interest with
the plotted background for the plotted parameter, in plain sentences with the numbers behind them:
medians and the Hodges–Lehmann difference, the AUC with its DeLong interval
and the Mann–Whitney test, the same comparison within calendar quarters (van
Elteren; Cochran–Mantel–Haenszel for categories), the share of batches of interest by value or
category (Wilson intervals; Fisher's exact test or a Monte Carlo chi-square),
consistency per site and year, and missing values. With a glassbox run: the
share of batches of interest per month (p-chart), a model check from the out-of-fold predictions
(sidebar), and a screen of every parameter within quarters with
Benjamini–Hochberg q-values. A test needs at least 10 batches per group. The
record downloads as CSV and PDF with its provenance (file hashes, versions,
selection). The calculations are in `cart_dashboard/stats.py`, checked in
`tests/test_stats.py`; see `docs/statistics_validation.md`.

### Plot and table

The value type decides the y-axis. Numeric and ratio values are plotted
as numbers, durations as minutes. Datetimes are shown as days from
manufacturing start, or as hour of day when at least 80% of the values are
`hh:mm[:ss]` clock times.
Categorical and `[a,b,c]` values get one row per category, in the listed
order for `[a,b,c]`. Past 30 categories the rarest are folded into
"Other", except those of the batches of interest.

Batches of interest have a thin dark blue ring around their point. When colouring, six colours
(none of them dark blue, red, pink or orange, so the rings and the trend stay visible) repeat
over the categories in the order they first appear (in the listed order
for `[a,b,c]` types), so neighbouring lots get different colours. A
category keeps its colour when others are filtered out. Past 12
categories the legend is left out; hover over a point to see its category.

Under the plot, a table puts each batch of interest in context: its
percentile among the plotted background batches, its distance from the
trend line in standard deviations of that trend segment, and whether the
EWMA or CUSUM chart signals at that batch (for categorical parameters: the
share of background batches with the same value). Click a column header
to sort, and a row to mark that batch in the plot.

## Transforms

Numerical parameters can be shown on a log or logit scale
(`cart_dashboard/transform.py`). The values are transformed before the trend,
EWMA and CUSUM are computed, and the y-axis is labelled in the original
units. Log needs values above zero. Logit needs percentages strictly between
0 and 100, or fractions strictly between 0 and 1. Values outside that range
are left out and counted under the plot.

The dashboard suggests a transform, with a button to apply it, when:

- logit: the parameter name marks it as a percentage (`%` or "percent"),
  at least 90% of the values are strictly between 0 and 100, and the median
  is at least 85 or at most 15;
- log: all values are above zero, the skewness is above 1, and a log at
  least halves it.

## EWMA and CUSUM

Both charts follow the plotted batches in manufacturing-date order
(`cart_dashboard/spc.py`), on the transformed scale when a transform is on.
The target and sigma come from the reference batches: the background batches
of the reference period picked in the sidebar; their mean, and their average
moving range divided by 1.128. Every batch, the batches of interest included,
is judged against them. Signals are raised on both sides, and the dashboard lists when each shift began (the CUSUM's
estimate) and which way.

- EWMA is drawn over the points, with control limits at ±3 sigma that widen
  to their steady-state value over the first batches. The weight of the
  newest batch is 0.2.
- CUSUM gets its own panel under the plot, sharing the date axis. It shows
  the tabular CUSUM C+ upwards and C− downwards in sigma units, with slack
  0.5 sigma, and decision intervals at ±5 sigma.

Blue diamonds mark the batches where a chart is outside its limits. The
numbers are set in the `spc` section of the config.

## Trend fit

For numerical parameters the dashboard fits a trend to all plotted batches
(`cart_dashboard/trend.py`). Two kinds of fit compete: flat segments, which
model level shifts, and sloped segments, which model trends and can also
jump at a breakpoint. The dashed lines mark the breakpoints, with their dates.

1. Points beyond 3 IQR below Q1 or above Q3 are left out of the fit and
   circled in the plot.
2. For each kind and for 0 to 10 breakpoints, dynamic programming finds the
   exact best segmentation (least squares, at least 15 batches per segment).
3. BIC = n ln(RSS/n) + k ln(n). k counts the parameters: per segment a
   level (flat) or an intercept and slope (sloped), plus one per breakpoint.
   Of the fits whose BIC is within 2 of the lowest, the one with the fewest
   parameters is shown.

The numbers are set in the `trend` section of the config.

Breakpoints are only considered between blocks of consecutive batches, at
most 2000 blocks. Up to 2000 batches that is every batch; for 20000 batches
a breakpoint can fall every 10 batches. The segment fits stay exact, and a
fit takes about a second whatever the data size.

## Code layout

```
app.py                         entry point: page style, selection bar, main view
cart_dashboard/config.py       YAML loading and parameter -> column lookup
cart_dashboard/data.py         CSV loading and normalisation
cart_dashboard/selection.py    batch selection logic (no Streamlit, unit tested)
cart_dashboard/plots.py        Plotly figure builders
cart_dashboard/trend.py        segmented trend fit
cart_dashboard/spc.py          EWMA and CUSUM
cart_dashboard/transform.py    log and logit transforms, transform suggestion
cart_dashboard/context.py      batches of interest against the background
cart_dashboard/search.py       word search for parameters and help
cart_dashboard/glassbox.py     reading a glassbox run (files only, no glassbox import)
cart_dashboard/stats.py        statistical tests and intervals (no Streamlit, checked in tests/test_stats.py)
cart_dashboard/evidence.py     the statistics section's sentences, numbers and the parameter screen
cart_dashboard/report.py       the statistics record as CSV and PDF, with provenance
cart_dashboard/views/          Streamlit views: selection bar and dialogs, statistics, feature relevance, main view, help page
docs/help.md                   the help page text
tests/                         pytest
```

Views are modules in `cart_dashboard/views/` with a `render(...)` function,
called from `app.py`. Refer to data through `cfg.col(...)` or
`cfg.group(...)`, never through raw column names.

Assumption: the CSV has one row per batch.
