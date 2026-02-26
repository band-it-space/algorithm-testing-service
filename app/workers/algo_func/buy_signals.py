import numpy as np
from typing import List, Dict, Optional, Union
import logging
from datetime import datetime

from app.workers.algo_func.types import OHLCV
from app.workers.algo_func.helpers import to_ts, sma, lewis_atr

logger = logging.getLogger(__name__)

# Bollinger Bands and utility functions
def bollinger_bands(values: List[float], period: int, std_dev: float) -> List[Dict[str, float]]:
    if len(values) < period:
        return []
    
    result = []
    for i in range(period - 1, len(values)):
        window = values[i - period + 1:i + 1]
        mean_val = sum(window) / period

        if period > 1:
            variance = sum((x - mean_val) ** 2 for x in window) / period
        else:
            variance = 0.0

        std = variance ** 0.5
        
        result.append({
            'upper': mean_val + std_dev * std,
            'middle': mean_val,
            'lower': mean_val - std_dev * std
        })
    return result

def condition8_b18(closes: list[float]) -> bool:

    input_BBW_len = 21  
    input_BBW_SD = 2.0  
    input_B18_Z = 21     
    input_B18_Y = 82     
    input_B18_X = 22.0   

    if len(closes) < input_BBW_len + input_B18_Z + input_B18_Y:
        return False

    bb = bollinger_bands(closes, input_BBW_len, input_BBW_SD)

    bbw = []
    for b in bb:
        mid = b['middle']
        if mid == 0 or mid is None:
            bbw.append(None)
            continue
        width_pct = (b['upper'] - b['lower']) / mid * 100
        bbw.append(width_pct)

    recent_bbw = [x for x in bbw if x is not None]
    if len(recent_bbw) < input_B18_Z + input_B18_Y:
        return False

    bbw_sma_now = mean(recent_bbw[-input_B18_Z:])

    try:
        bbw_y_ago = recent_bbw[-1 - input_B18_Y]
    except IndexError:
        return False

    if bbw_y_ago is None:
        return False

    cond_bbw = bbw_sma_now < bbw_y_ago * (input_B18_X / 100.0)

    bb_price = bollinger_bands(closes, input_B18_Z, 2.0)
    last_bb_price = bb_price[-1]
    last_close = closes[-1]
    cond_price = last_close > last_bb_price['upper']
    
    logger.info(f"Conditions 1 - {cond_bbw}, 2 - {cond_price}")

    return cond_bbw and cond_price

def atr(highs, lows, closes, period):
    if len(highs) < period + 1:
        return []

    trs = []
    for i in range(1, len(highs)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)

    atr_values = []
    first_atr = sum(trs[:period]) / period
    atr_values.append(first_atr)

    for i in range(period, len(trs)):
        atr = (atr_values[-1] * (period - 1) + trs[i]) / period
        atr_values.append(atr)

    return atr_values

def mean(arr: List[float]) -> float:
    return sum(arr) / len(arr) if arr else 0.0


#TODO B1 ++
def checkB1(ohlcv: List[OHLCV], targetDate) -> bool:
    if len(ohlcv) < 51:
        return False
    logger.info(f"Day - {targetDate}")
    closes = [bar.close for bar in ohlcv]
    highs = [bar.high for bar in ohlcv]
    last = ohlcv[-1]

    if len(ohlcv) < 21:
        return False
    prev20High = max(highs[-21:-1])
    condNew20DHigh = last.high > prev20High

    bb = bollinger_bands(closes, 51, 1.9)
    sma51 = sma(closes, 51)

    condBB = False
    if bb and sma51:
        lastBB = bb[-1]
        lastSMA51 = sma51[-1]
        logger.info(f"MA - {lastSMA51})")
        if lastBB and lastSMA51:
            deviation = (last.close - lastSMA51) / lastSMA51
            logger.info(f"clode: {last.close} lastSMA51: {lastSMA51}")
            condBB = last.close > lastBB['upper'] and deviation < 0.25

    condCloseInUpperRange = last.close > last.low + 0.65 * (last.high - last.low)
    
    logger.info(f"last.low: {last.low}, last_h: {last.high} last.close: {last.close}")


    logger.info(f"B1 Conditions - NewHigh: {condNew20DHigh}, last: {last.high} prev20High: {prev20High}  Bollinger: {condBB}, CloseInUpperRange: {condCloseInUpperRange}")

    return ((condNew20DHigh or condBB) and condCloseInUpperRange)

