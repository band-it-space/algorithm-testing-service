import numpy as np
from datetime import datetime
import pandas as pd
from dataclasses import dataclass
from typing import List, Optional
import logging

from app.workers.algo_func.get_code_energy import calculate_energy_indicators_last_16_days
from app.workers.algo_func.helpers import to_ts, sma, atr

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

def exit_by_stop_loss(ohlcv, stop_loss):
    if not isinstance(ohlcv, list) or len(ohlcv) == 0:
        return False
    if not isinstance(stop_loss, (int, float)) or not np.isfinite(stop_loss):
        return False

    last = ohlcv[-1]
    close = float(last.close)
    if not np.isfinite(close):
        return False

    return close <= stop_loss

def s4(ohlcv, buy_date, buy_price):
    data = sorted(ohlcv, key=lambda x: to_ts(x.date))
    if len(data) < 200:
        raise ValueError(
            "Insufficient history: need at least ~200 days for 150D SMA and validation window."
        )

    closes = [num(d.close, "close") for d in data]
    sma_vals = sma(closes, 150)  # length N-149
    sma150 = [None] * 149 + list(sma_vals)  # align to N

    bts = to_ts(buy_date)
    buy_idx = next((i for i, d in enumerate(data) if to_ts(d.date) == bts), -1)
    if buy_idx == -1:
        buy_idx = next((i for i, d in enumerate(data) if to_ts(d.date) > bts), -1)
    if buy_idx == -1:
        raise ValueError("Buy date is outside data range.")

    if buy_idx < 149:
        return False

    day50_idx = buy_idx + 50
    if day50_idx >= len(data):
        return False

    window_idx = range(buy_idx + 1, day50_idx + 1)
    if any(sma150[i] is None or not np.isfinite(sma150[i]) for i in window_idx):
        return False

    A = sum(1 for i in window_idx if np.isfinite(closes[i]) and closes[i] > sma150[i])
    ratio = A / 50.0

    close50 = closes[day50_idx]
    if not np.isfinite(close50):
        raise ValueError("Unexpected: no valid Close on day 50.")
    gain_pct = ((close50 - buy_price) / buy_price) * 100.0

    return (ratio < 0.5) and (gain_pct < 5.0)

def s5(ohlcv, buy_date, buy_price, stop_loss, trade_date: str):
    buy_date = datetime.fromisoformat(buy_date.replace("Z", "")).strftime("%Y-%m-%d")
    # logger.info(f"Day today: {trade_date}")
    # logger.info(f"Current stop_loss: {stop_loss}")

    current_index = len(ohlcv) - 1
    current_close = float(ohlcv[current_index].close)
    
    buy_index = next(
        (i for i, d in enumerate(ohlcv) if d.date == buy_date),
        None,  
    )
    
    if buy_index is None:
        return False, stop_loss

    days_since_buy = current_index - buy_index
    # logger.info(f"Days since buy: {days_since_buy}")
    
    is_key_day = False
    if days_since_buy == 45:
        is_key_day = True
    elif days_since_buy > 45 and (days_since_buy - 44) % 25 == 0:
        is_key_day = True
    elif days_since_buy > 45:
        return current_close < stop_loss , stop_loss

    if not is_key_day:
        return False, stop_loss

    current_atr = atr(ohlcv, 20)[-1]
    
    if current_atr is None or current_atr == 0:
        return False, stop_loss

    if days_since_buy == 45:
        new_stop_loss = buy_price + 0.62 * current_atr
    else:
        new_stop_loss = stop_loss + 0.62 * current_atr

    
    exit_signal = current_close < new_stop_loss

    return exit_signal, new_stop_loss

