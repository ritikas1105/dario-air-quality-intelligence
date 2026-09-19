"""Lightweight contract for a single city's decoded air-quality response."""

from collections.abc import Mapping, Sequence
from numbers import Real

from src.quality import POLLUTANT_COLUMNS


class APIResponseValidationError(ValueError):
    """The response cannot safely form a city's analytical frame."""


def validate_city_payload(payload: object) -> dict:
    """Return aligned analytical arrays without mutating the source response.

    Time and AQI arrays are required. All pollutant arrays are optional, including
    PM2.5: absent PM2.5 leaves AQI usable but the priority score/rank unavailable.
    Present arrays must be aligned sequences of numeric/null measurements.
    Numeric range, finiteness and completeness remain data-quality concerns.
    Unknown hourly fields are ignored so extra API fields cannot alter our frame.
    """
    if not isinstance(payload, Mapping):
        raise APIResponseValidationError(
            f"Expected API response object, received {type(payload).__name__}"
        )
    if payload.get("error"):
        raise APIResponseValidationError("API returned an error response")
    if "hourly" not in payload:
        raise APIResponseValidationError("Missing required response field: hourly")
    hourly = payload["hourly"]
    if not isinstance(hourly, Mapping):
        raise APIResponseValidationError(
            f"Expected hourly object, received {type(hourly).__name__}"
        )
    for field in ("time", "us_aqi"):
        if field not in hourly:
            raise APIResponseValidationError(f"Missing required hourly field: {field}")

    normalized = {}
    for field in ("time", "us_aqi", *POLLUTANT_COLUMNS):
        if field not in hourly:
            normalized[field] = [None] * len(normalized["time"])
            continue
        values = hourly[field]
        if not isinstance(values, Sequence) or isinstance(values, (str, bytes, bytearray)):
            raise APIResponseValidationError(f"Hourly field {field} must be an array")
        if field == "time":
            if not values:
                raise APIResponseValidationError("Hourly time array must not be empty")
        elif len(values) != len(normalized["time"]):
            raise APIResponseValidationError(
                f"Hourly field {field} length {len(values)} does not match time length "
                f"{len(normalized['time'])}"
            )
        for index, value in enumerate(values):
            if field == "time":
                valid = isinstance(value, str) and bool(value.strip())
            else:
                valid = value is None or (isinstance(value, Real) and not isinstance(value, bool))
            if not valid:
                expected = "non-empty timestamp string" if field == "time" else "number or null"
                raise APIResponseValidationError(
                    f"Hourly field {field} at index {index} must be a {expected}"
                )
        normalized[field] = list(values)

    for field in ("latitude", "longitude", "timezone"):
        value = payload.get(field)
        expected_type = str if field == "timezone" else Real
        if value is not None and (not isinstance(value, expected_type) or isinstance(value, bool)):
            raise APIResponseValidationError(f"Response field {field} has an unsupported type")
    return normalized
