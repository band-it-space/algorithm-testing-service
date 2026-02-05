import numpy as np
from datetime import datetime
from app.workers.algo_func.get_code_energy import calculate_energy_indicators_last_16_days
import pandas as pd
from dataclasses import dataclass
from typing import List, Optional
import logging

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

def calc_tr_series(data):
    trs = []
    for i in range(1, len(data)):
        high = num(data[i].high, "high") if num(data[i].high, "high") != 0 else num(data[i].close, "high")
        low = num(data[i].low, "low") if num(data[i].low, "low") != 0 else num(data[i].close, "low")
        prev_close = num(data[i - 1].close, "prevClose")
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
    return trs

def sma(values, period):
    if len(values) < period:
        return []
    result = []
    for i in range(period - 1, len(values)):
        result.append(sum(values[i - period + 1 : i + 1]) / period)
    return result

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
        atr_val = (atr_values[-1] * (period - 1) + trs[i]) / period
        atr_values.append(atr_val)

    return atr_values

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


def num(value, name):
    try:
        n = float(value)
        if not np.isfinite(n):
            return 0.0
        return n
    except (ValueError, TypeError):
        return 0.0


def exit_by_stop_loss(ohlcv, stop_loss, params: AlgorithmParameters = None):
    if not isinstance(ohlcv, list) or len(ohlcv) == 0:
        return False
    if not isinstance(stop_loss, (int, float)) or not np.isfinite(stop_loss):
        return False

    last = ohlcv[-1]
    close = float(last.close)
    if not np.isfinite(close):
        return False

    return close <= stop_loss

def s4(ohlcv, buy_date, buy_price, params: AlgorithmParameters = None):
    if params is None:
        params = AlgorithmParameters()
    
    max_days = params.input_S4_max_days  # was 50
    sma_period = params.input_S4_sma_period  # was 150
    ratio_threshold = params.input_S4_ratio_threshold  # was 0.5
    gain_threshold = params.input_S4_gain_threshold  # was 5.0
    
    data = sorted(ohlcv, key=lambda x: to_ts(x.date))
    min_required = sma_period + max_days
    if len(data) < min_required:
        return False

    closes = [num(d.close, "close") for d in data]
    sma_vals = sma(closes, sma_period)
    sma_aligned = [None] * (sma_period - 1) + list(sma_vals)

    bts = to_ts(buy_date)
    buy_idx = next((i for i, d in enumerate(data) if to_ts(d.date) == bts), -1)
    if buy_idx == -1:
        buy_idx = next((i for i, d in enumerate(data) if to_ts(d.date) > bts), -1)
    if buy_idx == -1:
        return False

    if buy_idx < sma_period - 1:
        return False

    day_n_idx = buy_idx + max_days
    if day_n_idx >= len(data):
        return False

    window_idx = range(buy_idx + 1, day_n_idx + 1)
    if any(sma_aligned[i] is None or not np.isfinite(sma_aligned[i]) for i in window_idx):
        return False

    A = sum(1 for i in window_idx if np.isfinite(closes[i]) and closes[i] > sma_aligned[i])
    ratio = A / float(max_days)

    close_n = closes[day_n_idx]
    if not np.isfinite(close_n):
        return False
    gain_pct = ((close_n - buy_price) / buy_price) * 100.0

    return (ratio < ratio_threshold) and (gain_pct < gain_threshold)

def s5(ohlcv, buy_date, buy_price, stop_loss, trade_date: str, params: AlgorithmParameters = None):
    if params is None:
        params = AlgorithmParameters()
    
    initial_days = params.input_S5_initial_days  # was 45
    step_days = params.input_S5_step_days  # was 25
    push_up_atr = params.input_S5_push_up_atr  # was 0.40
    atr_period = params.input_S5_atr_period  # was 20
    
    buy_date = datetime.fromisoformat(buy_date.replace("Z", "")).strftime("%Y-%m-%d")

    current_index = len(ohlcv) - 1
    current_close = float(ohlcv[current_index].close)
    
    buy_index = next(
        (i for i, d in enumerate(ohlcv) if d.date == buy_date),
        None,  
    )
    
    if buy_index is None:
        return False, stop_loss

    days_since_buy = current_index - buy_index
    
    is_key_day = False
    if days_since_buy == initial_days:
        is_key_day = True
    elif days_since_buy > initial_days and (days_since_buy - initial_days + 1) % step_days == 0:
        is_key_day = True
    elif days_since_buy > initial_days:
        return current_close < stop_loss, stop_loss

    if not is_key_day:
        return False, stop_loss

    current_atr = atr(ohlcv, atr_period)[-1]
    
    if current_atr is None or current_atr == 0:
        return False, stop_loss

    if days_since_buy == initial_days:
        new_stop_loss = buy_price + push_up_atr * current_atr
    else:
        new_stop_loss = stop_loss + push_up_atr * current_atr

    exit_signal = current_close < new_stop_loss

    return exit_signal, new_stop_loss

