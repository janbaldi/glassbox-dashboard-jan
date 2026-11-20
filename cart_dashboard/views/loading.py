"""Loading the config, the batch data and the parameter catalogue once, for every page."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from ..config import ConfigError, DashboardConfig, load_config, resolve_config_path
from ..data import load_batches, load_parameters


@st.cache_data(show_spinner="Loading batch data…")
def _load(config_path: str, mtimes: tuple[float, ...]) -> tuple[DashboardConfig, pd.DataFrame, pd.DataFrame]:
    # The mtimes are part of the cache key so edits to the files are picked up.
    cfg = load_config(config_path)
    return cfg, load_batches(cfg), load_parameters(cfg)


def load() -> tuple[DashboardConfig, pd.DataFrame, pd.DataFrame, tuple]:
    """(config, batches, parameter catalogue, cache key). Stops the page with the error when a file is wrong.

    The cache key (config path and the files' modification times) changes
    when a file changes; pages put it in the keys of their own caches.
    """
    config_path = resolve_config_path()
    try:
        cfg = load_config(config_path)
        files = [config_path, cfg.csv_path, cfg.parameters_path]
        mtimes = tuple(f.stat().st_mtime if f.exists() else 0.0 for f in files)
        cfg, df, params = _load(str(config_path), mtimes)
    except ConfigError as exc:
        st.error(str(exc))
        st.stop()
    return cfg, df, params, (str(config_path), mtimes)
