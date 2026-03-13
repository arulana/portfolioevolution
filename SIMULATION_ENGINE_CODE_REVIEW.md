# Code Review: Portfolio Evolution Simulation Engine

**Reviewer:** Principal Engineer (AI)  
**Date:** 2025-03-13  
**Files reviewed:**
- `src/portfolio_evolution/engines/simulation_runner.py`
- `src/portfolio_evolution/engines/pipeline_engine.py`
- `src/portfolio_evolution/engines/funded_engine.py`
- `src/portfolio_evolution/engines/rating_engine.py`
- `src/portfolio_evolution/engines/deposit_engine.py`
- `src/portfolio_evolution/engines/deposit_capture.py`
- `src/portfolio_evolution/engines/pipeline_generator.py`
- `src/portfolio_evolution/state/persistence.py`
- `src/portfolio_evolution/api/scheduler.py`
- Supporting: `rng.py`, `config_loader.py`, `calendar.py`, `duckdb_store.py`, `rollforward.py`, `balance_sheet.py`

---

## Summary

The simulation engine is well-structured with clear separation of concerns across pipeline, funded, rating, deposit, and aggregation engines. Financial calculations (amortisation, decay, rating migration) are mathematically sound. The main risks are: (1) scheduler cold-start when config paths are empty or invalid, (2) potential `IndexError` in `_persist_day_to_store` if aggregation fails mid-step, (3) config mutation in the scheduler affecting thread safety, and (4) missing validation for malformed config structures (e.g. rating matrix format).

---

## 1. Critical Issues (Must Fix)

| # | Issue | File:Line | Why It Matters | Suggested Fix |
|---|-------|-----------|----------------|---------------|
| 1 | **Scheduler cold-start fails when `funded_file`/`pipeline_file` are empty or invalid** | `scheduler.py:207-224` | `funded_file = project_root / self._config.get("funded_file", "")` yields `project_root` when empty. `Path("").exists()` is True for cwd. `load_portfolio(project_root, ...)` is then called; `_read_dataframe` treats a directory as unsupported format and raises `ValueError`. Cold-start crashes instead of returning empty lists. | Guard: `if not funded_file or not funded_file.is_file(): funded = []` (and same for pipeline). Only call `load_portfolio` when path is a valid file. |
| 2 | **Scheduler mutates shared config** | `scheduler.py:134-137` | `self._config["calendar"]["start_date"] = ...` mutates the config in place. If the same config dict is shared elsewhere or if two runs overlap (e.g. manual `run_now` during scheduled run), this can cause non-deterministic or incorrect start dates. | Create a copy of config for the run: `run_config = {**self._config, "calendar": {**self._config.get("calendar", {}), "start_date": ...}}` and pass `run_config` to `run_deterministic`. |
| 3 | **Persistence load failures unhandled** | `scheduler.py:131-134` | `load_state(state_dir)` can raise (e.g. corrupted JSON, `model_validate` failure). The exception propagates and the scheduled run fails with no fallback. | Wrap in try/except: on `json.JSONDecodeError` or `ValidationError`, log warning, call `_cold_start()`, and optionally clear corrupted state. |

---

## 2. Important Issues (Should Fix)

