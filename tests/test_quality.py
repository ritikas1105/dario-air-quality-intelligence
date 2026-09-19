import pandas as pd
import pytest

from src.quality import run_quality_checks


def test_quality_checks_pass_for_valid_frame():
    df = pd.DataFrame(
        {
            "city": ["A"],
            "country": ["X"],
            "timestamp": [pd.Timestamp("2026-09-18T00:00:00")],
            "us_aqi": [50],
            "pm2_5": [5.0],
            "pm10": [10.0],
            "nitrogen_dioxide": [8.0],
            "ozone": [20.0],
            "sulphur_dioxide": [1.0],
            "carbon_monoxide": [80.0],
        }
    )
    report = run_quality_checks(df, ["A"])
    assert (report["status"] == "PASS").all()


def valid_frame():
    return pd.DataFrame({
        "city": ["A"], "country": ["X"], "timestamp": ["2026-09-18T00:00:00"],
        "us_aqi": [50.0], "pm2_5": [5.0], "pm10": [10.0],
        "nitrogen_dioxide": [8.0], "ozone": [20.0],
        "sulphur_dioxide": [1.0], "carbon_monoxide": [80.0],
    })


def report_for(df):
    return run_quality_checks(df, ["A"]).set_index("check")


def test_null_aqi_is_completeness_warning_only():
    df = valid_frame().assign(us_aqi=float("nan"))
    report = report_for(df)
    assert report.loc["aqi_completeness", "status"] == "WARN"
    assert report.loc["aqi_completeness", "affected_rows"] == 1
    assert report.loc["aqi_plausible_range", "status"] == "PASS"
    assert report.loc["finite_numeric_measurements", "status"] == "PASS"
    assert not (report.status == "FAIL").any()


def test_multiple_missing_cells_count_one_affected_row():
    df = valid_frame().assign(pm2_5=float("nan"), pm10=float("nan"))
    report = report_for(df)
    assert report.loc["pollutant_completeness", "status"] == "WARN"
    assert report.loc["pollutant_completeness", "affected_rows"] == 1
    assert report.loc["non_negative_pollutants", "status"] == "PASS"
    assert report.loc["finite_numeric_measurements", "status"] == "PASS"


@pytest.mark.parametrize("column,value,check", [
    ("us_aqi", -1, "aqi_plausible_range"),
    ("us_aqi", 1001, "aqi_plausible_range"),
    ("pm2_5", -1, "non_negative_pollutants"),
    ("pm2_5", float("inf"), "finite_numeric_measurements"),
    ("pm10", float("-inf"), "finite_numeric_measurements"),
    ("us_aqi", float("inf"), "finite_numeric_measurements"),
    ("us_aqi", "bad", "finite_numeric_measurements"),
])
def test_populated_invalid_values_fail(column, value, check):
    report = report_for(valid_frame().assign(**{column: value}))
    assert report.loc[check, "status"] == "FAIL"
    assert report.loc[check, "affected_rows"] == 1
    assert report.loc["aqi_completeness", "status"] == "PASS"
    assert report.loc["pollutant_completeness", "status"] == "PASS"
    if check == "finite_numeric_measurements":
        assert report.loc["aqi_plausible_range", "status"] == "PASS"


@pytest.mark.parametrize("column,value,check", [
    ("city", None, "required_identifiers"),
    ("city", "  ", "required_identifiers"),
    ("timestamp", None, "valid_timestamps"),
    ("timestamp", "invalid", "valid_timestamps"),
])
def test_structural_problems_remain_failures(column, value, check):
    report = report_for(valid_frame().assign(**{column: value}))
    assert report.loc[check, "status"] == "FAIL"
    assert report.loc[check, "affected_rows"] == 1


def test_missing_columns_and_cities_have_row_based_counts():
    df = pd.concat([valid_frame()] * 3, ignore_index=True)
    report = report_for(df.drop(columns=["pm2_5", "pm10"]))
    assert report.loc["required_columns", "status"] == "FAIL"
    assert report.loc["required_columns", "affected_rows"] == 3
    empty_report = report_for(df.iloc[:0])
    assert empty_report.loc["expected_city_coverage", "status"] == "FAIL"
    assert empty_report.loc["expected_city_coverage", "affected_rows"] == 0
    assert report_for(df).loc["duplicate_city_timestamp", "affected_rows"] == 3
