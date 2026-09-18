import pandas as pd

from src.quality import run_quality_checks


def test_quality_checks_pass_for_valid_frame():
    df = pd.DataFrame(
        {
            "city": ["A"],
            "country": ["X"],
            "timestamp": [pd.Timestamp("2026-09-18T00:00:00")],
            "us_aqi": [50],
            "pm2_5": [5.0],
            "pm10": [10.0],
            "nitrogen_dioxide": [8.0],
            "ozone": [20.0],
            "sulphur_dioxide": [1.0],
            "carbon_monoxide": [80.0],
        }
    )
    report = run_quality_checks(df, ["A"])
    assert (report["status"] == "PASS").all()
