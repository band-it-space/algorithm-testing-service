"""
Check data availability from StockFisher API for specified stock codes.
Verifies date range coverage from 2016 to 2026.
"""
import os
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv('API_KEY')
STOCK_CODES = ["700", "9988", "3690", "1810", "1024", "2269", "1299", "2318", "1211", "9868"]
REQUIRED_START = 2016
REQUIRED_END = 2026


def fetch_stock_data(code: str) -> list[dict]:
    """Fetch raw stock data from API."""
    url = f'http://ete.stockfisher.com.hk/v1.1/debugHKEX/verifyData?TradeDay=&Code={code}&verifyType=price'
    headers = {'x-api-key': API_KEY}

    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"  ERROR fetching {code}: {e}")
        return []


def analyze_data(code: str, raw_data: list[dict]) -> None:
    """Analyze and report data availability for a stock code."""
    if not raw_data:
        print(f"  {code}: NO DATA RETURNED")
        return

    # Parse dates and filter valid records
    dates = []
    for row in raw_data:
        try:
            trade_date = datetime.fromisoformat(row["TradeDay"].replace('Z', '+00:00'))
            adj_close = row.get("adj_close") or 0
            if adj_close > 0:
                dates.append(trade_date)
        except (KeyError, ValueError):
            continue

    if not dates:
        print(f"  {code}: NO VALID RECORDS (all adj_close=0 or missing)")
        return

    dates.sort()
    min_date = dates[0]
    max_date = dates[-1]

    # Check year coverage
    years_present = sorted(set(d.year for d in dates))
    required_years = list(range(REQUIRED_START, REQUIRED_END + 1))
    missing_years = [y for y in required_years if y not in years_present]

    # Count records per year
    year_counts = {}
    for d in dates:
        year_counts[d.year] = year_counts.get(d.year, 0) + 1

    # Status
    has_full_coverage = len(missing_years) == 0
    status = "OK" if has_full_coverage else "GAPS"

    print(f"\n  Stock {code}: [{status}]")
    print(f"    Total valid records: {len(dates)}")
    print(f"    Date range: {min_date.strftime('%Y-%m-%d')} to {max_date.strftime('%Y-%m-%d')}")
    print(f"    Years with data: {years_present[0]}–{years_present[-1]}")

    if missing_years:
        print(f"    MISSING years (2016-2026): {missing_years}")

    # Per-year breakdown
    print(f"    Per-year record counts:")
    for year in range(REQUIRED_START, REQUIRED_END + 1):
        count = year_counts.get(year, 0)
        marker = "" if count > 0 else " <-- MISSING"
        print(f"      {year}: {count:>4} trading days{marker}")


def main():
    if not API_KEY or API_KEY == "your_api_key_here":
        print("ERROR: API_KEY not set in .env file")
        return

    print(f"Checking data availability for {len(STOCK_CODES)} stock codes")
    print(f"Required range: {REQUIRED_START}–{REQUIRED_END}")
    print("=" * 60)

    for code in STOCK_CODES:
        print(f"\nFetching stock {code}...", end="", flush=True)
        raw_data = fetch_stock_data(code)
        analyze_data(code, raw_data)

    print("\n" + "=" * 60)
    print("Done.")


if __name__ == "__main__":
    main()
