"""The monitoring pages: the calculations in cart_dashboard.monitor, and every page on the sample data."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from cart_dashboard import monitor as M
from cart_dashboard.config import load_config
from cart_dashboard.data import load_batches, load_parameters

ROOT = Path(__file__).parent.parent


@pytest.fixture(scope="module")
def sample(tmp_path_factory):
    """The sample data and the catalogue, through a config of its own (config.yaml may point elsewhere)."""
    raw = yaml.safe_load((ROOT / "config" / "config.yaml").read_text())
    raw["data"]["csv_path"] = str(ROOT / "data" / "sample_batches.csv.gz")
    raw["parameter_metadata"]["csv_path"] = str(ROOT / "config" / "parameters.csv")
    raw["parameter_metadata"]["catalog"] = {"path": str(ROOT / "catalog.xlsx"), "name_column": "Parameter"}
    path = tmp_path_factory.mktemp("cfg") / "config.yaml"
    path.write_text(yaml.safe_dump(raw))
    cfg = load_config(path)
    df, params = load_batches(cfg), load_parameters(cfg)
    params = params[params["name"].isin(df.columns)].reset_index(drop=True)
    return path, cfg, df, params


def test_catalogue_adds_columns_and_parameters(sample):
    _, cfg, _, _ = sample
    params = load_parameters(cfg)
    assert "Variation Source" in params.columns
    row = params.set_index("name").loc["FP Flow CAR+ (%)"]
    assert (row["type"], row["Process Day"], row["Variation Source"]) == ("numeric", "Final Product", "Outcome")
    only_catalogue = params.set_index("name").loc["Lactate_yield_on_glucose_D6"]  # not in parameters.csv
    assert only_catalogue["type"] == "" and only_catalogue["Functional Type"] == "Metabolism and feeding"


def test_windows_split_the_period():
    dates = pd.Series(pd.date_range("2025-01-01", "2025-12-31", freq="D"))
    recent, baseline = M.windows(dates, "2025-03-01", "2025-12-31", 30)
    assert recent.sum() == 30 and dates[recent].min() == pd.Timestamp("2025-12-02")
    assert dates[baseline].min() == pd.Timestamp("2025-03-01") and not (recent & baseline).any()
    assert baseline.sum() == (pd.Timestamp("2025-12-02") - pd.Timestamp("2025-03-01")).days


def test_scorecard_finds_the_shifted_parameter_and_only_that_one():
    rng = np.random.default_rng(1)
    n = 400
    dates = pd.Series(pd.date_range("2025-01-01", periods=n, freq="D"))
    recent, baseline = M.windows(dates, dates.min(), dates.max(), 60)
    values = pd.DataFrame({f"p{i}": rng.normal(10, 1, n) for i in range(20)})
    values.loc[recent, "p3"] += 1.5  # a shift of 1.5 SD in the recent window
    values["few"] = np.where(np.arange(n) < 5, 1.0, np.nan)
    score = M.scorecard(values, dates, recent, baseline).set_index("parameter")
    assert score.index[0] == "p3" and score.loc["p3", "status"] == M.STATUS_SHIFTED
    assert score.loc["p3", "shift"] == pytest.approx(1.5, abs=0.4)
    assert score.loc["p3", "ewma"] > 0 and score.loc["p3", "q"] < 0.001
    assert (score["status"] == M.STATUS_SHIFTED).sum() == 1
    assert score.loc["few", "status"] == M.STATUS_FEW
    assert len(score.loc["p0", "trend"]) == 14  # one median per month, Jan 2025 to Feb 2026


def test_monthly_z_marks_the_shifted_months():
    rng = np.random.default_rng(2)
    n = 360
    dates = pd.Series(pd.date_range("2025-01-01", periods=n, freq="D"))
    recent, baseline = M.windows(dates, dates.min(), dates.max(), 60)
    values = pd.DataFrame({"steady": rng.normal(0, 1, n), "moved": rng.normal(0, 1, n)})
    values.loc[recent, "moved"] += 2
    z = M.monthly_z(values, dates, recent | baseline, baseline)
    assert (z.loc["steady"].abs() < 3.5).all()
    assert z.loc["moved"].iloc[-1] > 3 and (z.loc["moved"].iloc[:9].abs() < 3.5).all()


def test_flag_keeps_missing_apart():
    f = M.flag(pd.Series(["Y", "n", None, " yes ", ""]), {"y", "yes"})
    assert f.tolist()[:2] == [True, False] and f.isna().tolist() == [False, False, True, False, True]
    assert M.oos_label("CAR% OOS (Y/N)") == "CAR%" and M.oos_label("OOS? (Y/N)") == "Any OOS"


def test_settings_follow_the_data(sample):
    _, cfg, df, params = sample
    s = M.settings(cfg, df, params)
    assert s.oos_flag == "OOS? (Y/N)" and "CAR% OOS (Y/N)" in s.oos_types and s.oos_flag not in s.oos_types
    assert [st.label for st in s.stages][0] == "Apheresis" and s.closed_from == "Shipped"
    assert (s.functional_type, s.process_day, s.variation_source) == ("Functional Type", "Process Day", "Variation Source")
    bare = M.settings(cfg, df[[cfg.col("batch_id"), cfg.col("manufacturing_date")]], params[["name", "type"]])
    assert bare.oos_flag is None and bare.stages == [] and bare.process_day is None  # nothing to go on: pages say so


def test_pipeline_follows_the_data_cut(sample):
    _, cfg, df, params = sample
    s = M.settings(cfg, df, params)
    assert M.as_of(df, s, cfg) == pd.Timestamp("2026-09-01")
    pipe = M.pipeline(df, params, s, cfg)
    start = df[cfg.col("manufacturing_date")]
    assert (pipe.loc[start < "2026-07-01", "state"] == "closed").all()
    open_ = pipe[pipe["state"] == "in process"]
    assert 30 < len(open_) < 90 and open_["days"].max() <= s.pipeline_days
    newest = pipe.loc[start.idxmax()]
    assert newest["state"] == "in process" and newest["stage"] in ("Apheresis", "Day 0 · selection", "Day 1 · activation")
    order = [st.label for st in s.stages]
    by_age = open_.assign(i=open_["stage"].map(order.index)).sort_values("days")
    assert by_age["i"].iloc[0] < by_age["i"].iloc[-1]  # older batches are further along


def test_unusual_values_are_about_two_percent(sample):
    _, cfg, df, params = sample
    s = M.settings(cfg, df, params)
    values, units = M.numeric_frame(df, params, cfg)
    assert "FP Flow CAR+ (%)" in values and "Manufacturing Site" not in values
    assert units["Date of Harvest"] == " (days from manufacturing start)"
    pipe = M.pipeline(df, params, s, cfg)
    history, rows = pipe["state"] == "closed", pipe["state"] == "in process"
    unusual = M.unusual_values(values, history, rows)
    recorded = int(values[rows].notna().sum().sum())
    assert 0.01 < len(unusual) / recorded < 0.04
    assert unusual["value"].notna().all() and unusual["z"].abs().iloc[0] >= unusual["z"].abs().iloc[-1]
    assert ((unusual["percentile"] <= 1.5) | (unusual["percentile"] >= 98.5)).all()


def test_lead_times_and_sites(sample):
    _, cfg, df, params = sample
    s = M.settings(cfg, df, params)
    leads = M.lead_times(df, s, cfg)
    assert list(leads.columns)[0] == "Apheresis → Manufacture start" and list(leads.columns)[-1] == "Apheresis → Infused"
    assert leads["Apheresis → Manufacture start"].median() == pytest.approx(13.5, abs=0.5)
    assert (leads.stack().dropna() >= 0).all()
    period = pd.Series(True, index=df.index)
    summary = M.site_summary(df, s, cfg, period, leads)
    assert summary["batches"].sum() == len(df) and (summary["oos"].between(0, 0.2)).all()
    values, _ = M.numeric_frame(df, params, cfg)
    screen = M.site_screen(values[["FP Flow CAR+ (%)", "Endotoxin (EU/mL)"]], df[cfg.col("site")], period)
    assert set(screen.columns) >= {"parameter", "p", "q", "gap", "low", "high", "median · SITE-A"}
    assert (screen["gap"] >= 0).all()


def test_site_screen_finds_a_site_effect():
    rng = np.random.default_rng(3)
    sites = pd.Series(np.repeat(["A", "B", "C"], 100))
    values = pd.DataFrame({"same": rng.normal(0, 1, 300), "differs": rng.normal(0, 1, 300) + (sites == "C") * 2})
    screen = M.site_screen(values, sites, pd.Series(True, index=sites.index)).set_index("parameter")
    assert screen.index[0] == "differs" and screen.loc["differs", "high"] == "C" and screen.loc["differs", "q"] < 0.001
    assert screen.loc["differs", "gap"] == pytest.approx(2, abs=0.6) and screen.loc["same", "q"] > 0.05


def test_day_families():
    names = ["Day 6 Glucose (g/L)", "Day 8 Glucose (g/L)", "D10 Glucose (g/L)", "Day 3 VSVg Result", "Day 10 VSVg Result",
             "Glucose_increment_D6_D8"]
    families = M.day_families(names)
    assert families == {"Glucose (g/L)": {6: "Day 6 Glucose (g/L)", 8: "Day 8 Glucose (g/L)", 10: "D10 Glucose (g/L)"}}


def test_categorical_shift_shares_sum_to_one():
    rng = np.random.default_rng(4)
    recent = pd.Series(np.arange(300) >= 200)
    values = pd.Series(np.where(recent, rng.choice(["a", "b"], 300, p=[0.8, 0.2]), rng.choice(["a", "b"], 300, p=[0.3, 0.7])))
    table, p = M.categorical_shift(values, recent, ~recent)
    assert table["recent"].sum() == pytest.approx(1) and table["baseline"].sum() == pytest.approx(1)
    assert p < 0.001 and table.set_index("category").loc["a", "recent"] > 0.6


PAGES = {
    "overview": "from cart_dashboard.views import overview; overview.render()",
    "pipeline": "from cart_dashboard.views import pipeline; pipeline.render()",
    "patient": "from cart_dashboard.views import groups; groups.patient()",
    "process": "from cart_dashboard.views import groups; groups.process()",
    "product": "from cart_dashboard.views import groups; groups.product()",
    "sites": "from cart_dashboard.views import sites; sites.render()",
    "cpv": "from cart_dashboard.views import cpv; cpv.render()",
}


@pytest.mark.parametrize("page", list(PAGES))
def test_every_monitoring_page_runs_on_the_sample_data(page, sample, monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("DASHBOARD_CONFIG", str(sample[0]))
    at = AppTest.from_string(PAGES[page], default_timeout=180).run()
    assert not at.exception, [e.value for e in at.exception]
    assert not at.error, [e.value for e in at.error]
    # A site filter and another window: every page follows the sidebar.
    at.session_state["mon_sites"] = ["SITE-A"]
    at.session_state["mon_recent"] = 30
    at.session_state["mon_period"] = "All data"
    at.run()
    assert not at.exception, [e.value for e in at.exception]


def test_the_app_opens_on_the_overview(sample, monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("DASHBOARD_CONFIG", str(sample[0]))
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=180).run()
    assert not at.exception, [e.value for e in at.exception]
    labels = [m.label for m in at.metric]
    assert "In process now" in labels and "Parameters shifted" in labels
