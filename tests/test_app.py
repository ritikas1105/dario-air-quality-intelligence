import json
import shutil
from pathlib import Path

import pandas as pd
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest


@pytest.fixture
def dashboard(tmp_path):
    """Exercise the real app against isolated data, including stale AQI labels."""
    shutil.copyfile(Path(__file__).resolve().parents[1] / "app.py", tmp_path / "app.py")
    processed = tmp_path / "data" / "processed"
    processed.mkdir(parents=True)
    rows = []
    for city, values in {
        "Alpha": [40, 200],
        "Beta": [30, 120],
        "Gamma": [None, float("inf"), -1, float("-inf")],
    }.items():
        for hour, value in enumerate(values):
            rows.append({
                "city": city,
                "country": "Example",
                "timestamp": f"2026-09-18 {hour:02d}:00:00",
                "us_aqi": value,
                "pm2_5": 10,
                "aqi_category": "Unknown",
                "is_elevated_aqi": True,
                "is_unhealthy_aqi": True,
            })
    pd.DataFrame(rows).to_csv(processed / "air_quality_hourly.csv", index=False)
    pd.DataFrame([{"check": "fixture", "status": "PASS"}]).to_csv(
        processed / "data_quality_report.csv", index=False
    )
    (processed / "etl_run_metadata.json").write_text(json.dumps({"row_count": len(rows)}))
    st.cache_data.clear()
    app = AppTest.from_file(str(tmp_path / "app.py"), default_timeout=20).run()
    assert not app.exception
    yield app
    st.cache_data.clear()


def metrics(app):
    return {metric.label: metric.value for metric in app.metric}


def test_default_dashboard_excludes_invalid_aqi_from_metrics_and_ranking(dashboard):
    assert dashboard.title[0].value == "Air Quality Operational Intelligence"
    values = metrics(dashboard)
    assert values["Average AQI"] == "98"
    assert values["Peak AQI"] == "200"
    assert values["Hours AQI > 100"] == "2"
    assert dashboard.dataframe[0].value["city"].tolist() == ["Alpha", "Beta"]
    assert any("Gamma" in caption.value for caption in dashboard.caption)
    assert "Unavailable" in dashboard.sidebar.multiselect[1].options
    assert "Unknown" not in dashboard.sidebar.multiselect[1].options
    assert len(dashboard.get("plotly_chart")) == 3
    assert any("AQI coverage: 50.0%" in caption.value for caption in dashboard.caption)


def test_good_category_keeps_kpis_ranking_narrative_and_charts_consistent(dashboard):
    dashboard.sidebar.multiselect[1].set_value(["Good"]).run()
    assert not dashboard.exception
    values = metrics(dashboard)
    assert values["Cities monitored"] == "2"
    assert values["Average AQI"] == "35"
    assert values["Peak AQI"] == "40"
    assert values["Hours AQI > 100"] == "0"
    table = dashboard.dataframe[0].value
    assert table["city"].tolist() == ["Alpha", "Beta"]
    assert table["avg_aqi"].tolist() == [40, 30]
    assert table["max_aqi"].tolist() == [40, 30]
    assert table["elevated_aqi_hours"].tolist() == [0, 0]
    assert table["aqi_coverage_pct"].tolist() == [100, 100]
    assert table["elevated_pct"].tolist() == [0, 0]
    assert "**Alpha**" in dashboard.info[0].value
    assert "peak AQI of 40" in dashboard.info[0].value
    charts = [json.loads(chart.proto.spec) for chart in dashboard.get("plotly_chart")]
    assert {trace["name"] for trace in charts[0]["data"]} == {"Alpha", "Beta"}
    assert sorted(value for trace in charts[0]["data"] for value in trace["y"]) == [30, 40]
    assert set(charts[1]["data"][0]["x"]) == {"Alpha", "Beta"}
    assert [trace["name"] for trace in charts[2]["data"]] == ["Good"]
    assert sum(charts[2]["data"][0]["y"]) == 2


