from typing import List, Dict, Optional, Union
import logging

from app.workers.algo_func.helpers import sma, lewis_atr
from app.workers.algo_func.buy_signals import ( 
    bollinger_bands,
    check_b12, 
    check_b10, 
    check_b13,
    wilder_atr
)
from app.workers.algo_func.types import OHLCV

logger = logging.getLogger(__name__)

#TODO B1
def check_b1_us(
    stock_prices: List[OHLCV],
    bb_period: int = 22,
    bb_std_dev: float = 0.89,
    sma_period: int = 50,
    max_deviation: float = 0.25,
    close_ratio: float = 0.65
) -> bool:
    """
    B1 for US King Algorithm
    
    Conditions:
    1. Close > Bollinger Band(bb_period, bb_std_dev) upper band
    2. Close deviation from sma_period MA < max_deviation
    3. Close > Low + close_ratio * (High - Low)  [close in upper range of the day]
    
    Args:
        stock_prices: Price data
        bb_period: Bollinger Band period (default 22)
        bb_std_dev: Bollinger Band standard deviation multiplier (default 0.89)
        sma_period: SMA period for deviation check (default 50)
        max_deviation: Maximum allowed deviation from SMA (default 0.25 = 25%)
        close_ratio: Ratio for close position in day's range (default 0.65)
    
    Documentation: "CLOSE ABOVE Bollinger Band (22, 0.89) but not deviating from {50MA} by {25%}"
    
    MC Code Reference:
    - cond01c_bb: close > BB(input_B1_Y=22, input_B1_X=0.89) AND deviation check
    - cond01b_ClosevsHighLow: close > low + 0.65 * (high - low)
    - Final B1 = cond01c_bb AND cond01b_ClosevsHighLow
    
    Note: MC code has discrepancy - uses 22MA for deviation, but documentation says 50MA.
          Following documentation (50MA) as source of truth.
    Note: New High condition is NOT part of B1 for US King (only used for Energy E1)
    """
    min_bars = max(bb_period, sma_period)
    if len(stock_prices) < min_bars:
        return False
    
    closes = [bar.close for bar in stock_prices]
    last = stock_prices[-1]

    # Condition 1 & 2: Bollinger Band breakout with deviation check
    bb = bollinger_bands(closes, bb_period, bb_std_dev)
    sma_values = sma(closes, sma_period)
    
    condBB = False
    if bb and sma_values:
        lastBB = bb[-1]
        lastSMA = sma_values[-1]
        if lastBB and lastSMA and lastSMA > 0:
            deviation = (last.close - lastSMA) / lastSMA
            condBB = last.close > lastBB['upper'] and deviation < max_deviation
    
    # Condition 3: Close in upper range of the day
    condCloseInUpperRange = last.close > last.low + close_ratio * (last.high - last.low)
    
    # logger.info(
    #     f"B1_US - "
    #     f"BB({bb_period},{bb_std_dev}) breakout: {condBB}, "
    #     f"Close in upper range: {condCloseInUpperRange}, "
    #     f"Result: {condBB and condCloseInUpperRange}"
    # )
    
    return condBB and condCloseInUpperRange

#TODO B8
def check_b8_us(
    stock_prices: List[OHLCV],
    recent_period: int = 85,
    lookback_period: int = 150
) -> bool:
    """
    B8 for US King Algorithm - Higher Low Pattern
    
    Checks if recent lows are higher than past lows (forming higher low pattern).
    
    Condition:
    - Minimum low of last {recent_period} days > Minimum low from {recent_period+1} to {lookback_period} days ago
    - This ensures the stock is forming higher lows (uptrend confirmation)
    
    Args:
        stock_prices: Price data
        recent_period: Number of recent days to check (default 85)
        lookback_period: Total lookback period (default 150)
    
    Documentation: "{85D} low > T-{86D} to T-{150D} low"
    
    MC Code Reference:
    - lowestbar(low, input_higher_low_len=150) > input_higher_low_threshold=85
    - This means: the BAR (position) where lowest low occurred is MORE than 85 bars ago
    - lowestbar() returns bars ago (0=today, 1=yesterday, etc.)
    - If lowestbar returns 86, it means lowest low was 86 days ago -> 86 > 85 -> TRUE
    - If lowestbar returns 85, it means lowest low was 85 days ago -> 85 > 85 -> FALSE
    - If lowestbar returns 50, it means lowest low was 50 days ago -> 50 > 85 -> FALSE
    
    CORRECT LOGIC: Find WHEN (bars ago) the lowest low occurred, not WHAT VALUE
    """
    if len(stock_prices) < lookback_period:
        return False
    
    lows = [bar.low for bar in stock_prices]
    # current_date = stock_prices[-1].date
    
    # Find the minimum low value in the last 150 days
    lowest_value = min(lows[-lookback_period:])
    
    # Find how many bars ago this lowest low occurred
    # lowestbar() returns bars ago: 0 = today, 1 = yesterday, etc.
    # We search from most recent (index 0) to oldest (index lookback_period-1)
    bars_ago = next(i for i in range(lookback_period) if lows[-(i+1)] == lowest_value)
    
    # In MultiCharts: lowestbar(low, 150) > 85
    # If lowest low was more than 85 days ago, it's a higher low pattern
    result = bars_ago > recent_period
    
    # Get the date and absolute index for logging
    # lowest_idx = len(lows) - 1 - bars_ago
    # lowest_date = stock_prices[lowest_idx].date
    
    # logger.info(
    #     f"B8_US - Current date: {current_date}\n"
    #     f"  Lowest low in past {lookback_period} days:\n"
    #     f"    Value: {lowest_value:.4f} on {lowest_date} ({bars_ago} bars ago)\n"
    #     f"  Threshold: {recent_period} bars\n"
    #     f"  Result: {result} (lowestbar {bars_ago} > {recent_period}: {bars_ago > recent_period})"
    # )
    
    return result

