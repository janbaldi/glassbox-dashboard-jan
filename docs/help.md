# Help

The dashboard follows CAR-T manufacturing from apheresis to infusion. It has
two halves, as tabs along the top:

- The **monitoring tabs** answer *where are we?* They compare the newest
  batches with the ones before them, for every parameter, and are calculated
  live from the data.
- The **Investigation tab** answers *why?* It compares batches you choose
  with a background, one parameter at a time, and can show what a machine
  learning model (a glassbox run) found.

This page explains every part. Search it with the field above, or jump to a
topic with the contents in the sidebar. The order is: getting started, the
monitoring tabs, the Investigation tab, the statistics in plain words, the
charts, configuration, and troubleshooting.

## Getting started

### The tabs at a glance

| Tab | The question it answers |
| --- | --- |
| **Overview** | How is manufacturing doing right now, and what changed? |
| **Pipeline** | Which batches are in process, does anything stand out in them, and how long does each step take? |
| **Patient** | Did the patients or the starting material change? |
| **Process** | Did a manufacturing step change, and on which day? |
| **Final product** | Are the quality attributes and the OOS rate stable? |
| **Materials** | Did a parameter move when a raw material or vector lot changed? |
| **Sites** | Do the manufacturing sites differ? |
| **CPV** | Is each parameter still in control? (continued process verification, with a PDF report) |
| **Investigation** | Why are these batches different from the others? |
| **Help** | This page. |

### A first look

1. Open **Overview**. The tiles give the number of batches started and in
   process, the OOS rate and how many parameters shifted; **What moved** at
   the bottom lists the parameters that changed most.
2. Check the sidebar: **Period**, **Recent window** and **Baseline** decide
   which batches are compared (see *Recent window and baseline*). The line
   under the page title says which batches are in each.
3. Open **Process**, **Patient** or **Final product** and click a row in the
   scorecard to see that parameter's trend plot.
4. Click **Investigate** next to a plot to take the parameter to the
   **Investigation** tab, where you can choose the batches yourself, see the
   full statistics, and open a glassbox run.

### Moving between tabs

Every setting is kept when you switch tabs: the sidebar choices, the row you
clicked, the batch selection of the Investigation tab. The monitoring tabs
share one sidebar; the Investigation tab has its own.

The **Investigate** buttons on the monitoring tabs open the Investigation tab
with the selection already made:

- next to a parameter: that parameter, with the recent window as the batches
  of interest and the baseline as the background;
- next to a batch on the Pipeline tab: that batch as the batch of interest,
  against the past year, on its most unusual parameter;
- on the Materials tab: the parameter, with the points coloured by the
  material's lots.

The sidebar can be folded away with the double arrow at its top, and dragged
wider at its right edge.

## Monitoring · How it works

### The sidebar

The monitoring tabs share these choices:

- **Period**: the manufacturing start dates the tabs look at: the last 6, 12
  or 24 months, all data, or **Custom** dates.
- **Recent window**: the newest 30, 60, 90 or 180 days of the period.
- **Baseline**: what the recent window is compared with: **Rest of the
  period** or **Fixed dates** (see *Fixed baseline*).
- **Manufacturing sites**: keep only some sites. Empty means all sites.
- **Re-manufactured batches**: include them, exclude them, or show only
  them (when the data has a re-manufacture column).

At the bottom: the data's last date (*Data as of*), the number of batches,
and the data and config files in use.

### Recent window and baseline

Every monitoring tab splits the batches in two by manufacturing start date:

- the **recent window**: the last 30 to 180 days of the period;
- the **baseline**: by default the rest of the period, before the recent
  window.

All statistics on the monitoring tabs compare the recent window with the
baseline. The line under each page title names both, for example *Recent:
191 batches started 2026-06-04 to 2026-09-01 · baseline: 580 batches from
2025-09-02*.

A baseline should be a time you trust. When the baseline itself contains a
shift, the comparison is with the average of before and after it, and
control limits come out too wide. Use a fixed baseline in that case.

### Fixed baseline

**Baseline** in the sidebar has two choices:

- **Rest of the period** (the default): everything in the period before the
  recent window. It moves along as new data comes in.
- **Fixed dates**: one date range you pick under **Baseline dates**,
  wherever it lies, for example the months after the last process change.
  It stays the same from month to month, so the scorecard, the control
  limits on the CPV tab and the CPV report keep one reference. Days of the
  recent window are never part of it.

With a fixed baseline before the period, the plots show the baseline batches
and the period, with the gap between them. The config can set the fixed
baseline the dashboard opens on (`monitor.baseline`, see *Sections of the
config file*).

### Data as of

The period ends at the **data's last date**: the latest date recorded in the
data (never later than today). It is shown at the bottom of the sidebar. The
dashboard shows the data as it was pulled: with a file from last week, "the
last 90 days" are the 90 days before that file's last date.

### The scorecard

