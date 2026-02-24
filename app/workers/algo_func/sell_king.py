import numpy as np
from datetime import datetime
import pandas as pd
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
import logging

from app.workers.algo_func.types import OHLCV
from app.workers.algo_func.helpers import to_ts, sma, lewis_atr
from app.workers.algo_func.sell_signals import s10, s11, s12, s15, s16, s17

logger = logging.getLogger(__name__)

#TODO S1
def checkS1_US(stock_prices: List[OHLCV], stop_loss: float) -> bool:
    """
    S1 for US King Algorithm - Stop Loss Exit
    
    Exit if current close price falls below the stop loss level.
    
    The stop_loss is calculated at entry using calcS1Stop_US():
    - Base stop = entry_close - 3.4 * ATR(22)
    - If risk > 20%, use fixed 7.2% stop instead
    
    This function simply checks if the stop has been hit.
    
    Args:
        stock_prices: Price data
        stop_loss: Stop loss level calculated at entry
    
    Returns:
        True if stop loss hit (exit signal)
        False otherwise
    
    Documentation: "Use [CLOSE - {3.4}*ATR({22})] as stop position, 
                    if stop loss is > {20%}, set stop loss at {7.2%}"
    
    MC Code Reference (lines 580-583):
        if close < stop_prev_low then
            is_stop_day_low = true
        else
            is_stop_day_low = false
    """
    if not isinstance(stock_prices, list) or len(stock_prices) == 0:
        return False
    
    if not isinstance(stop_loss, (int, float)) or not np.isfinite(stop_loss):
        return False
    
    last = stock_prices[-1]
    close = float(last.close)
    
    if not np.isfinite(close):
        return False
    
    return close < stop_loss

#TODO S4
def checkS4_US(
    stock_prices: List[OHLCV],
    entry_index: int,
    min_holding_period: int = 50,
    check_period: int = 50,
    ma_period: int = 50,
    threshold_percent: float = 0.45,
    min_gain_percent: float = 0.07
) -> bool:
    """
    S4 for US King Algorithm - Weak Performance Exit
    
    EFFECTIVE after {min_holding_period} days since entry.
    
    Exit if BOTH conditions are TRUE:
    1. In the last {check_period} days, less than {threshold_percent}% of days had close > {ma_period}D MA
    2. Gain over last {check_period} days < {min_gain_percent}%
    
    This identifies positions that are not performing well - price struggling
    to stay above its moving average and showing minimal gains.
    
    Args:
        stock_prices: Price data sorted by date, [-1] is today
        entry_index: Index of entry day in stock_prices array
        min_holding_period: Days to wait before activating rule (default 50)
        check_period: Period to check performance (default 50)
        ma_period: Moving average period to compare against (default 50)
        threshold_percent: Min % of days above MA (default 0.45 = 45%)
        min_gain_percent: Min gain required (default 0.07 = 7%)
    
    Returns:
        True if exit signal (weak performance)
        False otherwise (or if not enough days since entry)
    
    Documentation: "Enable this rule on the {50}th trading day after issuing Buy.
                    Let A = counting number of trading day whereas Daily Close > 50D MA in the past {50} days.
                    If A/{50} < {45%} and {50} Days gain is < {7%} then exit trade"
    
    MC Code Reference (lines 590-597):
        if barssinceentry(0) >= input_exit_barsinceentry then
        begin
            profitable_cnt = countif(close > average(close, 50), input_exit_barsinceentry);
            if profitable_cnt/input_exit_barsinceentry * 100 < input_exit_barsinceentry_threshold
                and (close - close[50]) / close[50] * 100 < 7 then
                is_stop_barsinceentry = true
        
        input_exit_barsinceentry = 50
        input_exit_barsinceentry_threshold = 45
    
    Comparison with HK S4:
        HK: Checks once on day 50, uses 150D SMA, looks at days SINCE entry, 50% threshold, 5% gain
        US: Checks daily after day 50, uses 50D MA, looks at LAST 50 days, 45% threshold, 7% gain
    """
    # Need data: check_period + ma_period for calculating MA at all points
    min_required = check_period + ma_period
    if len(stock_prices) < min_required:
        return False
    
    # Calculate days since entry (today is stock_prices[-1])
    days_since_entry = len(stock_prices) - 1 - entry_index
    
    if days_since_entry < min_holding_period:
        return False
    
    # Check if we have enough data for the check_period
    last_idx = len(stock_prices) - 1
    if last_idx < check_period - 1:
        return False
    
    # Get last check_period days (including today)
    closes = [float(bar.close) for bar in stock_prices]
    
    # Calculate 50D MA for the entire dataset
    sma_values = sma(closes, ma_period)
    
    if len(sma_values) < check_period:
        return False
    
    # Count how many of the last check_period days had close > 50D MA
    days_above_ma = 0
    
    for i in range(check_period):
        day_idx = last_idx - i
        sma_idx = day_idx - (ma_period - 1)  # SMA array is shorter
        
        if sma_idx >= 0 and sma_idx < len(sma_values):
            if closes[day_idx] > sma_values[sma_idx]:
                days_above_ma += 1
    
    # Calculate ratio
    ratio = days_above_ma / check_period
    
    # Condition 1: Less than threshold% of days above MA
    weak_ma_performance = ratio < threshold_percent
    
    # Condition 2: Gain over check_period < min_gain_percent
    current_close = closes[last_idx]
    past_close = closes[last_idx - check_period]
    
    if past_close <= 0:
        return False
    
    gain = (current_close - past_close) / past_close
    weak_gain = gain < min_gain_percent
    
    # Exit if BOTH conditions true
    result = weak_ma_performance and weak_gain
    
    # logger.info(
    #     f"S4_US - Days since entry: {days_since_entry}, "
    #     f"Days above MA: {days_above_ma}/{check_period} ({ratio*100:.1f}%), "
    #     f"Gain: {gain*100:.2f}%, "
    #     f"Exit: {result}"
    # )
    
    return result

