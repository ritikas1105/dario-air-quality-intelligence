from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

import pandas as pd


@dataclass
class QualityCheck:
    check: str
    status: str
    severity: str
    affected_rows: int
    details: str

    def to_dict(self) -> dict:
        return asdict(self)


def _result(check: str, passed: bool, affected: int, details: str, severity: str = "high") -> QualityCheck:
    return QualityCheck(
        check=check,
        status="PASS" if passed else "FAIL",
        severity="info" if passed else severity,
        affected_rows=int(affected),
        details=details,
    )


def run_quality_checks(df: pd.DataFrame, expected_cities: Iterable[str]) -> pd.DataFrame:
    checks: list[QualityCheck] = []

    required_columns = {
        "city",
        "country",
        "timestamp",
        "us_aqi",
        "pm2_5",
        "pm10",
        "nitrogen_dioxide",
        "ozone",
        "sulphur_dioxide",
        "carbon_monoxide",
    }
    missing_columns = required_columns.difference(df.columns)
    checks.append(
        _result(
            "required_columns",
            not missing_columns,
            len(missing_columns),
            "All required columns are present."
            if not missing_columns
            else f"Missing columns: {sorted(missing_columns)}",
        )
    )

    if missing_columns:
        return pd.DataFrame([c.to_dict() for c in checks])

    duplicate_mask = df.duplicated(subset=["city", "timestamp"], keep=False)
    duplicate_count = int(duplicate_mask.sum())
    checks.append(
        _result(
            "duplicate_city_timestamp",
            duplicate_count == 0,
            duplicate_count,
            "No duplicate city/timestamp rows found."
            if duplicate_count == 0
            else "Duplicate city/timestamp records were detected.",
        )
    )

    null_count = int(df[list(required_columns)].isna().sum().sum())
    checks.append(
        _result(
            "required_field_nulls",
            null_count == 0,
            null_count,
            "No nulls in required analytical fields."
            if null_count == 0
            else "Null values found in required analytical fields.",
            severity="medium",
        )
    )

    pollutant_columns = [
        "pm2_5",
        "pm10",
        "nitrogen_dioxide",
        "ozone",
        "sulphur_dioxide",
        "carbon_monoxide",
    ]
    negative_mask = (df[pollutant_columns] < 0).any(axis=1)
    negative_count = int(negative_mask.sum())
    checks.append(
        _result(
            "non_negative_pollutants",
            negative_count == 0,
            negative_count,
            "All pollutant concentrations are non-negative."
            if negative_count == 0
            else "Negative pollutant concentrations were detected.",
        )
    )

    invalid_aqi = (~df["us_aqi"].between(0, 1000, inclusive="both")).fillna(True)
    invalid_aqi_count = int(invalid_aqi.sum())
    checks.append(
        _result(
            "aqi_plausible_range",
            invalid_aqi_count == 0,
            invalid_aqi_count,
            "AQI values are within the configured plausibility range (0-1000)."
            if invalid_aqi_count == 0
            else "AQI values outside the configured plausibility range were detected.",
            severity="medium",
        )
    )

    actual_cities = set(df["city"].dropna().unique())
    expected_cities = set(expected_cities)
    missing_cities = expected_cities - actual_cities
    checks.append(
        _result(
            "expected_city_coverage",
            not missing_cities,
            len(missing_cities),
            "All configured cities are represented in the processed dataset."
            if not missing_cities
            else f"Missing configured cities: {sorted(missing_cities)}",
        )
    )

    unparsable_ts = pd.to_datetime(df["timestamp"], errors="coerce").isna()
    bad_ts_count = int(unparsable_ts.sum())
    checks.append(
        _result(
            "valid_timestamps",
            bad_ts_count == 0,
            bad_ts_count,
            "All timestamps are parseable."
            if bad_ts_count == 0
            else "Unparseable timestamps were detected.",
        )
    )

    return pd.DataFrame([c.to_dict() for c in checks])
