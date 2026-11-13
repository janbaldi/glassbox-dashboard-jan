# Help

The dashboard compares **batches of interest** (for example this week's
batches) with **background batches** (for example everything made in the past
year) for one manufacturing parameter at a time. You pick the two sets at the
top of the page and the parameter in the sidebar; the plot shows every batch
over time, with the batches of interest marked. Under the plot, the
**Statistics** section says in plain words how the two sets differ, and the
table at the bottom tells you where each batch of interest stands. With the
results of a glassbox run open, the run's own two classes are compared (for
example out-of-spec batches against the others, or one period against
another), and the machine learning model's feature relevance is shown next to
the process data.

Use the search field above to find a topic, or the contents in the sidebar to
jump to one.

## Quick start

1. Check the **selection bar** at the top. By default it compares this
   week's batches with the batches of the past year.
2. Pick the parameter from **Parameter** in the sidebar. Type a few
   letters of its name in the list to find it.
3. Read the plot: grey points are all batches, dark blue rings are the batches of
   interest. The **Batches of interest** table at the bottom (folded; click
   its title to open it) gives each batch of interest's percentile and
   distance from the trend.
4. Switch on **Trend**, **EWMA** or **CUSUM** in the sidebar to look for
   shifts and drifts.
5. Click a row in that table to mark that batch with a star in
   the plot.
6. Read **Statistics** under the plot: the headline says whether the
   parameter differs between the two sets, and how sure that is.

For the machine learning view, click **Open glassbox run** and open the
run's results folder (see *Glassbox run*). *Statistics* explains the numbers.

## Page layout

The dashboard is one page:

- **Selection bar** (top): the two batch sets and the buttons to change them.
- **Title**: the name of the plotted parameter, as on the y-axis, with its
  unit and transform.
- **Plot**: the chosen parameter over time, with notes under it.
- **Feature relevance**: only while a glassbox run is open. The model's
  contribution charts; see *Glassbox run*.
- **Statistics**: the difference between the two sets for the plotted
  parameter, in plain words, with the numbers behind it; see *Statistics*.
- **Batches of interest**: a table with one row per batch of
  interest, folded; click its title to open it.
- **Warnings and messages** (bottom, folded).
- **Sidebar** (left): everything that changes what the plot shows, the
  **Help** button, and the name of the data and config files. With a glassbox
  run open, its **Glassbox run** group (title, model and *How good is the
  model?*) is at the top.

The sidebar can be folded away with the double arrow at its top, and dragged
wider at its right edge.

## Selecting batches

### The selection bar

The bar at the top reads, for example:

`Interest 3 · 21–27 Sep 2026   Background 725 · 24 Sep 2025 – 24 Sep 2026, minus interest`

The numbers are how many batches each set holds; the grey text says how they
were chosen: a date range, a batch id, *N picked*, or *all batches*, followed
by any site or re-manufacture filter. *Minus interest* means the batches of
interest are taken out of the background.

- **Edit selection** opens the batch selection in a pop-up.
- **Clear** empties both sets and opens the pop-up, so you can build your own
  selection from scratch.
- **Default** goes back to the default selection.
- **Open glassbox run** loads the results of a glassbox run; see
  *Glassbox run*. While a run is open this button
  reads **Close** followed by the run's folder name.

### Default selection

When the dashboard opens, and whenever you click **Default**:

- batches of interest: all batches made this week, Monday to Sunday;
- background: all batches made from the same day one year ago up to today
  (28 February when today is 29 February), without the batches of interest;
- both sets: all sites, re-manufactured batches included.

If no batch was made this week yet, the set of interest is empty and the plot
shows the background only.

### Editing the selection

The pop-up has one panel per set. Each panel has:

- **Manufacturing site**: only batches from the listed sites can be selected.
  Remove a site with its cross, add one from the list.
- **Re-manufacture** (when the data has a re-manufacture column): include
  re-manufactured batches, exclude them, or select only those.
- **Select by**: how the batches are chosen:
  - *Single batch*: pick one batch id. Type part of the id to find it. The
    list shows id, manufacturing date and site, newest first.
  - *Manual selection*: pick any number of batch ids.
  - *Time frame*: all batches with a manufacturing date in the range. Both
    dates are included.
  - *All batches matching filters* (background only): every batch allowed by
    the site and re-manufacture filters.

Under each panel a green box says how many batches are selected;
**Show selected batches** lists them. The background panel also has
**Exclude the batch(es) of interest from the background**, on by default, so
a batch is never compared with itself.

At the top of the pop-up, **Clear both** and **Default selection** do the same
as **Clear** and **Default** in the bar. Click **Done**, or close the pop-up,
to update the dashboard. The selection is kept while the pop-up is closed and
while you read this help.

When a filter change rules out batches you picked by id, they are dropped
from the pick list.

## Choosing the parameter

### Finding a parameter