| # | Issue | File:Line | Why It Matters | Suggested Fix |
|---|-------|-----------|----------------|---------------|
| 1 | **`_persist_day_to_store` assumes non-empty `daily_aggregates`** | `simulation_runner.py:210` | `agg = state.daily_aggregates[-1]` raises `IndexError` if empty. Current flow always appends first, but refactoring could break this. | Add guard: `if not state.daily_aggregates: return` at start of `_persist_day_to_store`. |
| 2 | **Empty `segment_weights` causes crash** | `pipeline_generator.py:117-124` | If `segment_weights` is `{}`, `segments = []` and `gen.choice([], p=[])` raises. | Guard: `if not segments: return []` before the loop, or use default segment_weights when empty. |
| 3 | **Rating matrix format assumption** | `rating_engine.py:84-86` | `_convert_cadence(annual_row, cadence)` expects `annual_row` to be a list of floats in rating order. If config uses `{rating: probability}` dict format, iteration yields keys (strings), and `annual_to_daily_prob("AAA")` fails. | Document required format; add validation: `if isinstance(annual_row, dict): annual_row = [annual_row.get(r, 0.0) for r in ratings]`. |
| 4 | **Deposit evolution: `balance_change` sign inconsistency** | `deposit_engine.py:105` | `balance_change = balance - deposit.current_balance` is computed after all adjustments. With utilisation linkage, `inflow_amount` and `withdrawal_amount` are set from `diff * adjustment_factor`, but `balance_change` can be negative even when `inflow_amount > 0` if decay/withdrawals dominate. The field semantics are correct; just ensure consumers understand it's net change. | Add docstring: `balance_change` = net change (can be negative despite inflows). |
| 5 | **`run_time` format not validated** | `scheduler.py:69-71` | `hour, minute = self._run_time.split(":")` assumes "HH:MM". Malformed values (e.g. "6", "25:00") cause `ValueError` or invalid cron. | Validate: `parts = self._run_time.split(":"); assert len(parts) >= 2; hour, minute = int(parts[0]), int(parts[1])`; handle invalid format with a clear error. |
| 6 | **Required config files raise immediately** | `simulation_runner.py:127-130` | `load_yaml(config_dir / "pipeline_transitions.yaml")` etc. raise `FileNotFoundError` if missing. No user-friendly message or fallback. | Catch `FileNotFoundError`, log path, and raise with message: "Required config X not found. Ensure config/ directory exists." |
| 7 | **Deposit threshold hardcoded** | `simulation_runner.py:388` | `if dep_result.position.current_balance > 0.01` — magic number. Different currencies or scales may need different thresholds. | Extract to config: `deposit_config.get("min_balance_threshold", 0.01)`. |

---

## 3. Minor Issues (Nice to Fix)

| # | Issue | File:Line | Why It Matters | Suggested Fix |
|---|-------|-----------|----------------|---------------|
| 1 | **Tenor fallback uses 60 months** | `pipeline_engine.py:292` | When `maturity_date` and `tenor_months` are both None, fallback is 60 months. This is arbitrary. | Document in docstring; consider making configurable via `funded_config` default_tenor_months. |
| 2 | **`uuid.uuid4()` in deterministic run** | `simulation_runner.py:102` | `run_id = str(uuid.uuid4())[:8]` is non-deterministic. Same seed, same inputs → different run_id each time. Affects logging/tracing, not simulation results. | Acceptable for run identification; document that run_id is not deterministic. Or derive from seed + horizon + start_date hash if reproducibility is desired. |
| 3 | **Pipeline generator uses `rng.get_generator()` directly** | `pipeline_generator.py:105` | Other engines use `rng.uniform()`. Pipeline generator uses raw numpy generator. Both use `(path_id=0, scenario_id="baseline")`. Order of draws is deterministic. | No functional issue; consider adding `rng.poisson()`, `rng.choice()` to `SeededRNG` for API consistency. |
| 4 | **Persistence: no atomic write** | `persistence.py:69-88` | Four separate file writes. If process crashes mid-write, state can be partially updated. | Use temp file + rename pattern, or write to a single JSON file. |
| 5 | **Calendar `end_date` when empty** | `calendar.py:118` | `self._days[-1].date if self._days else self._start_date` — when `horizon_days=0`, `_days` is empty. `end_date` returns `start_date`. | Document; consider raising if horizon is 0. |

---

## 4. Architecture Observations