def ema(values, period):
    if len(values) < period:
        return []
    k = 1 / period
    ema_vals = [sum(values[:period]) / period]
    for v in values[period:]:
        ema_vals.append(ema_vals[-1] + k * (v - ema_vals[-1]))
    return ema_vals

def fibo_exit_stop(
    ohlcv,
    buy_date,
    *,
    xx_days: int,
    level: float,
    yy_days: int
) -> bool:
    data = sorted(ohlcv, key=lambda x: to_ts(x.date))
    n = len(data)

    if n < 250:
        return False

    bts = to_ts(buy_date)
    buy_idx = -1
    for i, d in enumerate(data):
        if to_ts(d.date) == bts:
            buy_idx = i
            break

    if buy_idx == -1:
        for i, d in enumerate(data):
            if to_ts(d.date) > bts:
                buy_idx = i
                break

    if buy_idx == -1:
        return False

    last_idx = n - 1
    bars_since_entry = last_idx - buy_idx

    if bars_since_entry <= xx_days:
        return False

    def below_fibo_level(i: int) -> bool:
        if i < 249:
            return False

        window = data[i - 249 : i + 1]
        highs = [num(d.high, "high") for d in window]
        lows  = [num(d.low,  "low")  for d in window]

        high250 = max(highs)
        low250  = min(lows)

        if (not np.isfinite(high250) or
            not np.isfinite(low250) or
            high250 <= low250):
            return False

        close_i = num(data[i].close, "close")
        if not np.isfinite(close_i):
            return False

        ratio = (high250 - close_i) / (high250 - low250)
        return ratio > level

    true_count = 0
    for offset in range(yy_days):
        i = last_idx - offset
        if i < 0:
            return False
        if below_fibo_level(i):
            true_count += 1

    return true_count == yy_days


def s6(ohlcv, buy_date, trade_date, params: AlgorithmParameters = None):
    if params is None:
        params = AlgorithmParameters()
    
    min_days = params.input_S6_min_days  # was 50
    high_window = params.input_S6_high_window  # was 90
    days_threshold = params.input_S6_days_threshold  # was 76
    
    data = sorted(ohlcv, key=lambda x: to_ts(x.date))

    if len(data) < high_window + 10:
        logger.info(f"S6: not enough data ({len(data)} rows). Exit=False")
        return False

    last_idx = len(data) - 1

    bts = to_ts(buy_date)
    buy_idx = -1

    for i, d in enumerate(data):
        if to_ts(d.date) == bts:
            buy_idx = i
            break

    if buy_idx == -1:
        for i, d in enumerate(data):
            if to_ts(d.date) > bts:
                buy_idx = i
                break

    if buy_idx == -1:
        logger.warning(f"S6: buy_date {buy_date} not found. Exit=False")
        return False

    days_since_buy = last_idx - buy_idx
    if days_since_buy < min_days:
        logger.info("S6: days_since_buy < min_days, condition not active. Exit=False")
        return False

    if last_idx < high_window - 1:
        logger.info(f"S6: not enough history for {high_window}D high. Exit=False")
        return False

    highs = [num(d.high, "high") for d in data]

    start_window = last_idx - high_window + 1
    window_highs = highs[start_window:last_idx + 1]
    high_n = max(window_highs)

    last_high_idx = max(
        i for i in range(start_window, last_idx + 1)
        if highs[i] == high_n
    )
    days_since_high = last_idx - last_high_idx

    if days_since_high >= days_threshold:
        logger.info(
            f"S6: no {high_window}D high in the last {days_threshold} days. Exit=True",
        )
        return True

    return False