def ema(values, period):
    if len(values) < period:
        return []
    k = 1 / period
    ema_vals = [sum(values[:period]) / period]  # стартуємо з SMA
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
    """
    Універсальна Fibo-умова виходу за аналогією з MultiCharts:

        if barssinceentry(0) > xx_days then
            if countif( (highest(high,250)-close)/(highest(high,250)-lowest(low,250)) > level,
                       yy_days ) = yy_days
                then EXIT

    Параметри:
        xx_days – через скільки днів після входу умова взагалі починає працювати
        level   – поріг у виразі (H - C)/(H - L) > level (0.382, 0.236, ...)
        yy_days – скільки останніх днів поспіль ця умова має бути виконана
    """

    # Сортуємо по даті
    data = sorted(ohlcv, key=lambda x: to_ts(x.date))
    n = len(data)

    if n < 250:
        raise ValueError("Insufficient history: need at least 250 days for 250D High/Low.")

    # Знаходимо індекс входу
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
        raise ValueError("Buy date is outside data range.")

    last_idx = n - 1
    bars_since_entry = last_idx - buy_idx  # аналог barssinceentry(0)

    # MultiCharts: barssinceentry(0) > xx_days
    if bars_since_entry <= xx_days:
        return False

    # Перевірка умови (H - C)/(H - L) > level для конкретного дня i
    def below_fibo_level(i: int) -> bool:
        # потрібні хоча б 250 барів до i включно
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

    # Аналог countif(cond, yy_days) = yy_days для ОСТАННІХ yy_days барів
    true_count = 0
    for offset in range(yy_days):
        i = last_idx - offset
        if i < 0:
            return False
        if below_fibo_level(i):
            true_count += 1

    return true_count == yy_days


def s6(ohlcv, buy_date, trade_date):
    # logger.info(f"Running S6 for trade date: {trade_date}. ohlcv: {ohlcv[-1]}")
    data = sorted(ohlcv, key=lambda x: to_ts(x.date))

    if len(data) < 100:
        logger.info(f"S6: not enough data ({len(data)} rows), need at least 100. Exit=False")
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
        logger.warning(f"S6: buy_date {buy_date} not found and no later date in data. Exit=False")
        return False

    days_since_buy = last_idx - buy_idx
    # logger.info(f"days since buy: {days_since_buy}")
    if days_since_buy < 50:
        logger.info("S6: days_since_buy < 50, condition not active. Exit=False")
        return False

    if last_idx < 89:
        logger.info("S6: not enough history for 90D high (last_idx={last_idx}). Exit=False")
        return False

    highs = [num(d.high, "high") for d in data]

    start_90 = last_idx - 89
    window_90 = highs[start_90:last_idx + 1]
    high_90 = max(window_90)

    last_high_idx = max(
        i for i in range(start_90, last_idx + 1)
        if highs[i] == high_90
    )
    high_90 = max(window_90)
    # logger.info(f"last_high_idx={last_high_idx} last_idx={last_idx} w_90: {window_90}, high_90: {high_90}, days_since_high: {last_idx - last_high_idx}")
    days_since_high = last_idx - last_high_idx

    if days_since_high >= 76:
        logger.info(
            "S6: no 90D high in the last 76 days (days_since_high=%d >= 76). Exit=True",
            days_since_high,
        )
        return True

    return False

def s7(ohlcv, buy_date, buy_price):
    data = sorted(ohlcv, key=lambda x: to_ts(x.date))
    n = len(data)
    if n < 23:
        raise ValueError("Insufficient data: need at least 23 daily bars for S7.")

    atr22_series = atr(data, 22)
    if len(atr22_series) < 2:
        raise ValueError(
            "Insufficient history to calculate ATR(22) for the last two days."
        )

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

    cond_prev = body_prev > 2 * atr_prev
    cond_last = body_last > 2 * atr_last

    return cond_prev and cond_last


def s8(ohlcv, buy_date, buy_price):
    data = sorted(ohlcv, key=lambda x: to_ts(x.date))
    n = len(data)

    if n < 148:
        raise ValueError("Insufficient history: need at least 148 days for S8.")

    trs = calc_tr_series(data)
    atr22 = sma(trs, 22)
    atr100 = sma(trs, 100)

    if len(atr22) < 126:
        raise ValueError("Too few ATR(22) values for 126-day window.")
    if len(atr100) < 5:
        raise ValueError("Too few ATR(100) values for last 5 days.")

    max_atr22_126 = max(atr22[-126:])
    current_atr100 = atr100[-1]
    if not (current_atr100 > 0.74 * max_atr22_126):
        return False

    last5_atr100 = atr100[-5:]
    count_bear_huge = 0
    for j in range(5):
        bar = data[n - 5 + j]
        body = num(bar.open, "open") - num(bar.close, "close")
        thr = 2.4 * num(last5_atr100[j], "ATR100")
        if body > thr:
            count_bear_huge += 1

    return count_bear_huge >= 3

def s9(trade_date, ohlcv, spy_data):
    energy_level = calculate_energy_indicators_last_16_days(trade_date, ohlcv, spy_data)
    return energy_level["energy_score"] < 0.22

