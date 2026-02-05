import numpy as np
from typing import List, Dict, Optional, Union
from dataclasses import dataclass
import logging
from datetime import datetime

from app.models.algorithm_models import AlgorithmParameters

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

def mean(arr: List[float]) -> float:
    return sum(arr) / len(arr) if arr else 0.0

def condition8_b18(closes: list[float], params: AlgorithmParameters = None) -> bool:
    if params is None:
        params = AlgorithmParameters()

    input_BBW_len = params.input_B18_bbw_len  # was 21
    input_BBW_SD = 2.0  
    input_B18_Z = params.input_B18_Z  # was 21
    input_B18_Y = params.input_B18_history  # was 82
    input_B18_X = params.input_B18_bbw_ratio * 100  # was 15.0

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


def checkB1(ohlcv: List[OHLCV], targetDate, params: AlgorithmParameters = None) -> bool:
    if params is None:
        params = AlgorithmParameters()
    
    lookback = params.input_B1_lookback  # was 20
    bb_len = params.input_B1_bb_len  # was 51
    bb_std = params.input_B1_bb_std  # was 1.9
    ma_dev = params.input_B1_ma_dev  # was 0.25
    upper_range = params.input_B1_upper_range  # was 0.75
    
    if len(ohlcv) < bb_len:
        return False
    logger.info(f"Day - {targetDate}")
    closes = [bar.close for bar in ohlcv]
    highs = [bar.high for bar in ohlcv]
    last = ohlcv[-1]

    if len(ohlcv) < lookback + 1:
        return False
    prev_high = max(highs[-(lookback + 1):-1])
    condNew20DHigh = last.high > prev_high

    bb = bollinger_bands(closes, bb_len, bb_std)
    sma_vals = sma(closes, bb_len)

    condBB = False
    if bb and sma_vals:
        lastBB = bb[-1]
        lastSMA = sma_vals[-1]
        logger.info(f"MA - {lastSMA})")
        if lastBB and lastSMA:
            deviation = (last.close - lastSMA) / lastSMA
            logger.info(f"clode: {last.close} lastSMA51: {lastSMA}")
            condBB = last.close > lastBB['upper'] and deviation < ma_dev

    condCloseInUpperRange = last.close > last.low + upper_range * (last.high - last.low)
    
    logger.info(f"last.low: {last.low}, last_h: {last.high} last.close: {last.close}")

    logger.info(f"B1 Conditions - NewHigh: {condNew20DHigh}, last: {last.high} prev20High: {prev_high}  Bollinger: {condBB}, CloseInUpperRange: {condCloseInUpperRange}")

    return ((condNew20DHigh or condBB) and condCloseInUpperRange)


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

def checkB3(ohlcv: List[OHLCV], params: AlgorithmParameters = None) -> bool:
    if params is None:
        params = AlgorithmParameters()
    
    SMA_BBW_LEN = params.input_B3_sma_bbw  # was 72
    LR_LEN = params.input_B3_LR_lookback  # was 40
    BBW_LEN = params.input_B3_bbw_len  # was 21

    if not ohlcv: 
        return False

    closes = [bar.close for bar in ohlcv]

    bb = bollinger_bands(closes, BBW_LEN, 2)

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


def checkB8(ohlcv: List[OHLCV], params: AlgorithmParameters = None) -> bool:
    if params is None:
        params = AlgorithmParameters()
    
    recent_low_period = params.input_B8_recent_low  # was 46
    past_low_period = params.input_B8_past_low  # was 270
    
    if len(ohlcv) < past_low_period:
        return False

    lows = [bar.low for bar in ohlcv]

    recent_low = min(lows[-recent_low_period:])
    
    past_end = -recent_low_period - 1
    past_start = -past_low_period
    pastRange = lows[past_start:past_end]
    pastMinRange = min(pastRange) if pastRange else float('inf')

    return recent_low > pastMinRange