def s7(ohlcv, buy_date, buy_price, params: AlgorithmParameters = None):
    if params is None:
        params = AlgorithmParameters()
    
    atr_period = params.input_S7_atr_period  # was 22
    body_mult = params.input_S7_body_mult  # was 2.0
    
    data = sorted(ohlcv, key=lambda x: to_ts(x.date))
    n = len(data)
    if n < atr_period + 2:
        return False

    atr22_series = atr(data, atr_period)
    if len(atr22_series) < 2:
        return False

    last_idx = n - 1
    prev_idx = n - 2

    atr_prev = atr22_series[-2]
    atr_last = atr22_series[-1]

    open_prev = num(data[prev_idx].open, "open(prev)")
    close_prev = num(data[prev_idx].close, "close(prev)")
    open_last = num(data[last_idx].open, "open(last)")
    close_last = num(data[last_idx].close, "close(last)")

    body_prev = open_prev - close_prev
    body_last = open_last - close_last

    cond_prev = body_prev > body_mult * atr_prev
    cond_last = body_last > body_mult * atr_last

    return cond_prev and cond_last


def s8(ohlcv, buy_date, buy_price, params: AlgorithmParameters = None):
    if params is None:
        params = AlgorithmParameters()
    
    atr22_window = params.input_S8_atr22_window  # was 126
    atr100_threshold = params.input_S8_atr100_threshold  # was 0.74
    body_mult = params.input_S8_body_mult  # was 2.4
    bear_count = params.input_S8_bear_count  # was 3
    
    data = sorted(ohlcv, key=lambda x: to_ts(x.date))
    n = len(data)

    if n < 148:
        return False

    trs = calc_tr_series(data)
    atr22 = sma(trs, 22)
    atr100 = sma(trs, 100)

    if len(atr22) < atr22_window:
        return False
    if len(atr100) < 5:
        return False

    max_atr22 = max(atr22[-atr22_window:])
    current_atr100 = atr100[-1]
    if not (current_atr100 > atr100_threshold * max_atr22):
        return False

    last5_atr100 = atr100[-5:]
    count_bear_huge = 0
    for j in range(5):
        bar = data[n - 5 + j]
        body = num(bar.open, "open") - num(bar.close, "close")
        thr = body_mult * num(last5_atr100[j], "ATR100")
        if body > thr:
            count_bear_huge += 1

    return count_bear_huge >= bear_count

def s9(trade_date, ohlcv, spy_data, params: AlgorithmParameters = None):
    if params is None:
        params = AlgorithmParameters()
    
    energy_thresh = params.input_S9_energy_thresh  # was 0.22
    
    energy_level = calculate_energy_indicators_last_16_days(trade_date, ohlcv, spy_data)
    return energy_level["energy_score"] < energy_thresh

def s10(ohlcv, buy_date, buy_price, params: AlgorithmParameters = None):
    if params is None:
        params = AlgorithmParameters()
    
    atr_ratio = params.input_S10_atr_ratio  # was 2.6
    drawdown = params.input_S10_drawdown  # was 0.05
    
    data = sorted(ohlcv, key=lambda x: to_ts(x.date))
    n = len(data)

    if n < 101:
        return False
    
    atr10_series = atr(data, 10)
    atr100_series = atr(data, 100)

    if len(atr10_series) < 1 or len(atr100_series) < 1:
        return False

    atr10 = num(atr10_series[-1], "ATR(10)")
    atr100 = num(atr100_series[-1], "ATR(100)")

    last90 = data[-91:-1]
    high90 = max(num(d.high, "high") for d in last90)
    if not np.isfinite(high90) or high90 <= 0:
        return False

    last_close = num(data[n - 1].close, "close")
    drawdown_pct = ((high90 - last_close) / high90)

    cond_vol = atr10 > atr_ratio * atr100
    cond_dd = drawdown_pct > drawdown

    return cond_vol and cond_dd


def s11(ohlcv, buy_date, buy_price, params: AlgorithmParameters = None):
    if params is None:
        params = AlgorithmParameters()
    
    return fibo_exit_stop(
        ohlcv,
        buy_date,
        xx_days=params.input_S11_xx_days,  # was 300
        level=params.input_S11_fib_level,   # was 0.382
        yy_days=params.input_S11_yy_days,   # was 2
    )


def s12(ohlcv, buy_date, buy_price, params: AlgorithmParameters = None):
    if params is None:
        params = AlgorithmParameters()
    
    return fibo_exit_stop(
        ohlcv,
        buy_date,
        xx_days=params.input_S12_xx_days,  # was 240
        level=params.input_S12_fib_level,   # was 0.236
        yy_days=params.input_S12_yy_days,   # was 22
    )


