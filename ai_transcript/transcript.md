# AI Collaboration Transcript


### Candidate

Hi, I want to build a project called **Air Quality Operational Intelligence** using a free public API.

A few requirements I need to satisfy are:

- Python should be used for the solution.
- Streamlit should be used for the analytics/dashboard layer.
- The data source should be a free public API.
- I need an ETL/data-processing layer that extracts, transforms, validates, and stores data locally.
- The dashboard should be business-facing and easy to understand.
- I need meaningful data-quality checks and error handling.
- The project should be easy for a reviewer to run locally.
- Git should be used throughout the project.

I want to keep the project practical and not overengineer it. Can you suggest a clean architecture and folder structure?

---

### AI

Yes. I would keep the solution modular but lightweight.

A clean structure would be:

```text
README.md
requirements.txt
app.py
etl.py

src/
  config.py
  schema.py
  transform.py
  quality.py
  storage.py

data/
  raw/
  processed/

tests/
  test_transform.py
  test_quality.py
  test_etl.py
  test_app.py
  test_storage.py
```

The responsibilities would be:

- `etl.py`: orchestrates the pipeline.
- `config.py`: cities, coordinates, API configuration, and constants.
- `schema.py`: validates API response structure before transformation.
- `transform.py`: converts raw API payloads into analytical datasets and calculates summary metrics.
- `quality.py`: checks completeness, validity, duplicates, and other data-quality rules.
- `storage.py`: publishes processed outputs safely.
- `app.py`: Streamlit dashboard.

For the data source, a keyless API would make the reviewer experience easier because there would be no secret or account setup.

---

### Candidate

I want the use case to make sense for a digital-health company, but I do not want to make medical claims. Which API would fit?

---

### AI

A good fit would be the **Open-Meteo Air Quality API**.

It is useful here because:

- it is free,
- it does not require a paid key,
- it provides hourly AQI and pollutant values,
- and it supports a health-adjacent operational story without requiring patient data.

I would position the product as **Air Quality Operational Intelligence**, not as a clinical risk product.

The core business question could be:

> Which monitored cities are experiencing elevated air-quality conditions, how complete is the underlying data, and which locations deserve operational review first?

That keeps the product useful without implying diagnosis or patient-level risk.

---

### Candidate

How should I store the data? I want the reviewer to be able to understand what came from the API and what was transformed.

---

### AI

I would separate the raw and processed layers.

**Raw layer**

Store the original API response for each city as JSON:

```text
data/raw/
  delhi_<timestamp>.json
  london_<timestamp>.json
  ...
```

That gives you traceability and makes debugging easier.

**Processed layer**

Create small analytical files such as:

```text
data/processed/
  air_quality_hourly.csv
  city_summary.csv
  data_quality_report.csv
  etl_run_metadata.json
```

Suggested grains:

- `air_quality_hourly.csv`: one row per city per hourly timestamp.
- `city_summary.csv`: one row per city for the current analytical window.
- `data_quality_report.csv`: one row per quality check.
- `etl_run_metadata.json`: one record describing the ETL run.

CSV is reasonable here because the dataset is small and easy for the reviewer to inspect.

---

### Candidate

What should the city-level summary contain?

---

### AI

I would calculate a small number of metrics that are easy to explain:

- average AQI,
- maximum AQI,
- expected hours,
- valid AQI hours,
- AQI coverage percentage,
- hours where AQI is above 100,
- hours where AQI is above 150,
- percentage of elevated AQI hours among valid AQI hours,
- average PM2.5,
- maximum PM2.5,
- heuristic review-priority score,
- priority rank.

The key point is to separate **coverage** from **severity**.

For example, if AQI values are:

```text
[120, missing]
```

then:

```text
expected hours = 2
valid AQI hours = 1
AQI coverage = 50%
elevated percentage = 100%
```

The missing value should not reduce the percentage among valid readings.

---

### Candidate

I also want proper test cases. What should I test first?

---

### AI

Start with behavior that protects the main logic, not just line coverage.

For transformation:

- AQI category boundaries:
  - 50 → Good
  - 51 → Moderate
- missing AQI → Unavailable
- city summary calculations
- AQI coverage
- elevated percentage denominator
- priority-score calculations

For data quality:

- missing AQI → completeness warning
- negative pollutant → failure
- infinite numeric value → failure
- duplicate city/timestamp → failure
- invalid timestamp → failure
- missing required column → failure

For ETL/schema handling:

- top-level API response is not an object
- missing `hourly`
- missing `time`
- missing `us_aqi`
- unequal array lengths
- missing optional pollutant
- one city fails while another succeeds
- all cities fail

For the dashboard:

- default state
- one city
- multiple cities
- Good category
- Unavailable category
- no-result filter
- ranking remains consistent with the active filter
- missing AQI does not display a severity label

---

### Candidate

I tested the dashboard and found an issue. Missing AQI can end up looking like the highest severity, and when I filter by a category, the KPI values change but the ranking can still use the full dataset.

How should I fix that?

---

### AI

Those are both correctness issues.

For missing AQI:

- `None`, `NaN`, or non-finite AQI should return **Unavailable**.
- Missing AQI should never be categorized as Hazardous.