#TODO S5
def checkS5_US(
    stock_prices: List[OHLCV],
    entry_index: int,
    buy_price: float,
    current_stop: float,
    activation_day: int = 50,
    update_period: int = 30,
    initial_atr_factor: float = 0.7,
    increment_atr_factor: float = 0.7,
    initial_atr_period: int = 20,
    increment_atr_period: int = 10
) -> tuple[bool, float]:
    """
    S5 for US King Algorithm - Trailing Stop Loss
    
    Progressive trailing stop that moves up every {update_period} days after activation.
    
    Logic:
    1. EFFECTIVE on day {activation_day} (default 50) after entry
    2. Initial stop = entry_price + {initial_atr_factor} * ATR({initial_atr_period})
    3. Every {update_period} days: new_stop = old_stop + {increment_atr_factor} * ATR({increment_atr_period})
    4. Exit if close < current_stop (checked DAILY after activation)
    
    This locks in profits by raising the stop as time passes.
    
    Args:
        stock_prices: Price data sorted by date, [-1] is today
        entry_index: Index of entry day in stock_prices array
        buy_price: Entry price
        current_stop: Current stop loss value (0 if not initialized)
        activation_day: Days after entry to activate (default 50)
        update_period: Days between stop updates (default 30)
        initial_atr_factor: Factor for initial stop ATR (default 0.7)
        increment_atr_factor: Factor for stop increments (default 0.7)
        initial_atr_period: ATR period for initial stop (default 20)
        increment_atr_period: ATR period for increments (default 10)
    
    Returns:
        Tuple of (exit_signal: bool, new_stop: float)
        - exit_signal: True if close < stop (exit now)
        - new_stop: Updated stop loss value
    
    Documentation: "Effective on or after {50} days
                    Initial stop = entry price + {0.7}*ATR(20)
                    Push up stop by {0.7}*ATR(10) every {30} days."
    
    MC Code Reference (lines 606-622):
        if barssinceentry(0) >= input_exit_moving_stop_day then
        begin
            moving_stop_day_cnt = moving_stop_day_cnt + 1;
            
            if moving_stop = 0 then
                moving_stop = OpenEntryPrice + input_exit_moving_stop_factor * _lewis_ATR(20);
            
            if mod(moving_stop_day_cnt, input_exit_moving_stop_period) = 0 then
            begin
                moving_stop = moving_stop + input_exit_moving_stop_factor * _lewis_ATR(10);
            end;
        end;
        if close < moving_stop then
            is_stop_moving = true
        
        input_exit_moving_stop_day = 50
        input_exit_moving_stop_period = 30
        input_exit_moving_stop_factor = 0.7
    
    Comparison with HK S5:
        HK: day 45, every 25 days, factor 0.62, ATR(20) for both, only check on key days
        US: day 50, every 30 days, factor 0.7, ATR(20) initial + ATR(10) increment, check DAILY
    """
    if len(stock_prices) < max(initial_atr_period, increment_atr_period) + 1:
        return False, current_stop
    
    # Calculate days since entry (today is stock_prices[-1])
    days_since_entry = len(stock_prices) - 1 - entry_index
    
    # Check if activated
    if days_since_entry < activation_day:
        return False, current_stop
    
    # Get current close
    current_close = float(stock_prices[-1].close)
    
    # Extract price data for ATR calculation
    highs = [bar.high for bar in stock_prices]
    lows = [bar.low for bar in stock_prices]
    closes = [bar.close for bar in stock_prices]
    
    # Initialize stop on activation day
    new_stop = current_stop
    
    if current_stop == 0 or not np.isfinite(current_stop):
        # First time initialization: day 50
        # Calculate ATR(20) for the current day
        atr20_values = lewis_atr(highs, lows, closes, initial_atr_period)
        if not atr20_values or atr20_values[-1] is None:
            return False, current_stop
        
        current_atr20 = atr20_values[-1]
        new_stop = buy_price + initial_atr_factor * current_atr20
        
        # logger.info(
        #     f"S5_US - Initialized stop on day {days_since_entry}: "
        #     f"buy_price={buy_price:.2f}, ATR(20)={current_atr20:.2f}, "
        #     f"stop={new_stop:.2f}"
        # )
    else:
        # Check if we need to update the stop (every 30 days after activation)
        # MultiCharts uses moving_stop_day_cnt that starts at 1 on activation day
        # Day 50: cnt=1, no update (mod(1,30)=1)
        # Day 79: cnt=30, UPDATE (mod(30,30)=0) - first update is 29 days after activation
        # Day 109: cnt=60, UPDATE (mod(60,30)=0)
        
        # To match MultiCharts logic: cnt = days_since_entry - activation_day + 1
        days_since_activation = days_since_entry - activation_day + 1
        
        if days_since_activation > 1 and days_since_activation % update_period == 0:
            # Time to update the stop
            atr10_values = lewis_atr(highs, lows, closes, increment_atr_period)
            if not atr10_values or atr10_values[-1] is None:
                # Can't calculate ATR, keep old stop
                new_stop = current_stop
            else:
                current_atr10 = atr10_values[-1]
                new_stop = current_stop + increment_atr_factor * current_atr10
                
                logger.info(
                    f"S5_US - Updated stop on day {days_since_entry} "
                    f"({days_since_activation} days since activation): "
                    f"old_stop={current_stop:.2f}, ATR(10)={current_atr10:.2f}, "
                    f"new_stop={new_stop:.2f}"
                )
        else:
            # Not an update day, keep current stop
            new_stop = current_stop
    
    # Check exit condition (daily after activation)
    exit_signal = current_close < new_stop
    
    # logger.info(
    #     f"S5_US - Day {days_since_entry}: "
    #     f"close={current_close:.2f}, stop={new_stop:.2f}, "
    #     f"exit={exit_signal}"
    # )
    
    return exit_signal, round(new_stop, 3)

