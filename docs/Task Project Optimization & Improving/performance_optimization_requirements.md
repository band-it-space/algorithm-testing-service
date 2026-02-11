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

The optimization is split into 7 independent phases. Each phase is self-contained — it can be implemented, tested, and merged individually without depending on other phases. Phases are ordered by expected impact (highest first).

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


## Phase 5 — Pre-Compute Sell-Side ATR and Rolling Window Arrays

### Goal

Replace the per-day O(n) ATR and rolling-window recomputations inside sell conditions (S4–S17) with O(1) pre-computed array lookups. This addresses the >90% of remaining per-sell-day cost that comes from full-pass ATR, SMA, TR, and rolling max/min recalculations.

**Expected speedup:** ~3–5× on sell-day cost, ~2–3× on total genome time (from ~133s to ~40–60s).

### Background

After Phases 1–3, the buy path uses O(1) lookups via `PrecomputedIndicators`, but every sell condition still recomputes indicator arrays from scratch on every I-day. Profiling shows:

| Sell function | Indicator recomputed from scratch | Approximate cost per call |
|---|---|---|
| S5 | `atr(ohlcv, 20)` — Wilder's ATR, full series | O(n) |
| S7 | `atr(data, 22)` — Wilder's ATR, full series | O(n) |
| S8 | `calc_tr_series()` + `sma(trs, 22)` + `sma(trs, 100)` — SMA-based ATR | O(n) |
| S10 | `atr(data, 10)` + `atr(data, 100)` + `max(highs[-91:-1])` | O(n) |
| S16 | `calc_tr_series()` + `atr(data, 22)` | O(n) |
| S4 | `sma(closes, 150)` — SMA of all closes | O(n) |
| S6 | `max(highs[-90:])` + argmax scan | O(window) |
| S13 | `min(closes[-80:])` | O(window) |
| S17 | `max(highs[-150:])` + `min(lows[-150:])` | O(window) |
| S11/S12 | `max(highs[-250:])` + `min(lows[-250:])` × yy_days | O(window × yy_days) |
| S14 | Timestamp alignment + 3 period ratios | O(n) |
| S15 | `close[-1]/close[-5]` | O(1) — already cheap |

Additionally, every sell function that needs `buy_idx` performs an O(n) linear scan over OHLCV dates to find the buy entry index, repeated 7+ times per sell-day.

### Tasks

#### 5.1 Add ATR Arrays (Wilder's Smoothing)

**Problem:** ATR is recomputed from scratch in S5 (period 20), S7 (period 22), S10 (period 10 and 100), S16 (period 22). Each call processes the full O(n) OHLCV series.

**Existing bug:** `self.atr_s5` in `PrecomputedIndicators` is computed with hardcoded period `22` (`precomputed_indicators.py`, line 222: `self.atr_s5 = self._atr_full(self.highs, self.lows, self.closes, 22)`), but S5 uses `params.input_S5_atr_period` which defaults to **20**. This must be corrected.

**Required arrays to add in `compute_all()`:**

```python
# === Sell-side ATR (Wilder's) ===
s5_atr_period = getattr(p, 'input_S5_atr_period', 20)
s7_atr_period = getattr(p, 'input_S7_atr_period', 22)

self.atr_s5 = self._atr_full(self.highs, self.lows, self.closes, s5_atr_period)  # Fix: was hardcoded 22
self.atr_s7 = self._atr_full(self.highs, self.lows, self.closes, s7_atr_period)  # S7, S16
self.atr_10 = self._atr_full(self.highs, self.lows, self.closes, 10)             # S10
self.atr_100 = self._atr_full(self.highs, self.lows, self.closes, 100)           # S10
```

**Note:** If `s7_atr_period == s1_atr_period`, the same array can be reused. Use `self.atr_s1` for S7/S16 if periods match; otherwise create `self.atr_s7` separately.

**Acceptance criteria:** For stock 3888, genome G_000, ATR values from pre-computed arrays must match the per-call `atr()` results for every sell-day to within ±1e-10. Validated via the energy+sell parity test (Task 5.8).

#### 5.2 Add SMA-of-TR Arrays for S8

**Problem:** S8 uses `sma(calc_tr_series(data), 22)` and `sma(calc_tr_series(data), 100)` — this is **simple moving average** of True Range, NOT Wilder's smoothing. The existing `_atr_full()` method uses Wilder's smoothing and produces different values.

**Required:** Add a new helper method `_sma_tr_full(period)` and pre-compute two arrays:

