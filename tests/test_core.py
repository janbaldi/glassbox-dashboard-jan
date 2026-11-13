from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from cart_dashboard.config import DEFAULT_CONFIG, ConfigError, load_config
from cart_dashboard.context import CUSUM_SIGNAL, DEVIATION, PERCENTILE, SAME_VALUE, context_table
from cart_dashboard.data import REMANUFACTURED, UNREAD_DATES, load_batches, load_parameters
from cart_dashboard.plots import (
    BACKGROUND_LABEL,
    CATEGORY_COLORS,
    INTEREST_LABEL,
    NO_VALUE_LABEL,
    OTHER_LABEL,
    SET_COLUMN,
    category_palette,
    color_groups,
    combine_sets,
    fold_categories,
    plot_values,
    timeline_scatter,
)
from cart_dashboard.search import highlight, search_parameters
from cart_dashboard.spc import control_charts
from cart_dashboard.views.help_page import HELP_FILE
from cart_dashboard.views.help_page import parse as parse_help
from cart_dashboard.transform import apply_transform, percent_scale, suggest_transform
from cart_dashboard.selection import (
    BatchSelection,
    RemanufactureFilter,
    SelectionMode,
    current_week,
    past_year,
    select_batches,
)
from cart_dashboard.trend import fit_trend


@pytest.fixture
def cfg_and_df(tmp_path: Path):
    csv = tmp_path / "d.csv"
    pd.DataFrame(
        {
            "ID": ["B1", "B2", "B3", "B4"],
            "DT": ["2024-01-01", "2024-02-01", "2024-03-01", "2024-03-15"],
            "SITE": ["A", "B", "A", "B"],
            "REMFG": ["no", "YES", "no", "no"],
            "VAL": [1.0, 2.0, None, 4.0],
        }
    ).to_csv(csv, index=False)
    meta = tmp_path / "p.csv"
    meta.write_text("Parameter;Value Type\nVAL;numeric\n")
    cfg_file = tmp_path / "c.yaml"
    cfg_file.write_text(
        yaml.safe_dump(
            {
                "data": {"csv_path": str(csv)},
                "columns": {
                    "batch_id": "ID",
                    "manufacturing_date": "DT",
                    "site": "SITE",
                    "remanufacture": "REMFG",
                },
                "column_groups": {"g": ["VAL"]},
                "remanufacture": {"true_values": ["yes"]},
                "parameter_metadata": {"csv_path": str(meta), "read_csv_options": {"sep": ";"}},
            }
        )
    )
    cfg = load_config(cfg_file)
    return cfg, load_batches(cfg)


def test_default_config_loads_sample_data():
    cfg = load_config(DEFAULT_CONFIG)
    df = load_batches(cfg)
    params = load_parameters(cfg)
    assert len(df) > 0
    assert params["name"].isin(df.columns).all()


def test_mapping_and_normalisation(cfg_and_df):
    cfg, df = cfg_and_df
    assert cfg.group("g") == ["VAL"]
    assert pd.api.types.is_datetime64_any_dtype(df["DT"])
    assert df[REMANUFACTURED].tolist() == [False, True, False, False]


def test_dates_in_mixed_formats_are_kept_and_the_rest_reported(cfg_and_df):
    """pandas takes the format from the first date; the others must not quietly vanish."""
    cfg, _ = cfg_and_df
    data = pd.read_csv(cfg.csv_path)
    data["DT"] = ["2024-01-01", "02/15/2024", "15 March 2024", "not a date"]
    data.to_csv(cfg.csv_path, index=False)
    df = load_batches(cfg)
    assert df["DT"].dt.strftime("%Y-%m-%d").tolist()[:3] == ["2024-01-01", "2024-02-15", "2024-03-15"]
    assert df["DT"].isna().tolist() == [False, False, False, True]
    assert df.attrs[UNREAD_DATES] == ["not a date"]

    # With dayfirst, an ISO date stays year-month-day.
    cfg.dayfirst = True
    data["DT"] = ["01/02/2024", "2024-03-01", "02/03/2024", None]
    data.to_csv(cfg.csv_path, index=False)
    df = load_batches(cfg)
    assert df["DT"].dt.strftime("%Y-%m-%d").tolist()[:3] == ["2024-02-01", "2024-03-01", "2024-03-02"]
    assert df.attrs[UNREAD_DATES] == []  # a missing date is not an unreadable one


