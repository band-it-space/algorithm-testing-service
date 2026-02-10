# Algorithm Worker Flow — Detailed Architecture & Execution Guide

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Architecture Diagram](#2-architecture-diagram)
3. [Infrastructure & Deployment](#3-infrastructure--deployment)
4. [Task Origination — How Work Enters the System](#4-task-origination--how-work-enters-the-system)
5. [Queue System — Redis & RQ](#5-queue-system--redis--rq)
6. [Worker Startup & Process Management](#6-worker-startup--process-management)
7. [ConcurrentWorker — Thread Pool Execution](#7-concurrentworker--thread-pool-execution)
8. [Algorithm Task Processing — `process_algorithm_task()`](#8-algorithm-task-processing--process_algorithm_task)
9. [Data Fetching & Caching Layer](#9-data-fetching--caching-layer)
10. [Signal Calculation Engine — `signals_for_the_period()`](#10-signal-calculation-engine--signals_for_the_period)
11. [Buy Signal Logic](#11-buy-signal-logic)
12. [Sell Signal Logic](#12-sell-signal-logic)
13. [Energy Indicators](#13-energy-indicators)
14. [CSV Output Formatting — `format_signals_csv_inplace()`](#14-csv-output-formatting--format_signals_csv_inplace)
15. [Result Processing Worker (Stage 2)](#15-result-processing-worker-stage-2)
16. [File Write Worker (Stage 3)](#16-file-write-worker-stage-3)
17. [Optimization Service & Genome System](#17-optimization-service--genome-system)
18. [Data Models](#18-data-models)
19. [Performance Optimizations](#19-performance-optimizations)
20. [Configuration Reference](#20-configuration-reference)
21. [Complete End-to-End Flow Summary](#21-complete-end-to-end-flow-summary)

---

## 1. System Overview

This project implements a **multi-stage, queue-based stock trading algorithm backtesting and optimization system** for Hong Kong Exchange (HKEX) stocks. The system evaluates buy/sell trading signals over historical data and compares results against a reference API.

The processing pipeline consists of **three sequential worker stages** connected by Redis queues:

| Stage | Worker | Queue Name | Purpose |
|-------|--------|------------|---------|
| 1 | **Algorithm Worker** | `algorithm_calculation` | Run buy/sell signal logic over historical OHLCV data |
| 2 | **Result Worker** | `result_processing` | Calculate financial metrics, compare with API, aggregate results |
| 3 | **File Write Worker** | `file_write` | Persist comparison results to CSV files |

Each stage is independent and communicates through Redis (RQ) job queues, enabling horizontal scaling.

---

## 2. Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        ENTRY POINTS                                      │
│                                                                          │
│   GET /algorithm/          POST /optimization/start                      │
│   (algorithm_controller)   (optimization_controller)                     │
│         │                         │                                      │
│         ▼                         ▼                                      │
│   Read screener.csv        OptimizationService.create_optimization()     │
│   Filter already done      GenomeService.generate_genomes()              │
│         │                         │                                      │
│         └──────────┬──────────────┘                                      │
│                    ▼                                                     │
│       QueueService.add_to_algorithm_queue()                              │
│       QueueService.add_batch_to_algorithm_queue()                        │
└────────────────────┬─────────────────────────────────────────────────────┘
                     │  Redis RQ enqueue
                     ▼
┌────────────────────────────────────────────────────────────────────────────┐
│  STAGE 1: algorithm_calculation queue                                      │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │  Algorithm Worker (start_algorithm_worker.py)                        │  │
│  │  ┌────────────────┐   ┌────────────────────────────────────────┐    │  │
│  │  │ ConcurrentWorker│──▶│ process_algorithm_task(task_data)      │    │  │
│  │  │ (ThreadPool)    │   │                                        │    │  │
│  │  └────────────────┘   │  1. init_db_pool()                     │    │  │
│  │                        │  2. warm_spy_cache()                   │    │  │
│  │                        │  3. get_data_and_save_to_csv()         │    │  │
│  │                        │  4. signals_for_the_period()           │    │  │
│  │                        │     ├── Fetch OHLCV data (code + SPY)  │    │  │
│  │                        │     ├── Build date index maps          │    │  │
│  │                        │     ├── For each trading day:          │    │  │
│  │                        │     │   ├── Calculate energy (E1-E5)   │    │  │
│  │                        │     │   ├── If FLAT: run buy signals   │    │  │
│  │                        │     │   └── If IN: run sell signals    │    │  │
│  │                        │     └── Append results to CSV          │    │  │
│  │                        │  5. format_signals_csv_inplace()       │    │  │
│  │                        │  6. Enqueue to result_processing queue │    │  │
│  │                        └────────────────────────────────────────┘    │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
└────────────────────┬───────────────────────────────────────────────────────┘
                     │  QueueService.add_to_result_processing_queue()
                     ▼
┌────────────────────────────────────────────────────────────────────────────┐
│  STAGE 2: result_processing queue                                          │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │  Result Worker (result_worker.py)                                    │  │
│  │  process_result_task()                                               │  │
│  │    1. Read algorithm signals CSV                                     │  │
│  │    2. save_financial_results() → general_results.csv                 │  │
│  │    3. save_genome_optimization_results() → optimization_results.csv  │  │
│  │       + "Automated Results.csv" + Redis store                        │  │
│  │    4. load_server_data() → fetch from reference API                  │  │
│  │    5. Compare algo signals vs API signals                            │  │
│  │    6. Calculate match %, deviations                                  │  │
│  │    7. Enqueue comparison to file_write queue                         │  │
│  │    8. OptimizationService.increment_completed_tasks()                │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
└────────────────────┬───────────────────────────────────────────────────────┘
                     │  QueueService.add_to_file_write_queue()
                     ▼
┌────────────────────────────────────────────────────────────────────────────┐
│  STAGE 3: file_write queue                                                 │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │  File Write Worker (file_write_worker.py)                            │  │
│  │  process_file_write_task()                                           │  │
│  │    1. Route by output_type:                                          │  │
│  │       - "comparison" → comparison_results.csv                        │  │
│  │       - default → Automated Results.csv                              │  │
│  │    2. file_service.add_data_to_csv()                                 │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────────┘
                     │
                     ▼
          ┌─────────────────────────┐
          │  Final Outputs:          │
          │  • data/general_results  │
          │  • data/Automated Results│
          │  • comparison_results    │
          │  • Google Sheets         │
          │  • Redis (per genome)    │
          └─────────────────────────┘
```

---

## 3. Infrastructure & Deployment

The system runs as a **Docker Compose** stack with 6 services:

| Service | Container Command | Description |
|---------|-------------------|-------------|
| `redis` | `redis-server` | Redis 7 Alpine — message broker & cache |
| `algorithm-service` | `uvicorn app.main:app` | FastAPI REST API (port 8000) |
| `algorithm-worker` | `python workers/start_algorithm_worker.py` | Stage 1 — signal calculation |
| `result-worker` | `python workers/start_result_worker.py` | Stage 2 — result aggregation |
| `file-write-worker` | `python workers/start_file_write_worker.py` | Stage 3 — file persistence |
| `rq-dashboard` | `python dashboard/start_dashboard.py` | RQ monitoring UI (port 9181) |

All workers share the same Docker image (`python:3.11-slim`) and mount common volumes:
- `./app` — Application code
- `./data` — CSV data files (read/write)
- `./logs` — Log output
- `./credentials` — Google Sheets service account key (read-only)

---

## 4. Task Origination — How Work Enters the System

Tasks can enter the algorithm pipeline through two entry points:

### 4.1 Manual Stock Testing (Single Genome)

**Endpoint:** `GET /algorithm/`  
**Controller:** `algorithm_controller.py`

Flow:
1. Reads stock codes from `data/screener.csv`
2. Loads already-processed stocks from `data/results.csv`
3. Filters out already-done stocks
4. For each remaining stock, calls `QueueService.add_to_algorithm_queue(code)` with default genome `G_000`
5. Each stock becomes one job in the `algorithm_calculation` queue

### 4.2 Optimization Run (Multiple Genomes)

**Endpoint:** `POST /optimization/start`  
**Service:** `OptimizationService.create_optimization()`

Flow:
1. Receives `stock_codes[]` and `parameter_ranges[]` (defining which parameters to vary and their min/max/step)
2. Calls `GenomeService.generate_genomes()` to produce all parameter combinations
3. Creates `total_tasks = total_genomes × len(stock_codes)` tasks
4. Each task is a unique `(stock_code, genome_id, parameters)` combination
5. All tasks are enqueued via `QueueService.add_batch_to_algorithm_queue()`
6. Optimization metadata is stored in Redis under `optimization:{id}`

### 4.3 Task Data Structure

Every task enqueued to the algorithm queue has this structure:

```python
{
    "task_id": "uuid4",            # Unique task identifier
    "stock": "3888",               # HKEX stock code
    "genome_id": "G_000",          # "G_000" = BASE, "G_001"+ = variants
    "parameters": { ... },         # AlgorithmParameters as dict
    "optimization_id": "opt_...",  # Optional, links to optimization run
    "created_at": "ISO timestamp"
}
```

---

## 5. Queue System — Redis & RQ

### 5.1 Queue Configuration

Defined in `app/config/queue_config.py`:

| Queue | Variable | Default Timeout |
|-------|----------|-----------------|
| `algorithm_calculation` | `ALGORITHM_WORKER_TIMEOUT` | 1000s |
| `result_processing` | `RESULT_WORKER_TIMEOUT` | 300s |
| `file_write` | `FILE_WRITE_WORKER_TIMEOUT` | 60s |

### 5.2 QueueService

`app/services/queue_service.py` provides static methods for queue operations:

- `add_to_algorithm_queue()` — Enqueue a single algorithm job
- `add_batch_to_algorithm_queue()` — Enqueue multiple jobs (for optimization)
- `add_to_result_processing_queue()` — Enqueue Stage 2 processing
- `add_to_file_write_queue()` — Enqueue Stage 3 file writes
- `get_queue_length()` — Monitor pending job count

Each method creates the appropriate task data dict and calls `queue.enqueue(handler_function, task_data)`.

---

## 6. Worker Startup & Process Management

### 6.1 Entry Point: `workers/start_algorithm_worker.py`

The startup script uses `multiprocessing` to spawn worker processes:

```python
def main():
    worker_count = get_worker_count("algorithm")       # ALGORITHM_WORKER_COUNT env var
    concurrent_tasks = get_concurrent_tasks("algorithm") # ALGORITHM_CONCURRENT_TASKS env var

    for i in range(worker_count):
        if concurrent_tasks > 1:
            p = Process(target=run_concurrent_worker, args=(i, concurrent_tasks))
        else:
            p = Process(target=run_standard_worker)  # Fallback: standard RQ Worker
        p.start()
```

- **`worker_count`** — Number of OS-level processes (default: 1)
- **`concurrent_tasks`** — Number of threads per process (default: 1)
- If `concurrent_tasks > 1`, uses `ConcurrentWorker`; otherwise, falls back to standard RQ `Worker`
- Handles `SIGINT`/`SIGTERM` for graceful shutdown

---

## 7. ConcurrentWorker — Thread Pool Execution

`app/workers/concurrent_worker.py` implements a custom worker that processes multiple RQ jobs simultaneously using `ThreadPoolExecutor`.

### 7.1 Architecture

```
ConcurrentWorker (per process)
├── ThreadPoolExecutor(max_workers=concurrent_tasks)
│   ├── Thread 1 → process_job(job_A) → asyncio.new_event_loop()
│   ├── Thread 2 → process_job(job_B) → asyncio.new_event_loop()
│   └── Thread N → process_job(job_N) → asyncio.new_event_loop()
└── Main loop: fetch_jobs() → submit to executor → collect results
```

### 7.2 Main Work Loop

```python
def work(self):
    with ThreadPoolExecutor(max_workers=self.concurrent_tasks) as executor:
        active_futures = {}
        while self.running:
            # 1. Calculate available slots
            slots_available = self.concurrent_tasks - len(active_futures)

            # 2. Fetch jobs from Redis (atomic lpop)
            if slots_available > 0:
                new_jobs = self.fetch_jobs(slots_available)
                for job in new_jobs:
                    future = executor.submit(self.process_job, job)
                    active_futures[future] = job

            # 3. Collect completed futures
            done_futures = [f for f in active_futures if f.done()]
            for future in done_futures:
                active_futures.pop(future)
                job_id, status, error = future.result()

            time.sleep(0.1)  # Prevent tight loop
```

### 7.3 Job Fetching

Jobs are fetched directly from Redis via `lpop` (not through RQ's standard dequeue) for atomicity:

```python
def fetch_jobs(self, count):
    jobs = []
    for _ in range(count):
        result = self.queue.connection.lpop(self.queue.key)
        if result:
            job = Job.fetch(job_id, connection=self.queue.connection)
            jobs.append(job)
    return jobs
```

### 7.4 Async Handling

Since `process_algorithm_task` is an `async` function, each thread creates its own event loop:

```python
def process_job(self, job):
    func = job.func
    if inspect.iscoroutinefunction(func):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(func(*args, **kwargs))
        loop.close()
    else:
        result = func(*args, **kwargs)
    job.set_status('finished')
```

---

## 8. Algorithm Task Processing — `process_algorithm_task()`

This is the core entry point for Stage 1 processing, defined in `app/workers/algorithm_worker.py`.

### 8.1 Function Signature

```python
@timed("algorithm_task_total")
async def process_algorithm_task(task_data: dict):
```

### 8.2 Step-by-Step Execution

| Step | Operation | Description |
|------|-----------|-------------|
| 1 | **Parse task data** | Extract `stock_code`, `genome_id`, `optimization_id`, `parameters` |
| 2 | **`AlgorithmParameters.from_dict()`** | Deserialize parameters into typed dataclass |
| 3 | **`init_db_pool()`** | Initialize MySQL connection pool (if not already done) |
| 4 | **`warm_spy_cache(END_DATE)`** | Pre-warm Redis cache with SPY (code 2800) data |
| 5 | **`get_data_and_save_to_csv()`** | Fetch stock data, write initial CSV row with FLAT position |
| 6 | **`signals_for_the_period()`** | **Core signal calculation** — iterate all trading days, compute buy/sell signals |
| 7 | **`format_signals_csv_inplace()`** | Transform raw signals into trade-pair format (Buy Signal → Stop Signal + Gain/Lose) |
| 8 | **Enqueue to Stage 2** | `QueueService.add_to_result_processing_queue()` |
| 9 | **Log profiling** | If `ALGORITHM_DEBUG=true`, log timing summary |

### 8.3 Date Range

The worker processes data between two environment-configured dates:

```python
START_DATE = os.getenv('OPTIMIZATION_START_DATE', '2025-01-01')
END_DATE   = os.getenv('OPTIMIZATION_END_DATE',   '2026-02-02')
```

---

## 9. Data Fetching & Caching Layer

### 9.1 Data Source

All stock OHLCV data comes from a single external API:

```
GET http://ete.stockfisher.com.hk/v1.1/debugHKEX/verifyData?TradeDay=&Code={code}&verifyType=price
Header: x-api-key: {API_KEY}
```

The response includes fields: `TradeDay`, `adj_open`, `adj_high`, `adj_low`, `adj_close`, `adj_volume`.

### 9.2 Data Processing (`get_db_data.py`)

Function `_fetch_stock_data_from_api()`:
1. Calls the API
2. Filters out dates after `END_DATE`
3. Filters out records with any zero-value OHLCV field
4. Converts to standardized dict format: `{date, time, open, high, low, close, volume}`
5. Sorts by date ascending
6. Returns list of dicts

### 9.3 Caching Layer (`DataCacheService`)

`app/services/data_cache_service.py` provides Redis-based caching:

- **Cache Key:** `stock_cache:{code}:{date_range}`
- **Serialization:** Python `pickle` for OHLCV lists
- **TTL:** Default 3600 seconds (1 hour)
- **SPY Warm:** `warm_spy_cache()` pre-fetches code `2800` data once per batch to avoid N redundant API calls

Flow in `get_stock_data_from_db()`:
```
Cache HIT  → Deserialize from Redis → Return
Cache MISS → Fetch from API → Store in Redis → Return
```

### 9.4 Initial CSV Setup (`get_data_and_save_to_csv()`)

Before signal calculation begins, this function:
1. Fetches raw stock data to determine the first available date
2. Writes an initial CSV row with:
   - `position_status = "F"` (FLAT — no position)
   - `next_open_action = "N"` (No action)
   - All energy indicators = 0

This establishes the starting state for the signal calculation loop.

---

## 10. Signal Calculation Engine — `signals_for_the_period()`

This is the **algorithmic heart** of the system. It iterates over every trading day in the date range and determines buy/sell actions.

### 10.1 Initialization Phase

```python
# 1. Fetch OHLCV data for both the target stock and SPY reference (code 2800)
spy_data_raw  = await get_stock_data_from_db("2800", trade_date)
code_data_raw = await get_stock_data_from_db(code, trade_date)

# 2. Convert to OHLCV dataclass objects
spy_data  = [OHLCV(bar["date"], bar["open"], bar["high"], bar["low"], bar["close"], bar["volume"]) ...]
code_data = [OHLCV(...) ...]

# 3. Build O(1) lookup indexes (optimization)
spy_date_index  = {bar.date: i for i, bar in enumerate(spy_data)}
code_date_index = {bar.date: i for i, bar in enumerate(code_data)}

# 4. Get latest signal (resume point) from existing CSV
latest_signal = await get_latest_signal(code, genome_id=genome_id)

# 5. Filter to only unprocessed dates (after latest_signal's tradeday)
filtered_code_data = [bar for bar in code_data if bar.date > latest_date]
```

### 10.2 Main Processing Loop — State Machine

The algorithm implements a two-state machine for each stock/genome combination:

```
         ┌──────────────────────────────────────────────┐
         │                                              │
         ▼                                              │
    ┌─────────┐    Buy signal = True    ┌───────────┐   │
    │  FLAT   │ ──── next day open ────▶│  IN POS   │   │
    │  (F)    │    action = "B"         │   (I)     │   │
    │         │◀─── next day open ──────│           │   │
    └─────────┘    Sell signal = True    └───────────┘   │
                   action = "S"                          │
                                                         │
```

**State `F` (FLAT — no position held):**
1. Run all buy conditions → `runAllBuyConditions()`
2. Evaluate with `isBuy()` — returns True if conditions are met
3. If buy: set `next_open_action = "B"`, transition to `I`
4. Record: entry price = current close, exit1 = calculated stop-loss

**State `I` (IN POSITION — holding stock):**
1. If `next_open_action == "B"`: fill entry at today's open price
2. Run all sell conditions → `runAllSellConditions()`
3. Evaluate with `isSell()` — returns True if any exit condition fires
4. If sell: set `next_open_action = "S"`, transition to `F`
5. Track: updated stop-loss level (trailing), entry date/price

### 10.3 Per-Day Data Slicing (Optimized)

For each trading day, the algorithm needs all historical data up to that day. Instead of re-filtering the entire array each time, it uses **index-based slicing**:

```python
# O(1) lookup via pre-built date index
code_end_idx = _find_end_index(code_date_index, code_dates_sorted, tradeday_str, len(code_data))
filtered_code = code_data[:code_end_idx + 1]  # Slice, not filter

# Fallback: binary search if date not in dataset
idx = bisect_right(sorted_dates, target_date)
```

### 10.4 Output

Each day produces a result dict:

```python
{
    "code": "3888",
    "genome_id": "G_001",
    "tradeday": "2025-03-15",
    "position_status": "F" or "I",
    "next_open_action": "B", "S", or "N",
    "E1": "UpTrend", "E2": "Neutral", ...,  # Energy indicators
    "exit1": 45.23,        # Stop-loss level
    "entry_price": 50.10,
    "close": 49.85,
    "entry_date": "2025-03-01",
    "exit_price": 0 or open_price_on_sell
}
```

Results are batched and appended to CSV via `append_to_signals_csv()`.

---

## 11. Buy Signal Logic

Defined in `app/workers/algo_func/buy_signals.py` (738 lines).

### 11.1 Buy Conditions

The system evaluates **9 buy conditions + a stop-loss calculation**:

| Condition | Name | Description |
|-----------|------|-------------|
| **B1** | Bollinger Band | Lookback, BB length/std, MA deviation, upper range |
| **B3** | BB Width + Linear Regression | BBW length, SMA of BBW, LR lookback |
| **B8** | Recent vs Past Low | Compares recent low (N days) vs past low (M days) |
| **B9** | Moving Average | MA length filter |
| **B10** | Low Window Proximity | Low window (250d) + proximity days (68d) |
| **B11** | ATR Threshold | ATR length, history, threshold |
| **B12** | Long MA Rise | Long MA (150d), rise percentage, deviation |
| **B13** | Stock vs SPY Comparison | XX/YY day comparison against SPY (2800) |
| **B18** | BB Width Squeeze | BBW length, history, ratio, Z-period |
| **stopLoss** | Initial Stop-Loss (`S1`) | ATR-based stop calculation for entry |

### 11.2 Buy Decision (`isBuy()`)

```python
def isBuy(signals):
    return bool(
        (B1 and B3 and B8 and B9 and B10 and B11 and B12 and B13)  # All primary
        or B18  # OR standalone squeeze signal
    )
```

**Logic:** ALL of B1-B13 must be True (conjunction), **OR** B18 alone is sufficient (standalone trigger).

### 11.3 Technical Indicators Used

- **Simple Moving Average (SMA)** — NumPy cumsum-based vectorized calculation
- **Bollinger Bands** — Pandas rolling mean/std
- **Linear Regression** — Slope calculation over lookback period
- **ATR (Average True Range)** — Wilder's smoothing
- **BB Width (BBW)** — (Upper - Lower) / Middle band

### 11.4 OHLCV Data Structure

```python
@dataclass
class OHLCV:
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float] = None
```

---

## 12. Sell Signal Logic

Defined in `app/workers/algo_func/sell_signals.py` (857 lines).

### 12.1 Sell Conditions

The system evaluates **15 sell conditions**:

| Condition | Description | Key Parameters |
|-----------|-------------|----------------|
| **S1** | Stop-loss hit | ATR multiplier, hard stop %, medium/high risk thresholds |
| **S4** | Max holding days + SMA ratio | Max days (50), SMA period (150), ratio threshold |
| **S5** | Trailing stop (push-up) | Initial days, step days, push-up ATR |
| **S6** | Duration near high | Min days, high window, days threshold |
| **S7** | Large body candle | ATR period, body multiplier |
| **S8** | ATR compression + bearish | ATR22 window, ATR100 threshold, bear count |
| **S9** | Energy threshold | Energy threshold value |
| **S10** | ATR ratio + drawdown | ATR ratio, drawdown percentage |
| **S11** | Fibonacci Level (38.2%) | XX days, fib level, YY days |
| **S12** | Fibonacci Level (23.6%) | XX days, fib level, YY days |
| **S13** | Long hold + lookback | Min days (238), lookback (80) |
| **S14** | Multi-horizon SPY comparison | Min days (300), horizons [35, 70, 105] |
| **S15** | Crash detection | Crash drop %, lookback days |
| **S16** | Gain-based + ATR increase | Gain %, effective days, ATR increase |
| **S17** | Wide range near bottom | Min days, wide range, near-bottom ratio |

### 12.2 Sell Decision (`isSell()`)

```python
def isSell(signals):
    return S1 or S4 or S5 or S6 or S7 or S8 or S9 or S10
           or S11 or S12 or S13 or S14 or S15 or S16 or S17
```

**Logic:** ANY single sell condition being True triggers a sell (disjunction).

### 12.3 Dynamic Stop-Loss

S5 implements a **trailing stop-loss** mechanism that tightens over holding time:
- Returns `(should_exit: bool, new_stop_loss: float)`
- The updated stop-loss is propagated through the `latest_signal` state

---

## 13. Energy Indicators

Defined in `app/workers/algo_func/get_code_energy.py` (449 lines).

### 13.1 Purpose

Energy indicators (E1–E5) are computed for each trading day as supplementary metadata. They measure the stock's momentum/trend state relative to SPY (code 2800).

### 13.2 Calculation

`calculate_energy_indicators_last_16_days()`:
- Takes the target date, filtered stock OHLCV, and SPY OHLCV
- Processes the last 16 trading days of data
- Uses RSI (vectorized), price action patterns, and relative performance
- Returns: `{"E1": "UpTrend", "E2": "Neutral", "E3": ..., "E4": ..., "E5": "..."}`

### 13.3 RSI Implementation

Uses Wilder's smoothing method with NumPy vectorization:
```python
calculate_rsi_vectorized(prices: np.ndarray, period: int = 10) -> np.ndarray
```

---

## 14. CSV Output Formatting — `format_signals_csv_inplace()`

After `signals_for_the_period()` writes daily raw signals, this function transforms them into a **trade-pair** format.

### 14.1 Input (Raw Signals CSV)

```
code, genome_id, tradeday, position_status, next_open_action, E1-E5, exit1, close, entry_price, entry_date, exit_price
3888, G_001, 2025-03-10, F, B, ..., 45.2, 50.1, 50.1, 0, 0
3888, G_001, 2025-03-11, I, N, ..., 45.2, 51.3, 50.1, 2025-03-11, 0
...
3888, G_001, 2025-04-15, I, S, ..., 48.0, 47.5, 50.1, 2025-03-11, 0
3888, G_001, 2025-04-16, F, N, ..., 0, 46.8, 0, 0, 47.5
```

### 14.2 Output (Trade-Pair Format)

```
Genome ID, Buy Signal, Stop Signal, Entry price, Exit price, Gain/Lose
G_001, 2025-03-11, 2025-04-16, 50.100, 47.500, -5.19
G_001, 2025-06-02, Open position, 55.300, Open position, 3.44
```

### 14.3 Logic

1. Find all rows where `next_open_action == "S"` (sell signals)
2. For each sell row: pair it with its entry date/price to form a closed trade
3. Calculate `Gain/Lose = ((exit_price - entry_price) / entry_price) × 100`
4. Handle open positions (last buy without corresponding sell)
5. Filter trades to only include those within the `START_DATE` to `END_DATE` range
6. Overwrite the original CSV with the formatted output

---

## 15. Result Processing Worker (Stage 2)

`app/workers/result_worker.py` — `process_result_task()`

### 15.1 Financial Results (`save_financial_results()`)

For each trade:
- Calculates `profit_usd = FIXED_DEPOSIT_AMOUNT ($10,000) × (gain_percent / 100)`
- Writes to `general_results.csv` with fields: symbol, genome_id, entryDay, entryPrice, exitDay, exitPrice, profit, Profit %, Invested
- Uses vectorized pandas operations for performance

### 15.2 Genome Optimization Results (`save_genome_optimization_results()`)

Calculates aggregate metrics per genome via `calculate_genome_metrics()`:

| Metric | Calculation |
|--------|-------------|
| Trade Count | Number of closed trades |
| Total Win ($) | Sum of profitable trades |
| Total Loss ($) | Sum of losing trades |
| Trades Win | Count of winners |
| Trades Loss | Count of losers |
| Avg Win ($) | Mean winning trade |
| Avg Loss ($) | Mean losing trade |
| Payoff Ratio | Avg Win / Avg Loss |
| Win Rate | Trades Win / Trade Count × 100 |

Results are written to:
- `optimization_results.csv`
- `Automated Results.csv`
- Redis hash: `optimization_results:{optimization_id}` (field: `{genome_id}:{stock_code}`)

### 15.3 API Comparison

The Result Worker also verifies algorithm output against a reference API:

1. Calls `load_server_data()` → fetches signal data from API (`verifyType=signal`)
2. Converts both API and CSV signals to `UnifiedTradeSignal` format
3. Compares buy/sell dates with tolerance (±2 trading days)
4. Calculates: exact matches, deviations, unmatched signals, match percentage
5. Enqueues comparison results to the file_write queue

### 15.4 Optimization Progress Tracking

After processing each task:
```python
OptimizationService.increment_completed_tasks(optimization_id)
```

When `completed_tasks >= total_tasks`, the optimization status is set to `COMPLETED` and results are written to Google Sheets (if `sheet_id` is configured).

---

## 16. File Write Worker (Stage 3)

`app/workers/file_write_worker.py` — `process_file_write_task()`

### 16.1 Routing

| `output_type` | Destination File |
|---------------|-----------------|
| `"comparison"` | `comparison_results.csv` |
| default | `Automated Results.csv` |

### 16.2 Implementation

Simply delegates to `FileService.add_data_to_csv()` which:
- Creates the file with headers if it doesn't exist
- Appends rows if the file already exists
- Uses buffered writing for efficiency

---

## 17. Optimization Service & Genome System

### 17.1 Genome Generation

`app/services/genome_service.py` generates parameter combinations:

1. **G_000 (BASE):** Always uses `AlgorithmParameters()` defaults
2. **G_001, G_002, ...:** Each has a unique combination of varied parameters

```python
# Example: If two parameters are varied:
# input_B1_upper_range: [0.5, 0.6, 0.7] (3 values)
# input_S1_atr_mult:    [3.5, 3.7, 3.9] (3 values)
# → 3 × 3 = 9 combinations + 1 BASE = 10 total genomes
```

### 17.2 Parameter Ranges

From `ParameterRange` model:

```python
@dataclass
class ParameterRange:
    name: str          # e.g., "input_B1_upper_range"
    base: float        # Default/base value
    min_val: float     # Minimum for optimization
    max_val: float     # Maximum for optimization
    step: float        # Step between values
    change: bool       # Whether this parameter is varied (True) or fixed (False)
```

### 17.3 Optimization Lifecycle

```
PENDING → QUEUED → RUNNING → COMPLETED
                           → FAILED
                           → CANCELLED
```

### 17.4 Delta Calculations

When all tasks complete, `_recalculate_deltas()` computes:
- **Profit Delta (%):** `((genome_profit - base_profit) / |base_profit|) × 100`
- **Win Rate Delta (%):** `genome_win_rate - base_win_rate` (percentage points)

These deltas are relative to G_000 (BASE) for each stock.

---

## 18. Data Models

### 18.1 AlgorithmParameters

A `@dataclass` with **52 configurable parameters** covering all buy (B1–B18) and sell (S1–S17) conditions:

**Buy Parameters:**
- `input_B1_*` — Bollinger Band (lookback, bb_len, bb_std, ma_dev, upper_range)
- `input_B3_*` — BBW + LR (bbw_len, sma_bbw, LR_lookback)
- `input_B8_*` — Recent/Past Low (recent_low, past_low)
- `input_B9_*` — MA (ma_len)
- `input_B10_*` — Low Window (low_window, prox_days)
- `input_B11_*` — ATR (atr_len, history, atr_threshold)
- `input_B12_*` — Long MA Rise (long_ma, rise_pct, deviation)
- `input_B13_*` — SPY Comparison (XX, YY)
- `input_B18_*` — BB Squeeze (bbw_len, history, bbw_ratio, Z)

**Sell Parameters:**
- `input_S1_*` — Stop-Loss (atr_mult, atr_period, hard_stop, medium_risk/stop, high_stop)
- `input_S4_*` — Max Days (max_days, sma_period, ratio_threshold, gain_threshold)
- `input_S5_*` — Trailing Stop (initial_days, step_days, push_up_atr, atr_period)
- `input_S6_*` through `input_S17_*` — Various exit conditions

### 18.2 GenomeResult

Calculated per `(genome_id, stock_code)` combination:
- Trade statistics (count, wins, losses, averages)
- Profit metrics
- Delta vs BASE (calculated post-hoc)

### 18.3 UnifiedTradeSignal

Used for API vs Algorithm comparison:
- `buy_signal`, `stop_signal` — Datetime or "Open position"
- `entry_price`, `exit_price` — Float or "Open position"
- `source` — "api" or "csv"

---

## 19. Performance Optimizations

The codebase includes several documented optimizations:

### 19.1 Data Access (Task 3.1 & 3.2)
- **Date-to-index mapping:** `_build_date_index()` creates `{date_str: int}` dict for O(1) lookups
- **Index-based slicing:** Instead of `[bar for bar in data if bar.date <= target]` (O(n) per day), uses `data[:end_idx + 1]` (O(1) slice)
- **Binary search fallback:** `bisect_right()` for O(log n) when date isn't in the dataset

### 19.2 API Call Reduction
- **Redis caching:** `DataCacheService` with 1-hour TTL
- **SPY warm cache:** `warm_spy_cache()` called once per batch — avoids N identical fetches for code 2800

### 19.3 Technical Indicator Calculations
- **NumPy vectorized SMA:** `np.cumsum`-based rolling mean (~10-50x faster)
- **NumPy vectorized ATR:** Wilder's smoothing with array operations
- **Pandas Bollinger Bands:** `pd.Series.rolling()` for mean/std
- **Vectorized RSI:** NumPy array operations instead of loop

### 19.4 Result Worker (Task 7.1)
- **Vectorized profit calculation:** `pd.to_numeric()` + NumPy `np.where` instead of `iterrows()`

### 19.5 CSV I/O
- **Buffered CSV writer:** Batches rows in memory (default: 1000) before flushing
- **Atomic writes:** Temp file + `os.replace()` for crash safety

### 19.6 Concurrency
- **Multi-process workers:** `multiprocessing.Process` for CPU isolation
- **Thread pool per process:** `ThreadPoolExecutor` for I/O-bound parallelism
- **Per-thread event loops:** Async functions run in isolated `asyncio` loops

---

## 20. Configuration Reference

### 20.1 Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPTIMIZATION_START_DATE` | `2025-01-01` | Start of backtesting window |
| `OPTIMIZATION_END_DATE` | `2026-02-02` | End of backtesting window |
| `ALGORITHM_WORKER_COUNT` | `1` | Number of worker processes |
| `ALGORITHM_CONCURRENT_TASKS` | `1` | Threads per worker process |
| `ALGORITHM_WORKER_TIMEOUT` | `1000` | Job timeout in seconds |
| `RESULT_WORKER_COUNT` | `2` | Result worker processes |
| `RESULT_CONCURRENT_TASKS` | `5` | Threads per result worker |
| `RESULT_WORKER_TIMEOUT` | `300` | Result job timeout |
| `FILE_WORKER_COUNT` | `1` | File write worker processes |
| `FILE_CONCURRENT_TASKS` | `3` | Threads per file worker |
| `FILE_WRITE_WORKER_TIMEOUT` | `60` | File write job timeout |
| `REDIS_HOST` | `localhost` | Redis server hostname |
| `REDIS_PORT` | `6379` | Redis server port |
| `API_KEY` | — | StockFisher API key |
| `ALGORITHM_DEBUG` | `false` | Enable verbose signal logging |
| `LOG_PROGRESS_INTERVAL` | — | Log progress every N days |
| `DATA_DIR` | `data` | Directory for CSV files |

### 20.2 Key File Paths

| File | Purpose |
|------|---------|
| `data/{stock_code}.csv` | Raw & formatted signal data per stock |
| `data/general_results.csv` | Per-trade financial results |
| `data/optimization_results.csv` | Genome metrics with optimization_id |
| `data/Automated Results.csv` | Final output (matches Output Results Sample format) |
| `data/comparison_results.csv` | API vs Algorithm comparison report |
| `data/screener.csv` | Input stock list |

---

## 21. Complete End-to-End Flow Summary

```
1. API Request (or Optimization trigger)
   │
2. Generate task(s): {stock_code, genome_id, parameters}
   │
3. Enqueue to Redis → algorithm_calculation queue
   │
4. Algorithm Worker picks up task
   │  ├── Initialize DB pool + SPY cache
   │  ├── Write initial FLAT signal to CSV
   │  ├── For each trading day (START_DATE → END_DATE):
   │  │   ├── Slice historical OHLCV data up to this day
   │  │   ├── Calculate energy indicators (E1–E5)
   │  │   ├── If FLAT: evaluate 9 buy conditions
   │  │   │   └── All B1-B13 = True → BUY (or B18 alone)
   │  │   └── If IN POSITION: evaluate 15 sell conditions
   │  │       └── Any S1-S17 = True → SELL
   │  ├── Batch-write all daily signals to stock CSV
   │  ├── Format CSV: raw signals → trade pairs + Gain/Lose
   │  └── Enqueue to result_processing queue
   │
5. Result Worker picks up task
   │  ├── Read formatted trades CSV
   │  ├── Calculate financial metrics (win/loss/profit)
   │  ├── If optimization: save genome metrics + Redis store
   │  ├── Fetch reference signals from API
   │  ├── Compare algorithm vs API (match %, deviations)
   │  ├── Enqueue comparison to file_write queue
   │  └── Increment optimization progress counter
   │
6. File Write Worker picks up task
   │  └── Write comparison data to comparison_results.csv
   │
7. When all optimization tasks complete:
   ├── Recalculate profit/win-rate deltas vs BASE (G_000)
   └── Write final results to Google Sheets (if configured)
```

---

*Document generated from codebase analysis. Last updated: 2026-02-09.*