```python
def _sma_tr_full(self, period: int) -> np.ndarray:
    """Calculate SMA-based ATR (simple moving average of True Range).
    
    This matches sell_signals.py's sma(calc_tr_series(data), period)
    which is different from Wilder's smoothing used in _atr_full().
    
    The TR series has n-1 elements (no TR for the first bar).
    The SMA starts producing values at index (period-1) of the TR array,
    which corresponds to index (period) of the original OHLCV array.
    """
    n = len(self.closes)
    result = np.full(n, np.nan)
    
    if n < period + 1:
        return result
    
    # True Range series (n-1 elements, offset by 1 from price array)
    prev_close = np.roll(self.closes, 1)
    prev_close[0] = self.closes[0]
    tr = np.maximum(
        self.highs[1:] - self.lows[1:],
        np.maximum(
            np.abs(self.highs[1:] - prev_close[1:]),
            np.abs(self.lows[1:] - prev_close[1:])
        )
    )
    
    # SMA of TR
    sma_vals = pd.Series(tr).rolling(period).mean().values
    
    # Align: TR[0] corresponds to OHLCV[1], so SMA_TR[i] → result[i+1]
    for i in range(len(sma_vals)):
        if not np.isnan(sma_vals[i]):
            result[i + 1] = sma_vals[i]
    
    return result
```

**Pre-compute in `compute_all()`:**
```python
# === S8: SMA-based ATR (NOT Wilder's) ===
self.sma_tr_22 = self._sma_tr_full(22)
self.sma_tr_100 = self._sma_tr_full(100)
self.rolling_max_sma_tr_22 = self._rolling_max(self.sma_tr_22, p.input_S8_atr22_window)  # default 126
```

**Critical distinction:** The original sell_signals.py `atr()` function (used by S5, S7, S10, S16) uses **Wilder's smoothing**: `atr[i] = (atr[i-1] * (period-1) + tr[i]) / period`. The `sma()` function used by S8 computes a **simple moving average**: `sum(tr[i-period+1:i+1]) / period`. These produce different values and must use different pre-computed arrays.

**Index alignment:** The original code's `calc_tr_series(data)` returns `n-1` values (starting from `data[1]`). Then `sma(trs, 22)` returns `len(trs) - 22 + 1` values starting from `trs[21]`. The first SMA value corresponds to OHLCV index `22`. The original then accesses `atr22[-1]` (last element) and `atr22[-atr22_window:]` (last 126 elements). Must verify that `self.sma_tr_22[idx]` produces the same value as `sma(calc_tr_series(data[:idx+1]), 22)[-1]` for every `idx`.

**Acceptance criteria:** `self.sma_tr_22[idx]` matches `sma(calc_tr_series(ohlcv[:idx+1]), 22)[-1]` for all sell-days. Validated via the sell parity test.

#### 5.3 Add Rolling Window Arrays for S6, S10, S13, S17

**Required arrays:**

```python
# === Rolling windows for sell conditions ===
self.rolling_max_high_90 = self._rolling_max(self.highs, 90)                    # S6, S10
self.rolling_max_high_150 = self._rolling_max(self.highs, p.input_S17_min_days) # S17 (default 150)
self.rolling_min_low_150 = self._rolling_min(self.lows, p.input_S17_min_days)   # S17 (default 150)
self.rolling_min_close_80 = self._rolling_min(self.closes, p.input_S13_lookback) # S13 (default 80)
self.rolling_max_high_5 = self._rolling_max(self.highs, 5)                      # E5
self.rolling_min_low_5 = self._rolling_min(self.lows, 5)                        # E5
```

**Note on offsets:** Several sell functions use windows that exclude the current bar:
- **S6:** `highs[start_window:last_idx + 1]` — includes current bar. Maps to `rolling_max_high_90[idx]`.
- **S10:** `data[-91:-1]` — excludes current bar (90 bars ending at `idx-1`). Must use `rolling_max_high_90[idx - 1]`.
- **S13:** `data[last_idx - lookback : last_idx]` — excludes current bar. Must use a shifted rolling min or `rolling_min(closes, lookback)` at index `idx - 1`.

These offset differences are critical for parity and must be verified per-function.

#### 5.4 Add Date-to-Index Map and S6 Days-Since-High

**Buy-index lookup:**
```python
# O(1) buy-date → index lookup (replaces 7+ linear scans per sell-day)
self.date_to_idx = {d: i for i, d in enumerate(self.dates)}
```

This replaces the `to_ts(buy_date)` + linear search pattern used in S4, S5, S6, S13, S14, S16, S17.

**S6 days-since-high:** S6 needs the number of days since the most recent 90-day high — specifically, `last_idx - last_high_idx` where `last_high_idx` is the last index that achieved the rolling 90-day max. This requires a custom helper:

```python
def _rolling_days_since_max(self, values: np.ndarray, period: int) -> np.ndarray:
    """For each index i, compute i - j where j is the latest index in [i-period+1, i]
    at which values[j] == rolling_max(values, period)[i]."""
    n = len(values)
    result = np.full(n, np.nan)
    for i in range(period - 1, n):
        window_start = i - period + 1
        max_val = values[window_start]
        max_idx = window_start
        for j in range(window_start + 1, i + 1):
            if values[j] >= max_val:
                max_val = values[j]
                max_idx = j
        result[i] = i - max_idx
    return result

# Pre-compute:
self.days_since_high_90 = self._rolling_days_since_max(self.highs, p.input_S6_high_window)  # default 90
```

