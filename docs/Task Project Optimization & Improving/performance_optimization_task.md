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

## Phase 3 — Eliminate Per-Day Overhead in the Main Loop ✅

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

## Phase 5 — Pre-Compute Sell-Side ATR and Rolling Window Arrays ✅

> **Goal:** Replace per-sell-day O(n) ATR, SMA-TR, and rolling-window recomputations with O(1) pre-computed array lookups.  
> **Expected speedup:** ~2–3× on total genome time (from ~133s to ~40–60s).  
> **Files modified:** `precomputed_indicators.py`, new test file.

---

### Step 5.1 — Fix `atr_s5` Period Bug

**File:** `app/workers/algo_func/precomputed_indicators.py`

**Problem:** `compute_all()` computes `self.atr_s5` with hardcoded period 22:
```python
self.atr_s5 = self._atr_full(self.highs, self.lows, self.closes, 22)
```
But `s5()` in `sell_signals.py` (line ~163) uses `params.input_S5_atr_period` which defaults to **20**. This will cause a parity failure when the pre-computed array replaces the per-call `atr()`.

**Step 5.1.1 — Replace the hardcoded period**

In `compute_all()`, locate the S5 ATR line (around line 222) and change:

```python
# === S5 ATR ===
self.atr_s5 = self._atr_full(self.highs, self.lows, self.closes, 22)
```

To:

```python
# === S5 ATR (Wilder's smoothing) ===
s5_atr_period = getattr(p, 'input_S5_atr_period', 20)
self.atr_s5 = self._atr_full(self.highs, self.lows, self.closes, s5_atr_period)
```

**Note:** Since S5 didn't previously use `self.atr_s5`, this change doesn't affect any existing code path. It only becomes relevant when the fast S5 method (Step 5.8) uses this array.

---

### Step 5.2 — Add All Sell-Side ATR Arrays (Wilder's Smoothing)

**File:** `app/workers/algo_func/precomputed_indicators.py`

**Step 5.2.1 — Add array declarations in `__init__()`**

After the existing `self.atr_s5` declaration (around line 126), add:

```python
# Sell-side ATR arrays (Wilder's smoothing)
self.atr_s7: Optional[np.ndarray] = None    # S7, S16
self.atr_10: Optional[np.ndarray] = None    # S10
self.atr_100: Optional[np.ndarray] = None   # S10
```

**Step 5.2.2 — Compute arrays in `compute_all()`**

After the fixed `atr_s5` line (Step 5.1), add:

```python
# === S7/S16 ATR (Wilder's) ===
s7_atr_period = getattr(p, 'input_S7_atr_period', 22)
if s7_atr_period == s1_atr_period:
    self.atr_s7 = self.atr_s1  # Reuse if same period
else:
    self.atr_s7 = self._atr_full(self.highs, self.lows, self.closes, s7_atr_period)

# === S10 ATR (Wilder's, periods 10 and 100) ===
self.atr_10 = self._atr_full(self.highs, self.lows, self.closes, 10)
self.atr_100 = self._atr_full(self.highs, self.lows, self.closes, 100)
```

**Verification:** After implementation, for every sell-day in the reference run, assert:
- `self.atr_s5[idx]` matches `atr(ohlcv[:idx+1], 20)[-1]`
- `self.atr_s7[idx]` matches `atr(ohlcv[:idx+1], 22)[-1]`
- `self.atr_10[idx]` matches `atr(ohlcv[:idx+1], 10)[-1]`
- `self.atr_100[idx]` matches `atr(ohlcv[:idx+1], 100)[-1]`

(All within ±1e-10 tolerance.)

---

### Step 5.3 — Add SMA-of-TR Helper and Arrays for S8

**File:** `app/workers/algo_func/precomputed_indicators.py`

**Problem:** S8 uses `sma(calc_tr_series(data), 22)` and `sma(calc_tr_series(data), 100)`. This is a **simple moving average** of True Range — NOT Wilder's smoothing. The existing `_atr_full()` uses Wilder's smoothing and will produce different values.

**Step 5.3.1 — Add the `_sma_tr_full()` helper method**

Add this method in the vectorized calculations section (after `_atr_full()`, around line 358):

```python
def _sma_tr_full(self, period: int) -> np.ndarray:
    """Calculate SMA-based ATR (simple moving average of True Range).
    
    Matches sell_signals.py's sma(calc_tr_series(data), period).
    DIFFERENT from Wilder's smoothing used in _atr_full().
    
    calc_tr_series() produces n-1 TR values (no TR for the first bar).
    sma(trs, period) returns len(trs) - period + 1 values starting from trs[period-1].
    First valid SMA corresponds to OHLCV index (period).
    """
    n = len(self.closes)
    result = np.full(n, np.nan)
    
    if n < period + 1:
        return result
    
    # True Range series (n-1 elements, offset by 1 from price array)
    prev_close = np.roll(self.closes, 1)
    prev_close[0] = self.closes[0]
    
    tr1 = self.highs[1:] - self.lows[1:]
    tr2 = np.abs(self.highs[1:] - prev_close[1:])
    tr3 = np.abs(self.lows[1:] - prev_close[1:])
    tr = np.maximum(tr1, np.maximum(tr2, tr3))
    
    # SMA of TR using pandas rolling
    sma_vals = pd.Series(tr).rolling(period, min_periods=period).mean().values
    
    # Align: TR[i] corresponds to OHLCV[i+1], so SMA_TR[j] → result[j+1]
    for i in range(len(sma_vals)):
        if not np.isnan(sma_vals[i]):
            result[i + 1] = sma_vals[i]
    
    return result
```

**Step 5.3.2 — Add array declarations in `__init__()`**

```python
# S8: SMA-based ATR (different algorithm from Wilder's)
self.sma_tr_22: Optional[np.ndarray] = None
self.sma_tr_100: Optional[np.ndarray] = None
self.rolling_max_sma_tr_22: Optional[np.ndarray] = None
```

**Step 5.3.3 — Compute arrays in `compute_all()`**

```python
# === S8: SMA-based ATR (NOT Wilder's — uses simple moving average of TR) ===
self.sma_tr_22 = self._sma_tr_full(22)
self.sma_tr_100 = self._sma_tr_full(100)
s8_window = getattr(p, 'input_S8_atr22_window', 126)
self.rolling_max_sma_tr_22 = self._rolling_max(self.sma_tr_22, s8_window)
```

**Step 5.3.4 — Verify index alignment**

The original S8 accesses:
- `sma(trs, 22)[-1]` → at the current sell-day `idx`, this equals the SMA of the last 22 TR values ending at `idx`. Our `self.sma_tr_22[idx]` must produce the same value.
- `sma(trs, 22)[-atr22_window:]` → `max(atr22[-atr22_window:])` → Our `self.rolling_max_sma_tr_22[idx]` must match.
- `sma(trs, 100)[-1]` → Our `self.sma_tr_100[idx]` must match.

**Verification code (for debugging only):**
```python
# In a test:
from sell_signals import calc_tr_series, sma
trs_orig = calc_tr_series(ohlcv[:idx+1])
atr22_orig = sma(trs_orig, 22)
atr100_orig = sma(trs_orig, 100)
assert abs(atr22_orig[-1] - self.sma_tr_22[idx]) < 1e-10
assert abs(atr100_orig[-1] - self.sma_tr_100[idx]) < 1e-10
```

