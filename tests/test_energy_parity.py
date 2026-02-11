"""
Validates that pre-computed energy indicators match the original
calculate_energy_indicators_last_16_days() for sampled sell-days.

Usage:
    python tests/test_energy_parity.py

Gate: Must print 'PASS' with 0 errors.
"""
import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.workers.algo_func.get_db_data import get_stock_data_from_db, init_db_pool
from app.workers.algo_func.get_code_energy import calculate_energy_indicators_last_16_days
from app.workers.algo_func.precomputed_indicators import (
    PrecomputedIndicators, OHLCV as PrecompOHLCV,
)
from app.workers.algo_func.buy_signals import OHLCV
from app.models.algorithm_models import AlgorithmParameters

STOCK = os.getenv('OPTIMIZATION_STOCK', '3888')
START_DATE = os.getenv('OPTIMIZATION_START_DATE', '2016-01-01')
END_DATE = os.getenv('OPTIMIZATION_END_DATE', '2026-02-02')
SAMPLE_STEP = 50  # Check every Nth day
SCORE_TOLERANCE = 1e-10


async def run_validation():
    await init_db_pool()
    params = AlgorithmParameters()

    print(f"Stock: {STOCK}, Date range: {START_DATE} to {END_DATE}")
    print("Fetching data...")

    code_raw = await get_stock_data_from_db(STOCK, END_DATE)
    spy_raw = await get_stock_data_from_db("2800", END_DATE)

    code_data = [OHLCV(b["date"], b["open"], b["high"], b["low"], b["close"], b["volume"])
                 for b in code_raw]
    spy_data = [OHLCV(b["date"], b["open"], b["high"], b["low"], b["close"], b["volume"])
                for b in spy_raw]

    print(f"Stock bars: {len(code_data)}, SPY bars: {len(spy_data)}")
    print("Building precomputed indicators...")

    t0 = time.time()
    precomp_code = [PrecompOHLCV(b.date, b.open, b.high, b.low, b.close, b.volume) for b in code_data]
    precomp_spy = [PrecompOHLCV(b.date, b.open, b.high, b.low, b.close, b.volume) for b in spy_data]
    precomputed = PrecomputedIndicators(precomp_code, precomp_spy, params)
    precomputed.compute_all()
    build_time = time.time() - t0
    print(f"Precomputation took {build_time:.2f}s")

    errors = []
    checked = 0
    sample_count = 0

    for idx in range(len(code_data)):
        date_str = code_data[idx].date
        if date_str < START_DATE:
            continue

        checked += 1
        if (checked - 1) % SAMPLE_STEP != 0:
            continue
        sample_count += 1

        # Original energy computation
        orig = calculate_energy_indicators_last_16_days(
            date_str, code_data[:idx + 1], spy_data
        )

        # Pre-computed energy
        pre = precomputed.get_energy_data(idx)

        # Compare E1–E5
        for key in ["E1", "E2", "E3", "E4", "E5"]:
            orig_val = str(orig.get(key, "0"))
            pre_val = str(pre.get(key, "0"))
            # Handle "N/A" from original — treat as "0" for comparison
            if orig_val == "N/A":
                orig_val = "0"
            if orig_val != pre_val:
                errors.append(f"{key} mismatch at idx={idx} ({date_str}): "
                              f"orig={orig.get(key)}, pre={pre.get(key)}")

        # Compare energy_score
        orig_es = float(orig.get("energy_score", 0))
        pre_es = float(pre.get("energy_score", 0))
        if abs(orig_es - pre_es) > SCORE_TOLERANCE:
            errors.append(f"energy_score mismatch at idx={idx} ({date_str}): "
                          f"orig={orig_es}, pre={pre_es}")

    print(f"\n{'='*60}")
    print(f"Total days in range: {checked}")
    print(f"Days sampled (every {SAMPLE_STEP}th): {sample_count}")
    print(f"Errors found: {len(errors)}")

    if errors:
        # Group errors by indicator key
        from collections import Counter
        key_counts = Counter(e.split(" ")[0] for e in errors)
        print(f"\nErrors by indicator:")
        for key, count in key_counts.most_common():
            print(f"  {key}: {count}")

        print(f"\nFirst 30 errors:")
        for e in errors[:30]:
            print(f"  {e}")
        print(f"\nFAIL — {len(errors)} errors detected")
        sys.exit(1)
    else:
        print("PASS — all energy indicators match")


if __name__ == "__main__":
    asyncio.run(run_validation())
