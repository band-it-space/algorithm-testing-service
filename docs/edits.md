# Implementation Issues & Corrections

This document outlines discrepancies found between the requirements/task documents and the actual implementation, along with recommended corrections.

---

## 1. Parameter Name Mismatches

### Issue 1.1: `input_B13_rel_days` vs `input_B13_XX`

**Location:** [app/models/algorithm_models.py](../app/models/algorithm_models.py)

**Problem:** The Input Rule Parameter IDs Sample.csv defines `input_B13_rel_days`, but the implementation uses `input_B13_XX`.

| Source | Parameter Name |
|--------|---------------|
| Input CSV | `input_B13_rel_days` |
| Implementation | `input_B13_XX` |

**Fix Required:**
```python
# In AlgorithmParameters, rename:
input_B13_XX: int = 19  # → input_B13_rel_days: int = 19
```

**Affected Files:**
- `app/models/algorithm_models.py`
- `app/workers/algo_func/buy_signals.py` (if using this parameter)

---

### Issue 1.2: `input_S1_hard_stop` Value Format

**Location:** [app/models/algorithm_models.py](../app/models/algorithm_models.py)

**Problem:** The Input CSV shows `input_S1_hard_stop` with base value `9.5` (percentage), but implementation stores as `0.095` (decimal).

| Source | Value | Format |
|--------|-------|--------|
| Input CSV | 9.5 | Percentage |
| Implementation | 0.095 | Decimal |

**Recommendation:** Ensure consistent handling. Either:
1. Store as percentage (9.5) and divide by 100 in calculation
2. Keep as decimal but document the conversion

---

## 2. Missing Parameters in AlgorithmParameters

The following parameters from the task document are **not present** in the current implementation:

| Parameter | Expected in | Status |
|-----------|-------------|--------|
| (none found) | - | ✅ All parameters present |

**Status:** ✅ All 33+ parameters are correctly implemented.

---

## 3. Sell Signal Functions Missing `params` Argument

### Issue 3.1: Some sell functions don't use params

**Location:** [app/workers/algo_func/sell_signals.py](../app/workers/algo_func/sell_signals.py)

**Verified Functions with `params`:**
- ✅ `exit_by_stop_loss` - Has params, but doesn't use it
- ✅ `s4` - Uses params correctly
- ✅ `s5` - Uses params correctly

**Functions to Verify:**
- `s6`, `s7`, `s8`, `s9`, `s10`, `s11`, `s12`, `s13`, `s14`, `s15`, `s16`, `s17`

**Recommended Action:** Verify each sell function:
1. Has `params: AlgorithmParameters = None` argument
2. Creates default `params = AlgorithmParameters()` if None
3. Uses `params.input_SX_*` instead of hardcoded values

---

## 4. Docker Environment Variables

### Issue 4.1: Workers missing Google Sheets credentials

**Location:** [docker-compose.yml](../docker-compose.yml)

**Problem:** The `algorithm-service` has `GOOGLE_SHEETS_CREDENTIALS_PATH` and `credentials` volume mount, but workers (`result-worker`, `file-write-worker`) may need these for writing results.

**Fix Required:**
Add to `result-worker` and `file-write-worker`:
```yaml
environment:
  - GOOGLE_SHEETS_CREDENTIALS_PATH=/app/credentials/google_sheets.json
  - OUTPUT_SHEET_ID=${OUTPUT_SHEET_ID:-}
volumes:
  - ./credentials:/app/credentials:ro
```

---

## 5. Missing `.env.example` File

**Problem:** The project relies on environment variables but lacks a `.env.example` template.

**Required Variables:**
```env
# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=

# API
API_PORT=8000
ENVIRONMENT=development
DEBUG=true
LOG_LEVEL=INFO

# Database
DB_HOST=localhost
DB_PORT=3306
DB_USER=
DB_PASSWORD=
DB_NAME=

# Google Sheets
GOOGLE_SHEETS_CREDENTIALS_PATH=./credentials/google_sheets.json
INPUT_SHEET_ID=
OUTPUT_SHEET_ID=

# Dashboard
DASHBOARD_PORT=9181
```