def s13(ohlcv, buy_date, buy_price, params: AlgorithmParameters = None):
    if params is None:
        params = AlgorithmParameters()
    
    min_days = params.input_S13_min_days  # was 238
    lookback = params.input_S13_lookback  # was 80
    
    data = sorted(ohlcv, key=lambda x: to_ts(x.date))
    n = len(data)
    if n < lookback + 1:
        return False

    bts = to_ts(buy_date)
    buy_idx = -1
    for i, d in enumerate(data):
        if to_ts(d.date) == bts:
            buy_idx = i
            break
    if buy_idx == -1:
        for i, d in enumerate(data):
            if to_ts(d.date) > bts:
                buy_idx = i
                break
    if buy_idx == -1:
        return False

    last_idx = n - 1
    days_since_buy = last_idx - buy_idx

    if days_since_buy < min_days:
        return False

    prev_n = data[last_idx - lookback : last_idx]
    min_close_n = min(num(d.close, "close") for d in prev_n)

    last_close = num(data[last_idx].close, "close")

    return last_close < min_close_n

def s14(ohlcv, hsi_ohlcv, buy_date, buy_price, params: AlgorithmParameters = None):
    if params is None:
        params = AlgorithmParameters()
    
    min_days = params.input_S14_min_days  # was 300
    horizons = params.input_S14_horizons  # was [35, 70, 105]
    
    asset = sorted(ohlcv, key=lambda x: to_ts(x.date))
    hsi = sorted(hsi_ohlcv, key=lambda x: to_ts(x.date))

    max_horizon = max(horizons) + 1
    if len(asset) < max_horizon or len(hsi) < max_horizon:
        return False

    map_asset = {to_ts(b.date): num(b.close, "asset.close") for b in asset}
    map_hsi = {to_ts(b.date): num(b.close, "hsi.close") for b in hsi}

    common_ts = sorted([ts for ts in map_asset.keys() if ts in map_hsi])
    if len(common_ts) < max_horizon:
        return False

    asset_c = [map_asset[ts] for ts in common_ts]
    hsi_c = [map_hsi[ts] for ts in common_ts]

    last_idx = len(common_ts) - 1

    bts = to_ts(buy_date)
    buy_idx = -1
    for i, ts in enumerate(common_ts):
        if ts == bts:
            buy_idx = i
            break
    if buy_idx == -1:
        for i, ts in enumerate(common_ts):
            if ts > bts:
                buy_idx = i
                break
    if buy_idx == -1:
        return False

    days_since_buy = last_idx - buy_idx
    if days_since_buy < min_days:
        return False

    under_all = True
    for horizon in horizons:
        if last_idx - horizon < 0:
            return False
        ra = asset_c[last_idx] / asset_c[last_idx - horizon] - 1
        rh = hsi_c[last_idx] / hsi_c[last_idx - horizon] - 1
        if ra >= rh:
            under_all = False
            break

    return under_all

def s15(ohlcv, buy_date, buy_price, params: AlgorithmParameters = None):
    if params is None:
        params = AlgorithmParameters()
    
    crash_drop = params.input_S15_crash_drop  # was 0.25
    lookback = params.input_S15_lookback  # was 4
    
    data = sorted(ohlcv, key=lambda x: to_ts(x.date))
    n = len(data)

    if n < lookback + 1:
        return False

    last_idx = n - 1
    last_close = num(data[last_idx].close, "close[last]")
    base_close = num(data[last_idx - lookback].close, f"close[t-{lookback}]")
    if base_close <= 0:
        return False

    ret = (last_close / base_close) - 1
    return ret < -crash_drop

