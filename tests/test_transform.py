import pandas as pd
import pytest

from src.transform import aqi_category, build_city_summary, transform_city_payload


@pytest.mark.parametrize("value", [None, float("nan"), pd.NA, float("inf"), float("-inf"), -1])
def test_invalid_aqi_is_unavailable(value):
    assert aqi_category(value) == "Unavailable"


def test_aqi_category_boundaries():
    assert aqi_category(0) == "Good"
    assert aqi_category(50) == "Good"
    assert aqi_category(51) == "Moderate"
    assert aqi_category(100) == "Moderate"
    assert aqi_category(101) == "Unhealthy for Sensitive Groups"
    assert aqi_category(150) == "Unhealthy for Sensitive Groups"
    assert aqi_category(151) == "Unhealthy"
    assert aqi_category(200) == "Unhealthy"
    assert aqi_category(201) == "Very Unhealthy"
    assert aqi_category(300) == "Very Unhealthy"
    assert aqi_category(301) == "Hazardous"


def test_transform_and_summary():
    payload = {
        "latitude": 10.0,
        "longitude": 20.0,
        "timezone": "UTC",
        "hourly": {
            "time": ["2026-09-18T00:00", "2026-09-18T01:00"],
            "us_aqi": [40, 120],
            "pm2_5": [8, 40],
            "pm10": [20, 60],
            "nitrogen_dioxide": [10, 15],
            "ozone": [40, 80],
            "sulphur_dioxide": [2, 3],
            "carbon_monoxide": [100, 120],
        },
    }
    frame = transform_city_payload("Test City", "Testland", payload)
    assert len(frame) == 2
    assert frame["is_elevated_aqi"].sum() == 1

    summary = build_city_summary(frame)
    assert summary.iloc[0]["city"] == "Test City"
    assert summary.iloc[0]["elevated_aqi_hours"] == 1


def summary_frame(values, pm=None):
    return pd.DataFrame({
        "city": ["A"] * len(values), "country": ["X"] * len(values),
        "timestamp": pd.date_range("2026-09-18", periods=len(values), freq="h"),
        "us_aqi": values, "pm2_5": pm if pm is not None else [10.0] * len(values),
    })


def test_elevated_percentage_and_coverage_use_separate_denominators():
    row = build_city_summary(summary_frame([120, float("nan")])).iloc[0]
    assert row.expected_hours == 2
    assert row.valid_aqi_hours == 1
    assert row.elevated_aqi_hours == 1
    assert row.unhealthy_aqi_hours == 0
    assert row.elevated_pct == 100
    assert row.aqi_coverage_pct == 50
    assert row.operational_priority_score == 65.5
    assert row.priority_rank == 1


def test_all_missing_aqi_has_coverage_but_no_percentage_score_or_rank():
    row = build_city_summary(summary_frame([float("nan"), float("nan")])).iloc[0]
    assert row.expected_hours == 2
    assert row.valid_aqi_hours == 0
    assert row.aqi_coverage_pct == 0
    assert pd.isna(row.elevated_pct)
    assert pd.isna(row.operational_priority_score)
    assert pd.isna(row.priority_rank)


def test_invalid_aqi_does_not_affect_counts_means_or_rank():
    frame = summary_frame([120, float("inf"), float("-inf"), -1, 1001])
    frame["is_elevated_aqi"] = True  # Stale persisted flags must not be trusted.
    row = build_city_summary(frame).iloc[0]
    assert row.valid_aqi_hours == 1
    assert row.elevated_aqi_hours == 1
    assert row.unhealthy_aqi_hours == 0
    assert row.avg_aqi == row.max_aqi == 120
    assert row.aqi_coverage_pct == 20
    assert row.elevated_pct == 100
    assert aqi_category(1001) == "Unavailable"


@pytest.mark.parametrize("pm", [[float("inf"), -1], [float("nan"), float("nan")]])
def test_no_usable_pm_cannot_generate_priority_score(pm):
    row = build_city_summary(summary_frame([120, 160], pm)).iloc[0]
    assert pd.isna(row.operational_priority_score)
    assert pd.isna(row.priority_rank)
    assert row.elevated_pct == 100


def test_empty_summary_is_safe_and_unavailable_cities_are_not_ranked():
    assert build_city_summary(summary_frame([])).empty
    frame = pd.concat([
        summary_frame([float("nan")]),
        summary_frame([160]).assign(city="B"),
    ], ignore_index=True)
    result = build_city_summary(frame).set_index("city")
    assert result.loc["B", "priority_rank"] == 1
    assert pd.isna(result.loc["A", "priority_rank"])
