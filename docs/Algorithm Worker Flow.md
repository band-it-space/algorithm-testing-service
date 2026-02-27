# Algorithm Worker Flow

## Table of Contents

- [1. High-Level Architecture Overview](#1-high-level-architecture-overview)
- [2. System Entry Points](#2-system-entry-points)
- [3. Queue Infrastructure](#3-queue-infrastructure)
- [4. Algorithm Worker Process (`process_algorithm_task`)](#4-algorithm-worker-process-process_algorithm_task)
  - [4.1 Task Initialization](#41-task-initialization)
  - [4.2 Step 1 — `get_data_and_save_to_csv`](#42-step-1--get_data_and_save_to_csv)
  - [4.3 Step 2 — `signals_for_the_period`](#43-step-2--signals_for_the_period)
  - [4.4 Step 3 — `format_signals_csv_inplace`](#44-step-3--format_signals_csv_inplace)
  - [4.5 Step 4 — Enqueue to Result Processing](#45-step-4--enqueue-to-result-processing)
- [5. Data Fetching & Caching Layer](#5-data-fetching--caching-layer)
- [6. Signal Calculation Engine](#6-signal-calculation-engine)
  - [6.1 Buy Signal Conditions (B1–B18)](#61-buy-signal-conditions-b1b18)
  - [6.2 Sell Signal Conditions (S1–S17)](#62-sell-signal-conditions-s1s17)
  - [6.3 Energy Indicators (E1–E5)](#63-energy-indicators-e1e5)
- [7. Main Signal Loop — Day-by-Day Processing](#7-main-signal-loop--day-by-day-processing)
  - [7.1 State Machine: Position Status](#71-state-machine-position-status)
  - [7.2 Free State (F) — Buy Logic](#72-free-state-f--buy-logic)
  - [7.3 In-Position State (I) — Sell Logic](#73-in-position-state-i--sell-logic)
  - [7.4 Stop-Loss Tracking](#74-stop-loss-tracking)
- [8. CSV Output Format & Formatting](#8-csv-output-format--formatting)
- [9. Result Worker (Second Queue Stage)](#9-result-worker-second-queue-stage)
- [10. File Write Worker (Third Queue Stage)](#10-file-write-worker-third-queue-stage)
- [11. Worker Concurrency Model](#11-worker-concurrency-model)
- [12. Algorithm Parameters & Genome Optimization](#12-algorithm-parameters--genome-optimization)
- [13. Performance Optimizations](#13-performance-optimizations)
- [14. End-to-End Flow Diagram](#14-end-to-end-flow-diagram)
- [15. File & Directory Structure Reference](#15-file--directory-structure-reference)

---

## 1. High-Level Architecture Overview

The algorithm worker system is a **three-stage queue-based pipeline** built on **Redis + RQ (Redis Queue)** that processes stock trading signals for Hong Kong equities. The system:

1. **Algorithm Worker** (Queue 1) — Fetches OHLCV price data, iterates day-by-day through the entire date range, evaluates buy/sell conditions in memory, formats trade pairs, and stores them in Redis.
2. **Result Worker** (Queue 2) — Loads trade pairs from Redis, calculates financial metrics (profit, win rate, payoff ratio), handles genome completion & smart filtering, compares results against the reference API, and queues comparison data.
3. **File Write Worker** (Queue 3) — Persists comparison results to CSV files (thread-safe serialized writes).

Each stock+genome combination flows through all three stages sequentially, but **multiple stocks/genomes are processed concurrently** across workers.

```
┌──────────────┐     ┌────────────────────┐     ┌───────────────────┐     ┌─────────────────┐
│  API Request │────▶│ Algorithm Queue     │────▶│ Result Queue      │────▶│ File Write Queue│
│  /start-test │     │ (algorithm_worker)  │     │ (result_worker)   │     │ (file_write)    │
└──────────────┘     └────────────────────┘     └───────────────────┘     └─────────────────┘
                           │                          │                          │
                     Produces:                  Produces:                  Produces:
                     - Trade pairs (Redis)      - general_results.csv      - comparison_results.csv
                                                - optimization_results.csv
                                                - Automated Results.csv
                                                - Automated Results Per Genome.csv
```

---

## 2. System Entry Points

### 2.1 REST API Trigger

The primary entry point is the **`GET /api/v1/start-testing/`** endpoint defined in `app/controllers/algorithm_controller.py`:

1. Reads a list of stock codes from `data/screener.csv`.
2. Reads already-processed codes from `data/results.csv` to skip duplicates.
3. For each unprocessed stock, calls `QueueService.add_to_algorithm_queue(code)`.

### 2.2 Optimization Trigger

For genome optimization runs, the optimization controller/service creates tasks with:
- A specific `genome_id` (e.g., `G_001`, `G_002`, etc.)
- Custom `parameters` (an `AlgorithmParameters` dictionary with varied parameter values)
- An `optimization_id` to group results

### 2.3 Task Data Structure

Every task pushed to the algorithm queue has this shape:

```json
{
  "task_id": "uuid-v4",
  "stock": "3888",
  "genome_id": "G_000",
  "parameters": { ... AlgorithmParameters fields ... },
  "optimization_id": "opt-uuid or null",
  "created_at": "2026-02-10T12:00:00"
}
```

---

## 3. Queue Infrastructure

### Redis Queues

| Queue Name              | Worker File                   | Purpose                              | Timeout |
|-------------------------|-------------------------------|--------------------------------------|---------|
| `algorithm_calculation` | `start_algorithm_worker.py`   | Signal calculation                   | 1000s   |
| `result_processing`     | `start_result_worker.py`      | Financial metrics + API comparison   | 300s    |
| `file_write`            | `start_file_write_worker.py`  | Serialized CSV persistence           | 60s     |

### Queue Configuration

Configured via environment variables in `app/config/queue_config.py`:

| Variable                       | Default | Description                         |
|--------------------------------|---------|-------------------------------------|
| `REDIS_HOST`                   | localhost | Redis server host                 |
| `REDIS_PORT`                   | 6379    | Redis server port                   |
| `ALGORITHM_WORKER_COUNT`       | 1       | Number of worker processes          |
| `ALGORITHM_CONCURRENT_TASKS`   | 1       | Threads per worker process          |
| `ALGORITHM_WORKER_TIMEOUT`     | 1000    | Max seconds per task                |

---

## 4. Algorithm Worker Process (`process_algorithm_task`)

**File:** `app/workers/algorithm_worker.py`

This is the core function enqueued to the `algorithm_calculation` queue. It receives `task_data` and executes the following steps.

### 4.1 Smart Filtering Check

Before any computation, if smart filtering is enabled (`SMART_FILTERING_ENABLED=true`), the worker checks:

```python
if SmartFilteringService.is_genome_skipped(optimization_id, genome_id):
    # Skip entirely — increment progress and return early
```

This avoids wasting compute on genomes whose parameter values have already been eliminated by earlier results.

### 4.2 Task Initialization

```python
stock_code = task_data['stock']           # e.g. "3888"
genome_id = task_data.get('genome_id')    # e.g. "G_000"
optimization_id = task_data.get('optimization_id')
params = AlgorithmParameters.from_dict(task_data.get('parameters', {}))
```

Key initialization actions:
1. **DB Pool Init** — `init_db_pool()` creates a global `aiomysql` connection pool (max 20 connections) to the MySQL database (used as fallback; primary fetch is via HTTP API).
2. **SPY Cache Warm** — `warm_spy_cache(END_DATE)` pre-fetches reference index data (code `2800`) into Redis cache so all subsequent SPY lookups are instant.

### 4.3 Step 1 — `compute_seed_row`

**Purpose:** Creates the initial position state **in memory** (no file I/O).

**Flow:**
1. Fetches full historical OHLCV data for the stock via `get_stock_data_from_db(code, END_DATE)`.
2. Determines `effective_date` — the later of `START_DATE` (env: `OPTIMIZATION_START_DATE`, default `2016-01-01`) or the first available data date.
3. Creates a seed row in memory:

```
code | genome_id | tradeday       | position_status | next_open_action | E1-E5 | exit1 | close | entry_price | entry_date | exit_price
3888 | G_000     | effective_date | F               | N                | 0     | 0     | 0     | 0           | 0          | 0
```

4. Returns the seed row as a dictionary (no file writes at this stage).

The seed row establishes:
- **`position_status = "F"`** (Free — no open position)
- **`next_open_action = "N"`** (No action pending)

### 4.4 Step 2 — `signals_for_the_period`

**Purpose:** The main computation engine. Iterates through every trading day from `START_DATE` to `END_DATE`, evaluating buy/sell conditions and building signal records.

This is the most computationally intensive step. See [Section 7](#7-main-signal-loop--day-by-day-processing) for detailed logic.

**High-level flow:**
1. Fetch OHLCV data for both the target stock and SPY (reference index `2800`).
2. Convert raw dictionaries to `OHLCV` dataclass objects.
3. Build date-to-index mappings for O(1) lookups.
4. **Precompute all technical indicators** via `PrecomputedIndicators.compute_all()` — RSI, SMA, ATR, Bollinger Bands, etc. are calculated once upfront as numpy arrays.
5. Use seed row from Step 1 as starting state.
6. Filter data to only dates after the seed row's `tradeday`.
7. Loop day-by-day:
   - Use precomputed index for O(1) indicator lookups.
   - Calculate energy indicators (E1–E5).
   - If **Free (F)**: `run_all_buy_conditions_fast()` with precomputed arrays → if buy, transition to **In-Position (I)**.
   - If **In-Position (I)**: `run_all_sell_conditions_fast()` with precomputed arrays → if sell, transition to **Free (F)**.
   - Append result row to in-memory batch.
8. Return all accumulated rows as `list[dict]` (no file I/O).

### 4.5 Step 3 — `format_signals_in_memory`

**Purpose:** Transforms the raw day-by-day signal list into a **trade-summary format** showing completed trades with entry/exit prices and gain/loss percentages. All processing is in memory.

**Flow:**
1. Takes the in-memory signal rows from Step 2.
2. Finds all rows where `next_open_action == "S"` (sell signal).
3. For each sell-signal row:
   - Extract `entry_price`, `entry_date` from the row.
   - Extract `exit_price` from the **next** row (the day the sell actually executes at market open).
   - Calculate `Gain/Lose = ((exit_price - entry_price) / entry_price) * 100`.
4. Detects any **open position** (a buy signal after the last sell with no subsequent sell).
5. Filters trades to only those within the `START_DATE` to `END_DATE` range.
6. Returns formatted trade pairs as `list[dict]`:

```
Genome ID | Buy Signal | Stop Signal   | Entry price | Exit price | Gain/Lose
G_000     | 2020-03-25 | 2020-06-15    | 12.500      | 14.200     | 13.60
G_000     | 2021-01-10 | Open position | 18.300      | Open pos   | 5.20
```

### 4.6 Step 4 — Store in Redis & Enqueue to Result Processing

After formatting, the trade pairs are stored in Redis and the task is pushed to the **result processing queue**:

```python
# Store trade pairs in Redis (TTL 1 hour)
redis_key = f"trade_pairs:{optimization_id}:{stock_code}:{genome_id}"
_store_trade_pairs_in_redis(redis_key, trade_pairs)

# Enqueue to Stage 2
QueueService.add_to_result_processing_queue(
    stock_code,
    genome_id=genome_id,
    parameters=params.to_dict(),
    optimization_id=optimization_id,
    results={}
)
```

Trade pairs are passed via **Redis keys** (not queue payload or temp files), keeping queue messages lightweight.

---

## 5. Data Fetching & Caching Layer

**File:** `app/workers/algo_func/get_db_data.py`

### Data Source

All stock price data is fetched from **StockFisher API**:
```
http://ete.stockfisher.com.hk/v1.1/debugHKEX/verifyData?TradeDay=&Code={code}&verifyType=price
```

Authentication is via the `x-api-key` header using the `API_KEY` environment variable.

### API Response Processing

The raw API response is processed into standardized records:
- Uses **adjusted** prices: `adj_open`, `adj_high`, `adj_low`, `adj_close`, `adj_volume`
- Filters out records with zero/null values
- Filters out records after `END_DATE`
- Sorts by date ascending

### Caching Strategy (Redis)

**File:** `app/services/data_cache_service.py`

The `DataCacheService` provides a Redis-based caching layer:

| Feature | Detail |
|---------|--------|
| Serialization | Python `pickle` for speed |
| Default TTL | 3600 seconds (1 hour) |
| Key format | `stock_cache:{code}:full` |
| SPY pre-warm | `warm_spy_cache()` fetches `2800` data once at batch start |

**Request flow:**
```
get_stock_data_from_db(code)
  ├── Redis cache HIT → return deserialized OHLCV list
  └── Redis cache MISS
       ├── Fetch from StockFisher API
       ├── Store in Redis cache
       └── Return data
```

---

## 6. Signal Calculation Engine

### 6.1 Buy Signal Conditions (B1–B18)

**File:** `app/workers/algo_func/buy_signals.py`

All buy conditions are evaluated via `runAllBuyConditions()` which returns a dictionary:

```python
{
    'B1': bool, 'B3': bool, 'B8': bool, 'B9': bool,
    'B10': bool, 'B11': bool, 'B12': bool, 'B13': bool,
    'B18': bool, 'stopLoss': float
}
```

**Buy decision formula (`isBuy`):**
```
BUY = (B1 AND B3 AND B8 AND B9 AND B10 AND B11 AND B12 AND B13) OR B18
```

There are two independent buy paths:
1. **Primary path**: All of B1, B3, B8, B9, B10, B11, B12, B13 must be True simultaneously.
2. **Alternative path (B18)**: A standalone Minervini-style trend template that can trigger a buy on its own.

#### Individual Condition Descriptions

| Condition | Name | Logic Summary | Key Parameters |
|-----------|------|---------------|----------------|
| **B1** | New High + Bollinger | New 20-day high OR price above upper Bollinger Band (51-period, 1.9 std), AND close in upper `upper_range` of day's range | `lookback=20`, `bb_len=51`, `bb_std=1.9`, `ma_dev=0.25`, `upper_range=0.65` |
| **B3** | Volatility Compression | Slope of SMA(BBW) is negative (volatility contracting). Uses linear regression on the SMA of Bollinger Band Width | `bbw_len=21`, `sma_bbw=72`, `LR_lookback=58` |
| **B8** | Higher Low | Recent low (46 days) is higher than the past low (270 days) — confirming uptrend | `recent_low=46`, `past_low=270` |
| **B9** | Favorable Structure | NOT (close < midpoint AND high came before low in the 50-day window). Rejects downtrend patterns | `ma_len=50` |
| **B10** | Not Near 250-Day Low | The 250-day low must NOT be in the most recent 68 days — avoids falling knives | `low_window=250`, `prox_days=68` |
| **B11** | ATR Filter | Current ATR(22) must NOT exceed `threshold × max(ATR over past 126 days)` — avoids high-volatility entries | `atr_len=22`, `history=126`, `threshold=0.87` |
| **B12** | SMA Overextension | NOT (SMA(150) grew > 16% in 50 days AND price > 20% above SMA) — avoids parabolic runs | `long_ma=150`, `rise_pct=0.16`, `deviation=0.2` |
| **B13** | Relative Strength | Stock outperforms SPY over at least one of two horizons (19-day or 60-day) | `XX=19`, `YY=60` |
| **B18** | Minervini Trend Template | 8-condition check: price above SMA50/150/200, SMAs in proper order, SMA200 trending up, price ≥30% above 250-day low, price ≥75% of 250-day high, AND Bollinger Band Width compression breakout | Multiple sub-parameters |

#### Stop-Loss Calculation (`calcS1Stop`)

Calculated at buy-signal time and tracked through the position's lifetime:

```
baseStop = close - (atr_mult × ATR(22))
riskFraction = (close - baseStop) / close

If riskFraction > 0.30 (hard_stop):    stop = close × (1 - 0.1425)    → 14.25% max risk
If riskFraction > 0.20 (medium_risk):   stop = close × (1 - 0.095)     → 9.5% risk
Otherwise:                              stop = baseStop                 → dynamic ATR-based
```

### 6.2 Sell Signal Conditions (S1–S17)

**File:** `app/workers/algo_func/sell_signals.py`

All sell conditions are evaluated via `runAllSellConditions()`:

```python
{
    "conditions": { "S1": bool, "S4": bool, ..., "S17": bool },
    "stop_loss": float  # updated stop-loss from S5's trailing mechanism
}
```

**Sell decision formula (`isSell`):**
```
SELL = S1 OR S4 OR S5 OR S6 OR S7 OR S8 OR S9 OR S10 OR S11 OR S12 OR S13 OR S14 OR S15 OR S16 OR S17
```

**Any single sell condition triggers an exit.**

#### Individual Condition Descriptions

| Condition | Name | Logic Summary | Key Parameters |
|-----------|------|---------------|----------------|
| **S1** | Stop-Loss Hit | Current close ≤ stop-loss price | Uses `stop_loss` from entry |
| **S4** | Underperformance | After 50 days: if price was below SMA(150) >50% of trading days AND gain < 5% | `max_days=50`, `sma_period=150`, `ratio=0.5`, `gain=5.0` |
| **S5** | Trailing Stop | At day 45: set stop to `buy_price + 0.62 × ATR(20)`. Every 25 days after: push stop up by `0.62 × ATR(20)`. Exit if close < stop | `initial_days=45`, `step_days=25`, `push_up_atr=0.62` |
| **S6** | No New High | After 50+ days in position: if no new 90-day high in the last 76 days → exit | `min_days=50`, `high_window=90`, `days_threshold=76` |
| **S7** | Crash Candles | Two consecutive bearish candles with body > `2.0 × ATR(22)` | `atr_period=22`, `body_mult=2.0` |
| **S8** | Volatility Regime | ATR(100) > `0.74 × max(ATR(22) over 126 days)` AND ≥3 of last 5 bars have body > `2.4 × ATR(100)` | `atr22_window=126`, `threshold=0.74`, `body_mult=2.4`, `bear_count=3` |
| **S9** | Energy Score Low | 16-day energy score (E1–E5 sum / 16) < `0.22` threshold | `energy_thresh=0.22` |
| **S10** | Volatility + Drawdown | ATR(10) > `2.6 × ATR(100)` AND drawdown from 90-day high > 5% | `atr_ratio=2.6`, `drawdown=0.05` |
| **S11** | Fibonacci Exit (Long) | After 300+ days: price below 38.2% Fibonacci level for 2 consecutive days | `xx_days=300`, `fib_level=0.382`, `yy_days=2` |
| **S12** | Fibonacci Exit (Short) | After 240+ days: price below 23.6% Fibonacci level for 22 consecutive days | `xx_days=240`, `fib_level=0.236`, `yy_days=22` |
| **S13** | New Low | After 238+ days: close < min(close over last 80 days) | `min_days=238`, `lookback=80` |
| **S14** | Relative Underperformance | After 300+ days: stock underperforms HSI over ALL of [35, 70, 105]-day horizons | `min_days=300`, `horizons=[35,70,105]` |
| **S15** | Crash Detection | >25% drop over last 4 days | `crash_drop=0.25`, `lookback=4` |
| **S16** | Volatility Spike + Drop | >15% drop in 10 days AND ATR(22) increased >50% in 12 days | `xx=15.0`, `yy=10`, `atr_inc=50.0`, `atr_day=12` |
| **S17** | Wide Range Bottom | After 150+ days: 150-day range > 1.6× wide AND close near bottom (< 1.3× low) | `min_days=150`, `wide_range=1.6`, `near_bottom=1.3` |

### 6.3 Energy Indicators (E1–E5)

**File:** `app/workers/algo_func/get_code_energy.py`

Calculated for the last 16 trading days. Each indicator is binary (`"1"` or `"0"`):

| Indicator | Logic |
|-----------|-------|
| **E1** | New 20-day high AND close > Low + 0.65 × (High - Low) |
| **E2** | StochRSI(10,10) > 0.5 |
| **E3** | 66-day slope > 0 (price trending up) |
| **E4** | 33-day stock performance > 33-day SPY performance |
| **E5** | Close in top half of 5-day range AND close > 5-day-ago close AND < 7% drawdown from 66-day high |

**Energy Score** = Sum of all E1–E5 values across 16 days / 16

This score is used by sell condition **S9** (exit if score < 0.22) and is stored in the raw CSV for diagnostics.

---

## 7. Main Signal Loop — Day-by-Day Processing

### 7.1 State Machine: Position Status

The algorithm operates as a **two-state finite state machine**:

```
         ┌──── isBuy() == True ────┐
         │                         ▼
    ┌─────────┐              ┌──────────┐
    │  FREE   │              │ IN-POS   │
    │  (F)    │◀─────────────│  (I)     │
    └─────────┘              └──────────┘
         ▲     isSell() == True    │
         └─────────────────────────┘
```

- **F (Free)**: No open position. Evaluating buy conditions each day.
- **I (In-Position)**: Holding a position. Evaluating sell conditions each day.

### 7.2 Free State (F) — Buy Logic

When `position_status == "F"`:

1. Run `runAllBuyConditions(filtered_code, tradeday_str, filtered_spy, params)`.
2. Check `isBuy(buySignals)`.
3. If **previous day's** `next_open_action == "S"`:
   - Record `exit_price = bar.open` (the sell executes at market open).
4. Write result row with:
   - `next_open_action = "B"` if buy signal, else `"N"`
   - `exit1 = buySignals['stopLoss']` (initial stop-loss)
   - `entry_price = last close`
5. Update `latest_signal`:
   - `position_status = "I"` if buy, else stays `"F"`

### 7.3 In-Position State (I) — Sell Logic

When `position_status == "I"`:

1. If **previous day's** `next_open_action == "B"`:
   - Set `entry_date = today`, `entry_price = bar.open` (the buy executes at market open).
2. Run `runAllSellConditions(filtered_code, filtered_spy, entry_date, entry_price, exit1, tradeday_str, params)`.
3. Check `isSell(sellSignals['conditions'])`.
4. Update stop-loss: `new_stop_loss = sellSignals['stop_loss']` (S5 may have adjusted it).
5. Write result row with:
   - `next_open_action = "S"` if sell signal, else `"N"`
   - `exit1 = new_stop_loss`
6. Update `latest_signal`:
   - `position_status = "F"` if sell, else stays `"I"`

### 7.4 Stop-Loss Tracking

The stop-loss (`exit1`) is:
1. **Set at entry** by `calcS1Stop()` — ATR-based with risk tiers.
2. **Updated during position** by `S5` trailing stop mechanism:
   - At day 45: pushed up by `push_up_atr × ATR(20)` from entry price.
   - Every 25 days thereafter: pushed up from previous stop level.
3. **Checked each day** by `S1` — simple `close ≤ stop_loss` check.

**Important:** The stop-loss only ratchets upward (via S5). It never moves down once set.

---

## 8. CSV Output Format & Formatting

### Raw Signal CSV (intermediate)

Written during `signals_for_the_period()`:

| Column | Description |
|--------|-------------|
| `code` | Stock code (e.g., `3888`) |
| `genome_id` | Genome identifier |
| `tradeday` | Trading date (YYYY-MM-DD) |
| `position_status` | `F` (free) or `I` (in-position) |
| `next_open_action` | `B` (buy tomorrow), `S` (sell tomorrow), `N` (none) |
| `E1`–`E5` | Energy indicators (binary) |
| `exit1` | Current stop-loss level |
| `close` | Close price |
| `entry_price` | Position entry price |
| `entry_date` | Position entry date |
| `exit_price` | Exit price (filled on sell execution day) |

### Formatted Trade CSV (final output)

Written by `format_signals_csv_inplace()`, **overwriting** the raw CSV:

| Column | Description |
|--------|-------------|
| `Genome ID` | Genome identifier |
| `Buy Signal` | Entry date (YYYY-MM-DD) |
| `Stop Signal` | Exit date or `"Open position"` |
| `Entry price` | Buy execution price (3 decimal places) |
| `Exit price` | Sell execution price or `"Open position"` |
| `Gain/Lose` | Percentage return: `((exit - entry) / entry) × 100` |

---

## 9. Result Worker (Second Queue Stage)

**File:** `app/workers/result_worker.py`

Triggered by the algorithm worker via `QueueService.add_to_result_processing_queue()`.

### Processing Steps

1. **Load Trade Pairs from Redis** — Reads and deletes `trade_pairs:{optimization_id}:{stock_code}:{genome_id}` from Redis.
2. **Save Financial Results** — Writes to `general_results.csv` with per-trade USD profit calculations (vectorized pandas, assuming $10,000 fixed investment per trade).
3. **Genome Optimization Results** — If part of optimization, calculates aggregated metrics via `calculate_genome_metrics()`:
   - Trade count, win/loss counts
   - Total win/loss amounts, average win/loss
   - Payoff ratio (avg win / avg loss)
   - Win rate percentage, total profit and profit percentage
   - Writes per-stock results to `optimization_results.csv` and `Automated Results Per Genome.csv`
   - Stores per-stock result in Redis via `OptimizationService.store_genome_result()`
4. **Genome Completion Check** — When all stocks for a genome are processed:
   - Computes **averaged metrics** across all stocks
   - Calculates **deltas vs BASE (G_000)** for profit and win rate
   - Writes averaged row to `Automated Results.csv` and Google Sheets
   - **Smart filtering trigger**: calls `SmartFilteringService.record_genome_result()` and `check_and_eliminate()` to potentially eliminate underperforming parameter values from future genomes
5. **API Comparison** — Fetches reference signals from StockFisher API (`verifyType=signal`) and compares:
   - **Exact matches**: buy/sell dates match perfectly.
   - **Deviations**: within ±2 trading day tolerance.
   - **Unmatched**: signals present in API but not in algo (or vice versa).
   - Calculates `match_percent` for accuracy tracking.
6. **Queue File Write** — Pushes comparison results to the file write queue.
7. **Update Progress** — `OptimizationService.increment_completed_tasks()` updates optimization tracking.

---

## 10. File Write Worker (Third Queue Stage)

**File:** `app/workers/file_write_worker.py`

A serialized writer that safely persists comparison results to `comparison_results.csv`. Runs with short timeout (60s) since it only does file I/O.

---

## 11. Worker Concurrency Model

**File:** `workers/start_algorithm_worker.py` + `app/workers/concurrent_worker.py`

### Process Model

```
main()
  ├── Worker Process 0 ─── ThreadPoolExecutor(concurrent_tasks threads)
  │     ├── Thread 0: process_algorithm_task(stock_A, G_000)
  │     ├── Thread 1: process_algorithm_task(stock_B, G_001)
  │     └── Thread 2: process_algorithm_task(stock_C, G_002)
  ├── Worker Process 1 ─── ThreadPoolExecutor(concurrent_tasks threads)
  │     └── ...
  └── ...
```

- `ALGORITHM_WORKER_COUNT` processes are spawned via `multiprocessing.Process`.
- Each process runs a `ConcurrentWorker` with `ALGORITHM_CONCURRENT_TASKS` threads.
- Jobs are fetched atomically from Redis via `lpop`.
- Each thread runs its own `asyncio` event loop (since the worker function is `async`).

### Concurrency Safety

- **File isolation**: Each genome run uses its own CSV file (`{stock}_{genome_id}.csv`) to avoid write conflicts.
- **Redis atomic ops**: Queue operations use Redis `lpop` for atomic job claiming.
- **Thread-safe profiler**: `PerformanceProfiler` uses threading locks.

---

## 12. Algorithm Parameters & Genome Optimization

**File:** `app/models/algorithm_models.py`

### `AlgorithmParameters` Dataclass

Contains ~60+ configurable parameters controlling all buy/sell conditions. Default values represent the **base genome (G_000)**.

### Optimization Flow

1. A `ParameterRange` defines min/max/step for each variable parameter.
2. The optimization service generates genome combinations (e.g., G_001, G_002, ...).
3. Each genome gets a unique `AlgorithmParameters` instance with varied values.
4. All genomes for a stock are queued as separate algorithm tasks.
5. Results are aggregated in `optimization_results.csv` with the genome's metrics and parameter values.
6. The **6 key variable parameters** tracked in output:
   - `input_B1_upper_range` (B1 close-in-range threshold)
   - `input_B3_LR_lookback` (B3 linear regression window)
   - `input_B11_atr_threshold` (B11 volatility filter)
   - `input_B18_bbw_ratio` (B18 BBW compression ratio)
   - `input_S1_atr_mult` (S1 stop-loss ATR multiplier)
   - `input_S5_push_up_atr` (S5 trailing stop ATR push)

---

## 13. Performance Optimizations

### Computation Optimizations

| Optimization | Location | Technique |
|-------------|----------|----------|
| **Precomputed indicators** | `PrecomputedIndicators.compute_all()` | All technical indicators (RSI, SMA, ATR, Bollinger Bands, slopes) computed once upfront as numpy arrays; signal checks are O(1) array lookups |
| **Fast signal functions** | `run_all_buy_conditions_fast()`, `run_all_sell_conditions_fast()` | Use precomputed arrays instead of recalculating per day |
| **In-memory processing** | `compute_seed_row()`, `format_signals_in_memory()` | No file I/O during signal generation; all intermediate data stays in memory |
| **Redis trade-pair passing** | `_store_trade_pairs_in_redis()` | Trade pairs passed between Stage 1→Stage 2 via Redis keys (TTL 1h), not temp files or queue payload |
| **Smart filtering** | `SmartFilteringService` | Eliminates underperforming parameter combinations early, skipping entire genome computations |

### Data Access Optimizations

| Optimization | Location | Technique |
|-------------|----------|-----------|
| **Date index mapping** | `_build_date_index()` | O(1) hash map lookup instead of O(n) linear scan |
| **Binary search fallback** | `_find_end_index()` | `bisect_right` for dates not in dataset |
| **Index-based slicing** | Main loop | `data[:end_idx + 1]` instead of list comprehension filtering |
| **Redis data cache** | `DataCacheService` | Eliminates redundant API calls for same stock/SPY across genomes |
| **SPY cache pre-warm** | `warm_spy_cache()` | Single fetch for reference data shared by all tasks |

### I/O Optimizations

| Optimization | Location | Technique |
|-------------|----------|-----------|
| **Batch CSV writes** | `FileService.add_data_to_csv()` | Accumulates rows and writes in batches |
| **Buffered CSV writer** | `BufferedCSVWriter` | Flushes every 1000 rows instead of per-row |
| **Atomic writes** | `write_csv_atomic()` | Write to temp file, then rename to prevent corruption |
| **Vectorized pandas** | `save_financial_results()` | Vectorized profit calculation instead of `iterrows()` |

### Profiling Infrastructure

**File:** `app/utils/performance_profiler.py`

- `@timed("label")` decorator measures function execution time.
- `TimingContext("label")` context manager for block-level timing.
- Thread-safe singleton `PerformanceProfiler` collects metrics.
- Controlled by `ALGORITHM_DEBUG` environment variable.

---

## 14. End-to-End Flow Diagram

```
User/Scheduler
     │
     ▼
GET /algorithm/ ─────────────────────────────────────────────────┐
     │                                                           │
     ▼                                                           │
Read screener.csv → Filter processed → For each stock:          │
     │                                                           │
     ▼                                                           │
QueueService.add_to_algorithm_queue(stock, genome_id, params)    │
     │                                                           │
     ▼                                                           │
┌─── Redis Queue: algorithm_calculation ───┐                     │
│                                          │                     │
│  ConcurrentWorker picks up job           │                     │
│     │                                    │                     │
│     ▼                                    │                     │
│  process_algorithm_task(task_data)        │                     │
│     │                                    │                     │
│     ├─ 1. init_db_pool()                 │                     │
│     ├─ 2. warm_spy_cache()               │                     │
│     ├─ 3. get_data_and_save_to_csv()     │ ← Creates seed CSV  │
│     │     └─ get_stock_data_from_db()    │ ← API/Cache fetch   │
│     │                                    │                     │
│     ├─ 4. signals_for_the_period()       │ ← MAIN COMPUTATION  │
│     │     ├─ Fetch stock + SPY OHLCV     │                     │
│     │     ├─ Build date indexes          │                     │
│     │     ├─ For EACH trading day:       │                     │
│     │     │   ├─ Slice data to date      │                     │
│     │     │   ├─ Calc E1-E5 energy       │                     │
│     │     │   ├─ If FREE:                │                     │
│     │     │   │   ├─ runAllBuyConditions  │                     │
│     │     │   │   ├─ isBuy? → B/N        │                     │
│     │     │   │   └─ calcS1Stop          │                     │
│     │     │   └─ If IN-POSITION:         │                     │
│     │     │       ├─ runAllSellConditions │                     │
│     │     │       ├─ isSell? → S/N       │                     │
│     │     │       └─ Update stop-loss    │                     │
│     │     └─ Batch write results to CSV  │                     │
│     │                                    │                     │
│     ├─ 5. format_signals_csv_inplace()   │ ← Overwrite CSV     │
│     │     └─ Convert signals → trades    │   with trade summary│
│     │                                    │                     │
│     └─ 6. add_to_result_processing_queue │ ← Push to Queue 2  │
│                                          │                     │
└──────────────────────────────────────────┘                     │
     │                                                           │
     ▼                                                           │
┌─── Redis Queue: result_processing ───────┐                     │
│                                          │                     │
│  process_result_task(processing_data)    │                     │
│     │                                    │                     │
│     ├─ Read formatted CSV                │                     │
│     ├─ save_financial_results()          │ → general_results   │
│     ├─ save_genome_optimization_results()│ → optimization_res  │
│     │   └─ calculate_genome_metrics()    │ → Automated Results │
│     ├─ load_server_data() ← API signals  │                     │
│     ├─ Compare algo vs API signals       │                     │
│     ├─ Calculate match_percent           │                     │
│     ├─ Cleanup temp genome CSV           │                     │
│     └─ add_to_file_write_queue()         │ ← Push to Queue 3  │
│                                          │                     │
└──────────────────────────────────────────┘                     │
     │                                                           │
     ▼                                                           │
┌─── Redis Queue: file_write ──────────────┐                     │
│                                          │                     │
│  process_file_write_task(task_data)      │                     │
│     └─ Write comparison_results.csv      │                     │
│                                          │                     │
└──────────────────────────────────────────┘                     │
                                                                 │
                                            ◀────────────────────┘
```

---

## 15. File & Directory Structure Reference

```
app/
├── workers/
│   ├── algorithm_worker.py          # Main algorithm worker (Queue 1)
│   ├── result_worker.py             # Result processing worker (Queue 2)
│   ├── file_write_worker.py         # File write worker (Queue 3)
│   ├── concurrent_worker.py         # Thread-pool based concurrent job runner
│   └── algo_func/
│       ├── buy_signals.py           # Buy conditions B1-B18 + isBuy + stopLoss
│       ├── sell_signals.py          # Sell conditions S1-S17 + isSell
│       ├── get_code_energy.py       # Energy indicators E1-E5
│       ├── get_db_data.py           # Data fetching (API + cache)
│       ├── precomputed_indicators.py # Pre-computed indicator arrays for O(1) lookups
│       └── types.py                 # OHLCV dataclass and data types
│
├── models/
│   └── algorithm_models.py          # AlgorithmParameters, ParameterRange, GenomeResult
│
├── services/
│   ├── queue_service.py             # Redis queue management
│   ├── file_service.py              # CSV I/O (buffered, atomic)
│   ├── data_cache_service.py        # Redis data caching layer
│   ├── optimization_service.py      # Genome optimization orchestration
│   ├── smart_filtering_service.py   # Toxic parameter elimination
│   ├── sheets_service.py            # Google Sheets integration
│   ├── genome_service.py            # Genome generation & parameter permutation
│   ├── get_all_stocks.py            # HK stock codes fetcher
│   └── results_aggregation_service.py # Financial metrics calculation
│
├── config/
│   ├── queue_config.py              # Redis connection + queue setup
│   ├── logging_config.py            # Log configuration & debug flags
│   └── smart_filtering_config.py    # Smart filtering env var config
│
├── controllers/
│   ├── algorithm_controller.py      # REST API — start testing
│   ├── optimization_controller.py   # REST API — optimization CRUD
│   ├── monitoring_controller.py     # REST API — queue & worker status
│   ├── summary_controller.py        # REST API — generate trading summary
│   ├── genome_controller.py         # REST API — genome parameter lookup
│   ├── sheets_controller.py         # REST API — Google Sheets health check
│   └── dashboard_controller.py      # HTML dashboard for optimization monitoring
│
└── utils/
    └── performance_profiler.py      # Timing decorators & metrics

workers/
├── start_algorithm_worker.py        # Algorithm worker process launcher
├── start_result_worker.py           # Result worker process launcher
└── start_file_write_worker.py       # File write worker process launcher

data/                                # Runtime CSV output directory
├── {stock}_{genome}.csv             # Temporary per-run signal files
├── general_results.csv              # All trade records with financials
├── optimization_results.csv         # Genome comparison metrics
├── comparison_results.csv           # Algo vs API comparison data
└── Automated Results.csv            # Final output matching sample format
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| **API & Service** | | |
| `API_KEY` | (required) | StockFisher API authentication key |
| `API_PORT` | `8000` | HTTP port for the FastAPI service |
| `ENVIRONMENT` | `development` | Runtime environment |
| `DEBUG` | `true` | Enable debug mode |
| **Date Range** | | |
| `OPTIMIZATION_START_DATE` | `2025-01-01` | Start of analysis date range |
| `OPTIMIZATION_END_DATE` | `2026-02-02` | End of analysis date range |
| **Redis** | | |
| `REDIS_HOST` | `localhost` | Redis server hostname |
| `REDIS_PORT` | `6379` | Redis server port |
| `REDIS_DB` | `0` | Redis database number |
| **Worker Parallelization** | | |
| `ALGORITHM_WORKER_COUNT` | `1` | Number of algorithm worker processes |
| `RESULT_WORKER_COUNT` | `1` | Number of result worker processes |
| `FILE_WORKER_COUNT` | `1` | Number of file write worker processes |
| `WORKER_CONCURRENT_TASKS` | `1` | Threads per worker (in-worker parallelization) |
| **Worker Timeouts** | | |
| `ALGORITHM_WORKER_TIMEOUT` | `1000` | Max seconds per algorithm task |
| `RESULT_WORKER_TIMEOUT` | `300` | Max seconds per result task |
| `FILE_WRITE_WORKER_TIMEOUT` | `60` | Max seconds per file write task |
| **Google Sheets** | | |
| `GOOGLE_SHEETS_CREDENTIALS_PATH` | `/app/credentials/google_sheets.json` | Path to Google Sheets service account JSON |
| `INPUT_SHEET_ID` | (required) | Google Sheets spreadsheet ID for input |
| `OUTPUT_SHEET_ID` | (required) | Google Sheets spreadsheet ID for output |
| `INPUT_SHEET_NAME` | `Parameter Tuning` | Input worksheet (tab) name |
| `OUTPUT_SHEET_NAME` | `Automated Results` | Output worksheet name (also used for CSV filename) |
| `OUTPUT_PER_GENOME_SHEET_NAME` | `Automated Results Per Genome` | Per-genome output worksheet name |
| **Smart Filtering** | | |
| `SMART_FILTERING_ENABLED` | `true` | Enable toxic parameter elimination |
| `MIN_PAYOFF_RATIO` | `2` | Minimum payoff ratio to keep a genome |
| `OUT_PAYOFF_RATIO` | `1` | Payoff ratio threshold for elimination |
| `MIN_OBSERVATIONS` | `2` | Minimum observations before filtering |
| **Logging & Debug** | | |
| `LOG_LEVEL` | `INFO` | Log level (DEBUG, INFO, WARNING, ERROR) |
| `ALGORITHM_DEBUG` | `false` | Enable detailed debug/profiling logging |
| `LOG_PROGRESS_INTERVAL` | `100` | Log progress every N trade days |