Click **Parameter** and type: the list keeps the parameters whose name
matches what you typed.

### Filter by metadata

**Filter by metadata** folds open a filter per metadata column (in the sample
setup: Functional Type, Process Day and Actionable?). Only parameters with one
of the chosen values stay in the list; an empty filter means all values. The
fold-out's title says how many filters are active. Search and filters work
together.

### The parameter list

**Parameter** shows how many parameters match out of all parameters that are
in the data, for example *Parameter (12 of 619)*. Each entry shows the
parameter's name and its value type. You can also type in the list itself to
jump to a name.

Under the list, the parameter's description from the metadata file is shown,
with your search words highlighted. A long description is shortened; hover over
it to read the full text.

Parameters that are listed in the metadata file but have no column in the
data are left out.

## Display options

### Manufacturing site

Show only the batches from one site. The trend, EWMA and CUSUM are then
computed from that site's batches only. Batches of interest from other sites
are listed under **Warnings and messages** at the bottom of the page. With a
glassbox run open, the contribution charts cover that site's batches too.

### Transform

For numerical parameters, choose how the values are scaled:

- **None**: the values as they are.
- **Log**: base-10 logarithm. Useful for values that span several orders of
  magnitude or are skewed to the right, such as cell counts and
  concentrations. Only values above zero can be shown.
- **Logit**: log(p / (1 − p)) of a fraction p. Useful for percentages close
  to 0 or 100, such as viability or purity, where differences near the limit
  matter more than they look. Percentages are divided by 100 first; values of
  exactly 0 or 100 cannot be shown.

The y-axis stays labelled in the original units, and hovering a point shows
its original value. The trend, EWMA and CUSUM are computed on the transformed
values, as are the percentile and the deviation in the table. Batches whose
value cannot be transformed are counted in a note under the plot.

### Suggested transform

For numerical parameters the dashboard checks whether a transform would suit
the data better and, if so, shows a **Suggested: ...** button under
**Transform**. Hover over it for the reason; click it to apply the transform:

- **Logit** is suggested when the parameter's name marks it as a percentage
  (it contains `%` or "percent"), at least 90% of the values lie strictly
  between 0 and 100, and the median is 85 or more, or 15 or less.
- **Log** is suggested when all values are above zero, their skewness is
  above 1, and a log transform at least halves it.

The suggestion disappears once the suggested transform is chosen. It is a
hint: you can keep any transform.

### Trend, EWMA and CUSUM

Three switches add analyses to the plot. Any combination can be on at the
same time.

- **Trend** (on by default): a piecewise linear fit that finds shifts and
  changes in slope. See *Trend fit*.
- **EWMA**: an exponentially weighted moving average with control limits,
  drawn over the points. See *EWMA chart*.
- **CUSUM**: cumulative sums of deviations, in a panel under the plot. See
  *CUSUM chart*.

They only apply to numerical parameters; for other parameters a note says so.

While EWMA or CUSUM is on, **Reference period (normal batches)** picks the
dates the charts take "normal" from. All dates by default.

## Monitoring

What the plot adds to watch a parameter over time:

- **EWMA and CUSUM measure normal from the background**: target and spread
  come from the background batches of the **reference period**; every batch,
  the batches of interest included, is judged against them. So the shifts you
  are looking for do not widen the limits. The reference period is shaded on
  the plot when it is shorter than the plotted period. Pick a stable period
  you trust.
- **Only the side that matters**: when the parameter has a direction of
  concern (low viability is a problem, high viability is not), EWMA and
  CUSUM only signal on that side, and the CUSUM draws only that decision
  line. This halves the false alarms.
- **When and which way**: a line under the plot lists the signals, newest
  first, for example *CUSUM: downward shift from 2025-06-27 (signal
  2025-07-03), 4 batches signalling*. For the CUSUM, the start is its
  estimate of when the shift began: the batch after the sum was last zero,
  often days or weeks before the signal.

To look at one site, pick it under **Manufacturing site**: the trend and the
reference batches are then that site's.

### Direction of concern

The column *Direction of concern* of the parameter metadata file
(`parameters.csv`) says which side of a parameter matters: `low`, `high` or
`both` (empty means both). EWMA and CUSUM then only signal on that side.

## Colouring points

### Colour points by

Colour the points by any non-numerical parameter (categorical or ordered),
for example a reagent lot or an equipment id. Six colours are used and repeat
(none is dark blue, red, pink or orange, so the rings and the trend stay visible)
in the order the categories first appear over time, so lots that follow each
other get different colours. For ordered types the listed order is used.
Batches without a value get a light grey.

With up to 12 categories each one has its own legend entry. With more, the
legend is left out and a note says so: hover over a point to see its
category.

### Categories to show

After choosing a colour, keep only the batches in some of its categories.
Empty means all categories. The trend, EWMA and CUSUM are computed again from
the remaining batches, and a category keeps its colour when others are
filtered out. Batches of interest that are filtered out are listed under
**Warnings and messages** at the bottom of the page.