#TODO S6
def checkS6_US(
    stock_prices: List[OHLCV],
    entry_index: int,
    activation_day: int = 50,
    lookback_period: int = 90,
    max_days_since_high: int = 76
) -> bool:
    """
    S6 for US King Algorithm - Stalled Momentum Exit
    
    Exit if no new high in recent period, indicating momentum has stalled.
    
    EFFECTIVE after {activation_day} days since entry.
    
    Logic:
    1. Find the highest HIGH in the last {lookback_period} days (stock_prices[-90:])
    2. Calculate how many days ago that high occurred
    3. If more than {max_days_since_high} days ago, EXIT
    
    Note: stock_prices[-1] is always today, stock_prices is sorted by date ascending.
    
    Args:
        stock_prices: Price data sorted by date, [-1] is today
        entry_index: Index of entry day in stock_prices array
        activation_day: Days after entry to activate (default 50)
        lookback_period: Period to search for highs (default 90)
        max_days_since_high: Max days since last high (default 76)
    
    Returns:
        True if exit signal (momentum stalled)
        False otherwise
    
    Documentation: "Effective after 50 days, if no new {90D} high in the last {76} days, then stop"
    
    MC Code Reference (lines 630-638):
        if barssinceentry(0) >= 50 then
            if highestbar(close, input_exit_new_high_len) > input_exit_new_high_day then
                is_stop_new_high_day = true
        
        input_exit_new_high_len = 90
        input_exit_new_high_day = 76
    """
    # Need enough total data
    if len(stock_prices) < lookback_period:
        return False
    
    # Calculate days since entry (today is stock_prices[-1])
    days_since_entry = len(stock_prices) - 1 - entry_index
    
    if days_since_entry < activation_day:
        return False
    
    # Get last lookback_period bars (last 90 days including today)
    # window[0] = 90 days ago, window[-1] = today
    window = stock_prices[-lookback_period:]
    
    # Extract highs and find maximum
    highs = [float(bar.close) for bar in window]
    max_high = max(highs)
    
    # Find LAST occurrence of max_high (search from end)
    # highs[::-1].index() finds first in reversed list = last in original
    max_high_position = len(highs) - 1 - highs[::-1].index(max_high)
    
    # Calculate days ago: position 0 = 89 days ago, position 89 = 0 days ago (today)
    days_since_high = len(window) - 1 - max_high_position
    
    # Exit if high was more than threshold days ago (> not >=)
    exit_signal = days_since_high > max_days_since_high
    
    # logger.info(
    #     f"S6_US - Day {days_since_entry}: "
    #     f"max_high={max_high:.2f} at position {max_high_position}/{len(window)-1} "
    #     f"({days_since_high} days ago), threshold={max_days_since_high}, exit={exit_signal}"
    # )
    
    return exit_signal

#TODO S7
def checkS7_US(
    stock_prices: List[OHLCV],
    entry_index: int,
    activation_day: int = 0,
    candle_factor: float = 2.0,
    atr_period: int = 22,
    consecutive_days: int = 2
) -> bool:
    """
    S7 for US King Algorithm - Large Bearish Candles Exit
    
    Exit if large bearish candles appear consecutively, indicating strong selling pressure.
    
    EFFECTIVE after {activation_day} days (default 0 means from day 2+ after entry).
    
    Logic:
    1. Check last {consecutive_days} days (default 2)
    2. For each day: (open - close) > {candle_factor} * ATR({atr_period})
    3. Both conditions must be close < open (bearish candle)
    4. If ALL days satisfy the condition, EXIT
    
    Note: Grace period - not checked on entry day (barssinceentry > 0)
    
    Args:
        stock_prices: Price data sorted by date, [-1] is today
        entry_index: Index of entry day in stock_prices array
        activation_day: Days after entry to activate (default 0 = from day 2)
        candle_factor: ATR multiplier for body size (default 2.0)
        atr_period: ATR calculation period (default 22)
        consecutive_days: Number of consecutive days to check (default 2)
    
    Returns:
        True if exit signal (consecutive large bearish candles)
        False otherwise
    
    Documentation: "Exit the position if (open - close) > {2} x ATR(22) for two consecutive trading days"
    
    MC Code Reference (lines 643-654):
        is_stop_candle = false;
        if barssinceentry(0) > input_exit_candle_day then
        begin
            if countif(close < open and (open - close) > input_exit_candle_factor * _lewis_ATR(22), 2) >= 2 then
                is_stop_candle = true
        end;
        
        input_exit_candle_factor = 2
        input_exit_candle_day = 0
        
    NOTE: input_exit_candle_day=0 means barssinceentry > 0, so S7 starts checking from day 2 after entry.
          This provides a 1-day grace period - no exit on entry day itself.
    """
    # Need enough data for ATR and consecutive days check
    if len(stock_prices) < atr_period + consecutive_days:
        return False
    
    # Calculate days since entry (today is stock_prices[-1])
    days_since_entry = len(stock_prices) - 1 - entry_index
    
    # Grace period: S7 activates from day 2 onwards (barssinceentry > activation_day)
    if days_since_entry <= activation_day:
        return False
    
    # Calculate ATR(22) for all bars
    highs = [bar.high for bar in stock_prices]
    lows = [bar.low for bar in stock_prices]
    closes = [bar.close for bar in stock_prices]
    
    atr_values = lewis_atr(highs, lows, closes, atr_period)
    if not atr_values or len(atr_values) < consecutive_days:
        return False
    
    # Check last consecutive_days (e.g., last 2 days)
    # stock_prices[-2] = yesterday, stock_prices[-1] = today
    count_bearish_large = 0
    
    for i in range(consecutive_days):
        bar_idx = len(stock_prices) - 1 - i
        atr_idx = len(atr_values) - 1 - i
        
        bar = stock_prices[bar_idx]
        atr = atr_values[atr_idx]
        
        if atr is None or atr <= 0:
            continue
        
        open_price = float(bar.open)
        close_price = float(bar.close)
        
        # Check both conditions:
        # 1. Bearish candle: close < open
        # 2. Large body: (open - close) > candle_factor * ATR
        is_bearish = close_price < open_price
        body_size = open_price - close_price
        is_large = body_size > candle_factor * atr
        
        if is_bearish and is_large:
            count_bearish_large += 1
    
    # Exit if ALL consecutive days have large bearish candles
    exit_signal = count_bearish_large >= consecutive_days
    
    # logger.info(
    #     f"S7_US - Day {days_since_entry}: "
    #     f"{count_bearish_large}/{consecutive_days} days with large bearish candles, "
    #     f"exit={exit_signal}"
    # )
    
    return exit_signal

