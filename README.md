# Air Quality Operational Intelligence

## Project overview

This project is a small end-to-end data product built for the AI Data Engineer home assignment. It uses the **Open-Meteo Air Quality API** to monitor hourly air-quality conditions across a fixed set of global cities and turns the API response into a business-facing operational view.

The practical question is:

> Which monitored cities are likely to experience elevated air-quality exposure, what is driving it, and where should a health program or operations team pay attention first?

The application is deliberately lightweight. It focuses on reproducibility, transparent ETL, data-quality checks, business-readable analytics, and a clean local run experience rather than infrastructure complexity.

> **Important:** This is an environmental-health analytics product, not a clinical decision system. The operational priority score is not a medical risk score.

## Selected API

**Open-Meteo Air Quality API**  
Endpoint: `https://air-quality-api.open-meteo.com/v1/air-quality`

Why it was selected:

- Free and keyless for this use case
- No private credentials or manual data preparation
- Hourly AQI and pollutant measures are directly useful for a health-adjacent product
- Supports reproducible API extraction and clear analytical transformations
- Reviewer can run the project immediately after cloning

The ETL requests US AQI, PM2.5, PM10, NO2, O3, SO2, and CO for seven configured cities. It includes two past days and five forecast days to give enough history/context for a useful dashboard.

## Architecture

```text
Open-Meteo Air Quality API
          |
          v
     Python extraction
   retries + timeout + validation
          |
          +---------------------> data/raw/*.json
          |
          v
  normalization / enrichment
  AQI category + flags + dates
          |
          v
      data quality checks
          |
          +---------------------> data/processed/data_quality_report.csv
          |
          v
  analytical output tables
          |
          +---------------------> air_quality_hourly.csv
          +---------------------> city_summary.csv
          +---------------------> etl_run_metadata.json
          |
          v
     Streamlit dashboard
```

## Repository structure

```text
README.md
requirements.txt
app.py
etl.py
src/
  __init__.py
  config.py
  quality.py
  transform.py
tests/
  test_quality.py
  test_transform.py
data/
  raw/
  processed/
ai_transcript/
  transcript.md
```

## How to run locally

```bash
git clone <repository-url>
cd <repository-folder>
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python etl.py
streamlit run app.py
```

Optional test run:

```bash
pytest -q
```

No Docker, database, cloud account, API key, or private package is required.

## ETL flow

### 1. Extract

`etl.py` loops over a small configured city list and requests hourly air-quality data from Open-Meteo.

Reliability features:

- HTTP timeout
- Retry with exponential backoff
- Retries for rate limits and common 5xx responses
- City-level exception handling
- Raw API response persisted locally with fetch timestamp and source metadata
- Partial city failures are recorded instead of silently ignored
- ETL fails if no city can be retrieved at all

### 2. Transform

Each API payload is normalized into a tabular hourly grain:

**Grain:** one row per city per local hourly timestamp.

Core columns:

- city / country
- timestamp / timezone
- latitude / longitude
- US AQI
- PM2.5 / PM10
- NO2 / O3 / SO2 / CO
- AQI category
- elevated-AQI flag (`AQI > 100`)
- unhealthy-AQI flag (`AQI > 150`)
- local date

A city-level summary is also produced with:

- average and peak AQI
- average and peak PM2.5
- hours above AQI 100
- hours above AQI 150
- share of elevated hours
- operational priority score

### 3. Operational priority score

The score is intentionally simple and transparent:

```text
50% = share of hours with AQI > 100
35% = capped peak AQI contribution
15% = capped average PM2.5 contribution
```

It exists only to rank locations for operational review. It must not be interpreted as a clinical or patient-level risk score.

## Data quality checks

The ETL writes a visible quality report and surfaces it in Streamlit.

Checks include:

1. Required columns exist
2. No duplicate `(city, timestamp)` records
3. Required analytical fields do not contain nulls
4. Pollutant concentrations are non-negative
5. AQI is inside a broad plausibility range
6. All configured cities are represented
7. Timestamps are parseable

This approach keeps quality rules explicit and auditable rather than burying them inside transformation code.

## Dashboard overview

The Streamlit application includes:

- City and AQI-category filters
- Monitored-city count
- Average and peak AQI
- Hours above AQI 100
- Ranked operational-priority table
- AQI trend over time
- Average PM2.5 comparison
- AQI category mix
- Data-quality and ETL health section
- Plain-language explanation of how the product should and should not be interpreted

## Assumptions

- City coordinates are intentionally configured in code instead of calling a second geocoding API. This removes an unnecessary dependency and makes runs deterministic.
- Open-Meteo local timezone output is kept for stakeholder readability.
- US AQI is used as a common comparison metric across monitored locations.
- The project uses API/model output and does not claim to represent regulatory ground-station observations.
- The AQI threshold flags are operational labels, not clinical recommendations.

## Known limitations

- The city list is intentionally small and static.
- There is no historical warehouse or incremental partitioning strategy because the assignment requires only a local runnable product.
- CSV is used for reviewer simplicity. For larger workloads I would use Parquet and partition by date/city.
- API availability is an external dependency. Retries reduce transient failures but cannot eliminate upstream outages.
- The prioritization model is heuristic and is not validated for clinical use.
- Forecast and past values should not be treated as equivalent to patient-level health outcomes.

## AI usage

AI was used as a working partner for:

- decomposing the assignment and evaluation criteria
- comparing possible public API/product ideas
- selecting a health-relevant but technically manageable direction
- designing the ETL/data model
- identifying reliability and quality checks
- reviewing code structure and edge cases
- drafting test scenarios and documentation
- challenging unnecessary complexity and keeping the solution reviewer-friendly

The AI conversation is included under `ai_transcript/`. The candidate should export/copy the full visible conversation from the AI tool into that folder before final submission so the repository contains the exact transcript reviewed by the hiring team.

## What I would improve with more time

1. Add configurable locations from the UI while keeping a deterministic default city set.
2. Store processed data as partitioned Parquet for scale and type fidelity.
3. Add schema validation with Pandera or Pydantic.
4. Add integration tests with mocked API responses and failure scenarios.
5. Add data freshness alerts and an explicit SLA/freshness panel.
6. Add CI to run tests and linting on every push.
7. If used inside a health platform, join this environmental context to properly consented/aggregated cohorts and validate any downstream prioritization logic with clinical and privacy stakeholders.

## Why this design

The assignment asks for practical judgment and end-to-end ownership. I therefore optimized for a project that is:

- useful enough to explain in business terms
- easy to run in a few commands
- explicit about data quality and failures
- structured like maintainable production code
- small enough for a reviewer to understand quickly