#TODO B9
def check_b9_us(
    stock_prices: List[OHLCV],
    lookback_period: int = 105
) -> bool:
    """
    B9 for US King Algorithm - Cancel Buy on Weak Price Action
    
    CANCEL buy signal if BOTH conditions are true:
    1. Current close < midpoint of (High + Low) over lookback period
    2. High occurred earlier than Low (high date < low date)
    
    This identifies weak price action where:
    - Stock reached its high early in the period
    - Then fell to its low
    - Current price is below the midpoint (weak recovery)
    
    Args:
        stock_prices: Price data
        lookback_period: Number of days to look back (default 105)
    
    Returns:
        True if buy signal is valid (NOT cancelled)
        False if buy signal should be cancelled
    
    Documentation: "CANCEL Buy if Close < (Last {105D} High + Last {105D} Low) /2 
                    and high Date is earlier than low date"
    
    MC Code Reference:
    - if close < (highest(high, input_hl_range) + lowest(low, input_hl_range)) / 2
        and highestbar(high, input_hl_range) > lowestbar(low, input_hl_range) then
        cond13_hl_range = false
    - input_hl_range = 105 for US King
    
    Example:
    - If high occurred on day 10 and low on day 80 of 105-day period
    - And current close < (high + low) / 2
    - This suggests weakness: peaked early, fell later, poor recovery → CANCEL
    """
    if len(stock_prices) < lookback_period:
        return False
    
    last_period = stock_prices[-lookback_period:]
    closes = [bar.close for bar in last_period]
    highs = [bar.high for bar in last_period]
    lows = [bar.low for bar in last_period]
    
    current_close = closes[-1]
    
    max_high = max(highs)
    min_low = min(lows)
    
    # Get the last occurrence of max and min values
    high_index = max(i for i, v in enumerate(highs) if v == max_high)
    low_index = max(i for i, v in enumerate(lows) if v == min_low)
    
    midpoint = (max_high + min_low) / 2
    
    cond_close_below_mid = current_close < midpoint
    cond_high_earlier_than_low = high_index < low_index
    
    # Return True if buy is valid (NOT cancelled)
    # Cancel if BOTH conditions are true
    result = not (cond_close_below_mid and cond_high_earlier_than_low)
    
    # logger.info(
    #     f"B9_US ({lookback_period}D) - "
    #     f"Close: {current_close:.2f}, Mid: {midpoint:.2f}, "
    #     f"High@idx:{high_index}, Low@idx:{low_index}, "
    #     f"Valid: {result}"
    # )
    
    return result

#TODO B10
# Documentation: "if 250D low happens within {68} days before breakout, cancel buy"
# MC Code: lowestbar(low, 250) < input_XXXD_low_day (where input_XXXD_low_day = 68)
# 
# Use check_b10() from buy_signals.py with default parameters:
# - lookback_period = 250
# - recent_period = 68
# 
# No need for separate check_b10_US() - parameters are identical

