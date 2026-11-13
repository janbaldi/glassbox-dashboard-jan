"""Monitoring: limits, reference batches, signal episodes and the plot."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from cart_dashboard.config import ConfigError, load_config
from cart_dashboard.data import load_batches, load_parameters
from cart_dashboard.plots import BACKGROUND_LABEL, INTEREST_LABEL, SET_COLUMN, Limit, timeline_scatter
from cart_dashboard.spc import control_charts, episodes
from cart_dashboard.trend import fit_trend


@pytest.fixture
def setup(tmp_path: Path):
    """Six batches with a CAR value and a categorical flag."""
    csv = tmp_path / "d.csv"
    pd.DataFrame({
        "ID": ["B1", "B2", "B3", "B4", "B5", "B6"],
        "DT": ["2024-01-01", "2024-01-02", "2024-02-01", "2024-02-02", "2024-03-01", "2024-03-02"],
        "OOS": ["Y", "Y", "Y", "N", "n", None],
        "CAR_OOS": ["Y", "N", "N", "N", "N", None],
        "DOSE_OOS": ["N", "yes", "N", "N", "N", None],
        "CAR": [30.0, 60.0, 55.0, 62.0, 40.0, 70.0],
    }).to_csv(csv, index=False)
    meta = tmp_path / "p.csv"
    meta.write_text(
        "Parameter;Value Type;LSL;USL;LAL;UAL;Dir\n"
        "CAR;numeric;45;;50;;low\n"
        "OOS;categorical;;;;;\n"
    )
    raw = {
        "data": {"csv_path": str(csv)},
        "columns": {"batch_id": "ID", "manufacturing_date": "DT"},
        "parameter_metadata": {
            "csv_path": str(meta), "read_csv_options": {"sep": ";"},
            "limit_columns": {"lower_spec": "LSL", "upper_spec": "USL", "lower_alert": "LAL",
                              "upper_alert": "UAL", "direction": "Dir"},
        },
    }
    cfg_file = tmp_path / "c.yaml"
    cfg_file.write_text(yaml.safe_dump(raw))
    cfg = load_config(cfg_file)
    return cfg, load_batches(cfg), load_parameters(cfg), cfg_file, raw


def test_config_reads_limits(setup):
    cfg, _, params, cfg_file, raw = setup
    row = params.set_index("name").loc["CAR"]
    assert (row["lower_spec"], row["lower_alert"], row["direction"]) == (45, 50, "low")
    assert np.isnan(row["upper_spec"])
    assert params.set_index("name").loc["OOS", "direction"] == "both"  # empty: both sides
    raw["parameter_metadata"]["limit_columns"]["lower"] = "LSL"
    cfg_file.write_text(yaml.safe_dump(raw))
    with pytest.raises(ConfigError, match="unknown key"):
        load_config(cfg_file)


def test_control_charts_take_normal_from_the_reference():
    rng = np.random.default_rng(1)
    dates = pd.Series(pd.date_range("2024-01-01", periods=300, freq="D"))
    y = pd.Series(rng.normal(10, 1, 300))
    oos = pd.Series(False, index=y.index)
    oos[::10] = True
    y[oos] -= 6  # the OOS batches are far off
    c = control_charts(dates, y, reference=~oos)
    assert c.from_reference and c.baseline == int((~oos).sum())
    assert c.target == pytest.approx(y[~oos].mean())
    early = control_charts(dates, y, baseline=100)
    assert early.target < c.target  # the OOS batches drag the old baseline down
    few = control_charts(dates, y, reference=pd.Series([True, True] + [False] * 298))
    assert not few.from_reference and few.baseline == 100


def test_direction_and_episodes():
    dates = pd.Series(pd.date_range("2024-01-01", periods=200, freq="D"))
    rng = np.random.default_rng(5)
    y = pd.Series(np.r_[np.zeros(100), np.full(50, -2.0), np.full(50, 2.0)] + rng.normal(0, 1, 200))
    ref = pd.Series(np.arange(200) < 100)
    low = control_charts(dates, y, reference=ref, direction="low")
    assert low.direction == "low" and not low.cusum_high.any() and low.cusum_low.any()
    eps = [e for e in episodes(low) if e.chart == "CUSUM"]
    assert len(eps) == 1 and eps[0].direction == "down"
    start = int(dates[dates == eps[0].start].index[0])
    assert abs(start - 100) <= 3  # the shift began at batch 100: the CUSUM dates it back from the signal
    assert eps[0].first_signal > eps[0].start
    both = control_charts(dates, y, reference=ref)
    assert {e.direction for e in episodes(both) if e.chart == "CUSUM"} == {"up", "down"}


def test_plot_with_every_overlay(setup):
    cfg, df, _, _, _ = setup
    rng = np.random.default_rng(0)
    n = 120
    data = pd.DataFrame({
        "ID": [f"B{i}" for i in range(n)],
        "DT": pd.date_range("2024-01-01", periods=n, freq="7D"),
        SET_COLUMN: np.where(np.arange(n) % 8 == 0, INTEREST_LABEL, BACKGROUND_LABEL),
    })
    y = pd.Series(rng.normal(60, 5, n))
    normal = data[SET_COLUMN] == BACKGROUND_LABEL
    trend = fit_trend(data["DT"], y)
    charts = control_charts(data["DT"], y, reference=normal, direction="low")
    fig = timeline_scatter(
        data, cfg, y, "CAR", trend=trend, ewma=charts, cusum=charts,
        limits=[Limit("Lower spec", 45, "45", "spec"), Limit("Lower alert", 50, "50", "alert")],
        reference=(pd.Timestamp("2024-06-01"), pd.Timestamp("2025-01-01")),
    )
    names = {t.name for t in fig.data}
    assert {"Specification limit", "Alert limit"} <= names
    assert fig.layout.yaxis2.title.text == "CUSUM (σ), h=5"  # rows: plot, CUSUM


def test_app_monitors_with_control_charts():
    """Every chart on: the control charts take normal from the background, and no OOS wording is left."""
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(Path(__file__).parent.parent / "app.py"), default_timeout=180)
    at.session_state["timeline_parameter"] = "FP Flow CAR+ (%)"
    at.session_state["timeline_ewma"] = True
    at.session_state["timeline_cusum"] = True
    at.run()
    assert not at.exception
    captions = " ".join(c.value for c in at.caption)
    assert "EWMA/CUSUM normal from" in captions and "background batches" in captions
    assert "signals on the low side only" in captions
    assert any(e.label == "Statistics · batches of interest compared with background batches" for e in at.expander)
    assert "OOS" not in " ".join([captions] + [e.label for e in at.expander] + [s.label for s in at.selectbox])
    # A narrower reference period is used and named.
    at.date_input(key="timeline_reference").set_value((pd.Timestamp("2025-01-01").date(), pd.Timestamp("2025-12-31").date())).run()
    assert not at.exception
    assert "made 2025-01-01 to 2025-12-31" in " ".join(c.value for c in at.caption)


def test_a_cusum_dip_under_the_limit_is_one_shift():
    dates = pd.Series(pd.date_range("2024-01-01", periods=60, freq="D"))
    # 30 batches on target, then 30 low, with one batch back up that brings the sum under h, not to zero.
    y = pd.Series(np.r_[np.tile([0.5, -0.5], 15), np.full(30, -2.0)])
    y[33] = 1.5  # after the first signal, back under h but not to zero
    c = control_charts(dates, y, reference=pd.Series(np.arange(60) < 30), direction="low")
    from cart_dashboard.spc import _runs

    assert len(_runs(c.cusum_low)) == 2  # two runs of signals...
    runs = [e for e in episodes(c) if e.chart == "CUSUM"]
    assert len(runs) == 1 and runs[0].signals == int(c.cusum_low.sum())
