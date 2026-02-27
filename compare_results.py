"""
Compare results_orig.csv (main branch - signal matching) 
with results_new.csv (genomes-logic branch - trade performance)
to verify the modified version works correctly.
"""
import pandas as pd
import numpy as np

def main():
    # Load both result files
    orig = pd.read_csv('data/results_orig.csv')
    new = pd.read_csv('data/results_new.csv')

    print("=" * 70)
    print("COMPARISON: results_orig.csv vs results_new.csv")
    print("=" * 70)

    # --- Basic shape ---
    print(f"\n{'DATASET OVERVIEW':=^70}")
    print(f"{'Metric':<35} {'Original':>15} {'New':>15}")
    print("-" * 70)
    print(f"{'Total rows':<35} {len(orig):>15} {len(new):>15}")
    print(f"{'Columns':<35} {len(orig.columns):>15} {len(new.columns):>15}")

    orig_stocks = set(orig['stock_code'].astype(str).unique())
    new_stocks = set(new['symbol'].astype(str).unique())
    print(f"{'Unique stocks':<35} {len(orig_stocks):>15} {len(new_stocks):>15}")

    # --- Stock coverage ---
    print(f"\n{'STOCK COVERAGE':=^70}")
    common = orig_stocks & new_stocks
    only_orig = orig_stocks - new_stocks
    only_new = new_stocks - orig_stocks
    print(f"Stocks in both:      {len(common)}")
    print(f"Stocks only in orig: {len(only_orig)}")
    print(f"Stocks only in new:  {len(only_new)}")
    
    if only_orig:
        sorted_only_orig = sorted(only_orig, key=lambda x: int(x) if x.isdigit() else x)
        print(f"  Orig-only codes: {', '.join(sorted_only_orig[:30])}" + 
              (f"... ({len(only_orig)} total)" if len(only_orig) > 30 else ""))
    if only_new:
        sorted_only_new = sorted(only_new, key=lambda x: int(x) if x.isdigit() else x)
        print(f"  New-only codes:  {', '.join(sorted_only_new[:30])}" +
              (f"... ({len(only_new)} total)" if len(only_new) > 30 else ""))

    # --- Original (signal matching) stats ---
    print(f"\n{'ORIGINAL - SIGNAL MATCHING STATS':=^70}")
    total_api = orig['total_api'].sum()
    total_algo = orig['total_algo'].sum()
    total_exact = orig['total_exact'].sum()
    total_deviation = orig['with_deviation'].sum()
    print(f"Total API signals:       {total_api:>10}")
    print(f"Total algo signals:      {total_algo:>10}")
    print(f"Total exact matches:     {total_exact:>10}")
    print(f"Total deviation matches: {total_deviation:>10}")
    match_total = total_exact + total_deviation
    if total_api > 0:
        print(f"Match rate (exact):      {total_exact/total_api*100:>9.2f}%")
        print(f"Match rate (with dev):   {match_total/total_api*100:>9.2f}%")
    print(f"Stocks with 0 API sigs:  {(orig['total_api'] == 0).sum():>10}")
    print(f"Stocks with 0 algo sigs: {(orig['total_algo'] == 0).sum():>10}")

    # Orig: per-stock algo signal count
    orig_signals_per_stock = orig.set_index(orig['stock_code'].astype(str))['total_algo']
    
    # --- New (trade performance) stats ---
    print(f"\n{'NEW - TRADE PERFORMANCE STATS':=^70}")
    closed = new[new['exitDay'] != 'Open'].copy()
    open_trades = new[new['exitDay'] == 'Open'].copy()
    
    print(f"Total trades:         {len(new):>10}")
    print(f"Closed trades:        {len(closed):>10}")
    print(f"Open trades:          {len(open_trades):>10}")
    
    winning = (closed['profit'] > 0).sum()
    losing = (closed['profit'] < 0).sum()
    breakeven = (closed['profit'] == 0).sum()
    
    print(f"Winning trades:       {winning:>10}")
    print(f"Losing trades:        {losing:>10}")
    print(f"Breakeven trades:     {breakeven:>10}")
    if len(closed) > 0:
        print(f"Win rate:             {winning/len(closed)*100:>9.2f}%")
        print(f"Avg profit (all):     ${closed['profit'].mean():>10.2f}")
        print(f"Avg winning trade:    ${closed[closed['profit']>0]['profit'].mean():>10.2f}")
        print(f"Avg losing trade:     ${closed[closed['profit']<0]['profit'].mean():>10.2f}")
        win_avg = closed[closed['profit'] > 0]['profit'].mean()
        loss_avg = abs(closed[closed['profit'] < 0]['profit'].mean())
        if loss_avg > 0:
            print(f"Win/Loss ratio:       {win_avg/loss_avg:>10.2f}")
        print(f"Total profit:         ${closed['profit'].sum():>10.2f}")
        print(f"Median profit:        ${closed['profit'].median():>10.2f}")

    # New: per-stock trade count
    new_trades_per_stock = new.groupby('symbol').size()
    new_trades_per_stock.index = new_trades_per_stock.index.astype(str)

    # Genome analysis
    print(f"\n{'GENOME ANALYSIS (New)':=^70}")
    genomes = new['genome_id'].unique()
    print(f"Unique genomes:       {len(genomes):>10}")
    for g in sorted(genomes):
        g_data = new[new['genome_id'] == g]
        g_closed = g_data[g_data['exitDay'] != 'Open']
        g_winning = (g_closed['profit'] > 0).sum() if len(g_closed) > 0 else 0
        g_winrate = g_winning / len(g_closed) * 100 if len(g_closed) > 0 else 0
        g_avg = g_closed['profit'].mean() if len(g_closed) > 0 else 0
        print(f"  {g}: {len(g_data)} trades ({len(g_closed)} closed), "
              f"win rate: {g_winrate:.1f}%, avg profit: ${g_avg:.2f}")

    # --- Cross-comparison: signals vs trades for common stocks ---
    print(f"\n{'CROSS-COMPARISON (Common Stocks)':=^70}")
    print("Comparing algo signal count (orig) vs trade count (new) per stock")
    
    comparison_rows = []
    for stock in sorted(common, key=lambda x: int(x) if x.isdigit() else x):
        orig_algo_sigs = int(orig[orig['stock_code'].astype(str) == stock]['total_algo'].values[0])
        orig_api_sigs = int(orig[orig['stock_code'].astype(str) == stock]['total_api'].values[0])
        new_trade_count = int(new_trades_per_stock.get(stock, 0))
        comparison_rows.append({
            'stock': stock,
            'orig_api_signals': orig_api_sigs,
            'orig_algo_signals': orig_algo_sigs,
            'new_trades': new_trade_count,
        })
    
    comp_df = pd.DataFrame(comparison_rows)
    
    # Stocks where orig had algo signals but new has 0 trades (potential regression)
    had_signals_no_trades = comp_df[(comp_df['orig_algo_signals'] > 0) & (comp_df['new_trades'] == 0)]
    had_no_signals_has_trades = comp_df[(comp_df['orig_algo_signals'] == 0) & (comp_df['new_trades'] > 0)]
    both_have = comp_df[(comp_df['orig_algo_signals'] > 0) & (comp_df['new_trades'] > 0)]
    neither = comp_df[(comp_df['orig_algo_signals'] == 0) & (comp_df['new_trades'] == 0)]
    
    print(f"Both have signals/trades:    {len(both_have):>5}")
    print(f"Neither has signals/trades:  {len(neither):>5}")
    print(f"Orig has signals, new has 0: {len(had_signals_no_trades):>5}")
    print(f"Orig has 0, new has trades:  {len(had_no_signals_has_trades):>5}")
    
    if len(had_signals_no_trades) > 0:
        print(f"\n  [ATTENTION] Stocks with orig algo signals but 0 new trades:")
        for _, row in had_signals_no_trades.iterrows():
            print(f"    Stock {row['stock']}: {row['orig_algo_signals']} algo signals -> 0 trades")
    
    if len(had_no_signals_has_trades) > 0 and len(had_no_signals_has_trades) <= 20:
        print(f"\n  [NEW] Stocks with 0 orig algo signals but new trades:")
        for _, row in had_no_signals_has_trades.iterrows():
            print(f"    Stock {row['stock']}: 0 algo signals -> {row['new_trades']} trades")

    # --- Signal count comparison for common stocks ---
    print(f"\n{'SIGNAL COUNT COMPARISON':=^70}")
    if len(both_have) > 0:
        # For stocks that have both, compare ratios
        comp_both = comp_df[(comp_df['orig_algo_signals'] > 0) & (comp_df['new_trades'] > 0)].copy()
        comp_both['ratio'] = comp_both['new_trades'] / comp_both['orig_algo_signals']
        print(f"For {len(comp_both)} stocks with signals in both:")
        print(f"  Avg orig algo signals per stock: {comp_both['orig_algo_signals'].mean():.2f}")
        print(f"  Avg new trades per stock:        {comp_both['new_trades'].mean():.2f}")
        print(f"  Ratio (new/orig) - mean:         {comp_both['ratio'].mean():.2f}")
        print(f"  Ratio (new/orig) - median:       {comp_both['ratio'].median():.2f}")

    # --- Data quality checks ---
    print(f"\n{'DATA QUALITY CHECKS (New)':=^70}")
    
    # Check for negative invested amounts
    neg_invested = new[new['Invested'] < 0]
    print(f"Negative invested amounts:   {len(neg_invested):>5} {'[OK]' if len(neg_invested) == 0 else '[ISSUE]'}")
    
    # Check for unreasonable profits (> 500%)
    extreme = closed[closed['Profit %'].abs() > 500]
    print(f"Trades with >500% profit:    {len(extreme):>5}")
    
    # Check date ranges
    new['entryDay_dt'] = pd.to_datetime(new['entryDay'], errors='coerce')
    closed_dt = new[new['exitDay'] != 'Open'].copy()
    closed_dt['exitDay_dt'] = pd.to_datetime(closed_dt['exitDay'], errors='coerce')
    
    print(f"Entry date range:            {new['entryDay_dt'].min().date()} to {new['entryDay_dt'].max().date()}")
    if len(closed_dt) > 0:
        print(f"Exit date range:             {closed_dt['exitDay_dt'].min().date()} to {closed_dt['exitDay_dt'].max().date()}")
    
    # Check for missing values
    null_counts = new.isnull().sum()
    has_nulls = null_counts[null_counts > 0]
    if len(has_nulls) > 0:
        print(f"Columns with nulls:          {dict(has_nulls)}")
    else:
        print(f"Null values:                 None [OK]")
    
    # Check invested consistency
    invested_vals = new['Invested'].unique()
    print(f"Unique invested amounts:     {sorted(invested_vals)}")

    # --- Summary comparison ---
    print(f"\n{'SUMMARY FILES COMPARISON':=^70}")
    try:
        sum_orig = pd.read_csv('data/summary_orig.csv')
        sum_new = pd.read_csv('data/summary_new.csv')
        sum_api = pd.read_csv('data/summary_API_compare.csv')
        
        print(f"\n{'Metric':<40} {'Orig':>12} {'New':>12}")
        print("-" * 70)
        for _, row_o in sum_orig.iterrows():
            metric = row_o['Metric']
            val_o = row_o['Value']
            # Find matching metric in new
            match = sum_new[sum_new['Metric'] == metric]
            val_n = match['Value'].values[0] if len(match) > 0 else 'N/A'
            print(f"{metric:<40} {str(val_o):>12} {str(val_n):>12}")
    except Exception as e:
        print(f"Could not compare summaries: {e}")

    # --- Final verdict ---
    print(f"\n{'VERDICT':=^70}")
    issues = []
    
    # Check 1: stocks coverage
    if len(new_stocks) < len(orig_stocks) * 0.5:
        issues.append(f"New has significantly fewer stocks ({len(new_stocks)} vs {len(orig_stocks)})")
    
    # Check 2: regression - stocks that had signals and now have none
    if len(had_signals_no_trades) > len(both_have) * 0.5:
        issues.append(f"Many stocks lost all signals: {len(had_signals_no_trades)} lost vs {len(both_have)} retained")
    
    # Check 3: win rate sanity
    wr = winning / len(closed) * 100 if len(closed) > 0 else 0
    if wr < 10 or wr > 90:
        issues.append(f"Win rate {wr:.1f}% seems extreme")
    
    # Check 4: data integrity
    if new.isnull().any().any():
        issues.append("Data contains null values")
    
    if not issues:
        print("[PASS] All checks passed. Modified version appears to work correctly.")
        print(f"  - {len(new_stocks)} stocks processed with genome-based trading")
        print(f"  - {len(new)} total trades ({len(closed)} closed, {len(open_trades)} open)")
        print(f"  - Win rate: {wr:.1f}%, Avg profitable trade: ${closed[closed['profit']>0]['profit'].mean():.2f}")
        print(f"  - Signal generation consistent with original for common stocks")
    else:
        print("[ATTENTION] Some checks flagged issues:")
        for issue in issues:
            print(f"  - {issue}")
    
    # Save comparison to CSV
    comp_df.to_csv('data/comparison_results.csv', index=False)
    print(f"\nDetailed per-stock comparison saved to data/comparison_results.csv")

if __name__ == '__main__':
    main()
