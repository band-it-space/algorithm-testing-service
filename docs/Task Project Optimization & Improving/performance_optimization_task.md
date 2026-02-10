# Performance Optimization — Implementation Task

> Step-by-step implementation guide based on [performance_optimization_requirements.md](performance_optimization_requirements.md).  
> Each phase is independent and merged sequentially.  
> **Golden rule:** input/output data must not change; indicator logic must not change.

---

## Pre-Work: Generate Reference Outputs ✅

Before touching any code, capture the current correct outputs for validation.

### Step 0.1 — Create Reference Data Generator

Created `tests/generate_reference.py` — generates:
- `tests/test_data/reference/buy_signals_reference.json` — per-day buy signals with all condition values
- `tests/test_data/reference/final_trades_reference.csv` — full pipeline output CSV

Also created `tests/validate_reference.py` — validates reference files are well-formed.

### Step 0.2 — Run the Generator

```bash
# Step 1: Generate reference data (run ONCE before any optimization)
python tests/generate_reference.py

# Step 2: Validate reference files
python tests/validate_reference.py
```

Verify files are created:
- `tests/test_data/reference/buy_signals_reference.json`
- `tests/test_data/reference/final_trades_reference.csv`

**Do NOT proceed until reference files exist and look correct.**

---

## Phase 1 — Enable PrecomputedIndicators for Buy Signals ✅

> **Goal:** Replace O(n²) per-day indicator recalculation with O(1) pre-computed array lookups.  
> **Expected speedup:** ~2–3× on total genome processing time.  
> **Files modified:** `precomputed_indicators.py`, `algorithm_worker.py`, new test file.

---

### Step 1.1 — Fix B18 Condition 8 (SMA of BBW)

**File:** `app/workers/algo_func/precomputed_indicators.py`

**Problem:** The precomputed `get_b18_condition()` (line ~857) uses a single BBW value (`bbw_now = self.bbw_b18[idx]`), but the original `condition8_b18()` in `buy_signals.py` (lines 71–115) computes the **SMA of the last Z BBW values** and compares that SMA against the BBW value Y days ago.

**Step 1.1.1 — Add `sma_bbw_b18` array in `compute_all()`**

Locate the B18 section in `compute_all()` (around line 200). After the line:
```python
self.bbw_b18 = self._calc_bbw(bb18_upper, bb18_lower, bb18_middle)
```

Add:
```python
# SMA of BBW for B18 condition 8 (matches original condition8_b18 which uses mean(recent_bbw[-Z:]))
b18_z = getattr(p, 'input_B18_Z', 10)
self.sma_bbw_b18 = self._sma_full(self.bbw_b18, b18_z)
```

**Step 1.1.2 — Fix `get_b18_condition()` condition 8 logic**

In `get_b18_condition()` (line ~855), replace the condition 8 block:

**Current code (lines 855–870):**
```python
b18_z = getattr(p, 'input_B18_Z', 10)
if idx < p.input_B18_history + b18_z:
    return False

bbw_now = self.bbw_b18[idx]
bbw_ago_idx = idx - p.input_B18_history

if bbw_ago_idx < 0 or np.isnan(bbw_now):
    return False

bbw_ago = self.bbw_b18[bbw_ago_idx]
if np.isnan(bbw_ago):
    return False

cond_bbw = bbw_now < bbw_ago * p.input_B18_bbw_ratio
```

**Replace with:**
```python
b18_z = getattr(p, 'input_B18_Z', 10)
if idx < p.input_B18_history + b18_z:
    return False

# Use SMA of last Z BBW values (matches original condition8_b18)
bbw_sma_now = self.sma_bbw_b18[idx]
bbw_ago_idx = idx - p.input_B18_history

if bbw_ago_idx < 0 or np.isnan(bbw_sma_now):
    return False

bbw_ago = self.bbw_b18[bbw_ago_idx]
if np.isnan(bbw_ago):
    return False

cond_bbw = bbw_sma_now < bbw_ago * p.input_B18_bbw_ratio
```

**Step 1.1.3 — Handle None-filtering discrepancy**

The original `condition8_b18()` filters out `None` BBW values with `recent_bbw = [x for x in bbw if x is not None]` before computing the SMA. The precomputed version uses NaN-padded arrays. This could cause index misalignment if any BBW values are NaN after the warm-up period.

Verify this by adding a debug check in the validation test (Step 1.3). If results diverge, the fix is to replace NaN BBW values with forward-filled values before computing `sma_bbw_b18`:

```python
# Only if discrepancy found:
bbw_clean = np.copy(self.bbw_b18)
# Forward-fill NaN values after initial warm-up
for i in range(1, len(bbw_clean)):
    if np.isnan(bbw_clean[i]):
        bbw_clean[i] = bbw_clean[i-1]
self.sma_bbw_b18 = self._sma_full(bbw_clean, b18_z)
```

---

### Step 1.2 — Verify B1 Rolling Max Window Alignment

**File:** `app/workers/algo_func/precomputed_indicators.py`

**Analysis required:** Confirm that `get_b1_condition()` line ~569:
```python
high52 = self.rolling_max_b1[idx - 1]
```
where `rolling_max_b1 = pd.Series(highs).rolling(lookback).max()`, matches the original `checkB1()` logic:
```python
max(highs[-(lookback+1):-1])
```

