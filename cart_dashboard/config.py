"""Loading and validating the YAML configuration.

The configuration maps dashboard *parameters* (e.g. ``batch_id``) onto the
column names of the user's dataset. The rest of the code only ever asks the
config for a column by parameter name, so the dataset layout can change without
touching the dashboard code.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_ENV_VAR = "DASHBOARD_CONFIG"
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "config.yaml"
LOCAL_CONFIG = PROJECT_ROOT / "config" / "config.local.yaml"

REQUIRED_PARAMETERS = ("batch_id", "manufacturing_date")


class ConfigError(ValueError):
    """Raised when the configuration file is missing or malformed."""


LIMIT_KEYS = ("lower_spec", "upper_spec", "lower_alert", "upper_alert", "direction")


@dataclass
class DashboardConfig:
    source_path: Path
    csv_path: Path
    read_csv_options: dict[str, Any] = field(default_factory=dict)
    date_format: str | None = None
    dayfirst: bool = False
    columns: dict[str, str] = field(default_factory=dict)
    column_groups: dict[str, list[str]] = field(default_factory=dict)
    remanufacture_true_values: list[str] = field(default_factory=list)
    parameters_path: Path | None = None
    parameters_read_csv_options: dict[str, Any] = field(default_factory=dict)
    parameters_name_column: str = "Parameter"
    parameters_type_column: str = "Value Type"
    parameters_description_column: str | None = None
    parameters_filter_columns: list[str] = field(default_factory=list)
    parameters_limit_columns: dict[str, str] = field(default_factory=dict)  # lower_spec, ..., direction
    trend: dict[str, float] = field(default_factory=dict)  # keyword arguments for trend.fit_trend
    spc: dict[str, float] = field(default_factory=dict)  # keyword arguments for spc.control_charts

    def has(self, parameter: str) -> bool:
        """True when ``parameter`` is mapped onto a dataset column."""
        return bool(self.columns.get(parameter))

    def col(self, parameter: str) -> str:
        """Dataset column name for a one-to-one ``parameter``."""
        try:
            column = self.columns[parameter]
        except KeyError:
            raise ConfigError(
                f"Parameter '{parameter}' is not defined under 'columns' in {self.source_path}"
            ) from None
        if not column:
            raise ConfigError(f"Parameter '{parameter}' has no column assigned in {self.source_path}")
        return column

    def group(self, name: str) -> list[str]:
        """Dataset column names for a one-to-many ``column_groups`` entry."""
        try:
            return list(self.column_groups[name])
        except KeyError:
            raise ConfigError(
                f"Group '{name}' is not defined under 'column_groups' in {self.source_path}"
            ) from None

    def referenced_columns(self) -> set[str]:
        """Every dataset column the config refers to."""
        cols = {c for c in self.columns.values() if c}
        for group in self.column_groups.values():
            cols.update(group)
        return cols


def resolve_config_path() -> Path:
    """Pick the config file: env var > config.local.yaml > config.yaml."""
    env_path = os.environ.get(CONFIG_ENV_VAR)
    if env_path:
        return Path(env_path).expanduser().resolve()
    if LOCAL_CONFIG.exists():
        return LOCAL_CONFIG
    return DEFAULT_CONFIG


def _resolve_path(value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def load_config(path: str | Path | None = None) -> DashboardConfig:
    path = Path(path) if path else resolve_config_path()
    if not path.exists():
        raise ConfigError(f"Configuration file not found: {path}")

    with path.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    if not isinstance(raw, dict):
        raise ConfigError(f"{path} must contain a YAML mapping at the top level")

    data = raw.get("data") or {}
    if not data.get("csv_path"):
        raise ConfigError(f"'data.csv_path' is missing in {path}")

    columns = {str(k): (str(v) if v is not None else None) for k, v in (raw.get("columns") or {}).items()}
    missing = [p for p in REQUIRED_PARAMETERS if not columns.get(p)]
    if missing:
        raise ConfigError(f"Required parameter(s) {missing} missing under 'columns' in {path}")

    groups_raw = raw.get("column_groups") or {}
    column_groups: dict[str, list[str]] = {}
    for name, cols in groups_raw.items():
        if not isinstance(cols, list):
            raise ConfigError(f"column_groups.{name} must be a list of column names in {path}")
        column_groups[str(name)] = [str(c) for c in cols]

    meta = raw.get("parameter_metadata") or {}
    if not meta.get("csv_path"):
        raise ConfigError(f"'parameter_metadata.csv_path' is missing in {path}")

    limit_columns = {str(k): str(v) for k, v in (meta.get("limit_columns") or {}).items() if v}
    unknown = sorted(set(limit_columns) - set(LIMIT_KEYS))
    if unknown:
        raise ConfigError(f"parameter_metadata.limit_columns: unknown key(s) {unknown} in {path}; use {list(LIMIT_KEYS)}")

    reman = raw.get("remanufacture") or {}
    true_values = [str(v) for v in reman.get("true_values", ["Y", "Yes", "True", "1"])]

    return DashboardConfig(
        source_path=path,
        csv_path=_resolve_path(str(data["csv_path"])),
        read_csv_options=dict(data.get("read_csv_options") or {}),
        date_format=data.get("date_format"),
        dayfirst=bool(data.get("dayfirst", False)),
        columns=columns,
        column_groups=column_groups,
        remanufacture_true_values=true_values,
        parameters_path=_resolve_path(str(meta["csv_path"])),
        parameters_read_csv_options=dict(meta.get("read_csv_options") or {}),
        parameters_name_column=str(meta.get("name_column", "Parameter")),
        parameters_type_column=str(meta.get("type_column", "Value Type")),
        parameters_description_column=str(meta["description_column"]) if meta.get("description_column") else None,
        parameters_filter_columns=[str(c) for c in meta.get("filter_columns") or []],
        parameters_limit_columns=limit_columns,
        trend=dict(raw.get("trend") or {}),
        spc=dict(raw.get("spc") or {}),
    )