For filtering:

- KPIs,
- rankings,
- narrative,
- charts,
- and displayed tables

should all use the same filtered scope.

If the selected filter returns no valid AQI rows, the application should show a clear message such as:

> AQI unavailable for the selected scope.

I would also add Streamlit AppTest cases so this does not regress later.

---

### Candidate

I found another issue around data quality.

Missing AQI is being treated as both a missing-value problem and an AQI-range problem. Also, elevated percentage is using all timestamps as the denominator.

I want missing data and invalid data to be treated differently.

---

### AI

That distinction is important.

I would use three categories:

**Structural failure**

Examples:

- missing required column,
- invalid timestamp,
- duplicate analytical key,
- unusable response structure.

**Completeness warning**

Examples:

- AQI field exists but some hourly values are missing,
- pollutant field exists but some values are unavailable.

**Validity failure**

Examples:

- negative pollutant concentration,
- infinite values,
- finite AQI outside the accepted numeric range.

A null AQI is not an out-of-range number, so it should not fail both checks.

For the denominator:

```text
AQI coverage =
valid_aqi_hours / expected_hours
```

and:

```text
elevated_pct =
elevated_aqi_hours / valid_aqi_hours
```

If `valid_aqi_hours` is zero, the elevated percentage should be unavailable instead of showing a misleading 0%.

---

### Candidate

What if the API returns malformed data for one city? I do not want the whole ETL to fail because one response is bad.

---

### AI

Add a lightweight schema-validation layer before transformation.

For each city:

```text
fetch
  → validate
  → transform
  → append
```

At minimum validate:

- top-level response is an object,
- `hourly` exists and is an object,
- `time` exists,
- `us_aqi` exists,
- required arrays are non-empty,
- required arrays have matching lengths.

Treat pollutant arrays as optional where possible.

If one city is invalid:

- record the city,
- record the stage,
- record a concise reason,
- continue with valid cities.

Example:

```json
{
  "city": "Mumbai",
  "stage": "validate",
  "error_type": "schema_validation",
  "message": "Missing required hourly field: us_aqi"
}
```

If every configured city fails, then the ETL should fail explicitly.

---

### Candidate

I also noticed that the processed outputs are written as separate files. If writing one of them fails midway, could the dashboard end up reading files from different runs?

---

### AI

Yes. That is possible if each output is written independently.

A simple solution is staged publication:

1. Build the full processed output set in memory.
2. Write all outputs to temporary files.
3. Only after all temporary writes succeed, replace the final files.
4. If any temporary write fails, keep the previous valid snapshot.
5. Clean up temporary files.

That gives you coherent publication without introducing a database or transaction framework.

Add tests for:

- successful full publication,
- failure during temporary writes,
- rollback to the previous valid snapshot,
- temporary-file cleanup.

---

### Candidate

For the dashboard, what should I show so that it feels business-facing instead of just a collection of charts?

---

### AI

I would keep the dashboard focused.

At the top:

- Cities monitored
- Average AQI
- Peak AQI
- Elevated city-hours
- AQI coverage

Then show:

- city review-priority ranking,
- a short narrative explaining which city needs attention,
- AQI trend over time,
- PM2.5 comparison,
- AQI category distribution,
- pipeline-health/data-quality section.

The priority score should be clearly described as a **heuristic operational review score**, not a clinical risk score.

Keep the dashboard filters simple:

- city,
- AQI category.

And make sure every business-facing metric respects the selected filters.

---

### Candidate

What about the priority score? I want something simple but explainable.

---

### AI

A simple heuristic is fine if you are transparent about it.

You can use a weighted combination such as:

```text
50% elevated AQI share
35% normalized peak AQI
15% normalized average PM2.5
```

The important part is not pretending the weights are clinically validated.

Explain that:

- it is used only to prioritize operational review,
- the weights are heuristic,
- it is not a medical or population-health risk model,
- a city with insufficient data should not receive a misleading score or rank.

---

### Candidate

Do I need Spark, Kafka, Airflow, Docker, or a database for this?

---

### AI

Not for this assignment.

The dataset is small and the reviewer needs to run it locally with minimal setup.

Python + pandas + local JSON/CSV + Streamlit is enough.

Using Spark or Kafka here would add complexity without solving a real scaling problem.

If this were productionized at much larger scale, then orchestration, partitioned storage, stronger observability, and possibly distributed processing could be considered.

---

### Candidate

I want to make sure the project is strong from a reviewer perspective. What should I validate before finalizing it?

---

### AI

I would validate five areas:

**1. ETL**
- real API run succeeds,
- partial city failure is isolated,
- all-city failure is explicit,
- raw files are preserved.

**2. Data quality**
- missing values become warnings where appropriate,
- invalid values fail,
- coverage is calculated correctly,
- no missing AQI is interpreted as severity.

**3. Dashboard**
- filters are consistent,
- rankings follow the selected scope,
- empty states are graceful,
- pipeline health loads correctly.

**4. Storage**
- processed outputs are published as a coherent snapshot,
- simulated write failures do not leave mixed runs.

