# Performance Optimization Requirements

## Context

**Current state:** 37 genomes processed in 194 minutes (8 workers × 5 threads).  
**Per-genome time:** ~5.2 minutes (~312 seconds).  
**Trading days per genome:** ~2,481 (2016-01-01 to 2026-02-02).

### Root Cause Analysis

Profiling and code review identified three dominant bottlenecks:

1. **O(n²) indicator recalculation** — every buy/sell signal function recomputes SMA, Bollinger Bands, ATR, and other indicators from scratch on every trading day as the data slice grows. This accounts for ~85% of total compute time and is visible in logs: processing speed degrades from ~16s/100 days early on to ~27s/100 days at the end.
2. **Redundant sorting and data conversion** — sell signal functions sort the entire OHLCV dataset 10+ times per day (once per condition), and data is triple-converted (pickle → OHLCV → dict → OHLCV) on every cache hit.
3. **GIL contention** — `ThreadPoolExecutor` provides zero CPU parallelism for CPU-bound Python code, making the 5 threads per worker counterproductive.

### Critical Constraint

**The logic of indicators must not change.** All buy conditions (B1–B18), sell conditions (S1–S17), and energy indicators (E1–E5) must produce identical results to the current implementation. Input and output data formats must remain unchanged. Each phase must be validated by comparing its outputs against the reference (current) outputs on a known stock/genome.

### Phased Approach

The optimization is split into 4 independent phases. Each phase is self-contained — it can be implemented, tested, and merged individually without depending on other phases. Phases are ordered by expected impact (highest first).

---

## Phase 1 — Enable PrecomputedIndicators for Buy Signals

### Goal

Replace the per-day O(n) indicator recalculations in the buy path with O(1) pre-computed array lookups. This addresses the primary bottleneck for the ~50% of trading days spent in `position_status == "F"`.

**Expected speedup:** ~2–3× on total genome processing time.

### Background

The module `app/workers/algo_func/precomputed_indicators.py` (942 lines) already exists but is disabled. It pre-computes all buy-side indicators (SMA, Bollinger Bands, ATR, RSI, rolling windows) once using NumPy/pandas vectorized operations, then provides O(1) index-based lookups via `run_all_buy_conditions_fast(idx)`.

Currently disabled at:
- Import commented out: `algorithm_worker.py` line 17
- Initialization commented out: `algorithm_worker.py` lines 228–231

### Tasks

#### 1.1 Fix B18 Condition 8 Correctness Discrepancy

**Problem:** The precomputed `get_b18_condition()` (precomputed_indicators.py, lines 855–870) compares a single current BBW value against `bbw_ago * bbw_ratio`. The original `condition8_b18()` (buy_signals.py, lines 71–115) computes `mean(recent_bbw[-input_B18_Z:])` (SMA of the last Z BBW values) vs `recent_bbw[-1 - input_B18_Y]`, then checks `bbw_sma_now < bbw_y_ago * (input_B18_X / 100.0)`. These are different calculations.

**Required fix:**
- In `compute_all()`, add a pre-computed `sma_bbw_b18` array: `self.sma_bbw_b18 = self._sma_full(self.bbw_b18, input_B18_Z)`.
- In `get_b18_condition()`, for condition 8:
  - Replace `bbw_now = self.bbw_b18[idx]` with `bbw_sma_now = self.sma_bbw_b18[idx]`.
  - Keep `bbw_ago_idx = idx - input_B18_history` for looking up `self.bbw_b18[bbw_ago_idx]`.
  - Apply the ratio as `bbw_sma_now < bbw_ago * (input_B18_X / 100.0)` where `input_B18_X = p.input_B18_bbw_ratio * 100`.
- Additionally, the original `condition8_b18()` filters out `None` BBW values (`recent_bbw = [x for x in bbw if x is not None]`) before applying the SMA and history lookup. The precomputed version uses NaN-padded arrays. Verify that the index offsets remain aligned — the original filters out NaN-equivalent values which could shift indices. If discrepancy arises, add a lookup correction.