#TODO B11
def check_b11_us(
    stock_prices: List[OHLCV],
    lookback_period: int = 215,
    threshold_percent: float = 0.67
) -> bool:
    """
    B11 for US King Algorithm - Cancel if ATR is too high (high volatility)
    
    CANCEL buy signal if current ATR is too high compared to historical max.
    High ATR indicates increased volatility/risk.
    
    Condition:
    - Calculate current ATR(22)
    - Find maximum ATR(22) in the past {lookback_period} days
    - If current > {threshold_percent} * max → CANCEL (too volatile)
    
    Args:
        stock_prices: Price data
        lookback_period: Period to find max ATR (default 215)
        threshold_percent: Threshold as decimal (default 0.67 = 67%)
    
    Returns:
        True if buy signal is valid (ATR not too high)
        False if buy signal should be cancelled (ATR too high)
    
    Documentation: "IF Current ATR(22) is higher than {67%} of maximum ATR(22) 
                    in the past {215} day, THEN cancel buy."
    
    MC Code Reference:
    - if _lewis_ATR(22) > highest(_lewis_ATR(22), input_highest_ATR_YY_day)[1] 
        * input_highest_ATR_XX_percent/100 then cond17_highest_ATR = false
    - input_highest_ATR_YY_day = 215 for US King
    - input_highest_ATR_XX_percent = 67 for US King
    
    Note: MC code comment is WRONG (says 87% and 126 days - that's from HK Algo)
          Real US King parameters are 67% and 215 days.
    
    Comparison with HK:
    - HK: 126 days lookback, 87% threshold (more lenient)
    - US: 215 days lookback, 67% threshold (more strict)
    """
    min_bars = lookback_period + 22  # Need lookback + ATR period
    if len(stock_prices) < min_bars:
        return False
    
    highs = [bar.high for bar in stock_prices]
    lows = [bar.low for bar in stock_prices]
    closes = [bar.close for bar in stock_prices]
    
    # Calculate ATR(22) for all bars
    atr_values = lewis_atr(highs, lows, closes, 22)
    
    current_atr = atr_values[-1]
    if current_atr is None:
        return False
    
    # Get ATR values for the lookback period (excluding current day)
    # atr_values[-lookback_period-1:-1] gives us last 'lookback_period' values before today
    prev_window = atr_values[-(lookback_period + 1):-1]
    prev_window = [x for x in prev_window if x is not None]
    
    if len(prev_window) < lookback_period:
        return False
    
    max_prev_atr = max(prev_window)
    
    # Check if current ATR > threshold * max historical ATR
    # If yes, volatility too high → cancel
    is_too_volatile = current_atr > (threshold_percent * max_prev_atr)
    result = not is_too_volatile
    
    # logger.info(
    #     f"B11_US ({lookback_period}D) - "
    #     f"Current ATR: {current_atr:.4f}, "
    #     f"Max historical: {max_prev_atr:.4f}, "
    #     f"Threshold ({threshold_percent*100:.0f}%): {threshold_percent * max_prev_atr:.4f}, "
    #     f"Valid: {result}"
    # )
    
    return result


#TODO B12
# Documentation: "If 150D SMA has risen {16%} in the past {50} days AND Today high is deviating from 150DMA by 20%, THEN CANCEL Buy"
# MC Code: if average(close,150)/average(close,150)[50]-1 > 16/100 and high/average(close, 150)-1 > 20/100 then cond18_B12 = false
# 
# Use check_b12() from buy_signals.py with default parameters:
# - input_B12_growth = 0.16 (16%)
# - input_B12_days = 50
# - input_B12_deviation = 0.2 (20%)
# - input_B12_sma_period = 150
# 
# No need for separate check_b12_US() - parameters are identical

#TODO B13
# Documentation: "CANCEL buy if the stock is underperforming SPY for {19}-Day AND {100}-Day look back periods."
# MC Code: if close/close[input_B13_XX] < close data(2)/close[input_B13_XX] data(2) and
#             close/close[input_B13_YY] < close data(2)/close[input_B13_YY] data(2) then cond19_B13 = false
# 
# Use check_b13() from buy_signals.py with US King parameters:
# - input_B13_XX = 19 (same as HK)
# - input_B13_YY = 100 (different from HK's 60)
# - Index data = SPY (for US), HSI (for HK)
# 
# Usage:
#   check_b13(stock_ohlcv, spy_ohlcv, input_B13_XX=19, input_B13_YY=100)
# 
# Note: Default parameters are for HK (19, 60), so MUST specify input_B13_YY=100 for US King

def linear_regression_slope(values: List[float], length: int) -> float:
    """
    Calculate linear regression slope for a series of values.
    
    Implements MultiCharts LINEARREGSLOPE function using standard least squares method.
    This is DIFFERENT from slope_sma_bbw_mc which uses HK-specific LinearRegValue method.
    
    US King uses: LINEARREGSLOPE(Vma, 50)
    HK uses: (LinearRegValue(sma, len, 0) - LinearRegValue(sma, len, len-1)) / len
    
    Args:
        values: List of values to calculate slope for
        length: Number of periods to use
    
    Returns:
        Slope value (positive = increasing, negative = decreasing)
        
    Formula: slope = Σ((x - x_mean)(y - y_mean)) / Σ((x - x_mean)^2)
    """
    if len(values) < length or length <= 0:
        return 0.0
    
    # Take last 'length' values
    window = values[-length:]
    
    # X values: 0, 1, 2, ..., length-1
    x_values = list(range(length))
    x_mean = sum(x_values) / length
    y_mean = sum(window) / length
    
    # Calculate slope using least squares
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_values, window))
    denominator = sum((x - x_mean) ** 2 for x in x_values)
    
    if denominator == 0:
        return 0.0
    
    return numerator / denominator

