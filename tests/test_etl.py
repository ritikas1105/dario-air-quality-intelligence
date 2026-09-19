import copy
import json
import logging
from unittest.mock import Mock

import pandas as pd
import pytest
import requests

import etl
from src.quality import POLLUTANT_COLUMNS, run_quality_checks
from src.schema import APIResponseValidationError, validate_city_payload
from src.transform import build_city_summary, transform_city_payload


def payload():
    return {
        "latitude": 10.0, "longitude": 20.0, "timezone": "UTC",
        "hourly": {"time": ["2026-09-18T00:00", "2026-09-18T01:00"],
                   "us_aqi": [40, 120], **{field: [5.0, 10.0] for field in POLLUTANT_COLUMNS}},
    }


def response(body):
    result = Mock()
    result.json.return_value = body
    return result


@pytest.mark.parametrize("body,message", [
    ([], "Expected API response object, received list"),
    ({}, "Missing required response field: hourly"),
    ({"hourly": []}, "Expected hourly object, received list"),
    ({"hourly": None}, "Expected hourly object, received NoneType"),
    ({"hourly": {"us_aqi": [20]}}, "Missing required hourly field: time"),
    ({"hourly": {"time": ["2026-09-18T00:00"]}}, "Missing required hourly field: us_aqi"),
    ({"hourly": {"time": ["2026-09-18T00:00"], "us_aqi": []}},
     "Hourly field us_aqi length 0 does not match time length 1"),
    ({"hourly": {"time": [], "us_aqi": []}}, "Hourly time array must not be empty"),
    ({"hourly": {"time": "bad", "us_aqi": [20]}}, "Hourly field time must be an array"),
    ({"hourly": {"time": ["2026-09-18T00:00"], "us_aqi": 20}}, "Hourly field us_aqi must be an array"),
])
def test_invalid_response_is_an_intentional_error_at_both_entry_points(body, message):
    session = Mock()
    session.get.return_value = response(body)
    with pytest.raises(APIResponseValidationError, match=message):
        etl.extract_city(session, "Delhi", etl.CITIES["Delhi"])
    with pytest.raises(APIResponseValidationError, match=message):
        transform_city_payload("Delhi", "India", body)


@pytest.mark.parametrize("field,value,message", [
    ("pm2_5", [1], "length 1 does not match time length 2"),
    ("pm10", None, "must be an array"),
    ("us_aqi", [{}, 20], "must be a number or null"),
    ("us_aqi", [True, 20], "must be a number or null"),
    ("time", [[], "2026-09-18T01:00"], "must be a non-empty timestamp string"),
])
def test_malformed_present_arrays_fail_before_pandas(field, value, message):
    body = payload()
    body["hourly"][field] = value
    with pytest.raises(APIResponseValidationError, match=message):
        transform_city_payload("Delhi", "India", body)


@pytest.mark.parametrize("missing", [["pm10"], ["pm2_5"], POLLUTANT_COLUMNS])
def test_missing_pollutants_degrade_without_losing_aqi(missing):
    body = payload()
    for field in missing:
        del body["hourly"][field]
    original = copy.deepcopy(body)
    frame = transform_city_payload("Delhi", "India", body)
    assert body == original
    assert frame[missing].isna().all().all()
    assert frame.us_aqi.tolist() == [40, 120]
    quality = run_quality_checks(frame, ["Delhi"]).set_index("check")
    assert quality.loc["pollutant_completeness", "status"] == "WARN"
    assert not (quality.status == "FAIL").any()
    summary = build_city_summary(frame).iloc[0]
    if "pm2_5" in missing:
        assert pd.isna(summary.operational_priority_score)
        assert pd.isna(summary.priority_rank)
    else:
        assert summary.priority_rank == 1


def test_supported_sequences_nulls_and_extra_fields():
    body = payload()
    body["hourly"]["time"] = tuple(body["hourly"]["time"])
    body["hourly"]["us_aqi"] = (40, None)
    body["hourly"]["extra_api_field"] = {"unrelated": "metadata"}
    frame = transform_city_payload("Delhi", "India", body)
    assert len(frame) == 2
    assert frame.aqi_category.tolist() == ["Good", "Unavailable"]
    assert "extra_api_field" not in frame