#TODO S8
def checkS8_US(
    stock_prices: List[OHLCV],
    entry_index: int,
    lookback_period: int = 126,
    atr_short: int = 22,
    atr_long: int = 100,
    atr_threshold_pct: float = 74.0,
    candle_factor: float = 2.4,
    check_days: int = 5,
    min_dark_days: int = 3
) -> bool:
    """
    S8 for US King Algorithm - Extreme Volatility Exit
    
    Exit if volatility is extreme AND multiple large bearish candles appear.
    
    Two-stage check:
    1. Volatility condition: Current ATR(100) > 74% of max ATR(22) over past 126 days
    2. Dark candle condition: 3+ out of last 5 days have (open-close) > 2.4 * ATR(100)
    
    Args:
        stock_prices: Complete price data
        entry_index: Index of entry day in stock_prices array
        lookback_period: Days to look back for max ATR(22) (default 126)
        atr_short: Short ATR period (default 22)
        atr_long: Long ATR period (default 100)
        atr_threshold_pct: Threshold percentage (default 74.0)
        candle_factor: Multiplier for dark candle check (default 2.4)
        check_days: Number of recent days to check (default 5)
        min_dark_days: Minimum dark candles to trigger exit (default 3)
    
    Returns:
        True if exit signal (extreme volatility + multiple dark candles)
        False otherwise
    
    Documentation: "IF Current ATR({100}) is higher than {74%} of maximum ATR(22) in the past 126 day,
                    THEN EXIT the position if (open - close) > {2.4} x ATR({100}) for [3 out of 5] trading days"
    
    MC Code Reference (lines 659-680):
        is_stop_S8 = false;
        S8_dark_cnt = 0;
        if barssinceentry(0) > 0 then
        begin
            if _lewis_ATR(input_exit_S8_ATR) > highest(_lewis_ATR(22), 126)[1] * input_exit_S8_XX_percent/100 then
            begin
                for value1 = 0 to 4
                begin
                    if close[value1] < open[value1] and (open[value1] - close[value1]) > input_exit_S8_factor * _lewis_ATR(input_exit_S8_ATR)[value1] then S8_dark_cnt = S8_dark_cnt + 1;
                    if S8_dark_cnt >= 3 then
                    begin
                        is_stop_S8 = true;
                        break;
                    end;
                end;
            end
        end;
        
        input_exit_S8_factor = 2.4
        input_exit_S8_XX_percent = 74
        input_exit_S8_ATR = 100
    """
    # Need enough data for both ATR calculations and lookback
    min_data = max(atr_short, atr_long) + lookback_period + check_days
    if len(stock_prices) < min_data:
        return False
    
    # Calculate days since entry
    days_since_entry = len(stock_prices) - 1 - entry_index
    if days_since_entry <= 0:
        return False
    
    # Extract price data for ATR calculation
    highs = [float(bar.high) for bar in stock_prices]
    lows = [float(bar.low) for bar in stock_prices]
    closes = [float(bar.close) for bar in stock_prices]
    
    # Calculate ATR(22) and ATR(100)
    atr22_values = lewis_atr(highs, lows, closes, atr_short)
    atr100_values = lewis_atr(highs, lows, closes, atr_long)
    
    # Need enough ATR values
    if not atr22_values or not atr100_values:
        return False
    if len(atr22_values) < lookback_period + 1 or len(atr100_values) < check_days:
        return False
    
    # Stage 1: Check volatility condition
    # highest(_lewis_ATR(22), 126)[1] means max of PREVIOUS 126 bars, excluding current
    # Filter out None values from ATR(22)
    atr22_window = [x for x in atr22_values[-(lookback_period + 1):-1] if x is not None]
    if not atr22_window:
        return False
    max_atr22_previous = max(atr22_window)
    
    # Get current ATR(100)
    current_atr100 = atr100_values[-1]
    if current_atr100 is None or current_atr100 <= 0:
        return False
    
    # ATR(100) must be > 74% of max ATR(22)
    if current_atr100 <= (atr_threshold_pct / 100.0) * max_atr22_previous:
        return False
    
    # Stage 2: Count dark candles in last 5 days
    # for value1 = 0 to 4 means check today (0) to 4 days ago
    dark_count = 0
    
    for i in range(check_days):
        bar_idx = len(stock_prices) - 1 - i
        atr_idx = len(atr100_values) - 1 - i
        
        bar = stock_prices[bar_idx]
        atr100 = atr100_values[atr_idx]
        
        if atr100 is None or atr100 <= 0:
            continue
        
        open_price = float(bar.open)
        close_price = float(bar.close)
        
        # Check: close < open AND (open - close) > 2.4 * ATR(100)
        if close_price < open_price:
            body = open_price - close_price
            if body > candle_factor * atr100:
                dark_count += 1
                
                # Early exit if threshold reached (like MC break)
                if dark_count >= min_dark_days:
                    return True
    
    return False

#TODO S9
def checkS9_US(
    energy_signals: List[Dict[str, Any]],
    current_day_idx: int,
    energy_threshold: float = 0.22,
    lookback_period: int = 16
) -> bool:
    """
    S9 for US King Algorithm - Low Energy Exit
    
    Exit if average energy level is too low over recent period.
    
    Energy is calculated as sum of 5 components (E1-E5), each 0 or 1:
    - E1: New 20D high + close in upper range
    - E2: StochRSI(10) > 0.5
    - E3: Positive 66D price slope
    - E4: Outperforming SPY over 33 days
    - E5: Price in upper half of 5D range + rising + near 250D high
    
    Exit if average(Energy, 16) < 0.22 (4.4% of max energy 5)
    
    Args:
        energy_signals: List of pre-calculated energy signals with structure:
                        {"idx": day_idx, "energy": energy_sum, ...}
        current_day_idx: Current day index in the data
        energy_threshold: Energy threshold for exit (default 0.22)
        lookback_period: Period to average energy (default 16)
    
    Returns:
        True if exit signal (low energy)
        False otherwise
    
    Documentation: "Exit by making use of energy: IF {16-day} average energy level < {0.22}, THEN EXIT."
    
    MC Code Reference (lines 686-690):
        if average(Energy, input_energy_xx) < input_energy_yy then
            is_stop_energy = True
        else
            is_stop_energy = false;
        
        input_energy_xx = 16
        input_energy_yy = 0.22
        
        where Energy = E1+E2+E3+E4+E5 (calculated for each bar, range 0-5)
    """
    if not energy_signals:
        logger.warning("S9_US - No energy signals provided")
        return False
    
    # Find energy values for current day and previous 15 days (16 total)
    # Filter signals that have idx <= current_day_idx
    relevant_signals = [s for s in energy_signals if s["idx"] <= current_day_idx]
    
    if len(relevant_signals) < lookback_period:
        # Not enough history to calculate 16-day average
        # logger.warning(
        #     f"S9_US - Not enough energy history: {len(relevant_signals)} < {lookback_period}"
        # )
        return False
    
    # Get last 16 energy values (including current day)
    last_16_signals = relevant_signals[-lookback_period:]
    
    # Extract energy values (each is 0-5)
    energy_values = [s["energy"] for s in last_16_signals]
    
    # Calculate average energy over 16 days
    avg_energy = sum(energy_values) / lookback_period
    
    # Exit if average energy below threshold
    exit_signal = avg_energy < energy_threshold
    
    # logger.info(
    #     f"S9_US - Day idx {current_day_idx}: "
    #     f"avg_energy={avg_energy:.4f}, threshold={energy_threshold}, "
    #     f"exit={exit_signal}"
    # )
    
    return exit_signal

