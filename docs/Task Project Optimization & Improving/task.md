# Task: Project Optimization & Improving

## Implementation Flow

This document provides a step-by-step guide to implement all requirements in the correct order.

---

## Phase 1: Environment Configuration
**Status:** [x] Complete

### Step 1.1: Create/Update `.env.example`
**Priority:** High | **Estimated:** 10 min | **Status:** [x] Complete

Added the following variables to `.env.example`:
```env
# Worker Parallelization
ALGORITHM_WORKER_COUNT=1
RESULT_WORKER_COUNT=1
FILE_WORKER_COUNT=1
WORKER_CONCURRENT_TASKS=1

# Algorithm Worker Debug Mode
ALGORITHM_DEBUG=false
LOG_PROGRESS_INTERVAL=100
```

**Verification:** ✅ File contains all new environment variables with default values.

---

## Phase 2: Fix Calculation Formulas
**Status:** [x] Complete

### Step 2.1: Update Profit Delta Calculation
**Priority:** High | **Estimated:** 30 min | **Status:** [x] Complete

**File:** `app/services/optimization_service.py`

Implemented:
- Added `_recalculate_deltas()` method called when retrieving results
- Formula: `((genome_profit - base_profit) / |base_profit|) × 100`
- Base algorithm (G_000) returns `profit_delta = 0`
- Division by zero handled (returns 0)
- Deltas are calculated at retrieval time using BASE genome for comparison

**Verification:** 
- Base profit=1000, genome profit=1200 → delta = 20% ✅
- Base profit=1000, genome profit=800 → delta = -20% ✅
- Base profit=0 → delta = 0% ✅
- API returns correct deltas ✅

### Step 2.2: Verify Win Rate Calculation
**Priority:** Medium | **Estimated:** 15 min | **Status:** [x] Complete

**File:** `app/services/optimization_service.py`

Win Rate Delta calculated as percentage point difference from BASE.

**Verification:** 3 wins / 5 total = 60% win rate ✅

---

## Phase 3: Log Optimization
**Status:** [x] Complete

### Step 3.1: Update Logging Configuration
**Priority:** Medium | **Estimated:** 20 min | **Status:** [x] Complete

**File:** `app/config/logging_config.py`

Added:
- `get_algorithm_debug_mode() -> bool`
- `get_log_progress_interval() -> int`

### Step 3.2: Refactor Algorithm Worker Logging
**Priority:** High | **Estimated:** 45 min | **Status:** [x] Complete

**File:** `app/workers/algorithm_worker.py`

Implemented:
- Module-level `ALGORITHM_DEBUG` and `LOG_INTERVAL` settings
- Per-day trade logging changed to `logger.debug()`
- Signal logging wrapped in `if ALGORITHM_DEBUG:` condition
- Progress logging every N days
- Summary log at task completion

**Verification:**
- `ALGORITHM_DEBUG=false`: No signal logs, only progress every N days ✅
- `ALGORITHM_DEBUG=true`: Full signal data in logs ✅

---

## Phase 4: New API Routes
**Status:** [x] Complete

### Step 4.1: Create Sheets Controller
**Priority:** Medium | **Estimated:** 45 min | **Status:** [x] Complete

**Created File:** `app/controllers/sheets_controller.py`

Endpoint: `GET /api/v1/sheets/health`

### Step 4.2: Update Sheets Service
**Priority:** Medium | **Estimated:** 30 min | **Status:** [x] Complete

**File:** `app/services/sheets_service.py`

Added methods:
- `check_read_permission() -> bool`
- `check_write_permission() -> bool`
- `get_sheet_config() -> dict`

### Step 4.3: Create Genome Controller
**Priority:** Low | **Estimated:** 30 min | **Status:** [x] Complete

**Created File:** `app/controllers/genome_controller.py`

Endpoint: `GET /api/v1/genome/{genome_id}/parameters`

### Step 4.4: Update Genome Service
**Priority:** Low | **Estimated:** 20 min | **Status:** [x] Complete

**File:** `app/services/genome_service.py`

Added `get_genome_parameters(genome_id, optimization_id)` function.

### Step 4.5: Register Routers in Main
**Priority:** Medium | **Estimated:** 10 min | **Status:** [x] Complete

**File:** `app/main.py`

Registered `sheets_router` and `genome_router`.

**Verification:**
- `GET /api/v1/sheets/health` returns connection status ✅
- `GET /api/v1/genome/G_001/parameters` returns genome config ✅

---

## Phase 5: Parallelization
**Status:** [x] Complete

### Step 5.1: Update Queue Configuration
**Priority:** High | **Estimated:** 15 min | **Status:** [x] Complete

**File:** `app/config/queue_config.py`

Added:
- `get_worker_count(worker_type)` function
- `get_concurrent_tasks()` function

### Step 5.2: Update Algorithm Worker Startup
**Priority:** High | **Estimated:** 45 min | **Status:** [x] Complete

**File:** `workers/start_algorithm_worker.py`

Implemented multiprocessing with configurable worker count.

### Step 5.3: Update Result Worker Startup
**Priority:** Medium | **Estimated:** 30 min | **Status:** [x] Complete

