"""
Validates that PrecomputedIndicators produces identical buy signals
to the original runAllBuyConditions for every trading day.

Usage:
    python tests/test_precomputed_buy_parity.py

Gate: Must print 'PASS — all buy signals match' with 0 mismatches before proceeding.
"""
import asyncio
import os
import sys
import json
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.workers.algo_func.get_db_data import get_stock_data_from_db, init_db_pool
from app.workers.algo_func.buy_signals import (
    runAllBuyConditions, isBuy, OHLCV as BuyOHLCV,
)
from app.workers.algo_func.precomputed_indicators import (
    PrecomputedIndicators, is_buy_fast, OHLCV as PrecompOHLCV,
)
from app.models.algorithm_models import AlgorithmParameters

STOCK = os.getenv('OPTIMIZATION_STOCK', '3888')
START_DATE = os.getenv('OPTIMIZATION_START_DATE', '2016-01-01')
END_DATE = os.getenv('OPTIMIZATION_END_DATE', '2026-02-02')
STOP_LOSS_TOLERANCE = 0.0001


def ohlcv_buy_to_precomp(bars):
    """Convert buy_signals OHLCV to precomputed OHLCV."""
    return [PrecompOHLCV(b.date, b.open, b.high, b.low, b.close, b.volume) for b in bars]


async def run_validation():
    await init_db_pool()
    params = AlgorithmParameters()

    print(f"Stock: {STOCK}, Date range: {START_DATE} to {END_DATE}")
    print("Fetching data...")

    code_raw = await get_stock_data_from_db(STOCK, END_DATE)
    spy_raw = await get_stock_data_from_db("2800", END_DATE)

    code_data = [BuyOHLCV(b["date"], b["open"], b["high"], b["low"], b["close"], b["volume"])
                 for b in code_raw]
    spy_data = [BuyOHLCV(b["date"], b["open"], b["high"], b["low"], b["close"], b["volume"])
                for b in spy_raw]

    print(f"Stock bars: {len(code_data)}, SPY bars: {len(spy_data)}")

    # Build precomputed indicators
    print("Building precomputed indicators...")
    t0 = time.time()
    precomp_code = ohlcv_buy_to_precomp(code_data)
    precomp_spy = ohlcv_buy_to_precomp(spy_data)
    precomputed = PrecomputedIndicators(precomp_code, precomp_spy, params)
    precomputed.compute_all()
    precomp_time = time.time() - t0
    print(f"Precomputation took {precomp_time:.2f}s")

    mismatches = []
    total_compared = 0
    buy_condition_keys = ['B1', 'B3', 'B8', 'B9', 'B10', 'B11', 'B12', 'B13', 'B18']
    isbuy_mismatches = 0

    total_original_time = 0.0
    total_precomp_time = 0.0

    total_days = sum(1 for bar in code_data if bar.date >= START_DATE)
    print(f"Comparing {total_days} trading days...")

    for idx in range(len(code_data)):
        date_str = code_data[idx].date
        if date_str < START_DATE:
            continue

        total_compared += 1

        if total_compared % 500 == 0:
            print(f"  Progress: {total_compared}/{total_days} days...")

        # --- Original path ---
        t1 = time.time()
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
        original_buy = isBuy(original)
        t2 = time.time()
        total_original_time += (t2 - t1)

        # --- Precomputed path ---
        t3 = time.time()
        precomp = precomputed.run_all_buy_conditions_fast(idx)
        precomp_buy = is_buy_fast(precomp)
        t4 = time.time()
        total_precomp_time += (t4 - t3)

        # Compare isBuy decisions
        if original_buy != precomp_buy:
            isbuy_mismatches += 1

        # Compare individual boolean conditions
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
        elif (orig_sl is None) != (pre_sl is None):
            mismatches.append({
                "idx": idx, "date": date_str, "key": "stopLoss",
                "original": orig_sl, "precomputed": pre_sl,
            })

    print(f"\n{'='*60}")
    print(f"RESULTS")
    print(f"{'='*60}")
    print(f"Total days compared:    {total_compared}")
    print(f"Condition mismatches:   {len(mismatches)}")
    print(f"isBuy() mismatches:     {isbuy_mismatches}")
    print(f"Original total time:    {total_original_time:.2f}s")
    print(f"Precomputed total time: {total_precomp_time:.2f}s (+ {precomp_time:.2f}s init)")
    if total_original_time > 0:
        speedup = total_original_time / (total_precomp_time + precomp_time)
        print(f"Speedup:                {speedup:.1f}x")

    if mismatches:
        print(f"\nFirst 20 mismatches:")
        for m in mismatches[:20]:
            print(f"  Day {m['idx']} ({m['date']}): {m['key']} "
                  f"original={m['original']} precomputed={m['precomputed']}")

        # Group mismatches by condition key for summary
        from collections import Counter
        key_counts = Counter(m['key'] for m in mismatches)
        print(f"\nMismatches by condition:")
        for key, count in key_counts.most_common():
            print(f"  {key}: {count}")

        print(f"\nFAIL — {len(mismatches)} mismatches detected")
        sys.exit(1)
    else:
        print("\nPASS — all buy signals match")


if __name__ == "__main__":
    asyncio.run(run_validation())
