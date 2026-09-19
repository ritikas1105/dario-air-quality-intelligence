from __future__ import annotations

from math import isfinite

import pandas as pd


def aqi_category(aqi: float | int | None) -> str:
    if pd.isna(aqi) or not isfinite(aqi) or aqi < 0:
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
    frame["is_elevated_aqi"] = frame["us_aqi"] > 100
    frame["is_unhealthy_aqi"] = frame["us_aqi"] > 150
    frame["date"] = frame["timestamp"].dt.date.astype("string")
    return frame


def build_city_summary(hourly_df: pd.DataFrame) -> pd.DataFrame:
    grouped = hourly_df.groupby(["city", "country"], as_index=False).agg(
        avg_aqi=("us_aqi", "mean"),
        max_aqi=("us_aqi", "max"),
        avg_pm2_5=("pm2_5", "mean"),
        max_pm2_5=("pm2_5", "max"),
        elevated_aqi_hours=("is_elevated_aqi", "sum"),
        unhealthy_aqi_hours=("is_unhealthy_aqi", "sum"),
        observed_hours=("timestamp", "count"),
    )

    grouped["elevated_hour_pct"] = (
        grouped["elevated_aqi_hours"] / grouped["observed_hours"] * 100
    ).round(1)
    grouped["avg_aqi"] = grouped["avg_aqi"].round(1)
    grouped["avg_pm2_5"] = grouped["avg_pm2_5"].round(1)
    grouped["max_pm2_5"] = grouped["max_pm2_5"].round(1)

    # Operational prioritization only. This is intentionally not a clinical risk score.
    grouped["operational_priority_score"] = (
        grouped["elevated_hour_pct"] * 0.5
        + grouped["max_aqi"].clip(upper=300) / 3 * 0.35
        + grouped["avg_pm2_5"].clip(upper=100) * 0.15
    ).round(1)

    grouped = grouped.sort_values(
        ["operational_priority_score", "max_aqi"], ascending=False
    ).reset_index(drop=True)
    grouped["priority_rank"] = grouped.index + 1
    return grouped