def test_missing_column_raises(cfg_and_df, tmp_path):
    cfg, _ = cfg_and_df
    cfg.columns["site"] = "NOPE"
    with pytest.raises(ConfigError, match="NOPE"):
        load_batches(cfg)


def test_required_parameter_missing(tmp_path):
    f = tmp_path / "c.yaml"
    f.write_text(yaml.safe_dump({"data": {"csv_path": "x.csv"}, "columns": {"batch_id": "ID"}}))
    with pytest.raises(ConfigError, match="manufacturing_date"):
        load_config(f)


def test_select_modes(cfg_and_df):
    cfg, df = cfg_and_df
    assert select_batches(df, cfg, BatchSelection(SelectionMode.SINGLE, batch_ids=["B2"])) == ["B2"]
    assert select_batches(df, cfg, BatchSelection(SelectionMode.MANUAL, batch_ids=["B3", "B1"])) == ["B1", "B3"]
    tf = BatchSelection(SelectionMode.TIME_FRAME, date_range=(date(2024, 2, 1), date(2024, 3, 1)))
    assert select_batches(df, cfg, tf) == ["B2", "B3"]  # both ends inclusive
    assert select_batches(df, cfg, BatchSelection(SelectionMode.ALL)) == ["B1", "B2", "B3", "B4"]


def test_filters(cfg_and_df):
    cfg, df = cfg_and_df
    sel = BatchSelection(SelectionMode.ALL, sites=["B"])
    assert select_batches(df, cfg, sel) == ["B2", "B4"]
    sel.remanufacture = RemanufactureFilter.EXCLUDE
    assert select_batches(df, cfg, sel) == ["B4"]
    sel.remanufacture = RemanufactureFilter.ONLY
    assert select_batches(df, cfg, sel) == ["B2"]


def test_plot(cfg_and_df):
    cfg, df = cfg_and_df
    data = combine_sets(df, cfg, ["B1"], ["B1", "B2", "B3", "B4"])
    assert (data[SET_COLUMN] == INTEREST_LABEL).sum() == 1
    assert (data[SET_COLUMN] == BACKGROUND_LABEL).sum() == 3
    y, order, _ = plot_values(data["VAL"], "numeric", data["DT"])
    fig = timeline_scatter(data, cfg, y, "VAL", order)
    points, interest = fig.data
    assert len(points.x) == 3 and len(interest.x) == 1  # B3 has no value; B1 gets the ring

    color, color_order = color_groups(data["SITE"], "categorical", data["DT"])
    fig = timeline_scatter(data, cfg, y, "VAL", order, color=color, color_order=color_order, color_label="SITE")
    assert sorted(t.name for t in fig.data[:2]) == ["A (n=1)", "B (n=2)"]  # B3 (site A) has no value


def test_color_groups_cycle_colours_in_order_of_first_appearance():
    lots = [f"lot{i:02d}" for i in range(9)]
    raw = pd.Series(lots[::-1] + [None])  # listed newest first...
    dates = pd.Series(pd.date_range("2024-01-01", periods=10)[::-1])  # ...but lot00 is made first
    color, order = color_groups(raw, "categorical", dates)
    assert order == lots + [NO_VALUE_LABEL]
    assert color.iloc[-1] == NO_VALUE_LABEL
    palette = category_palette(order)
    assert palette["lot00"] == palette["lot06"] == CATEGORY_COLORS[0]  # colours restart after six
    assert palette["lot05"] != palette["lot06"]
    _, order = color_groups(pd.Series(["4+", "1", "1"]), "[1,2-3,4+]", pd.Series(pd.date_range("2024-01-01", periods=3)))
    assert order == ["1", "4+"]