#TODO B3 ++
def linear_reg_value_mc(series: List[float], length: int, tgt_bar: int) -> float:
    if length <= 0 or len(series) < length:
        return 0.0
    window = series[-length:]
    ys = [window[-1 - j] for j in range(length)]
    xs = list(range(length))

    x_mean = sum(xs) / length
    y_mean = sum(ys) / length

    num = 0.0
    den = 0.0
    for x, y in zip(xs, ys):
        dx = x - x_mean
        dy = y - y_mean
        num += dx * dy
        den += dx * dx

    if den == 0:
        return ys[0]

    a = num / den
    b = y_mean - a * x_mean

    return a * tgt_bar + b

def slope_sma_bbw_mc(sma_bbw: List[float], length: int) -> float:
    if len(sma_bbw) < length:
        return 0.0

    var1 = linear_reg_value_mc(sma_bbw, length, 0)
    var2 = linear_reg_value_mc(sma_bbw, length, length - 1)
    slope1 = (var1 - var2) / length

    return slope1

def checkB3(ohlcv: List[OHLCV]) -> bool:
    SMA_BBW_LEN = 72
    LR_LEN = 58

    if not ohlcv: 
        return False

    closes = [bar.close for bar in ohlcv]

    bb = bollinger_bands(closes, 21, 2)

    if len(bb) < SMA_BBW_LEN + LR_LEN:
        return False

    bbw: List[float] = []
    for i, b in enumerate(bb):
        m = b["middle"]
        if m == 0:
            continue
        bbw_val = (b["upper"] - b["lower"]) / m * 100
        bbw.append(bbw_val)

    smaBBW = sma(bbw, SMA_BBW_LEN)
    if not smaBBW:
        return False

    if len(smaBBW) < LR_LEN:
        return False

    slope = slope_sma_bbw_mc(smaBBW, LR_LEN)

    return slope < 0

#TODO B8 ++
def checkB8(ohlcv: List[OHLCV]) -> bool:
    if len(ohlcv) < 270:
        return False

    lows = [bar.low for bar in ohlcv]

    recent46Low = min(lows[-46:])

    pastRange = lows[-270:-46]
    pastMinRange = min(pastRange)

    return recent46Low > pastMinRange

#TODO B9 ++
def checkB9(ohlcv: List[OHLCV]) -> bool:
    if len(ohlcv) < 50:
        return False

    last50 = ohlcv[-50:]
    closes = [bar.close for bar in last50]
    highs = [bar.high for bar in last50]
    lows = [bar.low for bar in last50]

    lastClose = closes[-1]

    maxHigh = max(highs)
    minLow = min(lows)

    # Get the last occurrence of max and min values
    highIndex = max(i for i, v in enumerate(highs) if v == maxHigh)
    lowIndex = max(i for i, v in enumerate(lows) if v == minLow)

    mid = (maxHigh + minLow) / 2

    condCloseBelowMid = lastClose < mid
    condHighEarlierThanLow = highIndex < lowIndex
    
    return not (condCloseBelowMid and condHighEarlierThanLow)