def checkB9(ohlcv: List[OHLCV], params: AlgorithmParameters = None) -> bool:
    if params is None:
        params = AlgorithmParameters()
    
    ma_len = params.input_B9_ma_len  # was 50
    
    if len(ohlcv) < ma_len:
        return False

    last_n = ohlcv[-ma_len:]
    closes = [bar.close for bar in last_n]
    highs = [bar.high for bar in last_n]
    lows = [bar.low for bar in last_n]

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


def checkB10(ohlcv: List[OHLCV], params: AlgorithmParameters = None) -> bool:
    if params is None:
        params = AlgorithmParameters()
    
    low_window = params.input_B10_low_window  # was 250
    prox_days = params.input_B10_prox_days  # was 68
    
    if len(ohlcv) < low_window:
        return False

    last_n = ohlcv[-low_window:]
    lows = [bar.low for bar in last_n]

    minLow = min(lows)

    return minLow not in lows[-prox_days:]


def lewis_atr(highs: List[float], lows: List[float], closes: List[float], period: int) -> List[Optional[float]]:
    n = len(highs)
    if n < 2:
        return [None] * n
    atr_values: List[Optional[float]] = [None] * n
    
    prev_atr = 0.0
    
    for i in range(1, n):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        
        current_atr = (prev_atr * (period - 1) + tr) / period
        
        atr_values[i] = current_atr
        prev_atr = current_atr

    return atr_values

def checkB11(ohlcv: List["OHLCV"], params: AlgorithmParameters = None) -> bool:
    if params is None:
        params = AlgorithmParameters()
    
    atr_len = params.input_B11_atr_len  # was 22
    history = params.input_B11_history  # was 126
    atr_threshold = params.input_B11_atr_threshold  # was 0.87 (now 0.8 in original)
    
    ohlcv = sorted(ohlcv, key=lambda x: to_ts(x.date))
    n = len(ohlcv)

    min_required = history + atr_len + 1
    if n < min_required:
        return False

    highs = [b.high for b in ohlcv]
    lows  = [b.low for b in ohlcv]
    closes= [b.close for b in ohlcv]

    atr_vals = lewis_atr(highs, lows, closes, atr_len)

    current = atr_vals[-1]
    if current is None:
        return False
    
    prev_window = atr_vals[-(history + 1):-1]
    prev_window = [x for x in prev_window if x is not None]
    if len(prev_window) < history:
        return False

    max_prev = max(prev_window)

    # MC logic: if current > max_prev * threshold => cancel => return False
    return not (current > atr_threshold * max_prev)


def checkB12(
    ohlcv: List["OHLCV"],
    params: AlgorithmParameters = None
) -> bool:
    if params is None:
        params = AlgorithmParameters()
    
    long_ma = params.input_B12_long_ma  # was 150
    growth = params.input_B12_rise_pct  # was 0.16
    deviation = params.input_B12_deviation  # was 0.2
    days = 50  # lookback for SMA comparison

    closes = [b.close for b in ohlcv]
    n = len(closes)
    if n < long_ma + days:
        return False

    sma_vals = sma(closes, long_ma)
    warmup = long_ma - 1
    if not sma_vals or len(sma_vals) != n - warmup:
        return False

    sma_now = sma_vals[-1]
    sma_past = sma_vals[-days - 1]
    if sma_now in (None, 0) or sma_past in (None, 0):
        return False

    sma_growth = (sma_now / sma_past) - 1.0
    dev = (ohlcv[-1].high / sma_now) - 1.0

    return not ((sma_growth > growth) and (dev > deviation))


