"""
Generate reference outputs from the CURRENT (unmodified) codebase.
Run ONCE before any optimization work begins.
Stores results in tests/test_data/reference/.

Usage:
    python tests/generate_reference.py

Environment variables (optional):
    OPTIMIZATION_START_DATE  default: 2016-01-01
    OPTIMIZATION_END_DATE    default: 2026-02-02
"""
import asyncio
import json
import os
import sys
import shutil
import csv
import traceback

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.workers.algorithm_worker import (
    process_algorithm_task,
    get_data_and_save_to_csv,
    signals_for_the_period,
    format_signals_csv_inplace,
)
from app.workers.algo_func.get_db_data import get_stock_data_from_db, init_db_pool
from app.workers.algo_func.buy_signals import runAllBuyConditions, isBuy, OHLCV
from app.workers.algo_func.sell_signals import runAllSellConditions, isSell
from app.workers.algo_func.get_code_energy import calculate_energy_indicators_last_16_days
from app.models.algorithm_models import AlgorithmParameters
from app.services.file_service import FileService

STOCK = "3888"
GENOME = "G_000"
START_DATE = os.getenv('OPTIMIZATION_START_DATE', '2016-01-01')
END_DATE = os.getenv('OPTIMIZATION_END_DATE', '2026-02-02')
REF_DIR = os.path.join(os.path.dirname(__file__), "test_data", "reference")


def serialize_value(val):
    """Convert non-JSON-serializable values to strings."""
    if val is None:
        return None
    if isinstance(val, (bool,)):
        return val
    if isinstance(val, (int, float)):
        return val
    return str(val)


async def generate_buy_signal_reference(code_data, spy_data, params):
    """Generate per-day buy signal reference records."""
    buy_records = []
    total_days = sum(1 for bar in code_data if bar.date >= START_DATE)
    processed = 0

    for end_idx in range(len(code_data)):
        date_str = code_data[end_idx].date
        if date_str < START_DATE:
            continue

        processed += 1
        if processed % 200 == 0:
            print(f"  Buy signals: {processed}/{total_days} days processed...")

        filtered_code = code_data[:end_idx + 1]

        # Find matching SPY index
        spy_end = -1
        for i in range(len(spy_data) - 1, -1, -1):
            if spy_data[i].date <= date_str:
                spy_end = i
                break
        if spy_end < 0:
            continue

        filtered_spy = spy_data[:spy_end + 1]

        signals = runAllBuyConditions(filtered_code, date_str, filtered_spy, params)
        buy_decision = isBuy(signals)

        record = {
            "date": date_str,
            "idx": end_idx,
            "isBuy": buy_decision,
        }
        # Add all signal keys
        for key, val in signals.items():
            record[key] = serialize_value(val)

        buy_records.append(record)

    return buy_records


async def generate_pipeline_reference():
    """Run the full pipeline and save the final CSV as reference."""
    genome_file = f"{STOCK}_{GENOME}"

    # Run the full pipeline (same as process_algorithm_task does)
    await get_data_and_save_to_csv(STOCK, START_DATE, GENOME, file_name=genome_file)

    params = AlgorithmParameters()
    await signals_for_the_period(STOCK, END_DATE, params, GENOME, file_name=genome_file)

    file_service = FileService()
    await format_signals_csv_inplace(file_service=file_service, file_name=genome_file, genome_id=GENOME)

    # Copy the final CSV into reference folder
    src = f"data/{genome_file}.csv"
    if os.path.exists(src):
        dst = os.path.join(REF_DIR, "final_trades_reference.csv")
        shutil.copy2(src, dst)
        print(f"  Saved final trades reference CSV: {dst}")

        # Count rows for verification
        with open(dst, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            print(f"  Final CSV contains {len(rows)} rows")
            if rows:
                print(f"  Columns: {list(rows[0].keys())}")
                print(f"  First row date: {rows[0].get('tradeday', 'N/A')}")
                print(f"  Last row date:  {rows[-1].get('tradeday', 'N/A')}")
        return True
    else:
        print(f"  ERROR: Expected output file not found: {src}")
        return False


async def generate():
    os.makedirs(REF_DIR, exist_ok=True)
    print(f"Reference output directory: {REF_DIR}")
    print(f"Stock: {STOCK}, Genome: {GENOME}")
    print(f"Date range: {START_DATE} to {END_DATE}")
    print("=" * 60)

    # Initialize DB connection pool
    await init_db_pool()

    # 1. Fetch raw data
    print("\n[1/3] Fetching raw data from DB...")
    code_data_raw = await get_stock_data_from_db(STOCK, END_DATE)
    spy_data_raw = await get_stock_data_from_db("2800", END_DATE)

    print(f"  Stock {STOCK}: {len(code_data_raw)} bars")
    print(f"  SPY (2800):  {len(spy_data_raw)} bars")

    code_data = [
        OHLCV(b["date"], b["open"], b["high"], b["low"], b["close"], b["volume"])
        for b in code_data_raw
    ]
    spy_data = [
        OHLCV(b["date"], b["open"], b["high"], b["low"], b["close"], b["volume"])
        for b in spy_data_raw
    ]

    params = AlgorithmParameters()

    # 2. Generate per-day buy signal reference
    print("\n[2/3] Generating per-day buy signal reference...")
    buy_records = await generate_buy_signal_reference(code_data, spy_data, params)

    buy_ref_path = os.path.join(REF_DIR, "buy_signals_reference.json")
    with open(buy_ref_path, "w", encoding='utf-8') as f:
        json.dump(buy_records, f, indent=2, default=str)

    print(f"  Saved {len(buy_records)} buy-signal reference records: {buy_ref_path}")

    # Count how many days had a buy signal
    buy_true_count = sum(1 for r in buy_records if r.get("isBuy"))
    print(f"  Days with isBuy=True: {buy_true_count}/{len(buy_records)}")

    # 3. Run full pipeline and save final CSV
    print("\n[3/3] Running full pipeline to generate final trades CSV...")
    pipeline_ok = await generate_pipeline_reference()

    # Summary
    print("\n" + "=" * 60)
    print("REFERENCE GENERATION COMPLETE")
    print("=" * 60)

    files_to_check = [
        ("buy_signals_reference.json", buy_ref_path),
        ("final_trades_reference.csv", os.path.join(REF_DIR, "final_trades_reference.csv")),
    ]

    all_ok = True
    for name, path in files_to_check:
        exists = os.path.exists(path)
        size = os.path.getsize(path) if exists else 0
        status = f"OK ({size:,} bytes)" if exists and size > 0 else "MISSING or EMPTY"
        print(f"  {name}: {status}")
        if not exists or size == 0:
            all_ok = False

    if all_ok:
        print("\nAll reference files generated successfully.")
        print("You may now proceed with optimization phases.")
    else:
        print("\nWARNING: Some reference files are missing or empty!")
        print("Do NOT proceed with optimization until all files are valid.")
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(generate())
    except KeyboardInterrupt:
        print("\nAborted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\nFATAL ERROR: {e}")
        traceback.print_exc()
        sys.exit(1)