**Acceptance criteria:** For stock 3888, genome G_000, the `B18` field in `run_all_buy_conditions_fast(idx)` must return the same boolean as `checkB18()` for every trading day in the range.

#### 1.2 Verify B1 Rolling Max Window Alignment

**Problem:** The precomputed `get_b1_condition()` (precomputed_indicators.py, line 569) uses `self.rolling_max_b1[idx - 1]` where `rolling_max_b1` is a pandas `rolling(lookback).max()` over the highs array. The original `checkB1()` (buy_signals.py, line 163) computes `max(highs[-(lookback+1):-1])` — the max of `lookback` highs ending one bar before the current bar.

**Required analysis:**
- Confirm that `pd.Series(highs).rolling(lookback).max()` at position `idx-1` produces the same value as `max(highs[idx-lookback:idx])` (i.e., lookback values ending at `idx-1`).
- If there is an edge-case difference (e.g., when `idx < lookback`), fix the precomputed version to match.

**Acceptance criteria:** For stock 3888, genome G_000, the `B1` field must match for all trading days.

#### 1.3 Validate All Buy Conditions (B1, B3, B8–B13, B18, stopLoss)

**Required:** Build a validation test (can be placed in `tests/`) that:
1. Fetches stock 3888 data and SPY (2800) data.
2. Iterates through all trading days from START_DATE to END_DATE.
3. For each day, computes buy conditions via both:
   - `runAllBuyConditions(filtered_code, tradeday_str, filtered_spy, params)` (original)
   - `precomputed.run_all_buy_conditions_fast(idx)` (precomputed)
4. Compares all fields: `B1`, `B3`, `B8`, `B9`, `B10`, `B11`, `B12`, `B13`, `B18`, `stopLoss`.
5. Reports any mismatches with day index, date, and both values.
6. The test must pass with **zero mismatches** before proceeding.

**Note:** The `stopLoss` value uses `wilder_atr()` in the original and `_atr_full()` in the precomputed version. Both implement Wilder's smoothing but may have floating-point differences. Allow tolerance of ±0.0001 for `stopLoss` comparison.

#### 1.4 Integrate PrecomputedIndicators into Algorithm Worker

**Changes to `algorithm_worker.py`:**

1. Uncomment the import on line 17:
   ```python
   from app.workers.algo_func.precomputed_indicators import PrecomputedIndicators, is_buy_fast
   ```

2. In `signals_for_the_period()`, after OHLCV object creation and date index building, uncomment and activate:
   ```python
   precomputed = PrecomputedIndicators(code_data, spy_data, params)
   precomputed.compute_all()
   ```

3. In the `position_status == "F"` branch (line 262), replace:
   ```python
   buySignals = runAllBuyConditions(filtered_code, tradeday_str, filtered_spy, params)
   buy = isBuy(buySignals)
   ```
   with:
   ```python
   buySignals = precomputed.run_all_buy_conditions_fast(code_end_idx)
   buy = is_buy_fast(buySignals)
   ```
   The `code_end_idx` variable (computed on line 259) is the index into the full `code_data` array — this is exactly what `PrecomputedIndicators` expects.

4. The sell path (`position_status == "I"`) remains unchanged in this phase.

**Important:** `PrecomputedIndicators.__init__()` expects `List[OHLCV]` where `OHLCV` is the dataclass from `precomputed_indicators.py`. The worker uses `OHLCV` from `buy_signals.py`. Both have the same fields (`date`, `open`, `high`, `low`, `close`, `volume`). Verify duck-typing compatibility or import the correct class.

#### 1.5 End-to-End Validation

After integration, run the full pipeline on stock 3888 with genome G_000 and compare the final formatted trade CSV against the reference output. All columns (`Genome ID`, `Buy Signal`, `Stop Signal`, `Entry price`, `Exit price`, `Gain/Lose`) must match exactly.

### Files Modified