#### 5.5 Add Fibonacci Ratio and Consecutive-Day Arrays for S11/S12

**Fibonacci ratio:**
```python
# fibo_ratio[i] = (high250[i] - close[i]) / (high250[i] - low250[i])
# where high250 = rolling_max_250, low250 = rolling_min_250 (already pre-computed)
with np.errstate(divide='ignore', invalid='ignore'):
    range_250 = self.rolling_max_250 - self.rolling_min_250
    self.fibo_ratio_250 = np.where(
        range_250 > 0,
        (self.rolling_max_250 - self.closes) / range_250,
        np.nan
    )
```

**Boolean threshold arrays:**
```python
self.fibo_above_382 = self.fibo_ratio_250 > p.input_S11_fib_level   # default 0.382
self.fibo_above_236 = self.fibo_ratio_250 > p.input_S12_fib_level   # default 0.236
```

**Consecutive-day arrays:** S11 requires the fibo condition to be True for 2 consecutive days. S12 requires it for 22 consecutive days. Pre-compute rolling "all True in last N" arrays:

```python
def _rolling_all_true(self, bools: np.ndarray, window: int) -> np.ndarray:
    """True at index i if bools[i-window+1 : i+1] are all True."""
    n = len(bools)
    result = np.full(n, False)
    count = 0
    for i in range(n):
        if bools[i]:
            count += 1
        else:
            count = 0
        if count >= window:
            result[i] = True
    return result

self.fibo_consec_s11 = self._rolling_all_true(self.fibo_above_382, p.input_S11_yy_days)  # default 2
self.fibo_consec_s12 = self._rolling_all_true(self.fibo_above_236, p.input_S12_yy_days)  # default 22
```

**Note:** The original `fibo_exit_stop()` requires `n >= 250`, `bars_since_entry > xx_days`, and evaluates `below_fibo_level` for the last `yy_days` bars. The pre-computed `fibo_consec_s11[idx]` gives the answer for whether all `yy_days` bars ending at `idx` satisfy the condition. The `bars_since_entry > xx_days` guard remains in the fast lookup method (trade-specific, O(1)).

#### 5.6 Add S14 Period Ratios

**Required:**
```python
# S14 relative performance: stock vs SPY at horizons 35, 70, 105
self.stock_ratio_35, self.index_ratio_35 = self._calc_period_ratios(self.closes, self.spy_closes, 35)
self.stock_ratio_70, self.index_ratio_70 = self._calc_period_ratios(self.closes, self.spy_closes, 70)
self.stock_ratio_105, self.index_ratio_105 = self._calc_period_ratios(self.closes, self.spy_closes, 105)
```

**Note:** The existing `_calc_period_ratios()` method handles stock/SPY date alignment via exact string match with bisect fallback, which matches S14's alignment logic (S14 uses `to_ts()` timestamp matching, but since dates are YYYY-MM-DD strings that map 1:1 to timestamps, the results are equivalent). Verify numerically.

**Parameterization:** S14's horizons come from `params.input_S14_horizons` (default `[35, 70, 105]`). The pre-computed arrays should use these values:
```python
for horizon in p.input_S14_horizons:
    stock_r, idx_r = self._calc_period_ratios(self.closes, self.spy_closes, horizon)
    self.s14_stock_ratios[horizon] = stock_r
    self.s14_index_ratios[horizon] = idx_r
```

#### 5.7 Add Fast Sell-Condition Lookup Methods

Add methods to `PrecomputedIndicators` that replace the per-call O(n) computations with O(1) array lookups. Each method handles only the indicator-heavy part; trade-specific logic (buy_idx, days_since_buy guards) remains as cheap arithmetic.

```python
def get_s4_condition(self, idx: int, buy_idx: int, buy_price: float) -> bool:
    """S4: SMA ratio + gain check within max_days window after buy."""
    ...

def get_s5_condition(self, idx: int, buy_idx: int, buy_price: float,
                     stop_loss: float) -> Tuple[bool, float]:
    """S5: Trailing stop with ATR push-up on key days. Returns (exit_signal, new_stop_loss)."""
    ...

def get_s6_condition(self, idx: int, buy_idx: int) -> bool:
    """S6: Days since most recent 90-day high."""
    ...

def get_s7_condition(self, idx: int) -> bool:
    """S7: Two consecutive large bearish bodies > body_mult * ATR(22)."""
    ...

def get_s8_condition(self, idx: int) -> bool:
    """S8: ATR(100) SMA > threshold * max(ATR(22) SMA, 126) + bearish body count."""
    ...

def get_s10_condition(self, idx: int) -> bool:
    """S10: ATR(10) > atr_ratio * ATR(100) + drawdown from 90-day high."""
    ...

def get_s11_condition(self, idx: int, buy_idx: int) -> bool:
    """S11: Fibonacci level (0.382) for 2 consecutive days after 300 bars."""
    ...

def get_s12_condition(self, idx: int, buy_idx: int) -> bool:
    """S12: Fibonacci level (0.236) for 22 consecutive days after 240 bars."""
    ...

def get_s13_condition(self, idx: int, buy_idx: int) -> bool:
    """S13: Close < min(close, 80) after min_days since buy."""
    ...

def get_s14_condition(self, idx: int, buy_idx: int) -> bool:
    """S14: Underperforming SPY at all three horizons after min_days."""
    ...

def get_s15_condition(self, idx: int) -> bool:
    """S15: Crash drop — close/close[idx-lookback] < -crash_drop."""
    ...

def get_s16_condition(self, idx: int, buy_idx: int) -> bool:
    """S16: Big price drop + ATR volatility spike."""
    ...

def get_s17_condition(self, idx: int, buy_idx: int) -> bool:
    """S17: Wide range + near bottom."""
    ...
```