## Reading the plot

### Axes and value types

The x-axis is the manufacturing date. The y-axis depends on the parameter's
value type in the metadata file:

- *numeric* and *ratio*: the value. A ratio written as `a:b` is plotted as
  a divided by b.
- *duration*: the value in minutes.
- *datetime*: days from the batch's manufacturing start, or the hour of the
  day when the values are clock times such as `14:30` or `14:30:15` (when at
  least 80% of them are; the others then have no value). A clock time among
  dates has no date, so it has no value either.
- *categorical*: one row per category, the most frequent at the top.
- ordered, written as `[low,medium,high]`: one row per category in that
  order.

With more than 30 categories the rarest are folded into *Other*, except the
categories of the batches of interest.

### Markers and lines

- **Grey points** (or coloured, see *Colouring points*): all plotted batches.
- **Dark blue rings**: the batches of interest, a thin ring around the point.
- **Star with label**: the batch picked in the **Batches of interest** table.
- **Orange lines**: the trend fit, one line per segment.
- **Orange dashed vertical lines**: trend breakpoints, labelled with their
  date.
- **Orange crosses**: outliers left out of the trend fit.
- **Light blue shading**: the reference period of EWMA and CUSUM, when it is
  shorter than the plotted period.
- **Dark line with dotted lines**: the EWMA and its control limits.
- **Dark blue diamonds**: where the EWMA (on the plot) or the CUSUM (in the panel
  below) is outside its limits, on the side that matters.

### Working with the plot

- Hover over a point for its batch id, manufacturing date, value, site and
  colour category.
- Drag the handles of the **time-period slider** under the plot to zoom
  to a period; drag the shaded window to move it along. The slider shows
  the whole date range.
- Drag over an area to zoom in; double-click to zoom out again.
- Click a legend entry to hide or show it; double-click one to show only that
  entry.
- The toolbar at the top right of the plot (visible when hovering) can save
  the plot as a PNG, switch between zoom and pan, and reset the axes. The
  expand icon shows the plot full screen.

### Notes and warnings

A single line under the plot notes what was left out or how it was computed,
for example `22 without value or date · trend (flat segments) breaks: none ·
EWMA/CUSUM normal from 1321 background batches made 2024-01-03 to 2026-08-31:
target 66.46, σ 9.516, signals on the low side only`: batches without a value
or date, values the transform cannot handle, the trend model and breakpoint
dates, and where EWMA and CUSUM take normal from. With EWMA or CUSUM on, a
second line lists the signals, newest first (see *Monitoring*).

Warnings, such as batches of interest not made at the chosen site, filtered
out by category, or without a value, batches of a glassbox run missing from
the data, or duplicated batch ids, are collected in **Warnings and messages**
at the bottom of the page. It is folded; its title says how many there are.

## Batches of interest table

The table **Batches of interest**, near the bottom of the page, has one row per plotted batch of
interest. It is folded: click its title to open it. It has:

- batch id, manufacturing date and site;
- **Value**: the value in original units;
- **Background percentile**: share of the plotted background batches with a
  lower value, ties counting half;
- **Deviation from trend (SD)**: distance from the trend line at the batch's
  date, in standard deviations of the residuals of that trend segment. Values
  beyond ±2 are unusual, beyond ±3 rare;
- **Trend segment**: which segment of the trend fit the batch falls in;
- **EWMA signal** and **CUSUM signal**: ticked when that chart is outside its
  limits at this batch;
- for non-numerical parameters: **Background with same value (%)**;
- while a glassbox run is open: **Model probability (out-of-fold)**, and for a
  parameter the model uses, its **In-sample contribution** and
  **Leave-one-out contribution** for that batch, with the model's scale in
  the column title.

Columns only appear when they apply (for example the deviation needs the
trend). Click a column header to sort. Click a row to mark that batch with a
star in the plot; click it again to remove the mark. The mark stays with that
batch when you change the parameter or the selection; it only shows while the
batch is in the table.

## Glassbox run

Glassbox is the machine learning pipeline that looks for what sets one class
of batches apart from the rest: batches that went out of spec, or the batches
of one period against another. The dashboard can open the results of a
glassbox classification run and show what the models found next to the
process data.

### Opening a glassbox run

Click **Open glassbox run** in the selection bar. Either:

- **Browse for the results folder**: pick the folder glassbox wrote to (its
  `--output-dir`, the one holding `run_manifest.json`). Only the CSV and JSON
  files are read; the browser asks to confirm the upload;
- or type the folder's path in **Or type the folder's path on this computer**,
  when the dashboard runs on your own computer. A model folder inside the run
  works too.

Then click **Open**. Everything is read from the folder: the id column, the
target, which label is the class of interest, the models and their results.
Nothing is written to the config.