The Patient, Process and Final product tabs list their numerical parameters
in a scorecard: one row per parameter, the most changed first.

| Column | Meaning |
| --- | --- |
| **Status** | The row summed up; see *Status*. |
| **Process day** | The parameter's process day in the catalogue. |
| **Recent**, **Baseline** | The median of each group of batches. |
| **Shift (SD)** | Recent median minus baseline median, in baseline standard deviations (see *Standard deviation (SD)*). +1 means the typical recent batch sits one SD above the typical baseline batch. |
| **q** | Is the difference more than chance? The p-value of recent against baseline (Mann-Whitney test), corrected for testing every parameter at once (see *q-value*). Below 0.05: unlikely to be chance alone. |
| **Beyond ±3 SD** | Recent batches further than 3 baseline SD from the baseline median: single unusual batches. |
| **EWMA signals** | Recent batches at which the EWMA chart is outside its limits (see *EWMA chart*), with normal taken from the baseline. |
| **Trend** | The monthly medians over the period, as a small line. |
| **n recent** | Recent batches with a value. |

The q-value is corrected over all numerical parameters of the data, so a
parameter has the same q and the same status on every tab.

**Only shifted or on watch** shortens the list. Click a column header to
sort; the search and download icons appear when hovering the table.

### Status

| Status | When |
| --- | --- |
| **▲ Shifted up**, **▼ Shifted down** | The recent median differs from the baseline (q below 0.05) by at least 0.5 SD. |
| **◆ Watch** | Weaker evidence, any of: a smaller difference that is still unlikely to be chance (q below 0.05, less than 0.5 SD); the EWMA outside its limits at the latest batch; or more recent batches beyond ±3 SD than chance gives (at least 2, and over 2% of the recent batches). |
| **Stable** | None of these. |
| **Too few batches** | Fewer than 10 values in the recent window or in the baseline: nothing is tested. |

A shift is a change, not a verdict. Whether it matters depends on the
parameter and its direction; the status says where to look.

### A parameter's trend and statistics

Click a row of a scorecard. Under the table:

- the parameter's name with its process day, functional type and variation
  source;
- the **trend plot**: every batch of the period by manufacturing date, the
  recent window shaded in light blue, with a time-period slider under it.
  The switches above it add the **Trend fit** (on by default), the **EWMA**
  and the **CUSUM** (see *Charts and methods*; normal comes from the
  baseline), and **Colour by site**. The plot works like the one on the
  Investigation tab (see *Working with the plot*);
- the **comparison in sentences**: both medians, the typical difference with
  its interval, how often a recent batch is higher than a baseline batch,
  the p- and q-value, and the counts behind the status (see *Statistics in
  plain words*);
- **OOS rate by value**: the batches of the period split into four groups of
  about equal size by their value, lowest first, with the share of OOS
  batches in each. A staircase going up or down means the OOS rate depends
  on the value. Shown when the data has an OOS column and OOS batches;
- **Investigate**: opens the parameter on the Investigation tab.

### Categorical parameters

Scorecards hold numerical parameters. A tab's categorical parameters with 2
to 30 categories in the period (so lots of ids drop out) are under
**Categorical parameters**, below the trend. Pick one to see each category's
share of the batches per month, its share in the recent window and in the
baseline, and whether the mix differs between the two (Fisher's exact test
for two categories, otherwise a simulated chi-square test). Categories with
fewer than 10 batches are pooled as *Other*.

## Monitoring · The tabs

### Overview

The state of manufacturing in one screen.

**Tiles** (top):

- **Batches started**: in the recent window, against the same number of days
  before it.
- **In process now**: see *Pipeline*.
- **OOS rate, recent**: the share of recent batches that are OOS, against
  the baseline in percentage points. Batches without an OOS result yet are
  left out. Hover the question mark for the counts and intervals.
- **Parameters shifted**: how many numerical parameters have the status
  Shifted, and how many are on watch, of all those monitored.
- **Lead time** (for example *Apheresis → Infused*): the median number of
  days from the first to the last dated stage, against the baseline.
  Batches that are not through yet are left out, so the recent value leans
  to the fast batches.

**Charts**:

- **Batches started per month**, stacked by site.
- **OOS rate per month**, with control limits (see *P-chart*). Months above
  the upper limit are ringed and named under the chart.
- **OOS rate by type**: bar: the recent rate with its 95% interval; tick:
  the baseline rate. Types that are higher than the baseline (Fisher's
  exact test, p below 0.05) are named under the chart.
- **Batches in process**, by the last stage with data and by site.

**What moved** (bottom): up to 12 shifted parameters, the largest shifts
first, with their process day and functional type. Open the Patient, Process
or Final product tab for their trends.

### Pipeline

The batches **in process**: started at most 45 days before the data's last
date and not yet shipped.

A batch's **stage** is the last one with data. A dated stage (apheresis,
cryopreservation, shipment, infusion) is reached when its date is filled in;
a process day (day 0, 1, 3, 6, 8, 10, final product testing) when at least
half of that day's parameters have a value.