**5. Documentation**
- setup commands are copyable,
- data grains are explained,
- limitations are honest,
- source attribution is present,
- the priority score is clearly non-clinical.

---

### Candidate

One limitation I still have is that the API returns city-local windows. I do not want to make a risky timezone refactor at the last minute.

Would documenting it be acceptable?

---

### AI

Yes, as long as the limitation is explicit.

You can state that:

- the current API windows are city-local,
- cross-city ranking is an operational/directional comparison,
- it is not a perfectly synchronized simultaneous exposure comparison,
- normalizing all cities to a fixed UTC comparison window would be a future improvement.

That is better than introducing a rushed timezone change late in the assignment.

---

---

### Candidate

Before I finalize this, I want to make sure I am not just accepting every AI suggestion. Which recommendations are actually worth implementing for this assignment, and which ones would just add unnecessary complexity?

---

### AI

For this scope, I would prioritize only changes that materially improve correctness, reliability, or reviewer confidence.

High-value items:

- fix incorrect handling of missing AQI,
- make dashboard filters consistent,
- separate completeness warnings from validity failures,
- add schema validation for malformed API responses,
- make partial city failures predictable,
- prevent half-written processed snapshots,
- add focused regression tests,
- document limitations honestly.

I would **not** add technologies only to make the project look more advanced.

Skip for now:

- Spark,
- Kafka,
- Airflow,
- databases,
- Docker,
- Kubernetes,
- cloud deployment,
- an LLM layer.

The assignment is small enough that those would make the solution harder to run without solving a real problem.

---

### Candidate

That makes sense. I want the project to stay small and understandable. I would rather have a reliable local solution than add tools just because they are common in data engineering.

For testing, I also do not want dozens of superficial tests. I want tests around the failures we actually found.

What are the highest-value regression cases?

---

### AI

Focus on tests that protect the behavior you already had to debug:

- missing AQI must be `Unavailable`, never `Hazardous`,
- filtered KPIs and rankings must use the same scope,
- `[120, missing]` must produce 50% coverage and 100% elevated percentage among valid readings,
- missing AQI must not also fail the AQI range rule,
- negative or infinite pollutant values must fail validity checks,
- malformed API payloads must fail at schema validation rather than leaking `KeyError` or `AttributeError`,
- one bad city must not stop valid cities,
- all-city failure must stop the ETL explicitly,
- failed publication must preserve the previous good processed snapshot.

Those tests demonstrate that AI was used to improve the reliability of the solution after issues were identified, not just to produce initial code.

---

### Candidate

I also want to make sure the AI output is being reviewed rather than followed blindly.

For example, I was considering changing all timestamps to UTC after the audit, but that feels risky this late in the assignment. Would you still recommend changing it?

---

### AI

Not necessarily.

A synchronized UTC comparison window would be cleaner analytically, but a late timezone refactor touches extraction, transformation, aggregation, dashboard behavior, generated data, and tests.

Since the current city-local behavior is known and the limitation can be explained honestly, documenting it is a reasonable engineering decision for this assignment.

That is a good example of **not** taking an AI recommendation automatically. The better choice here is to keep the stable implementation, document the limitation, and list UTC normalization as a future improvement.

---

### Candidate

Good. I also want to stop once the main correctness and reliability issues are resolved. I do not want the assignment to become unnecessarily large.

What should be the final validation checklist before I consider the technical work complete?

---

### AI

I would stop once you can verify:

- the real ETL succeeds,
- all expected cities are either processed or clearly reported as failed,
- data-quality failures and warnings have clear semantics,
- the dashboard works for normal and empty filter states,
- processed outputs are published coherently,
- focused regression tests pass,
- the README matches the actual implementation,
- limitations are documented,
- and the repository can be cloned and run without hidden dependencies.

At that point, more features would add less value than being able to explain the implementation clearly.


### Candidate

After the fixes, I ran the full validation.

The final run produced:

- 1,176 rows,
- all 7 cities successful,
- 0 failed cities,
- 0 quality failures,
- 2 completeness warnings,
- and all tests passed.

Does this look ready technically?

---

### AI

Yes, assuming the dashboard and README also reflect the final generated data.

The main engineering areas are now covered:

- extraction,
- raw-data persistence,
- schema validation,
- transformation,
- data-quality checks,
- coverage semantics,
- partial failure handling,
- coherent output publication,
- analytical summaries,
- Streamlit interaction,
- and regression testing.

At this point I would stop adding new infrastructure and focus on final documentation, repository hygiene, and making sure you can explain each file and trade-off clearly.

---

### Candidate

That makes sense. I will keep the project simple and make sure I can explain the architecture, data flow, quality checks, dashboard, tests, and limitations before submission.

---

### AI

That is the right final step.

The strongest explanation is:

> `etl.py` orchestrates the data pipeline, `schema.py` validates API structure, `transform.py` creates analytical data and metrics, `quality.py` checks completeness and validity, `storage.py` publishes outputs safely, and `app.py` presents the processed data in Streamlit.

If you can explain that flow, the data grains, the main quality rules, and why you deliberately avoided unnecessary infrastructure, you will be able to answer most implementation questions about the project.

---
