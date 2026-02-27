"""
Compare results_orig_aggregated.csv (original API signals) with
results_new.csv (optimized algo results). Generates results_comparation.csv
with per-trade buy/sell match analysis for debugging optimized logic.
"""
import pandas as pd
import numpy as np

ORIG_FILE = "data/Comparation 4/results_orig.csv"
NEW_FILE = "data/Comparation 4/results_new.csv"
OUTPUT_FILE = "data/Comparation 4/results_comparation.csv"


def compare_results():
    orig = pd.read_csv(ORIG_FILE)
    new = pd.read_csv(NEW_FILE)

    orig_stocks = set(orig["symbol"].unique())
    new_stocks = set(new["symbol"].unique())
    common = sorted(orig_stocks & new_stocks)

    rows = []

    for stock in common:
        o_trades = orig[orig["symbol"] == stock].sort_values("entryDay").reset_index(drop=True)
        n_trades = new[new["symbol"] == stock].sort_values("entryDay").reset_index(drop=True)

        o_entries = set(o_trades["entryDay"].values)
        n_entries = set(n_trades["entryDay"].values)

        # --- Matched: same buy date in both ---
        for _, o in o_trades.iterrows():
            n_match = n_trades[n_trades["entryDay"] == o["entryDay"]]
            if len(n_match) > 0:
                n = n_match.iloc[0]

                entry_price_diff = round(n["entryPrice"] - o["entryPrice"], 4)
                exit_price_diff = None
                exit_day_diff_days = None

                o_exit_dt = pd.to_datetime(o["exitDay"], errors="coerce")
                n_exit_dt = pd.to_datetime(n["exitDay"], errors="coerce")

                if pd.notna(o_exit_dt) and pd.notna(n_exit_dt):
                    exit_day_diff_days = (n_exit_dt - o_exit_dt).days
                    try:
                        exit_price_diff = round(float(n["exitPrice"]) - float(o["exitPrice"]), 4)
                    except (ValueError, TypeError):
                        exit_price_diff = None

                buy_match = "exact" if abs(entry_price_diff) < 0.01 else (
                    "close" if abs(entry_price_diff) < 0.1 else "different"
                )

                if o["exitDay"] == n["exitDay"]:
                    sell_match = "exact"
                elif exit_day_diff_days is not None and abs(exit_day_diff_days) <= 2:
                    sell_match = "close (±2d)"
                elif exit_day_diff_days is not None and abs(exit_day_diff_days) <= 5:
                    sell_match = "close (±5d)"
                elif pd.isna(n_exit_dt):
                    sell_match = "new_open"
                elif pd.isna(o_exit_dt):
                    sell_match = "orig_open"
                else:
                    sell_match = "different"

                o_dir = "win" if o["Profit %"] > 0 else ("lose" if o["Profit %"] < 0 else "even")
                n_dir = "win" if n["Profit %"] > 0 else ("lose" if n["Profit %"] < 0 else "even")
                direction_match = o_dir == n_dir

                rows.append({
                    "symbol": stock,
                    "match_type": "matched",
                    "buy_match": buy_match,
                    "sell_match": sell_match,
                    "direction_match": direction_match,
                    "orig_entryDay": o["entryDay"],
                    "new_entryDay": n["entryDay"],
                    "orig_entryPrice": o["entryPrice"],
                    "new_entryPrice": n["entryPrice"],
                    "entry_price_diff": entry_price_diff,
                    "orig_exitDay": o["exitDay"],
                    "new_exitDay": n["exitDay"],
                    "exit_day_diff_days": exit_day_diff_days,
                    "orig_exitPrice": o["exitPrice"],
                    "new_exitPrice": n["exitPrice"],
                    "exit_price_diff": exit_price_diff,
                    "orig_profit_pct": o["Profit %"],
                    "new_profit_pct": n["Profit %"],
                    "profit_pct_diff": round(n["Profit %"] - o["Profit %"], 2),
                    "orig_profit": o["profit"],
                    "new_profit": n["profit"],
                    "orig_direction": o_dir,
                    "new_direction": n_dir,
                })
            else:
                # --- Buy in original only (missing in optimized) ---
                o_dir = "win" if o["Profit %"] > 0 else ("lose" if o["Profit %"] < 0 else "even")
                rows.append({
                    "symbol": stock,
                    "match_type": "orig_only",
                    "buy_match": "missing_in_new",
                    "sell_match": "missing_in_new",
                    "direction_match": None,
                    "orig_entryDay": o["entryDay"],
                    "new_entryDay": None,
                    "orig_entryPrice": o["entryPrice"],
                    "new_entryPrice": None,
                    "entry_price_diff": None,
                    "orig_exitDay": o["exitDay"],
                    "new_exitDay": None,
                    "exit_day_diff_days": None,
                    "orig_exitPrice": o["exitPrice"],
                    "new_exitPrice": None,
                    "exit_price_diff": None,
                    "orig_profit_pct": o["Profit %"],
                    "new_profit_pct": None,
                    "profit_pct_diff": None,
                    "orig_profit": o["profit"],
                    "new_profit": None,
                    "orig_direction": o_dir,
                    "new_direction": None,
                })

        # --- Buy in optimized only (missing in original) ---
        for _, n in n_trades.iterrows():
            if n["entryDay"] not in o_entries:
                n_dir = "win" if n["Profit %"] > 0 else ("lose" if n["Profit %"] < 0 else "even")
                rows.append({
                    "symbol": stock,
                    "match_type": "new_only",
                    "buy_match": "missing_in_orig",
                    "sell_match": "missing_in_orig",
                    "direction_match": None,
                    "orig_entryDay": None,
                    "new_entryDay": n["entryDay"],
                    "orig_entryPrice": None,
                    "new_entryPrice": n["entryPrice"],
                    "entry_price_diff": None,
                    "orig_exitDay": None,
                    "new_exitDay": n["exitDay"],
                    "exit_day_diff_days": None,
                    "orig_exitPrice": None,
                    "new_exitPrice": n["exitPrice"],
                    "exit_price_diff": None,
                    "orig_profit_pct": None,
                    "new_profit_pct": n["Profit %"],
                    "profit_pct_diff": None,
                    "orig_profit": None,
                    "new_profit": n["profit"],
                    "orig_direction": None,
                    "new_direction": n_dir,
                })

    result = pd.DataFrame(rows)
    result = result.sort_values(["symbol", "orig_entryDay", "new_entryDay"]).reset_index(drop=True)
    result.to_csv(OUTPUT_FILE, index=False)

    # --- Print summary ---
    print("=" * 70)
    print("COMPARISON RESULTS")
    print("=" * 70)

    matched = result[result["match_type"] == "matched"]
    orig_only = result[result["match_type"] == "orig_only"]
    new_only = result[result["match_type"] == "new_only"]

    print(f"\nTotal rows:              {len(result)}")
    print(f"Matched trades:          {len(matched)}")
    print(f"Original only:           {len(orig_only)}")
    print(f"Optimized only:          {len(new_only)}")

    print(f"\n--- BUY SIGNAL MATCHING ---")
    buy_counts = matched["buy_match"].value_counts()
    for k, v in buy_counts.items():
        print(f"  {k:<20} {v:>5} ({v / len(matched) * 100:.1f}%)")

    print(f"\n--- SELL SIGNAL MATCHING ---")
    sell_counts = matched["sell_match"].value_counts()
    for k, v in sell_counts.items():
        print(f"  {k:<20} {v:>5} ({v / len(matched) * 100:.1f}%)")

    print(f"\n--- DIRECTION MATCH ---")
    dir_match = matched["direction_match"].sum()
    dir_mismatch = len(matched) - dir_match
    print(f"  Same direction:    {dir_match:>5} ({dir_match / len(matched) * 100:.1f}%)")
    print(f"  Different:         {dir_mismatch:>5} ({dir_mismatch / len(matched) * 100:.1f}%)")

    print(f"\n--- PERFORMANCE METRICS ---")
    orig_closed = orig[~orig["exitDay"].isin(["Open", "Open position"]) & orig["exitDay"].notna()]
    new_closed = new[~new["exitDay"].isin(["Open", "Open position"]) & new["exitDay"].notna()]

    for label, df in [("Original", orig_closed), ("Optimized", new_closed)]:
        winning = (df["profit"] > 0).sum()
        losing = (df["profit"] < 0).sum()
        wr = winning / len(df) * 100 if len(df) > 0 else 0
        avg_win = df[df["profit"] > 0]["profit"].mean() if winning > 0 else 0
        avg_loss = df[df["profit"] < 0]["profit"].mean() if losing > 0 else 0
        wl_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else 0
        total = df["profit"].sum()
        print(f"\n  {label}:")
        print(f"    Trades: {len(df)}, Win: {winning}, Lose: {losing}, WR: {wr:.2f}%")
        print(f"    Avg win: ${avg_win:.2f}, Avg loss: ${avg_loss:.2f}, W/L ratio: {wl_ratio:.2f}")
        print(f"    Total profit: ${total:.2f}")

    # --- Sell-specific problem analysis ---
    sell_diff = matched[matched["sell_match"] == "different"]
    if len(sell_diff) > 0:
        print(f"\n--- SELL PROBLEMS (different exit date) ---")
        print(f"  Total: {len(sell_diff)}")
        worse = sell_diff[sell_diff["profit_pct_diff"] < 0]
        better = sell_diff[sell_diff["profit_pct_diff"] > 0]
        print(f"  New worse than orig:  {len(worse)}")
        print(f"  New better than orig: {len(better)}")
        if len(worse) > 0:
            print(f"  Avg loss from sell diff: {worse['profit_pct_diff'].mean():.2f}%")
        if len(better) > 0:
            print(f"  Avg gain from sell diff: {better['profit_pct_diff'].mean():.2f}%")

    dir_mismatch_df = matched[matched["direction_match"] == False]
    if len(dir_mismatch_df) > 0:
        print(f"\n--- DIRECTION MISMATCH DETAIL ---")
        print(f"  Total: {len(dir_mismatch_df)}")
        orig_win_new_lose = dir_mismatch_df[
            (dir_mismatch_df["orig_direction"] == "win") & (dir_mismatch_df["new_direction"] == "lose")
        ]
        orig_lose_new_win = dir_mismatch_df[
            (dir_mismatch_df["orig_direction"] == "lose") & (dir_mismatch_df["new_direction"] == "win")
        ]
        print(f"  Orig win -> New lose: {len(orig_win_new_lose)}")
        print(f"  Orig lose -> New win: {len(orig_lose_new_win)}")

    print(f"\nResults saved to {OUTPUT_FILE}")

    # --- Generate summary CSV ---
    generate_summary(orig, new, result)