def test_plot_values_by_type():
    mfg = pd.Series(pd.to_datetime(["2024-01-01", "2024-01-01", "2024-01-01"]))

    y, order, _ = plot_values(pd.Series(["1", "2", None]), "numeric", mfg)
    assert order is None and y.tolist()[:2] == [1, 2]

    y, order, _ = plot_values(pd.Series(["1:2", "0.25", None]), "ratio", mfg)
    assert y.tolist()[:2] == [0.5, 0.25]

    y, order, unit = plot_values(pd.Series(["90", "135", None]), "duration", mfg)
    assert y.tolist()[:2] == [90, 135] and "min" in unit

    y, _, unit = plot_values(pd.Series(["2024-01-03 12:00", "2023-12-31", None]), "datetime", mfg)
    assert y.tolist()[:2] == [2.5, -1] and "days" in unit

    y, _, unit = plot_values(pd.Series(["14:30", "08:00", None]), "datetime", mfg)
    assert y.tolist()[:2] == [14.5, 8] and "hour of day" in unit

    _, order, _ = plot_values(pd.Series(["4+", "1", "odd"]), "[1,2-3,4+]", mfg)
    assert order == ["1", "2-3", "4+", "odd"]

    _, order, _ = plot_values(pd.Series(["b", "a", "b"]), "categorical", mfg)
    assert order == ["b", "a"]

    _, order, _ = plot_values(pd.Series(["Negative", "Positive"]), "TODO", mfg)
    assert order is not None  # unknown type, text values -> categorical


def test_clock_times():
    """hh:mm and hh:mm:ss share a column; a stray value does not turn clock times into dates."""
    mfg = pd.Series(pd.to_datetime(["2024-01-01"] * 11))
    clocks = ["14:30:36", "08:00"] + ["09:15"] * 8 + ["n/a"]
    y, _, unit = plot_values(pd.Series(clocks), "datetime", mfg)
    assert "hour of day" in unit
    assert y.tolist()[:3] == [pytest.approx(14.51), 8.0, 9.25]
    assert pd.isna(y.iloc[-1])  # not a clock time: no value

    # A bare clock time among dates has no date, so no value (not today's date).
    dates = ["2024-01-03 12:00", "2023-12-31", "14:30"] + ["2024-01-02"] * 8
    y, _, unit = plot_values(pd.Series(dates), "datetime", mfg)
    assert "days" in unit
    assert y.tolist()[:2] == [2.5, -1] and pd.isna(y.iloc[2])


def test_fold_categories_keeps_interest():
    y = pd.Series(["a", "b", "c", "d", "z"])
    folded, order = fold_categories(y, ["a", "b", "c", "d", "z"], keep={"z"}, max_categories=3)
    assert order == ["a", "b", "z", OTHER_LABEL]
    assert folded.tolist() == ["a", "b", OTHER_LABEL, OTHER_LABEL, "z"]


def _series(n=300, seed=0):
    rng = np.random.default_rng(seed)
    dates = pd.Series(pd.date_range("2024-01-01", periods=n, freq="D"))
    return dates, rng.normal(0, 1, n)


def test_trend_finds_shift_without_endpoints():
    dates, y = _series()
    y[180:] += 3
    fit = fit_trend(dates, y)
    assert fit.breakpoints == [dates[180]]  # interior only, at the shift
    assert len(fit.segments) == 2
    assert fit.segments[1].intercept - fit.segments[0].value_at(dates[179]) > 2  # a jump


def test_trend_flat_noise_has_no_breaks_and_flags_outliers():
    dates, y = _series()
    y[10] = 50
    fit = fit_trend(dates, y)
    assert fit.breakpoints == []
    assert fit.outlier[10] and fit.outlier.sum() == 1


def test_trend_picks_fewest_parameters_within_margin_of_best():
    dates, y = _series()
    y[150:] += 0.6
    loose = fit_trend(dates, y, bic_margin=1e9)  # everything within the margin -> simplest model
    assert loose.breakpoints == [] and loose.model == "shifts"
    fit = fit_trend(dates, y)
    chosen = fit.bic[(fit.bic["model"] == fit.model) & (fit.bic["n_breaks"] == len(fit.breakpoints))]
    assert chosen["bic"].iloc[0] <= fit.bic["bic"].min() + 2
    close = fit.bic[fit.bic["bic"] <= fit.bic["bic"].min() + 2]
    assert chosen["n_params"].iloc[0] == close["n_params"].min()


