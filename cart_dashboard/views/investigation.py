"""The investigation page: batches of interest against a background, for one parameter at a time.

The selection bar, the trend plot, a glassbox run's feature relevance, the
statistics and the batches-of-interest table.
"""

from __future__ import annotations

import streamlit as st

from ..data import UNREAD_DATES
from . import drivers, messages, selection, statistics, timeline
from .loading import load


def render() -> None:
    cfg, df, params, _ = load()

    messages.reset()
    if unread := df.attrs.get(UNREAD_DATES):
        examples = ", ".join(f"'{v}'" for v in unread[:3])
        messages.add(
            f"{len(unread)} manufacturing date(s) in {cfg.csv_path.name} could not be read "
            f"(for example {examples}); those batches have no date. Set `data.date_format` in "
            f"{cfg.source_path.name} if the dates use an unusual format."
        )
    run = selection.open_run()
    interest_ids, background_ids = selection.render(df, cfg)
    # Fixed slots, top to bottom: plot, feature relevance, statistics, batches
    # of interest table. The sections are drawn after the plot so they cover
    # the parameter and the batches it shows.
    plot_area, drivers_area, stats_area, table_area = st.container(), st.container(), st.container(), st.container()
    model = None
    available = params[params["name"].isin(df.columns)]
    if run is not None:
        with st.sidebar:
            model = drivers.sidebar(run)
        drivers.prepare(available, cfg)
    with plot_area:
        plotted = timeline.render(df, cfg, params, interest_ids, background_ids, model, table_area)
    if run is not None:
        with drivers_area:
            drivers.render(run, model, available, cfg, interest_ids, plotted.interest_ids)
    with stats_area:
        statistics.render(plotted, df, cfg, available, run, model, interest_ids, background_ids)

    with st.sidebar:
        st.divider()
        st.caption(
            f"{df[cfg.col('batch_id')].nunique()} batches in {cfg.csv_path.name}  \n"
            f"Config: {cfg.source_path.name}"
        )
        duplicated = df[cfg.col("batch_id")].duplicated().sum()
        if duplicated:
            messages.add(f"{duplicated} duplicated batch id row(s) in the data.")
    messages.render()