---

### Step 5.4 — Add Rolling Window Arrays for Sell Conditions

**File:** `app/workers/algo_func/precomputed_indicators.py`

**Step 5.4.1 — Add declarations in `__init__()`**

```python
# Rolling windows for sell conditions
self.rolling_max_high_90: Optional[np.ndarray] = None   # S6, S10
self.rolling_max_high_150: Optional[np.ndarray] = None  # S17
self.rolling_min_low_150: Optional[np.ndarray] = None   # S17
self.rolling_min_close_80: Optional[np.ndarray] = None  # S13
self.rolling_max_high_5: Optional[np.ndarray] = None    # E5
self.rolling_min_low_5: Optional[np.ndarray] = None     # E5
```

**Step 5.4.2 — Compute in `compute_all()`**

```python
# === Rolling windows for sell conditions ===
s6_window = getattr(p, 'input_S6_high_window', 90)
s17_window = getattr(p, 'input_S17_min_days', 150)
s13_lookback = getattr(p, 'input_S13_lookback', 80)

self.rolling_max_high_90 = self._rolling_max(self.highs, s6_window)
self.rolling_max_high_150 = self._rolling_max(self.highs, s17_window)
self.rolling_min_low_150 = self._rolling_min(self.lows, s17_window)
self.rolling_min_close_80 = self._rolling_min(self.closes, s13_lookback)
self.rolling_max_high_5 = self._rolling_max(self.highs, 5)
self.rolling_min_low_5 = self._rolling_min(self.lows, 5)
```

**Step 5.4.3 — Verify offset semantics**

Critical: different sell functions use windows with different offset conventions:

| Sell function | Original code | Pre-computed equivalent | Offset note |
|--|--|--|--|
| S6 | `highs[start_window:last_idx + 1]` | `rolling_max_high_90[idx]` | **Includes** current bar |
| S10 | `data[-91:-1]` | `rolling_max_high_90[idx - 1]` | **Excludes** current bar (90 bars ending at `idx-1`) |
| S13 | `data[last_idx - lookback : last_idx]` | `rolling_min_close_80[idx - 1]` | **Excludes** current bar |
| S17 | `data[-min_days:]` | `rolling_max_high_150[idx]` and `rolling_min_low_150[idx]` | **Includes** current bar |

When implementing the fast methods (Step 5.8), apply the correct offset for each function.

---

### Step 5.5 — Add Date-to-Index Map and Days-Since-High Helper

**File:** `app/workers/algo_func/precomputed_indicators.py`

**Step 5.5.1 — Add `date_to_idx` map in `compute_all()`**

```python
# O(1) buy-date → index lookup (replaces 7+ linear scans per sell-day)
self.date_to_idx = {d: i for i, d in enumerate(self.dates)}
```

This replaces the `to_ts(buy_date)` + linear search pattern used in S4, S5, S6, S13, S14, S16, S17. Each sell function currently does:
```python
bts = to_ts(buy_date)
buy_idx = -1
for i, d in enumerate(data):
    if to_ts(d.date) == bts:
        buy_idx = i
        break
```
This is O(n) × 7+ functions per sell-day. With `date_to_idx`, it becomes O(1) once per sell-day.

**Step 5.5.2 — Add `_rolling_days_since_max()` helper**

S6 needs `days_since_high = last_idx - last_high_idx` where `last_high_idx` is the most recent index achieving the rolling 90-day max:

```python
def _rolling_days_since_max(self, values: np.ndarray, period: int) -> np.ndarray:
    """For each index i, compute i - j where j is the latest index in
    [i - period + 1, i] at which values[j] == max(values[i-period+1:i+1]).
    
    Used by S6 to find days since the most recent high in the window.
    """
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
```

**Step 5.5.3 — Compute in `compute_all()`**

```python
self.days_since_high_90 = self._rolling_days_since_max(self.highs, s6_window)
```

**Verification:** For the reference run, `self.days_since_high_90[idx]` must match the `days_since_high` variable in the original `s6()` at every sell-day where S6 is evaluated.

---

### Step 5.6 — Add Fibonacci Ratio and Consecutive-Day Arrays

**File:** `app/workers/algo_func/precomputed_indicators.py`

Used by S11 (`fibo_exit_stop` with level 0.382, yy_days 2) and S12 (level 0.236, yy_days 22).

**Step 5.6.1 — Add declarations in `__init__()`**

```python
# Fibonacci ratio for S11/S12
self.fibo_ratio_250: Optional[np.ndarray] = None
self.fibo_above_382: Optional[np.ndarray] = None
self.fibo_above_236: Optional[np.ndarray] = None
self.fibo_consec_s11: Optional[np.ndarray] = None
self.fibo_consec_s12: Optional[np.ndarray] = None
```

**Step 5.6.2 — Add `_rolling_all_true()` helper method**

```python
def _rolling_all_true(self, bools: np.ndarray, window: int) -> np.ndarray:
    """True at index i if bools[i-window+1 : i+1] are all True (or == 1).
    
    Efficiently counts consecutive True values using a running counter.
    """
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
```

**Step 5.6.3 — Compute in `compute_all()`**

```python
# === Fibonacci ratio for S11/S12 ===
# fibo_ratio[i] = (high250[i] - close[i]) / (high250[i] - low250[i])
with np.errstate(divide='ignore', invalid='ignore'):
    range_250 = self.rolling_max_250 - self.rolling_min_250
    self.fibo_ratio_250 = np.where(
        range_250 > 0,
        (self.rolling_max_250 - self.closes) / range_250,
        np.nan
    )

s11_level = getattr(p, 'input_S11_fib_level', 0.382)
s12_level = getattr(p, 'input_S12_fib_level', 0.236)
s11_yy = getattr(p, 'input_S11_yy_days', 2)
s12_yy = getattr(p, 'input_S12_yy_days', 22)

self.fibo_above_382 = ~np.isnan(self.fibo_ratio_250) & (self.fibo_ratio_250 > s11_level)
self.fibo_above_236 = ~np.isnan(self.fibo_ratio_250) & (self.fibo_ratio_250 > s12_level)
self.fibo_consec_s11 = self._rolling_all_true(self.fibo_above_382, s11_yy)
self.fibo_consec_s12 = self._rolling_all_true(self.fibo_above_236, s12_yy)
```

**Step 5.6.4 — Verify against original `fibo_exit_stop()`**

The original `fibo_exit_stop()` checks `below_fibo_level(i)` for each of the last `yy_days` bars, where `below_fibo_level(i)` computes `ratio > level` using a 250-bar rolling window. Our pre-computed `fibo_consec_s11[idx]` answers: "were all of the last 2 bars above 0.382?" — which is the same check.

The original also requires:
- `n >= 250` → guarded by `idx >= 249`
- `bars_since_entry > xx_days` → trade-specific, remains in the fast method
- Each `below_fibo_level(i)` checks `i >= 249` → satisfied by the outer `idx >= 249` check since `offset ∈ [0, yy_days)` and `yy_days` is small

**Gate:** Run the sell parity test (Step 5.10) to confirm S11/S12 produce identical results.

---

### Step 5.7 — Add S14 Period Ratios

**File:** `app/workers/algo_func/precomputed_indicators.py`

**Step 5.7.1 — Add declarations in `__init__()`**