### Strengths
- **Clear engine boundaries**: Pipeline, funded, rating, deposit engines are independent and testable.
- **Determinism**: `SeededRNG` with derived seeds per (path_id, scenario_id) ensures reproducibility. Hash-based seed derivation avoids Python's randomized `hash()`.
- **Resource management**: `SimulationStore` uses context manager; file I/O uses `Path.write_text`/`read_text` (no handle leaks).
- **Financial correctness**:
  - Linear amortisation: `remaining_days = max((maturity_date - sim_date).days, 1)` avoids division by zero.
  - Deposit decay: `balance *= 0.5^(1/half_life)` is correct exponential decay.
  - Rating migration: annual→daily/monthly conversion `1 - (1-p)^(1/365)` is correct.
  - Pipeline probabilities: cumulative comparison without normalisation is appropriate for "daily probability of transition".

### Concerns
- **Scheduler runs in thread pool**: `asyncio.to_thread(self._execute_run)` runs the simulation in a worker thread. APScheduler typically prevents overlapping jobs, but `run_now()` can be called from API while a scheduled job runs — potential race on `_config` mutation.
- **No circuit breaker**: External config/file loads have no retry or backoff. Transient filesystem issues cause immediate failure.
- **Strategy signals not used in pipeline**: `strategy_adj` is computed but never passed to `advance_pipeline_day` or `generate_daily_inflow`. Likely placeholder for future work.

### Recommendations
1. Add integration tests with fixed seed to assert deterministic output across runs.
2. Add property-based tests for edge cases: empty funded/pipeline, zero balances, `horizon=0`.
3. Consider extracting config loading into a dedicated function that validates required keys and returns a typed config object.

---

## 5. Correctness Verification

| Calculation | Location | Status |
|-------------|----------|--------|
| Linear amortisation | `funded_engine.py:46-52` | Correct: `daily = funded_amount / max(remaining_days, 1)` |
| Maturity check | `funded_engine.py:76-77` | Correct: `sim_date > maturity_date + grace` |
| Deposit decay | `deposit_engine.py:57-59` | Correct: `0.5^(1/half_life)` per day |
| Annual→daily prob | `rating_engine.py:27-31` | Correct: `1 - (1-p)^(1/365)` |
| Pipeline age factor | `pipeline_engine.py:67` | Correct: `0.5^(days/half_life)` for decay |
| Division by zero | Multiple | Guarded: `total_committed > 0`, `total_deposits > 0`, `linked_loan_amount > 0`, `remaining_days > 0` |

---

## 6. Edge Cases Covered

| Edge Case | Handling |
|-----------|----------|
| Empty funded + pipeline | `simulation_runner.py:112-114`: `start_date = max(all_dates) if all_dates else date.today()` |
| Zero `funded_amount` | `funded_engine.py:39-40`: returns 0 amortisation |
| `maturity_date` None | `funded_engine.py:46`: returns 0 for linear; `check_maturity` returns False |
| `half_life` ≤ 0 | `pipeline_engine.py:65-66`, `deposit_engine.py:56`: returns 1.0 or skips |
| Absorbing rating (D) | `rating_engine.py:142-151`: no migration |
| Deposit balance ≤ 0.01 | `simulation_runner.py:388`: filtered out |

---

## 7. Production Readiness Score

| Area | Status | Notes |
|------|--------|-------|
| Error handling | Needs work | Config/file load failures propagate; persistence load unhandled in scheduler |
| Logging | Ready | Scheduler logs key events; engines are mostly silent (acceptable for library) |
| Monitoring | Needs work | No metrics, health checks, or run-duration tracking |
| Security | Ready | No secrets in code; paths from config |
| Performance | Ready | No obvious N+1; Polars used for batch writes |
| Rollback safety | Ready | State persistence is additive; old runs remain queryable |

---

## Verdict

**Ship?** Yes with fixes

Address critical issues #2 (scheduler cold-start), #3 (config mutation), and #4 (persistence load handling) before production. Important issues #1 (empty segment_weights) and #2 (rating matrix format) should be fixed to avoid runtime crashes on edge configs. The simulation logic itself is sound and deterministic.