#TODO B10 ++
def checkB10(
    ohlcv: List[OHLCV],
    lookback_period: int = 250,
    recent_period: int = 68
) -> bool:
    """
    B10 - Cancel if recent 250D low happened too recently (within 68 days)
    
    IDENTICAL for both HK Algo and US King algorithms.
    
    Condition:
    - Find the lowest low in the last {lookback_period} days
    - If this low occurred within the last {recent_period} days → CANCEL buy
    - If this low occurred MORE than {recent_period} days ago → OK
    
    Rationale: If the stock just made a new low recently, it's too risky to buy.
    We want the low to be old enough (established base).
    
    Args:
        ohlcv: Price data
        lookback_period: Period to find the lowest low (default 250)
        recent_period: Days to check if low is too recent (default 68)
    
    Returns:
        True if buy signal is valid (low is old enough)
        False if buy signal should be cancelled (low too recent)
    
    Documentation: "if 250D low happens within {68} days before breakout, cancel buy"
    
    MC Code Reference:
    - if lowestbar(low, 250) < input_XXXD_low_day then cond15_XXXD_low = false
    - input_XXXD_low_day = 68 for both HK and US King
    - lowestbar returns index of lowest bar (0 = today, 1 = yesterday, etc.)
    - If index < 68, low is within last 68 days → cancel
    """
    if len(ohlcv) < lookback_period:
        return False

    last_period = ohlcv[-lookback_period:]
    lows = [bar.low for bar in last_period]

    min_low = min(lows)
    
    # Check if min_low is NOT in the last recent_period days
    # If it's not there, it's old enough → valid
    result = min_low not in lows[-recent_period:]
    
    if not result:
        # Find actual index for logging
        min_index = len(lows) - 1 - max(i for i in range(len(lows)) if lows[i] == min_low)
        # logger.info(
        #     f"B10 - CANCEL: 250D low ({min_low:.2f}) occurred {min_index} days ago "
        #     f"(within {recent_period} days)"
        # )
    
    return result
from typing import List


def checkB11(ohlcv: List["OHLCV"]) -> bool:
    ohlcv = sorted(ohlcv, key=lambda x: to_ts(x.date))
    n = len(ohlcv)

    if n < 148:
        return False

    highs = [b.high for b in ohlcv]
    lows  = [b.low for b in ohlcv]
    closes= [b.close for b in ohlcv]

    atr = lewis_atr(highs, lows, closes, 22)

    current = atr[-1]
    if current is None:
        return False
    
    prev_window = atr[-127:-1]  # aligned to bars now
    prev_window = [x for x in prev_window if x is not None]
    if len(prev_window) < 126:
        return False

    max_prev = max(prev_window)

    # MC logic: if current > max_prev*0.87 => cancel => return False
    return not (current > 0.87 * max_prev)

#TODO B12 ++
def checkB12(
    ohlcv: List["OHLCV"],
    input_B12_growth: float = 0.16,
    input_B12_days: int = 50,
    input_B12_deviation: float = 0.2,
    input_B12_sma_period: int = 150
) -> bool:
    """
    B12 - Cancel buy if SMA grew too fast AND price deviated too much
    
    SIMILAR logic for both HK Algo and US King, but with different parameters.
    
    Two conditions (BOTH must be TRUE to CANCEL buy):
    1. SMA({sma_period}) grew more than {growth}% in last {days} days
    2. Today's HIGH is more than {deviation}% above SMA({sma_period})
    
    Logic: Avoid buying overheated stocks with rapid MA growth + excessive price extension
    
    Args:
        ohlcv: Price data
        input_B12_growth: MA growth threshold as decimal (default 0.16 = 16%)
        input_B12_days: Days to check MA growth (default 50)
        input_B12_deviation: High deviation threshold as decimal (default 0.2 = 20%)
        input_B12_sma_period: SMA period for both calculations (default 150)
    
    Returns:
        True if buy signal is valid (NOT overheated)
        False if buy should be cancelled (overheated)
    
    HK Algo Parameters:
        - growth: 16%, days: 50, deviation: 20%, sma_period: 150
    
    US King Parameters:
        - growth: 16%, days: 50, deviation: 20%, sma_period: 150
        (Note: SAME default values for both algorithms)
    
    MC Code Reference (US King):
        if average(close,150)/average(close,150)[50]-1 > 16/100 
           and high/average(close, 150)-1 > 20/100 then
            cond18_B12 = false
    
    Example:
        - 150MA today = $100, 150MA 50 days ago = $85
        - MA Growth: 100/85-1 = 17.6% > 16% ✓
        - Today's HIGH = $125
        - Deviation: 125/100-1 = 25% > 20% ✓
        - Result: CANCEL buy (too overheated)
    """
    closes = [b.close for b in ohlcv]
    n = len(closes)
    if n < input_B12_sma_period + input_B12_days:
        return False

    sma_series = sma(closes, input_B12_sma_period)
    warmup = input_B12_sma_period - 1
    if not sma_series or len(sma_series) != n - warmup:
        return False

    sma_now = sma_series[-1]
    sma_past = sma_series[-(input_B12_days + 1)]
    if sma_now in (None, 0) or sma_past in (None, 0):
        return False

    sma_growth = (sma_now / sma_past) - 1.0
    deviation = (ohlcv[-1].high / sma_now) - 1.0

    return not ((sma_growth > input_B12_growth) and (deviation > input_B12_deviation))