def s10(ohlcv, buy_date, buy_price):
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
    drawdown_pct = ((high90 - last_close) / high90) * 100

    cond_vol = atr10 > 2.6 * atr100
    cond_dd = drawdown_pct > 5

    return cond_vol and cond_dd


def s11(ohlcv, buy_date, buy_price):
    # S11. EFFECTIVE after {300} Days
    # level = 0.382, YY ≈ 2
    try:
        return fibo_exit_stop(
            ohlcv,
            buy_date,
            xx_days=300,
            level=0.382,
            yy_days=2,
        )
    except (ValueError, Exception):
        return False


def s12(ohlcv, buy_date, buy_price):
    # S12. EFFECTIVE after {240} Days
    # level = 0.236, YY ≈ 22
    try:
        return fibo_exit_stop(
            ohlcv,
            buy_date,
            xx_days=240,
            level=0.236,
            yy_days=22,
        )
    except (ValueError, Exception):
        return False
# def s12(ohlcv, buy_date, buy_price):
#     data = sorted(ohlcv, key=lambda x: to_ts(x.date))
#     n = len(data)

#     if n < 250:
#         raise ValueError(
#             "Insufficient history: need at least 250 days for Fibo Top/Bottom."
#         )

#     bts = to_ts(buy_date)
#     buy_idx = -1
#     for i, d in enumerate(data):
#         if to_ts(d.date) == bts:
#             buy_idx = i
#             break
#     if buy_idx == -1:
#         for i, d in enumerate(data):
#             if to_ts(d.date) > bts:
#                 buy_idx = i
#                 break
#     if buy_idx == -1:
#         raise ValueError("Buy date is outside data range.")

#     last_idx = n - 1
#     days_since_buy = last_idx - buy_idx

#     if days_since_buy < 240:
#         return False

#     window250 = data[-250:]
#     top = max(num(d.high, "high") for d in window250)
#     bottom = min(num(d.low, "low") for d in window250)
#     if not np.isfinite(top) or not np.isfinite(bottom) or top <= bottom:
#         raise ValueError("Invalid 250D High/Low range.")

#     level0236 = bottom + 0.236 * (top - bottom)

#     streak_below = 0
#     for i in range(last_idx, -1, -1):
#         c = num(data[i].close, "close")
#         if c < level0236:
#             streak_below += 1
#         else:
#             break

#     return streak_below >= 23

def s13(ohlcv, buy_date, buy_price):
    data = sorted(ohlcv, key=lambda x: to_ts(x.date))
    n = len(data)
    if n < 81:
        raise ValueError("Insufficient history: need at least 81 days.")

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
        raise ValueError("Buy date is outside data range.")

    last_idx = n - 1
    days_since_buy = last_idx - buy_idx

    if days_since_buy < 238:
        return False

    prev80 = data[last_idx - 80 : last_idx]
    min_close80 = min(num(d.close, "close") for d in prev80)

    last_close = num(data[last_idx].close, "close")

    return last_close < min_close80

def s14(ohlcv, hsi_ohlcv, buy_date, buy_price):
    asset = sorted(ohlcv, key=lambda x: to_ts(x.date))
    hsi = sorted(hsi_ohlcv, key=lambda x: to_ts(x.date))

    if len(asset) < 106 or len(hsi) < 106:
        raise ValueError("Insufficient history: need at least 106 days.")

    map_asset = {to_ts(b.date): num(b.close, "asset.close") for b in asset}
    map_hsi = {to_ts(b.date): num(b.close, "hsi.close") for b in hsi}

    common_ts = sorted([ts for ts in map_asset.keys() if ts in map_hsi])
    if len(common_ts) < 106:
        raise ValueError("Too few common trading days between asset and HSI.")

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
        raise ValueError("Buy date is outside common dates range.")

    days_since_buy = last_idx - buy_idx
    if days_since_buy < 300:
        return False

    horizons = [35, 70, 105]
    for horizon in horizons:
        if last_idx - horizon < 0:
            raise ValueError(f"Too few common data for {horizon} day horizon.")

    under_all = True
    for horizon in horizons:
        ra = asset_c[last_idx] / asset_c[last_idx - horizon] - 1
        rh = hsi_c[last_idx] / hsi_c[last_idx - horizon] - 1
        if ra >= rh:
            under_all = False
            break

    return under_all