#TODO B18
def check_b18_us(
    stock_prices: List[OHLCV],
    high_price_period: int = 252,
    near_high_threshold: float = 0.6,
    vol_ma_period: int = 50,
    vol_slope_period: int = 50,
    pivot_period: int = 5,
    pivot_width_threshold: float = 0.1,
    vol_dryup_period: int = 5
) -> bool:
    """
    B18 for US King Algorithm - Volatility Contraction Pattern (VCP) Detection
    
    VCP is Mark Minervini's pattern for identifying breakout setups.
    ALL 4 conditions must be TRUE for a valid VCP signal.
    
    Conditions:
    1. NearHigh: Price below 252D high but above 60% of 252D high
    2. VolDecreasing: 50D SMA of volume has negative linear regression slope (50 periods)
    3. IsPivot: 5D range < 10% of price AND 5D high was at start of period
    4. VolDryUp: Each of last 5 days has volume < its own 50D volume MA
    
    Args:
        stock_prices: Price data with OHLCV
        high_price_period: Period for finding high price (default 252)
        near_high_threshold: Threshold for near high (default 0.6 = 60%)
        vol_ma_period: Volume MA period (default 50)
        vol_slope_period: Period for volume slope calculation (default 50)
        pivot_period: Period for pivot detection (default 5)
        pivot_width_threshold: Max pivot width as fraction of price (default 0.1 = 10%)
        vol_dryup_period: Period to check for volume dry-up (default 5)
    
    Returns:
        True if VCP pattern detected (all 4 conditions met)
        False otherwise
    
    Documentation: "B18. Mark Minervini's Volatility Contraction Pattern (VCP) Detection"
    
    MC Code Reference (lines 403-429):
        HighPrice = highest(close, 252);
        NearHigh = close < HighPrice AND close > 0.6 * HighPrice;
        
        Vma = average(volume, 50);
        VolSlope = LINEARREGSLOPE(Vma, 50);
        VolDecreasing = VolSlope < 0;
        
        PivotHighPrice = highest(high, 5);
        PivotLowPrice = lowest(L, 5);
        PivotWidth = (PivotHighPrice - PivotLowPrice)/close;
        PivotStartHP = high[5-1];
        IsPivot = PivotWidth < 0.1 AND PivotHighPrice = PivotStartHP;
        
        VolDryUp = True;
        for value1 = 0 to 4
            VolDryUp = VolDryUp AND volume[value1] < Vma[value1];
        
        if NearHigh AND VolDecreasing AND IsPivot AND VolDryUp then cond_B18 = true
    
    Note: Volume is REQUIRED for VCP - pattern cannot be detected without volume data
    """
    # Need enough data for all calculations
    min_required = max(high_price_period, vol_ma_period + vol_slope_period)
    if len(stock_prices) < min_required:
        return False
    
    closes = [bar.close for bar in stock_prices]
    highs = [bar.high for bar in stock_prices]
    lows = [bar.low for bar in stock_prices]
    volumes = [bar.volume if bar.volume is not None else 0 for bar in stock_prices]
    
    current_close = closes[-1]
    
    # Condition 1: NearHigh
    # Price is below 252D high but above 60% of it
    high_price_252 = max(closes[-high_price_period:])
    near_high = (current_close < high_price_252) and (current_close > near_high_threshold * high_price_252)
    
    if not near_high:
        # logger.debug(f"B18_US - NearHigh failed: close={current_close:.2f}, 252D high={high_price_252:.2f}")
        return False
    
    # Condition 2: VolDecreasing
    # 50D SMA of volume has negative linear regression slope
    vol_ma_series = sma(volumes, vol_ma_period)
    
    if len(vol_ma_series) < vol_slope_period:
        return False
    
    vol_slope = linear_regression_slope(vol_ma_series, vol_slope_period)
    vol_decreasing = vol_slope < 0
    
    if not vol_decreasing:
        # logger.debug(f"B18_US - VolDecreasing failed: slope={vol_slope:.6f}")
        return False
    
    # Condition 3: IsPivot
    # 5D range < 10% of current price AND 5D high was at the start (4 days ago)
    last_5_highs = highs[-pivot_period:]
    last_5_lows = lows[-pivot_period:]
    
    pivot_high = max(last_5_highs)
    pivot_low = min(last_5_lows)
    pivot_width = (pivot_high - pivot_low) / current_close
    
    # high[5-1] in MC = highs[-5] in Python (high from 4 days ago, at start of 5-day window)
    pivot_start_hp = highs[-pivot_period]
    
    is_pivot = (pivot_width < pivot_width_threshold) and (pivot_high == pivot_start_hp)
    
    if not is_pivot:
        # logger.debug(
        #     f"B18_US - IsPivot failed: width={pivot_width:.4f} (threshold={pivot_width_threshold}), "
        #     f"pivot_high={pivot_high:.2f}, start_high={pivot_start_hp:.2f}"
        # )
        return False
    
    # Condition 4: VolDryUp
    # Each of last 5 days has volume < its own 50D volume MA
    # In MC: volume[i] < Vma[i] means volume i days ago < 50MA of volume i days ago
    
    # Calculate 50MA for each of the last 5 days
    vol_dry_up = True
    
    for i in range(vol_dryup_period):
        # Index in our array: -1 is today (i=0), -2 is yesterday (i=1), etc.
        day_index = -(i + 1)
        
        # Calculate 50D MA for this specific day
        # Need vol_ma_period bars ending at this day
        start_idx = len(volumes) + day_index - vol_ma_period + 1
        end_idx = len(volumes) + day_index + 1
        
        if start_idx < 0:
            return False
        
        vol_window = volumes[start_idx:end_idx]
        day_vol_ma = sum(vol_window) / vol_ma_period
        day_volume = volumes[day_index]
        
        if day_volume >= day_vol_ma:
            vol_dry_up = False
            # logger.debug(
            #     f"B18_US - VolDryUp failed at day {i}: "
            #     f"volume={day_volume:.0f}, 50MA={day_vol_ma:.0f}"
            # )
            break
    
    if not vol_dry_up:
        return False
    
    # All 4 conditions met - VCP detected!
    # logger.info(
    #     f"B18_US - VCP DETECTED: "
    #     f"NearHigh={near_high}, VolDecreasing={vol_decreasing}, "
    #     f"IsPivot={is_pivot}, VolDryUp={vol_dry_up}"
    # )
    
    return True

