from __future__ import annotations

from math import isfinite

import pandas as pd

from src.quality import MAX_VALID_AQI, valid_aqi_mask


def aqi_category(aqi: float | int | None) -> str:
    if pd.isna(aqi) or not isfinite(aqi) or not 0 <= aqi <= MAX_VALID_AQI:
        return "Unavailable"
    if aqi <= 50:
        return "Good"
    if aqi <= 100:
        return "Moderate"
    if aqi <= 150:
        return "Unhealthy for Sensitive Groups"
    if aqi <= 200:
        return "Unhealthy"
    if aqi <= 300:
        return "Very Unhealthy"
    return "Hazardous"


def transform_city_payload(city: str, country: str, payload: dict) -> pd.DataFrame:
    hourly = payload.get("hourly") or {}
    times = hourly.get("time") or []

    if not times:
        raise ValueError(f"No hourly observations returned for {city}.")

    frame = pd.DataFrame(hourly)
    frame.insert(0, "city", city)
    frame.insert(1, "country", country)
    frame["latitude"] = payload.get("latitude")
    frame["longitude"] = payload.get("longitude")
    frame["timezone"] = payload.get("timezone")
    frame["timestamp"] = pd.to_datetime(frame.pop("time"), errors="coerce")

    numeric_columns = [
        "us_aqi",
        "pm2_5",
        "pm10",
        "nitrogen_dioxide",
        "ozone",
        "sulphur_dioxide",
        "carbon_monoxide",
    ]
    for column in numeric_columns:
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")

    frame["aqi_category"] = frame["us_aqi"].apply(aqi_category)
    valid_aqi = valid_aqi_mask(frame["us_aqi"])
    frame["is_elevated_aqi"] = valid_aqi & (frame["us_aqi"] > 100)
    frame["is_unhealthy_aqi"] = valid_aqi & (frame["us_aqi"] > 150)
    frame["date"] = frame["timestamp"].dt.date.astype("string")
    return frame


def build_city_summary(hourly_df: pd.DataFrame) -> pd.DataFrame:
    """Summarize available measurements; expected hours means input rows, not a calendar grid."""
    frame = hourly_df.copy()
    frame["us_aqi"] = pd.to_numeric(frame["us_aqi"], errors="coerce").where(
        valid_aqi_mask(frame["us_aqi"])
    )
    pm = pd.to_numeric(frame["pm2_5"], errors="coerce").replace(
        [float("inf"), float("-inf")], float("nan")
    )
    frame["pm2_5"] = pm.where(pm >= 0)
    frame["is_elevated_aqi"] = frame["us_aqi"] > 100
    frame["is_unhealthy_aqi"] = frame["us_aqi"] > 150
    grouped = frame.groupby(["city", "country"], as_index=False).agg(
        avg_aqi=("us_aqi", "mean"),
        max_aqi=("us_aqi", "max"),
        avg_pm2_5=("pm2_5", "mean"),
        max_pm2_5=("pm2_5", "max"),
        elevated_aqi_hours=("is_elevated_aqi", "sum"),
        unhealthy_aqi_hours=("is_unhealthy_aqi", "sum"),
        expected_hours=("timestamp", "size"),
        valid_aqi_hours=("us_aqi", "count"),
    )

    grouped["aqi_coverage_pct"] = (
        grouped["valid_aqi_hours"] / grouped["expected_hours"].replace(0, float("nan")) * 100
    ).round(1)
    grouped["elevated_pct"] = (
        grouped["elevated_aqi_hours"] / grouped["valid_aqi_hours"].replace(0, float("nan")) * 100
    ).round(1)
    grouped["avg_aqi"] = grouped["avg_aqi"].round(1)
    grouped["avg_pm2_5"] = grouped["avg_pm2_5"].round(1)
    grouped["max_pm2_5"] = grouped["max_pm2_5"].round(1)

    # Operational prioritization only. This is intentionally not a clinical risk score.
    grouped["operational_priority_score"] = (
        grouped["elevated_pct"] * 0.5
        + grouped["max_aqi"].clip(upper=300) / 3 * 0.35
        + grouped["avg_pm2_5"].clip(upper=100) * 0.15
    ).round(1)
    # Unavailable scores remain null and must never receive a priority rank.
    grouped["operational_priority_score"] = grouped["operational_priority_score"].replace(
        [float("inf"), float("-inf")], float("nan")
    )

    grouped = grouped.sort_values(
        ["operational_priority_score", "max_aqi"], ascending=False
    ).reset_index(drop=True)
    ranked = grouped["operational_priority_score"].notna()
    grouped["priority_rank"] = pd.Series(pd.NA, index=grouped.index, dtype="Int64")
    grouped.loc[ranked, "priority_rank"] = range(1, int(ranked.sum()) + 1)
    return grouped
