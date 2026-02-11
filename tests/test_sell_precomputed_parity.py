"""
Validates that pre-computed sell indicator arrays produce values identical
to the original per-call computations for every sampled day.

Usage:
    python tests/test_sell_precomputed_parity.py

Gate: Must print 'PASS' with 0 errors.
"""
import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import numpy as np
from app.workers.algo_func.get_db_data import get_stock_data_from_db, init_db_pool
from app.workers.algo_func.sell_signals import atr, calc_tr_series, sma
from app.workers.algo_func.precomputed_indicators import (
    PrecomputedIndicators, OHLCV as PrecompOHLCV,
)
from app.workers.algo_func.buy_signals import OHLCV
from app.models.algorithm_models import AlgorithmParameters

STOCK = os.getenv('OPTIMIZATION_STOCK', '3888')
END_DATE = os.getenv('OPTIMIZATION_END_DATE', '2026-02-02')
TOLERANCE = 1e-8
SAMPLE_STEP = 100  # Check every Nth index


async def run_validation():
    await init_db_pool()
    params = AlgorithmParameters()

    print(f"Stock: {STOCK}, End date: {END_DATE}")
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

    for idx in range(200, len(code_data), SAMPLE_STEP):
        ohlcv_slice = code_data[:idx + 1]
        checked += 1

        # --- Wilder's ATR(20) — S5 ---
        try:
            orig_atr20_arr = atr(ohlcv_slice, 20)
            if orig_atr20_arr and len(orig_atr20_arr) > 0:
                orig_atr20 = orig_atr20_arr[-1]
                pre_atr20 = precomputed.atr_s5[idx]
                if not np.isnan(pre_atr20) and abs(orig_atr20 - pre_atr20) > TOLERANCE:
                    errors.append(f"ATR(20) idx={idx}: orig={orig_atr20}, pre={pre_atr20}")
        except Exception as e:
            errors.append(f"ATR(20) idx={idx}: exception {e}")

        # --- Wilder's ATR(22) — S7/S16 ---
        try:
            orig_atr22_arr = atr(ohlcv_slice, 22)
            if orig_atr22_arr and len(orig_atr22_arr) > 0:
                orig_atr22 = orig_atr22_arr[-1]
                pre_atr22 = precomputed.atr_s7[idx]
                if not np.isnan(pre_atr22) and abs(orig_atr22 - pre_atr22) > TOLERANCE:
                    errors.append(f"ATR(22) idx={idx}: orig={orig_atr22}, pre={pre_atr22}")
        except Exception as e:
            errors.append(f"ATR(22) idx={idx}: exception {e}")

        # --- Wilder's ATR(10) — S10 ---
        try:
            orig_atr10_arr = atr(ohlcv_slice, 10)
            if orig_atr10_arr and len(orig_atr10_arr) > 0:
                orig_atr10 = orig_atr10_arr[-1]
                pre_atr10 = precomputed.atr_10[idx]
                if not np.isnan(pre_atr10) and abs(orig_atr10 - pre_atr10) > TOLERANCE:
                    errors.append(f"ATR(10) idx={idx}: orig={orig_atr10}, pre={pre_atr10}")
        except Exception as e:
            errors.append(f"ATR(10) idx={idx}: exception {e}")

        # --- Wilder's ATR(100) — S10 ---
        try:
            orig_atr100_arr = atr(ohlcv_slice, 100)
            if orig_atr100_arr and len(orig_atr100_arr) > 0:
                orig_atr100 = orig_atr100_arr[-1]
                pre_atr100 = precomputed.atr_100[idx]
                if not np.isnan(pre_atr100) and abs(orig_atr100 - pre_atr100) > TOLERANCE:
                    errors.append(f"ATR(100) idx={idx}: orig={orig_atr100}, pre={pre_atr100}")
        except Exception as e:
            errors.append(f"ATR(100) idx={idx}: exception {e}")

        # --- SMA-TR(22) — S8 ---
        try:
            trs = calc_tr_series(ohlcv_slice)
            orig_sma22_arr = sma(trs, 22)
            if orig_sma22_arr and len(orig_sma22_arr) > 0:
                orig_sma22 = orig_sma22_arr[-1]
                pre_sma22 = precomputed.sma_tr_22[idx]
                if not np.isnan(pre_sma22) and abs(orig_sma22 - pre_sma22) > TOLERANCE:
                    errors.append(f"SMA-TR(22) idx={idx}: orig={orig_sma22}, pre={pre_sma22}")
        except Exception as e:
            errors.append(f"SMA-TR(22) idx={idx}: exception {e}")

        # --- SMA-TR(100) — S8 ---
        try:
            trs = calc_tr_series(ohlcv_slice)
            orig_sma100_arr = sma(trs, 100)
            if orig_sma100_arr and len(orig_sma100_arr) > 0:
                orig_sma100 = orig_sma100_arr[-1]
                pre_sma100 = precomputed.sma_tr_100[idx]
                if not np.isnan(pre_sma100) and abs(orig_sma100 - pre_sma100) > TOLERANCE:
                    errors.append(f"SMA-TR(100) idx={idx}: orig={orig_sma100}, pre={pre_sma100}")
        except Exception as e:
            errors.append(f"SMA-TR(100) idx={idx}: exception {e}")

    # --- Verify date_to_idx map ---
    for i, bar in enumerate(code_data):
        mapped = precomputed.date_to_idx.get(bar.date)
        if mapped != i:
            errors.append(f"date_to_idx[{bar.date}] = {mapped}, expected {i}")
            if len(errors) > 50:
                break

    print(f"\n{'='*60}")
    print(f"Indices checked: {checked} (every {SAMPLE_STEP}th from 200 to {len(code_data)})")
    print(f"Errors found: {len(errors)}")

    if errors:
        print(f"\nFirst 30 errors:")
        for e in errors[:30]:
            print(f"  {e}")
        print(f"\nFAIL — {len(errors)} errors detected")
        sys.exit(1)
    else:
        print("PASS — all ATR/rolling arrays match")


if __name__ == "__main__":
    asyncio.run(run_validation())