#TODO B20
def check_b20_us(
    stock_prices: List[OHLCV],
    volume_period: int = 20,
    highvol_period: int = 20
) -> bool:
    """
    B20 for US King Algorithm - Volume Analysis (Up/Down Volume + Recent High Volume)
    
    Checks for buying pressure and recent volume activity:
    1. Total up-day volume > total down-day volume over the period
    2. Highest volume in recent period is in TOP-2 among all 21 days
    
    This identifies accumulation patterns where buyers are more active
    and the interest is RECENT (not stale from weeks ago).
    
    Args:
        stock_prices: Price data with OHLCV
        volume_period: Period for volume analysis (default 20)
        highvol_period: Period for checking recent high volume (default 20)
    
    Returns:
        True if both conditions met (buying pressure + recent activity)
        False otherwise
    
    Documentation: "Total up day volume more than total down day volume in the past {20} days 
                    and the highest volume in the past {20} days is the highest or the second 
                    highest volume in the past {20} days."
    
    MC Code Reference (lines 433-465):
        Array_SetMaxIndex(vol_hist, input_B20_XX);  // input_B20_XX = 20
        
        for value1 = 0 to input_B20_XX  // 0 to 20 = 21 iterations
        begin
            vol_hist[value1] = volume[value1];
        end;
        
        array_sort(vol_hist, 0, input_B20_XX, false);  // descending
        
        if highest(volume, input_B20_YY) >= vol_hist[1] then  // input_B20_YY = 20
            highvol = true
        
        updayvol = 0;
        downdayvol = 0;
        IF CLOSE > CLOSE[1] THEN
            updayvol = VOLUME
        else if close < close[1] then
            downdayvol = VOLUME;
        
        value1 = summation(updayvol, input_B20_XX);
        value2 = summation(downdayvol, input_B20_XX);
        if value2 > 0 then
        begin
            if value1 > value2 and highvol then
                cond_B20 = True
        end;
    
    Note: The check uses 21 days (volume[0] to volume[20]) to include one extra day
          for detecting if big volume was stale (happened 21 days ago vs recent 20 days)
    """
    # Need 21 days: volume[0] to volume[20]
    min_required = volume_period + 1 + 1  # +1 for volume[20], +1 for close[1] reference
    if len(stock_prices) < min_required:
        return False
    
    closes = [bar.close for bar in stock_prices]
    volumes = [bar.volume if bar.volume is not None else 0 for bar in stock_prices]
    
    # Check for volume data
    if all(v == 0 for v in volumes[-min_required:]):
        # logger.warning("B20_US: No volume data available")
        return False
    
    # Condition 1: highvol check
    # Copy volume[0] to volume[20] (21 values) and sort descending
    vol_hist = volumes[-(volume_period + 1):]  # Last 21 values
    vol_hist_sorted = sorted(vol_hist, reverse=True)
    
    # vol_hist_sorted[0] = biggest volume of 21 days
    # vol_hist_sorted[1] = second biggest volume of 21 days
    
    # Check if highest volume in last 20 days >= second biggest of 21 days
    max_recent_volume = max(volumes[-highvol_period:])  # Last 20 days only
    highvol = max_recent_volume >= vol_hist_sorted[1]
    
    if not highvol:
        # logger.debug(
        #     f"B20_US - highvol failed: max_recent={max_recent_volume:.0f}, "
        #     f"second_of_21={vol_hist_sorted[1]:.0f}"
        # )
        return False
    
    # Condition 2: Up-day volume vs Down-day volume
    # Calculate total volume on up days and down days
    total_up_volume = 0
    total_down_volume = 0
    
    for i in range(1, volume_period + 1):
        idx = -i
        current_close = closes[idx]
        prev_close = closes[idx - 1]
        current_volume = volumes[idx]
        
        if current_close > prev_close:
            total_up_volume += current_volume
        elif current_close < prev_close:
            total_down_volume += current_volume
    
    # Need some down volume to avoid division issues and ensure meaningful comparison
    if total_down_volume == 0:
        # logger.debug("B20_US - No down volume in period (all up days or flat)")
        # If no down days, check if there's significant up volume
        result = total_up_volume > 0
    else:
        result = total_up_volume > total_down_volume
    
    # logger.info(
    #     f"B20_US - "
    #     f"Up volume: {total_up_volume:.0f}, Down volume: {total_down_volume:.0f}, "
    #     f"highvol: {highvol}, Result: {result and highvol}"
    # )
    
    return result and highvol

