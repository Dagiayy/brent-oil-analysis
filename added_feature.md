# Added / Modified — Engineering Changelog

This document records, in detail, everything that was changed in this repository during
the productionization pass: what was broken, what was added, what was modified, and why.
It complements `README.md` (which describes the system as it is now) by describing the
**delta** from the original state.

---

## 0. Starting state (what was actually here before)

Before any changes, this was a partially-broken academic submission, not a working
prototype. On inspection:

- `README.md`, `requirements.txt`, `.gitignore`, `src/utils.py`,
  `src/data_preprocessing.py`, `src/change_point_model.py`, `src/__init__.py`, and 3 of
  the 5 notebooks (`01_eda.ipynb`, `02_change_point_model.ipynb`,
  `03_dashboard_logic.ipynb`) were **corrupted UTF-16 files** — effectively empty
  (1–6 bytes) despite having real-looking names.
- **No ETL step existed anywhere.** `data/processed/` did not exist. The README
  documented an EDA notebook that would produce `brent_log_returns.csv`, but no such
  notebook (or any script) actually did this. Both the model script and the Flask API
  therefore had nothing to read out of the box.
- `dashboard/backend/data_loader.py` and `dashboard/backend/requirments.txt` (note the
  typo) were empty (0 bytes).
- **Duplicate/dead structure**: `dashboard/frontend/frontend/` (nested duplicate of the
  whole React app), `outputs/outputs/` (nested duplicate, empty), `notebooks/1_eda.ipynb`
  (0 bytes) and `notebooks/2_change_point_model.ipynb` (the one file that actually had
  real content) duplicating the corrupted `01_/02_` versions, a stray `package.json` +
  `package-lock.json` for **frontend** npm packages sitting inside the **Python** Flask
  backend folder, and an unused duplicate `ChartComponent`/`App.js`/`chart-setup.js` at
  the frontend root that nothing imported.
- The only genuinely working, real code was: the raw price CSV, `data/events.xlsx`, one
  PyMC script (`src/modeling/change_point_model.py`), the Flask route handlers
  (`dashboard/backend/app.py`), and the React dashboard (`dashboard/frontend/src/App.js`
  + friends).
- `requirements.txt` listed `pymc3` (an abandoned, incompatible package) while the code
  imported `pymc` (v5+ API) — the two are different packages; installing the listed
  requirements would not have made the code run.
- The committed model output (`outputs/logs/trace_summary.csv`) showed an effective
  sample size of only **~60–120 out of 8,000 draws** with missing `r_hat` — i.e. even the
  one part that "worked" was producing a statistically untrustworthy posterior.
- No tests, no CI, no Docker, no `.env.example`, no centralized config — all paths and
  ports hardcoded, `debug=True` in Flask.

---

## 1. Files added (new)

### Python package (`src/`)
| File | Purpose |
|---|---|
| `src/config.py` | Centralized, environment-driven configuration: `Paths` (all file locations, resolved relative to project root, overridable via env vars), `ModelConfig` (MCMC hyperparameters + reliability thresholds), `APIConfig` (Flask host/port/debug/CORS). |
| `src/data/__init__.py`, `src/data/ingestion.py` | Extract step. `load_raw_prices()` / `load_events()` with schema validation (`DataValidationError`), type coercion, and — critically — a fix for the **mixed date-format bug** (see §3). |
| `src/data/preprocessing.py` | Transform/Load step. `compute_log_returns()`, `add_rolling_volatility()`, `deduplicate_and_reindex()`, `build_processed_prices()`, `save_processed_prices()`, `save_processed_events()`. This is the ETL logic that simply did not exist before. |
| `src/data/quality.py` | `check_price_quality()` — duplicate-date detection, IQR-based outlier flagging on daily returns, returns a JSON-serializable `DataQualityReport`. |
| `src/analysis/__init__.py`, `src/analysis/eda.py` | `run_adf_test()` (stationarity), `summary_statistics()` — reusable functions backing both the notebook and the pipeline. |
| `src/insights/__init__.py`, `src/insights/event_alignment.py` | `find_nearest_event()`, `quantify_shift()`, `build_alignment_report()` — aligns a detected change point with the nearest curated event and quantifies the before/after return & volatility shift. This implements what the original README called "Task 3" but which had no code anywhere. |
| `src/ai/__init__.py`, `src/ai/narrative.py` | Optional Claude-generated analyst narrative from the structured statistical output, with a deterministic template fallback when no API key is configured. New capability, not a rewrite of anything. |
| `src/modeling/__init__.py` | Was a missing `__init__.py` — `src/modeling/` was not a valid importable package before. |

