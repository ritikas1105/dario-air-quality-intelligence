from src.transform import aqi_category, build_city_summary, transform_city_payload


def test_aqi_category_boundaries():
    assert aqi_category(0) == "Good"
    assert aqi_category(50) == "Good"
    assert aqi_category(51) == "Moderate"
    assert aqi_category(101) == "Unhealthy for Sensitive Groups"
    assert aqi_category(151) == "Unhealthy"
    assert aqi_category(201) == "Very Unhealthy"
    assert aqi_category(301) == "Hazardous"


def test_transform_and_summary():
    payload = {
        "latitude": 10.0,
        "longitude": 20.0,
        "timezone": "UTC",
        "hourly": {
            "time": ["2026-09-18T00:00", "2026-09-18T01:00"],
            "us_aqi": [40, 120],
            "pm2_5": [8, 40],
            "pm10": [20, 60],
            "nitrogen_dioxide": [10, 15],
            "ozone": [40, 80],
            "sulphur_dioxide": [2, 3],
            "carbon_monoxide": [100, 120],
        },
    }
    frame = transform_city_payload("Test City", "Testland", payload)
    assert len(frame) == 2
    assert frame["is_elevated_aqi"].sum() == 1

    summary = build_city_summary(frame)
    assert summary.iloc[0]["city"] == "Test City"
    assert summary.iloc[0]["elevated_aqi_hours"] == 1