def s16(
    ohlcv,
    buy_date,
    params: AlgorithmParameters = None,
):
    if params is None:
        params = AlgorithmParameters()
    
    s16_xx = params.input_S16_xx  # was 15.0
    s16_yy = params.input_S16_yy  # was 10
    s16_effective = params.input_S16_effective  # was 0
    s16_atr_inc = params.input_S16_atr_inc  # was 50.0
    s16_atr_day = params.input_S16_atr_day  # was 12
    atr_period = 22
    
    data = sorted(ohlcv, key=lambda x: to_ts(x.date))
    n = len(data)
    if n < atr_period + s16_yy + s16_atr_day + 1:
        return False

    bts = to_ts(buy_date)
    entry_idx = -1
    for i, d in enumerate(data):
        if to_ts(d.date) == bts:
            entry_idx = i
            break
    if entry_idx == -1:
        for i, d in enumerate(data):
            if to_ts(d.date) > bts:
                entry_idx = i
                break
    if entry_idx == -1:
        return False

    last_idx = n - 1
    bars_since_entry = last_idx - entry_idx
    if bars_since_entry <= s16_effective:
        return False

    if last_idx - s16_yy < 0:
        return False

    last_close = num(data[last_idx].close, "close[last]")
    base_close = num(data[last_idx - s16_yy].close, "close[t-YY]")
    if base_close <= 0:
        return False

    ret_yy = last_close / base_close - 1
    big_drop = ret_yy < -s16_xx / 100.0

    trs = calc_tr_series(data)
    atr22 = atr(data, atr_period)
    if len(atr22) < s16_atr_day + 1:
        return False

    atr_now = num(atr22[-1], "ATR22[now]")
    atr_past = num(atr22[-1 - s16_atr_day], "ATR22[t-ATR_day]")
    if atr_past <= 0:
        return False

    vol_spike = (atr_now / atr_past - 1.0) * 100.0 > s16_atr_inc

    return vol_spike and big_drop

def s17(ohlcv, buy_date, buy_price, params: AlgorithmParameters = None):
    if params is None:
        params = AlgorithmParameters()
    
    min_days = params.input_S17_min_days  # was 150
    wide_range = params.input_S17_wide_range  # was 1.6
    near_bottom = params.input_S17_near_bottom  # was 1.3
    
    data = sorted(ohlcv, key=lambda x: to_ts(x.date))
    n = len(data)

    if n < min_days:
        return False

    bts = to_ts(buy_date)
    buy_idx = -1
    for i, d in enumerate(data):
        if to_ts(d.date) == bts:
            buy_idx = i
            break
    if buy_idx == -1:
        for i, d in enumerate(data):
            if to_ts(d.date) > bts:
                buy_idx = i
                break
    if buy_idx == -1:
        return False

    last_idx = n - 1
    days_since_buy = last_idx - buy_idx

    if days_since_buy < min_days:
        return False

    window = data[-min_days:]
    high_n = max(num(d.high, "high") for d in window)
    low_n = min(num(d.low, "low") for d in window)
    if not np.isfinite(high_n) or not np.isfinite(low_n) or high_n <= low_n:
        return False

    is_wide_range = high_n > wide_range * low_n

    if not is_wide_range:
        return False

    last_close = num(data[last_idx].close, "close")
    is_near_bottom = last_close < near_bottom * low_n

    return is_near_bottom


def runAllSellConditions(ohlcv, spy_data, buy_date, buy_price, stop_loss, trade_date, 
                         params: AlgorithmParameters = None):
    if params is None:
        params = AlgorithmParameters()
    
    s5_exit, new_stop = s5(ohlcv, buy_date, buy_price, stop_loss, trade_date, params)

    conditions = {
        "S1": exit_by_stop_loss(ohlcv, stop_loss, params),
        "S4": s4(ohlcv, buy_date, buy_price, params),
        "S5": s5_exit,
        "S6": s6(ohlcv, buy_date, trade_date, params),
        "S7": s7(ohlcv, buy_date, buy_price, params),
        "S8": s8(ohlcv, buy_date, buy_price, params),
        "S9": s9(trade_date, ohlcv, spy_data, params),
        "S10": s10(ohlcv, buy_date, buy_price, params),
        "S11": s11(ohlcv, buy_date, buy_price, params),
        "S12": s12(ohlcv, buy_date, buy_price, params),
        "S13": s13(ohlcv, buy_date, buy_price, params),
        "S14": s14(ohlcv, spy_data, buy_date, buy_price, params),
        "S15": s15(ohlcv, buy_date, buy_price, params),
        "S16": s16(ohlcv, buy_date, params),
        "S17": s17(ohlcv, buy_date, buy_price, params),
    }

    return {"conditions": conditions, "stop_loss": new_stop}


def isSell(signals):
    return (
        signals["S1"]
        or signals["S4"]
        or signals["S5"]
        or signals["S6"]
        or signals["S7"]
        or signals["S8"]
        or signals["S9"]
        or signals["S10"]
        or signals["S11"]
        or signals["S12"]
        or signals["S13"]
        or signals["S14"]
        or signals["S15"]
        or signals["S16"]
        or signals["S17"]
    )