### Pipeline / orchestration
| File | Purpose |
|---|---|
| `pipelines/run_pipeline.py` | New end-to-end CLI: Extract → Validate → Transform → Load → Model → Align → Narrate → Report. Writes a timestamped, self-contained JSON manifest per run (`outputs/reports/run_<ts>.json`) plus `outputs/reports/latest_run.json` for the API to serve. This is the single command that regenerates everything; it did not exist before. |

### Dashboard backend
| File | Purpose |
|---|---|
| `dashboard/backend/data_loader.py` | Was an empty 0-byte file — now a real data-access layer (`get_prices`, `get_events`, `get_change_point`, `get_stats`, `get_latest_report`), separating pandas/IO concerns from the Flask route handlers in `app.py`. |
| `dashboard/backend/requirements.txt` | New, correctly-spelled file: a **lean** dependency set (flask, flask-cors, python-dotenv, pandas, gunicorn) used specifically by the Docker image, deliberately excluding pymc/arviz/statsmodels since the API only serves precomputed artifacts. |

### Frontend
| File | Purpose |
|---|---|
| `dashboard/frontend/.env.example` | Documents `REACT_APP_API_URL` (previously hardcoded `http://localhost:5000` in 4 places in `App.js`). |
| `dashboard/frontend/nginx.conf` | SPA-fallback nginx config for the production Docker image. |

### Tests (all new — there were zero tests before)
| File | Covers |
|---|---|
| `tests/conftest.py` | Shared fixtures: synthetic raw prices, synthetic events, a processed-prices fixture. |
| `tests/test_ingestion.py` | Raw price/event loading, schema validation errors, **the mixed-date-format regression** (see §3). |
| `tests/test_data_preprocessing.py` | Log-return correctness (checked against a manual `np.log` calc), dedup/reindex, quality-report outlier/duplicate detection, rolling volatility windowing. |
| `tests/test_eda.py` | ADF test correctly distinguishes a stationary series from a random walk. |
| `tests/test_event_alignment.py` | Nearest-event matching (incl. the "outside max window → None" case), before/after shift quantification. |
| `tests/test_narrative.py` | AI narrative falls back to the deterministic template with no API key configured, and correctly surfaces an "unreliable" diagnostics flag in the text. |
| `tests/test_api.py` | Every Flask endpoint, success and 404 paths, via dependency-injected `Paths` (no real files needed) — including a regression test for the NaN/JSON bug (§3). |
| `tests/test_change_point_model_smoke.py` | **Real** (not mocked) small-scale MCMC runs verifying the rewritten model builds, samples, and recovers an injected change point; skips cleanly if pymc isn't installed. |

### Config / infra
| File | Purpose |
|---|---|
| `requirements-dev.txt` | Adds pytest, pytest-cov, ruff on top of runtime requirements. |
| `pyproject.toml` | `pytest` config (`pythonpath`, `slow` marker) and `ruff` lint config. |
| `.env.example` (root) | Documents every env var `src/config.py` reads (Flask, MCMC hyperparameters, optional `ANTHROPIC_API_KEY`, path overrides). |
| `.dockerignore` | Keeps `.venv/`, `node_modules/`, caches, etc. out of Docker build contexts. |
| `Dockerfile.backend`, `Dockerfile.frontend`, `docker-compose.yml` | Full containerization — none existed before. |
| `.github/workflows/ci.yml` | Lint + fast tests (Python), `npm run build` (frontend), and a Docker-build verification job for both images — no CI existed before. |

---

## 2. Files substantially rewritten (kept the name/role, replaced the content)

