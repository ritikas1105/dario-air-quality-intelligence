from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.config import (
    API_URL,
    CITIES,
    FORECAST_DAYS,
    HOURLY_VARIABLES,
    PAST_DAYS,
    REQUEST_TIMEOUT_SECONDS,
)
from src.quality import run_quality_checks
from src.schema import APIResponseValidationError, validate_city_payload
from src.transform import build_city_summary, transform_city_payload

BASE_DIR = Path(__file__).resolve().parent
RAW_DIR = BASE_DIR / "data" / "raw"
PROCESSED_DIR = BASE_DIR / "data" / "processed"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
LOGGER = logging.getLogger(__name__)


def build_session() -> requests.Session:
    retry = Retry(
        total=3,
        backoff_factor=1.0,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def extract_city(session: requests.Session, city: str, cfg: dict) -> dict:
    params = {
        "latitude": cfg["latitude"],
        "longitude": cfg["longitude"],
        "hourly": ",".join(HOURLY_VARIABLES),
        "timezone": "auto",
        "past_days": PAST_DAYS,
        "forecast_days": FORECAST_DAYS,
    }
    response = session.get(API_URL, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    try:
        payload = response.json()
    except requests.exceptions.JSONDecodeError as exc:
        raise APIResponseValidationError("API response is not valid JSON") from exc
    validate_city_payload(payload)
    return payload


def persist_raw(city: str, payload: dict, run_id: str) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    safe_city = city.lower().replace(" ", "_")
    path = RAW_DIR / f"{safe_city}_{run_id}.json"
    envelope = {
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": API_URL,
        "city": city,
        "payload": payload,
    }
    path.write_text(json.dumps(envelope, indent=2), encoding="utf-8")
    return path


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    session = build_session()
    frames: list[pd.DataFrame] = []
    failures: list[dict] = []

    for city, cfg in CITIES.items():
        LOGGER.info("Fetching air-quality data for %s", city)
        stage = "fetch"
        try:
            payload = extract_city(session, city, cfg)
            stage = "transform"
            frame = transform_city_payload(city, cfg["country"], payload)
            stage = "persist_raw"
            raw_path = persist_raw(city, payload, run_id)
            LOGGER.info("Saved raw payload: %s", raw_path.relative_to(BASE_DIR))
            frames.append(frame)
            LOGGER.info("Processed %s: %s hourly rows", city, len(frame))
        except (requests.RequestException, ValueError, RuntimeError) as exc:
            error_type = "schema_validation" if isinstance(exc, APIResponseValidationError) else type(exc).__name__
            if isinstance(exc, APIResponseValidationError):
                stage = "validate"
            message = " ".join(str(exc).split())[:300]
            LOGGER.warning("Failed city %s at %s (%s): %s", city, stage, error_type, message)
            failures.append({"city": city, "stage": stage, "error_type": error_type, "message": message})

    if not frames:
        LOGGER.error("ETL failed: all %s configured cities failed; existing outputs preserved.", len(CITIES))
        raise RuntimeError("ETL failed: no city data could be extracted.")

    hourly_df = pd.concat(frames, ignore_index=True)
    hourly_df = hourly_df.sort_values(["city", "timestamp"]).reset_index(drop=True)

    quality_df = run_quality_checks(hourly_df, CITIES.keys())
    city_summary_df = build_city_summary(hourly_df)

    hourly_path = PROCESSED_DIR / "air_quality_hourly.csv"
    summary_path = PROCESSED_DIR / "city_summary.csv"
    quality_path = PROCESSED_DIR / "data_quality_report.csv"
    run_meta_path = PROCESSED_DIR / "etl_run_metadata.json"

    hourly_df.to_csv(hourly_path, index=False)
    city_summary_df.to_csv(summary_path, index=False)
    quality_df.to_csv(quality_path, index=False)

    metadata = {
        "run_id": run_id,
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": API_URL,
        "configured_cities": list(CITIES),
        "successful_cities": sorted(hourly_df["city"].unique().tolist()),
        "failed_cities": failures,
        "row_count": int(len(hourly_df)),
        "quality_failures": int((quality_df["status"] == "FAIL").sum()),
        "quality_warnings": int((quality_df["status"] == "WARN").sum()),
    }
    run_meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    LOGGER.info("Processed %s rows across %s cities", len(hourly_df), hourly_df["city"].nunique())
    if failures:
        LOGGER.warning("Partial run: %s/%s cities failed: %s", len(failures), len(CITIES),
                       ", ".join(failure["city"] for failure in failures))
    if (quality_df["status"] == "FAIL").any():
        LOGGER.warning("ETL completed with data-quality failures. Review %s", quality_path)
    elif (quality_df["status"] == "WARN").any():
        LOGGER.warning("ETL completed with completeness warnings. Review %s", quality_path)
    else:
        LOGGER.info("All configured data-quality checks passed.")


if __name__ == "__main__":
    main()