```python
# S14 relative performance at multiple horizons
self.s14_stock_ratios: Dict[int, np.ndarray] = {}
self.s14_index_ratios: Dict[int, np.ndarray] = {}
```

**Step 5.7.2 — Compute in `compute_all()`**

```python
# === S14 relative performance ===
s14_horizons = getattr(p, 'input_S14_horizons', [35, 70, 105])
for horizon in s14_horizons:
    stock_r, idx_r = self._calc_period_ratios(self.closes, self.spy_closes, horizon)
    self.s14_stock_ratios[horizon] = stock_r
    self.s14_index_ratios[horizon] = idx_r
```

**Note:** `_calc_period_ratios()` already exists and handles stock/SPY date alignment via exact string match with bisect fallback. The same method is used for B13 (periods XX and YY) and is validated. S14 uses different periods (35, 70, 105) but the same alignment logic applies.

**Verification:** For the reference run, at each sell-day where S14 is evaluated, compare:
- `self.s14_stock_ratios[35][idx]` vs the original `ra = asset_c[last_idx] / asset_c[last_idx - 35] - 1`
- Same for horizons 70 and 105

Note the difference: the pre-computed ratio is `close[i] / close[i - period]` while the original S14 computes `close[last] / close[last - period] - 1`. The fast method must subtract 1 when comparing, or the pre-computed ratio should store `ratio - 1`. Choose whichever is cleaner — the important thing is parity.

---

### Step 5.8 — Add Fast Sell-Condition Lookup Methods

**File:** `app/workers/algo_func/precomputed_indicators.py`

Add methods for each sell condition that replaces O(n) indicator computation with O(1) array lookups. Each method receives only trade-specific parameters (buy_idx, buy_price, stop_loss) as arguments.

**Step 5.8.1 — Add `get_s4_condition()`**

```python
def get_s4_condition(self, idx: int, buy_idx: int, buy_price: float) -> bool:
    """S4: SMA ratio + gain check within max_days window after buy.
    
    Original: s4(ohlcv, buy_date, buy_price, params)
    Reuses self.sma_150 for SMA(150).
    """
    p = self.params
    max_days = p.input_S4_max_days
    sma_period = p.input_S4_sma_period
    
    if buy_idx < 0 or buy_idx < sma_period - 1:
        return False
    
    day_n_idx = buy_idx + max_days
    if day_n_idx >= self.n:
        return False
    
    # S4 only fires at exactly day_n_idx — if idx != day_n_idx, return False
    if idx != day_n_idx:
        return False
    
    # Compute SMA ratio: fraction of days where close > SMA in window
    sma_arr = self.sma_150 if sma_period == 150 else self._sma_full(self.closes, sma_period)
    
    window_idx = range(buy_idx + 1, day_n_idx + 1)
    if any(np.isnan(sma_arr[i]) for i in window_idx):
        return False
    
    A = sum(1 for i in window_idx if self.closes[i] > sma_arr[i])
    ratio = A / float(max_days)
    
    close_n = self.closes[day_n_idx]
    gain_pct = ((close_n - buy_price) / buy_price) * 100.0
    
    return (ratio < p.input_S4_ratio_threshold) and (gain_pct < p.input_S4_gain_threshold)
```

**Note on S4:** S4 only evaluates at exactly `buy_idx + max_days`. On all other days it returns False. The original achieves this implicitly because `day_n_idx >= len(data)` returns False when the window extends past the current slice. Our `idx` is the current day, so we must check `idx == day_n_idx`. This is a subtle but critical behavioral match.

**Step 5.8.2 — Add `get_s5_condition()`**

```python
def get_s5_condition(self, idx: int, buy_idx: int, buy_price: float,
                     stop_loss: float) -> tuple:
    """S5: Trailing stop with ATR push-up on key days.
    Returns (exit_signal: bool, new_stop_loss: float).
    
    Original: s5(ohlcv, buy_date, buy_price, stop_loss, trade_date, params)
    """
    p = self.params
    initial_days = p.input_S5_initial_days
    step_days = p.input_S5_step_days
    push_up_atr = p.input_S5_push_up_atr
    
    if buy_idx < 0:
        return False, stop_loss
    
    current_close = self.closes[idx]
    days_since_buy = idx - buy_idx
    
    is_key_day = False
    if days_since_buy == initial_days:
        is_key_day = True
    elif days_since_buy > initial_days and (days_since_buy - initial_days + 1) % step_days == 0:
        is_key_day = True
    elif days_since_buy > initial_days:
        return current_close < stop_loss, stop_loss
    
    if not is_key_day:
        return False, stop_loss
    
    # O(1) ATR lookup instead of O(n) atr(ohlcv, period)
    current_atr = self.atr_s5[idx]
    if np.isnan(current_atr) or current_atr == 0:
        return False, stop_loss
    
    if days_since_buy == initial_days:
        new_stop_loss = buy_price + push_up_atr * current_atr
    else:
        new_stop_loss = stop_loss + push_up_atr * current_atr
    
    exit_signal = current_close < new_stop_loss
    return exit_signal, new_stop_loss
```

**Step 5.8.3 — Add `get_s6_condition()`**

```python
def get_s6_condition(self, idx: int, buy_idx: int) -> bool:
    """S6: Days since most recent 90-day high exceeds threshold.
    
    Original: s6(ohlcv, buy_date, trade_date, params)
    """
    p = self.params
    high_window = p.input_S6_high_window
    
    if buy_idx < 0 or idx < high_window - 1:
        return False
    if self.n < high_window + 10:
        return False
    
    days_since_buy = idx - buy_idx
    if days_since_buy < p.input_S6_min_days:
        return False
    
    days_since_high = self.days_since_high_90[idx]
    if np.isnan(days_since_high):
        return False
    
    return int(days_since_high) >= p.input_S6_days_threshold
```

**Step 5.8.4 — Add `get_s7_condition()`**

```python
def get_s7_condition(self, idx: int) -> bool:
    """S7: Two consecutive large bearish bodies > body_mult * ATR(22).
    
    Original: s7(ohlcv, buy_date, buy_price, params)
    """
    p = self.params
    atr_period = p.input_S7_atr_period
    
    if idx < 2 or idx >= self.n:
        return False
    if self.n < atr_period + 2:
        return False
    
    atr_prev = self.atr_s7[idx - 1]
    atr_last = self.atr_s7[idx]
    
    if np.isnan(atr_prev) or np.isnan(atr_last):
        return False
    
    body_prev = self.opens[idx - 1] - self.closes[idx - 1]
    body_last = self.opens[idx] - self.closes[idx]
    
    cond_prev = body_prev > p.input_S7_body_mult * atr_prev
    cond_last = body_last > p.input_S7_body_mult * atr_last
    
    return cond_prev and cond_last
```

**Step 5.8.5 — Add `get_s8_condition()`**