def test_trend_drift_is_one_sloped_line_and_step_is_flat_segments():
    dates, y = _series(n=600)
    drift = fit_trend(dates, y + np.linspace(0, 1.5, 600))
    assert drift.model == "trends" and drift.breakpoints == []
    step = y.copy()
    step[300:] += 0.5  # a modest shift of 0.5 SD
    fit = fit_trend(dates, step)
    assert fit.model == "shifts" and len(fit.breakpoints) == 1
    assert abs((fit.breakpoints[0] - dates[300]).days) <= 15


def test_trend_too_few_points():
    dates, y = _series(n=10)
    assert fit_trend(dates, y, min_segment_size=15) is None


def test_context_table_percentile_and_deviation(cfg_and_df):
    cfg, _ = cfg_and_df
    n = 200
    dates, y = _series(n=n)
    data = pd.DataFrame({"ID": [f"B{i}" for i in range(n)], "DT": dates, "SITE": "A", "VAL": y})
    data.loc[199, "VAL"] = 5.0  # far above the rest
    data[SET_COLUMN] = [BACKGROUND_LABEL] * (n - 1) + [INTEREST_LABEL]
    trend = fit_trend(data["DT"], data["VAL"])
    table = context_table(data, cfg, data["VAL"], trend)
    assert table["ID"].tolist() == ["B199"]
    assert table[PERCENTILE].iloc[0] == 100
    assert table[DEVIATION].iloc[0] > 4

    cats = pd.Series(["x"] * 150 + ["y"] * 50)
    table = context_table(data, cfg, cats, None)
    assert table[SAME_VALUE].iloc[0] == pytest.approx(100 * 49 / 199)


def test_plot_highlight_on_log_scale(cfg_and_df):
    cfg, df = cfg_and_df
    data = combine_sets(df, cfg, ["B1"], ["B2", "B4"])
    y, order, _ = plot_values(data["VAL"], "numeric", data["DT"])
    t = apply_transform(y, "Log")
    fig = timeline_scatter(data, cfg, t.values, "VAL", order, highlight="B4", raw=y, ticks=(t.tickvals, t.ticktext))
    assert fig.data[-1].name == "Selected: B4"
    assert fig.layout.annotations[0].y == pytest.approx(np.log10(4.0))
    assert list(fig.layout.yaxis.ticktext)[:1] == ["1"]


def test_log_and_logit_transforms():
    t = apply_transform(pd.Series([0.0, 1.0, 10.0, 100.0, np.nan]), "Log")
    assert t.values.tolist()[1:4] == [0.0, 1.0, 2.0] and t.out_of_domain == 1
    assert {"1", "10", "100"} <= set(t.ticktext)

    t = apply_transform(pd.Series([50.0, 90.0, 100.0]), "Logit", "Viability (%)")
    assert t.values.iloc[0] == pytest.approx(0.0) and t.values.iloc[1] == pytest.approx(np.log(9))
    assert t.out_of_domain == 1  # 100 % has no logit
    assert percent_scale(pd.Series([0.2, 0.9]), "x") == 1 and percent_scale(pd.Series([150.0]), "x") is None


def test_suggest_transform():
    rng = np.random.default_rng(0)
    assert suggest_transform(pd.Series(rng.lognormal(0, 1, 500)))[0] == "Log"
    assert suggest_transform(pd.Series(rng.normal(10, 1, 500))) is None
    viability = pd.Series(100 / (1 + np.exp(-rng.normal(3, 0.7, 500))))
    assert suggest_transform(viability, "Viability (%)")[0] == "Logit"


def test_ewma_and_cusum_signal_after_a_shift():
    dates, y = _series(n=300)
    y[200:] += 1.5
    c = control_charts(pd.Series(dates), pd.Series(y), lam=0.2, L=3, k=0.5, h=5, baseline=100)
    for signal in (c.ewma_signal, c.cusum_signal):
        assert signal[:200].sum() <= 5  # the odd false alarm in the noise
        assert 200 <= 200 + int(np.argmax(signal[200:])) < 215 and signal[215:].mean() > 0.75
    assert c.sigma == pytest.approx(y[:100].std(), rel=0.2) and c.baseline == 100
    assert control_charts(pd.Series(dates[:2]), pd.Series(y[:2])) is None