Each method uses only pre-computed arrays (O(1) lookups) and trade-specific parameters passed as arguments.

#### 5.8 Add `run_all_sell_conditions_fast()` Method

Add a single entry point that mirrors the existing `runAllSellConditions()` in `sell_signals.py`:

```python
def run_all_sell_conditions_fast(self, idx: int, buy_idx: int, buy_price: float,
                                  stop_loss: float) -> Dict[str, Any]:
    """Run all sell conditions using pre-computed indicators.
    
    Drop-in replacement for sell_signals.runAllSellConditions().
    Returns {"conditions": {...}, "stop_loss": new_stop} — same format.
    """
    p = self.params

    # S5 MUST always run — it returns updated stop_loss
    s5_exit, new_stop = self.get_s5_condition(idx, buy_idx, buy_price, stop_loss)

    ordered_checks = [
        ("S1",  lambda: self.closes[idx] <= stop_loss if np.isfinite(stop_loss) else False),
        ("S15", lambda: self.get_s15_condition(idx)),
        ("S5",  lambda: s5_exit),
        ("S7",  lambda: self.get_s7_condition(idx)),
        ("S9",  lambda: self.get_s9_condition(idx)),
        ("S17", lambda: self.get_s17_condition(idx, buy_idx)),
        ("S13", lambda: self.get_s13_condition(idx, buy_idx)),
        ("S10", lambda: self.get_s10_condition(idx)),
        ("S8",  lambda: self.get_s8_condition(idx)),
        ("S6",  lambda: self.get_s6_condition(idx, buy_idx)),
        ("S4",  lambda: self.get_s4_condition(idx, buy_idx, buy_price)),
        ("S16", lambda: self.get_s16_condition(idx, buy_idx)),
        ("S11", lambda: self.get_s11_condition(idx, buy_idx)),
        ("S12", lambda: self.get_s12_condition(idx, buy_idx)),
        ("S14", lambda: self.get_s14_condition(idx, buy_idx)),
    ]

    conditions = {}
    for key, check_fn in ordered_checks:
        result = check_fn()
        conditions[key] = result
        if result:
            for remaining_key, _ in ordered_checks:
                if remaining_key not in conditions:
                    conditions[remaining_key] = False
            break

    return {"conditions": conditions, "stop_loss": new_stop}
```

Also add an energy lookup method for CSV output:

```python
def get_energy_data(self, idx: int) -> Dict[str, Any]:
    """Return energy data dict for CSV output (E1–E5 + energy_score)."""
    return {
        "energy_score": self.energy_score[idx] if not np.isnan(self.energy_score[idx]) else 0,
        "E1": str(int(self.e1[idx])) if idx < len(self.e1) else "0",
        "E2": str(int(self.e2[idx])) if idx < len(self.e2) else "0",
        "E3": str(int(self.e3[idx])) if idx < len(self.e3) else "0",
        "E4": str(int(self.e4[idx])) if idx < len(self.e4) else "0",
        "E5": str(int(self.e5[idx])) if idx < len(self.e5) else "0",
    }
```

#### 5.9 Sell Parity Test

**Required:** Build a validation test `tests/test_sell_precomputed_parity.py` that:
1. Runs the full pipeline with `process_algorithm_task()` using the new pre-computed sell path.
2. Compares the final formatted trade CSV against `tests/test_data/reference/final_trades_reference.csv`.
3. All 10 trade rows must match exactly: `Genome ID`, `Buy Signal`, `Stop Signal`, `Entry price`, `Exit price`, `Gain/Lose`.

**Extended validation (optional but recommended):** For every sell-day, compare `run_all_sell_conditions_fast()` output against `runAllSellConditions()` for the same inputs. This catches any per-condition discrepancy before it compounds into a trade-level difference.

```bash
docker cp tests/test_sell_precomputed_parity.py hk-algo-improve-algorithm-worker-1:/app/tests/
docker-compose exec algorithm-worker python tests/test_sell_precomputed_parity.py
```