def generate_summary(orig, new, comparison):
    """Generate results_summary.csv with key statistics."""
    SUMMARY_FILE = "data/Comparation 4/results_summary.csv"

    orig_closed = orig[~orig["exitDay"].isin(["Open", "Open position"]) & orig["exitDay"].notna()]
    new_closed = new[~new["exitDay"].isin(["Open", "Open position"]) & new["exitDay"].notna()]

    matched = comparison[comparison["match_type"] == "matched"]
    orig_only = comparison[comparison["match_type"] == "orig_only"]
    new_only = comparison[comparison["match_type"] == "new_only"]

    def stats(df):
        winning = (df["profit"] > 0).sum()
        losing = (df["profit"] < 0).sum()
        wr = round(winning / len(df) * 100, 2) if len(df) > 0 else 0
        avg_win = round(df[df["profit"] > 0]["profit"].mean(), 2) if winning > 0 else 0
        avg_loss = round(df[df["profit"] < 0]["profit"].mean(), 2) if losing > 0 else 0
        wl = round(abs(avg_win / avg_loss), 2) if avg_loss != 0 else 0
        return {
            "trades": len(df), "winning": winning, "losing": losing,
            "win_rate": wr, "avg_win": avg_win, "avg_loss": avg_loss,
            "wl_ratio": wl, "total_profit": round(df["profit"].sum(), 2),
        }

    o = stats(orig_closed)
    n = stats(new_closed)

    buy_exact = (matched["buy_match"] == "exact").sum()
    buy_close = (matched["buy_match"] == "close").sum()
    buy_diff = (matched["buy_match"] == "different").sum()

    sell_exact = (matched["sell_match"] == "exact").sum()
    sell_close_2 = (matched["sell_match"] == "close (±2d)").sum()
    sell_close_5 = (matched["sell_match"] == "close (±5d)").sum()
    sell_diff = (matched["sell_match"] == "different").sum()

    dir_same = (matched["direction_match"] == True).sum()
    dir_diff = (matched["direction_match"] == False).sum()

    rows = [
        ("", "Original", "Optimized"),
        ("Total Trades", o["trades"], n["trades"]),
        ("Open Trades", len(orig) - len(orig_closed), len(new) - len(new_closed)),
        ("Unique Stocks", orig["symbol"].nunique(), new["symbol"].nunique()),
        ("Winning Trades", o["winning"], n["winning"]),
        ("Losing Trades", o["losing"], n["losing"]),
        ("Win Rate (%)", o["win_rate"], n["win_rate"]),
        ("Avg Winning Trade ($)", o["avg_win"], n["avg_win"]),
        ("Avg Losing Trade ($)", o["avg_loss"], n["avg_loss"]),
        ("Win/Loss Ratio", o["wl_ratio"], n["wl_ratio"]),
        ("Total Profit ($)", o["total_profit"], n["total_profit"]),
        ("", "", ""),
        ("Comparison", "Count", "% of Matched"),
        ("Matched Trades", len(matched), ""),
        ("Original Only Trades", len(orig_only), ""),
        ("Optimized Only Trades", len(new_only), ""),
        ("", "", ""),
        ("Buy Match - Exact", buy_exact, f"{buy_exact / len(matched) * 100:.1f}%"),
        ("Buy Match - Close", buy_close, f"{buy_close / len(matched) * 100:.1f}%"),
        ("Buy Match - Different", buy_diff, f"{buy_diff / len(matched) * 100:.1f}%"),
        ("", "", ""),
        ("Sell Match - Exact", sell_exact, f"{sell_exact / len(matched) * 100:.1f}%"),
        ("Sell Match - Close (±2d)", sell_close_2, f"{sell_close_2 / len(matched) * 100:.1f}%"),
        ("Sell Match - Close (±5d)", sell_close_5, f"{sell_close_5 / len(matched) * 100:.1f}%"),
        ("Sell Match - Different", sell_diff, f"{sell_diff / len(matched) * 100:.1f}%"),
        ("", "", ""),
        ("Direction - Same", dir_same, f"{dir_same / len(matched) * 100:.1f}%"),
        ("Direction - Different", dir_diff, f"{dir_diff / len(matched) * 100:.1f}%"),
    ]

    summary = pd.DataFrame(rows, columns=["Metric", "Value1", "Value2"])
    summary.to_csv(SUMMARY_FILE, index=False)
    print(f"Summary saved to {SUMMARY_FILE}")


if __name__ == "__main__":
    compare_results()