The precomputed `rolling_max_b1[idx - 1]` gives `max(highs[idx-lookback : idx])`, which is `lookback` values ending at `idx-1`. The original `max(highs[-(lookback+1):-1])` also gives `lookback` values ending one before the last. These should match when `idx` is the last element.

**Action:** Verify in the validation test (Step 1.3). If any B1 mismatch is found, check whether the `rolling()` window boundary includes/excludes the correct endpoints and adjust the index offset.

---

### Step 1.3 — Create Buy Signal Validation Test

**File:** Create `tests/test_precomputed_buy_parity.py`

```python
"""
Validates that PrecomputedIndicators produces identical buy signals
to the original runAllBuyConditions for every trading day.
"""
import asyncio, os, sys, json
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.workers.algo_func.get_db_data import get_stock_data_from_db, init_db_pool
from app.workers.algo_func.buy_signals import (
    runAllBuyConditions, isBuy, OHLCV as BuyOHLCV,
)
from app.workers.algo_func.precomputed_indicators import (
    PrecomputedIndicators, is_buy_fast, OHLCV as PrecompOHLCV,
)
from app.models.algorithm_models import AlgorithmParameters

STOCK = "3888"
START_DATE = os.getenv('OPTIMIZATION_START_DATE', '2016-01-01')
END_DATE = os.getenv('OPTIMIZATION_END_DATE', '2026-02-02')
STOP_LOSS_TOLERANCE = 0.0001


def ohlcv_buy_to_precomp(bars):
    """Convert buy_signals OHLCV to precomputed OHLCV if needed."""
    return [PrecompOHLCV(b.date, b.open, b.high, b.low, b.close, b.volume) for b in bars]


async def run_validation():
    await init_db_pool()
    params = AlgorithmParameters()

    code_raw = await get_stock_data_from_db(STOCK, END_DATE)
    spy_raw = await get_stock_data_from_db("2800", END_DATE)

    code_data = [BuyOHLCV(b["date"], b["open"], b["high"], b["low"], b["close"], b["volume"])
                 for b in code_raw]
    spy_data = [BuyOHLCV(b["date"], b["open"], b["high"], b["low"], b["close"], b["volume"])
                for b in spy_raw]

    # Build precomputed (using precomp OHLCV type)
    precomp_code = ohlcv_buy_to_precomp(code_data)
    precomp_spy = ohlcv_buy_to_precomp(spy_data)
    precomputed = PrecomputedIndicators(precomp_code, precomp_spy, params)
    precomputed.compute_all()

    # Build SPY date index for fast lookup
    spy_date_idx = {bar.date: i for i, bar in enumerate(spy_data)}
    spy_dates = [bar.date for bar in spy_data]

    mismatches = []
    total_compared = 0
    buy_condition_keys = ['B1', 'B3', 'B8', 'B9', 'B10', 'B11', 'B12', 'B13', 'B18']

    for idx in range(len(code_data)):
        date_str = code_data[idx].date
        if date_str < START_DATE:
            continue

        total_compared += 1

        # Original
        filtered_code = code_data[:idx + 1]
        spy_end = -1
        for si in range(len(spy_data) - 1, -1, -1):
            if spy_data[si].date <= date_str:
                spy_end = si
                break
        if spy_end < 0:
            continue
        filtered_spy = spy_data[:spy_end + 1]
        original = runAllBuyConditions(filtered_code, date_str, filtered_spy, params)

        # Precomputed
        precomp = precomputed.run_all_buy_conditions_fast(idx)

        # Compare boolean conditions
        for key in buy_condition_keys:
            orig_val = bool(original.get(key, False))
            pre_val = bool(precomp.get(key, False))
            if orig_val != pre_val:
                mismatches.append({
                    "idx": idx, "date": date_str, "key": key,
                    "original": orig_val, "precomputed": pre_val,
                })

        # Compare stopLoss with tolerance
        orig_sl = original.get('stopLoss')
        pre_sl = precomp.get('stopLoss')
        if orig_sl is not None and pre_sl is not None:
            if abs(float(orig_sl) - float(pre_sl)) > STOP_LOSS_TOLERANCE:
                mismatches.append({
                    "idx": idx, "date": date_str, "key": "stopLoss",
                    "original": orig_sl, "precomputed": pre_sl,
                })

    print(f"\n{'='*60}")
    print(f"Total days compared: {total_compared}")
    print(f"Mismatches found:    {len(mismatches)}")

    if mismatches:
        print(f"\nFirst 20 mismatches:")
        for m in mismatches[:20]:
            print(f"  Day {m['idx']} ({m['date']}): {m['key']} "
                  f"original={m['original']} precomputed={m['precomputed']}")
        print(f"\nFAIL — {len(mismatches)} mismatches detected")
        sys.exit(1)
    else:
        print("PASS — all buy signals match")


if __name__ == "__main__":
    asyncio.run(run_validation())
```

### Step 1.3.1 — Run the Test

```bash
python tests/test_precomputed_buy_parity.py
```

**Gate:** Must print `PASS — all buy signals match` with 0 mismatches before proceeding.

If mismatches appear:
- Check B18 mismatches first — apply the NaN-filtering fix from Step 1.1.3 if needed.
- Check B1 mismatches — adjust rolling max index offset if needed.
- Investigate any other condition mismatches individually.
- Re-run until 0 mismatches.

