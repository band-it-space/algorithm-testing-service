"""
Tests for B11, B12, B13, and B18 buy signal conditions.
These tests are written according to the specification documentation,
not the implementation, to catch potential bugs in the implementation.
"""
import math
from datetime import datetime, timedelta

import numpy as np
import pytest

from app.workers.algo_func.buy_signals import (
    OHLCV,
    checkB11,
    checkB12,
    checkB13,
    checkB18,
)


def _mk(date_str, o, h, l, c, v=1_000):
    return OHLCV(date=date_str, open=o, high=h, low=l, close=c, volume=v)


def _date_seq(start, count):
    base = datetime.strptime(start, "%Y-%m-%d")
    return [(base + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(count)]


# ============================================================================
# B11 Tests
# Specification: IF Current ATR(22) is higher than {87%} of maximum ATR(22) 
#                in the past {126} day, THEN cancel buy.
# ============================================================================

def _create_ohlcv_for_atr(length, base_close=100.0, tr_range=10.0):
    """Create OHLCV data with specified true range."""
    dates = _date_seq("2024-01-01", length)
    data = []
    for d in dates:
        high = base_close + tr_range / 2.0
        low = base_close - tr_range / 2.0
        data.append(_mk(d, base_close, high, low, base_close))
    return data


def test_b11_allows_buy_when_current_atr_below_87pct_of_max():
    """
    B11 Specification: Cancel buy ONLY if current ATR(22) > 87% of max ATR(22) in past 126 days.
    If current ATR is below this threshold, buy should be allowed (return True).
    """
    # Create data where:
    # - First 126+ days: high volatility (TR=20) -> high ATR(22)
    # - Last 22+ days: low volatility (TR=2) -> low current ATR(22)
    # Current ATR(22) should be much lower than 87% of the max ATR(22) from past 126 days
    high_vol_period = _create_ohlcv_for_atr(150, base_close=100.0, tr_range=20.0)
    low_vol_period = _create_ohlcv_for_atr(50, base_close=100.0, tr_range=2.0)
    data = high_vol_period + low_vol_period
    
    # According to spec: if current ATR(22) <= 87% * max(ATR(22) in past 126), allow buy
    assert checkB11(data) is True, "B11 should allow buy when current ATR is below 87% threshold"


def test_b11_cancels_buy_when_current_atr_above_87pct_of_max():
    """
    B11 Specification: Cancel buy if current ATR(22) > 87% of max ATR(22) in past 126 days.
    """
    # Create data where:
    # - First 126+ days: low volatility (TR=2) -> low ATR(22) max
    # - Last 22+ days: high volatility (TR=20) -> high current ATR(22)
    # Current ATR(22) should exceed 87% of the max ATR(22) from past 126 days
    low_vol_period = _create_ohlcv_for_atr(150, base_close=100.0, tr_range=2.0)
    high_vol_period = _create_ohlcv_for_atr(50, base_close=100.0, tr_range=20.0)
    data = low_vol_period + high_vol_period
    
    # According to spec: if current ATR(22) > 87% * max(ATR(22) in past 126), cancel buy
    assert checkB11(data) is False, "B11 should cancel buy when current ATR exceeds 87% threshold"


def test_b11_requires_sufficient_history():
    """B11 needs at least 126 + 22 = 148 days of data."""
    data = _create_ohlcv_for_atr(140, base_close=100.0, tr_range=10.0)
    assert checkB11(data) is False, "B11 should return False with insufficient history"


# ============================================================================
# B12 Tests
# Specification: If 150D SMA has risen {16%} in the past {50} days AND 
#                Today high is deviating from 150DMA by 20%, THEN CANCEL Buy
# ============================================================================

def test_b12_cancels_buy_when_both_conditions_met():
    """
    B12 Specification: Cancel buy if:
    1. 150D SMA has risen >= 16% in the past 50 days
    2. Today's high deviates from 150D SMA by >= 20%
    
    Implementation calculates:
    - Current 150D SMA: average of closes[targetIndex-150:targetIndex]
    - Past 150D SMA (50 days ago): average of closes[targetIndex-50-150:targetIndex-50]
    - Growth = (current SMA - past SMA) / past SMA
    """
    # Need at least 200 days: 150 (SMA window) + 50 (growth period)
    total_days = 220
    dates = _date_seq("2023-01-01", total_days)
    data = []
    
    # Past period: 150 days at constant price 100
    # This forms the "past 150D SMA" ending 50 days before target (indices 0-149)
    for idx in range(150):
        close = 100.0
        data.append(_mk(dates[idx], close, close + 1, close - 1, close))
    
    # Growth period: 50 days at high price to ensure 16%+ growth
    # Current 150D SMA (indices 50-199) includes: 100 values at 100 + 50 values at 148
    # Average = (100*100 + 148*50) / 150 = 116, Growth = (116-100)/100 = 16%
    for idx in range(150, 200):
        close = 148.0
        data.append(_mk(dates[idx], close, close + 1, close - 1, close))
    
    # Target date and beyond: maintain price
    for idx in range(200, total_days):
        close = 148.0
        data.append(_mk(dates[idx], close, close + 1, close - 1, close))
    
    # At target date (index 200):
    # - Past 150D SMA: closes[0:150] = 100, average = 100
    # - Current 150D SMA: closes[50:200] = 100 at 100 + 50 at 148, average = 116
    # - Growth = 16% ✓
    # - Set high to be 20%+ above current SMA (116): high >= 139.2
    target_date = data[200].date
    data[200] = _mk(
        data[200].date,
        data[200].open,
        140.0,  # high = 140, deviation = (140 - 116) / 116 ≈ 20.7% >= 20% ✓
        data[200].low,
        data[200].close,
    )
    
    # According to spec: if both conditions met, cancel buy (return False)
    assert checkB12(data, targetDate=target_date) is False, (
        "B12 should cancel buy when SMA growth >= 16% AND deviation >= 20%"
    )


def test_b12_allows_buy_when_growth_below_threshold():
    """
    B12 Specification: Allow buy if 150D SMA growth < 16% (even if deviation >= 20%).
    """
    total_days = 250
    dates = _date_seq("2023-01-01", total_days)
    data = []
    
    # Past period: average = 100
    for idx in range(50):
        close = 100.0
        data.append(_mk(dates[idx], close, close + 1, close - 1, close))
    
    # Small growth: only 10% growth (below 16% threshold)
    for idx in range(50, 200):
        progress = (idx - 50) / 150.0
        close = 100.0 + progress * 10.0  # grows from 100 to 110
        data.append(_mk(dates[idx], close, close + 1, close - 1, close))
    
    for idx in range(200, total_days):
        close = 110.0
        data.append(_mk(dates[idx], close, close + 1, close - 1, close))
    
    # At target: growth = (105 - 100) / 100 = 5% < 16%
    # Even if high deviates by 20%+, buy should be allowed
    target_date = data[200].date
    data[200] = _mk(
        data[200].date,
        data[200].open,
        130.0,  # high deviation, but growth < 16%
        data[200].low,
        data[200].close,
    )
    
    assert checkB12(data, targetDate=target_date) is True, (
        "B12 should allow buy when SMA growth < 16%"
    )


def test_b12_allows_buy_when_deviation_below_threshold():
    """
    B12 Specification: Allow buy if deviation < 20% (even if growth >= 16%).
    """
    total_days = 250
    dates = _date_seq("2023-01-01", total_days)
    data = []
    
    # Past period: average = 100
    for idx in range(50):
        close = 100.0
        data.append(_mk(dates[idx], close, close + 1, close - 1, close))
    
    # Growth period: 16%+ growth
    for idx in range(50, 200):
        progress = (idx - 50) / 150.0
        close = 100.0 + progress * 32.0
        data.append(_mk(dates[idx], close, close + 1, close - 1, close))
    
    for idx in range(200, total_days):
        close = 132.0
        data.append(_mk(dates[idx], close, close + 1, close - 1, close))
    
    # At target: growth >= 16%, but deviation < 20%
    target_date = data[200].date
    data[200] = _mk(
        data[200].date,
        data[200].open,
        120.0,  # high = 120, deviation = (120 - 116) / 116 ≈ 3.4% < 20%
        data[200].low,
        data[200].close,
    )
    
    assert checkB12(data, targetDate=target_date) is True, (
        "B12 should allow buy when deviation < 20%"
    )


# ============================================================================
# B13 Tests
# Specification: CANCEL buy if the stock is underperforming 2800 for 
#                {19}-Day AND {60}-Day look back periods.
# ============================================================================

def _create_ohlcv_series(close_values, start_date="2024-01-01"):
    """Create OHLCV series from close prices."""
    dates = _date_seq(start_date, len(close_values))
    data = []
    for date_str, close in zip(dates, close_values):
        high = close + 1.0
        low = close - 1.0
        open_ = close
        data.append(_mk(date_str, open_, high, low, close))
    return data


def test_b13_cancels_buy_when_underperforming_both_periods():
    """
    B13 Specification: Cancel buy if stock underperforms index in BOTH 19-day AND 60-day periods.
    """
    # Stock grows slowly, index grows faster
    # Over 19 days: stock return < index return
    # Over 60 days: stock return < index return
    days = 80
    stock_closes = [100.0 + i * 0.5 for i in range(days)]  # +0.5 per day
    index_closes = [100.0 + i * 1.5 for i in range(days)]  # +1.5 per day
    
    stock_data = _create_ohlcv_series(stock_closes, "2024-01-01")
    index_data = _create_ohlcv_series(index_closes, "2024-01-01")
    
    # Stock return over 19 days: (109.5 - 100) / 100 = 9.5%
    # Index return over 19 days: (128.5 - 100) / 100 = 28.5% -> stock underperforms ✓
    # Stock return over 60 days: (130 - 100) / 100 = 30%
    # Index return over 60 days: (190 - 100) / 100 = 90% -> stock underperforms ✓
    
    assert checkB13(stock_data, index_data) is False, (
        "B13 should cancel buy when stock underperforms in both 19-day AND 60-day periods"
    )


def test_b13_allows_buy_when_outperforming_19_day_period():
    """
    B13 Specification: Allow buy if stock outperforms in at least one period.
    """
    # Stock outperforms in 19-day period, underperforms in 60-day period
    days = 80
    stock_closes = [100.0 + i * 2.0 for i in range(days)]  # +2.0 per day
    index_closes = [100.0 + i * 1.0 for i in range(days)]  # +1.0 per day
    
    stock_data = _create_ohlcv_series(stock_closes, "2024-01-01")
    index_data = _create_ohlcv_series(index_closes, "2024-01-01")
    
    # Stock return over 19 days: (138 - 100) / 100 = 38%
    # Index return over 19 days: (119 - 100) / 100 = 19% -> stock outperforms ✓
    # Even if stock underperforms over 60 days, buy should be allowed
    
    assert checkB13(stock_data, index_data) is True, (
        "B13 should allow buy when stock outperforms in at least one period"
    )


def test_b13_allows_buy_when_outperforming_60_day_period():
    """
    B13 Specification: Allow buy if stock outperforms in at least one period.
    """
    # Stock underperforms in 19-day period, outperforms in 60-day period
    days = 80
    # Stock starts slow, then accelerates
    stock_closes = [100.0 + i * 0.5 if i < 20 else 110.0 + (i - 20) * 2.5 for i in range(days)]
    index_closes = [100.0 + i * 1.0 for i in range(days)]
    
    stock_data = _create_ohlcv_series(stock_closes, "2024-01-01")
    index_data = _create_ohlcv_series(index_closes, "2024-01-01")
    
    assert checkB13(stock_data, index_data) is True, (
        "B13 should allow buy when stock outperforms in at least one period"
    )


# ============================================================================
# B18 Tests - Mark Minervini's Trend Template
# Specification: All 8 conditions must be True for B18 to return True
# ============================================================================

def _build_b18_compliant_dataset():
    """
    Build dataset that satisfies all B18 conditions:
    B18(1) Price > 150MA and Price > 200MA
    B18(2) 150MA > 200MA
    B18(3) 200MA trending up for 1 month (21 days)
    B18(4) 50MA > 150MA and 50MA > 200MA
    B18(5) Price > 50MA
    B18(6) Price >= 52-week low * 1.30 (30% above)
    B18(7) Price >= 52-week high * 0.75 (within 25% of high)
    B18(8) Avg BBW(21) < 22% of Avg BBW(82) AND Price > BB(21,2) upper band
    """
    # Need at least 250 days for 52-week conditions, and enough for BB(21) + 82 days
    days = 350
    dates = _date_seq("2023-01-01", days)
    
    # Create strong, steady uptrend to ensure all MAs are in correct order
    # Start at 60, end around 270 (strong 210-point gain over 350 days)
    x = np.arange(days)
    base_trend = 60.0 + (210.0 / days) * x  # Linear growth from 60 to 270
    
    closes = []
    data = []
    
    # Strategy for BBW condition 8:
    # 1. Create period with VERY HIGH volatility (to increase BBW82 average)
    # 2. Follow with LONG period with VERY LOW volatility (to decrease BBW21 average)
    # The low volatility period must be long enough (21+ days) so that
    # all BB(21) windows in the last 21 days use only low-volatility data
    for i, date_str in enumerate(dates):
        if i < days - 103:
            # Early period: steady growth with moderate noise
            close = base_trend[i] + 2.0 * np.sin(2 * np.pi * i / 30.0)
            range_size = 3.0
        elif i < days - 42:
            # High volatility period (days 247-307): EXTREMELY HIGH volatility
            # This creates high BBW values that will be in BBW82 average
            oscillation = 30.0 * np.sin(2 * np.pi * i / 1.5)  # Very frequent, huge swings
            close = base_trend[i] + oscillation
            range_size = 35.0  # Very wide range
        else:
            # Low volatility period (days 308-349): ABSOLUTELY CONSTANT closes
            # This period is 42 days long, ensuring that all BB(21) windows
            # in the last 21 days (days 329-349) use only constant closes
            # Result: BBW ≈ 0 for all these windows, making avgBBW21 very small
            constant_price = 275.0
            close = constant_price  # Exactly constant, zero std deviation
            range_size = 0.0001  # Minimal range
        
        closes.append(close)
        high = close + range_size
        low = close - range_size
        open_ = close
        data.append(_mk(date_str, open_, high, low, close))
    
    # Ensure last close is high and above BB upper
    # Set to 280 to be safely above BB upper band
    last_close = 280.0
    data[-1] = _mk(
        data[-1].date,
        data[-1].open,
        last_close + 1.0,
        last_close - 1.0,
        last_close,
    )
    closes[-1] = last_close
    
    return data


def test_b18_returns_true_when_all_conditions_met():
    """
    B18 Specification: Return True only when ALL 8 conditions are satisfied.
    """
    from app.workers.algo_func.buy_signals import sma, bollinger_bands, mean
    
    data = _build_b18_compliant_dataset()
    
    # Verify dataset setup
    assert len(data) >= 250, "Need at least 250 days for B18"
    
    # Check all conditions manually to identify which one fails
    closes = [bar.close for bar in data]
    lows = [bar.low for bar in data]
    highs = [bar.high for bar in data]
    last_close = data[-1].close
    
    # Calculate MAs
    sma50 = sma(closes, 50)
    sma150 = sma(closes, 150)
    sma200 = sma(closes, 200)
    
    if not sma50 or not sma150 or not sma200:
        assert False, f"Not enough data for MAs: sma50={len(sma50) if sma50 else 0}, sma150={len(sma150) if sma150 else 0}, sma200={len(sma200) if sma200 else 0}"
    
    last_sma50 = sma50[-1]
    last_sma150 = sma150[-1]
    last_sma200 = sma200[-1]
    
    # Check each condition
    cond1 = last_close > last_sma150 and last_close > last_sma200
    cond2 = last_sma150 > last_sma200
    cond3 = len(sma200) >= 22 and sma200[-1] > sma200[-1 - 20] if len(sma200) >= 22 else False
    cond4 = last_sma50 > last_sma150 and last_sma50 > last_sma200
    cond5 = last_close > last_sma50
    
    last250_low = min(lows[-250:])
    last250_high = max(highs[-250:])
    cond6 = last_close >= last250_low * 1.30
    cond7 = last_close >= last250_high * 0.75
    
    bb21 = bollinger_bands(closes, 21, 2)
    if len(bb21) >= 82:
        bbw = [(b['upper'] - b['lower']) / b['middle'] for b in bb21]
        avg_bbw21 = mean(bbw[-21:])
        avg_bbw82 = mean(bbw[-82:])
        last_bb21 = bb21[-1]
        cond8 = (avg_bbw21 < 0.22 * avg_bbw82) and (last_close > last_bb21['upper'])
    else:
        cond8 = False
    
    # Print condition status for debugging
    conditions = {
        "1 (Price > 150MA and > 200MA)": cond1,
        "2 (150MA > 200MA)": cond2,
        "3 (200MA trending up)": cond3,
        "4 (50MA > 150MA and > 200MA)": cond4,
        "5 (Price > 50MA)": cond5,
        "6 (Price >= 52w low * 1.30)": cond6,
        "7 (Price >= 52w high * 0.75)": cond7,
        "8 (BBW condition and Price > BB upper)": cond8,
    }
    
    failed_conditions = [name for name, value in conditions.items() if not value]
    
    result = checkB18(data)
    assert result == True, (
        f"B18 should return True when all 8 conditions are met.\n"
        f"Failed conditions: {failed_conditions}\n"
        f"All conditions: {conditions}\n"
        f"Last close: {last_close:.2f}, SMA50: {last_sma50:.2f}, SMA150: {last_sma150:.2f}, SMA200: {last_sma200:.2f}\n"
        f"52w low: {last250_low:.2f}, 52w high: {last250_high:.2f}\n"
        + (f"BBW21: {avg_bbw21:.6f}, BBW82: {avg_bbw82:.6f}, BB upper: {last_bb21['upper']:.2f}\n" if len(bb21) >= 82 else "BB21 data insufficient\n")
    )


def test_b18_returns_false_when_price_too_low_relative_to_52_week_low():
    """
    B18 Specification: Condition 6 - Price must be at least 30% above 52-week low.
    """
    data = _build_b18_compliant_dataset()
    
    # Violate condition 6: set price to only 10% above 52-week low
    last250_low = min(bar.low for bar in data[-250:])
    adjusted_close = last250_low * 1.10  # Only 10% above, needs 30%
    
    last = data[-1]
    data_modified = data[:-1] + [
        _mk(last.date, last.open, adjusted_close + 1.0, adjusted_close - 1.0, adjusted_close)
    ]
    
    result = checkB18(data_modified)
    # Use == instead of 'is' to handle numpy boolean types
    assert result == False, f"B18 should return False when condition 6 is violated, got {result} (type: {type(result)})"


def test_b18_returns_false_when_price_too_far_from_52_week_high():
    """
    B18 Specification: Condition 7 - Price must be within 25% of 52-week high.
    """
    data = _build_b18_compliant_dataset()
    
    # Violate condition 7: set price to only 50% of 52-week high (50% away, needs to be within 25%)
    last250_high = max(bar.high for bar in data[-250:])
    adjusted_close = last250_high * 0.50  # 50% of high, but needs >= 75%
    
    last = data[-1]
    data_modified = data[:-1] + [
        _mk(last.date, last.open, adjusted_close + 1.0, adjusted_close - 1.0, adjusted_close)
    ]
    
    result = checkB18(data_modified)
    # Use == instead of 'is' to handle numpy boolean types
    assert result == False, f"B18 should return False when condition 7 is violated, got {result} (type: {type(result)})"


def test_b18_requires_sufficient_history():
    """B18 needs at least 250 days for 52-week conditions."""
    data = _build_b18_compliant_dataset()[:200]
    result = checkB18(data)
    assert result is False, "B18 should return False with insufficient history"
