# Requirements: Project Optimization & Improving

## 1. Parallelization - Multiple Worker Processes

### 1.1 Environment Variables
Add to `.env.example`:
```env
ALGORITHM_WORKER_COUNT=1    # Number of algorithm worker processes
RESULT_WORKER_COUNT=1       # Number of result worker processes
FILE_WORKER_COUNT=1         # Number of file write worker processes
```

### 1.2 Queue Configuration
**File:** `app/config/queue_config.py`
- Add `get_worker_count(worker_type: str) -> int` function
- Read worker counts from environment variables

### 1.3 Worker Startup Scripts
**Files:**
- `workers/start_algorithm_worker.py`
- `workers/start_result_worker.py`
- `workers/start_file_write_worker.py`

**Changes:**
- Import `multiprocessing` module
- Read `*_WORKER_COUNT` from environment
- Spawn N worker processes in a process pool
- Handle graceful shutdown (SIGTERM/SIGINT) for all spawned processes

### 1.4 Docker Configuration
**File:** `Dockerfile`
- Update CMD/ENTRYPOINT to use new environment variables

---

## 2. Log Optimization for Algorithm Worker

### 2.1 Environment Variables
Add to `.env.example`:
```env
ALGORITHM_DEBUG=false       # Enable verbose debug logging
LOG_PROGRESS_INTERVAL=100   # Log progress every N trade days
```

### 2.2 Logging Configuration
**File:** `app/config/logging_config.py`
- Add `get_algorithm_debug_mode() -> bool` helper function
- Configure conditional log handlers based on debug flag

### 2.3 Algorithm Worker Refactoring
**File:** `app/workers/algorithm_worker.py`

**Changes:**
- Move per-day trade logging from `logger.info` to `logger.debug`
- Add conditional check: only log signals when `ALGORITHM_DEBUG=true`
- Add progress logging every N days (configurable via `LOG_PROGRESS_INTERVAL`)
- Include signal data in debug mode logs
- Add summary log at task completion with key metrics only

---

## 3. New API Routes

### 3.1 Google Sheets Health Check

**Endpoint:** `GET /api/v1/sheets/health`

**New File:** `app/controllers/sheets_controller.py`

**Response Schema:**
```json
{
  "connected": true,
  "read": true,
  "write": true,
  "config": {
    "credentials_path": "credentials/google_sheets.json",
    "input_sheet_id": "...",
    "output_sheet_id": "..."
  },
  "error": null
}
```

**Service Changes:**
**File:** `app/services/sheets_service.py`
- Add `check_read_permission(sheet_id: str) -> bool` method
- Add `check_write_permission(sheet_id: str) -> bool` method
- Add `get_sheet_config() -> dict` method

**Registration:**
**File:** `app/main.py`
- Import and register `sheets_router`

### 3.2 Genome Parameters by ID

**Endpoint:** `GET /api/v1/genome/{genome_id}/parameters`

**Query Parameters:**
- `optimization_id` (optional) - scope search to specific optimization

**New File:** `app/controllers/genome_controller.py`

**Response Schema:**
```json
{
  "genome_id": "G_001",
  "optimization_id": "opt_abc123",
  "parameters": {
    "rule_1": { ... },
    "rule_2": { ... }
  }
}
```

**Service Changes:**
**File:** `app/services/genome_service.py`
- Add `get_genome_parameters(genome_id: str, optimization_id: Optional[str]) -> dict`
- Handle 404 when genome not found

**Registration:**
**File:** `app/main.py`
- Import and register `genome_router`

---

## 4. Fix Calculation Formulas

### 4.1 Profit Delta (%)

**File:** `app/services/results_aggregation_service.py`

**Current Implementation (incorrect):**
```python
profit_delta = result.profit_percent - base.profit_percent
```

**New Implementation:**
```python
if base.total_profit != 0:
    profit_delta = ((result.total_profit - base.total_profit) / abs(base.total_profit)) * 100
else:
    profit_delta = 0.0
```

**Formula:** `((genome_profit - base_profit) / |base_profit|) × 100`

- For base algorithm (G_000): `profit_delta = 0`
- When base profit is 0: `profit_delta = 0`

### 4.2 Win Rate (%)

**File:** `app/services/results_aggregation_service.py`

**Current Implementation (verify correctness):**
```python
win_rate = (trades_win / trade_count * 100) if trade_count > 0 else 0.0
```

**Definition:** Ratio of profitable closed positions to total trades
- `trades_win` = positions where `sell_price > buy_price`
- No changes needed if implementation matches this pattern

---

## Verification Checklist

| Task | Test Method |
|------|-------------|
| Parallelization | Set `ALGORITHM_WORKER_COUNT=4`, start worker, verify 4 processes with `ps aux` |
| Log optimization | Set `ALGORITHM_DEBUG=false`, run task, verify no signal logs; set `true`, verify signals appear |
| Sheets health | `curl /api/v1/sheets/health` - verify JSON with read/write status |
| Genome params | `curl /api/v1/genome/G_001/parameters` - verify genome configuration returned |
| Profit Delta | Base profit=1000, genome profit=1200 → delta should be 20% |
| Win Rate | 3 wins / 5 total trades → should be 60% |

---

## Files Summary

| Task | Files to Modify/Create |
|------|------------------------|
| Parallelization | `.env.example`, `app/config/queue_config.py`, `workers/start_*.py`, `Dockerfile` |
| Log Optimization | `.env.example`, `app/config/logging_config.py`, `app/workers/algorithm_worker.py` |
| Sheets Health API | **NEW:** `app/controllers/sheets_controller.py`, `app/services/sheets_service.py`, `app/main.py` |
| Genome Params API | **NEW:** `app/controllers/genome_controller.py`, `app/services/genome_service.py`, `app/main.py` |
| Fix Calculations | `app/services/results_aggregation_service.py`, `app/models/algorithm_models.py` |