---

### Step 1.4 — Integrate PrecomputedIndicators into Algorithm Worker

**File:** `app/workers/algorithm_worker.py`

**Step 1.4.1 — Uncomment the import (line 17)**

Change:
```python
# from app.workers.algo_func.precomputed_indicators import PrecomputedIndicators, is_buy_fast  # Disabled for correctness verification
```
To:
```python
from app.workers.algo_func.precomputed_indicators import PrecomputedIndicators, is_buy_fast
```

**Step 1.4.2 — Activate precomputation in `signals_for_the_period()`**

Locate the commented-out block (lines ~228–231):
```python
# NOTE: Pre-computed indicators disabled for correctness verification
# Using original buy_signals.py functions instead
# with TimingContext("precompute_indicators"):
#     precomputed = PrecomputedIndicators(code_data, spy_data, params)
#     precomputed.compute_all()
```

Replace with:
```python
# Pre-compute all indicators once for O(1) lookups
with TimingContext("precompute_indicators"):
    from app.workers.algo_func.precomputed_indicators import OHLCV as PrecompOHLCV
    precomp_code = [PrecompOHLCV(b.date, b.open, b.high, b.low, b.close, b.volume) for b in code_data]
    precomp_spy = [PrecompOHLCV(b.date, b.open, b.high, b.low, b.close, b.volume) for b in spy_data]
    precomputed = PrecomputedIndicators(precomp_code, precomp_spy, params)
    precomputed.compute_all()
```

> **Note on OHLCV type compatibility:** `algorithm_worker.py` imports `OHLCV` from `buy_signals.py`, while `PrecomputedIndicators` defines its own `OHLCV` in `precomputed_indicators.py`. Both are dataclasses with identical fields (`date`, `open`, `high`, `low`, `close`, `volume`). We explicitly convert to ensure type safety. If duck-typing is confirmed safe (both use `.date`, `.open`, etc.), the conversion can be removed in a follow-up.

**Step 1.4.3 — Replace buy signal computation in the "F" branch**

In the `position_status == "F"` branch (around line 262), replace:
```python
buySignals = runAllBuyConditions(filtered_code, tradeday_str, filtered_spy, params)
```
With:
```python
buySignals = precomputed.run_all_buy_conditions_fast(code_end_idx)
```

And replace:
```python
buy = isBuy(buySignals)
```
With:
```python
buy = is_buy_fast(buySignals)
```

The `code_end_idx` variable (computed on line ~258 via `_find_end_index()`) is the index into the full `code_data` array — this is exactly what `PrecomputedIndicators` expects.

**Step 1.4.4 — Verify the sell path is unchanged**

The `position_status == "I"` branch must remain untouched in this phase. Confirm that `runAllSellConditions()`, `isSell()`, and the sell-related `latest_signal` updates are not modified.

---

### Step 1.5 — End-to-End Validation

**Step 1.5.1 — Run the full pipeline on stock 3888, genome G_000**

```bash
# Ensure the same environment variables as production
export OPTIMIZATION_START_DATE=2016-01-01
export OPTIMIZATION_END_DATE=2026-02-02

python -c "
import asyncio
from app.workers.algorithm_worker import process_algorithm_task

task = {
    'task_id': 'validation_phase1',
    'stock': '3888',
    'genome_id': 'G_000',
    'parameters': {},
}
asyncio.run(process_algorithm_task(task))
"
```

**Step 1.5.2 — Compare output against reference**

```python
import csv

def load_csv(path):
    with open(path, 'r', encoding='utf-8') as f:
        return list(csv.DictReader(f))

ref = load_csv("tests/test_data/reference/final_trades_reference.csv")
new = load_csv("data/3888_G_000.csv")

assert len(ref) == len(new), f"Row count differs: {len(ref)} vs {len(new)}"
for i, (r, n) in enumerate(zip(ref, new)):
    for col in r:
        assert r[col] == n[col], f"Row {i}, col '{col}': '{r[col]}' vs '{n[col]}'"
print("PASS — final trades CSV matches reference")
```

**Step 1.5.3 — Benchmark**

Compare `signals_for_the_period` wall time (logged by `PerformanceProfiler`) before and after.
- Before: ~312s per genome (baseline)
- Expected after Phase 1: ~100–160s per genome (buy path ~50x faster, sell path unchanged)

**Gate:** Output CSV must match exactly. Speedup must be ≥1.5×.

---

## Phase 2 — Optimize Sell Signal Path ✅

> **Goal:** Eliminate redundant sorting, duplicate energy computation, and add short-circuit evaluation.  
> **Expected speedup:** ~1.5–2.5× additional on total genome time.  
> **Files modified:** `sell_signals.py`, `algorithm_worker.py`, new test file.

---

### Step 2.1 — Remove Redundant Sorting

**File:** `app/workers/algo_func/sell_signals.py`

The OHLCV data is already sorted chronologically when it enters sell conditions (sliced from `code_data[:code_end_idx + 1]` which originates from API data sorted by date in `get_db_data.py`).

**Step 2.1.1 — Remove sort calls in 10 functions**

In each function below, find the line `data = sorted(ohlcv, key=lambda x: to_ts(x.date))` and replace it with `data = ohlcv`:

| Function | Approximate line | Change |
|----------|-----------------|--------|
| `s4()` | line ~119 | `data = sorted(...)` → `data = ohlcv` |
| `s6()` | line ~290 | `data = sorted(...)` → `data = ohlcv` |
| `s7()` | line ~354 | `data = sorted(...)` → `data = ohlcv` |
| `s8()` | line ~392 | `data = sorted(...)` → `data = ohlcv` |
| `s10()` | line ~447 | `data = sorted(...)` → `data = ohlcv` |
| `s13()` | line ~505 | `data = sorted(...)` → `data = ohlcv` |
| `s14()` | line ~540 (both stock and SPY) | `asset = sorted(...)` → `asset = ohlcv` and `hsi = sorted(...)` → `hsi = hsi_ohlcv` |
| `s15()` | line ~597 | `data = sorted(...)` → `data = ohlcv` |
| `s16()` | line ~632 | `data = sorted(...)` → `data = ohlcv` |
| `s17()` | line ~671 | `data = sorted(...)` → `data = ohlcv` |

**Step 2.1.2 — Add a safety assertion**

At the top of `runAllSellConditions()` (line ~727), add a lightweight sort-order check:

```python
def runAllSellConditions(ohlcv, spy_data, buy_date, buy_price, stop_loss, trade_date,
                         params: AlgorithmParameters = None, energy_data=None):
    if params is None:
        params = AlgorithmParameters()

    # Safety: verify data is sorted (check first and last only — O(1))
    if len(ohlcv) >= 2:
        assert ohlcv[0].date <= ohlcv[-1].date, \
            f"OHLCV not sorted: first={ohlcv[0].date}, last={ohlcv[-1].date}"

    # ... rest of function
```

---

### Step 2.2 — Eliminate Duplicate Energy Computation in S9

**Step 2.2.1 — Modify `s9()` to accept pre-computed energy data**

**File:** `app/workers/algo_func/sell_signals.py`

Change the `s9()` signature and body (around line ~430):

**Current:**
```python
def s9(trade_date, ohlcv, spy_data, params: AlgorithmParameters = None):
    if params is None:
        params = AlgorithmParameters()

    energy_thresh = params.input_S9_energy_thresh

    energy_level = calculate_energy_indicators_last_16_days(trade_date, ohlcv, spy_data)
    return energy_level["energy_score"] < energy_thresh
```

**Replace with:**
```python
def s9(trade_date, ohlcv, spy_data, params: AlgorithmParameters = None, energy_data=None):
    if params is None:
        params = AlgorithmParameters()

    energy_thresh = params.input_S9_energy_thresh

    if energy_data is None:
        energy_data = calculate_energy_indicators_last_16_days(trade_date, ohlcv, spy_data)

    return energy_data["energy_score"] < energy_thresh
```

**Step 2.2.2 — Update `runAllSellConditions()` to accept and pass `energy_data`**

Change the signature (around line ~727):
```python
def runAllSellConditions(ohlcv, spy_data, buy_date, buy_price, stop_loss, trade_date,
                         params: AlgorithmParameters = None, energy_data=None):
```

Update the S9 call inside the function:
```python
"S9": s9(trade_date, ohlcv, spy_data, params, energy_data=energy_data),
```

**Step 2.2.3 — Pass `energy_data` from algorithm worker**

**File:** `app/workers/algorithm_worker.py`

In the `position_status == "I"` branch (around line ~320), update the `runAllSellConditions` call:

**Current:**
```python
sellSignals = runAllSellConditions(
    filtered_code,
    filtered_spy,
    entry_date,
    to_float_or_none(entry_price),
    exit1,
    tradeday_str,
    params,
)
```

**Replace with:**
```python
sellSignals = runAllSellConditions(
    filtered_code,
    filtered_spy,
    entry_date,
    to_float_or_none(entry_price),
    exit1,
    tradeday_str,
    params,
    energy_data=energy_data,
)
```

The `energy_data` variable is already computed earlier in the loop (around line ~263) for every day.

---

### Step 2.3 — Short-Circuit Sell Evaluation

**File:** `app/workers/algo_func/sell_signals.py`

**Step 2.3.1 — Replace `runAllSellConditions()` body**

Replace the entire `runAllSellConditions()` function (lines ~727–752):

**Current:**
```python
def runAllSellConditions(ohlcv, spy_data, buy_date, buy_price, stop_loss, trade_date,
                         params: AlgorithmParameters = None):
    if params is None:
        params = AlgorithmParameters()

    s5_exit, new_stop = s5(ohlcv, buy_date, buy_price, stop_loss, trade_date, params)

    conditions = {
        "S1": exit_by_stop_loss(ohlcv, stop_loss, params),
        "S4": s4(ohlcv, buy_date, buy_price, params),
        "S5": s5_exit,
        "S6": s6(ohlcv, buy_date, trade_date, params),
        "S7": s7(ohlcv, buy_date, buy_price, params),
        "S8": s8(ohlcv, buy_date, buy_price, params),
        "S9": s9(trade_date, ohlcv, spy_data, params),
        "S10": s10(ohlcv, buy_date, buy_price, params),
        "S11": s11(ohlcv, buy_date, buy_price, params),
        "S12": s12(ohlcv, buy_date, buy_price, params),
        "S13": s13(ohlcv, buy_date, buy_price, params),
        "S14": s14(ohlcv, spy_data, buy_date, buy_price, params),
        "S15": s15(ohlcv, buy_date, buy_price, params),
        "S16": s16(ohlcv, buy_date, params),
        "S17": s17(ohlcv, buy_date, buy_price, params),
    }

    return {"conditions": conditions, "stop_loss": new_stop}
```