def s15(ohlcv, buy_date, buy_price):
    """
    S15: Rapid decline exit - price drops > 25% in 4 days
    
    MC Code: (close[4] - close) / close[4] * 100 > 25
    Equivalent: (close / close[4]) - 1 < -0.25
    """
    try:
        data = sorted(ohlcv, key=lambda x: to_ts(x.date))
        n = len(data)

        if n < 5:
            return False

        last_idx = n - 1
        last_close = num(data[last_idx].close, "close[last]")
        base_close = num(data[last_idx - 4].close, "close[t-4]")
        if base_close <= 0:
            return False

        ret4d = (last_close / base_close) - 1
        return ret4d < -0.25
    except (ValueError, Exception):
        return False

def s16(
    ohlcv,
    buy_date,
    *,
    s16_xx: float = 15.0,
    s16_yy: int = 10,
    s16_effective: int = 0,
    s16_atr_inc: float = 50.0,
    s16_atr_day: int = 12,
    atr_period: int = 22,
):
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

def s17(ohlcv, buy_date, buy_price):
    """
    S17: Wide range retracement exit (effective after 150 days)
    
    MC Code:
        if barssinceentry(0) > input_S17_XX then
            if (highest(high, XX) / lowest(low, XX) - 1) * 100 > input_S17_YY then
                if (close / lowest(low, XX) - 1) * 100 < input_S17_YY / 2 then
                    is_stop_S17 = true
    
    Logic:
    1. Activation: days_since_entry > 150
    2. Wide range: (150D_high / 150D_low - 1) > 0.6 (60%)
    3. Near bottom: (close / 150D_low - 1) < 0.3 (30%)
    
    input_S17_XX = 150, input_S17_YY = 60
    """
    try:
        data = sorted(ohlcv, key=lambda x: to_ts(x.date))
        n = len(data)

        if n < 150:
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

        # MC: barssinceentry(0) > 150 (activation AFTER 150 days)
        if days_since_buy <= 150:
            return False

        window150 = data[-150:]
        high150 = max(num(d.high, "high") for d in window150)
        low150 = min(num(d.low, "low") for d in window150)
        if not np.isfinite(high150) or not np.isfinite(low150) or high150 <= low150:
            return False

        # Condition 1: (high/low - 1) * 100 > 60  =>  high > 1.6 * low
        wide_range = high150 > 1.6 * low150

        if not wide_range:
            return False

        last_close = num(data[last_idx].close, "close")
        
        # Condition 2: (close/low - 1) * 100 < 30  =>  close < 1.3 * low
        near_bottom = last_close < 1.3 * low150

        return near_bottom
    except (ValueError, Exception):
        return False


def runAllSellConditions(ohlcv, spy_data, buy_date, buy_price, stop_loss, trade_date):
    s5_exit, new_stop = s5(ohlcv, buy_date, buy_price, stop_loss, trade_date)

    conditions = {
        "S1": exit_by_stop_loss(ohlcv, stop_loss),
        "S4": s4(ohlcv, buy_date, buy_price),
        "S5": s5_exit,
        "S6": s6(ohlcv, buy_date, trade_date),
        "S7": s7(ohlcv, buy_date, buy_price),
        "S8": s8(ohlcv, buy_date, buy_price),
        "S9": s9(trade_date, ohlcv, spy_data),
        "S10": s10(ohlcv, buy_date, buy_price),
        "S11": s11(ohlcv, buy_date, buy_price),
        "S12": s12(ohlcv, buy_date, buy_price),
        "S13": s13(ohlcv, buy_date, buy_price),
        "S14": s14(ohlcv, spy_data, buy_date, buy_price),
        "S15": s15(ohlcv, buy_date, buy_price),
        "S16": s16(ohlcv, buy_date),
        "S17": s17(ohlcv, buy_date, buy_price),
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



def num(value, name):
    try:
        n = float(value)
        if not np.isfinite(n):
            return 0.0
        return n
    except (ValueError, TypeError):
        return 0.0


# def wilder_atr(trs, period):
#     if len(trs) < period:
#         return []

#     atr = [None] * len(trs)
#     # перше значення – це проста середня TR за весь період
#     atr[period - 1] = sum(trs[:period]) / period

#     # далі йде рекурсивна формула Вайлдера
#     for i in range(period, len(trs)):
#         atr[i] = (atr[i - 1] * (period - 1) + trs[i]) / period

#     return atr