```python
def get_s8_condition(self, idx: int) -> bool:
    """S8: ATR(100) SMA > threshold * max(ATR(22) SMA, 126 window) + bearish body count.
    
    Original: s8(ohlcv, buy_date, buy_price, params)
    Uses SMA-of-TR (NOT Wilder's ATR).
    """
    p = self.params
    
    if self.n < 148 or idx < 148:
        return False
    
    # O(1) lookups
    current_atr100 = self.sma_tr_100[idx]
    max_atr22 = self.rolling_max_sma_tr_22[idx]
    
    if np.isnan(current_atr100) or np.isnan(max_atr22):
        return False
    
    if not (current_atr100 > p.input_S8_atr100_threshold * max_atr22):
        return False
    
    # Count bearish bodies in last 5 bars (still O(1) — fixed window of 5)
    count_bear_huge = 0
    for j in range(5):
        bar_idx = idx - 4 + j
        if bar_idx < 0:
            continue
        body = self.opens[bar_idx] - self.closes[bar_idx]
        atr100_j = self.sma_tr_100[bar_idx]
        if np.isnan(atr100_j):
            continue
        if body > p.input_S8_body_mult * atr100_j:
            count_bear_huge += 1
    
    return count_bear_huge >= p.input_S8_bear_count
```

**Step 5.8.6 — Add `get_s10_condition()`**

```python
def get_s10_condition(self, idx: int) -> bool:
    """S10: ATR(10) > atr_ratio * ATR(100) + drawdown from 90-day high.
    
    Original: s10(ohlcv, buy_date, buy_price, params)
    Note: Original uses data[-91:-1] for 90-day high — excludes current bar.
    """
    p = self.params
    
    if idx < 101 or self.n < 101:
        return False
    
    atr10 = self.atr_10[idx]
    atr100 = self.atr_100[idx]
    
    if np.isnan(atr10) or np.isnan(atr100):
        return False
    
    # S10 uses data[-91:-1] — 90 bars EXCLUDING current bar
    # rolling_max_high_90[idx-1] = max(highs[idx-90:idx]) which is the same
    high90 = self.rolling_max_high_90[idx - 1]
    if np.isnan(high90) or high90 <= 0:
        return False
    
    last_close = self.closes[idx]
    drawdown_pct = (high90 - last_close) / high90
    
    cond_vol = atr10 > p.input_S10_atr_ratio * atr100
    cond_dd = drawdown_pct > p.input_S10_drawdown
    
    return cond_vol and cond_dd
```

**Step 5.8.7 — Add `get_s11_condition()` and `get_s12_condition()`**

```python
def get_s11_condition(self, idx: int, buy_idx: int) -> bool:
    """S11: Fibonacci level (0.382) for 2 consecutive days after xx_days bars since entry.
    
    Original: s11(ohlcv, buy_date, buy_price, params) → fibo_exit_stop(xx=300, level=0.382, yy=2)
    """
    p = self.params
    
    if buy_idx < 0 or idx < 249 or self.n < 250:
        return False
    
    bars_since_entry = idx - buy_idx
    if bars_since_entry <= p.input_S11_xx_days:
        return False
    
    return bool(self.fibo_consec_s11[idx])

def get_s12_condition(self, idx: int, buy_idx: int) -> bool:
    """S12: Fibonacci level (0.236) for 22 consecutive days after xx_days bars since entry.
    
    Original: s12(ohlcv, buy_date, buy_price, params) → fibo_exit_stop(xx=240, level=0.236, yy=22)
    """
    p = self.params
    
    if buy_idx < 0 or idx < 249 or self.n < 250:
        return False
    
    bars_since_entry = idx - buy_idx
    if bars_since_entry <= p.input_S12_xx_days:
        return False
    
    return bool(self.fibo_consec_s12[idx])
```

**Step 5.8.8 — Add `get_s13_condition()`**

```python
def get_s13_condition(self, idx: int, buy_idx: int) -> bool:
    """S13: Close < min(close, 80) after min_days since buy.
    
    Original: s13(ohlcv, buy_date, buy_price, params)
    Note: Original uses data[last_idx - lookback : last_idx] — excludes current bar.
    """
    p = self.params
    lookback = p.input_S13_lookback
    
    if buy_idx < 0 or idx < lookback + 1 or self.n < lookback + 1:
        return False
    
    days_since_buy = idx - buy_idx
    if days_since_buy < p.input_S13_min_days:
        return False
    
    # Excludes current bar: rolling_min_close_80[idx - 1] = min(closes[idx-80:idx])
    min_close_n = self.rolling_min_close_80[idx - 1]
    if np.isnan(min_close_n):
        return False
    
    return self.closes[idx] < min_close_n
```

**Step 5.8.9 — Add `get_s14_condition()`**

```python
def get_s14_condition(self, idx: int, buy_idx: int) -> bool:
    """S14: Underperforming SPY at all three horizons after min_days.
    
    Original: s14(ohlcv, spy_data, buy_date, buy_price, params)
    """
    p = self.params
    
    if buy_idx < 0:
        return False
    
    days_since_buy = idx - buy_idx
    if days_since_buy < p.input_S14_min_days:
        return False
    
    horizons = p.input_S14_horizons
    
    for horizon in horizons:
        stock_r = self.s14_stock_ratios.get(horizon)
        index_r = self.s14_index_ratios.get(horizon)
        
        if stock_r is None or index_r is None:
            return False
        
        sr = stock_r[idx]
        ir = index_r[idx]
        
        if np.isnan(sr) or np.isnan(ir):
            return False
        
        # Original: ra = asset_c[last_idx] / asset_c[last_idx - horizon] - 1
        # Pre-computed: stock_r[idx] = closes[idx] / closes[idx - horizon]
        # So original's ra = stock_r[idx] - 1, rh = index_r[idx] - 1
        # Comparison ra >= rh is equivalent to stock_r[idx] >= index_r[idx]
        if sr >= ir:
            return False  # Not underperforming at this horizon
    
    return True  # Underperforming at ALL horizons
```

**Step 5.8.10 — Add `get_s15_condition()`**

```python
def get_s15_condition(self, idx: int) -> bool:
    """S15: Crash drop — close/close[idx-lookback] < -crash_drop.
    
    Original: s15(ohlcv, buy_date, buy_price, params)
    """
    p = self.params
    lookback = p.input_S15_lookback
    
    if idx < lookback + 1:
        return False
    
    base_close = self.closes[idx - lookback]
    if base_close <= 0:
        return False
    
    ret = (self.closes[idx] / base_close) - 1
    return ret < -p.input_S15_crash_drop
```

**Step 5.8.11 — Add `get_s16_condition()`**

```python
def get_s16_condition(self, idx: int, buy_idx: int) -> bool:
    """S16: Big price drop + ATR volatility spike.
    
    Original: s16(ohlcv, buy_date, params)
    """
    p = self.params
    s16_xx = p.input_S16_xx
    s16_yy = p.input_S16_yy
    s16_effective = p.input_S16_effective
    s16_atr_inc = p.input_S16_atr_inc
    s16_atr_day = p.input_S16_atr_day
    atr_period = 22
    
    if buy_idx < 0:
        return False
    if self.n < atr_period + s16_yy + s16_atr_day + 1:
        return False
    
    bars_since_entry = idx - buy_idx
    if bars_since_entry <= s16_effective:
        return False
    
    if idx - s16_yy < 0:
        return False
    
    last_close = self.closes[idx]
    base_close = self.closes[idx - s16_yy]
    if base_close <= 0:
        return False
    
    ret_yy = last_close / base_close - 1
    big_drop = ret_yy < -s16_xx / 100.0
    
    # ATR volatility spike check — uses Wilder's ATR(22) same as S7
    atr_now = self.atr_s7[idx]
    atr_past_idx = idx - s16_atr_day
    if atr_past_idx < 0:
        return False
    atr_past = self.atr_s7[atr_past_idx]
    
    if np.isnan(atr_now) or np.isnan(atr_past) or atr_past <= 0:
        return False
    
    vol_spike = (atr_now / atr_past - 1.0) * 100.0 > s16_atr_inc
    
    return vol_spike and big_drop
```