**Replace with:**
```python
def runAllSellConditions(ohlcv, spy_data, buy_date, buy_price, stop_loss, trade_date,
                         params: AlgorithmParameters = None, energy_data=None):
    if params is None:
        params = AlgorithmParameters()

    # Safety: verify data is sorted (O(1) check)
    if len(ohlcv) >= 2:
        assert ohlcv[0].date <= ohlcv[-1].date, \
            f"OHLCV not sorted: first={ohlcv[0].date}, last={ohlcv[-1].date}"

    # S5 MUST always run — it returns the updated stop_loss value
    s5_exit, new_stop = s5(ohlcv, buy_date, buy_price, stop_loss, trade_date, params)

    # Ordered cheapest-to-most-expensive for early exit
    ordered_checks = [
        ("S1",  lambda: exit_by_stop_loss(ohlcv, stop_loss, params)),
        ("S15", lambda: s15(ohlcv, buy_date, buy_price, params)),
        ("S5",  lambda: s5_exit),
        ("S7",  lambda: s7(ohlcv, buy_date, buy_price, params)),
        ("S9",  lambda: s9(trade_date, ohlcv, spy_data, params, energy_data=energy_data)),
        ("S17", lambda: s17(ohlcv, buy_date, buy_price, params)),
        ("S13", lambda: s13(ohlcv, buy_date, buy_price, params)),
        ("S10", lambda: s10(ohlcv, buy_date, buy_price, params)),
        ("S8",  lambda: s8(ohlcv, buy_date, buy_price, params)),
        ("S6",  lambda: s6(ohlcv, buy_date, trade_date, params)),
        ("S4",  lambda: s4(ohlcv, buy_date, buy_price, params)),
        ("S16", lambda: s16(ohlcv, buy_date, params)),
        ("S11", lambda: s11(ohlcv, buy_date, buy_price, params)),
        ("S12", lambda: s12(ohlcv, buy_date, buy_price, params)),
        ("S14", lambda: s14(ohlcv, spy_data, buy_date, buy_price, params)),
    ]

    conditions = {}
    for key, check_fn in ordered_checks:
        result = check_fn()
        conditions[key] = result
        if result:
            # Fill remaining conditions as False (not evaluated)
            for remaining_key, _ in ordered_checks:
                if remaining_key not in conditions:
                    conditions[remaining_key] = False
            break

    return {"conditions": conditions, "stop_loss": new_stop}
```

**Important notes:**
- `s5()` is called **before** the loop because it returns `new_stop` (updated stop-loss) which is needed regardless of sell decision.
- `isSell()` remains unchanged — it uses OR logic so the first `True` is sufficient.
- Unevaluated conditions are set to `False`. This is safe because `isSell()` is the only consumer of the conditions dict and the OR-chain short-circuits.

---

### Step 2.4 — Create Sell Signal Validation Test

**File:** Create `tests/test_sell_parity.py`

```python
"""
Validates that the optimized sell path produces identical isSell() decisions
to the original for a full pipeline run.
"""
import asyncio, os, sys, csv
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.workers.algorithm_worker import process_algorithm_task
from app.services.file_service import FileService

STOCK = "3888"
GENOME = "G_000"
REF_PATH = os.path.join("tests", "test_data", "reference", "final_trades_reference.csv")


def load_csv(path):
    with open(path, 'r', encoding='utf-8') as f:
        return list(csv.DictReader(f))


async def run_validation():
    task = {
        'task_id': 'validation_phase2',
        'stock': STOCK,
        'genome_id': GENOME,
        'parameters': {},
    }
    await process_algorithm_task(task)

    ref = load_csv(REF_PATH)
    new = load_csv(f"data/{STOCK}_{GENOME}.csv")

    assert len(ref) == len(new), f"Row count differs: {len(ref)} vs {len(new)}"
    for i, (r, n) in enumerate(zip(ref, new)):
        for col in r:
            assert r[col] == n[col], f"Row {i}, col '{col}': '{r[col]}' vs '{n[col]}'"

    print("PASS — sell path optimization produces identical output")


if __name__ == "__main__":
    asyncio.run(run_validation())
```

Run:
```bash
python tests/test_sell_parity.py
```

**Gate:** Must print `PASS`. All trade rows must be identical to the Phase 1 reference.

---

## Phase 3 — Eliminate Per-Day Overhead in the Main Loop

> **Goal:** Remove redundant datetime parsing, duplicate data fetches, triple data conversion.  
> **Expected speedup:** ~1.3–1.5× additional on total genome time.  
> **Files modified:** `algorithm_worker.py`, `get_db_data.py`.

---

### Step 3.1 — Replace `pd.to_datetime()` in Inner Loop

**File:** `app/workers/algorithm_worker.py`

**Step 3.1.1 — Fix `latest_date` parsing (line ~241)**

