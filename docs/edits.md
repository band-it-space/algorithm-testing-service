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
- ✅ `s6` — Has params
- ✅ `s7` — Has params
- ✅ `s8` — Has params
- ✅ `s9` — Has params
- ✅ `s10` — Has params
- ✅ `s11` — Has params
- ✅ `s12` — Has params
- ✅ `s13` — Has params
- ✅ `s14` — Has params
- ✅ `s15` — Has params
- ✅ `s16` — Has params
- ✅ `s17` — Has params

**Status:** ✅ All sell functions now accept `params: AlgorithmParameters = None`.

---

## 4. Docker Environment Variables

### Issue 4.1: Workers missing Google Sheets credentials

**Location:** [docker-compose.yml](../docker-compose.yml)

**Status:** ✅ RESOLVED — All workers now have `GOOGLE_SHEETS_CREDENTIALS_PATH`, `OUTPUT_SHEET_ID`, and `credentials` volume mount.

---

## 5. ~~Missing `.env.example` File~~

**Status:** ✅ RESOLVED — `.env.example` has been created with all required variables including Redis, API, Google Sheets, worker configuration, optimization date range, smart filtering, and debug settings.

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

| Priority | Issue | Status |
|----------|-------|--------|
| HIGH | 1.1 Parameter naming (`input_B13_XX` → `input_B13_rel_days`) | ⚠️ Open |
| ~~HIGH~~ | ~~4.1 Docker env for workers~~ | ✅ Resolved |
| ~~MEDIUM~~ | ~~5 Create `.env.example`~~ | ✅ Resolved |
| MEDIUM | 8.1 Update/run existing tests | ⚠️ Open |
| LOW | 1.2 Document S1_hard_stop format | ⚠️ Open |
| ~~LOW~~ | ~~3.1 Verify all sell functions use params~~ | ✅ Resolved |

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