**Note on S16 ATR:** The original `s16()` calls `atr(data, 22)` which uses Wilder's smoothing (the `atr()` function in `sell_signals.py`). This is the same as `self.atr_s7` (Wilder's ATR period 22). Do NOT confuse with `self.sma_tr_22` (SMA-based, used only by S8).

**Step 5.8.12 — Add `get_s17_condition()`**

```python
def get_s17_condition(self, idx: int, buy_idx: int) -> bool:
    """S17: Wide range + near bottom.
    
    Original: s17(ohlcv, buy_date, buy_price, params)
    """
    p = self.params
    min_days = p.input_S17_min_days
    
    if buy_idx < 0 or idx < min_days or self.n < min_days:
        return False
    
    days_since_buy = idx - buy_idx
    if days_since_buy < min_days:
        return False
    
    # S17 uses data[-min_days:] — includes current bar
    high_n = self.rolling_max_high_150[idx]
    low_n = self.rolling_min_low_150[idx]
    
    if np.isnan(high_n) or np.isnan(low_n) or high_n <= low_n:
        return False
    
    is_wide_range = high_n > p.input_S17_wide_range * low_n
    if not is_wide_range:
        return False
    
    last_close = self.closes[idx]
    is_near_bottom = last_close < p.input_S17_near_bottom * low_n
    
    return is_near_bottom
```

---

### Step 5.9 — Add S4 SMA Array (if non-default period)

**Problem:** `get_s4_condition()` uses `self.sma_150` which was pre-computed for B18. If `params.input_S4_sma_period != 150`, a separate SMA array is needed.

**Step 5.9.1 — Add in `compute_all()`**

```python
# === S4 SMA (reuse sma_150 if period matches) ===
s4_sma_period = getattr(p, 'input_S4_sma_period', 150)
if s4_sma_period == 150:
    self.sma_s4 = self.sma_150
else:
    self.sma_s4 = self._sma_full(self.closes, s4_sma_period)
```

Then update `get_s4_condition()` to use `self.sma_s4` instead of `self.sma_150`.

---

### Step 5.10 — Create Sell Parity Test for ATR/Rolling Windows

**File:** Create `tests/test_sell_precomputed_parity.py`

```python
"""
Validates that pre-computed sell indicator arrays produce values identical
to the original per-call computations for every sell-day.
"""
import asyncio, os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.workers.algo_func.get_db_data import get_stock_data_from_db, init_db_pool
from app.workers.algo_func.sell_signals import atr, calc_tr_series, sma
from app.workers.algo_func.precomputed_indicators import (
    PrecomputedIndicators, OHLCV as PrecompOHLCV,
)
from app.workers.algo_func.buy_signals import OHLCV
from app.models.algorithm_models import AlgorithmParameters
import numpy as np

STOCK = "3888"
END_DATE = os.getenv('OPTIMIZATION_END_DATE', '2026-02-02')
TOLERANCE = 1e-10


async def run_validation():
    await init_db_pool()
    params = AlgorithmParameters()

    code_raw = await get_stock_data_from_db(STOCK, END_DATE)
    spy_raw = await get_stock_data_from_db("2800", END_DATE)

    code_data = [OHLCV(b["date"], b["open"], b["high"], b["low"], b["close"], b["volume"])
                 for b in code_raw]
    spy_data = [OHLCV(b["date"], b["open"], b["high"], b["low"], b["close"], b["volume"])
                for b in spy_raw]

    precomp_code = [PrecompOHLCV(b.date, b.open, b.high, b.low, b.close, b.volume) for b in code_data]
    precomp_spy = [PrecompOHLCV(b.date, b.open, b.high, b.low, b.close, b.volume) for b in spy_data]
    precomputed = PrecomputedIndicators(precomp_code, precomp_spy, params)
    precomputed.compute_all()

    errors = []
    # Spot-check ATR arrays at every 100th index
    for idx in range(200, len(code_data), 100):
        ohlcv_slice = code_data[:idx + 1]

        # Wilder's ATR(20) — S5
        orig_atr20 = atr(ohlcv_slice, 20)[-1]
        pre_atr20 = precomputed.atr_s5[idx]
        if abs(orig_atr20 - pre_atr20) > TOLERANCE:
            errors.append(f"ATR(20) mismatch at idx={idx}: orig={orig_atr20}, pre={pre_atr20}")

        # SMA-TR(22) — S8
        trs = calc_tr_series(ohlcv_slice)
        orig_sma22 = sma(trs, 22)[-1] if len(sma(trs, 22)) > 0 else None
        pre_sma22 = precomputed.sma_tr_22[idx]
        if orig_sma22 is not None and not np.isnan(pre_sma22):
            if abs(orig_sma22 - pre_sma22) > TOLERANCE:
                errors.append(f"SMA-TR(22) mismatch at idx={idx}: orig={orig_sma22}, pre={pre_sma22}")

    print(f"\n{'='*60}")
    print(f"ATR/Rolling array parity check: {len(errors)} errors")
    if errors:
        for e in errors[:20]:
            print(f"  {e}")
        print("FAIL")
        sys.exit(1)
    else:
        print("PASS — all ATR/rolling arrays match")


if __name__ == "__main__":
    asyncio.run(run_validation())
```

Run:
```bash
docker cp tests/test_sell_precomputed_parity.py hk-algo-improve-algorithm-worker-1:/app/tests/
docker-compose exec algorithm-worker python tests/test_sell_precomputed_parity.py
```

**Gate:** Must print `PASS`.

Additionally, run the existing sell parity test to confirm the unchanged sell path still produces identical trade output:
```bash
docker cp tests/test_sell_parity.py hk-algo-improve-algorithm-worker-1:/app/tests/
docker-compose exec algorithm-worker python tests/test_sell_parity.py
```

**Gate:** All 10 trade rows must match reference.

---

## Phase 6 — Pre-Compute Energy Indicators (E1–E5)

> **Goal:** Replace the per-sell-day O(n) energy computation (`calculate_energy_indicators_last_16_days()`) with O(1) pre-computed array lookups.  
> **Expected speedup:** ~5–10× on sell-day cost when combined with Phase 5. Energy is the dominant remaining bottleneck (~80% of sell-day cost).  
> **Files modified:** `precomputed_indicators.py`, new test file.

---

### Step 6.1 — Pre-Compute E1 Boolean Array

**File:** `app/workers/algo_func/precomputed_indicators.py`

**E1 formula:** "New high in past 20 days AND close is in upper 35% of day's range."

The original code in `get_code_energy.py` (lines 176–191):
```python
start_idx = max(0, idx - 20)
end_idx = idx - 1  # not including current bar
max_high_20d = max(high[start_idx:end_idx + 1])
E1 = "1" if (high[idx] > max_high_20d and
             close[idx] > (high[idx] - low[idx]) * 0.65 + low[idx]) else "0"
```

**Step 6.1.1 — Add declaration in `__init__()`**

```python
# Energy indicator arrays
self.e1: Optional[np.ndarray] = None
```

**Step 6.1.2 — Compute in `compute_all()`**

