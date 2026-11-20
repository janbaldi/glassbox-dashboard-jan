"""Reading the batch data defined in the configuration."""

from __future__ import annotations

import pandas as pd

from .config import ConfigError, DashboardConfig

# Internal helper columns added to the dataset. Prefixed so they cannot clash
# with columns in the user's data.
REMANUFACTURED = "__remanufactured"
# df.attrs key: the manufacturing dates that could not be read, as written.
UNREAD_DATES = "unread_dates"


def _parse_dates(raw: pd.Series, date_format: str | None, dayfirst: bool) -> pd.Series:
    """Manufacturing dates as datetimes; NaT where a date cannot be read.

    With a configured ``date_format`` that format is used, strictly. Without one,
    pandas takes the format from the first date and turns every date written
    another way into NaT, silently; and with ``dayfirst`` it reads an ISO date as
    year-day-month ('2024-03-01' becomes 3 January). So ISO 8601 dates are read
    first, then the rest in the format of their first date, then whatever is
    left one by one: a column mixing '3/1/2024' and '2024-03-01' keeps both.
    """
    if date_format is not None:
        return pd.to_datetime(raw, format=date_format, errors="coerce")
    parsed = pd.to_datetime(raw, format="ISO8601", errors="coerce")
    for how in ({"dayfirst": dayfirst}, {"format": "mixed", "dayfirst": dayfirst}):
        rest = parsed.isna() & raw.notna()
        if not rest.any():
            break
        parsed[rest] = pd.to_datetime(raw[rest], errors="coerce", **how)
    return parsed


def load_batches(cfg: DashboardConfig) -> pd.DataFrame:
    """Read the CSV and normalise the columns the dashboard relies on.

    - the manufacturing date column is parsed to datetimes; the dates that could
      not be read are listed in ``df.attrs[UNREAD_DATES]``
    - the batch id column is cast to string
    - a boolean ``REMANUFACTURED`` helper column is added (all False when the
      ``remanufacture`` parameter is not configured)
    """
    if not cfg.csv_path.exists():
        raise ConfigError(f"Data file not found: {cfg.csv_path}")

    df = pd.read_csv(cfg.csv_path, **cfg.read_csv_options)

    missing = sorted(c for c in cfg.referenced_columns() if c not in df.columns)
    if missing:
        raise ConfigError(
            f"Column(s) referenced in {cfg.source_path.name} not found in "
            f"{cfg.csv_path.name}: {missing}"
        )

    batch_col = cfg.col("batch_id")
    df[batch_col] = df[batch_col].astype(str).str.strip()

    date_col = cfg.col("manufacturing_date")
    raw = df[date_col]
    df[date_col] = _parse_dates(raw, cfg.date_format, cfg.dayfirst)
    given = raw.notna() & raw.astype(str).str.strip().ne("")
    unread = raw[given & df[date_col].isna()].astype(str).tolist()

    df = df.copy()  # de-fragment after the column rewrites above (wide data)
    df.attrs[UNREAD_DATES] = unread  # reported by app.py; those batches have no date
    if cfg.has("remanufacture"):
        truthy = {v.strip().lower() for v in cfg.remanufacture_true_values}
        df[REMANUFACTURED] = (
            df[cfg.col("remanufacture")].astype(str).str.strip().str.lower().isin(truthy)
        )
    else:
        df[REMANUFACTURED] = False

    return df


def load_parameters(cfg: DashboardConfig) -> pd.DataFrame:
    """The parameter catalogue: ``name`` and ``type``, plus every other column of the catalogue.

    The catalogue is an Excel or CSV file with one row per parameter. Rows
    whose ``exclude_column`` holds one of ``exclude_values`` (case does not
    matter) are left out, so the dashboard never shows those parameters.
    ``type`` is empty where the catalogue gives no value type: such a
    parameter is read as numbers when its values are numbers.
    """
    path = cfg.parameters_path
    if not path.exists():
        raise ConfigError(f"Parameter catalogue not found: {path}")
    excel = path.suffix.lower() in (".xlsx", ".xlsm", ".xls")
    meta = (pd.read_excel if excel else pd.read_csv)(path, **cfg.parameters_read_options)
    name, vtype, exclude = cfg.parameters_name_column, cfg.parameters_type_column, cfg.parameters_exclude_column
    wanted = [name, vtype] + cfg.parameters_filter_columns + ([exclude] if exclude else [])
    missing = [c for c in dict.fromkeys(wanted) if c not in meta.columns]
    if missing:
        raise ConfigError(f"Column(s) {missing} not found in {path.name}")
    meta = meta.dropna(subset=[name])
    if exclude:
        marked = {v.strip().lower() for v in cfg.parameters_exclude_values}
        meta = meta[~meta[exclude].astype("string").str.strip().str.lower().isin(marked).fillna(False)]
    clash = [c for c in ("name", "type") if c in meta.columns and c not in (name, vtype)]
    meta = meta.drop(columns=clash).rename(columns={name: "name", vtype: "type"})
    meta["name"] = meta["name"].astype(str).str.strip()
    meta["type"] = meta["type"].fillna("").astype(str).str.strip()
    return meta.drop_duplicates("name").reset_index(drop=True)