**Gate:** Must print `PASS` with all 10 trade rows identical to reference.

### Files Modified

| File | Change |
|------|--------|
| `app/workers/algo_func/precomputed_indicators.py` | Add sell-side arrays, new helpers, fast sell methods |
| `tests/test_sell_precomputed_parity.py` | New: validate sell pre-computation against reference |

### Risks

- **SMA-TR vs Wilder ATR confusion:** S8 uses SMA-of-TR while S5/S7/S10/S16 use Wilder's ATR. Using the wrong array type would produce silent parity failures. The implementation MUST use `_sma_tr_full()` for S8 and `_atr_full()` for the others.
- **Rolling window offset errors:** S10 uses `data[-91:-1]` (excluding current bar) while S6 uses `data[-90:]` (including current bar). Off-by-one in the pre-computed array index would flip individual sell decisions. Each function's offset must be verified against the original.
- **S5 statefulness:** S5's stop-loss update depends on the previous stop_loss value chained across days. The ATR lookup is O(1) but the key-day logic and stop accumulation are inherently sequential. The pre-computed method only eliminates the ATR recomputation, not the sequential logic.
- **atr_s5 period bug:** The existing `atr_s5` uses hardcoded period 22 instead of `params.input_S5_atr_period` (default 20). Fixing this changes the pre-computed array values. Since S5 wasn't previously using the pre-computed array, this fix is safe — but must be validated.

---

## Phase 6 — Pre-Compute Energy Indicators (E1–E5)

### Goal

Replace the per-sell-day O(n) energy computation (`calculate_energy_indicators_last_16_days()`) with O(1) pre-computed array lookups. Energy computation is the single most expensive operation remaining after Phase 5, accounting for ~80% of sell-day cost.

**Expected speedup:** ~5–10× on sell-day cost when combined with Phase 5, bringing total pipeline to ~15–25s.

### Background

`calculate_energy_indicators_last_16_days()` (`get_code_energy.py`) computes five sub-indicators (E1–E5) for the last 16 trading days, sums them, and divides by 16 to produce `energy_score`. On each call it:

1. **Re-filters** the full stock/SPY dataset from `trade_day - 24 months` via `process_stock_data()` — O(n) date parsing and filtering.
2. **Recomputes RSI(10)** from scratch 16 times — once for each of the 16 lookback days, each time starting from index 0 of the filtered data.
3. **Recomputes StochRSI(10)** from each RSI result.
4. **Scans** rolling max/min windows (20-day high, 5-day range, 250-day high, 66-day slope, 33-day performance) 16 times.

Pre-computing E1–E5 as boolean arrays and `energy_score` as a rolling-sum array eliminates all this redundancy.

### Tasks

#### 6.1 Pre-Compute E1 Boolean Array

**E1 formula:** "New high in past 20 days AND close is in upper 35% of day's range."
```
E1[idx] = (high[idx] > max(high[idx-20 : idx]))   # 20-bar max EXCLUDING current bar
       AND (close[idx] > low[idx] + 0.65 * (high[idx] - low[idx]))
```

**Implementation:**
```python
# E1: note rolling_max_20 includes current bar, so use [idx-1] for "past 20 not including current"
self.e1 = np.zeros(self.n, dtype=np.int8)
for i in range(66, self.n):
    if i >= 20:
        max_high_20_excl = self.rolling_max_20[i - 1]  # max of highs[i-20 : i]
        cond_high = self.highs[i] > max_high_20_excl
        cond_close = self.closes[i] > self.lows[i] + 0.65 * (self.highs[i] - self.lows[i])
        if cond_high and cond_close:
            self.e1[i] = 1
```

**Edge case:** When `i < 20`, the original uses `max(high[max(0, idx-20) : idx])`. Since `idx >= 66` is required by the original code, this is always satisfied.

**Note on `rolling_max_20`:** The existing `self.rolling_max_20 = self._rolling_max(self.highs, 20)` computes `pd.Series(highs).rolling(20).max()`, where `rolling_max_20[i]` is `max(highs[i-19:i+1])` — the 20-bar max **including** the current bar. The original E1 code uses `max(high[idx-20:idx])` — the 20-bar max **excluding** the current bar. So:
- `rolling_max_20[i-1]` = `max(highs[i-20:i])` = what E1 needs.
- This is correct as long as `i >= 20`. For `i < 20`, `rolling_max_20[i-1]` is NaN, but the `i >= 66` guard prevents this.

#### 6.2 Pre-Compute E2 Boolean Array (RSI Convergence)

**E2 formula:** "StochRSI(10) > 0.5"

**Problem:** The original energy function computes RSI on data filtered to a 24-month window (`trade_day - 24 months`). `PrecomputedIndicators._rsi_full()` computes RSI on the **full dataset**. Since RSI uses Wilder's smoothing (an exponential moving average), the starting point affects all subsequent values.