**Tiles**: batches in process; batches started in the last 7 days; batches
**standing out**; and **Not closed, older**: batches of the period that
started more than 45 days ago and have no shipment date (terminated, or
never recorded).

**Batches in process** (table), the batches with the most unusual values
first:

- **Days**: days since manufacturing start, at the data's last date.
- **Values**: numerical parameters recorded so far.
- **Unusual**: recorded values outside the central 98% of the completed
  batches (below their 1st or above their 99th percentile).
- **Stands out** (●): about 2% of any batch's values are unusual by chance.
  A batch stands out when it has more than chance gives: fewer than 1 in 100
  batches would have as many.

Click a row for the batch's 15 most unusual values: each as its distance
from the typical value of the completed batches, in standard deviations
(grey band: within ±3; red: above, blue: below; the scale stops at ±8).
Hover a point for the value, the typical value and the percentile.
**Investigate** opens the Investigation tab with the batch as the batch of
interest.

**Lead times** (bottom): the days between the dated stages. The chart shows
the monthly median of each step; the table compares the recent window with
the baseline (Mann-Whitney test). Batches that are not through a step yet
are left out, so the newest months lean to the fast batches.

### Patient

What comes in: the parameters the catalogue files under functional type
*Starting material and patient*, variation source *Patient / starting
material*, or process day *Apheresis*. A scorecard, the picked parameter's
trend, and the categorical parameters (see *The scorecard*).

### Process

The manufacturing steps: every parameter that is not on the Patient or Final
product tab.

- Pick a **process day** along the top, in process order. The number of
  shifted parameters is shown on each day.
- Narrow it by **Functional type** (activation, transduction, growth and
  expansion, ...) or **Variation source** (biological response, operator,
  equipment, raw material, ...).

Then the scorecard, the picked parameter's trend, and the categorical
parameters.

**Across process days** (bottom, folded) shows a quantity measured on three
or more days, for example glucose per cell on days 6, 8 and 10, as one
profile: the baseline's median and middle half per day (grey), and the
recent median (blue). Each day is its own measurement; the lines only join
the medians.

### Final product

Quality attributes and release: the parameters on process day *Final
Product*, *Post-Thaw* or *Post-Release*, or with variation source *Outcome*.

- **OOS** (top): left, the rate per month of the OOS type picked in the list
  above the chart, with control limits (see *P-chart*); right, every type's
  recent rate against the baseline. Recent batches without an OOS result yet
  are left out; a line says how many.
- **Key quality attributes**: small trend plots of the attributes named in
  the config (`monitor.key_cqas`). Grey points: batches; grey band: the
  baseline's middle half, with its median dashed; orange line: the monthly
  median; blue shade: the recent window. A status other than Stable is in
  the plot's title.
- **All final product parameters**: the scorecard, the picked parameter's
  trend, and the categorical parameters.

### Materials

Did a parameter move when a raw material or vector lot changed?

1. Pick the **Parameter** at the top (by default the first key quality
   attribute).
2. The table lists every **material**: the categorical parameters with
   variation source *Raw material / vector* that were used in at least two
   lots. For each material, every lot is compared with the lot used before
   it (Mann-Whitney test; lots in order of their median date of use). A
   comparison needs at least 10 values in both lots; smaller lots are
   skipped.
3. Click a material for the plot and its lot changes.

**Table of materials**, those with the most moves first:

- **Lots**: lots used in the period; **Changes tested**: lot changes where
  both lots have enough values.
- **Moved**: lot changes at which the parameter differs between the two
  lots (q below 0.05). The q-values are corrected over every lot change of
  every material (see *q-value*).
- **Largest shift (SD)**: the largest difference between two consecutive
  lots' medians, in within-lot standard deviations; **Smallest q**.

**Plot**: grey points are the batches; each dark bar is a lot's median,
drawn over the time the lot was in use; an orange dashed line marks a lot
change at which the value moved, labelled with the new lot. Under it, every
lot change with both medians, the shift and the q-value (● = moved).

A lot change shows *when* the value moved, not *why*. When a parameter
shifts on a date, every material whose lot changed near that date shows a
move, and so would a change of site or procedure. Use the table to see which
materials changed together, and what you know of the process to tell them
apart.

The sidebar's period and filters apply; the recent window and the baseline
play no part on this tab.

### Sites

How the manufacturing sites compare, over the recent window and the baseline
together.

- **OOS rate per site**, with 95% intervals; the dashed line is the rate
  over all batches, and the line under the chart says whether the sites
  differ.
- **Per site**: batches, OOS count and rate, and the median of each lead
  time in days.