@pytest.fixture
def isolated_run(tmp_path, monkeypatch):
    monkeypatch.setattr(etl, "BASE_DIR", tmp_path)
    monkeypatch.setattr(etl, "RAW_DIR", tmp_path / "data/raw")
    monkeypatch.setattr(etl, "PROCESSED_DIR", tmp_path / "data/processed")
    monkeypatch.setattr(etl, "CITIES", {name: etl.CITIES[name] for name in ("Mumbai", "Delhi")})
    session = Mock()
    monkeypatch.setattr(etl, "build_session", lambda: session)
    return session


@pytest.mark.parametrize("bad_body", [[], {"hourly": {"time": ["2026-09-18T00:00"]}}])
def test_bad_city_is_recorded_and_valid_city_completes(isolated_run, caplog, bad_body):
    isolated_run.get.side_effect = [response(bad_body), response(payload())]
    with caplog.at_level(logging.INFO):
        etl.main()
    metadata = json.loads((etl.PROCESSED_DIR / "etl_run_metadata.json").read_text())
    assert metadata["successful_cities"] == ["Delhi"]
    failure = metadata["failed_cities"][0]
    assert set(failure) == {"city", "stage", "error_type", "message"}
    assert failure["city"] == "Mumbai"
    assert failure["stage"] == "validate"
    assert failure["error_type"] == "schema_validation"
    assert "Traceback" not in failure["message"]
    assert metadata["row_count"] == 2
    assert pd.read_csv(etl.PROCESSED_DIR / "air_quality_hourly.csv").city.unique().tolist() == ["Delhi"]
    assert len(list(etl.RAW_DIR.glob("*.json"))) == 1
    assert "Failed city Mumbai" in caplog.text
    assert "Processed Delhi" in caplog.text
    assert "Partial run: 1/2 cities failed" in caplog.text


@pytest.mark.parametrize("previous_outputs", [False, True])
def test_total_failure_preserves_previous_outputs(isolated_run, caplog, previous_outputs):
    etl.PROCESSED_DIR.mkdir(parents=True)
    names = ["air_quality_hourly.csv", "city_summary.csv", "data_quality_report.csv", "etl_run_metadata.json"]
    if previous_outputs:
        for name in names:
            (etl.PROCESSED_DIR / name).write_text("previous " + name)
    before = {path.name: path.read_bytes() for path in etl.PROCESSED_DIR.iterdir()}
    isolated_run.get.side_effect = [response([]), response({})]
    with pytest.raises(RuntimeError, match="no city data could be extracted"):
        etl.main()
    assert {path.name: path.read_bytes() for path in etl.PROCESSED_DIR.iterdir()} == before
    assert not list(etl.RAW_DIR.glob("*.json"))
    assert "all 2 configured cities failed" in caplog.text


def test_optional_pm_absence_completes_entire_etl(isolated_run):
    body = payload()
    del body["hourly"]["pm2_5"]
    isolated_run.get.side_effect = [response(body), response(payload())]
    etl.main()
    summary = pd.read_csv(etl.PROCESSED_DIR / "city_summary.csv").set_index("city")
    assert pd.isna(summary.loc["Mumbai", "priority_rank"])
    assert summary.loc["Delhi", "priority_rank"] == 1
    metadata = json.loads((etl.PROCESSED_DIR / "etl_run_metadata.json").read_text())
    assert metadata["failed_cities"] == []
    assert metadata["quality_warnings"] == 1


@pytest.mark.parametrize("failure_type", ["json", "timeout", "http"])
def test_decode_and_request_failures_are_isolated(isolated_run, failure_type):
    bad = response(None)
    if failure_type == "json":
        bad.json.side_effect = requests.exceptions.JSONDecodeError("Invalid JSON", "x", 0)
        first = bad
    elif failure_type == "timeout":
        first = requests.Timeout("Request timed out")
    else:
        bad.raise_for_status.side_effect = requests.HTTPError("HTTP 500")
        first = bad
    isolated_run.get.side_effect = [first, response(payload())]
    etl.main()
    metadata = json.loads((etl.PROCESSED_DIR / "etl_run_metadata.json").read_text())
    assert metadata["successful_cities"] == ["Delhi"]
    failure = metadata["failed_cities"][0]
    assert failure["city"] == "Mumbai"
    assert failure["stage"] == ("validate" if failure_type == "json" else "fetch")
    if failure_type == "json":
        assert failure["message"] == "API response is not valid JSON"