```python
# === Energy E1: New high in past 20 days + close in upper range ===
self.e1 = np.zeros(self.n, dtype=np.int8)
for i in range(66, self.n):
    # Max of highs in [i-20, i-1] — excludes current bar
    # rolling_max_20[i-1] = max(highs[max(0, i-20):i]) which is exactly what we need
    if i >= 20:
        max_high_20_excl = self.rolling_max_20[i - 1]
    else:
        max_high_20_excl = np.max(self.highs[max(0, i - 20):i]) if i > 0 else 0
    
    if np.isnan(max_high_20_excl):
        continue
    
    cond_high = self.highs[i] > max_high_20_excl
    cond_close = self.closes[i] > (self.highs[i] - self.lows[i]) * 0.65 + self.lows[i]
    
    if cond_high and cond_close:
        self.e1[i] = 1
```

**Note on `rolling_max_20` vs E1 window:** The existing `self.rolling_max_20 = self._rolling_max(self.highs, 20)` computes `pd.Series(highs).rolling(20).max()` where `rolling_max_20[i] = max(highs[i-19:i+1])` — includes the current bar. The original E1 uses `max(high[max(0, idx-20):idx])` — up to 20 bars **excluding** current. Using `rolling_max_20[i-1]` gives `max(highs[i-20:i])` which matches the original's 20-bar window ending one before current. The slight difference is the original uses `max(0, idx-20)` as the start while `rolling_max_20` uses a fixed window of 20. For `i >= 20`, they are identical. For `i < 20` but `i >= 66` (our guard), this is always satisfied.

---

### Step 6.2 — Pre-Compute E2 Boolean Array (StochRSI)

**File:** `app/workers/algo_func/precomputed_indicators.py`

**E2 formula:** "StochRSI(10) > 0.5"

**Convergence rationale:** The original computes RSI on a 24-month-filtered window. `PrecomputedIndicators._rsi_full()` computes RSI on the entire dataset. Wilder's smoothing has effective memory of ~3× period bars. For RSI(10), values converge within ~30 bars. The 24-month window provides ~500 trading days before the evaluation point, so values are identical to machine precision.

**Step 6.2.1 — Add declaration in `__init__()`**

```python
self.e2: Optional[np.ndarray] = None
```

**Step 6.2.2 — Compute in `compute_all()`**

```python
# === Energy E2: StochRSI(10) > 0.5 ===
self.e2 = np.zeros(self.n, dtype=np.int8)
for i in range(66, self.n):
    if not np.isnan(self.stochrsi_10[i]) and self.stochrsi_10[i] > 0.5:
        self.e2[i] = 1
```

**Validation:** The energy parity test (Step 6.6) will compare pre-computed E2 against the original for every sell-day. If discrepancies appear, fall back to computing RSI on the 24-month-filtered window.

---

### Step 6.3 — Pre-Compute E3, E4, E5 Boolean Arrays

**File:** `app/workers/algo_func/precomputed_indicators.py`

**Step 6.3.1 — Add declarations in `__init__()`**

```python
self.e3: Optional[np.ndarray] = None
self.e4: Optional[np.ndarray] = None
self.e5: Optional[np.ndarray] = None
```

**Step 6.3.2 — Compute E3 (slope > 0)**

```python
# === Energy E3: slope(close, 66) > 0 → close[i] > close[i-66] ===
self.e3 = np.zeros(self.n, dtype=np.int8)
for i in range(66, self.n):
    if self.closes[i] > self.closes[i - 66]:
        self.e3[i] = 1
```

**Step 6.3.3 — Compute E4 (stock vs SPY performance over 33 days)**

First, add the 33-day period ratios if not already computed:

```python
# === Energy E4: stock outperforms SPY over 33 days ===
self.stock_ratio_33, self.spy_ratio_33 = self._calc_period_ratios(
    self.closes, self.spy_closes, 33
)

self.e4 = np.zeros(self.n, dtype=np.int8)
for i in range(66, self.n):
    sr = self.stock_ratio_33[i]
    ir = self.spy_ratio_33[i]
    if not np.isnan(sr) and not np.isnan(ir) and sr > ir:
        self.e4[i] = 1
```

**Note on E4 alignment:** The original uses `sdate_spy.index(sdate[idx])` for exact date string matching, then looks back 33 bars in each series independently. `_calc_period_ratios()` uses exact string matching with bisect fallback, and also looks back `period` bars in each series independently. These produce identical results for dates present in both series. For missing dates, bisect maps to the previous date while the original raises `ValueError` and outputs `E4 = "0"`. The pre-computed version handles NaN gracefully (treated as `E4 = 0`), matching the original's `except ValueError: E4 = "0"`.

**Step 6.3.4 — Compute E5 (price position in range + near high)**

```python
# === Energy E5: upper half of 5-day range + close > 5-day-ago + near 250-day high ===
self.e5 = np.zeros(self.n, dtype=np.int8)
for i in range(66, self.n):
    if i < 5:
        continue
    
    min5 = self.rolling_min_low_5[i]    # min(low[i-4:i+1])
    max5 = self.rolling_max_high_5[i]    # max(high[i-4:i+1])
    max250 = self.rolling_max_250[i]     # max(high[i-249:i+1])
    
    if np.isnan(min5) or np.isnan(max5) or np.isnan(max250):
        continue
    
    cond1 = (self.closes[i] - min5) / (max5 - min5) > 0.5 if max5 != min5 else False
    cond2 = self.closes[i] > self.closes[i - 5]
    cond3 = (max250 - self.closes[i]) / max250 < 0.07 if max250 != 0 else False
    
    if cond1 and cond2 and cond3:
        self.e5[i] = 1
```

**Note on E5 window alignment:**
- Original `lowest(low, 5)`: `min(low[max(0, idx-4):idx+1])` = 5 bars including current. Our `rolling_min_low_5[i]` = `pd.Series(lows).rolling(5).min()[i]` = `min(lows[i-4:i+1])`. Identical for `i >= 4`.
- Original `highest(high, 250)`: `max(high[max(0, idx-249):idx+1])`. Our `rolling_max_250[i]` = `max(highs[i-249:i+1])`. Identical for `i >= 249`, which is guaranteed since `i >= 66` and E5 only uses `max250` which is NaN for `i < 249` — but the original also handles short windows. Since stock 3888 has ~6000 bars, indices in the evaluation range are well above 249.

---

### Step 6.4 — Pre-Compute Energy Score as Rolling Sum

**File:** `app/workers/algo_func/precomputed_indicators.py`

**Step 6.4.1 — Add declarations in `__init__()`**

```python
self.e_total: Optional[np.ndarray] = None
self.energy_score: Optional[np.ndarray] = None
```

**Step 6.4.2 — Compute in `compute_all()` (AFTER E1–E5 arrays)**

```python
# === Energy score: rolling 16-day sum of E1+E2+E3+E4+E5, divided by 16 ===
self.e_total = (self.e1 + self.e2 + self.e3 + self.e4 + self.e5).astype(np.float64)
e_series = pd.Series(self.e_total)
self.energy_score = (e_series.rolling(16, min_periods=16).sum() / 16.0).values
```

**Formula match:** The original sums `E1 + E2 + E3 + E4 + E5` for each of the last 16 days, counting only numeric values (not `"N/A"`), then divides by 16. Since our pre-computed arrays use `0` for indices where the original outputs `"N/A"`, and `0` contributes nothing to the sum, the result is identical: `sum(e_total[i-15:i+1]) / 16`.