**Resolution — convergence:** Wilder's smoothing has effective memory of ~3× period bars. For RSI(10), values converge within ~30 bars regardless of starting point. The 24-month window provides ~500 trading days of history before the 16-day evaluation window. After 500 bars of identical price data, the RSI values from full-dataset and 24-month-filtered starting points are identical to machine precision (~1e-14). The boolean threshold `> 0.5` is therefore safe.

**Implementation:** Use the existing `self.stochrsi_10` array directly:
```python
self.e2 = np.zeros(self.n, dtype=np.int8)
for i in range(66, self.n):
    if not np.isnan(self.stochrsi_10[i]) and self.stochrsi_10[i] > 0.5:
        self.e2[i] = 1
```

**Validation:** Run the energy parity sub-test (Task 6.6) which compares pre-computed E2 values against the original `calculate_energy_indicators_last_16_days()` output for every sell-day. If any discrepancy is found, fall back to computing RSI on the 24-month-filtered window (more complex but exact).

#### 6.3 Pre-Compute E3, E4, E5 Boolean Arrays

**E3 formula:** "Slope(Close, 66) > 0" — simplifies to `close[idx] > close[idx - 66]`:
```python
self.e3 = np.zeros(self.n, dtype=np.int8)
for i in range(66, self.n):
    if self.closes[i] > self.closes[i - 66]:
        self.e3[i] = 1
```

**E4 formula:** "33-day stock performance > 33-day SPY performance":
```python
# Use _calc_period_ratios for stock/SPY alignment
self.stock_ratio_33, self.spy_ratio_33 = self._calc_period_ratios(self.closes, self.spy_closes, 33)

self.e4 = np.zeros(self.n, dtype=np.int8)
for i in range(66, self.n):
    if (not np.isnan(self.stock_ratio_33[i]) and
        not np.isnan(self.spy_ratio_33[i]) and
        self.stock_ratio_33[i] > self.spy_ratio_33[i]):
        self.e4[i] = 1
```

**Note on E4 alignment:** The original uses `sdate_spy.index(sdate[idx])` for exact date string matching. `_calc_period_ratios()` uses exact string matching with bisect fallback. These produce identical results when the date exists in both series (which is common for stock and SPY on the same exchange). The bisect fallback handles missing dates gracefully. Verify numerically in the parity test.

**E5 formula:** Three sub-conditions: (1) close is in upper half of 5-day range, (2) close > close 5 days ago, (3) close within 7% of 250-day high:
```python
self.e5 = np.zeros(self.n, dtype=np.int8)
for i in range(66, self.n):
    if i < 5:
        continue
    min5 = self.rolling_min_low_5[i]     # min(low[i-4:i+1])
    max5 = self.rolling_max_high_5[i]     # max(high[i-4:i+1])
    max250 = self.rolling_max_250[i]      # max(high[i-249:i+1])
    
    if np.isnan(min5) or np.isnan(max5) or np.isnan(max250):
        continue
    
    cond1 = (self.closes[i] - min5) / (max5 - min5) > 0.5 if max5 != min5 else False
    cond2 = self.closes[i] > self.closes[i - 5]
    cond3 = (max250 - self.closes[i]) / max250 < 0.07 if max250 != 0 else False
    
    if cond1 and cond2 and cond3:
        self.e5[i] = 1
```

**Note:** The original E5 uses `highest(high, 250)` — `max(high[idx-249:idx+1])`. The pre-computed `rolling_max_250[i]` = `pd.Series(highs).rolling(250).max()[i]` = `max(highs[i-249:i+1])`. These are identical.

#### 6.4 Pre-Compute Energy Score as Rolling Sum

**Formula:** `energy_score[i] = sum(e1[j] + e2[j] + e3[j] + e4[j] + e5[j] for j in range(i-15, i+1)) / 16`

```python
# Total energy per day (0–5)
self.e_total = self.e1 + self.e2 + self.e3 + self.e4 + self.e5

# Rolling 16-day sum divided by 16
e_series = pd.Series(self.e_total.astype(np.float64))
self.energy_score = (e_series.rolling(16, min_periods=16).sum() / 16.0).values
```

The `get_s9_condition()` method becomes:
```python
def get_s9_condition(self, idx: int) -> bool:
    """S9: energy_score < threshold."""
    if idx >= self.n or np.isnan(self.energy_score[idx]):
        return False
    return self.energy_score[idx] < self.params.input_S9_energy_thresh
```

#### 6.5 Handle the `idx < 66` Guard

The original energy code skips E1–E5 computation when `idx < 66`, outputting `"N/A"` for all indicators. `"N/A"` values are excluded from the energy_score sum but the denominator remains 16. In practice, since the trading range starts at 2016-01-01 and the stock data extends back well before that, all evaluation-range indices are well above 66. The pre-computed arrays use `int8` with value 0 for indices < 66, matching the effect of excluding N/A (0 contributes nothing to the sum).

