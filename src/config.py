from __future__ import annotations

CITIES = {
    "Delhi": {"latitude": 28.6139, "longitude": 77.2090, "country": "India"},
    "Mumbai": {"latitude": 19.0760, "longitude": 72.8777, "country": "India"},
    "Bengaluru": {"latitude": 12.9716, "longitude": 77.5946, "country": "India"},
    "London": {"latitude": 51.5072, "longitude": -0.1276, "country": "United Kingdom"},
    "New York": {"latitude": 40.7128, "longitude": -74.0060, "country": "United States"},
    "San Francisco": {"latitude": 37.7749, "longitude": -122.4194, "country": "United States"},
    "Singapore": {"latitude": 1.3521, "longitude": 103.8198, "country": "Singapore"},
}

API_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

HOURLY_VARIABLES = [
    "us_aqi",
    "pm2_5",
    "pm10",
    "nitrogen_dioxide",
    "ozone",
    "sulphur_dioxide",
    "carbon_monoxide",
]

FORECAST_DAYS = 5
PAST_DAYS = 2
REQUEST_TIMEOUT_SECONDS = 30
