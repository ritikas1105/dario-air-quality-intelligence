from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

import pandas as pd

# Existing broad plausibility limit, shared with analytical validity handling.
MAX_VALID_AQI = 1000
POLLUTANT_COLUMNS = [
    "pm2_5", "pm10", "nitrogen_dioxide", "ozone", "sulphur_dioxide", "carbon_monoxide",
]


def valid_aqi_mask(values: pd.Series) -> pd.Series:
    """Usable AQI is present, numeric, finite, and within the accepted range."""
    numeric = pd.to_numeric(values, errors="coerce")
    return numeric.between(0, MAX_VALID_AQI).fillna(False)


@dataclass
class QualityCheck:
    check: str
    status: str
    severity: str
    affected_rows: int
    details: str

    def to_dict(self) -> dict:
        return asdict(self)


def _result(
    check: str, affected: int, details: str, *, failed: bool | None = None,
    warning: bool = False,
) -> QualityCheck:
    failed = affected > 0 if failed is None else failed
    return QualityCheck(
        check=check,
        status=("WARN" if warning else "FAIL") if failed else "PASS",
        severity=("medium" if warning else "high") if failed else "info",
        affected_rows=int(affected),
        details=details,
    )


def run_quality_checks(df: pd.DataFrame, expected_cities: Iterable[str]) -> pd.DataFrame:
    """Count affected rows per check, never cells or missing-city counts.

    Dataset-level failures with no identifiable existing rows have a count of
    zero; their status and details still record the failure. Counts across checks
    overlap and must not be summed into a total number of bad rows.
    """
    checks: list[QualityCheck] = []
    required_columns = {"city", "country", "timestamp", "us_aqi", *POLLUTANT_COLUMNS}
    missing_columns = required_columns.difference(df.columns)
    checks.append(_result(
        "required_columns", len(df) if missing_columns else 0,
        f"Missing columns: {sorted(missing_columns)}" if missing_columns
        else "All required columns are present.",
        failed=bool(missing_columns),
    ))
    if missing_columns:
        return pd.DataFrame([c.to_dict() for c in checks])

    missing_identifier = pd.Series(False, index=df.index)
    for column in ("city", "country"):
        missing_identifier |= df[column].isna() | df[column].astype("string").str.strip().eq("").fillna(False)
    checks.append(_result("required_identifiers", missing_identifier.sum(),
                          "City and country identifiers must be populated."))
    checks.append(_result(
        "duplicate_city_timestamp", df.duplicated(["city", "timestamp"], keep=False).sum(),
        "Analytical keys (city, timestamp) must be unique.",
    ))
    checks.append(_result(
        "valid_timestamps", pd.to_datetime(df["timestamp"], errors="coerce").isna().sum(),
        "Timestamps must be populated and parseable.",
    ))
    checks.append(_result("aqi_completeness", df["us_aqi"].isna().sum(),
                          "Rows with unavailable AQI measurements.", warning=True))
    checks.append(_result(
        "pollutant_completeness", df[POLLUTANT_COLUMNS].isna().any(axis=1).sum(),
        "Rows with at least one unavailable pollutant measurement (each row counted once).",
        warning=True,
    ))

    measurements = df[["us_aqi", *POLLUTANT_COLUMNS]]
    numeric = measurements.apply(pd.to_numeric, errors="coerce")
    nonfinite = numeric.isin([float("inf"), float("-inf")])
    invalid_numeric = measurements.notna() & (numeric.isna() | nonfinite)
    checks.append(_result(
        "finite_numeric_measurements", invalid_numeric.any(axis=1).sum(),
        "Populated measurements must be numeric and finite; nulls are completeness warnings.",
    ))
    finite_aqi = numeric["us_aqi"].notna() & ~nonfinite["us_aqi"]
    checks.append(_result(
        "aqi_plausible_range",
        (finite_aqi & ~numeric["us_aqi"].between(0, MAX_VALID_AQI)).sum(),
        f"Finite AQI measurements must be within 0–{MAX_VALID_AQI}; nulls are excluded.",
    ))
    negative = numeric[POLLUTANT_COLUMNS].lt(0) & ~nonfinite[POLLUTANT_COLUMNS]
    checks.append(_result(
        "non_negative_pollutants", negative.any(axis=1).sum(),
        "Populated finite pollutant measurements must be non-negative.",
    ))
    missing_cities = set(expected_cities) - set(df["city"].dropna().unique())
    checks.append(_result(
        "expected_city_coverage", 0,
        f"Missing configured cities: {sorted(missing_cities)}; no existing rows to count."
        if missing_cities else "All configured cities are represented.",
        failed=bool(missing_cities),
    ))
    return pd.DataFrame([c.to_dict() for c in checks])