Change:
```python
latest_date = pd.to_datetime(latest_signal["tradeday"]).tz_localize(None)
```
To:
```python
_raw_td = str(latest_signal["tradeday"]).split("T")[0]
latest_date = datetime.strptime(_raw_td, "%Y-%m-%d")
```

**Step 3.1.2 — Fix the filter loop (lines ~244–247)**

Change:
```python
for bar in code_data:
    bar_date = pd.to_datetime(bar.date)
    if bar_date > latest_date:
        filtered_code_data.append(bar)
```
To:
```python
for bar in code_data:
    bar_date = datetime.strptime(bar.date, "%Y-%m-%d")
    if bar_date > latest_date:
        filtered_code_data.append(bar)
```

**Step 3.1.3 — Fix the main loop tradeday parsing (line ~253)**

Change:
```python
tradeday = pd.to_datetime(bar.date).tz_localize(None)
tradeday_str = tradeday.strftime("%Y-%m-%d")
```
To:
```python
tradeday_str = bar.date  # Already in "YYYY-MM-DD" format
```

Then update all uses of `tradeday` (the datetime object) in the same loop. Search for every place `tradeday` (not `tradeday_str`) is used and replace with the string form. The main uses are:
- `result["tradeday"] = tradeday` → change to `result["tradeday"] = tradeday_str`
- `latest_signal["entry_date"] = tradeday` → change to `latest_signal["entry_date"] = tradeday_str`

If any downstream code needs a datetime object rather than a string, create it lazily:
```python
# Only convert if truly needed (e.g., for date arithmetic)
# tradeday_dt = datetime.strptime(tradeday_str, "%Y-%m-%d")
```

---

### Step 3.2 — Eliminate Redundant Data Fetch

**File:** `app/workers/algorithm_worker.py`

**Step 3.2.1 — Fetch data once in `process_algorithm_task()`**

In `process_algorithm_task()` (around line ~100), before calling `get_data_and_save_to_csv`, add:

```python
# Fetch data once — reuse across all steps
with TimingContext("fetch_all_data"):
    code_data_raw = await get_stock_data_from_db(stock_code, END_DATE)
    spy_data_raw = await get_stock_data_from_db("2800", END_DATE)
```

**Step 3.2.2 — Update `get_data_and_save_to_csv()` signature**

Add `code_data_raw=None` parameter:
```python
async def get_data_and_save_to_csv(code: str, trade_date: str, genome_id: str = "G_000",
                                    file_service: "FileService" = None,
                                    file_name: str = None,
                                    code_data_raw=None):
```

Replace the internal fetch:
```python
# Current:
code_data_raw = await get_stock_data_from_db(code, END_DATE)
# Replace with:
if code_data_raw is None:
    code_data_raw = await get_stock_data_from_db(code, END_DATE)
```

**Step 3.2.3 — Update `signals_for_the_period()` signature**

Add `code_data_raw=None, spy_data_raw=None` parameters:
```python
async def signals_for_the_period(code, trade_date, params: AlgorithmParameters = None,
                                  genome_id: str = "G_000", file_name: str = None,
                                  code_data_raw=None, spy_data_raw=None):
```

Replace the internal fetches:
```python
# Current:
with TimingContext("fetch_spy_data"):
    spy_data_raw = await get_stock_data_from_db("2800", trade_date)

with TimingContext("fetch_code_data"):
    code_data_raw = await get_stock_data_from_db(code, trade_date)

# Replace with:
if spy_data_raw is None:
    with TimingContext("fetch_spy_data"):
        spy_data_raw = await get_stock_data_from_db("2800", trade_date)

if code_data_raw is None:
    with TimingContext("fetch_code_data"):
        code_data_raw = await get_stock_data_from_db(code, trade_date)
```

**Step 3.2.4 — Update callers in `process_algorithm_task()`**

```python
await get_data_and_save_to_csv(stock_code, START_DATE, genome_id,
                                file_name=genome_file_name,
                                code_data_raw=code_data_raw)

await signals_for_the_period(stock_code, END_DATE, params, genome_id,
                              file_name=genome_file_name,
                              code_data_raw=code_data_raw,
                              spy_data_raw=spy_data_raw)
```

---

### Step 3.3 — Eliminate Triple Data Conversion on Cache Hit

**File:** `app/workers/algo_func/get_db_data.py`

**Problem flow on cache hit:**
1. Cache stores: `List[OHLCV]` objects
2. `get_stock_data_from_db()` converts: `OHLCV → dict` (lines ~108–120)
3. `signals_for_the_period()` converts back: `dict → OHLCV` (lines ~209–216)

**Step 3.3.1 — Add `return_ohlcv` parameter**

```python
async def get_stock_data_from_db(code: str, end_date: str | None = None, return_ohlcv: bool = False):
    """Отримати дані про акції з API з підтримкою кешування."""
    cache = _get_cache_service()

    if cache:
        try:
            from app.services.data_cache_service import OHLCV
            cached_data = cache.get_stock_data(code, end_date=end_date)

            if cached_data is not None:
                logger.debug(f"Cache HIT for stock {code}")
                if return_ohlcv:
                    return cached_data  # Return OHLCV objects directly
                return [
                    {
                        "date": bar.date,
                        "time": "00:00:00",
                        "open": bar.open,
                        "high": bar.high,
                        "low": bar.low,
                        "close": bar.close,
                        "volume": int(bar.volume),
                    }
                    for bar in cached_data
                ]
        except Exception as e:
            logger.warning(f"Cache read error for {code}: {e}")

    # ... rest unchanged (API fetch returns dicts, which is fine)
```

