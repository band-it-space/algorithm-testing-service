from datetime import datetime
from typing import List, Optional
from app.workers.algo_func.types import OHLCV

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

def atr(ohlcv: List[OHLCV], period: int):
    if len(ohlcv) < period + 1:
        return []  
    trs = []
    
    for i in range(1, len(ohlcv)):
        high = ohlcv[i].high
        low = ohlcv[i].low
        prev_close = ohlcv[i - 1].close
        
        if i == 0:
            tr = high - low
        else:
            prev_close = ohlcv[i - 1].close
            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close),
            )
        trs.append(tr)

    atr_values = []

    first_atr = sum(trs[:period]) / period
    atr_values.append(first_atr)

    for i in range(period, len(trs)):
        atr = (atr_values[-1] * (period - 1) + trs[i]) / period
        atr_values.append(atr)

    return atr_values