#TODO S13
def checkS13_US(
    stock_prices: List[OHLCV],
    entry_index: int,
    activation_day: int = 238,
    lookback_period: int = 80
) -> bool:
    """
    S13 for US King Algorithm - 80-Day Low Breakdown Exit
    
    Exit if current close falls below the lowest LOW of previous 80 days.
    
    EFFECTIVE after {activation_day} days since entry.
    
    Logic:
    1. Check if days_since_entry > 238
    2. Find lowest LOW in previous 80 bars (NOT including current bar)
    3. If close < lowest_low_80, EXIT
    
    Note: MC uses lowest(low, 80)[1], where [1] means previous bars.
    
    Args:
        stock_prices: Price data sorted by date, [-1] is today
        entry_index: Index of entry day in stock_prices array
        activation_day: Days after entry to activate (default 238)
        lookback_period: Period to find low (default 80)
    
    Returns:
        True if exit signal (close below 80D low)
        False otherwise
    
    Documentation: "Effective after {238} Days, Exit if close below {80} day closing low"
    
    MC Code Reference (lines 737-749):
        if barssinceentry(0) > input_S13_XX_day then
            if close < lowest(low, input_S13_YY_day)[1] then
                is_stop_S13 = True
        
        input_S13_XX_day = 238
        input_S13_YY_day = 80
    """
    # Need enough total data: current + previous 80 bars
    if len(stock_prices) < lookback_period + 1:
        return False
    
    # Calculate days since entry
    days_since_entry = len(stock_prices) - 1 - entry_index
    
    # Check activation condition (> not >=)
    if days_since_entry <= activation_day:
        return False
    
    # Get previous 80 bars (NOT including current)
    # stock_prices[-81:-1] gives bars from 81 days ago to yesterday
    prev_80_bars = stock_prices[-lookback_period - 1 : -1]
    
    if len(prev_80_bars) < lookback_period:
        return False
    
    # Find lowest LOW in previous 80 days
    lows = [float(bar.low) for bar in prev_80_bars]
    lowest_low_80 = min(lows)
    
    # Get current close
    current_close = float(stock_prices[-1].close)
    
    # Exit if current close below 80-day low
    exit_signal = current_close < lowest_low_80
    
    # logger.info(
    #     f"S13_US - Day {days_since_entry}: "
    #     f"current_close={current_close:.2f}, lowest_low_80={lowest_low_80:.2f}, "
    #     f"exit={exit_signal}"
    # )
    
    return exit_signal

#TODO S14
def checkS14_US(
    stock_prices: List[OHLCV],
    spy_prices: List[OHLCV],
    entry_index: int,
    activation_day: int = 300,
    base_period: int = 65
) -> bool:
    """
    S14 for US King Algorithm - Underperformance vs SPY Exit
    
    Exit if stock underperforms SPY benchmark across multiple timeframes.
    
    EFFECTIVE after {activation_day} days since entry.
    
    Logic:
    1. Check if days_since_entry > 300
    2. Calculate stock return over last 65, 130, 195 days
    3. Calculate SPY return over same periods
    4. If stock < SPY for ALL three periods, EXIT
    
    Return calculation: current_close / close[XX days ago]
    
    Args:
        stock_prices: Stock OHLCV data
        spy_prices: SPY benchmark OHLCV data
        entry_index: Index of entry day in stock_prices array
        activation_day: Days after entry to activate (default 300)
        base_period: Base comparison period (default 65)
    
    Returns:
        True if exit signal (underperforming SPY on all horizons)
        False otherwise
    
    Documentation: "Effective after {300} days, if price underperforming SPY for {65} and 2*{65} and 3*{65} days, then Exit"
    
    MC Code Reference (lines 751-760):
        if barssinceentry(0) > input_S14_YY then
            if close / close[input_S14_XX] < close data(2) / close[input_S14_XX] data(2) and
               close / close[input_S14_XX*2] < close data(2) / close[input_S14_XX*2] data(2) and
               close / close[input_S14_XX*3] < close data(2) / close[input_S14_XX*3] data(2) then
                   is_stop_S14 = true
        
        input_S14_XX = 65
        input_S14_YY = 300
        data(2) = SPY benchmark
    """
    # Calculate days since entry
    days_since_entry = len(stock_prices) - 1 - entry_index
    
    # Check activation condition (> not >=)
    if days_since_entry <= activation_day:
        return False
    
    # Define three comparison horizons
    horizons = [base_period, base_period * 2, base_period * 3]  # [65, 130, 195]
    
    # Need enough history for longest horizon
    max_horizon = horizons[-1]
    if len(stock_prices) < max_horizon + 1 or len(spy_prices) < max_horizon + 1:
        return False
    
    # Build date-to-close mappings
    stock_map = {bar.date: float(bar.close) for bar in stock_prices}
    spy_map = {bar.date: float(bar.close) for bar in spy_prices}
    
    # Find common trading dates
    common_dates = sorted([d for d in stock_map.keys() if d in spy_map])
    
    if len(common_dates) < max_horizon + 1:
        return False
    
    # Get aligned price series
    stock_closes = [stock_map[d] for d in common_dates]
    spy_closes = [spy_map[d] for d in common_dates]
    
    # Current index in common dates array
    current_idx = len(stock_closes) - 1
    
    # Check if stock underperforms SPY for ALL three horizons
    underperforms_all = True
    
    for horizon in horizons:
        past_idx = current_idx - horizon
        
        if past_idx < 0:
            return False
        
        # Calculate returns: current / past
        stock_return = stock_closes[current_idx] / stock_closes[past_idx]
        spy_return = spy_closes[current_idx] / spy_closes[past_idx]
        
        # MC: close / close[XX] < close data(2) / close[XX] data(2)
        if stock_return >= spy_return:
            underperforms_all = False
            break
    
    # logger.info(
    #     f"S14_US - Day {days_since_entry}: "
    #     f"horizons={horizons}, underperforms_all={underperforms_all}"
    # )
    
    return underperforms_all

