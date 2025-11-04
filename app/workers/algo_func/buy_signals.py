import numpy as np
from typing import List, Dict, Optional, Union
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class OHLCV:
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float] = None

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
        variance = sum((x - mean_val) ** 2 for x in window) / period
        std = variance ** 0.5
        
        result.append({
            'upper': mean_val + std_dev * std,
            'middle': mean_val,
            'lower': mean_val - std_dev * std
        })
    return result

# def atr(highs: List[float], lows: List[float], closes: List[float], period: int) -> List[float]:
#     if len(highs) < period + 1:
#         return []
    
#     true_ranges = []
#     for i in range(1, len(highs)):
#         tr1 = highs[i] - lows[i]
#         tr2 = abs(highs[i] - closes[i-1])
#         tr3 = abs(lows[i] - closes[i-1])
#         true_ranges.append(max(tr1, tr2, tr3))
    
#     result = []
#     for i in range(period - 1, len(true_ranges)):
#         window = true_ranges[i - period + 1:i + 1]
#         result.append(sum(window) / period)
#     return result

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

def linear_regression_slope(values: List[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    
    x_mean = (n - 1) / 2
    y_mean = sum(values) / n
    
    numerator = 0
    denominator = 0
    
    for i in range(n):
        dx = i - x_mean
        dy = values[i] - y_mean
        numerator += dx * dy
        denominator += dx * dx
    
    return numerator / denominator if denominator != 0 else 0.0

def checkB1(ohlcv: List[OHLCV]) -> bool:
    if len(ohlcv) < 51:
        return False

    closes = [bar.close for bar in ohlcv]
    highs = [bar.high for bar in ohlcv]
    last = ohlcv[-1]

    if len(ohlcv) < 21:
        return False
    prev20High = max(highs[-21:-1])
    condNewHigh = last.high > prev20High

    bb = bollinger_bands(closes, 51, 1.9)
    sma51 = sma(closes, 51)

    condBoll = False
    if bb and sma51:
        lastBB = bb[-1]
        lastSMA51 = sma51[-1]
        if lastBB and lastSMA51:
            deviation = (last.close - lastSMA51) / lastSMA51
            condBoll = last.close > lastBB['upper'] and deviation < 0.25

    condCloseInUpperRange = last.close > last.low + 0.65 * (last.high - last.low)

    # print(last.close)
    # print(last.low)
    # print(last.high)
    # print(condCloseInUpperRange)

    return (condNewHigh or condBoll) and condCloseInUpperRange

def checkB3(ohlcv: List[OHLCV]) -> bool:
    if not ohlcv: 
        return False

    closes = [bar.close for bar in ohlcv]

    bb = bollinger_bands(closes, 21, 2)
    if len(bb) < 72 + 58:
        return False

    bbw = [(x['upper'] - x['lower']) / x['middle'] * 100  for x in bb]

    smaBBW = sma(bbw, 72)
    if len(smaBBW) < 58:
        return False

    win = smaBBW[-58:]
    slope = linear_regression_slope(win)

    return slope < 0

def checkB8(ohlcv: List[OHLCV]) -> bool:
    if len(ohlcv) < 270:
        return False

    lows = [bar.low for bar in ohlcv]

    recent46Low = min(lows[-46:])

    pastRange = lows[-270:-46]
    pastMin = min(pastRange)

    return recent46Low > pastMin


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

    # print(maxHigh)
    # print(minLow)
    # print(condCloseBelowMid)
    # print(condHighEarlierThanLow)
    # print(mid)

    return not (condCloseBelowMid and condHighEarlierThanLow)

def checkB10(ohlcv: List[OHLCV]) -> bool:
    if len(ohlcv) < 250:
        return False

    last250 = ohlcv[-250:]
    lows = [bar.low for bar in last250]

    minLow = min(lows)
    minIndex = lows.index(minLow)

    daysSinceLow = len(last250) - 1 - minIndex

    return daysSinceLow >= 68

def checkB11(ohlcv: List[OHLCV]) -> bool:
    if len(ohlcv) < 126 + 22:
        return False

    highs = [bar.high for bar in ohlcv]
    lows = [bar.low for bar in ohlcv]
    closes = [bar.close for bar in ohlcv]

    atr22 = atr(highs, lows, closes, 22)
    if len(atr22) < 126:
        return False

    currentATR = atr22[-1]

    last126 = atr22[-126:]
    maxATR = max(last126)

    return not (currentATR > 0.87 * maxATR)

def checkB12(ohlcv: List[OHLCV], targetDate: str, input_B12_growth: float = 0.16, 
             input_B12_days: int = 50, input_B12_deviation: float = 0.2) -> bool:
    targetIndex = next((i for i, bar in enumerate(ohlcv) if bar.date == targetDate), -1)
    if targetIndex == -1:
        raise ValueError(f"Дата {targetDate} не знайдена")

    if targetIndex < 150 + input_B12_days:
        return False

    smaNow = average([bar.close for bar in ohlcv[targetIndex - 150:targetIndex]])

    smaPast = average([bar.close for bar in ohlcv[targetIndex - input_B12_days - 150:targetIndex - input_B12_days]])

    smaGrowth = (smaNow - smaPast) / smaPast

    todayHigh = ohlcv[targetIndex].high

    deviation = (todayHigh - smaNow) / smaNow

    cancel = smaGrowth >= input_B12_growth and deviation >= input_B12_deviation
    return not cancel

def average(arr: List[float]) -> float:
    return sum(arr) / len(arr) if arr else 0.0

def checkB13(ohlcvStock: List[OHLCV], ohlcvIndex: List[OHLCV], periods: List[int] = [19, 60]) -> bool:

    if not ohlcvStock or not ohlcvIndex:
        return False

    idxCloseByDate = {bar.date: bar.close for bar in ohlcvIndex}
    aligned = [{'s': bar.close, 'i': idxCloseByDate[bar.date]} 
               for bar in ohlcvStock if bar.date in idxCloseByDate]

    if not aligned:
        return False

    maxPeriod = max(periods)
    if len(aligned) < maxPeriod + 1:
        return False

    underperformAll = True
    for period in periods:
        if len(aligned) < period + 1:
            return False

        sStart = aligned[len(aligned) - period - 1]['s']
        sEnd = aligned[len(aligned) - 1]['s']
        iStart = aligned[len(aligned) - period - 1]['i']
        iEnd = aligned[len(aligned) - 1]['i']

        sRet = (sEnd - sStart) / sStart
        iRet = (iEnd - iStart) / iStart

        if not (sRet < iRet):
            underperformAll = False
            break

    return not underperformAll

def checkB18(ohlcv: List[OHLCV]) -> bool:
    if not ohlcv or len(ohlcv) < 250:
        return False

    closes = [bar.close for bar in ohlcv]
    highs = [bar.high for bar in ohlcv]
    lows = [bar.low for bar in ohlcv]

    last = ohlcv[-1]
    lastClose = last.close

    sma50 = sma(closes, 50)
    sma150 = sma(closes, 150)
    sma200 = sma(closes, 200)

    if not sma50 or not sma150 or not sma200:
        return False

    lastSMA50 = sma50[-1]
    lastSMA150 = sma150[-1]
    lastSMA200 = sma200[-1]

    cond1 = lastClose > lastSMA150 and lastClose > lastSMA200
    cond2 = lastSMA150 > lastSMA200
    if len(sma200) < 22:
        return False
    sma200_21d_ago = sma200[-1 - 20]
    cond3 = lastSMA200 > sma200_21d_ago
    cond4 = lastSMA50 > lastSMA150 and lastSMA50 > lastSMA200
    cond5 = lastClose > lastSMA50

    last250High = max(highs[-250:])
    last250Low = min(lows[-250:])
    cond6 = lastClose >= last250Low * 1.30
    cond7 = lastClose >= last250High * 0.75

    bb21 = bollinger_bands(closes, 21, 2)

    if len(bb21) < 82:
        return False

    
    bbw = [(b['upper'] - b['lower']) / b['middle'] * 100 for b in bb21]

    avgBBW21 = mean(bbw[-21:])
    avgBBW82 = mean(bbw[-82:])
    lastBB21 = bb21[-1]
    cond8 = (avgBBW21 < 0.22 * avgBBW82) and (lastClose > lastBB21['upper'])
    
    logger.info(f'B18 Conditions: {cond1}, {cond2}, {cond3}, {cond4}, {cond5}, {cond6}, {cond7}, {cond8}')
    return cond1 and cond2 and cond3 and cond4 and cond5 and cond6 and cond7 and cond8

def mean(arr: List[float]) -> float:
    return sum(arr) / len(arr) if arr else 0.0


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

    # Перше значення ATR = SMA TR за period
    first_atr = sum(true_ranges[:period]) / period
    atr_values.append(first_atr)

    # Далі використовуємо формулу Вайлдера
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
        'B1': checkB1(ohlcv),
        'B3': checkB3(ohlcv),
        'B8': checkB8(ohlcv),
        'B9': checkB9(ohlcv),
        'B10': checkB10(ohlcv),
        'B11': checkB11(ohlcv),
        'B12': checkB12(ohlcv, targetDate),
        'B13': checkB13(ohlcv, spyData),
        'B18': checkB18(ohlcv),
        'stopLoss': calcS1Stop(ohlcv)
    }

def isBuy(signals: Dict[str, Union[bool, float]]) -> bool:
    return ((signals['B1'] and signals['B3'] and signals['B8'] and 
             signals['B9'] and signals['B10'] and signals['B11'] and 
             signals['B12'] and signals['B13']) or signals['B18'])