**File:** `workers/start_result_worker.py`

Implemented multiprocessing with configurable worker count.

### Step 5.4: Update File Write Worker Startup
**Priority:** Medium | **Estimated:** 30 min | **Status:** [x] Complete

**File:** `workers/start_file_write_worker.py`

Implemented multiprocessing with configurable worker count.

### Step 5.5: Update docker-compose.yml
**Priority:** Medium | **Estimated:** 15 min | **Status:** [x] Complete

Added all environment variables to ensure proper passthrough to containers.

**Verification:**
- Set `ALGORITHM_WORKER_COUNT=4`
- Start workers
- Verify 4 processes running with `ps aux | grep algorithm` ✅

---

## Phase 6: Bug Fixes - Profit Delta & Win Rate Not Calculated
**Status:** [x] Complete

### Issue Analysis
The Profit Delta and Win Rate Delta values were showing **0** for all genomes because deltas were not recalculated when results were retrieved.

### Step 6.1: Fix Profit Delta Calculation in Results Retrieval
**Priority:** Critical | **Estimated:** 45 min | **Status:** [x] Complete

**File:** `app/services/optimization_service.py`

**Changes:**
1. Added `_recalculate_deltas()` method
2. Modified `get_optimization_results()` to call recalculation
3. Groups results by stock_code, finds BASE (G_000) for each stock
4. Applies profit delta and win rate delta calculation

**Verification:**
- G_000 (BASE): Profit Delta = 0, Win Rate Delta = 0 ✅
- Other genomes: Correct relative delta calculated ✅

---

## Phase 7: Complete Log Silencing for Algorithm Worker
**Status:** [x] Complete

### Step 7.1: Silence buy_signals.py Logging
**Priority:** High | **Estimated:** 30 min | **Status:** [x] Complete

**File:** `app/workers/algo_func/buy_signals.py`

**Changes:**
- Added `ALGORITHM_DEBUG` flag from environment
- Changed all `logger.info()` to conditional `if ALGORITHM_DEBUG: logger.debug()`

### Step 7.2: Add Debug Control to Other algo_func Modules
**Priority:** Medium | **Estimated:** 20 min | **Status:** [x] Complete

**Files:**
- `app/workers/algo_func/sell_signals.py`

**Verification:**
- `ALGORITHM_DEBUG=false`: Docker logs show only task start/complete, progress every N days ✅
- `ALGORITHM_DEBUG=true`: Full detailed logs including buy/sell conditions ✅

---

## Phase 8: In-Worker Task Parallelization
**Status:** [x] Complete

### Step 8.1: Add Environment Configuration
**Priority:** High | **Estimated:** 10 min | **Status:** [x] Complete

**Added to `.env.example` and `docker-compose.yml`:**
```env
WORKER_CONCURRENT_TASKS=1
```

### Step 8.2: Update Queue Configuration
**Priority:** High | **Estimated:** 15 min | **Status:** [x] Complete

**File:** `app/config/queue_config.py`

Added `get_concurrent_tasks()` function.

### Step 8.3: Update docker-compose.yml
**Priority:** Medium | **Estimated:** 10 min | **Status:** [x] Complete

Added `WORKER_CONCURRENT_TASKS` to all worker environments.

---

## Implementation Order Summary

| Order | Task | Priority | Time | Status |
|-------|------|----------|------|--------|
| 1 | Step 1.1: Environment variables | High | 10 min | ✅ |
| 2 | Step 2.1: Profit Delta fix | High | 30 min | ✅ |
| 3 | Step 2.2: Win Rate verification | Medium | 15 min | ✅ |
| 4 | Step 3.1: Logging config | Medium | 20 min | ✅ |
| 5 | Step 3.2: Worker log refactor | High | 45 min | ✅ |
| 6 | Step 4.1-4.5: API routes | Medium | 2h 15min | ✅ |
| 7 | Step 5.1-5.5: Parallelization | High | 2h 15min | ✅ |
| 8 | Phase 6: Delta calculation fix | Critical | 45 min | ✅ |
| 9 | Phase 7: Log silencing | High | 50 min | ✅ |
| 10 | Phase 8: Concurrent tasks config | Medium | 35 min | ✅ |

**Total Estimated Time:** ~8 hours

---

## Updated Testing Checklist

- [x] Environment variables load correctly
- [x] Profit Delta calculates correctly in `/optimization/{id}/results`
- [x] Win Rate Delta calculates correctly
- [x] Win Rate counts profitable closes
- [x] `ALGORITHM_DEBUG=false` silences ALL verbose logs (including buy_signals)
- [x] `ALGORITHM_DEBUG=true` shows full signal data
- [x] `GET /api/v1/sheets/health` works
- [x] `GET /api/v1/genome/{id}/parameters` works
- [x] Multiple workers spawn based on config
- [x] `WORKER_CONCURRENT_TASKS` configuration available
- [x] Graceful shutdown works with SIGTERM

---

## Rollback Plan

If issues arise:
1. Set `*_WORKER_COUNT=1` to disable parallelization
2. Set `ALGORITHM_DEBUG=true` to restore original logging
3. API routes are additive - no rollback needed
4. Calculation fixes can be reverted via git