**Edge case:** The original's denominator is always 16 (`total_energy_sum / 16`), even if some indicators are `"N/A"`. Our rolling sum with `min_periods=16` returns NaN if fewer than 16 values are available. For the evaluation range (starting 2016), all indices have 16+ preceding bars with valid energy values (since `i >= 66` is required and evaluation starts well past index 66+16).

---

### Step 6.5 — Add `get_energy_data()` and `get_s9_condition()` Methods

**File:** `app/workers/algo_func/precomputed_indicators.py`

**Step 6.5.1 — Add `get_energy_data()`**

```python
def get_energy_data(self, idx: int) -> dict:
    """Return energy data dict for CSV output — drop-in replacement
    for calculate_energy_indicators_last_16_days() return value.
    
    Returns dict with keys: energy_score, E1, E2, E3, E4, E5.
    Values are strings ("0"/"1") matching the original format.
    """
    if idx < 0 or idx >= self.n:
        return {
            "energy_score": 0,
            "E1": "0", "E2": "0", "E3": "0", "E4": "0", "E5": "0",
        }
    
    es = self.energy_score[idx] if not np.isnan(self.energy_score[idx]) else 0
    
    return {
        "energy_score": es,
        "E1": str(int(self.e1[idx])),
        "E2": str(int(self.e2[idx])),
        "E3": str(int(self.e3[idx])),
        "E4": str(int(self.e4[idx])),
        "E5": str(int(self.e5[idx])),
    }
```

**Step 6.5.2 — Add `get_s9_condition()`**

```python
def get_s9_condition(self, idx: int) -> bool:
    """S9: energy_score < threshold.
    
    Original: s9(trade_date, ohlcv, spy_data, params, energy_data=energy_data)
    """
    if idx < 0 or idx >= self.n or np.isnan(self.energy_score[idx]):
        return False
    return self.energy_score[idx] < self.params.input_S9_energy_thresh
```

---

### Step 6.6 — Energy Parity Test

**File:** Create `tests/test_energy_parity.py`

```python
"""
Validates that pre-computed energy indicators match the original
calculate_energy_indicators_last_16_days() for sell-days.
"""
import asyncio, os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.workers.algo_func.get_db_data import get_stock_data_from_db, init_db_pool
from app.workers.algo_func.get_code_energy import (
    calculate_energy_indicators_last_16_days, StockRecord,
)
from app.workers.algo_func.precomputed_indicators import (
    PrecomputedIndicators, OHLCV as PrecompOHLCV,
)
from app.workers.algo_func.buy_signals import OHLCV
from app.models.algorithm_models import AlgorithmParameters

STOCK = "3888"
START_DATE = os.getenv('OPTIMIZATION_START_DATE', '2016-01-01')
END_DATE = os.getenv('OPTIMIZATION_END_DATE', '2026-02-02')


async def run_validation():
    await init_db_pool()
    params = AlgorithmParameters()

    code_raw = await get_stock_data_from_db(STOCK, END_DATE)
    spy_raw = await get_stock_data_from_db("2800", END_DATE)

    code_data = [OHLCV(b["date"], b["open"], b["high"], b["low"], b["close"], b["volume"])
                 for b in code_raw]
    spy_data = [OHLCV(b["date"], b["open"], b["high"], b["low"], b["close"], b["volume"])
                for b in spy_raw]

    precomp_code = [PrecompOHLCV(b.date, b.open, b.high, b.low, b.close, b.volume) for b in code_data]
    precomp_spy = [PrecompOHLCV(b.date, b.open, b.high, b.low, b.close, b.volume) for b in spy_data]
    precomputed = PrecomputedIndicators(precomp_code, precomp_spy, params)
    precomputed.compute_all()

    # Convert to StockRecord for original energy function
    stock_records = [StockRecord(b.date, b.open, b.high, b.low, b.close, b.volume)
                     for b in code_data]
    spy_records = [StockRecord(b.date, b.open, b.high, b.low, b.close, b.volume)
                   for b in spy_data]

    errors = []
    checked = 0

    # Check every 50th day in the evaluation range
    for idx in range(len(code_data)):
        date_str = code_data[idx].date
        if date_str < START_DATE:
            continue
        if checked % 50 != 0:
            checked += 1
            continue
        checked += 1

        # Original
        orig = calculate_energy_indicators_last_16_days(
            date_str, stock_records[:idx + 1], spy_records
        )
        # Pre-computed
        pre = precomputed.get_energy_data(idx)

        for key in ["E1", "E2", "E3", "E4", "E5"]:
            if str(orig.get(key, "0")) != str(pre.get(key, "0")):
                errors.append(f"{key} mismatch at idx={idx} ({date_str}): "
                              f"orig={orig[key]}, pre={pre[key]}")

        orig_es = orig.get("energy_score", 0)
        pre_es = pre.get("energy_score", 0)
        if abs(float(orig_es) - float(pre_es)) > 1e-10:
            errors.append(f"energy_score mismatch at idx={idx} ({date_str}): "
                          f"orig={orig_es}, pre={pre_es}")

    print(f"\n{'='*60}")
    print(f"Energy parity check: {checked} days checked, {len(errors)} errors")
    if errors:
        for e in errors[:20]:
            print(f"  {e}")
        print("FAIL")
        sys.exit(1)
    else:
        print("PASS — all energy indicators match")


if __name__ == "__main__":
    asyncio.run(run_validation())
```

Run:
```bash
docker cp tests/test_energy_parity.py hk-algo-improve-algorithm-worker-1:/app/tests/
docker-compose exec algorithm-worker python tests/test_energy_parity.py
```

**Gate:** Must print `PASS`. If E2 shows discrepancies, investigate RSI convergence and implement 24-month-windowed RSI fallback if needed.

---

## Phase 7 — Integrate Pre-Computed Sell Path into Algorithm Worker

> **Goal:** Wire the pre-computed sell methods from Phases 5–6 into the main loop, replacing all per-call O(n) sell computations with O(1) lookups.  
> **Expected speedup:** Activates the full speedup from Phases 5+6. Total pipeline ~15–25s per genome (from ~133s).  
> **Files modified:** `algorithm_worker.py`.

---

### Step 7.1 — Add `run_all_sell_conditions_fast()` Method

**File:** `app/workers/algo_func/precomputed_indicators.py`

```python
def run_all_sell_conditions_fast(self, idx: int, buy_idx: int, buy_price: float,
                                  stop_loss: float) -> dict:
    """Run all sell conditions using pre-computed indicators.
    
    Drop-in replacement for sell_signals.runAllSellConditions().
    Returns {"conditions": {...}, "stop_loss": new_stop} — same format.
    """
    # S5 MUST always run — it returns updated stop_loss
    s5_exit, new_stop = self.get_s5_condition(idx, buy_idx, buy_price, stop_loss)

    # Short-circuit evaluation ordered cheapest-to-most-expensive
    ordered_checks = [
        ("S1",  lambda: self.closes[idx] <= stop_loss
                        if isinstance(stop_loss, (int, float))
                           and np.isfinite(stop_loss)
                        else False),
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

---

### Step 7.2 — Update Sell Branch in `signals_for_the_period()`

**File:** `app/workers/algorithm_worker.py`

**Step 7.2.1 — Replace the sell branch**

In `signals_for_the_period()` (around line 320), replace the entire `elif position_status == "I":` block.

**Current code:**
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

**Replace with:**
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

    # Pre-computed sell evaluation — all O(1) lookups
    sellSignals = precomputed.run_all_sell_conditions_fast(
        code_end_idx, buy_idx, to_float_or_none(entry_price), exit1
    )

    # Pre-computed energy data for CSV output
    energy_data = precomputed.get_energy_data(code_end_idx)
```