def checkB13(
    ohlcvStock: List[OHLCV],
    ohlcvIndex: List[OHLCV],
    params: AlgorithmParameters = None
) -> bool:
    if params is None:
        params = AlgorithmParameters()
    
    input_B13_XX = params.input_B13_XX  # was 19
    input_B13_YY = params.input_B13_YY  # was 60
    
    if not ohlcvStock or not ohlcvIndex:
        return False
    
    stock = sorted(ohlcvStock, key=lambda x: to_ts(x.date))
    index = sorted(ohlcvIndex, key=lambda x: to_ts(x.date))

    max_period = max(input_B13_XX, input_B13_YY)

    if len(stock) <= max_period or len(index) <= max_period:
        return False

    s_today = stock[-1].close
    i_today = index[-1].close

    s_x_ago = stock[-input_B13_XX - 1].close
    i_x_ago = index[-input_B13_XX - 1].close

    s_y_ago = stock[-input_B13_YY - 1].close
    i_y_ago = index[-input_B13_YY - 1].close

    stock_ratio_x = s_today / s_x_ago
    index_ratio_x = i_today / i_x_ago

    stock_ratio_y = s_today / s_y_ago
    index_ratio_y = i_today / i_y_ago

    if (stock_ratio_x < index_ratio_x) and (stock_ratio_y < index_ratio_y):
        return False
    else: 
        return True


def checkB18(ohlcv: List[OHLCV], targetDate: str, params: AlgorithmParameters = None) -> bool:
    if params is None:
        params = AlgorithmParameters()
    
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

    if not sma50 or not sma150 or not sma200:
        logger.info(f"Failed to calculate required SMAs on {targetDate}")
        return False

    lastSMA50 = sma50[-1]
    lastSMA150 = sma150[-1]
    lastSMA200 = sma200[-1]

    cond1 = lastClose > lastSMA150 and lastClose > lastSMA200
    cond2 = lastSMA150 > lastSMA200

    if len(sma200) < 22:
        logger.info(f"Not enough data for SMA200 on {targetDate}")
        return False

    sma200_21d_ago = sma200[-21]
    cond3 = lastSMA200 > sma200_21d_ago
    cond4 = lastSMA50 > lastSMA150 and lastSMA50 > lastSMA200
    cond5 = lastClose > lastSMA50

    last250Low = min(lows[-250:])
    cond6 = lastClose > last250Low * 1.30

    last250High = max(highs[-250:])
    cond7 = lastClose > last250High * 0.75

    cond8 = condition8_b18(closes, params)

    return cond1 and cond2 and cond3 and cond4 and cond5 and cond6 and cond7 and cond8


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

def calcS1Stop(ohlcv: List[OHLCV], params: AlgorithmParameters = None,
               entryClose: Optional[float] = None) -> float:
    if params is None:
        params = AlgorithmParameters()
    
    factor = params.input_S1_atr_mult  # was 3.7
    atrPeriod = params.input_S1_atr_period  # was 22
    hard_stop = params.input_S1_hard_stop  # was 0.30
    medium_risk = params.input_S1_medium_risk  # was 0.20
    medium_stop = params.input_S1_medium_stop  # was 0.095
    high_stop = params.input_S1_high_stop  # was 0.1425
    
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

    if riskFrac > hard_stop:
        return round(close * (1 - high_stop), 4)  
    if riskFrac > medium_risk:
        return round(close * (1 - medium_stop), 4)   
    return round(baseStop, 4)

def runAllBuyConditions(ohlcv: List[OHLCV], targetDate: str, spyData: List[OHLCV], 
                        params: AlgorithmParameters = None) -> Dict[str, Union[bool, float]]:
    if params is None:
        params = AlgorithmParameters()
    
    return {
        'B1':  checkB1(ohlcv, targetDate, params),
        'B3':  checkB3(ohlcv, params),
        'B8':  checkB8(ohlcv, params),
        'B9':  checkB9(ohlcv, params),
        'B10': checkB10(ohlcv, params),
        'B11': checkB11(ohlcv, params),
        'B12': checkB12(ohlcv, params),
        'B13': checkB13(ohlcv, spyData, params),
        'B18': checkB18(ohlcv, targetDate, params),
        'stopLoss': calcS1Stop(ohlcv, params)
    }

def isBuy(signals: Dict[str, Union[bool, float]]) -> bool:
    return bool((signals['B1'] and signals['B3'] and signals['B8'] and 
            signals['B9'] and signals['B10'] and signals['B11'] and 
            signals['B12'] and signals['B13']) or signals['B18'])
