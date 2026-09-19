from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from src.transform import aqi_category, build_city_summary

BASE_DIR = Path(__file__).resolve().parent
PROCESSED_DIR = BASE_DIR / "data" / "processed"

st.set_page_config(
    page_title="Air Quality Operational Intelligence",
    page_icon="🌿",
    layout="wide",
)


@st.cache_data
def load_data() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    hourly_path = PROCESSED_DIR / "air_quality_hourly.csv"
    quality_path = PROCESSED_DIR / "data_quality_report.csv"
    metadata_path = PROCESSED_DIR / "etl_run_metadata.json"

    required = [hourly_path, quality_path, metadata_path]
    missing = [path.name for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError(
            "Missing processed outputs: "
            + ", ".join(missing)
            + ". Run `python etl.py` first."
        )

    hourly = pd.read_csv(hourly_path, parse_dates=["timestamp"])
    # Reclassify persisted data so older "Unknown" labels and invalid AQI
    # cannot leak into the dashboard's categories, metrics, or ranking.
    hourly["us_aqi"] = pd.to_numeric(hourly["us_aqi"], errors="coerce")
    hourly["aqi_category"] = hourly["us_aqi"].apply(aqi_category)
    hourly.loc[hourly["aqi_category"] == "Unavailable", "us_aqi"] = float("nan")
    hourly["is_elevated_aqi"] = hourly["us_aqi"] > 100
    hourly["is_unhealthy_aqi"] = hourly["us_aqi"] > 150
    quality = pd.read_csv(quality_path)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    return hourly, quality, metadata


st.title("Air Quality Operational Intelligence")
st.caption(
    "A lightweight environmental-health decision product built from the Open-Meteo Air Quality API. "
    "It is designed for operational prioritization, not clinical diagnosis or medical advice."
)

try:
    hourly_df, quality_df, metadata = load_data()
except FileNotFoundError as exc:
    st.error(str(exc))
    st.code("python etl.py\nstreamlit run app.py", language="bash")
    st.stop()

with st.sidebar:
    st.header("Filters")
    available_cities = sorted(hourly_df["city"].unique())
    selected_cities = st.multiselect(
        "Cities",
        options=available_cities,
        default=available_cities,
    )
    categories = list(hourly_df["aqi_category"].dropna().unique())
    selected_categories = st.multiselect(
        "AQI categories",
        options=categories,
        default=categories,
    )
    st.divider()
    st.caption(f"Last ETL run: {metadata.get('completed_at_utc', 'unknown')}")

filtered = hourly_df[
    hourly_df["city"].isin(selected_cities)
    & hourly_df["aqi_category"].isin(selected_categories)
].copy()

if filtered.empty:
    st.warning("No rows match the current filters.")
    st.stop()

if not filtered["us_aqi"].notna().any():
    st.info("AQI unavailable for the selected scope.")
    st.stop()

filtered_summary = build_city_summary(filtered)
unranked = filtered_summary["operational_priority_score"].isna()
if unranked.any():
    st.caption(
        "Priority unavailable for: "
        + ", ".join(filtered_summary.loc[unranked, "city"])
        + ". Insufficient data in the selected scope."
    )
filtered_summary = filtered_summary.loc[~unranked].copy()
filtered_summary["priority_rank"] = range(1, len(filtered_summary) + 1)

kpi1, kpi2, kpi3, kpi4 = st.columns(4)
kpi1.metric("Cities monitored", filtered["city"].nunique())
kpi2.metric("Average AQI", f"{filtered['us_aqi'].mean():.0f}", aqi_category(filtered["us_aqi"].mean()))
kpi3.metric("Peak AQI", f"{filtered['us_aqi'].max():.0f}", aqi_category(filtered["us_aqi"].max()))
kpi4.metric("Hours AQI > 100", int((filtered["us_aqi"] > 100).sum()))

st.subheader("Where attention is needed")
if not filtered_summary.empty:
    leader = filtered_summary.sort_values("operational_priority_score", ascending=False).iloc[0]
    st.info(
        f"**{leader['city']}** ranks highest within the selected scope "
        f"(score {leader['operational_priority_score']:.1f}). It has a peak AQI of "
        f"{leader['max_aqi']:.0f} and {leader['elevated_hour_pct']:.1f}% of observed/forecast hours above AQI 100."
    )

priority_display = filtered_summary[
    [
        "priority_rank",
        "city",
        "country",
        "avg_aqi",
        "max_aqi",
        "avg_pm2_5",
        "elevated_aqi_hours",
        "elevated_hour_pct",
        "operational_priority_score",
    ]
].sort_values("operational_priority_score", ascending=False)
st.dataframe(priority_display, use_container_width=True, hide_index=True)

st.subheader("AQI trend")
trend = filtered.groupby(["timestamp", "city"], as_index=False)["us_aqi"].mean()
fig = px.line(
    trend,
    x="timestamp",
    y="us_aqi",
    color="city",
    markers=False,
    labels={"us_aqi": "US AQI", "timestamp": "Local timestamp"},
)
fig.add_hline(y=100, line_dash="dash", annotation_text="AQI 100")
fig.add_hline(y=150, line_dash="dash", annotation_text="AQI 150")
st.plotly_chart(fig, use_container_width=True)

left, right = st.columns(2)
with left:
    st.subheader("PM2.5 by city")
    pm = (
        filtered.groupby("city", as_index=False)["pm2_5"]
        .mean()
        .sort_values("pm2_5", ascending=False)
    )
    pm_fig = px.bar(pm, x="city", y="pm2_5", labels={"pm2_5": "Average PM2.5 (μg/m³)"})
    st.plotly_chart(pm_fig, use_container_width=True)

with right:
    st.subheader("AQI category mix")
    category_mix = filtered.groupby(["city", "aqi_category"], as_index=False).size()
    category_fig = px.bar(
        category_mix,
        x="city",
        y="size",
        color="aqi_category",
        labels={"size": "Hours", "aqi_category": "AQI category"},
    )
    st.plotly_chart(category_fig, use_container_width=True)

st.subheader("Data quality & pipeline health")
st.caption("Pipeline checks below cover the full ETL run, independently of the city/category filters.")
failed_checks = quality_df[quality_df["status"] == "FAIL"]
q1, q2, q3 = st.columns(3)
q1.metric("Quality checks", len(quality_df))
q2.metric("Failed checks", len(failed_checks))
q3.metric("ETL rows", metadata.get("row_count", len(hourly_df)))

st.dataframe(quality_df, use_container_width=True, hide_index=True)

if metadata.get("failed_cities"):
    st.warning(f"API failures in the latest ETL run: {metadata['failed_cities']}")
else:
    st.success("Latest ETL run completed without city-level API failures.")

with st.expander("How to interpret this product"):
    st.markdown(
        """
        - **US AQI** is used as the main comparable air-quality indicator.
        - **AQI > 100** is treated as an elevated-exposure operating threshold for prioritization.
        - The **operational priority score** is a transparent ranking heuristic using elevated-hour share, peak AQI, and average PM2.5.
        - It is **not a medical or clinical risk score** and should not be used for patient-level decisions.
        - In a real health platform, this environmental context could be joined to consented population/cohort data before downstream outreach or analysis.
        """
    )