#TODO S18
def checkS18_US(
    stock_prices: List[OHLCV],
    entry_index: int,
    activation_period: int = 20,
    lookback_period: int = 120
) -> bool:
    """
    S18 for US King Algorithm - Early Stage 120-Day Low Breakdown Exit
    
    Exit if close breaks below 120-day low during early holding period.
    
    This is an EARLY WARNING signal effective ONLY in first {activation_period} days.
    
    Logic:
    1. Check if days_since_entry < 20 (ONLY active in first 20 days)
    2. Find lowest LOW in PREVIOUS 120 bars (NOT including current bar)
    3. If close < lowest_low_120, EXIT
    
    This protects new positions - if stock breaks down through 120D low
    right after entry, it's a strong negative signal.
    
    Note: MC uses lowest(low, 120)[1], where [1] means previous bars only.
    
    Args:
        stock_prices: Price data sorted by date, [-1] is today
        entry_index: Index of entry day in stock_prices array
        activation_period: Days after entry when rule is active (default 20)
        lookback_period: Period to find low (default 120)
    
    Returns:
        True if exit signal (close below 120D low in first 20 days)
        False otherwise (or if activation period passed)
    
    Documentation: "If close below {120} days low then exit. Only valid for first {20} days"
    
    MC Code Reference (lines 796-803):
        //S18
        if barssinceentry(0) < input_S18_Y then
        begin
            if close < lowest(low, input_S18_X)[1] then
                is_stop_S18 = True
            else
                is_stop_S18 = false;
        end;
        
        input_S18_X = 120  (lookback_period for low)
        input_S18_Y = 20   (activation_period)
    
    Comparison with S13:
        S13: Active AFTER day 238, checks 80D low - long-term protection
        S18: Active BEFORE day 20, checks 120D low - early protection
    """
    # Need enough total data: current + previous 120 bars
    if len(stock_prices) < lookback_period + 1:
        return False
    
    # Calculate days since entry
    days_since_entry = len(stock_prices) - 1 - entry_index
    
    # Rule ONLY active during first {activation_period} days (< not <=)
    if days_since_entry >= activation_period:
        return False
    
    # Get previous 120 bars (NOT including current)
    # stock_prices[-121:-1] gives bars from 121 days ago to yesterday
    prev_120_bars = stock_prices[-lookback_period - 1 : -1]
    
    if len(prev_120_bars) < lookback_period:
        return False
    
    # Find lowest LOW in previous 120 days
    lows = [float(bar.low) for bar in prev_120_bars]
    lowest_low_120 = min(lows)
    
    # Get current close
    current_close = float(stock_prices[-1].close)
    
    # Exit if current close below 120-day low
    exit_signal = current_close < lowest_low_120
    
    # logger.info(
    #     f"S18_US - Day {days_since_entry}/{activation_period}: "
    #     f"current_close={current_close:.2f}, lowest_low_120={lowest_low_120:.2f}, "
    #     f"exit={exit_signal}"
    # )
    
    return exit_signal