#TODO B21
def check_b21_us(
    stock_prices: List[OHLCV],
    r3_period: int = 60,          # 3M approximation
    r1_period: int = 20,          # 1M approximation
    range_multiplier: float = 1.09,  # R3 must be 9% bigger
    drawdown_threshold: float = 0.042  # 4.2% from high
) -> bool:
    """
    B21 for US King Algorithm - Range Expansion Check
    
    CANCEL buy if range is too narrow or price too close to peak.
    
    Conditions (both must be TRUE):
    1. R3 (60D range) > R1 (20D range) × 1.09
       - Ensures stock has sufficient range expansion (not stuck in narrow consolidation)
    2. Close < 60D high × (1 - 4.2%)
       - Ensures we're not buying at the very peak (room to breathe)
    
    Args:
        stock_prices: Price data
        r3_period: Period for R3 range calculation (default 60 = 3 months)
        r1_period: Period for R1 range calculation (default 20 = 1 month)
        range_multiplier: Minimum R3/R1 ratio (default 1.09 = 9% bigger)
        drawdown_threshold: Max drawdown from high (default 0.042 = 4.2%)
    
    Returns:
        True if buy signal is valid (good range + not at peak)
        False if buy signal should be cancelled
    
    Documentation: "R3 = 3M high - 3M low, R1 = 1M high - 1M low
                    Only release buy signal if R3 is at least {1.09} bigger than R1
                    AND Price is less than {4.2%} below 3 month high"
    
    MC Code Reference (lines 468-480):
        value3 = highest(high, 60) - lowest(low, 60);  // R3
        value1 = highest(high, 20) - lowest(low, 20);  // R1
        
        if value3 > value1 * input_B21_XX and 
           close < highest(high, 60) * (1-input_B21_YY/100) then
            cond_B21 = true
        
        input_B21_XX = 1.09
        input_B21_YY = 4.2
    """
    # Step 1: Validate data availability
    if len(stock_prices) < r3_period:
        return False
    
    # Step 2: Extract price data
    highs = [bar.high for bar in stock_prices]
    lows = [bar.low for bar in stock_prices]
    closes = [bar.close for bar in stock_prices]
    current_close = closes[-1]
    
    # Step 3: Calculate R3 (60D range)
    high_60d = max(highs[-r3_period:])
    low_60d = min(lows[-r3_period:])
    r3 = high_60d - low_60d
    
    # Step 4: Calculate R1 (20D range)
    high_20d = max(highs[-r1_period:])
    low_20d = min(lows[-r1_period:])
    r1 = high_20d - low_20d
    
    # Step 5: Condition 1 - Range expansion check
    # R3 must be at least 9% bigger than R1
    range_expansion_ok = r3 > (r1 * range_multiplier)
    
    # Step 6: Condition 2 - Not at peak check
    # Close must be below (60D high - 4.2%)
    max_allowed_price = high_60d * (1 - drawdown_threshold)
    not_at_peak = current_close < max_allowed_price
    
    # Step 7: Both conditions must be TRUE
    result = range_expansion_ok and not_at_peak
    
    # Step 8: Logging for debug
    # logger.info(
    #     f"B21_US - "
    #     f"R3(60D): {r3:.2f}, R1(20D): {r1:.2f}, "
    #     f"R3/R1: {r3/r1:.2f} (min {range_multiplier:.2f}), "
    #     f"Close: {current_close:.2f}, Max allowed: {max_allowed_price:.2f} "
    #     f"({(1-drawdown_threshold)*100:.1f}% of {high_60d:.2f}), "
    #     f"Range OK: {range_expansion_ok}, Not at peak: {not_at_peak}, "
    #     f"Result: {result}"
    # )
    
    return result