The rest of the sell branch (after `sellSignals` and `energy_data` are set) remains unchanged:
```python
    sell = isSell(sellSignals['conditions'])
    new_stop_loss = sellSignals['stop_loss']
    result = {
        "code": code,
        "genome_id": genome_id,
        ...
        "E1": energy_data["E1"],
        ...
    }
```

**Key changes:**
1. `calculate_energy_indicators_last_16_days()` call removed entirely.
2. `runAllSellConditions()` replaced with `precomputed.run_all_sell_conditions_fast()`.
3. `buy_idx` obtained via O(1) dict lookup instead of O(n) linear scan (done 7+ times in original).
4. `filtered_code` / `filtered_spy` no longer needed in the sell branch.

**Step 7.2.2 — Handle `buy_idx == -1`**

When `entry_date` is not found in `precomputed.date_to_idx` (e.g., buy happened before data range), `buy_idx` will be -1. All fast sell methods that receive `buy_idx` already return `False` when `buy_idx < 0`, matching the original behavior where `buy_idx == -1` causes the function to return `False`.

---

### Step 7.3 — Remove Unnecessary List Slicing (Optional)

**File:** `app/workers/algorithm_worker.py`

After Phase 7, neither the buy branch (Phase 1) nor the sell branch (Phase 7) uses `filtered_code` or `filtered_spy`. The slicing can be removed from the main loop to save memory allocation:

**Current:**
```python
filtered_spy = spy_data[:spy_end_idx + 1] if spy_end_idx >= 0 else []
filtered_code = code_data[:code_end_idx + 1] if code_end_idx >= 0 else []
```

**Replace with:**
```python
# filtered_spy / filtered_code no longer needed — buy and sell paths use pre-computed index lookups
```

Update any remaining uses:
- `filtered_code[-1].close` → `code_data[code_end_idx].close` (direct O(1) index access).
- `filtered_code` in buy branch result → `code_data[code_end_idx]`.

**Important:** Keep `spy_end_idx` and `code_end_idx` computation — they are still used by pre-computed method calls.

---

### Step 7.4 — Backward Compatibility

Keep `sell_signals.py` and `get_code_energy.py` untouched. The original sell functions remain available as reference implementation and for tests.

- `isSell()` is still used to evaluate the conditions dict from `run_all_sell_conditions_fast()` — keep the import.
- `runAllSellConditions` import can remain but is no longer called in the hot path.
- `calculate_energy_indicators_last_16_days` import can remain but is no longer called in the hot path.

---

### Step 7.5 — Full Pipeline Validation

**Step 7.5.1 — Run the existing sell parity test**

```bash
docker cp tests/test_sell_parity.py hk-algo-improve-algorithm-worker-1:/app/tests/
docker cp tests/test_data/reference/final_trades_reference.csv \
    hk-algo-improve-algorithm-worker-1:/app/tests/test_data/reference/
docker-compose exec algorithm-worker python tests/test_sell_parity.py
```

**Gate:** Must print `PASS` with all 10 trade rows identical to reference.

**Step 7.5.2 — Performance benchmark**

Compare `signals_for_the_period` wall time (logged by `PerformanceProfiler`):

| Component | Before (Phases 1–3) | After (Phases 5–7) |
|---|---|---|
| `precompute_indicators` | ~0.3s (buy only) | ~1–2s (buy + sell + energy) |
| `main_signal_loop` | ~133s (~0.05s/day) | ~10–20s (~0.005s/day) |
| **Total** | **~133s** | **~15–25s** |

The one-time precomputation cost increases by ~1s but per-day cost drops by ~10×.

**Step 7.5.3 — Run full batch (all genomes)**

```bash
# Start Docker environment
docker-compose up -d

# Submit optimization batch and monitor
docker-compose logs -f algorithm-worker
```

Expected total batch time: ~10–15 min (vs ~82 min with Phases 1–3 only).

---

## Summary: Expected Performance After All Phases

| Phase | Change | Speedup Factor |
|-------|--------|---------------|
| 1 — PrecomputedIndicators | Buy path: O(n²) → O(n) precompute + O(1) lookup | ~2–3× |
| 2 — Sell optimization | No sorting, short-circuit, no duplicate energy | ~1.5–2.5× |
| 3 — Loop overhead | No pd.to_datetime, no redundant fetch, no triple convert | ~1.3–1.5× |
| 4 — Concurrency fix | True CPU parallelism per core | ~1× on single genome, better batch throughput |
| 5 — Sell-side ATR arrays | ATR/SMA-TR/rolling windows → O(1) lookups | ~2–3× |
| 6 — Energy pre-compute | E1–E5 + energy_score → O(1) lookups | ~5–10× on sell-day |
| 7 — Integrate sell path | Wire pre-computed sell methods into main loop | Activates Phases 5+6 |

**Cumulative estimate:**
- Per-genome: ~312s → ~133s (Phases 1–3) → ~15–25s (Phases 5–7)
- 37 genomes on 8 cores: ~194 min → ~82 min → ~10–15 min

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
| 5 | `precomputed_indicators.py` | Add sell ATR arrays, SMA-TR, rolling windows, fibo, date map, fast methods |
| 5 | `tests/test_sell_precomputed_parity.py` | New: ATR/rolling array parity test |
| 6 | `precomputed_indicators.py` | Add E1–E5 arrays, energy_score, get_energy_data(), get_s9_condition() |
| 6 | `tests/test_energy_parity.py` | New: energy indicator parity test |
| 7 | `algorithm_worker.py` | Replace sell branch with pre-computed path, remove list slicing |

---

## Rollback Instructions

Each phase modifies a small set of files. To rollback:

1. **Phase 1:** Re-comment the import on line 17 of `algorithm_worker.py`, re-comment the precomputed init block, restore `runAllBuyConditions()` call in the "F" branch.
2. **Phase 2:** Revert `runAllSellConditions()` to the non-short-circuit version, restore `sorted()` calls, remove `energy_data` parameter.
3. **Phase 3:** Restore `pd.to_datetime()` calls, remove `return_ohlcv` parameter, remove data pass-through parameters.
4. **Phase 4:** Set `ALGORITHM_CONCURRENT_TASKS` back to 5, restore per-job event loop creation.
5. **Phase 5:** Remove sell-side arrays and fast sell methods from `precomputed_indicators.py`. No changes to `algorithm_worker.py` required (sell path not yet wired in Phase 5).
6. **Phase 6:** Remove E1–E5 arrays and energy_score from `precomputed_indicators.py`. Remove `get_energy_data()` and `get_s9_condition()`.
7. **Phase 7:** Restore the original sell branch in `algorithm_worker.py`: re-add `calculate_energy_indicators_last_16_days()` call, replace `run_all_sell_conditions_fast()` with `runAllSellConditions()`, re-add `filtered_code`/`filtered_spy` slicing.

Use `git stash` or feature branches per phase for clean rollback points.