**Verify:** Assert that the first trading day in the evaluation range (START_DATE) maps to an index > 66 + 16 in the stock data array. If this assumption fails, the rolling sum guard (`min_periods=16`) produces NaN, and `get_s9_condition()` returns False, which is a safe fallback.

#### 6.6 Energy Parity Test

**Required:** Build a validation sub-test that compares pre-computed energy values against the original `calculate_energy_indicators_last_16_days()` for a set of representative sell-days.

```python
# For each sell-day (position_status == "I"):
original = calculate_energy_indicators_last_16_days(tradeday_str, filtered_code, filtered_spy)
precomp = precomputed.get_energy_data(code_end_idx)

# Compare:
assert original["E1"] == precomp["E1"], f"E1 mismatch at {tradeday_str}"
assert original["E2"] == precomp["E2"], f"E2 mismatch at {tradeday_str}"
assert original["E3"] == precomp["E3"], f"E3 mismatch at {tradeday_str}"
assert original["E4"] == precomp["E4"], f"E4 mismatch at {tradeday_str}"
assert original["E5"] == precomp["E5"], f"E5 mismatch at {tradeday_str}"
assert abs(original["energy_score"] - precomp["energy_score"]) < 1e-10, \
    f"energy_score mismatch at {tradeday_str}"
```

This test runs **alongside** the original path (not replacing it) to validate parity before switching. If E2 shows discrepancies due to RSI convergence, investigate and potentially implement the 24-month-windowed RSI fallback.

### Files Modified

| File | Change |
|------|--------|
| `app/workers/algo_func/precomputed_indicators.py` | Add E1–E5 arrays, energy_score, get_energy_data(), get_s9_condition() |
| `tests/` | Energy parity sub-test |

### Risks

- **RSI convergence edge case:** If a stock has very few trading days before START_DATE (less than ~30 bars between data start and the 24-month-filtered start), RSI convergence may not hold. For stock 3888 with data from ~2001, this is not an issue (~500+ bars before 2016). For stocks with shorter history, the parity test will catch any discrepancy.
- **E4 date alignment:** The original uses linear search (`sdate_spy.index(sdate[idx])`) while pre-computed uses bisect. For dates that exist in both series (normal case), results are identical. For missing dates, bisect maps to the previous date while the original would raise `ValueError` and return `E4 = "0"`. The pre-computed version should handle this correctly via the NaN guard.
- **Energy score precision:** The rolling sum uses float64 arithmetic. Cumulative floating-point rounding over 16 additions may produce differences at the ~1e-15 level. The sell threshold (`< 0.22`) has more than enough margin for this to be safe.

---

## Phase 7 — Integrate Pre-Computed Sell Path into Algorithm Worker

### Goal

Replace the sell-side call chain in `signals_for_the_period()` with the pre-computed methods from Phases 5 and 6. This is the integration phase that activates the pre-computed sell path in the main loop.

**Expected speedup:** This phase does not add new computation — it activates the arrays pre-computed in Phases 5–6. The full speedup from Phases 5+6+7 combined is ~7–10× on the sell path, bringing total pipeline time to ~15–25s per genome.

### Background

After Phases 5 and 6, `PrecomputedIndicators` contains all the sell-side arrays and fast methods. This phase wires them into the main loop, replacing:
- `calculate_energy_indicators_last_16_days()` with `precomputed.get_energy_data(code_end_idx)`
- `runAllSellConditions()` with `precomputed.run_all_sell_conditions_fast(code_end_idx, buy_idx, buy_price, stop_loss)`
- `filtered_code` / `filtered_spy` slicing with direct `code_end_idx` usage

### Tasks

#### 7.1 Update Sell Branch in `signals_for_the_period()`

**Current code** (algorithm_worker.py, sell branch):
```python
elif position_status == "I":
    # Energy needed for sell evaluation (S9)
    energy_data = calculate_energy_indicators_last_16_days(
        tradeday_str, filtered_code, filtered_spy
    )

    entry_date = latest_signal.get("entry_date")
    entry_price = latest_signal.get("entry_price")

    if latest_signal["next_open_action"] == "B":
        entry_date = tradeday_str
        entry_price = bar.open

    exit1 = to_float_or_none(latest_signal.get("exit1"))
    sellSignals = runAllSellConditions(
        filtered_code, filtered_spy, entry_date,
        to_float_or_none(entry_price), exit1, tradeday_str, params,
        energy_data=energy_data,
    )
    sell = isSell(sellSignals['conditions'])
    new_stop_loss = sellSignals['stop_loss']
```