| File | Change |
|------|--------|
| `app/workers/algo_func/precomputed_indicators.py` | Fix B18 condition 8 (SMA of BBW), verify B1 rolling max |
| `app/workers/algorithm_worker.py` | Uncomment import, activate precomputed path for buy signals |
| `tests/` | New validation test for buy signal parity |

### Risks

- **Floating-point precision:** NumPy/pandas use 64-bit floats with different operation ordering than pure Python. Minor rounding differences may cause edge-case signal differences. Mitigate by comparing with tolerance where appropriate (stop-loss, ATR values) but requiring exact match on boolean conditions.
- **B9/B10 completeness:** These methods in `PrecomputedIndicators` re-slice raw numpy arrays within the method body rather than using fully pre-computed rolling arrays. This is functionally correct but not maximally optimized. Acceptable for Phase 1.

---

## Phase 2 — Optimize Sell Signal Path

### Goal

Eliminate redundant sorting, duplicate computations, and missed short-circuit opportunities in the 15 sell conditions. This addresses the bottleneck for the ~50% of trading days spent in `position_status == "I"`.

**Expected speedup:** ~3–5× on in-position days, ~1.5–2.5× on total genome time.

### Background

Currently, `runAllSellConditions()` (sell_signals.py, lines 727–752) evaluates all 15 sell conditions sequentially without short-circuiting. Each condition independently:
- Sorts the entire OHLCV list with `sorted(ohlcv, key=lambda x: to_ts(x.date))` — O(n log n) with `to_ts()` parsing date strings via `datetime.fromisoformat()`.
- Recomputes ATR, SMA, True Range Series from scratch.
- `s9()` recalculates energy indicators that were already computed in the main loop.

### Tasks

#### 2.1 Remove Redundant Sorting