#TODO B22
def check_b22_us(
    stock_prices: List[OHLCV],
    lookback_period: int = 41,
    atr_multiplier: float = 2.45
) -> bool:
    """
    B22 for US King Algorithm - Hard Stop Validation
    
    CANCEL buy if cannot find a valid hard_stop level.
    
    Searches for the highest volume UP day in the past {lookback_period} days
    where a hard_stop (low - atr_multiplier * ATR(10)) can be placed below
    the current close price.
    
    This ensures we can set a protective stop at a meaningful level
    (below a high-volume accumulation day).
    
    Algorithm:
    1. Loop through past {lookback_period} days (excluding today)
    2. For each day, check if:
       a) It's an UP day: close[i] > close[i+1]
       b) hard_stop is valid: low[i] - 2.45*ATR(10)[i] < current_close
       c) Track the day with highest volume among valid candidates
    3. If at least one valid day found → True (can set stop)
       If no valid day found → False (CANCEL buy - no safe stop level)
    
    Args:
        stock_prices: Price data with OHLCV
        lookback_period: Period to search for high volume day (default 41)
        atr_multiplier: Multiplier for ATR in stop calculation (default 2.45)
    
    Returns:
        True if valid hard_stop can be found
        False if no valid hard_stop (CANCEL buy)
    
    Documentation: "Cancel buy if hard_stop cannot be found at the 
                    low-{2.45}*ATR(10) of the highest volume UP day 
                    (with low-{2.45}*ATR(10) < buy close price) in past {41} days"
    
    MC Code Reference (lines 485-505):
        B22_max_idx = 0;
        B22_max_vol = 0;
        for value1 = 1 to input_B22_XX  // 1 to 41
        begin
            if low[value1] - input_B22_YY * _lewis_ATR(10)[value1] < close
            and close[value1] > close[value1+1]
            and volume[value1] > B22_max_vol then
            begin
                B22_max_vol = volume[value1];
                B22_max_idx = value1;
            end;
        end;
        
        if B22_max_idx > 0 then cond_B22 = True
        
        input_B22_XX = 41
        input_B22_YY = 2.45
    
    Note: Volume is REQUIRED - cannot validate hard_stop without volume data
    """
    # Step 1: Validate data availability
    # Need lookback_period + 1 (for close[i+1] comparison) + 10 (for ATR)
    min_required = lookback_period + 1 + 10
    if len(stock_prices) < min_required:
        return False
    
    # Step 2: Extract price data
    highs = [bar.high for bar in stock_prices]
    lows = [bar.low for bar in stock_prices]
    closes = [bar.close for bar in stock_prices]
    volumes = [bar.volume if bar.volume is not None else 0 for bar in stock_prices]
    
    current_close = closes[-1]
    
    # Check for volume data
    if all(v == 0 for v in volumes[-min_required:]):
        # logger.warning("B22_US: No volume data available")
        return False
    
    # Step 3: Calculate ATR(10) for all bars
    atr_values = lewis_atr(highs, lows, closes, 10)
    
    # Step 4: Search for highest volume UP day with valid hard_stop
    max_volume = 0
    max_volume_idx = 0
    
    # Loop from 1 to lookback_period (value1 = 1 to 41 in MC)
    # value1 = 1 means yesterday (closes[-2])
    for i in range(1, lookback_period + 1):
        idx = -i - 1  # Current day index in our list
        idx_prev = idx - 1  # Previous day (i+1 in MC notation)
        
        day_close = closes[idx]
        prev_close = closes[idx_prev]
        day_low = lows[idx]
        day_volume = volumes[idx]
        day_atr = atr_values[idx]
        
        if day_atr is None:
            continue
        
        # Condition 1: UP day (close[i] > close[i+1])
        is_up_day = day_close > prev_close
        
        # Condition 2: hard_stop < current close
        hard_stop = day_low - (atr_multiplier * day_atr)
        stop_is_valid = hard_stop < current_close
        
        # Condition 3: Track maximum volume
        if is_up_day and stop_is_valid and day_volume > max_volume:
            max_volume = day_volume
            max_volume_idx = i
            # logger.debug(
            #     f"B22_US - Found valid candidate: day {i} days ago, "
            #     f"volume={day_volume:.0f}, low={day_low:.2f}, "
            #     f"ATR(10)={day_atr:.2f}, hard_stop={hard_stop:.2f}"
            # )
    
    # Step 5: Check if valid day was found
    result = max_volume_idx > 0
    
    # Step 6: Logging for debug
    # if result:
    #     logger.info(
    #         f"B22_US - Valid hard_stop found: "
    #         f"{max_volume_idx} days ago, volume={max_volume:.0f}, "
    #         f"Result: True"
    #     )
    # else:
    #     logger.info(
    #         f"B22_US - No valid hard_stop found in past {lookback_period} days, "
    #         f"Result: False (CANCEL buy)"
    #     )
    
    return result


def calc_s1_stop_us(
    stock_prices: List[OHLCV], 
    factor: float = 3.4,
    atr_period: int = 22, 
    loss_threshold: float = 0.20,
    adjusted_stop_percent: float = 0.072,
    entry_close: Optional[float] = None
) -> float:
    """
    Calculate S1 stop loss for US King Algorithm
    
    US King uses different parameters than HK Algo:
    - ATR factor: 3.4 (vs 3.7 for HK)
    - Adjusted stop: 7.2% (vs 9.5% for HK)
    - NO 30% risk threshold (HK has 14.25% stop for >30% risk)
    
    Logic:
    1. Base stop = close - 3.4 * ATR(22)
    2. Calculate risk = (close - base_stop) / close
    3. If risk > 20%, use adjusted stop at 7.2% instead
    
    Args:
        stock_prices: Price data
        factor: ATR multiplier (default 3.4 for US)
        atr_period: ATR period (default 22)
        loss_threshold: Risk threshold (default 0.20 = 20%)
        adjusted_stop_percent: Fixed stop when risk too high (default 0.072 = 7.2%)
        entry_close: Optional entry price (default: last close)
    
    Returns:
        Stop loss price, or NaN if calculation fails
    
    Documentation: "Use [CLOSE - {3.4}*ATR({22})] as stop position, 
                    if stop loss is > {20%}, set stop loss at {7.2%}"
    
    MC Code Reference (lines 550-553):
        stop_prev_low = close - input_exit_S1_factor * _lewis_ATR(input_exit_S1_ATR_len);
        if (close - stop_prev_low) / close > input_day_low_loss_percentage then
            stop_prev_low = close * (1 - input_exit_adj_stop_percent/100);
        
        input_exit_S1_factor = 3.4
        input_exit_S1_ATR_len = 22
        input_day_low_loss_percentage = 0.2
        input_exit_adj_stop_percent = 7.2
    
    Comparison with HK:
        HK: factor=3.7, adjusted=9.5%, has 30% threshold (14.25% stop)
        US: factor=3.4, adjusted=7.2%, NO 30% threshold
    """
    if not stock_prices or len(stock_prices) < atr_period + 1:
        return float('nan')

    highs = [bar.high for bar in stock_prices]
    lows = [bar.low for bar in stock_prices]
    closes = [bar.close for bar in stock_prices]

    close = entry_close if entry_close is not None else closes[-1]
    if close <= 0:
        return float('nan')

    # Calculate ATR using Wilder's method (same as HK)
    atr_series = wilder_atr(highs, lows, closes, atr_period)
    if not atr_series:
        return float('nan')
    current_atr = atr_series[-1]

    # Base stop: close - 3.4 * ATR(22)
    base_stop = close - factor * current_atr

    # Calculate risk percentage
    risk_fraction = (close - base_stop) / close  

    # If risk > 20%, use fixed 7.2% stop instead
    if risk_fraction > loss_threshold:
        return round(close * (1 - adjusted_stop_percent), 3)
    
    return round(base_stop, 3)