- **Parameters that differ between sites**: every numerical parameter,
  tested for a difference between the sites (Kruskal-Wallis test, with
  q-values over all parameters). **Gap (SD)** is the distance between the
  highest and the lowest site median, in within-site standard deviations;
  **Lowest** and **Highest** name those sites. A site needs at least 10
  values of a parameter to take part. **Only those that differ** (on by
  default) keeps the parameters with q below 0.05.

Click a row for the values per site (box plots) and the **monthly median per
site**, which shows whether the gap is steady or belongs to one period.

A difference between sites can come from the site, or from what the site
received: patients, material lots, the period it was active. With a site
filter that leaves one site, the tab asks you to clear it.

### CPV

Continued process verification: is each parameter still in its state of
control?

1. Pick a **Parameter set**: the key quality attributes, the final product
   parameters, one process day, or all parameters.
2. Read the tiles: parameters charted, how many are **in control in the
   recent window** (no recent month beyond the control limits), and how
   many are not.
3. Read the **heat map**: one row per parameter, one column per month. Each
   cell is that month's mean compared with the baseline mean (see *Control
   limits*). White: on target; blue: below; red: above; a dot (●): beyond
   the 3-sigma control limits; empty: fewer than 3 values that month. The
   parameters with the most recent months out of control are at the top (at
   most 40; the table has all).
4. Click a row of the table under it for the parameter's **control chart**:
   its trend plot with EWMA and CUSUM switched on.

A single dot can be chance: with many parameters and months, about 3 cells
in 1,000 are beyond the limits when nothing changed. A row of dots, or a row
that turns from white to one colour, is a shift.

**Table**: **Months out, recent** and **Months out, period** count the dots
in the recent window and in the whole period; the other columns are the
scorecard's (see *The scorecard*).

Control limits come from the baseline batches only. For CPV, use a **fixed
baseline** you trust (see *Fixed baseline*); with *Rest of the period* the
limits move every time new data comes in.

### CPV report

**CPV report (PDF)**, under the table on the CPV tab, downloads the view as
a report for the file:

- the scope: parameter set, period, recent window, baseline, site and
  re-manufacture filters;
- a summary: parameters in and out of control, those shifted or on watch,
  and the OOS rate of the recent window and the baseline;
- the heat map and the table of parameters (the 40 most out of control);
- control charts of the parameters that are out of control in the recent
  window, shifted or on watch (at most 12): the batches, the baseline centre
  and 3-sigma limits, and the EWMA with its limits;
- the methods, the points to read with care, and the provenance: when it was
  made, the dashboard version, and the data, parameter list and config files
  with their SHA-256 checksums.

For a monthly report: set the period so it ends with the month, set the
recent window, pick a fixed baseline so every month is judged against the
same reference, and download one report per parameter set.

## Investigation · Overview

The Investigation tab compares **batches of interest** (for example this
week's batches) with **background batches** (for example everything made in
the past year) for one parameter at a time. You pick the two sets at the top
of the page and the parameter in the sidebar. With a glassbox run open, the
run's own two classes are compared, and the model's feature relevance is
shown next to the process data.

### Quick start

1. Check the **selection bar** at the top. By default it compares this
   week's batches with the batches of the past year.
2. Pick the parameter from **Parameter** in the sidebar. Type a few letters
   of its name in the list to find it.
3. Read the plot: grey points are all batches, dark blue rings are the
   batches of interest.
4. Switch on **Trend**, **EWMA** or **CUSUM** in the sidebar to look for
   shifts and drifts.
5. Read **Statistics** under the plot: the headline says whether the
   parameter differs between the two sets, and how sure that is.
6. Open the **Batches of interest** table at the bottom (folded; click its
   title) for each batch's percentile and distance from the trend. Click a
   row to mark that batch with a star in the plot.

For the machine learning view, click **Open glassbox run** and open the
run's results folder (see *Glassbox run*).

### Page layout

From top to bottom:

- **Selection bar**: the two batch sets and the buttons to change them.
- **Title**: the plotted parameter, as on the y-axis, with its unit and
  transform.
- **Plot**: the parameter over time, with notes under it.
- **Feature relevance**: only while a glassbox run is open; see *Glassbox
  run*.
- **Statistics**: the difference between the two sets for the plotted
  parameter, in plain words, with the numbers behind it.
- **Batches of interest**: a table with one row per batch of interest,
  folded.
- **Warnings and messages**: folded; its title says how many there are.

The **sidebar** holds everything that changes what the plot shows:
**Parameter**, **Display** and **Colour**, and the names of the data and
config files. With a glassbox run open, its **Glassbox run** group (title,
model and *How good is the model?*) is at the top.

## Investigation · Selecting batches

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

When the tab is first opened, and whenever you click **Default**:

- batches of interest: all batches made this week, Monday to Sunday;
- background: all batches made from the same day one year ago up to today
  (28 February when today is 29 February), without the batches of interest;
- both sets: all sites, re-manufactured batches included.

The default follows today's date, not the data's last date. If the data has
no batch made this week, the set of interest is empty and the plot shows the
background only.

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
while you are on another tab.