#TODO S19
def checkS19_US(
    stock_prices: List[OHLCV],
    entry_index: int,
    buy_price: float,
    lookback_period: int = 41,
    atr_factor: float = 2.45,
    atr_period: int = 10
) -> bool:
    """
    S19 for US King Algorithm - Volume-Based Hard Stop Exit
    
    Exit if price falls below hard stop of highest volume UP day.
    
    This uses structural support based on volume profile to set stop loss.
    
    Logic:
    1. Search PREVIOUS {lookback_period} days (from yesterday to 41 days ago)
    2. Find UP days where: close[i] > close[i+1]
    3. Calculate hard_stop for each: low[i] - {atr_factor} * ATR({atr_period})[i]
    4. Filter: hard_stop must be below entry price
    5. Among qualifying days, select the one with HIGHEST volume
    6. EXIT if current close < that day's hard_stop
    
    The idea: High volume UP days represent strong support levels.
    If price breaks below that support, the structure is broken.
    
    Args:
        stock_prices: Price data sorted by date, [-1] is today
        entry_index: Index of entry day in stock_prices array
        buy_price: Entry price (entryprice(0) in MC)
        lookback_period: Days to search for reference day (default 41)
        atr_factor: ATR multiplier for hard stop (default 2.45)
        atr_period: ATR calculation period (default 10)
    
    Returns:
        True if exit signal (price below hard stop)
        False otherwise
    
    Documentation: "Set hard stop at low-{2.45}*ATR(10) of the highest volume UP day 
                    (with low-{2.45}*ATR(10) < buy close price) in past {41} days"
    
    MC Code Reference (lines 817-841):
        vars: is_stop_S19(false), max_vol(0), max_idx(0);
        
        is_stop_S19 = false;
        max_idx = 0;
        max_vol = 0;
        
        for value1 = 1 to input_B22_XX
        begin
            if low[value1] - input_B22_YY * _lewis_ATR(10)[value1] < entryprice(0)
            and close[value1] > close[value1+1]
            and volume[value1] > max_vol then
            begin
                max_vol = volume[value1];
                max_idx = value1;
            end;
        end;
        
        if max_idx > 0 and close < low[max_idx] - input_B22_YY * _lewis_ATR(10)[max_idx] then
            is_stop_S19 = True
        
        input_B22_XX = 41
        input_B22_YY = 2.45
    
    Relation to B22:
        B22: Checks if such a day EXISTS before entry (buy filter)
        S19: Uses same logic to set dynamic stop loss after entry
    """
    # Need enough data for ATR and lookback
    if len(stock_prices) < atr_period + lookback_period + 1:
        return False
    
    # Calculate days since entry (for logging only)
    days_since_entry = len(stock_prices) - 1 - entry_index
    
    # Extract price data for ATR calculation
    highs = [float(bar.high) for bar in stock_prices]
    lows = [float(bar.low) for bar in stock_prices]
    closes = [float(bar.close) for bar in stock_prices]
    volumes = [float(bar.volume) if bar.volume is not None else 0.0 for bar in stock_prices]
    
    # Calculate ATR(10) for all bars
    atr10_values = lewis_atr(highs, lows, closes, atr_period)
    if not atr10_values or len(atr10_values) < lookback_period + 1:
        return False
    
    # Current day index
    current_idx = len(stock_prices) - 1
    
    # Search for highest volume UP day in PREVIOUS 41 days
    # MC: for value1 = 1 to 41 means [1] to [41] (yesterday to 41 days ago)
    max_vol = 0
    max_idx = -1
    
    # logger.info(
    #     f"S19_US - Day {days_since_entry}: Searching for highest volume UP day in last {lookback_period} days. "
    #     f"Entry price: {buy_price:.2f}"
    # )
    
    for i in range(1, lookback_period + 1):
        day_idx = current_idx - i  # Yesterday to 41 days ago
        older_day_idx = day_idx - 1  # Day BEFORE (older in history)
        
        # Need at least one day before for UP day comparison
        if day_idx <= 0 or older_day_idx < 0:
            continue
        
        # ATR array is same length as price arrays - direct access
        atr10 = atr10_values[day_idx]
        if atr10 is None or atr10 <= 0:
            continue
        
        # Calculate hard stop for this day
        hard_stop = lows[day_idx] - atr_factor * atr10
        
        # Check three conditions:
        # 1. Hard stop below entry price
        # 2. UP day: close[value1] > close[value1+1] - compare with OLDER day
        # 3. Volume is maximum so far
        is_below_entry = hard_stop < buy_price
        is_up_day = closes[day_idx] > closes[older_day_idx]
        is_max_volume = volumes[day_idx] > max_vol
        
        if is_below_entry and is_up_day and is_max_volume:
            # logger.info(
            #     f"  → Day {i} days ago: NEW MAX - close={closes[day_idx]:.2f} > prev_close={closes[older_day_idx]:.2f}, "
            #     f"volume={volumes[day_idx]:.0f}, low={lows[day_idx]:.2f}, ATR(10)={atr10:.3f}, "
            #     f"hard_stop={hard_stop:.2f} (< entry {buy_price:.2f})"
            # )
            max_vol = volumes[day_idx]
            max_idx = day_idx
    
    # If no qualifying day found, no exit signal
    if max_idx < 0:
        # logger.info(
        #     f"S19_US - Day {days_since_entry}: ❌ No qualifying day found. "
        #     f"Searched last {lookback_period} days, NO EXIT"
        # )
        return False
    
    # Calculate hard stop of the reference day
    # ATR array is same length as price arrays - direct access
    atr10 = atr10_values[max_idx]
    if atr10 is None or atr10 <= 0:
        # logger.warning(
        #     f"S19_US - Day {days_since_entry}: Invalid ATR value at max_idx={max_idx}: {atr10}"
        # )
        return False
    
    hard_stop = lows[max_idx] - atr_factor * atr10
    
    # Get current close
    current_close = closes[current_idx]
    
    # Exit if current close below hard stop
    exit_signal = current_close < hard_stop
    
    days_ago = current_idx - max_idx
    # logger.info(
    #     f"S19_US - Day {days_since_entry}: 📊 Reference day: {days_ago} days ago, "
    #     f"volume={max_vol:.0f}, low={lows[max_idx]:.2f}, ATR(10)={atr10:.3f}, "
    #     f"hard_stop={hard_stop:.2f}, current_close={current_close:.2f}, "
    #     f"{'🚨 EXIT SIGNAL!' if exit_signal else '✅ No exit'}"
    # )
    
    return exit_signal