#TODO B13 ++
def checkB13(
    ohlcvStock: List[OHLCV],
    ohlcvIndex: List[OHLCV],
    input_B13_XX: int = 19,
    input_B13_YY: int = 60
) -> bool:
    """
    B13 - Cancel buy if stock underperforms market index
    
    IDENTICAL logic for both HK Algo and US King, but with DIFFERENT parameters.
    
    Condition:
    - Compare stock performance vs index over TWO periods
    - CANCEL buy if stock underperforms index in BOTH periods
    
    Logic:
    - Stock XX-day return = close[0] / close[XX]
    - Index XX-day return = close[0] / close[XX]
    - If stock_return_XX < index_return_XX AND stock_return_YY < index_return_YY → CANCEL
    
    Args:
        ohlcvStock: Stock price data
        ohlcvIndex: Index price data (HSI for HK, SPY for US)
        input_B13_XX: Short period lookback (default 19)
        input_B13_YY: Long period lookback (default 60 for HK)
    
    Returns:
        True if buy signal is valid (stock performing OK vs index)
        False if buy should be cancelled (underperforming in both periods)
    
    HK Algo Parameters:
        - input_B13_XX = 19 days
        - input_B13_YY = 60 days
        - Index = HSI (data(2) in MC code)
    
    US King Parameters:
        - input_B13_XX = 19 days
        - input_B13_YY = 100 days (NOT 60!)
        - Index = SPY (data(2) in MC code)
    
    HK Documentation: "CANCEL Buy if the stock is underperforming 2800 for {19}-Day AND {60}-Day"
    US Documentation: "CANCEL buy if the stock is underperforming SPY for {19}-Day AND {100}-Day"
    
    MC Code Reference (same logic for both):
        if close/close[input_B13_XX] < close data(2)/close[input_B13_XX] data(2) and
           close/close[input_B13_YY] < close data(2)/close[input_B13_YY] data(2) then
            cond19_B13 = false
    
    Usage:
        # For HK Algo (default):
        checkB13(stock_data, hsi_data)  # Uses 19 and 60
        
        # For US King:
        checkB13(stock_data, spy_data, input_B13_XX=19, input_B13_YY=100)
    """
    if not ohlcvStock or not ohlcvIndex:
        return False
    
    stock = sorted(ohlcvStock, key=lambda x: to_ts(x.date))
    index = sorted(ohlcvIndex, key=lambda x: to_ts(x.date))

    # Need current bar + lookback period
    max_period = max(input_B13_XX, input_B13_YY) + 1  # +1 for lookback offset

    if len(stock) <= max_period or len(index) <= max_period:
        return False

    # MultiCharts indexing: close[0] = current bar, close[N] = N bars back
    # Python: stock[-1] = current bar (today)
    s_today = stock[-1].close
    i_today = index[-1].close

    # close[19] in MC = 19 bars back = stock[-(19+1)] = stock[-20]
    s_x_ago = stock[-(input_B13_XX + 1)].close
    i_x_ago = index[-(input_B13_XX + 1)].close

    # close[100] in MC = 100 bars back = stock[-(100+1)] = stock[-101]
    s_y_ago = stock[-(input_B13_YY + 1)].close
    i_y_ago = index[-(input_B13_YY + 1)].close

    stock_ratio_x = s_today / s_x_ago
    index_ratio_x = i_today / i_x_ago

    stock_ratio_y = s_today / s_y_ago
    index_ratio_y = i_today / i_y_ago
    
    # Check if stock underperforms index in BOTH periods
    underperforms_x = stock_ratio_x < index_ratio_x
    underperforms_y = stock_ratio_y < index_ratio_y
    underperforms_both = underperforms_x and underperforms_y
    
    # Debug logging
    # logger.info(f"B13 DEBUG - Data length: Stock={len(stock)}, Index={len(index)}")
    # logger.info(f"B13 DEBUG - Stock dates: today={stock[-1].date}, {input_B13_XX}d_ago={stock[-(input_B13_XX+1)].date}, {input_B13_YY}d_ago={stock[-(input_B13_YY+1)].date}")
    # logger.info(f"B13 DEBUG - Index dates: today={index[-1].date}, {input_B13_XX}d_ago={index[-(input_B13_XX+1)].date}, {input_B13_YY}d_ago={index[-(input_B13_YY+1)].date}")
    # logger.info(f"B13 DEBUG - Stock prices: today={s_today:.2f}, {input_B13_XX}d_ago={s_x_ago:.2f}, {input_B13_YY}d_ago={s_y_ago:.2f}")
    # logger.info(f"B13 DEBUG - Index prices: today={i_today:.2f}, {input_B13_XX}d_ago={i_x_ago:.2f}, {input_B13_YY}d_ago={i_y_ago:.2f}")
    
    # logger.info(f"B13 - Stock {input_B13_XX}-day: {stock_ratio_x} {'<' if underperforms_x else '>='} Index: {index_ratio_x} {'(underperforms)' if underperforms_x else '(OK)'}")
    # logger.info(f"B13 - Stock {input_B13_YY}-day: {stock_ratio_y} {'<' if underperforms_y else '>='} Index: {index_ratio_y:} {'(underperforms)' if underperforms_y else '(OK)'}")
    # logger.info(f"B13 - Final result: {'FALSE - Cancel buy (underperforms both periods)' if underperforms_both else 'TRUE - Allow buy (performing OK)'}")

    if underperforms_both:
        return False  # Cancel buy - stock underperforming
    else: 
        return True  # Allow buy - stock performing OK