When a filter change rules out batches you picked by id, they are dropped
from the pick list.

## Investigation · The sidebar

### Parameter

**Parameter** lists every parameter that is in the catalogue, is not marked
*Exclude* there, and has a column in the data, with its value type. Its title says how many are listed, for
example *Parameter (12 of 619)*.

- **To find a parameter**, click the list and type: it keeps the names that
  contain what you typed.
- **Filter by catalogue** folds open one filter per catalogue column (in the
  sample setup: Functional Type, Process Day and Variation Source). Only parameters with one of the chosen values stay in the list;
  an empty filter means all values. The fold-out's title says how many
  filters are active.

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

For numerical parameters with at least 20 values the dashboard checks whether a transform would suit
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

While EWMA or CUSUM is on, **Reference period (normal batches)** appears
under the switches; see *Reference period*.

### Reference period

EWMA and CUSUM need to know what is normal. They measure it (target and
spread) from the **background batches made in the reference period**, and
judge every batch, the batches of interest included, against it. So the
shift you are looking for does not widen the limits.

**Reference period (normal batches)** picks the dates; all dates by default.
Pick a stable period you trust. It is shaded light blue on the plot when it
is shorter than the plotted period. With fewer than 3 reference batches, the
first 100 plotted batches are used instead, and the note under the plot says
so.

With one **Manufacturing site** chosen, the reference batches are that
site's.

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

## Investigation · The plot

### Axes and value types

The x-axis is the manufacturing date. The y-axis depends on the parameter's
value type in the catalogue:

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

- **Grey points** (or coloured, see *Colour points by*): all plotted batches.
- **Dark blue rings**: the batches of interest, a thin ring around the point.
- **Star with label**: the batch picked in the **Batches of interest** table.
- **Orange lines**: the trend fit, one line per segment.
- **Orange dashed vertical lines**: trend breakpoints, labelled with their
  date.
- **Small orange crosses**: outliers left out of the trend fit.
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

### Notes under the plot

A line under the plot notes what was left out or how it was computed, for
example `22 without value or date · trend (flat segments) breaks: none ·
EWMA/CUSUM normal from 1321 background batches made 2024-01-03 to 2026-08-31:
target 66.46, σ 9.516`. It can name:

- batches without a value or a date;
- values the transform cannot handle;
- the trend model and the dates of its breakpoints;
- where EWMA and CUSUM take normal from.

### Signals under the plot

With EWMA or CUSUM on, a second line lists the signals, newest first, for
example *CUSUM: downward shift from 2025-06-27 (signal 2025-07-03), 4
batches signalling*. For the CUSUM, the start is its estimate of when the
shift began: the batch after the sum was last zero, often days or weeks
before the signal. At most three are listed; the line says how many earlier
ones there are.

### Warnings and messages

Warnings are collected in **Warnings and messages** at the bottom of the
page. It is folded; its title says how many there are. They cover:

- batches of interest not made at the chosen site, filtered out by category,
  or without a value;
- batches of a glassbox run that are not in the data, and files of a run
  that were left out or changed;
- manufacturing dates that could not be read, and duplicated batch ids.

## Investigation · Batches of interest table

The table **Batches of interest**, near the bottom of the page, has one row
per plotted batch of interest. It is folded: click its title to open it. Its
columns:

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

## Investigation · Glassbox run

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
interest from the background; see *How good is the model?*.

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
**Parameter** in the sidebar, and the catalogue filters are cleared if they
would hide it. The plotted parameter is in bold on a light blue
band in both charts. Greyed-out names are features the dashboard does not
have as a parameter; clicking them shows a message instead.

## Investigation · Statistics

The **Statistics** section, under the plot, answers three questions about the
plotted parameter in plain words:

1. Is it different in the batches of interest than in the background?
2. How big is the difference, and how sure can we be?
3. Could something else explain it, such as a change over time?

It is written to be read by people who do not work with statistics every
day. The sentences come first; every number behind them is one click away in
*Numbers and methods*, and the whole record can be downloaded for the
investigation file. The terms (median, interval, p-value, AUC, ...) are
explained under *Statistics in plain words*.

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
  changes over time (see *Comparing within quarters*). It ends in one of:
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
  See *Consistency*. Or *Not consistent everywhere*, naming the sites or years where it goes
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

Only for a glassbox run's own groups. The chart shows the share of batches
of interest of each month against the overall rate and its control limits;
see *P-chart* for how to read it.

A month **above the upper limit** is ringed in dark blue and named in the
text, for example "Jan 2024: 12 of 44 (27%, limit 22%)": that month had more
batches of interest than chance explains, so look for what was different
then (a lot, a change, a site). When no month is flagged, no single month
stands out; the rate can still drift slowly, which the dark line shows.

The chart covers the plotted batches only: the sidebar's filters apply.

### All parameters