#TODO S20
def checkS20_US(
    stock_prices: List[OHLCV],
    entry_index: int,
    drop_factor: float = 5.4,
    check_days: int = 5,
    atr_periods: tuple[int, int, int] = (100, 20, 5),
    atr_count: float = 3
) -> bool:
    """
    S20 for US King Algorithm - Rapid Price Drop Exit
    
    Exit if price drops excessively within short period based on multi-period ATR.
    
    Logic:
    1. Calculate average of three ATR periods: ATR(100), ATR(20), ATR(5)
    2. Check if price drop over last {check_days} days exceeds {drop_factor} × avg_atr
    3. If close[5 days ago] - close[today] > 5.4 × avg_atr, EXIT
    
    This uses a composite ATR (combining long, medium, short-term volatility)
    to identify extreme price drops that exceed "normal" volatility-adjusted moves.
    
    Args:
        stock_prices: Price data sorted by date, [-1] is today
        entry_index: Index of entry day in stock_prices array
        drop_factor: ATR multiplier threshold (default 5.4)
        check_days: Days to check for price drop (default 5)
        atr_periods: Tuple of (long, medium, short) ATR periods (default (100, 20, 5))
        atr_count: Number of ATR periods to average (default 3)
    
    Returns:
        True if exit signal (excessive price drop)
        False otherwise
    
    Documentation: "ATR = [ATR(100)+ATR(20)+ATR(5)]/3
                    If price drops [{5.4} x ATR] within {5} days, Exit"
    
    MC Code Reference (lines 843-852):
        //S20
        input: input_S20_XX(5.4), input_S20_YY(5);
        vars: is_stop_S20(false);
        
        value1 = (_lewis_ATR(100) + _lewis_ATR(20) + _lewis_ATR(5)) / 3;
        
        if close[input_S20_YY] - close > input_S20_XX * value1 then
            is_stop_S20 = True
        else
            is_stop_S20 = false;
        
        input_S20_XX = 5.4
        input_S20_YY = 5
    
    Comparison with other signals:
        S7: 2 consecutive large bearish candles (2× ATR(22))
        S15: Fixed 25% drop in 4 days
        S16: 14% drop in 10 days with rising ATR
        S20: Dynamic threshold using multi-period ATR (5.4× avg_atr in 5 days)
    """
    atr_long, atr_medium, atr_short = atr_periods
    
    # Need enough data for longest ATR period (check_days are already within this data)
    min_required = max(atr_long, atr_medium, atr_short)
    if len(stock_prices) < min_required:
        return False
    
    
    # Extract price data for ATR calculations
    highs = [float(bar.high) for bar in stock_prices]
    lows = [float(bar.low) for bar in stock_prices]
    closes = [float(bar.close) for bar in stock_prices]
    
    # Calculate three ATR series
    atr100_values = lewis_atr(highs, lows, closes, atr_long)
    atr20_values = lewis_atr(highs, lows, closes, atr_medium)
    atr5_values = lewis_atr(highs, lows, closes, atr_short)
    
    # Verify all ATR calculations succeeded
    if not atr100_values or not atr20_values or not atr5_values:
        return False
    
    # Get current (latest) ATR values
    current_atr100 = atr100_values[-1]
    current_atr20 = atr20_values[-1]
    current_atr5 = atr5_values[-1]
    
    # Validate ATR values
    if (current_atr100 is None or current_atr100 <= 0 or
        current_atr20 is None or current_atr20 <= 0 or
        current_atr5 is None or current_atr5 <= 0):
        return False
    
    # Calculate composite ATR (average of atr_count periods)
    avg_atr = (current_atr100 + current_atr20 + current_atr5) / atr_count
    
    current_close = closes[-1]
    past_close = closes[-check_days-1]
    
    # Calculate price drop: close[5 days ago] - close[today]
    price_drop = past_close - current_close
    
    # Calculate threshold
    threshold = drop_factor * avg_atr
    
    # Exit if price drop exceeds threshold
    exit_signal = price_drop > threshold
    
    # logger.info(
    #     f"Past_close[{check_days}d ago]={past_close:.2f}, current_close={current_close:.2f}, "
    #     f"drop={price_drop:.2f}, "
    #     f"ATR(100)={current_atr100:.2f}, ATR(20)={current_atr20:.2f}, ATR(5)={current_atr5:.2f}, "
    #     f"avg_atr={avg_atr:.2f}, threshold={threshold:.2f}, "
    #     f"exit={exit_signal}"
    # )
    
    return exit_signal

def runAllSellConditions_US(
    stock_prices: List[OHLCV],
    spy_data: List[OHLCV],
    entry_index: int,
    buy_price: float,
    s1_stop_loss: float,
    s5_stop_loss: float,
    energy_signals: Optional[List[Dict[str, Any]]] = None,
    current_day_idx: Optional[int] = None
) -> dict:
    """
    Run all US King sell signal checks and return their states.
    
    Args:
        stock_prices: Stock OHLCV data
        spy_data: SPY benchmark data (for future signals like S9)
        entry_index: Index of entry day in stock_prices array
        buy_price: Entry price
        s1_stop_loss: S1 static stop loss value
        s5_stop_loss: S5 trailing stop loss value (0 if not initialized)
        trade_date: Current trading date
        energy_signals: Pre-calculated energy signals for S9 (optional)
        current_day_idx: Current day index for S9 (optional)
    
    Returns:
        Dictionary with:
        - conditions: Dict of signal names -> bool
        - s1_stop: S1 stop loss (unchanged)
        - s5_stop: Updated S5 stop loss value
        - exit1: max(s1_stop, s5_stop) - the active stop
    """
    # S5 returns both exit signal and new stop loss
    s5_exit, new_s5_stop = checkS5_US(stock_prices, entry_index, buy_price, s5_stop_loss)
    
    # S9 check
    s9_exit = False
    if energy_signals is not None and current_day_idx is not None:
        s9_exit = checkS9_US(energy_signals, current_day_idx)
    
    # Get buy_date from entry_index for signals that need it
    buy_date = stock_prices[entry_index].date
    
    conditions = {
        "S1": checkS1_US(stock_prices, s1_stop_loss),
        "S4": checkS4_US(stock_prices, entry_index),
        "S5": s5_exit,
        "S6": checkS6_US(stock_prices, entry_index),
        "S7": checkS7_US(stock_prices, entry_index),
        "S8": checkS8_US(stock_prices, entry_index),
        "S9": s9_exit,
        "S10": s10(stock_prices, buy_date, buy_price),
        "S11": s11(stock_prices, buy_date, buy_price),
        "S12": s12(stock_prices, buy_date, buy_price),
        "S13": checkS13_US(stock_prices, entry_index),
        "S14": checkS14_US(stock_prices, spy_data, entry_index),
        "S15": s15(stock_prices, buy_date, buy_price),
        "S16": s16(stock_prices, buy_date, s16_xx=14.0),
        "S17": s17(stock_prices, buy_date, buy_price),
        "S18": checkS18_US(stock_prices, entry_index),
        "S19": checkS19_US(stock_prices, entry_index, buy_price),
        "S20": checkS20_US(stock_prices, entry_index),
    }
    
    # Calculate exit1 as max of all stops (MultiCharts logic)
    exit1 = max(s1_stop_loss, new_s5_stop) if new_s5_stop > 0 else s1_stop_loss
    
    return {
        "conditions": conditions,
        "s1_stop": s1_stop_loss,
        "s5_stop": new_s5_stop,
        "exit1": exit1
    }

def isSell_US(signals: dict) -> bool:
    """
    Check if any sell signal is triggered for US King.
    
    Args:
        signals: Dictionary of signal names -> bool values
    
    Returns:
        True if any sell signal is True
        False otherwise
    """
    return (
        signals.get("S1", False)
        or signals.get("S4", False)
        or signals.get("S5", False)
        or signals.get("S6", False)
        or signals.get("S7", False)
        or signals.get("S8", False)
        or signals.get("S9", False)
        or signals.get("S10", False)
        or signals.get("S11", False)
        or signals.get("S12", False)
        or signals.get("S13", False)
        or signals.get("S14", False)
        or signals.get("S15", False)
        or signals.get("S16", False)
        or signals.get("S17", False)
        or signals.get("S18", False)
        or signals.get("S19", False)
        or signals.get("S20", False)
    )