**Step 3.3.2 — Use `return_ohlcv=True` in algorithm worker**

In `process_algorithm_task()` or `signals_for_the_period()`, when fetching data that will be converted to OHLCV anyway, use the new parameter:

```python
code_data_raw = await get_stock_data_from_db(stock_code, END_DATE, return_ohlcv=True)
```

Then in `signals_for_the_period()`, check the type before converting:

```python
# Convert to OHLCV objects only if needed (might already be OHLCV from cache)
with TimingContext("convert_to_ohlcv"):
    if code_data_raw and isinstance(code_data_raw[0], dict):
        code_data = [
            OHLCV(bar["date"], bar["open"], bar["high"], bar["low"], bar["close"], bar["volume"])
            for bar in code_data_raw
        ]
    else:
        # Already OHLCV objects from cache — use directly
        code_data = code_data_raw

    if spy_data_raw and isinstance(spy_data_raw[0], dict):
        spy_data = [
            OHLCV(bar["date"], bar["open"], bar["high"], bar["low"], bar["close"], bar["volume"])
            for bar in spy_data_raw
        ]
    else:
        spy_data = spy_data_raw
```

> **Important:** Verify that the `OHLCV` from `data_cache_service.py` has the same fields as the `OHLCV` from `buy_signals.py`. If they differ (different classes, same fields), either use duck typing (both have `.date`, `.open`, etc.) or convert once from cache OHLCV to buy_signals OHLCV.

---

### Step 3.4 — Pass Seed Row Directly (Skip CSV Re-Read)

**File:** `app/workers/algorithm_worker.py`

**Step 3.4.1 — Return seed row from `get_data_and_save_to_csv()`**

`get_data_and_save_to_csv()` already returns `csv_row` on success. Capture it:

```python
# In process_algorithm_task():
seed_row = await get_data_and_save_to_csv(stock_code, START_DATE, genome_id,
                                           file_name=genome_file_name,
                                           code_data_raw=code_data_raw)
```

**Step 3.4.2 — Add `initial_signal` parameter to `signals_for_the_period()`**

```python
async def signals_for_the_period(code, trade_date, params=None,
                                  genome_id="G_000", file_name=None,
                                  code_data_raw=None, spy_data_raw=None,
                                  initial_signal=None):
```

Replace:
```python
latest_signal = await get_latest_signal(csv_file_name, genome_id=genome_id)

if latest_signal is None:
    print(f"Немає сигналу для коду {code}, genome: {genome_id}")
    latest_signal = await get_data_and_save_to_csv(code, trade_date, genome_id, file_name=csv_file_name)
```

With:
```python
if initial_signal is not None:
    latest_signal = initial_signal
else:
    latest_signal = await get_latest_signal(csv_file_name, genome_id=genome_id)
    if latest_signal is None:
        print(f"Немає сигналу для коду {code}, genome: {genome_id}")
        latest_signal = await get_data_and_save_to_csv(code, trade_date, genome_id, file_name=csv_file_name)
```

**Step 3.4.3 — Pass seed row in `process_algorithm_task()`**

```python
await signals_for_the_period(stock_code, END_DATE, params, genome_id,
                              file_name=genome_file_name,
                              code_data_raw=code_data_raw,
                              spy_data_raw=spy_data_raw,
                              initial_signal=seed_row)
```

---

### Step 3.5 — End-to-End Validation

Re-run the Phase 2 validation test (same command):
```bash
python tests/test_sell_parity.py
```

**Gate:** Must still produce `PASS`. Output CSV identical to reference.

Benchmark improvement: compare `signals_for_the_period` wall time.
- Expected: measurable improvement from eliminated parsing/fetching overhead.

---

## Phase 4 — Fix Concurrency Model

> **Goal:** Eliminate GIL contention, remove per-job event loop overhead.  
> **Expected speedup:** Near-linear CPU scaling.  
> **Files modified:** `concurrent_worker.py`, environment config.

---

### Step 4.1 — Set Threads to 1 (Config Change)

**Step 4.1.1 — Update environment variables**

In `docker-compose.yml` (or `.env` file), set:
```yaml
environment:
  ALGORITHM_WORKER_COUNT: 8        # Match CPU core count
  ALGORITHM_CONCURRENT_TASKS: 1    # Single thread per worker = no GIL contention
```

**Why this works:** Each worker is a separate process with its own GIL. With `CONCURRENT_TASKS=1`, each process runs one genome at a time at full CPU speed. With 8 workers, 8 genomes process in parallel.

**Step 4.1.2 — Verify**

Run the full optimization batch and confirm:
- Each worker process uses ~100% of one CPU core
- No thread contention visible in logs (no interleaved output from the same worker)
- Total throughput is better than 8 workers × 5 threads

---

### Step 4.2 — Reuse Event Loop Per Worker

**File:** `app/workers/concurrent_worker.py`

**Step 4.2.1 — Add persistent event loop**

Replace `process_job()` method:

**Current (lines ~36–55):**
```python
def process_job(self, job: Job):
    """Process a single job, handling both sync and async functions."""
    try:
        self.logger.info(f"Worker {self.worker_id}: Starting job {job.id}")
        func = job.func
        args = job.args
        kwargs = job.kwargs

        if inspect.iscoroutinefunction(func):
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(func(*args, **kwargs))
            finally:
                loop.close()
        else:
            result = func(*args, **kwargs)

        job.set_status('finished')
        self.logger.info(f"Worker {self.worker_id}: Job {job.id} completed")
        return job.id, "success", None
    except Exception as e:
        self.logger.error(f"Worker {self.worker_id}: Job {job.id} failed: {e}")
        job.set_status('failed')
        return job.id, "failed", str(e)
```

**Replace with:**
```python
def _get_loop(self):
    """Get or create a reusable event loop for this worker."""
    if not hasattr(self, '_loop') or self._loop is None or self._loop.is_closed():
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
    return self._loop

def process_job(self, job: Job):
    """Process a single job, handling both sync and async functions."""
    try:
        self.logger.info(f"Worker {self.worker_id}: Starting job {job.id}")
        func = job.func
        args = job.args
        kwargs = job.kwargs

        if inspect.iscoroutinefunction(func):
            loop = self._get_loop()
            result = loop.run_until_complete(func(*args, **kwargs))
        else:
            result = func(*args, **kwargs)

        job.set_status('finished')
        self.logger.info(f"Worker {self.worker_id}: Job {job.id} completed")
        return job.id, "success", None
    except Exception as e:
        self.logger.error(f"Worker {self.worker_id}: Job {job.id} failed: {e}")
        job.set_status('failed')
        return job.id, "failed", str(e)
```

---

### Step 4.3 — Reduce Polling Interval

**File:** `app/workers/concurrent_worker.py`

**Step 4.3.1 — Optimize the work loop polling**

In the `work()` method (around line ~101), change the active polling sleep:

```python
# Current:
time.sleep(0.1)

# Replace with:
time.sleep(0.01)
```

The idle sleep (`time.sleep(0.5)` on line ~95) stays as-is — it only triggers when no jobs are queued.

---

### Step 4.4 — End-to-End Validation

**Step 4.4.1 — Run a single-genome sanity check**

```bash
python tests/test_sell_parity.py
```

**Gate:** Output CSV must still match reference.

**Step 4.4.2 — Run full batch benchmark**

Run all 37 genomes with the new config:
- `ALGORITHM_WORKER_COUNT=8`, `ALGORITHM_CONCURRENT_TASKS=1`
- Compare total batch time vs baseline (194 minutes)

**Step 4.4.3 — Monitor resources**

```bash
docker stats
```

Verify:
- Each worker process uses ~100% CPU (one core)
- Total memory stays within bounds (~2–4 GB expected with 8 workers)
- No Redis connection errors

---

## Summary: Expected Performance After All Phases

| Phase | Change | Speedup Factor |
|-------|--------|---------------|
| 1 — PrecomputedIndicators | Buy path: O(n²) → O(n) precompute + O(1) lookup | ~2–3× |
| 2 — Sell optimization | No sorting, short-circuit, no duplicate energy | ~1.5–2.5× |
| 3 — Loop overhead | No pd.to_datetime, no redundant fetch, no triple convert | ~1.3–1.5× |
| 4 — Concurrency fix | True CPU parallelism per core | ~1× on single genome, better batch throughput |

**Cumulative estimate:**
- Per-genome: ~312s → ~15–30s
- 37 genomes on 8 cores: ~194 min → ~10–20 min

---

## Quick Reference: Files Changed Per Phase

| Phase | Files | Type of Change |
|-------|-------|----------------|
| 1 | `precomputed_indicators.py` | Fix B18 cond8 (add `sma_bbw_b18` array) |
| 1 | `algorithm_worker.py` | Uncomment import, activate precomputed buy path |
| 1 | `tests/test_precomputed_buy_parity.py` | New validation test |
| 2 | `sell_signals.py` | Remove 10 sorts, add `energy_data` param, short-circuit |
| 2 | `algorithm_worker.py` | Pass `energy_data` to `runAllSellConditions` |
| 2 | `tests/test_sell_parity.py` | New validation test |
| 3 | `algorithm_worker.py` | Replace `pd.to_datetime`, pass raw data, pass seed row |
| 3 | `get_db_data.py` | Add `return_ohlcv` parameter |
| 4 | `concurrent_worker.py` | Reuse event loop, reduce polling |
| 4 | `docker-compose.yml` / env | `CONCURRENT_TASKS=1`, tune `WORKER_COUNT` |

---

## Rollback Instructions

Each phase modifies a small set of files. To rollback:

1. **Phase 1:** Re-comment the import on line 17 of `algorithm_worker.py`, re-comment the precomputed init block, restore `runAllBuyConditions()` call in the "F" branch.
2. **Phase 2:** Revert `runAllSellConditions()` to the non-short-circuit version, restore `sorted()` calls, remove `energy_data` parameter.
3. **Phase 3:** Restore `pd.to_datetime()` calls, remove `return_ohlcv` parameter, remove data pass-through parameters.
4. **Phase 4:** Set `ALGORITHM_CONCURRENT_TASKS` back to 5, restore per-job event loop creation.

Use `git stash` or feature branches per phase for clean rollback points.