| File | What changed |
|---|---|
| `src/modeling/change_point_model.py` | **Core ML rewrite** — see §3 for the full rationale. Kept `run_change_point_analysis()` signature-compatible with the original for backward compatibility, but the implementation underneath is new: continuous sigmoid-relaxed `tau`, three model variants (`null`/`mean_shift`/`mean_vol_shift`), PSIS-LOO model comparison, structured `ChangePointResult`, diagnostic thresholds, and a `sys.path` bootstrap so `python src/modeling/change_point_model.py ...` works standalone as documented. |
| `dashboard/backend/app.py` | Route handlers now only do HTTP concerns (status codes, param parsing, JSON shaping); all pandas/IO moved to `data_loader.py`. Added `/api/health`, `/api/insights`. Added a proper `HTTPException` handler so Flask's own 404/405 aren't collapsed into generic 500s. Fixed a **real JSON-validity bug** (§3). Config (host/port/debug/CORS) now comes from `src.config.API_CONFIG` instead of being hardcoded. |
| `dashboard/frontend/src/App.js` | Removed the inline duplicate `ChartComponent`/`StatCard` definitions in favor of importing the real components (removing duplication). Replaced 4 hardcoded `http://localhost:5000` occurrences with `process.env.REACT_APP_API_URL`. Added the new `AnalystInsights` panel that calls `/api/insights` and renders the narrative + a "diagnostics flagged this run" badge. Switched `Promise.all` to `Promise.allSettled` so one failing secondary call (e.g. `/api/insights` 404 before a pipeline run) doesn't blank out the whole dashboard. |
| `dashboard/frontend/src/components/ChartComponent.jsx`, `StatsCard.jsx` | Were dead files (nothing imported them; `App.js` had its own inline copies with drifted APIs). Rewritten to match what the API actually returns and wired into `App.js`, eliminating the duplication instead of leaving two divergent implementations. |
| `src/change_point_model.py`, `src/data_preprocessing.py` | Were empty/corrupted stub files at these exact paths. Rebuilt as thin, documented re-export/CLI-shim modules pointing at the real implementations now under `src/modeling/` and `src/data/`, so the original documented entry point (`python src/change_point_model.py --data ... --output ...`) still works unchanged. |
| `README.md` | Full rewrite: architecture diagram, an honest explanation of the model's original reliability problem and the fix, API reference, install/run/test instructions that actually work, a `Limitations` section (single change point, correlation-not-causation, curated-event coverage gaps), and a `Future Improvements` section. |
| `requirements.txt` | Was `pandas, numpy, matplotlib, seaborn, pymc3, arviz, jupyter, scipy` (note: `pymc3`, not `pymc` — mismatched with the actual code). Rewritten with the packages actually imported (`pymc`, `arviz`, `flask`, `flask-cors`, `python-dotenv`, `openpyxl`, `statsmodels`), version ranges validated against a real install (see §4 for the version-resolution work this took). |
| `.gitignore` | Rewritten (the original was unreadable UTF-16); trimmed to what this repo actually needs, added `.venv/`, `outputs/logs/run_*.json` (regenerable run manifests). |
| `notebooks/01_eda.ipynb`, `02_change_point_model.ipynb`, `03_dashboard_logic.ipynb` | Rebuilt from scratch as real, runnable notebooks. Deliberately kept **thin** — each imports and calls the tested `src/` functions rather than duplicating logic inline, so the notebook is a view onto tested code, not a second, divergent copy of it. `02_` now fits three model variants and shows the PSIS-LOO comparison table; `03_` demonstrates event alignment + narrative generation and documents how each dashboard endpoint maps back to it. |

---

## 3. The specific bugs found and fixed (with evidence)

These were not style preferences — each was verified to actually cause wrong or broken
behavior, and each has a regression test.

1. **Unreliable Bayesian posterior.** The original model used
   `tau = pm.DiscreteUniform(...)` with `pm.math.switch`. A discrete `tau` forces PyMC
   into a compound Metropolis(tau)+NUTS(rest) sampler, which mixed very poorly here —
   the committed `outputs/logs/trace_summary.csv` showed ESS ≈ 60–120 out of 8,000 draws
   and no `r_hat`. Fix: model `tau` as continuous with a sigmoid relaxation of the switch
   function (`weight = sigmoid((t - tau) / smoothness)`), enabling full NUTS sampling.
   **Verified on the real 9,010-row dataset after the fix**: `max_r_hat = 1.0092`,
   `min_ess_bulk = 415.2` — both inside the configured reliability thresholds.

2. **Silent data loss from a mixed date format.** `data/raw/BrentOilPrices.csv` switches
   date format partway through the file: rows through 2020-04-21 are `20-May-87`
   (`%d-%b-%y`); every row from 2020-04-22 onward is `Apr 22, 2020` (`%b %d, %Y`). Parsing
   with a single `pd.to_datetime(..., format="%d-%b-%y")` silently dropped 651 of 9,011
   rows (~7%) — the **entire 2020–2022 tail, including the 2022 Russia-Ukraine oil
   shock**. First pipeline run (before the fix) detected a change point at 2020-04-15
   (last day of usable data); after fixing `src/data/ingestion.py` to try both formats in
   sequence, the pipeline correctly uses the full 1987–2022 range and detects a different,
   better-supported change point at 2006-02-02. Regression test:
   `test_load_raw_prices_handles_mixed_date_formats`.

