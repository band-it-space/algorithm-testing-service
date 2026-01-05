import numpy as np
from typing import List, Dict, Optional, Union
from dataclasses import dataclass
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

@dataclass
class OHLCV:
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float] = None

# Utility functions
def to_ts(date):
    if isinstance(date, datetime):
        return date.timestamp() * 1000
    if isinstance(date, (int, float)):
        return date
    try:
        if isinstance(date, str):
            dt = datetime.fromisoformat(date.replace("Z", "+00:00"))
        else:
            dt = datetime.fromisoformat(str(date))
        return dt.timestamp() * 1000
    except (ValueError, TypeError):
        raise ValueError(f"Invalid date: {date}")

def sma(values: List[float], period: int) -> List[float]:
    if len(values) < period:
        return []
    
    result = []
    for i in range(period - 1, len(values)):
        window = values[i - period + 1:i + 1]
        result.append(sum(window) / period)
    return result

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

    pastRange = lows[-270:-47]
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

    highIndex = highs.index(maxHigh)
    lowIndex = lows.index(minLow)

    mid = (maxHigh + minLow) / 2

    condCloseBelowMid = lastClose < mid
    condHighEarlierThanLow = highIndex < lowIndex
    
    return not (condCloseBelowMid and condHighEarlierThanLow)

#TODO B10 ++
def checkB10(ohlcv: List[OHLCV]) -> bool:
    if len(ohlcv) < 250:
        return False

    last250 = ohlcv[-250:]
    lows = [bar.low for bar in last250]

    minLow = min(lows)
    minIndex = lows.index(minLow)

    return minLow not in lows[-68:]


    # daysSinceLow = len(last250) - 1 - minIndex

    # return daysSinceLow > 68

#TODO B11 ++
def checkB11(ohlcv: List[OHLCV]) -> bool:
    if len(ohlcv) < 126 + 22:
        return False

    highs = [bar.high for bar in ohlcv]
    lows = [bar.low for bar in ohlcv]
    closes = [bar.close for bar in ohlcv]

    atr22 = atr(highs, lows, closes, 22)

    currentATR = atr22[-1]

    last126 = atr22[-127:-1]
    maxATR = max(last126)

    return not (currentATR > 0.87 * maxATR)

#TODO B12 ++
def checkB12(
    ohlcv: List["OHLCV"],
    input_B12_growth: float = 0.16,
    input_B12_days: int = 50,
    input_B12_deviation: float = 0.2
) -> bool:


    closes = [b.close for b in ohlcv]
    n = len(closes)
    if n < 150 + input_B12_days:
        return False

    sma150 = sma(closes, 150)
    warmup = 150 - 1
    if not sma150 or len(sma150) != n - warmup:
        return False



    sma_now = sma150[-1]
    sma_past = sma150[-51]
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
    if not ohlcvStock or not ohlcvIndex:
        return False
    
    stock = sorted(ohlcvStock, key=lambda x: to_ts(x.date))
    index = sorted(ohlcvIndex, key=lambda x: to_ts(x.date))

    max_period = max(input_B13_XX, input_B13_YY)

    if len(stock) <= max_period or len(index) <= max_period:
        return False

    s_today = stock[-1].close
    i_today = index[-1].close

    s_x_ago = stock[-input_B13_XX -1].close
    i_x_ago = index[-input_B13_XX -1].close

    s_y_ago = stock[-input_B13_YY -1].close
    i_y_ago = index[-input_B13_YY -1].close

    stock_ratio_x = s_today / s_x_ago
    index_ratio_x = i_today / i_x_ago

    stock_ratio_y = s_today / s_y_ago
    index_ratio_y = i_today / i_y_ago

    if (stock_ratio_x < index_ratio_x) and (stock_ratio_y < index_ratio_y):
        return False
    else: 
        return True

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


# 1,0,1,1,1,0,1,1,0,1,0,0,1,1,1,0,0,