Click **Screen all N parameters** to test every parameter at once. It takes
some seconds; the result is kept until the plotted batches change, when the
button comes back. Each parameter is tested **within quarters** (see *Comparing within
quarters*),
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

## Statistics in plain words

The terms the dashboard uses, for people who do not work with statistics
every day. Every comparison is between two groups of batches: **batches of
interest** and **background batches** on the Investigation tab, the **recent
window** and the **baseline** on the monitoring tabs. The examples below
speak of batches of interest and background; read "recent" and "baseline"
for the monitoring tabs.

A test needs at least **10 batches with a value in each group**. With fewer,
the dashboard says so and does not test: with so few batches, any "finding"
would be mostly chance.

### Median

The middle value: half the batches are below it, half above.
Unlike the average, a few extreme batches do not pull it around.

### Standard deviation (SD)

How much the batches normally vary around their typical value. About two
thirds of the batches lie within 1 SD of the middle and almost all within 3
SD, so a difference "in SD" says how big it is compared with the normal
batch-to-batch variation, whatever the parameter's units: 0.2 SD is small,
0.5 SD is visible in a plot, 1 SD is large.

The monitoring tabs use a **robust** SD: 1.4826 × the median absolute
deviation (the median distance of the batches from their median). A few
extreme batches do not inflate it, as they do the ordinary SD. When more
than half the values are identical, the ordinary SD is used instead.

### 95% interval

Written "95% CI". Every number computed from batches is
an estimate: with other batches it would come out a little different. The
interval is the range of values that are consistent with the data. A narrow
interval means a precise estimate; a wide one means few batches or much
variation. When the interval of a difference does not include zero (or the
interval of an AUC does not include 0.5), the difference is, as a rule,
clear.

### p-value

How surprising the observed difference would be if there were
really no difference between the groups. A small p-value (below 0.05, one
in twenty) means the difference is unlikely to be chance alone; the
dashboard then calls it *clear* and says *higher* or *lower*. A large
p-value means the data do not show a difference; it does not prove there is
none. "p < 0.001" means less than one in a thousand. A p-value says nothing
about how *big* a difference is: with thousands of batches a tiny difference
can have a small p-value. Always read it together with the size (the typical
difference, the AUC or the rates).

For two groups of numbers the dashboard uses the **Mann-Whitney test**. It
compares ranks, so it does not assume a bell-shaped distribution and is not
thrown by a few extreme batches. For more than two groups (the sites) it
uses the **Kruskal-Wallis test**, the same idea.

### q-value

When hundreds of parameters are tested, some look different by
chance alone: at p < 0.05, about 1 in 20 unrelated parameters would. The
q-value corrects for this (Benjamini–Hochberg). Among the parameters with
q below 0.05, you can expect about 1 in 20 to be a false lead, however many
parameters were tested.

The dashboard uses q-values wherever it tests many things at once: the
scorecards (every parameter), the Sites tab (every parameter), the Materials
tab (every lot change of every material), and the screen under **All
parameters** on the Investigation tab.

### Typical difference

How much higher or lower the value of a batch of
interest typically is than that of a background batch, in the parameter's
own units (statisticians call it the Hodges–Lehmann estimate: the median of
the differences between every batch of interest and every background batch).
"+1.39 (95% CI +1.18 to +1.6)" means batches of interest are typically about 1.4
units higher, and with 95% confidence somewhere between 1.2 and 1.6.

### AUC

Area under the curve. The chance that a randomly picked batch of
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

On the monitoring tabs the same number is written as a sentence: "a recent
batch is higher than a baseline batch 77% of the time".

### Share and its interval

A share of batches is given with its count and interval, for example "13 of
198 (6.6%, 95% CI 4.0%–11%)". The interval is a Wilson interval, which stays
sensible for small counts and for rates close to 0% or 100%. The dashboard
uses it for the share of batches of interest, the OOS rates, and the bars
with error bars.

To compare a share between two groups it uses **Fisher's exact test**; for
more than two categories, a chi-square test whose p-value is found by
simulating 20,000 tables, which stays correct for small counts.

### Comparing within quarters

Used on the Investigation tab. Many things drift over time: a parameter's
typical value, and also the share of batches of interest. If both happen to
change over the same period, the parameter looks different in the batches of
interest even when it has nothing to do with them. To rule that out, the
dashboard also compares batches of interest with background batches **made in
the same calendar quarter** only, and then
combines the quarters (van Elteren test for numbers,
Cochran–Mantel–Haenszel test for categories). A difference that survives
this comparison cannot be explained by slow changes over time.

### Consistency

Used on the Investigation tab. A real process effect usually shows at every site and in
every year. The dashboard repeats the comparison per site and per year and
says whether the difference points the same way everywhere. A difference
that exists at one site only points to something local to that site.

### Association is not cause

A parameter that differs between two groups may cause the difference, be
caused by it, or travel along with the real cause: a lot change, a site, a
season. Statistics narrow the search; process knowledge and experiments
confirm the cause. See also *Reading the statistics with care*.