@pytest.mark.parametrize("cities,average,peak,hours", [
    (["Beta"], "75", "120", "1"),
    (["Alpha", "Beta"], "98", "200", "2"),
])
def test_city_filters_update_metrics_and_ranking(dashboard, cities, average, peak, hours):
    dashboard.sidebar.multiselect[0].set_value(cities).run()
    assert not dashboard.exception
    values = metrics(dashboard)
    assert values["Cities monitored"] == str(len(cities))
    assert values["Average AQI"] == average
    assert values["Peak AQI"] == peak
    assert values["Hours AQI > 100"] == hours
    table = dashboard.dataframe[0].value
    assert set(table["city"]) == set(cities)
    assert table["priority_rank"].tolist() == list(range(1, len(cities) + 1))
    assert f"**{table.iloc[0]['city']}**" in dashboard.info[0].value


@pytest.mark.parametrize("selection", ["category", "city"])
def test_zero_valid_aqi_has_explicit_unavailable_state(dashboard, selection):
    if selection == "category":
        dashboard.sidebar.multiselect[1].set_value(["Unavailable"])
    else:
        dashboard.sidebar.multiselect[0].set_value(["Gamma"])
    dashboard.run()
    assert not dashboard.exception
    assert [info.value for info in dashboard.info] == ["AQI unavailable for the selected scope."]
    assert not dashboard.metric
    assert not dashboard.dataframe
    assert not dashboard.get("plotly_chart")
    assert any("AQI coverage: 0.0%" in caption.value for caption in dashboard.caption)


def test_partial_coverage_and_completeness_warnings_are_visible(dashboard, tmp_path):
    processed = tmp_path / "data" / "processed"
    hourly = pd.read_csv(processed / "air_quality_hourly.csv").iloc[:2].copy()
    hourly["us_aqi"] = [120, float("nan")]
    hourly.to_csv(processed / "air_quality_hourly.csv", index=False)
    pd.DataFrame([{"check": "aqi_completeness", "status": "WARN"}]).to_csv(
        processed / "data_quality_report.csv", index=False
    )
    st.cache_data.clear()
    app = AppTest.from_file(str(tmp_path / "app.py"), default_timeout=20).run()
    assert not app.exception
    assert metrics(app)["Completeness warnings"] == "1"
    assert metrics(app)["Failed checks"] == "0"
    assert any("AQI coverage: 50.0%" in caption.value for caption in app.caption)
    row = app.dataframe[0].value.iloc[0]
    assert row.expected_hours == 2
    assert row.valid_aqi_hours == 1
    assert row.elevated_pct == 100
    assert row.aqi_coverage_pct == 50
    assert "100.0% elevated among available AQI hours" in app.info[0].value


@pytest.mark.parametrize("selection", ["combination", "no cities", "no categories"])
def test_empty_filtered_scope_stops_gracefully(dashboard, selection):
    if selection == "combination":
        dashboard.sidebar.multiselect[0].set_value(["Beta"])
        dashboard.sidebar.multiselect[1].set_value(["Unhealthy"])
    elif selection == "no cities":
        dashboard.sidebar.multiselect[0].set_value([])
    else:
        dashboard.sidebar.multiselect[1].set_value([])
    dashboard.run()
    assert not dashboard.exception
    assert [warning.value for warning in dashboard.warning] == ["No rows match the current filters."]
    assert not dashboard.metric
    assert not dashboard.dataframe
    assert not dashboard.get("plotly_chart")


def test_rerun_reads_refreshed_files(dashboard, tmp_path):
    hourly_path = tmp_path / 'data/processed/air_quality_hourly.csv'
    hourly = pd.read_csv(hourly_path)
    hourly['us_aqi'] = 10
    hourly.to_csv(hourly_path, index=False)
    dashboard.run()
    assert not dashboard.exception
    assert metrics(dashboard)['Average AQI'] == '10'
    assert metrics(dashboard)['Peak AQI'] == '10'
