"""
Validate that reference files exist and are well-formed.
Run after generate_reference.py to confirm readiness for optimization phases.

Usage:
    python tests/validate_reference.py
"""
import json
import os
import sys
import csv

REF_DIR = os.path.join(os.path.dirname(__file__), "test_data", "reference")

REQUIRED_FILES = {
    "buy_signals_reference.json": "json",
    "final_trades_reference.csv": "csv",
}

BUY_SIGNAL_KEYS = {"date", "idx", "isBuy"}
BUY_CONDITION_KEYS = {"B1", "B3", "B8", "B9", "B10", "B11", "B12", "B13", "B18"}


def validate_buy_signals(path):
    """Validate buy_signals_reference.json structure."""
    with open(path, 'r', encoding='utf-8') as f:
        records = json.load(f)

    assert isinstance(records, list), "Expected a JSON array"
    assert len(records) > 0, "No buy signal records found"

    # Check first record has expected keys
    first = records[0]
    missing_keys = BUY_SIGNAL_KEYS - set(first.keys())
    assert not missing_keys, f"Missing keys in buy signal record: {missing_keys}"

    # Check that at least some condition keys exist
    found_conditions = BUY_CONDITION_KEYS & set(first.keys())
    assert len(found_conditions) > 0, \
        f"No buy condition keys found. Available keys: {list(first.keys())}"

    # Check date ordering
    dates = [r["date"] for r in records]
    assert dates == sorted(dates), "Buy signal records not in date order"

    # Stats
    buy_count = sum(1 for r in records if r.get("isBuy"))
    print(f"  Records: {len(records)}")
    print(f"  Date range: {dates[0]} to {dates[-1]}")
    print(f"  Buy=True days: {buy_count}")
    print(f"  Condition keys present: {sorted(found_conditions)}")

    return True


def validate_trades_csv(path):
    """Validate final_trades_reference.csv structure."""
    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    assert len(rows) > 0, "No rows in final trades CSV"

    columns = list(rows[0].keys())
    print(f"  Rows: {len(rows)}")
    print(f"  Columns ({len(columns)}): {columns[:10]}{'...' if len(columns) > 10 else ''}")

    # Check for tradeday column
    assert "tradeday" in columns or any("date" in c.lower() for c in columns), \
        "No date/tradeday column found in CSV"

    return True


def main():
    print(f"Reference directory: {REF_DIR}")
    print("=" * 60)

    if not os.path.isdir(REF_DIR):
        print(f"FAIL: Reference directory does not exist: {REF_DIR}")
        print("Run 'python tests/generate_reference.py' first.")
        sys.exit(1)

    all_ok = True

    for filename, filetype in REQUIRED_FILES.items():
        path = os.path.join(REF_DIR, filename)
        print(f"\nChecking {filename}...")

        if not os.path.exists(path):
            print(f"  FAIL: File not found")
            all_ok = False
            continue

        size = os.path.getsize(path)
        if size == 0:
            print(f"  FAIL: File is empty")
            all_ok = False
            continue

        print(f"  Size: {size:,} bytes")

        try:
            if filetype == "json":
                validate_buy_signals(path)
            elif filetype == "csv":
                validate_trades_csv(path)
            print(f"  PASS")
        except Exception as e:
            print(f"  FAIL: {e}")
            all_ok = False

    print("\n" + "=" * 60)
    if all_ok:
        print("ALL CHECKS PASSED — reference data is ready.")
        print("You may proceed with optimization phases.")
    else:
        print("SOME CHECKS FAILED — fix issues before proceeding.")
        sys.exit(1)


if __name__ == "__main__":
    main()