#TODO B18
def checkB18(ohlcv: List[OHLCV], targetDate: str) -> bool:
    if not ohlcv or len(ohlcv) < 250:
        logger.info(f"Insufficient data for {targetDate}. Length of ohlcv: {len(ohlcv)}")
        return False
    
    

    closes = [bar.close for bar in ohlcv]
    highs = [bar.high for bar in ohlcv]
    lows = [bar.low for bar in ohlcv]

    last = ohlcv[-1]
    lastClose = last.close

    sma50 = sma(closes, 50)
    sma150 = sma(closes, 150)
    sma200 = sma(closes, 200)

    # Check if the SMAs were calculated properly
    if not sma50 or not sma150 or not sma200:
        logger.info(f"Failed to calculate required SMAs on {targetDate}")
        return False

    lastSMA50 = sma50[-1]
    lastSMA150 = sma150[-1]
    lastSMA200 = sma200[-1]

    # Condition 1: Check if last close is above both SMA150 and SMA200
    cond1 = lastClose > lastSMA150 and lastClose > lastSMA200

    # Condition 2: Check if SMA150 > SMA200
    cond2 = lastSMA150 > lastSMA200

    # Ensure we have enough data for the 200-period SMA
    if len(sma200) < 22:
        logger.info(f"Not enough data for SMA200 on {targetDate}")
        return False

    sma200_21d_ago = sma200[-21]
    # Condition 3: Check if last SMA200 is greater than SMA200 21 days ago
    cond3 = lastSMA200 > sma200_21d_ago

    # Condition 4: Check if last SMA50 > both SMA150 and SMA200
    cond4 = lastSMA50 > lastSMA150 and lastSMA50 > lastSMA200

    # Condition 5: Check if last close is above SMA50
    cond5 = lastClose > lastSMA50

    # Condition 6: Check if last close is greater than 30% above the 250-day low
    last250Low = min(lows[-250:])
    cond6 = lastClose > last250Low * 1.30


    # Condition 7: Check if last close is greater than 75% of the 250-day high
    last250High = max(highs[-250:])
    cond7 = lastClose > last250High * 0.75

    # Calculate Bollinger Bands for the last 21 and 82 days
    


    cond8 = condition8_b18(closes)

    # logger.info(f"Final B18 Conditions for {targetDate}: "
    #     f"cond1: {cond1}, cond2: {cond2}, cond3: {cond3}, cond4: {cond4}, "
    #     f"cond5: {cond5}, cond6: {cond6}, cond7: {cond7}, cond8: {cond8}")

    # Return the final result based on all conditions
    return cond1 and cond2 and cond3 and cond4 and cond5 and cond6 and cond7 and cond8