## Charts and methods

### Trend fit

The trend fit looks for level shifts and changes in slope over time, over
all plotted batches. It is the orange line in the trend plots of every tab.

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

### Control limits

A control chart asks whether a process still behaves as it did in a
reference set of batches: the **baseline** on the monitoring tabs, the
**reference period** on the Investigation tab.

- The **centre** is the mean of the reference batches.
- **Sigma** is their normal batch-to-batch variation: the average moving
  range (the mean absolute difference between consecutive batches, in date
  order) divided by 1.128, the usual estimate for individual values. Unlike
  the ordinary SD, it is not inflated by a slow drift within the reference
  batches.
- The **control limits** lie 3 sigma on either side of the centre. A process
  that has not changed stays within them almost always (about 997 times in
  1,000), so a point beyond them is a signal worth a look.

For a monthly mean (the CPV heat map) the limits are narrower: 3 sigma
divided by the square root of the number of batches in the month, because a
mean of many batches varies less than a single batch. The heat map shows
each month's distance from the centre in these units (standard errors), so
±3 is the limit for every cell.

Control limits describe the process's own variation. They are not
specification limits: a parameter can be in control and out of
specification, or the reverse.

### EWMA chart

The exponentially weighted moving average (EWMA) smooths the values in
manufacturing-date order, giving the newest batch a weight of 0.2 and the
previous average the rest. It reacts to small, lasting shifts that single
points do not show.

- **Target and sigma** come from the reference batches, as described under
  *Control limits*: the background batches of the reference period on the
  Investigation tab, the baseline on the monitoring tabs.
- **Control limits** lie at ±3 sigma, scaled for the averaging. They start
  narrow and widen to their final value over the first batches.
- A **signal** (dark blue diamond) is a batch where the EWMA is outside the limits,
  on either side.

Every plotted batch is judged against the reference batches. The weight and the limits are set in the `spc` section of the config
file.

### CUSUM chart

The tabular CUSUM adds up deviations from the target (the same target and
sigma as the EWMA), in sigma units, in manufacturing-date order:

- **C+** (line going up) adds deviations above target, minus a slack of 0.5
  sigma, and never goes below zero. It grows when values stay high.
- **C−** (line going down, drawn negative) does the same for values below
  target.
- A **signal** (dark blue diamond) is a batch where either sum passes the decision
  interval of 5 sigma (the dark blue dashed lines), on the side that matters.

The point where a line leaves zero and keeps climbing shows when a shift
started; on the Investigation tab the signal line under the plot names that
date. The CUSUM is not reset after a signal, so a lasting shift keeps
signalling. The slack and decision interval are set in the `spc` section of
the config file.

### P-chart

The control chart for a rate per month: the OOS rate on the Overview and
Final product tabs, the share of batches of interest on the Investigation
tab.

- **Dark line**: the rate of each month.
- **Solid grey line**: the rate over all months together.
- **Dotted lines**: the control limits, 3 standard errors on either side.
  They show how far a month's rate can stray from the overall rate by chance
  alone, given how many batches the month had: they are wider for months
  with few batches.
- **Ringed month**: above the upper limit, so more than chance explains.
  Months with fewer than 10 batches are never ringed. A month below the
  lower limit is unusually good.

## Configuration

### Choosing the config file

The dashboard reads its settings from a YAML file, in this order:

1. the file named in the `DASHBOARD_CONFIG` environment variable;
2. `config/config.local.yaml`, if it exists (not in version control, for
   your real data);
3. `config/config.yaml`.

The file in use is named at the bottom of the sidebar. Changes to the config,
data or catalogue files are picked up the next time the page updates.

### Sections of the config file

| Section | What it sets |
| --- | --- |
| `data` | The path of the batch CSV (a `.csv.gz` works too), options for reading it, and how to read the manufacturing dates (`date_format`, `dayfirst`). Without a `date_format`, dates written in different ways in one column are all read; dates that cannot be read are listed under **Warnings and messages** on the Investigation tab, and those batches have no date. |
| `columns` | Which column of the data holds each field the dashboard needs. Batch id and manufacturing date are required; site and re-manufacture are optional, and their filters disappear when left out. |
| `column_groups` | Fields that offer a choice of columns. |
| `remanufacture.true_values` | The values that mark a batch as re-manufactured, such as Y or Yes. |
| `parameters` | The parameter catalogue (`path`: Excel or CSV, one row per parameter; `read_options` for reading it), and which of its columns hold the name (`name_column`), the value type (`type_column`), the catalogue filters (`filter_columns`) and the parameters to hide (`exclude_column`; see *Hiding parameters*). A parameter without a value type is read as numbers when at least 80% of its values are numbers. |
| `monitor` | The monitoring tabs; see *The monitor section*. |
| `trend` | The trend fit: `max_breaks`, `min_segment_size`, `bic_margin`, `outlier_iqr` (see *Trend fit*). |
| `spc` | EWMA and CUSUM: `lam`, `L`, `k`, `h` (see *EWMA chart* and *CUSUM chart*), and `baseline`, the number of first batches used only when there are too few reference batches. |