The leave-one-out results (the `investigation/` folder) are only used when
`run_manifest.json` names them and they still match the checksums (SHA-256)
the manifest recorded. A folder left by an earlier run into the same output
folder, or files edited afterwards, are left out, and **Warnings and
messages** says so. Model files that no longer match are shown but flagged
there too.

The batches of interest become the run's positive class (usually the minority
class of the ML dataset) and the background its other batches.
Batches of the run that are not in the dashboard data are listed under
**Warnings and messages** at the bottom of the page. **Close** (followed by
the run's name) closes the run and goes back to the default selection.

### Selection modes of a glassbox run

While a run is open, the selection pop-up offers one more mode per set:
**Glassbox run: interest** for the batches of interest and **Glassbox run:
background** for the background. Opening a run picks both. To compare the
run's batches of interest with every other batch, including batches that were
not in the ML dataset (for example newer ones), pick **All batches matching
filters** for the background and keep **Exclude the batch(es) of interest from
the background** on.

The site and re-manufacture filters still apply. You can also pick a few of the
run's batches by hand (**Manual selection**): the contribution charts then cover
only those.

### Model

The **Glassbox run** group at the top of the sidebar shows the run's title and
description (`report.title` and `report.description` in the glassbox config;
the folder name when there is no title). A long description is shortened;
hover over it to read it all. Under them, **Model** picks the model family when
the run trained more than one. The one with the highest PR-AUC is picked
first. Under it: how many batches are of interest and the PR-AUC a model that
learned nothing would score (the share of batches of interest). If no model
beats it, the sidebar and **Warnings and messages** say so:
the contributions then describe the model rather than the process. Fold open
**How good is the model?** for how well the model tells the batches of
interest from the background; see *Statistics*.

### Feature relevance

The section **Feature relevance**, between the plot and the statistics, has
two charts. A contribution is how far a feature pushed a batch's predicted
probability of being of interest up (to the right) or down (to the left), on
the model's own scale: log-odds for
EBM, XGBoost and the GAM, a probability for the decision tree. The scale is
named above the charts and on their axes; numbers from different models cannot
be compared. Every batch gets two readings, as in glassbox's investigation
report:

- **In-sample**: the final model, fitted on every batch including this one.
  A flexible model can partly memorise a batch, so treat it as a hypothesis.
- **Leave-one-out**: the same model refitted without this batch, then asked
  to explain it. A driver it reproduces is evidence. Glassbox only does this
  for the highest-probability batches (its `max_detail` setting); the others
  have in-sample contributions only.

**Drivers across the batches of interest** (left): the 15 features with the
largest mean |in-sample contribution| over the batches the chart covers. Grey
bars are the mean in-sample contribution, blue bars the mean leave-one-out
contribution, and the dots each batch's own in-sample contribution: a feature
with all dots on one side drives most of them; one far dot is one batch.

Both means are always over the same batches (hover a bar to see how many).
When only some of the run's batches of interest have a leave-one-out refit, a
switch above the chart picks what to average over:

- **N refitted batches**, the default: in-sample and leave-one-out side by
  side, over the batches glassbox refitted;
- **all N**: every batch of interest of the run, in-sample only.

A leave-one-out mean over the refitted batches next to an in-sample mean over
all of them would compare the highest-probability batches with every batch, and
the blue bar would come out larger for that reason alone.

The charts cover the run's batches of interest the plot shows: the
**Manufacturing site** and **Categories to show** filters in the sidebar apply
to them too, and the text above the charts says how many the filters leave out.

**Batch** (right): pick a batch, highest out-of-fold probability (of the chosen
model) first, or click
its row in the **Batches of interest** table. The line above the chart gives its
out-of-fold, in-sample and leave-one-out probabilities and the decision
threshold. The chart shows its 12 largest drivers, in-sample and
leave-one-out side by side. Hatched bars mark a value glassbox imputed; a dark
blue ✕ marks a driver the leave-one-out refit does not reproduce (pushes the
other way). Features carrying at most 1% of the batch's total in-sample
contribution are not drivers, so they never get one. Hover a bar for the
batch's value, the typical value in the background, its percentile and z-score.

### Clicking a feature

Click a feature's name, bar or dot in either chart to plot that feature: it becomes the
**Parameter** in the sidebar, and the search text or metadata filters are
cleared if they would hide it. The plotted parameter is in bold on a light blue
band in both charts. Greyed-out names are features the dashboard does not
have as a parameter; clicking them shows a message instead.

## Statistics

The **Statistics** section, under the plot, answers three questions about the
plotted parameter in plain words:

1. Is it different in the batches of interest than in the background?
2. How big is the difference, and how sure can we be?
3. Could something else explain it, such as a change over time?

It is written to be read by people who do not work with statistics every
day. The sentences come first; every number behind them is one click away in
*Numbers and methods*, and the whole record can be downloaded for the
investigation file.

### Which batches are compared

The section compares the **plotted batches of interest** with the **plotted
background batches**, for the parameter in the plot. The **Manufacturing
site** and **Categories to show** filters in the sidebar apply, so the
statistics always describe the batches you see.

It speaks of **batches of interest**, **background batches** and the **share
of batches of interest**. When the two groups are a glassbox run's own (every
batch of interest is of the run's class of interest and every background batch
of its other class, as after opening a run), the tab *Share of batches of
interest per month* appears and the model's point of view is added.