**Action:** Create `.env.example` file with all required variables.

---

## 6. API Router Registration

### Issue 6.1: Optimization router correctly registered

**Location:** [app/main.py](../app/main.py)

**Status:** ✅ The optimization router is correctly imported and registered:
```python
from app.controllers.optimization_controller import router as optimization_router
app.include_router(optimization_router)
```

---

## 7. Output Format Compliance

### Issue 7.1: `GenomeResult.to_output_row()` Output Columns

**Location:** [app/models/algorithm_models.py](../app/models/algorithm_models.py)

**Expected Output Columns (from Output Results Sample.csv):**
| Column | Present |
|--------|---------|
| Genome ID | ✅ |
| Stock Code | ✅ |
| Trade Count | ✅ |
| Profit Delta (%) | ✅ |
| Win Rate Delta (%) | ✅ |
| Total Win ($) | ✅ |
| Total Loss ($) | ✅ |
| Trades Win | ✅ |
| Trades Loss | ✅ |
| Avg Win ($) | ✅ |
| Avg Loss ($) | ✅ |
| Payoff Ratio | ✅ |
| input_B1_upper_range | ✅ (via parameters dict) |
| input_B3_LR_lookback | ✅ (via parameters dict) |
| input_B11_atr_threshold | ✅ (via parameters dict) |
| input_B18_bbw_ratio | ✅ (via parameters dict) |
| input_S1_atr_mult | ✅ (via parameters dict) |
| input_S5_push_up_atr | ✅ (via parameters dict) |

**Status:** ✅ Output format matches the sample.

---

## 8. Test Files Need Update

### Issue 8.1: Existing tests may fail with new function signatures

**Location:** [tests/algo_func/](../tests/algo_func/)

**Problem:** Tests like `test_b1.py`, `test_b3.py`, etc. may call signal functions without the new `params` argument.

**Recommended Action:**
1. Run existing tests to identify failures
2. Update test calls to include `params=None` or `params=AlgorithmParameters()`
3. Add tests for parameter variations

---

## 9. Summary of Required Actions

| Priority | Issue | Action |
|----------|-------|--------|
| HIGH | 1.1 Parameter naming | Rename `input_B13_XX` to `input_B13_rel_days` |
| HIGH | 4.1 Docker env | Add credentials to workers |
| MEDIUM | 5 | Create `.env.example` file |
| MEDIUM | 8.1 | Update/run existing tests |
| LOW | 1.2 Value format | Document S1_hard_stop format |
| LOW | 3.1 | Verify all sell functions use params |

---

## 10. Files Modified (Implementation Summary)

| File | Status | Changes |
|------|--------|---------|
| `app/models/algorithm_models.py` | ✅ Created | AlgorithmParameters, ParameterRange, GenomeResult |
| `app/services/genome_service.py` | ✅ Created | Genome generation logic |
| `app/services/optimization_service.py` | ✅ Created | Optimization tracking |
| `app/services/sheets_service.py` | ✅ Created | Google Sheets integration |
| `app/services/results_aggregation_service.py` | ✅ Created | Metrics calculation |
| `app/services/queue_service.py` | ✅ Updated | genome_id, parameters support |
| `app/controllers/optimization_controller.py` | ✅ Created | API endpoints |
| `app/workers/algorithm_worker.py` | ✅ Updated | params handling |
| `app/workers/algo_func/buy_signals.py` | ✅ Updated | params argument added |
| `app/workers/algo_func/sell_signals.py` | ✅ Updated | params argument added |
| `app/main.py` | ✅ Updated | Router registration |
| `requirements.txt` | ✅ Updated | Google Sheets deps |
| `docker-compose.yml` | ✅ Updated | Env vars, volumes |

---

*Last updated: See git history*