3. **Invalid JSON from `/api/prices`.** After adding the rolling-volatility column, the
   first ~20 rows have `Volatility_21d = NaN`. Python's `json` module happily emits a
   literal `NaN` token, which is **not valid JSON** per RFC 8259 — `JSON.parse` in a
   browser throws on it, even though Python-side `json.loads` (and therefore
   `resp.get_json()` in a naive test) tolerates it. Fixed by converting `NaN` → `None`
   before `jsonify` so it serializes as `null`. Regression test explicitly asserts on the
   **raw response body** (`"NaN" not in raw`), not the parsed object, because parsing
   with Python's own `json` module would not have caught this.

4. **Generic error handler swallowing real HTTP status codes.** A blanket
   `@app.errorhandler(Exception)` returning 500 for everything would also catch Flask's
   own `404 NotFound` / `405 MethodNotAllowed` for unmatched routes, always reporting 500.
   Fixed by adding a more specific `@app.errorhandler(HTTPException)` that passes through
   `err.code`.

5. **Dependency version resolution.** `pymc>=5.10` (with default `arviz`) was tried
   first, but the arviz/pymc/scipy/matplotlib combination that pip resolved on Python
   3.13 was internally inconsistent (arviz using a `scipy.signal` function removed in
   newer scipy; then a newer arviz using an `xarray`-DataTree API pymc 5.x doesn't
   support). Resolved by pinning **`pymc>=6.0,<7.0` + `arviz>=1.0,<2.0`**, then fixing two
   small call-site API changes in `src/modeling/change_point_model.py` for
   arviz-stats 1.x: `az.hdi(..., hdi_prob=...)` → `prob=...`, and `az.compare(..., ic="loo")`
   → `az.compare(...)` (LOO is now the only supported method). Verified by actually
   running the sampler and the model-comparison path end-to-end on real data, not just by
   getting imports to succeed.

---

## 4. Files removed / cleaned up

- `outputs/outputs/` — empty nested duplicate directory.
- `notebooks/1_eda.ipynb`, `notebooks/2_change_point_model.ipynb` — duplicate/stub
  notebooks superseded by the rebuilt `01_`/`02_` versions.
- `dashboard/frontend/frontend/*` — the entire React app was nested one level too deep
  (`dashboard/frontend/frontend/src/...`); flattened up to `dashboard/frontend/src/...`.
- `dashboard/backend/package.json`, `package-lock.json` — stray **npm** dependency files
  (axios, react-bootstrap, chart.js, …) that had no business inside the **Python** Flask
  backend directory; clearly the result of an accidental `npm install` run from the wrong
  folder at some point. Nothing in the backend used them.
- `dashboard/frontend/App.js`, `dashboard/frontend/index.js` (at the frontend root, not
  `src/`) — dead duplicate copies of the real entry points under `src/`; Create React
  App's actual entry point is `src/index.js`, so these were unreachable dead code.
- `dashboard/frontend/src/chart-setup.js` — grepped for any import of this file across the
  frontend source tree; found none. Dead code.

---

## 5. What was deliberately *not* changed

- The core `Flask` + `React` + `PyMC` technology choices — all appropriate for this
  project's actual size; no framework migrations.
- The Bayesian modeling *approach* (change-point detection with a mean/volatility shift
  hypothesis) — only its numerical parameterization (discrete → continuous `tau`) changed,
  because that parameterization was the actual defect, not the modeling idea.
- No database, message queue, or vector store was introduced — the dataset is ~9,000 rows
  of daily prices and ~11 curated events; a flat-file pipeline (CSV/JSON artifacts) is the
  appropriate scale, and adding infrastructure here would be complexity without a real
  problem behind it.

---

## 6. Verification performed (not just written — actually run)

- `pytest` — **35/35 passing**, including 3 real (not mocked) MCMC smoke tests.
- `ruff check` — clean after auto-fixing 4 import-order/unused-import findings.
- Full pipeline run on the real, complete dataset (`python pipelines/run_pipeline.py`):
  produced correct output — detected change point 2006-02-02, `reliable: true`
  diagnostics, and (on an earlier verification run using the COVID-era subset before the
  date-format fix was in place) a coherent narrative correctly identifying the 2020 oil
  crash and its nearest catalogued event.
- Model comparison (`--variant compare`) run end-to-end on real data — confirms `null` vs
  `mean_shift` vs `mean_vol_shift` all sample and rank via PSIS-LOO without error.
- Flask API started for real and hit with `curl`: `/api/health`, `/api/prices`,
  `/api/events`, `/api/stats`, `/api/change-point`, `/api/insights`, and an unmatched
  route (confirmed real `404`, not a swallowed `500`).
- React frontend production build (`react-scripts build`) — compiles successfully,
  189.76 kB gzipped main bundle; only pre-existing third-party sourcemap warnings from
  `react-datepicker`, no errors in any of the code touched.