**New code:**
```python
elif position_status == "I":
    entry_date = latest_signal.get("entry_date")
    entry_price = latest_signal.get("entry_price")

    if latest_signal["next_open_action"] == "B":
        entry_date = tradeday_str
        entry_price = bar.open

    # O(1) buy-index lookup via pre-computed date map
    buy_idx = precomputed.date_to_idx.get(entry_date, -1)
    exit1 = to_float_or_none(latest_signal.get("exit1"))

    # Pre-computed sell evaluation — replaces runAllSellConditions + energy
    sellSignals = precomputed.run_all_sell_conditions_fast(
        code_end_idx, buy_idx, to_float_or_none(entry_price), exit1
    )
    sell = isSell(sellSignals['conditions'])
    new_stop_loss = sellSignals['stop_loss']

    # Pre-computed energy data for CSV output
    energy_data = precomputed.get_energy_data(code_end_idx)
```

**Key changes:**
1. `calculate_energy_indicators_last_16_days()` call removed entirely.
2. `runAllSellConditions()` replaced with `precomputed.run_all_sell_conditions_fast()`.
3. `buy_idx` obtained via O(1) dict lookup instead of O(n) linear scan.
4. `filtered_code` / `filtered_spy` slicing no longer needed in the sell branch.

#### 7.2 Remove Unnecessary List Slicing

After this phase, neither the buy branch (Phase 1) nor the sell branch (Phase 7) use `filtered_code` or `filtered_spy`. The list slicing can be removed from the main loop:

```python
# REMOVE these lines:
filtered_spy = spy_data[:spy_end_idx + 1] if spy_end_idx >= 0 else []
filtered_code = code_data[:code_end_idx + 1] if code_end_idx >= 0 else []
```

Replace uses of `filtered_code[-1].close` with `code_data[code_end_idx].close` (direct index access, O(1)).

**Note:** Keep `spy_end_idx` and `code_end_idx` computation — they are used by pre-computed method calls.

#### 7.3 Backward Compatibility

Keep `sell_signals.py` and `get_code_energy.py` untouched. The original sell functions remain available as reference implementation and fallback. The import of `runAllSellConditions` and `isSell` in `algorithm_worker.py` can remain — `isSell()` is still used to evaluate the conditions dict from the fast path.

The `calculate_energy_indicators_last_16_days` import can be guarded or removed from the main loop, but should remain importable for tests.

#### 7.4 Full Pipeline Validation

**Required:** Run the existing sell parity test:

```bash
docker cp tests/test_sell_parity.py hk-algo-improve-algorithm-worker-1:/app/tests/
docker cp tests/test_data/reference/final_trades_reference.csv \
    hk-algo-improve-algorithm-worker-1:/app/tests/test_data/reference/
docker-compose exec algorithm-worker python tests/test_sell_parity.py
```

**Gate:** Must print `PASS` with all 10 trade rows identical to reference. Pipeline time should be ~15–25s (vs 133.6s before Phases 5–7).

**Performance benchmark:** Record `signals_for_the_period()` wall time. Expected breakdown:
- `precompute_indicators` (compute_all): ~1–2s (one-time, includes both buy and sell arrays)
- `main_signal_loop`: ~10–20s (all lookups are O(1), only CSV formatting and loop overhead remain)

### Files Modified

| File | Change |
|------|--------|
| `app/workers/algorithm_worker.py` | Replace sell branch with pre-computed path, remove list slicing |

### Risks

- **buy_idx not found:** If `entry_date` is not in `precomputed.date_to_idx`, `buy_idx` will be -1. All sell condition methods must handle `buy_idx == -1` by returning `False` (matching original behavior where buy_idx not found causes the function to return `False`).
- **Stop-loss chain:** S5's trailing stop-loss is stateful across days. `get_s5_condition()` receives `stop_loss` from the previous day's `latest_signal["exit1"]` and returns the updated value. This chain must be preserved exactly — the pre-computed ATR lookup replaces only the `atr(ohlcv, 20)[-1]` call, not the stop-loss accumulation logic.
- **Import order:** `precomputed.run_all_sell_conditions_fast()` must be called AFTER the buy branch updates `latest_signal` (which sets `entry_date` and `entry_price` on the buy day). The current code structure already ensures this (sell branch is `elif position_status == "I"`).

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
| 5 | All sell condition values identical for evaluated conditions | ≥2× speedup on sell-day cost |
| 6 | E1–E5 and energy_score match original for all sell-days | Energy computation eliminated from hot path |
| 7 | Final trade CSV identical to reference (10 rows) | Total pipeline ≤30s (from ~133s) |

---

## Estimated Impact

| Metric | Current | After Phases 1–3 | After Phases 5–7 |
|--------|---------|-------------------|-------------------|
| Per-genome time | ~312s | ~133s | ~15–25s |
| 37 genomes (8 cores) | 194 min | ~82 min | ~10–15 min |
| Buy-day bottleneck | O(n²) recalculation | O(1) pre-computed lookup | O(1) pre-computed lookup |
| Sell-day bottleneck | O(n) per-call ATR/energy | O(n) per-call ATR/energy | O(1) pre-computed lookup |
| Energy computation | O(n) × 16 per sell-day | Skipped on buy days | O(1) array lookup |
| CPU utilization | ~12.5% effective (GIL) | ~100% per core | ~100% per core |