### The monitor section

All of it is optional; the defaults follow the names in the catalogue.

| Setting | Meaning | Default |
| --- | --- | --- |
| `recent_days` | The recent window the tabs open on. | 90 |
| `baseline` | `start` and `end` of a fixed baseline to open on. | none: the rest of the period |
| `pipeline_days` | How long an unfinished batch counts as in process. | 45 |
| `oos.flag` | The column that says a batch is OOS. | `OOS? (Y/N)` |
| `oos.types` | The columns of the OOS types. | every column ending in `OOS (Y/N)` |
| `true_values` | The values that mean yes in those columns. | Y, Yes, True, 1 |
| `stages` | The pipeline stages in process order: each a `label` with a date `column` or a `process_day`. | apheresis, days 0 to 10, cryopreservation, final product, shipment, infusion |
| `closed_from` | The stage from which a batch has left the pipeline. | Shipped |
| `key_cqas` | The key quality attributes of the Final product and CPV tabs. | eight final product attributes |
| `material_sources` | The variation sources whose categorical parameters are lots (Materials tab). | Raw material / vector |
| `group_columns` | The catalogue columns holding `functional_type`, `process_day` and `variation_source`. | Functional Type, Process Day, Variation Source |

Stages, OOS columns and attributes that are not in the data are skipped.

### What the tabs need from the data

| Tab or chart | Needs |
| --- | --- |
| Patient, Process, Final product | The catalogue's Functional Type or Process Day column. |
| Process filters, Materials | The catalogue's Variation Source column. Without it, the Materials tab takes the categorical parameters named *lot* or *batch*. |
| OOS tiles and charts, OOS rate by value | The OOS columns. |
| Pipeline, lead times | The stage date columns and the process days. |
| Sites, site filter | The site column (`columns.site`). |

A chart whose columns are missing is left out; a tab that cannot work
without them says what it needs.

### Hiding parameters

Every parameter in the catalogue that is also a column in the data is shown.
To hide one, put `Y` in its *Exclude* column in the catalogue (`Yes`, `True`,
`1` and `X` work too; case does not matter). It then disappears from every
page: the parameter lists, the monitoring tabs, the screens and the
scorecards. Empty the cell to show it again. The config's
`parameters.exclude_column` and `parameters.exclude_values` change the
column and the values that hide.

### Data requirements

The data has one row per batch. A batch id that appears more than once is
reported under **Warnings and messages** on the Investigation tab. Values
that cannot be read as the parameter's type count as missing and are not
plotted.

## Troubleshooting

### A monitoring tab says the parameters cannot be grouped

The parameter catalogue has no Functional Type or Process Day column. Add them
to the catalogue, or name its columns under `monitor.group_columns`.

### Every status is "Too few batches"

The recent window or the baseline has fewer than 10 batches with a value.
Check the line under the page title: pick a longer **Recent window** or
**Period**, check the **Baseline dates**, or clear the site filter.

### A status changed though the process did not

With **Rest of the period** the baseline moves as the data grows and the
period slides, so the comparison changes a little every time. Use a fixed
baseline for a stable reference.

### Many parameters are shifted at once

Often the baseline contains a change, so "recent against baseline" compares
after with a mix of before and after. Look at a trend plot for the date of
the break and start a fixed baseline after it.

### No batches in process

The Pipeline tab counts batches started at most 45 days before the data's
last date that have no shipment date. Check *Data as of* in the sidebar: an
old data file has none. With other date columns than the sample's, set
`monitor.stages` in the config.

### The OOS charts are missing

The data has no `OOS? (Y/N)` column. Name yours under `monitor.oos` in the
config.

### The Materials tab finds moves in many materials

A parameter that shifted on one date shows a move in every material whose
lot changed near that date. See *Materials*.

### The plot shows only grey points

On the Investigation tab: there are no batches of interest in the plot. With
the default selection this happens when the data has no batch made this
week. Use **Edit selection** to pick
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

On the Investigation tab, clear the catalogue filters. A parameter only
appears when it is in the catalogue, is not marked in its *Exclude* column,
and has a column in the data. On the monitoring tabs, a parameter is on the tab its catalogue
entry puts it on (see *Monitoring · The tabs*); the **All parameters** set on
the CPV tab has every numerical one.

### The statistics say "Too few batches"

A test needs at least 10 batches with a value in each group. With the default
selection (this week's batches) that is rarely the case. Pick a longer time
frame for the batches of interest, or open a glassbox run.

### The screen button is back

The screen is kept for the batches it was run on. After a change of the
selection, the site or the category filter, the plotted batches are different
and the screen has to be run again.