def run_all_buy_conditions_us(
    stock_prices: List[OHLCV], 
    spy_prices: List[OHLCV],
    targetDate: str
) -> Dict[str, Union[bool, float]]:
    """
    Run all US King buy signal checks and calculate stop loss.
    
    Executes all buy signal conditions for US King algorithm:
    - B1_US: Bollinger breakout with deviation check
    - B8_US: Higher low pattern (85D/150D)
    - B9_US: Weak price action filter
    - B10: 250D low timing (shared with HK)
    - B11_US: ATR volatility check
    - B12: SMA growth filter (shared with HK)
    - B13: SPY underperformance check (US params: 19/100)
    - B18_US: VCP pattern detection
    - B20_US: Volume analysis (up/down + highvol)
    - B21_US: Range expansion check
    - B22_US: Hard stop validation
    - stopLoss: S1 stop calculation (US King: factor=3.4, adjusted=7.2%)
    
    Args:
        stock_prices: Stock OHLCV data
        spy_prices: SPY OHLCV data for B13 comparison
        targetDate: Date string for logging
    
    Returns:
        Dictionary with boolean results for each signal and float for stopLoss
        Example: {'B1': True, 'B8': False, ..., 'stopLoss': 95.42}
    
    US King Buy Rule:
        Buy if {[B1 AND B8] OR [B18]} AND B9 AND B10 AND B11 AND B12 AND B13 AND B20 AND B21 AND B22
    """
    
    return {
        'B1':  check_b1_us(stock_prices),
        'B8':  check_b8_us(stock_prices),
        'B9':  check_b9_us(stock_prices),
        'B10': check_b10(stock_prices),  # Shared with HK
        'B11': check_b11_us(stock_prices),
        'B12': check_b12(stock_prices),  # Shared with HK
        'B13': check_b13(stock_prices, spy_prices, input_B13_XX=19, input_B13_YY=100),  # US params with 0.75% tolerance
        'B18': check_b18_us(stock_prices),
        'B20': check_b20_us(stock_prices),
        'B21': check_b21_us(stock_prices),
        'B22': check_b22_us(stock_prices),
        'stop_loss': calc_s1_stop_us(stock_prices)  # US King specific
    }


def is_buy_us(signals: Dict[str, Union[bool, float]]) -> bool:
    """
    Determine if US King buy signal is triggered based on all conditions.
    
    US King Buy Rule:
        Buy if {[B1 AND B8] OR [B18]} AND B9 AND B10 AND B11 AND B12 AND B13 AND B20 AND B21 AND B22
    
    Logic breakdown:
    - Core trigger: (B1 AND B8) OR B18
      * Traditional breakout: B1 (Bollinger) AND B8 (higher low)
      * OR VCP pattern: B18 (Volatility Contraction Pattern)
    
    - Required filters (all must be TRUE):
      * B9: Not weak price action
      * B10: 250D low not too recent
      * B11: ATR not too high (volatility check)
      * B12: SMA not overheated
      * B13: Not underperforming SPY
      * B20: Volume accumulation pattern
      * B21: Range expansion sufficient
      * B22: Valid hard stop can be set
    
    Args:
        signals: Dictionary from run_all_buy_conditions_us()
    
    Returns:
        True if buy signal triggered, False otherwise
    
    Comparison with HK Algo:
        HK:  (B1 AND B3 AND B8 AND B9 AND B10 AND B11 AND B12 AND B13) OR B18
        US:  ([B1 AND B8] OR B18) AND B9 AND B10 AND B11 AND B12 AND B13 AND B20 AND B21 AND B22
        
        Key differences:
        - US removed B3 (BBW slope check)
        - US added B20 (volume analysis)
        - US added B21 (range expansion)
        - US added B22 (hard stop validation)
        - US changed logic: B18 is alternative to [B1 AND B8], but still needs all filters
    """
    # Core trigger: Breakout OR VCP
    core_trigger = (signals['B1'] and signals['B8']) or signals['B18']
    
    # Required filters
    filters_ok = (
        signals['B9'] and 
        signals['B10'] and 
        signals['B11'] and 
        signals['B12'] and 
        signals['B13'] and 
        signals['B20'] and 
        signals['B21'] and 
        signals['B22']
    )
    
    return bool(core_trigger and filters_ok)