A comparison needs at least **10 batches with a value in each group**. With
fewer (for example this week's three batches against a year) the section
says so and does not test anything: with so few batches, any "finding" would
be mostly chance. That is why the statistics are most useful with a glassbox
run or another comparison where both groups are large.

### Tabs and buttons

- **This parameter**: the evidence for the plotted parameter, in sentences
  and two small charts. Explained under *Reading "This parameter"*.
- **Share of batches of interest per month** (a glassbox run's own groups
  only): is the share stable over time, or were some months worse than chance explains?
- **All parameters**: the same test for every parameter at once, to find
  the ones worth a closer look.
- **Numbers and methods**: a table of every number with its interval,
  p-value and group sizes, the list of methods used, and the points to read
  with care.
- **CSV** and **PDF** (bottom of the section): download the record. See
  *Downloading the record*.

### The key ideas in one page

**Median.** The middle value: half the batches are below it, half above.
Unlike the average, a few extreme batches do not pull it around.

**95% interval** (written "95% CI"). Every number computed from batches is
an estimate: with other batches it would come out a little different. The
interval is the range of values that are consistent with the data. A narrow
interval means a precise estimate; a wide one means few batches or much
variation. When the interval of a difference does not include zero (or the
interval of an AUC does not include 0.5), the difference is, as a rule,
clear.

**p-value.** How surprising the observed difference would be if there were
really no difference between the groups. A small p-value (below 0.05, one
in twenty) means the difference is unlikely to be chance alone; the
dashboard then calls it *clear* and says *higher* or *lower*. A large
p-value means the data do not show a difference; it does not prove there is
none. "p < 0.001" means less than one in a thousand. A p-value says nothing
about how *big* a difference is: with thousands of batches a tiny difference
can have a small p-value. Always read it together with the size (the typical
difference, the AUC or the rates).

**Typical difference.** How much higher or lower the value of a batch of
interest typically is than that of a background batch, in the parameter's
own units (statisticians call it the Hodges–Lehmann estimate: the median of
the differences between every batch of interest and every background batch).
"+1.39 (95% CI +1.18 to +1.6)" means batches of interest are typically about 1.4
units higher, and with 95% confidence somewhere between 1.2 and 1.6.

**AUC** (area under the curve). The chance that a randomly picked batch of
interest has a higher value than a randomly picked background batch.

- 0.5: no difference, a coin toss;
- above 0.5: batches of interest tend to be higher; 1.0 would mean every
  one of them is higher than every background batch;
- below 0.5: they tend to be lower; 0.0 would be complete separation the
  other way.

As a rough guide, an AUC of 0.6 (or 0.4) is a modest difference, 0.7 (or 0.3)
a clear one, and 0.8 (or 0.2) or beyond a strong one that you would see by
eye in the plot. The AUC does not depend on the units, so it can be compared
between parameters, as the screen does. Its p-value is from the Mann–Whitney
test, which asks the same question.

**Share of batches of interest.** For example "13 of 198
(6.6%, 95% CI 4.0%–11%)". The interval is a Wilson interval, which stays
sensible for small counts and for rates close to 0% or 100%.

**Comparing within quarters.** Many things drift over time: a parameter's
typical value, and also the share of batches of interest. If both happen to
change over the same period, the parameter looks different in the batches of
interest even when it has nothing to do with them. To rule that out, the
dashboard also compares batches of interest with background batches **made in
the same calendar quarter** only, and then
combines the quarters (van Elteren test for numbers,
Cochran–Mantel–Haenszel test for categories). A difference that survives
this comparison cannot be explained by slow changes over time.

**q-value.** When hundreds of parameters are tested, some look different by
chance alone: at p < 0.05, about 1 in 20 unrelated parameters would. The
q-value corrects for this (Benjamini–Hochberg). Among the parameters with
q below 0.05, you can expect about 1 in 20 to be a false lead, however many
parameters were tested.

**Consistency.** A real process effect usually shows at every site and in
every year. The dashboard repeats the comparison per site and per year and
says whether the difference points the same way everywhere. A difference
that exists at one site only points to something local to that site.

### Reading "This parameter"

The first line is the **headline**:

- *"X is higher in batches of interest."* or *"… lower …"*: a clear difference
  (p below 0.05);
- *"No clear difference in X between batches of interest and background batches."*: the
  data do not show one;
- *"Too few batches to compare X …"*: fewer than 10 batches with a value in
  one of the groups.

Under it, for a **numerical parameter**, as far as they apply:

- **Median … typical difference …**: the medians of both groups, and the
  typical difference with its interval.
- **Comparing a random batch of interest with a random background batch …**:
  the AUC in words ("the batch of interest has the higher value 77% of the
  time"), with its
  interval, the p-value and the number of batches in each group.
- **Comparing only batches made in the same quarter …**: the check for
  changes over time. It ends in one of:
  - *still higher / still lower*: the difference holds within quarters;
  - *the difference is no longer clear; it may come from changes over
    time*: be careful, the parameter may only drift along with the share of batches of interest;
  - *the other way round*: within quarters the difference reverses, a strong
    sign that the overall difference is a time effect;
  - *a difference shows*: no clear overall difference, but there is one
    within quarters (a time trend was hiding it).
- **Share of batches of interest: x% in the lowest values (…), y% in the
  highest (…)**: the
  batches are split into four groups of about equal size by their value
  (quarters of the batches, lowest values first), and the share is given
  for the lowest and the highest group. This is often the easiest number to
  act on: "above 9 minutes, one batch in five is of interest".
- **Consistent: higher in batches of interest at all 3 sites and in all 3 years.**
  Or *Not consistent everywhere*, naming the sites or years where it goes
  the other way. Sites and years with fewer than 10 batches in a group are
  not judged.
- **Missing more often in …**: only shown when one group clearly has more
  batches without a value (Fisher's exact test). Worth checking how the data
  were recorded: a missing value can itself be a sign of a problem.
- **Model (…)**: with a glassbox run, how the model uses the parameter for
  these batches of interest: in how many it pushes the probability up, in how many it is the
  #1 driver and a top-3 driver, and in how many of the batches that were
  refitted without themselves (leave-one-out) the refit reproduces it. Or
  *not one of its features*.

The two charts:

- **Values** (left): a box per group. The box holds the middle half of the
  batches, the line in it is the median, and the whiskers reach the bulk of
  the other batches; dots are unusual values. Boxes that barely overlap
  mean a large difference.
- **Share by value** (right): the share of batches of interest in each of the four value
  groups, with its interval as an error bar. The dashed line is the rate
  over all batches. A staircase going up (or down) shows a dose–response:
  the higher the value, the more batches of interest.

For a **categorical parameter** (a site, a lot, an equipment id):

- the headline says whether the share of batches of interest **differs between the
  categories** (Fisher's exact test for two categories; for more, a
  chi-square test whose p-value is found by simulating 20,000 tables, which
  stays correct for small counts);
- the category with the **highest** and the **lowest** share, and the
  rate over all batches;
- the same question **within quarters**, as for numbers;
- a chart of the share per category with intervals, the dashed line
  being the rate over all batches. A category whose interval lies wholly to
  the right of the dashed line has clearly more batches of interest than average.

Categories with fewer than 10 batches are pooled as **"Other"**: a rate
from 3 batches says little on its own.

### Share of batches of interest per month

Only for a glassbox run's own groups. The chart shows the share of batches of
interest of each month
(dark line) against the overall rate (solid grey line) and two dotted
**control limits**. The limits show how far a month's rate can stray from
the overall rate by chance alone, given how many batches it had: they are
wider for months with few batches. This is a **p-chart**, a standard
statistical process control chart, with limits at 3 standard errors.

A month **above the upper limit** is ringed in dark blue and named in the text,
for example "Jan 2024: 12 of 44 (27%, limit 22%)": that month had more batches
of interest than chance explains, so look for what was different then (a lot, a
change, a site). Months with fewer than 10 batches are never flagged. A
month below the lower limit is unusually good. When no month is flagged, no
single month stands out; the rate can still drift slowly, which the dark
line shows.

### All parameters

Click **Screen all N parameters** to test every parameter at once. It takes
some seconds; the result is kept until the plotted batches change, when the
button comes back. Each parameter is tested **within quarters** (see above),
so parameters that merely drift over time drop out, and the list is sorted
by q-value, strongest evidence first.

The table shows the parameters with q below 0.05, and at least the first 15;
**Show all** lists every parameter tested. Its columns:

- **Parameter**.
- **Difference (all batches)**: for numbers, the AUC with its interval and
  *higher* or *lower*; for categories, the category with the highest
  share against the rate over all batches.
- **Within quarters**: the AUC when comparing only batches made in the same
  quarter (for categories, see q).
- **q**: the q-value of the within-quarter test. Below 0.05: a finding.
- **Model feature**: *yes (#3)* when the glassbox model uses the parameter,
  with its rank among the model's features.
- **Moves with**: for a finding the model does not use, the model feature it
  rises and falls with most (Spearman correlation ρ, from −1 to +1). A
  parameter that moves closely with a model feature (ρ near ±1) probably
  tells the same story; one that moves with none may be something the model
  missed.

The sentence above the table says how many parameters differ with
q < 0.05. **Click a row** to plot that parameter; the evidence for it then
appears in *This parameter*.

The screen is **exploratory**: a list of leads to check with process
knowledge, not a list of causes. A parameter can be a finding because it is
a consequence of what sets the batches of interest apart, or because it travels with the real cause.

### Numbers and methods

A table of every number behind the sentences, one per row:

- **section**: which part it belongs to (parameter, within quarters,
  consistency, missing values, model, over time, model check);
- **statistic**: what was computed, for example *AUC, site SITE-A*;
- **estimate**, **ci_low**, **ci_high**: the value and its 95% interval;
- **p** and **q**: the p-value and, in the screen, the q-value;
- **n**: the number of batches in each group;
- **note**: counts such as "48 of 307", and remarks.

Under it: every method used, in one line each, and the points to read with
care. Nothing in the sentences is computed differently from this table.

### How good is the model?

In the sidebar, under **Model**, while a glassbox run is open (fold it
open). It tells how well the model tells the batches of interest from the background, from the
run's **out-of-fold** predictions: each batch was scored by a version of the
model that never saw that batch, as it would score a new batch.

- **Flags x of the N batches of interest … and y of the M background
  batches**: at the model's decision threshold, how many batches of interest
  it catches, and how many background batches it raises a false alarm for. Both with intervals.
- **The 10% highest-probability batches contain x of the N batches of
  interest … z times what chance would give**: if you checked only the tenth
  of the batches the model scores highest, how many of the batches of
  interest you would find. Chance
  alone would find 10% of them; the multiple ("lift") says how much better
  the model does.
- **PR-AUC**: a single score of how well the model ranks batches of interest
  above background ones, from their share up to 1. A model that learned
  nothing scores about the share of batches of interest, which is given next
  to it.

These numbers are somewhat optimistic: glassbox chose the model's features
and settings with every batch in view. A model that barely beats the
baseline cannot be trusted to explain anything; the sidebar then warns.

### Downloading the record

**CSV** and **PDF**, at the bottom of the section, download the statistics
as a record for the investigation file.

- **CSV**: every number (the same table as *Numbers and methods*, plus the
  screen's results for every parameter once the screen has been run, and
  the model check), one row each, with the method and notes. It opens in a
  spreadsheet program.
- **PDF**: the headline and sentences, the charts, the share of batches of interest per month,
  the model check, the 25 strongest parameters of the screen, all numbers,
  the methods, the points to read with care, and the provenance.

Both carry the **provenance**, so the result can be traced and repeated:

- when it was made, and the version of the dashboard (git commit, with a
  note when it had uncommitted changes);
- the data file, parameter list and config file, each with its SHA-256
  checksum (a fingerprint: any change to the file changes it);
- the glassbox run, the checksum of its `run_manifest.json`, and glassbox's
  own record of its version and data;
- the model, the selection of both batch sets, the plot filters, the number
  of batches compared and the parameter;
- the settings (at least 10 batches per group; 20,000 simulated tables with
  a fixed seed, so a p-value comes out the same every time) and the versions
  of the software used.

### Reading the statistics with care

- **Association, not cause.** A parameter that differs between batches of
  interest and background batches may cause the difference, be caused by it, or travel along
  with the real cause. Statistics narrow the search; process knowledge and
  experiments confirm the cause.
- **Time is ruled out, other factors are not.** Comparing within quarters
  removes slow changes over time. It does not remove other differences, such
  as site, material lots or operators. Use **Manufacturing site** or
  **Categories to show** to look within one of them.
- **Batches are treated as independent.** Batches that share a donor, a
  material lot or a run are not, and then the intervals are too narrow.
- **Picked because it looked different.** A parameter chosen because the
  plot or the model pointed at it tends to look more convincing than it is.
  The screen's q-values allow for testing every parameter; the p-values of a
  single parameter do not.
- **"No clear difference" is not "no difference".** With few batches, a real
  but small difference can go unseen. Look at the interval: a wide one means
  the data cannot tell.
- **The filters change the batches.** The statistics describe only the
  plotted batches; a result for one site is not a result for all sites.

## Trend fit

The trend fit looks for level shifts and changes in slope over time, over
all plotted batches.

1. Points more than 3 interquartile ranges below the first quartile or above
   the third quartile are left out as outliers (orange crosses).
2. Two kinds of fit compete: **flat segments**, a constant level per segment,
   which model shifts; and **sloped segments**, a straight line per segment,
   which model drifts and can also jump at a breakpoint.
3. For each kind and for 0 up to 10 breakpoints, the best segmentation is
   found exactly (least squares, at least 15 batches per segment).
4. The fits are compared with the Bayesian information criterion (BIC), which
   rewards a good fit but penalises every extra parameter. Of the fits whose
   BIC is within 2 of the lowest, the simplest is shown.

With many batches, breakpoints are only tried between blocks of consecutive
batches (at most 2000 blocks; with 20,000 batches, every 10 batches). The fit
within each segment stays exact.

The numbers above are defaults, set in the `trend` section of the config
file.

## EWMA chart

The exponentially weighted moving average (EWMA) smooths the values in
manufacturing-date order, giving the newest batch a weight of 0.2 and the
previous average the rest. It reacts to small, lasting shifts that single
points do not show.

- **Target and sigma** come from the **reference batches**: the background
  batches of the reference period picked in the sidebar. The target is their mean;
  sigma is their average moving range (the mean absolute difference between
  consecutive batches) divided by 1.128, the usual estimate for individual
  values. With fewer than 3 reference batches, the first 100 plotted batches
  are used instead, and the note under the plot says so.
- **Control limits** lie at ±3 sigma, scaled for the averaging. They start
  narrow and widen to their final value over the first batches.
- A **signal** (dark blue diamond) is a batch where the EWMA is outside the limits,
  on the side that matters (the parameter's direction of concern).

Every plotted batch, the batches of interest included, is judged against the reference
batches. The weight and the limits are set in the `spc` section of the config
file.

## CUSUM chart

The tabular CUSUM adds up deviations from the target (the same target and
sigma as the EWMA), in sigma units, in manufacturing-date order:

- **C+** (line going up) adds deviations above target, minus a slack of 0.5
  sigma, and never goes below zero. It grows when values stay high.
- **C−** (line going down, drawn negative) does the same for values below
  target.
- A **signal** (dark blue diamond) is a batch where either sum passes the decision
  interval of 5 sigma (the dark blue dashed lines), on the side that matters.

The point where a line leaves zero and keeps climbing shows when a shift
started; the signal line under the plot names that date. The CUSUM is not reset after a signal, so a lasting shift keeps
signalling. The slack and decision interval are set in the `spc` section of
the config file.

## Configuration

### Choosing the config file

The dashboard reads its settings from a YAML file, in this order:

1. the file named in the `DASHBOARD_CONFIG` environment variable;
2. `config/config.local.yaml`, if it exists (not in version control, for
   your real data);
3. `config/config.yaml`, which points at the synthetic sample data.

The file in use is named at the bottom of the sidebar. Changes to the config,
data or metadata files are picked up the next time the page updates.

### Sections of the config file

- `data`: the path of the batch CSV (a `.csv.gz` works too), options for
  reading it, and how to read the manufacturing dates (`date_format`,
  `dayfirst`). Without a `date_format`, dates written in different ways in
  one column are all read; dates that cannot be read are listed under
  **Warnings and messages**, and those batches have no date.
- `columns`: which column of the data holds each field the dashboard needs.
  Batch id and manufacturing date are required; site and re-manufacture are
  optional, and their filters disappear when left out.
- `column_groups`: fields that offer a choice of columns.
- `remanufacture.true_values`: the values that mark a batch as
  re-manufactured, such as Y or Yes.
- `parameter_metadata`: the metadata CSV with one row per parameter, and
  which of its columns hold the name (`name_column`), value type
  (`type_column`), description (`description_column`), the metadata
  filters (`filter_columns`) and the direction of concern
  (`limit_columns.direction`, see *Direction of concern*).
- `trend`: the trend fit settings (see *Trend fit*).
- `spc`: the EWMA and CUSUM settings: `lam`, `L`, `k` and `h` (see *EWMA
  chart* and *CUSUM chart*), and `baseline`, the number of first batches
  used only when there are too few reference batches.

### Data requirements

The data has one row per batch. A batch id that appears more than once is
reported under **Warnings and messages**. Values that cannot be read as the parameter's type
count as missing and are not plotted.

## Troubleshooting

### The plot shows only grey points

There are no batches of interest in the plot. With the default selection this
happens when no batch was made this week yet. Use **Edit selection** to pick
other batches of interest.

### "No batches selected"

Both sets are empty, for example after **Clear**. Use **Edit selection** or
**Default**.

### A batch of interest is missing from the plot

Open **Warnings and messages** at the bottom of the page: it may have no value for this
parameter, be from another site than the one chosen, or be outside the chosen
colour categories.

### Logit is not applied

Logit needs percentages between 0 and 100 or fractions between 0 and 1. For
other values a warning under **Transform** says so and the values are shown
unchanged.

### The parameter I want is not in the list

Clear the metadata filters. A parameter only
appears when it is in the metadata file and has a column in the data.

### The statistics say "Too few batches"

A test needs at least 10 batches with a value in each group. With the default
selection (this week's batches) that is rarely the case. Pick a longer time
frame for the batches of interest, or open a glassbox run.

### The screen button is back

The screen is kept for the batches it was run on. After a change of the
selection, the site or the category filter, the plotted batches are different
and the screen has to be run again.

### The page looks different (fonts, colours)

The theme is read from `.streamlit/config.toml`. Start the dashboard from
the project folder with `streamlit run app.py`.
