"""
Validates that the optimized sell path produces identical isSell() decisions
and final trade outputs to the reference (unoptimized) pipeline run.

Usage:
    python tests/test_sell_parity.py

Gate: Must print 'PASS' with all trade rows identical to reference.
"""
import asyncio
import os
import sys
import csv
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.workers.algorithm_worker import process_algorithm_task

STOCK = os.getenv('OPTIMIZATION_STOCK', '3888')
GENOME = os.getenv('OPTIMIZATION_GENOME', 'G_000')
REF_PATH = os.path.join("tests", "test_data", "reference", "final_trades_reference.csv")


def load_csv(path):
    with open(path, 'r', encoding='utf-8') as f:
        return list(csv.DictReader(f))


async def run_validation():
    if not os.path.exists(REF_PATH):
        print(f"ERROR: Reference file not found: {REF_PATH}")
        print("Run 'python tests/generate_reference.py' first.")
        sys.exit(1)

    print(f"Stock: {STOCK}, Genome: {GENOME}")
    print(f"Reference: {REF_PATH}")
    print("Running full pipeline...")

    t0 = time.time()
    task = {
        'task_id': 'validation_phase2_sell',
        'stock': STOCK,
        'genome_id': GENOME,
        'parameters': {},
    }
    await process_algorithm_task(task)
    elapsed = time.time() - t0
    print(f"Pipeline completed in {elapsed:.1f}s")

    output_path = f"data/{STOCK}_{GENOME}.csv"
    if not os.path.exists(output_path):
        print(f"ERROR: Output file not found: {output_path}")
        sys.exit(1)

    ref = load_csv(REF_PATH)
    new = load_csv(output_path)

    print(f"Reference rows: {len(ref)}")
    print(f"New output rows: {len(new)}")

    if len(ref) != len(new):
        print(f"FAIL — Row count differs: {len(ref)} vs {len(new)}")
        sys.exit(1)

    mismatches = []
    for i, (r, n) in enumerate(zip(ref, new)):
        for col in r:
            if r[col] != n.get(col):
                mismatches.append({
                    "row": i,
                    "col": col,
                    "reference": r[col],
                    "new": n.get(col),
                    "date": r.get("tradeday", "?"),
                })

    if mismatches:
        print(f"\nFAIL — {len(mismatches)} cell mismatches detected")
        print(f"\nFirst 20 mismatches:")
        for m in mismatches[:20]:
            print(f"  Row {m['row']} ({m['date']}), col '{m['col']}': "
                  f"ref='{m['reference']}' vs new='{m['new']}'")
        sys.exit(1)
    else:
        print(f"\nPASS — sell path optimization produces identical output ({len(ref)} rows verified)")


if __name__ == "__main__":
    asyncio.run(run_validation())