def test_plot_with_trend_ewma_and_cusum(cfg_and_df):
    cfg, _ = cfg_and_df
    n = 200
    dates, y = _series(n=n)
    y[120:] += 2
    data = pd.DataFrame({"ID": [f"B{i}" for i in range(n)], "DT": dates, "SITE": "A", "VAL": y})
    data[SET_COLUMN] = [BACKGROUND_LABEL] * (n - 1) + [INTEREST_LABEL]
    trend = fit_trend(data["DT"], data["VAL"])
    c = control_charts(data["DT"], data["VAL"])
    fig = timeline_scatter(data, cfg, data["VAL"], "VAL", trend=trend, ewma=c, cusum=c)
    names = [t.name or "" for t in fig.data]
    assert any(n.startswith("EWMA (") for n in names) and "CUSUM C+" in names
    assert {t.yaxis for t in fig.data if (t.name or "").startswith("CUSUM")} == {"y2"}
    table = context_table(data, cfg, data["VAL"], trend, charts=c)
    assert table[CUSUM_SIGNAL].iloc[0]


def test_trend_on_many_batches_uses_blocks():
    dates, y = _series(n=6000)
    y[4000:] += 0.5
    fit = fit_trend(dates, y, max_candidates=500)  # blocks of 12 batches
    assert fit.model == "shifts" and len(fit.breakpoints) == 1
    assert abs((fit.breakpoints[0] - dates[4000]).days) <= 12


def test_default_date_ranges():
    assert current_week(date(2026, 9, 24)) == (date(2026, 9, 21), date(2026, 9, 27))  # Thursday
    assert current_week(date(2026, 9, 21)) == (date(2026, 9, 21), date(2026, 9, 27))  # Monday
    assert past_year(date(2026, 9, 24)) == (date(2025, 9, 24), date(2026, 9, 24))
    assert past_year(date(2028, 2, 29)) == (date(2027, 2, 28), date(2028, 2, 29))


def test_app_runs_with_all_overlays():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(Path(__file__).parent.parent / "app.py"), default_timeout=120)
    at.session_state["interest_mode"] = SelectionMode.MANUAL
    at.session_state["interest_manual"] = ["CT26-01999"]
    at.session_state["background_mode"] = SelectionMode.ALL
    at.run()
    assert not at.exception
    at.selectbox(key="timeline_parameter").select("Apheresis Volume (mL)").run()
    at.checkbox(key="timeline_ewma").check().run()
    at.checkbox(key="timeline_cusum").check().run()
    assert not at.exception
    assert not at.metric
    assert any("Apheresis Volume (mL)" in m.value for m in at.markdown)  # the title
    assert any("EWMA signal" in d.value.columns for d in at.dataframe)  # the batch table


def test_parameter_search_needs_every_word_and_ranks_name_matches_first():
    params = pd.DataFrame({
        "name": ["Viable Cell Yield (%)", "Glucose", "Cell Count"],
        "type": ["numeric"] * 3,
        "description": ["", "Viable cell yield proxy", "Total cells"],
    })
    assert search_parameters(params, "viable YIELD")["name"].tolist() == ["Viable Cell Yield (%)", "Glucose"]
    assert search_parameters(params, "cell total")["name"].tolist() == ["Cell Count"]
    assert search_parameters(params, "  ")["name"].tolist() == params["name"].tolist()
    assert highlight("CUSUM limits `cusum`", "cusum") == "<mark>CUSUM</mark> limits `cusum`"


def test_help_file_parses_into_unique_sections():
    intro, sections = parse_help(HELP_FILE.read_text(encoding="utf-8"))
    assert intro and len(sections) > 20
    assert len({s.anchor for s in sections}) == len(sections)
    assert all(s.body.strip() or s.level == 2 for s in sections)
    assert {s.parent for s in sections if s.level == 3} <= {s.title for s in sections if s.level == 2}


def test_help_page_search():
    from streamlit.testing.v1 import AppTest

    def script():
        import streamlit as st

        from cart_dashboard.views import help_page

        help_page.render(back_to=st.Page(lambda: None, title="Dashboard", url_path="dashboard"))

    at = AppTest.from_function(script).run()
    assert not at.exception
    all_headers = len(at.header) + len(at.subheader)
    at.text_input(key="help_search").input("cusum decision").run()
    assert not at.exception and 0 < len(at.header) + len(at.subheader) < all_headers
    assert any("<mark>" in m.value for m in at.markdown)