**Problem:** 10 out of 15 sell conditions sort the input OHLCV list, but data is already sorted chronologically when passed from the main loop (it's sliced from `code_data[:code_end_idx + 1]` which was built from API data sorted ascending in `get_db_data.py`).

**Required change:** In each of the following functions, remove the `data = sorted(ohlcv, key=lambda x: to_ts(x.date))` call and use `ohlcv` directly (or assign `data = ohlcv` to minimize diff):
- `s4()` (line 119)
- `s6()` (line 290)
- `s7()` (line 354)
- `s8()` (line 392)
- `s10()` (line 447)
- `s13()` (line 505)
- `s14()` (line 540, sorts both stock and SPY)
- `s15()` (line 597)
- `s16()` (line 632)
- `s17()` (line 671)

**Safety check:** Add an assertion at the top of `runAllSellConditions()` to validate sort order:
```python
assert all(to_ts(ohlcv[i].date) <= to_ts(ohlcv[i+1].date) for i in range(len(ohlcv)-2)), \
    "OHLCV data must be sorted by date ascending"
```
This assertion should be conditional on a debug flag to avoid O(n) overhead in production. Alternatively, check only the first and last elements.

**Acceptance criteria:** Sell signals must produce identical results before and after the change for stock 3888, genome G_000.

#### 2.2 Eliminate Duplicate Energy Computation in S9

**Problem:** In the main loop (algorithm_worker.py, line 240), `calculate_energy_indicators_last_16_days()` is called for every day. Then, when in position, `s9()` (sell_signals.py, line 430) calls `calculate_energy_indicators_last_16_days()` again with the same arguments.

**Required change:**
- Add an `energy_data` parameter to `runAllSellConditions()`:
  ```python
  def runAllSellConditions(ohlcv, spy_data, buy_date, buy_price, stop_loss, trade_date,
                           params=None, energy_data=None):
  ```
- Inside `runAllSellConditions()`, pass `energy_data` to `s9()` instead of having `s9()` call energy calculation independently.
- Modify `s9()` to accept pre-computed energy data:
  ```python
  def s9(trade_date, ohlcv, spy_data, params=None, energy_data=None):
      if energy_data is None:
          energy_data = calculate_energy_indicators_last_16_days(trade_date, ohlcv, spy_data)
      return energy_data["energy_score"] < energy_thresh
  ```
- In algorithm_worker.py, pass `energy_data` from the main loop:
  ```python
  sellSignals = runAllSellConditions(
      filtered_code, filtered_spy, entry_date,
      to_float_or_none(entry_price), exit1, tradeday_str, params,
      energy_data=energy_data
  )
  ```

**Acceptance criteria:** `s9()` results unchanged. Function backwards-compatible via default `energy_data=None`.

#### 2.3 Short-Circuit Sell Evaluation

**Problem:** `isSell()` uses `or` — only one `True` condition is needed to trigger a sell. But `runAllSellConditions()` always evaluates all 15 conditions, including expensive ones (S11/S12 Fibonacci with nested loops, S14 relative performance with dual dataset traversal).

**Required change:** Restructure `runAllSellConditions()` to evaluate conditions from cheapest to most expensive and return early on the first `True`.

Recommended evaluation order (cheapest first):
1. **S1** — single float comparison (`close <= stop_loss`)
2. **S15** — 4 bars, one division
3. **S7** — 2 bars, 2 ATR lookups (if pre-computed) or last 2 values
4. **S5** — index arithmetic + 1 ATR lookup (on key days only)
5. **S9** — pre-computed energy score comparison (with 2.2 fix)
6. **S17** — min/max of last 150 bars
7. **S13** — min of last 80 close values
8. **S10** — 2 ATR values + 90-bar max
9. **S8** — TR series + SMA(22) + SMA(100)
10. **S6** — 90-bar max + index scan
11. **S4** — SMA(150) + 50-bar scan
12. **S16** — ATR(22) + 2 index scans
13. **S11** — Fibonacci with 2-day window over 250 bars
14. **S12** — Fibonacci with 22-day window over 250 bars
15. **S14** — dual dataset scan with timestamp alignment

**Implementation pattern:**
```python
def runAllSellConditions(ohlcv, spy_data, buy_date, buy_price, stop_loss, trade_date,
                         params=None, energy_data=None):
    if params is None:
        params = AlgorithmParameters()

    s5_exit, new_stop = s5(ohlcv, buy_date, buy_price, stop_loss, trade_date, params)

    conditions = {}
    # Evaluate cheapest first, short-circuit on first True
    ordered_checks = [
        ("S1", lambda: exit_by_stop_loss(ohlcv, stop_loss, params)),
        ("S15", lambda: s15(ohlcv, buy_date, buy_price, params)),
        ("S5", lambda: s5_exit),
        ("S7", lambda: s7(ohlcv, buy_date, buy_price, params)),
        ("S9", lambda: s9(trade_date, ohlcv, spy_data, params, energy_data=energy_data)),
        # ... remaining conditions
    ]

    found_sell = False
    for key, check_fn in ordered_checks:
        result = check_fn()
        conditions[key] = result
        if result:
            found_sell = True
            break

    # Fill remaining conditions as False (not evaluated)
    for key, _ in ordered_checks:
        if key not in conditions:
            conditions[key] = False

    return {"conditions": conditions, "stop_loss": new_stop}
```

**Important:** `s5()` must always be evaluated because it returns `new_stop` (the updated stop-loss value) which is needed regardless of sell decision. The `s5()` call at the top of the function must remain.

**Acceptance criteria:** Final sell decisions (`isSell()` result) must be identical for all trading days. Individual condition values for non-triggered days will differ (showing `False` instead of being computed) — this is acceptable because only the first `True` matters, and all subsequent processing only uses `isSell()`.

#### 2.4 Precompute Sell-Side ATR Arrays (Optional Extension)

**Scope:** If Phase 1 `PrecomputedIndicators` is active, extend it with sell-side arrays. This is optional because it depends on Phase 1.

**Add to `PrecomputedIndicators.compute_all()`:**
- `self.atr_22_wilder` — Wilder's ATR, period 22 (for S7, S8, S16)
- `self.atr_10_wilder` — Wilder's ATR, period 10 (for S10)
- `self.atr_100_sma` — SMA-based ATR, period 100 (for S8, S10) — note: S8 uses `sma(tr_series, 100)`, not Wilder's smoothing
- `self.rolling_max_90` — rolling max of highs, period 90 (for S6, S10)

**Create corresponding lookup methods:** `get_s7_data(idx)`, `get_s8_data(idx)`, etc., returning pre-computed values that the sell condition functions can use instead of recomputing from scratch.

**Acceptance criteria:** Same as 2.1 — sell results must be identical.

### Files Modified

| File | Change |
|------|--------|
| `app/workers/algo_func/sell_signals.py` | Remove sorting, short-circuit, accept energy_data |
| `app/workers/algorithm_worker.py` | Pass energy_data to runAllSellConditions |
| `app/workers/algo_func/precomputed_indicators.py` | (Optional 2.4) Add sell-side arrays |
| `tests/` | New validation test for sell signal parity |

### Risks

- **S5 side effect:** `s5()` modifies `new_stop` and must always run. The short-circuit pattern must accommodate this.
- **Sort removal safety:** If any code path feeds unsorted data to sell conditions (e.g., a different caller), removing sort would break it. The debug assertion mitigates this.
- **Short-circuit logging:** When short-circuiting, unevaluated conditions show `False` instead of their true value. If downstream code logs or analyzes individual condition states, this could mislead. Ensure `isSell()` is the only consumer of the conditions dict.

---

## Phase 3 — Eliminate Per-Day Overhead in the Main Loop

### Goal

Remove redundant work that happens on every iteration of the day-by-day loop: repeated pandas datetime parsing, list slice copying, redundant data fetching, and triple data type conversion.

**Expected speedup:** ~1.3–1.5× on total genome time.

### Background

The main loop in `signals_for_the_period()` (algorithm_worker.py, lines 252–365) processes ~2,481 days. Several O(1)-per-day operations accumulate significant overhead due to the high iteration count.

### Tasks

#### 3.1 Replace `pd.to_datetime()` in Inner Loop

**Problem:** Line 253 uses `tradeday = pd.to_datetime(bar.date).tz_localize(None)` inside the main loop. `pd.to_datetime()` is a high-overhead function designed for Series, not scalar string parsing. Called 2,481 times per genome.

**Required change:** Replace with `datetime.strptime()`:
```python
tradeday = datetime.strptime(bar.date, "%Y-%m-%d")
tradeday_str = bar.date  # Already in "YYYY-MM-DD" format
```

Also apply the same fix to the pre-loop filter (lines 244–247):
```python
# Replace:
bar_date = pd.to_datetime(bar.date)
if bar_date > latest_date:
# With:
bar_date = datetime.strptime(bar.date, "%Y-%m-%d")
if bar_date > latest_date:
```

And to `latest_date` parsing (line 241):
```python
# Replace:
latest_date = pd.to_datetime(latest_signal["tradeday"]).tz_localize(None)
# With:
latest_date = datetime.strptime(str(latest_signal["tradeday"]).split("T")[0], "%Y-%m-%d")
```

**Acceptance criteria:** All date comparisons and `tradeday_str` outputs must remain identical.

#### 3.2 Eliminate Redundant Data Fetch in `get_data_and_save_to_csv`

**Problem:** `process_algorithm_task()` calls `get_data_and_save_to_csv()` (line 103) which fetches stock data via `get_stock_data_from_db(code, END_DATE)`. Then `signals_for_the_period()` (line 107) fetches the **same stock data** and also SPY data again (lines 200, 203). This causes 2 redundant Redis cache deserialization + OHLCV conversion cycles per genome.

**Required change:**
- Fetch stock data and SPY data once in `process_algorithm_task()`.
- Pass the raw data as parameters to both `get_data_and_save_to_csv()` and `signals_for_the_period()`.

Updated signatures:
```python
async def get_data_and_save_to_csv(code, trade_date, genome_id="G_000",
                                    file_service=None, file_name=None,
                                    code_data_raw=None):
    # If code_data_raw not provided, fetch it (backwards compatible)
    if code_data_raw is None:
        code_data_raw = await get_stock_data_from_db(code, END_DATE)
    ...

async def signals_for_the_period(code, trade_date, params=None,
                                  genome_id="G_000", file_name=None,
                                  code_data_raw=None, spy_data_raw=None):
    # If not provided, fetch (backwards compatible)
    if spy_data_raw is None:
        spy_data_raw = await get_stock_data_from_db("2800", trade_date)
    if code_data_raw is None:
        code_data_raw = await get_stock_data_from_db(code, trade_date)
    ...
```

In `process_algorithm_task()`:
```python
code_data_raw = await get_stock_data_from_db(stock_code, END_DATE)
spy_data_raw = await get_stock_data_from_db("2800", END_DATE)

await get_data_and_save_to_csv(stock_code, START_DATE, genome_id,
                                file_name=genome_file_name,
                                code_data_raw=code_data_raw)

await signals_for_the_period(stock_code, END_DATE, params, genome_id,
                              file_name=genome_file_name,
                              code_data_raw=code_data_raw,
                              spy_data_raw=spy_data_raw)
```

**Acceptance criteria:** No change in behavior. Data is fetched at most once per genome per data type.

#### 3.3 Eliminate Triple Data Conversion on Cache Hit

**Problem:** The caching layer stores data as `OHLCV` objects (from `data_cache_service.py`). On cache hit, `get_stock_data_from_db()` (get_db_data.py, lines 108–120) converts cached `OHLCV` objects back to dict format:
```python
return [{"date": bar.date, "open": bar.open, ...} for bar in cached_data]
```
Then `signals_for_the_period()` (algorithm_worker.py, lines 209–216) converts those dicts back to `OHLCV` objects:
```python
code_data = [OHLCV(bar["date"], bar["open"], ...) for bar in code_data_raw]
```

**Required change:** Add a function (or parameter flag) that returns cached data directly as `OHLCV` objects without the dict round-trip. Two approaches:

**Approach A (minimal):** Add a `return_ohlcv=True` parameter to `get_stock_data_from_db()`:
```python
async def get_stock_data_from_db(code, end_date=None, return_ohlcv=False):
    # On cache hit, if return_ohlcv, return OHLCV objects directly
    # Otherwise return dicts (backward compatible)
```

**Approach B (cleaner):** Add a separate function `get_stock_ohlcv_from_db(code, end_date)` that returns `List[OHLCV]` directly.

Either approach eliminates ~9,000 redundant object creations per genome (4,500 for stock + 4,500 for SPY).

**Acceptance criteria:** Same data arrives in `signals_for_the_period()`. OHLCV objects have identical field values.

#### 3.4 Reduce List Slicing Overhead

**Problem:** Lines 259–260 create list slices every day:
```python
filtered_spy = spy_data[:spy_end_idx + 1]
filtered_code = code_data[:code_end_idx + 1]
```
Python list slicing copies all element references. On the last trading day, this copies ~4,500 references × 2 lists.

**Required change (conditional on Phase 1):** If `PrecomputedIndicators` is active, the buy path no longer needs `filtered_code` and `filtered_spy` (it uses `code_end_idx` directly). The slicing is only needed for:
- Energy calculation: `calculate_energy_indicators_last_16_days(tradeday_str, filtered_code, filtered_spy)`
- Sell conditions: `runAllSellConditions(filtered_code, filtered_spy, ...)`

**Option 1 — Lazy slicing:** Only slice when entering the branch that needs it:
```python
# Don't slice upfront; defer to where needed
if position_status == "F":
    buySignals = precomputed.run_all_buy_conditions_fast(code_end_idx)
    # Only slice for energy (still needed)
    filtered_code = code_data[:code_end_idx + 1]
    filtered_spy = spy_data[:spy_end_idx + 1]
    energy_data = calculate_energy_indicators_last_16_days(tradeday_str, filtered_code, filtered_spy)
    ...
elif position_status == "I":
    filtered_code = code_data[:code_end_idx + 1]
    filtered_spy = spy_data[:spy_end_idx + 1]
    energy_data = calculate_energy_indicators_last_16_days(tradeday_str, filtered_code, filtered_spy)
    ...
```

This doesn't eliminate slicing but avoids it in the buy path when only the precomputed index is needed.

**Option 2 — Pass index bounds:** Refactor energy and sell functions to accept `(data, end_idx)` tuples and operate on `data[:end_idx+1]` internally. Higher effort, higher payoff.

**Acceptance criteria:** Output unchanged. Profile to confirm improvement.

#### 3.5 Optimize `get_latest_signal()` for Single-Row CSV

**Problem:** `get_latest_signal()` (algorithm_worker.py, lines 429–465) reads the entire CSV, filters by code and genome_id, parses all dates, finds the max. At the start of each genome run, the CSV has exactly 1 row (the seed from `get_data_and_save_to_csv()`), making all this work unnecessary.

**Required change:** Since `get_data_and_save_to_csv()` always returns the seed row, pass it directly to `signals_for_the_period()` instead of re-reading from CSV:

```python
# In process_algorithm_task():
seed_row = await get_data_and_save_to_csv(...)
await signals_for_the_period(..., initial_signal=seed_row)
```

In `signals_for_the_period()`, use `initial_signal` as `latest_signal` instead of calling `get_latest_signal()`.

**Acceptance criteria:** Same `latest_signal` data used in the loop.

### Files Modified

| File | Change |
|------|--------|
| `app/workers/algorithm_worker.py` | Replace pd.to_datetime, pass data, pass seed row |
| `app/workers/algo_func/get_db_data.py` | (Optional 3.3) Add OHLCV return path |

### Risks

- **Date format edge cases:** `datetime.strptime` is strict about format. If any `tradeday` values come in formats other than `YYYY-MM-DD` (e.g., with timezone info), it will raise an error. Add a fallback to `pd.to_datetime` in a try/except if needed.
- **Backward compatibility:** All signature changes must use default parameters to keep existing callers working.

---

## Phase 4 — Fix Concurrency Model

### Goal

Switch from thread-based to process-based parallelism for CPU-bound work, eliminating GIL contention. Optionally remove unnecessary async/event loop overhead.

**Expected speedup:** Near-linear scaling with CPU cores (currently ~0% benefit from threads → potential ~5× with 8 cores fully utilized).

### Background

`ConcurrentWorker` (concurrent_worker.py) uses `ThreadPoolExecutor` with `concurrent_tasks` threads. The algorithm computation is purely CPU-bound Python — indicator calculations, list comprehensions, sorting. Python's GIL allows only one thread to execute Python bytecode at a time, making multithreading counterproductive for CPU work — the threads add context-switching overhead without gaining parallelism.

Current setup: 8 workers (processes) × 5 threads = 40 logical workers, but effective CPU parallelism = 8 (one per process, the threads fight over each process's GIL).

### Tasks

#### 4.1 Set Threads to 1 (Zero-Code-Change Option)

**Simplest fix:** Change `ALGORITHM_CONCURRENT_TASKS` from 5 to 1 via environment variable. This eliminates GIL contention immediately.

**Compensate:** Increase `ALGORITHM_WORKER_COUNT` to equal the number of available CPU cores (e.g., 8 or 10). Each worker process has its own GIL and can run at full speed.

**Required change (environment/config only):**
```
ALGORITHM_WORKER_COUNT=8    # or number of CPU cores
ALGORITHM_CONCURRENT_TASKS=1
```

**Acceptance criteria:** Total throughput improves. Each worker process runs at full single-thread speed without contention.

#### 4.2 Remove Per-Job Event Loop Creation

**Problem:** Each job creates and destroys an asyncio event loop (concurrent_worker.py, lines 43–47):
```python
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
try:
    result = loop.run_until_complete(func(*args, **kwargs))
finally:
    loop.close()
```

With `ALGORITHM_CONCURRENT_TASKS=1`, only one job runs at a time per process, so the event loop is created/destroyed sequentially for every single genome.

**Required change:** Create a single event loop per worker process and reuse it:
```python
class ConcurrentWorker:
    def __init__(self, ...):
        ...
        self._loop = None

    def _get_loop(self):
        if self._loop is None or self._loop.is_closed():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
        return self._loop

    def process_job(self, job):
        ...
        if inspect.iscoroutinefunction(func):
            loop = self._get_loop()
            result = loop.run_until_complete(func(*args, **kwargs))
        ...
```

**Note:** If no `async` operations in the worker actually perform true I/O (currently they don't — the `await` calls are over synchronous `requests.get()` wrapped in async), consider making the worker functions synchronous entirely in a future refactor to eliminate async overhead completely. This is out of scope for this phase (changes function signatures across the codebase).

**Acceptance criteria:** Worker behavior unchanged. Event loop overhead eliminated.

#### 4.3 Reduce Polling Interval

**Problem:** The work loop (concurrent_worker.py, line 101) sleeps `0.1s` between checking for completed futures and `0.5s` when no jobs are active (line 95). With `concurrent_tasks=1`, the `0.1s` sleep adds a flat 100ms latency after each job completes before the next one starts.

**Required change:**
- Reduce active polling from `0.1s` to `0.01s` or remove it when `concurrent_tasks == 1` (single sequential loop with blocking queue pop).
- Keep `0.5s` for idle polling (no jobs available).

**Acceptance criteria:** Reduced latency between job completions. No busy-wait.

### Files Modified

| File | Change |
|------|--------|
| `app/workers/concurrent_worker.py` | Reuse event loop, reduce polling |
| Environment / docker-compose.yml | Set ALGORITHM_CONCURRENT_TASKS=1, adjust ALGORITHM_WORKER_COUNT |

### Risks

- **Memory per process:** Each worker process has its own memory space. If `ALGORITHM_WORKER_COUNT` is set too high, total memory usage may exceed available RAM (each process holds OHLCV data arrays, precomputed indicators, etc.). Monitor memory with `docker stats` after changes.
- **Redis connection limits:** More worker processes = more Redis connections. Ensure Redis `maxclients` can handle `ALGORITHM_WORKER_COUNT × 2` (one for queue, one for cache).

---

## Validation Strategy (All Phases)

### Reference Output Generation

Before starting any phase, generate reference outputs:

1. **Run stock 3888 with genome G_000** using the current (unmodified) code.
2. Save the intermediate raw signal CSV (before `format_signals_csv_inplace` overwrites it).
3. Save the final formatted trade CSV.
4. Record per-day buy/sell signal values for all conditions.

Store these in `tests/test_data/` as reference fixtures.

### Per-Phase Validation

After each phase:

1. **Unit test:** Run the specific validation test for that phase (buy parity, sell parity, etc.).
2. **Integration test:** Run stock 3888 with G_000 through `process_algorithm_task()`. Compare final formatted CSV against reference.
3. **Performance benchmark:** Record `signals_for_the_period()` wall time via `PerformanceProfiler`. Compare against pre-optimization baseline.

### Acceptance Criteria Summary

| Phase | Correctness Gate | Performance Gate |
|-------|-----------------|------------------|
| 1 | All buy signals identical to reference | ≥1.5× speedup on total genome time |
| 2 | All sell decisions (`isSell()`) identical to reference | ≥1.2× additional speedup |
| 3 | Final trade CSV identical to reference | Measurable speedup (profile-confirmed) |
| 4 | Final trade CSV identical to reference | Near-linear scaling with CPU cores |

---

## Estimated Impact

| Metric | Current | After All Phases |
|--------|---------|-----------------|
| Per-genome time | ~312s | ~15–30s |
| 37 genomes (8 cores) | 194 min | ~10–20 min |
| Bottleneck | O(n²) indicator recalculation | O(n) precomputed + constant lookups |
| CPU utilization | ~12.5% effective (GIL) | ~100% per core |
