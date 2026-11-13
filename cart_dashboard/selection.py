"""Pure (Streamlit-free) batch selection logic, so it can be unit tested."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum

import pandas as pd

from .config import DashboardConfig
from .data import REMANUFACTURED


class SelectionMode(str, Enum):
    SINGLE = "Single batch"
    MANUAL = "Manual selection"
    TIME_FRAME = "Time frame"
    ALL = "All batches matching filters"
    # Only offered while a glassbox run is open; ``batch_ids`` then holds the
    # run's batches of interest or its background batches.
    RUN_INTEREST = "Glassbox run: interest"
    RUN_BACKGROUND = "Glassbox run: background"


RUN_MODES = (SelectionMode.RUN_INTEREST, SelectionMode.RUN_BACKGROUND)


class RemanufactureFilter(str, Enum):
    ALL = "Include re-manufactured"
    EXCLUDE = "Exclude re-manufactured"
    ONLY = "Only re-manufactured"


@dataclass
class BatchSelection:
    mode: SelectionMode
    sites: list[str] | None = None  # None = no site filter
    remanufacture: RemanufactureFilter = RemanufactureFilter.ALL
    batch_ids: list[str] = field(default_factory=list)  # SINGLE / MANUAL / RUN modes
    date_range: tuple[date, date] | None = None  # TIME_FRAME


def filter_pool(
    df: pd.DataFrame,
    cfg: DashboardConfig,
    sites: list[str] | None = None,
    remanufacture: RemanufactureFilter = RemanufactureFilter.ALL,
) -> pd.DataFrame:
    """Apply the site and re-manufacture filters."""
    mask = pd.Series(True, index=df.index)
    if sites is not None and cfg.has("site"):
        mask &= df[cfg.col("site")].astype(str).isin(sites)
    if remanufacture == RemanufactureFilter.EXCLUDE:
        mask &= ~df[REMANUFACTURED]
    elif remanufacture == RemanufactureFilter.ONLY:
        mask &= df[REMANUFACTURED]
    return df[mask]


def select_batches(df: pd.DataFrame, cfg: DashboardConfig, selection: BatchSelection) -> list[str]:
    """Batch ids matching ``selection``, in order of manufacturing date."""
    pool = filter_pool(df, cfg, selection.sites, selection.remanufacture)
    batch_col = cfg.col("batch_id")
    date_col = cfg.col("manufacturing_date")

    if selection.mode in (SelectionMode.SINGLE, SelectionMode.MANUAL, *RUN_MODES):
        pool = pool[pool[batch_col].isin(selection.batch_ids)]
    elif selection.mode == SelectionMode.TIME_FRAME:
        if selection.date_range is None:
            return []
        start, end = (pd.Timestamp(d) for d in selection.date_range)
        # The end date is inclusive: keep everything before the next midnight.
        end = end + pd.Timedelta(days=1)
        pool = pool[(pool[date_col] >= start) & (pool[date_col] < end)]

    ordered = pool.sort_values(date_col, na_position="last")
    return list(dict.fromkeys(ordered[batch_col]))


def current_week(today: date) -> tuple[date, date]:
    """Monday to Sunday of the week containing ``today``."""
    monday = today - timedelta(days=today.weekday())
    return monday, monday + timedelta(days=6)


def past_year(today: date) -> tuple[date, date]:
    """From the same day one year ago (28 Feb for 29 Feb) up to ``today``."""
    try:
        start = today.replace(year=today.year - 1)
    except ValueError:
        start = today.replace(year=today.year - 1, day=28)
    return start, today
