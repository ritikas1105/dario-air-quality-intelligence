# Air Quality Operational Intelligence

A small, end-to-end Python data product for the Dario Health Senior AI Data Engineer assignment. It helps an operations or health-program analyst review **which configured cities have more elevated air-quality hours in the returned data window**, supported by AQI trends, PM2.5 comparisons, and visible data coverage.

The application is environmental operational intelligence. Its heuristic review-priority score is **not a clinical risk score, a population health-risk model, or a basis for patient-level advice**. It does not establish which pollutant caused an AQI change.

## Run locally

Validated locally on macOS with **Python 3.9.6**, using the pinned dependencies in `requirements.txt`. No API key, database, container, or cloud account is needed.

### macOS / Linux

```bash
git clone https://github.com/ritikas1105/dario-air-quality-intelligence.git
cd dario-air-quality-intelligence
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

### Windows PowerShell

```powershell
git clone https://github.com/ritikas1105/dario-air-quality-intelligence.git
cd dario-air-quality-intelligence
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m streamlit run app.py
```

Windows/Linux instructions use the same modules but were not separately executed on those operating systems.

The dashboard initially uses the **committed sample snapshot**, so reviewing it needs no live API request. Check the displayed ETL timestamp; the sample is a dated model snapshot, not current conditions.

To refresh data, stop the dashboard, run the ETL, wait for completion, then restart the dashboard:

```bash
python etl.py
python -m streamlit run app.py
```

On Windows, substitute `.venv\Scripts\python.exe` for `python`. Do not run concurrent ETL processes or read the snapshot while publication is in progress. The dashboard rereads processed files on each interaction; no cached snapshot needs clearing after a completed refresh.

Run the complete tests:

```bash
python -m pytest -q
```

The local Apple Python emits a `NotOpenSSLWarning` because it uses LibreSSL 2.8.3 with urllib3 v2. API requests and tests completed successfully in this environment; the warning remains a portability limitation. A Python build linked to supported OpenSSL avoids that mismatch. Streamlit's optional Watchdog suggestion does not prevent execution.

## Source and attribution

Data is retrieved from the [Open-Meteo Air Quality API](https://open-meteo.com/en/docs/air-quality-api), backed by **Copernicus Atmosphere Monitoring Service (CAMS)** atmospheric forecasts, including **CAMS European ENSEMBLE** and global composition data. Credit: Open-Meteo and the [CAMS / Copernicus Atmosphere Data Store and contributing providers](https://ads.atmosphere.copernicus.eu/), following the API's [attribution instructions](https://open-meteo.com/en/docs/air-quality-api#citation).

Endpoint: `https://air-quality-api.open-meteo.com/v1/air-quality`. This assignment uses the keyless public API. Consult the provider's usage terms for other deployments.

The API was chosen because it supplies useful environmental measurements without private credentials. The project requests US AQI, PM2.5, PM10, NO2, O3, SO2, and CO for Delhi, Mumbai, Bengaluru, London, New York, San Francisco, and Singapore. Coordinates are fixed in `src/config.py` to keep the example small and reproducible; they do not represent a validated target population.