#TODO Stop Loss
def wilder_atr(highs: List[float], lows: List[float], closes: List[float], period: int) -> List[float]:
    if len(highs) < period + 1:
        return []

    true_ranges = []
    for i in range(1, len(highs)):
        tr1 = highs[i] - lows[i]
        tr2 = abs(highs[i] - closes[i - 1])
        tr3 = abs(lows[i] - closes[i - 1])
        true_ranges.append(max(tr1, tr2, tr3))

    atr_values = []

    first_atr = sum(true_ranges[:period]) / period
    atr_values.append(first_atr)

    for i in range(period, len(true_ranges)):
        prev_atr = atr_values[-1]
        current_atr = ((prev_atr * (period - 1)) + true_ranges[i]) / period
        atr_values.append(current_atr)

    return atr_values

def calcS1Stop(ohlcv: List[OHLCV], factor: float = 3.7, atrPeriod: int = 22, 
               entryClose: Optional[float] = None) -> float:
    if not ohlcv or len(ohlcv) < atrPeriod + 1:
        return float('nan')

    highs = [bar.high for bar in ohlcv]
    lows = [bar.low for bar in ohlcv]
    closes = [bar.close for bar in ohlcv]

    close = entryClose if entryClose is not None else closes[-1]
    if close <= 0:
        return float('nan')

    atrSeries = wilder_atr(highs, lows, closes, atrPeriod)
    if not atrSeries:
        return float('nan')
    currentATR = atrSeries[-1]

    baseStop = close - factor * currentATR

    riskFrac = (close - baseStop) / close  

    if riskFrac > 0.30:
        return round(close * (1 - 0.1425), 4)  
    if riskFrac > 0.20:
        return round(close * (1 - 0.095), 4)   
    return round(baseStop, 4)

def runAllBuyConditions(ohlcv: List[OHLCV], targetDate: str, spyData: List[OHLCV]) -> Dict[str, Union[bool, float]]:
    return {
        'B1':  checkB1(ohlcv, targetDate),
        'B3':  checkB3(ohlcv),
        'B8':  checkB8(ohlcv),
        'B9':  checkB9(ohlcv),
        'B10': checkB10(ohlcv),
        'B11': checkB11(ohlcv),
        'B12': checkB12(ohlcv),
        'B13': checkB13(ohlcv, spyData),
        'B18': checkB18(ohlcv, targetDate),
        'stopLoss': calcS1Stop(ohlcv)
    }

def isBuy(signals: Dict[str, Union[bool, float]]) -> bool:
    return bool((signals['B1'] and signals['B3'] and signals['B8'] and 
            signals['B9'] and signals['B10'] and signals['B11'] and 
            signals['B12'] and signals['B13']) or signals['B18'])
