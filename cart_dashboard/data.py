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


def _with_catalog(meta: pd.DataFrame, cfg: DashboardConfig) -> pd.DataFrame:
    """The metadata with the parameter catalogue merged in.

    The catalogue (one row per parameter) wins where both have a column, adds
    its other columns, and adds the parameters the metadata file does not list
    (without a value type: read as numbers when their values are numbers).
    """
    if cfg.catalog_path is None:
        return meta
    if not cfg.catalog_path.exists():
        raise ConfigError(f"Parameter catalogue not found: {cfg.catalog_path}")
    excel = cfg.catalog_path.suffix.lower() in (".xlsx", ".xlsm", ".xls")
    catalog = (pd.read_excel if excel else pd.read_csv)(cfg.catalog_path, **cfg.catalog_read_options)
    key, name = cfg.catalog_name_column, cfg.parameters_name_column
    if key not in catalog.columns:
        raise ConfigError(f"Column '{key}' not found in {cfg.catalog_path.name}")
    catalog = catalog.dropna(subset=[key]).rename(columns={key: name})
    catalog[name] = catalog[name].astype(str).str.strip()
    catalog = catalog.drop_duplicates(name).set_index(name)
    meta = meta.dropna(subset=[name]).copy()
    meta[name] = meta[name].astype(str).str.strip()
    meta = meta.drop_duplicates(name).set_index(name)
    merged = meta.reindex(meta.index.union(catalog.index, sort=False))
    for column in catalog.columns:
        merged[column] = catalog[column].reindex(merged.index).combine_first(
            merged[column] if column in merged else pd.Series(index=merged.index, dtype=object)
        )
    return merged.reset_index()


def load_parameters(cfg: DashboardConfig) -> pd.DataFrame:
    """Parameter metadata: ``name``, ``type`` and ``description`` plus the configured filter columns.

    With ``limit_columns`` configured, also ``lower_spec``, ``upper_spec``,
    ``lower_alert``, ``upper_alert`` (numbers, NaN when empty) and
    ``direction`` ("low", "high" or "both").

    ``description`` is empty when no description column is configured.
    """
    if not cfg.parameters_path.exists():
        raise ConfigError(f"Parameter metadata file not found: {cfg.parameters_path}")
    meta = pd.read_csv(cfg.parameters_path, **cfg.parameters_read_csv_options)
    meta = _with_catalog(meta, cfg)
    cols = {cfg.parameters_name_column: "name", cfg.parameters_type_column: "type"}
    if cfg.parameters_description_column:
        cols[cfg.parameters_description_column] = "description"
    for key, column in cfg.parameters_limit_columns.items():
        cols[column] = key
    wanted = list(dict.fromkeys(list(cols) + cfg.parameters_filter_columns))
    missing = [c for c in wanted if c not in meta.columns]
    if missing:
        raise ConfigError(f"Column(s) {missing} not found in {cfg.parameters_path.name}")
    meta = meta[wanted].rename(columns=cols).dropna(subset=["name"])
    meta["name"] = meta["name"].astype(str).str.strip()
    meta["type"] = meta["type"].fillna("").astype(str).str.strip()
    meta["description"] = meta["description"].fillna("").astype(str).str.strip() if "description" in meta else ""
    for key in cfg.parameters_limit_columns:
        if key == "direction":
            meta[key] = meta[key].fillna("both").astype(str).str.strip().str.lower().replace("", "both")
        else:
            meta[key] = pd.to_numeric(meta[key], errors="coerce")
    return meta.drop_duplicates("name").reset_index(drop=True)