These are model outputs, including past model data and forecasts, rather than regulatory ground-station observations. Returned coordinates may refer to model grid cells. Forecast availability can leave measurement gaps, especially near the returned horizon. See the [provider documentation](https://open-meteo.com/en/docs/air-quality-api) for model domains, units, and availability.

## Architecture and repository

```text
Open-Meteo -> fetch/retry -> validate response -> transform each valid city
                                                |              |
                                         raw JSON archive      v
                                                     combine hourly rows
                                                              |
                                                  quality checks + summary
                                                              |
                                            stage all four processed outputs
                                                              |
                                                publish local CSV/JSON snapshot
                                                              |
                                                     Streamlit dashboard
```

- `etl.py`: orchestration, HTTP requests, raw persistence, logging and run metadata.
- `src/config.py`: seven configured cities, requested variables, timeout and window settings.
- `src/schema.py`: lightweight city-response contract and intentional validation errors.
- `src/transform.py`: normalization, AQI categories, coverage, and analytical summaries.
- `src/quality.py`: completeness, structural and numeric validity checks.
- `src/storage.py`: temporary writes, replacement, rollback and cleanup.
- `app.py`: filters, KPIs, ranking, charts and pipeline health.
- `tests/`: transformation, quality, mocked ETL, publication and Streamlit AppTest regressions.
- `data/raw/`: source responses for the submitted snapshot.
- `data/processed/`: analytical CSVs and completed-run metadata.
- `ai_transcript/transcript.md`: reserved for the genuine finalized AI transcript; see AI usage below.

JSON retains source evidence; CSV makes this small dataset easy to inspect. Neither a database nor a distributed processing system is justified here.

## Data model and ETL contract

| Artifact | Grain / key |
|---|---|
| Raw JSON | One response per successful city/run, with city, source and UTC fetch timestamp |
| `air_quality_hourly.csv` | One city/local hourly timestamp within the snapshot; expected key `(city, timestamp)` |
| `city_summary.csv` | One city/country over its returned window |
| `data_quality_report.csv` | One check result for the entire snapshot |
| `etl_run_metadata.json` | One completed run: run ID, cities, row count, failure and warning counts |

Requests have a 30-second timeout and up to three retries for eligible failures, including rate limits and common server errors. Backoff is exponential. A timeout is not a total pipeline deadline.

The decoded response and `hourly` must be objects. Non-empty `time` and `us_aqi` arrays are required and must align. All pollutant arrays, including PM2.5, are optional; absent arrays become null analytical columns. Supplied arrays must align and contain supported values. Extra hourly fields are ignored. The original response is retained without fabricated measurements.

PM2.5 is needed for the existing score, but not for retaining a city's AQI data. If no valid AQI or no usable PM2.5 is available, its score and rank are unavailable. The score is not reweighted to hide missing inputs.

A malformed city or failed request is logged and skipped while other cities continue. Metadata records `city`, `stage`, `error_type`, and a concise `message`, without stack traces. Missing configured cities also appear as quality failures. If every city fails, the ETL raises an error and leaves previous processed outputs untouched; it does not publish empty success data. In this case existing metadata still describes the last completed run; inspect the failed command's logs.

## Data quality and coverage

- **PASS:** the check found no issue.
- **WARN:** measurement incompleteness, such as missing AQI or pollutant values.
- **FAIL:** missing required analytical columns/identifiers, duplicate keys, invalid timestamps, invalid numeric values, negative pollutant concentrations, finite AQI outside the project's broad 0–1000 plausibility range, or missing configured cities.

Null AQI is a completeness warning and is excluded from numeric-range checks. Infinite values are invalid; missing optional columns are materialized before quality checks. `affected_rows` counts rows once per check, not cells. Counts can overlap across checks and must not be summed. A missing-city check reports zero existing affected rows and lists absent cities in its details.

For each city and selected analytical scope:

```text
expected_hours      = number of included rows
valid_aqi_hours     = rows with numeric, finite AQI within 0–1000
elevated_aqi_hours  = valid AQI hours above 100
unhealthy_aqi_hours = valid AQI hours above 150
aqi_coverage_pct    = 100 * valid_aqi_hours / expected_hours
elevated_pct        = 100 * elevated_aqi_hours / valid_aqi_hours
```

`expected_hours` is the returned/selected row count, not a reconstructed complete calendar. Empty input is handled safely. With no valid AQI, elevated percentage, score and rank are unavailable. `[120, null]` therefore has **50% coverage and 100% elevated among available AQI hours**.

AQI categories are Good (0–50), Moderate (>50–100), Unhealthy for Sensitive Groups (>100–150), Unhealthy (>150–200), Very Unhealthy (>200–300), and Hazardous (>300 within the accepted range). Missing or invalid AQI is **Unavailable**, never Hazardous. These are display categories, not medical recommendations.

Quality results are diagnostic: a completed partial run can publish with FAIL results for inspection. There is no blanket quality-based publication gate. Invalid AQI and invalid PM2.5 are excluded from score inputs; consult the quality report before interpreting a run.

## Heuristic review-priority score

```text
score = 0.50 * elevated_pct
      + 0.35 * (min(max_aqi, 300) / 300 * 100)
      + 0.15 * min(avg_pm2_5, 100)
```

Components contribute at most 50, 35 and 15 points for valid inputs. Percentages and means are rounded to one decimal before scoring; the score is rounded to one decimal. Sorting uses descending score, then peak AQI. Unavailable scores receive no rank.

The weights favor sustained elevation, then peaks, then average PM2.5. They are transparent demonstration choices, not empirically validated weights. Peak AQI is sensitive to isolated hours, PM2.5 overlaps with information already in AQI, and close rankings can change with weights or coverage. The score is solely for **operational review prioritization**, not clinical or population risk estimation.

## Dashboard behavior

City and AQI-category selections apply to business KPIs, recomputed rankings, the priority callout, and charts. Coverage refers to the selected rows; filtering out Unavailable rows changes that denominator. Global pipeline-health checks are explicitly labeled as covering the entire ETL run.

The dashboard provides AQI trends, average PM2.5 comparisons, category counts, and a ranked review table. Across cities, the elevated-hour KPI counts city-hours rather than distinct simultaneous clock hours. An unavailable-only selection shows a clear message; zero-result filters stop gracefully. Missing processed files show the ETL command to run.

## Publication guarantees and limitations

All four processed outputs are serialized in memory, then written to a temporary directory. Final files are untouched until every temporary write and backup succeeds. Replacement errors trigger restoration of previous files; temporary files are removed after success or successful rollback. If rollback itself fails, recovery files are retained and an explicit error identifies their location.

This is a **single-process local publication mechanism**, not a multi-file filesystem transaction. Do not read during publication or run concurrent writers. A process kill, power loss, or unrecoverable filesystem failure may require recovery. Raw extracts are written separately and can remain after a later publication failure. The submitted raw directory contains only the responses corresponding to the final committed processed snapshot; earlier snapshots remain in Git history.

## Time windows and other limitations

The ETL deliberately retains `timezone=auto`, two past days and five forecast days. Timestamps are city-local, without a unified UTC analytical column. Around midnight, cities can receive different calendar-date windows. The trend chart compares local clock labels, not necessarily simultaneous instants. Past and future model values are summarized together.

Cross-city ranking is therefore **directional operational comparison**, not a perfectly synchronized simultaneous comparison or a current-conditions alert. Local timestamps can also be ambiguous around daylight-saving transitions. Synchronized UTC windows are deferred rather than introducing a rushed timezone migration.

API refreshes return evolving data; reproducibility of a stored snapshot does not imply identical future API responses. Missing values, small fixed city coverage, diagnostic rather than gating quality checks, and heuristic scoring limit interpretation.

## AI usage and final submission

AI assisted decomposition, implementation, review, failure simulation, testing, and documentation. The submission repository will include the genuine AI conversation at `ai_transcript/transcript.md` **once finalized**. It is intentionally not part of this technical commit. No transcript content has been fabricated.

## With more time

1. Use an identical UTC comparison window and distinguish past estimates from future forecasts.
2. Define business-approved coverage thresholds and publication gates, plus freshness/failed-refresh status.
3. Add automated CI for the existing test suite and validate additional Python/OS environments.
4. Validate score sensitivity with the intended analyst, or replace it with a simpler explicit ordering.

The priority is correctness and clear operational meaning, not additional infrastructure.
