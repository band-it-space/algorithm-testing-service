import numpy as np
from datetime import datetime
from app.workers.algo_func.get_code_energy import calculate_energy_indicators_last_16_days
import pandas as pd


def sma(values, period):
    if len(values) < period:
        return []
    result = []
    for i in range(period - 1, len(values)):
        result.append(sum(values[i - period + 1 : i + 1]) / period)
    return result


def exit_by_stop_loss(ohlcv, stop_loss):
    if not isinstance(ohlcv, list) or len(ohlcv) == 0:
        raise ValueError("OHLCV is empty or invalid.")
    if not isinstance(stop_loss, (int, float)) or not np.isfinite(stop_loss):
        raise ValueError("stopLoss must be a number.")

    last = ohlcv[-1]
    close = float(last.close)
    if not np.isfinite(close):
        raise ValueError("Invalid Close value for the last day.")

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


def calc_atr20(ohlcv):
    if len(ohlcv) < 21:
        raise ValueError("Insufficient data for ATR(20).")

    trs = []
    for i in range(1, len(ohlcv)):
        high = float(ohlcv[i].high)
        low = float(ohlcv[i].low)
        prev_close = float(ohlcv[i - 1].close)
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)

    atr_vals = wilder_atr(trs, 20)
    return atr_vals[-1]

def s5(ohlcv, buy_date, buy_price, stop_loss):
    buy_date = datetime.fromisoformat(buy_date.replace("Z", "")).strftime("%Y-%m-%d")
    
    buy_index = next(
        (i for i, d in enumerate(ohlcv) if d.date == buy_date),
        None,  
    )
    
    if buy_index is None:
        return False, stop_loss
    
    current_index = len(ohlcv) - 1

    days_since_buy = current_index - buy_index
    print(f"Days since buy: {days_since_buy}")
    
    is_key_day = False
    if days_since_buy == 45:
        is_key_day = True
    elif days_since_buy > 45 and (days_since_buy - 44) % 25 == 0:
        is_key_day = True

    if not is_key_day:
        return False, stop_loss

    # Розраховуємо ATR(20) на поточну дату
    current_atr = calc_atr20(ohlcv)  # повертає float, не Series
    
    # Якщо ATR не може бути розрахований (недостатньо даних), повертаємо поточний стоп
    if current_atr is None or current_atr == 0:
        return False, stop_loss

    # Розраховуємо новий стоп-лос
    if days_since_buy == 45:
        # Перший раз встановлюємо стоп
        new_stop_loss = buy_price + 0.62 * current_atr
    else:
        # Піднімаємо стоп на 0.62*ATR
        new_stop_loss = stop_loss + 0.62 * current_atr

    # Поточна ціна закриття
    current_close = float(ohlcv[current_index].close)

    # Перевіряємо умову виходу (close нижче нового стоп-лосу)
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


def s6(ohlcv, buy_date, buy_price):
    data = sorted(ohlcv, key=lambda x: to_ts(x.date))
    if len(data) < 100:
        raise ValueError(
            "Insufficient history: need at least ~100 days to evaluate 90D high."
        )
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
        raise ValueError("Buy date is outside data range.")

    days_since_buy = last_idx - buy_idx  # 101
    if days_since_buy < 50:
        return False

    start = max(last_idx - 76, 0)
    end = last_idx
    start = max(start, 90)
    if start > end:
        raise ValueError(
            "Insufficient history to check 90-day highs in the given window."
        )

    highs = [num(d.high, "high") for d in data]
    had_new_90d_high = False

    for t in range(start, end + 1):
        prev_max = -float("inf")
        for k in range(t - 90, t):
            if highs[k] > prev_max:
                prev_max = highs[k]
        if highs[t] > prev_max:
            had_new_90d_high = True
            break

    return not had_new_90d_high


def calc_atr22_series(ohlcv):
    n = len(ohlcv)
    trs = []
    for i in range(1, n):
        high = num(ohlcv[i].high, "high")
        low = num(ohlcv[i].low, "low")
        prev_close = num(ohlcv[i - 1].close, "prevClose")
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)

    atr_vals = sma(trs, 22)
    return atr_vals


def s7(ohlcv, buy_date, buy_price):
    data = sorted(ohlcv, key=lambda x: to_ts(x.date))
    n = len(data)
    if n < 23:
        raise ValueError("Insufficient data: need at least 23 daily bars for S7.")

    atr22_series = calc_atr22_series(data)
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


def calc_tr_series(data):
    trs = []
    for i in range(1, len(data)):
        high = num(data[i].high, "high")
        low = num(data[i].low, "low")
        prev_close = num(data[i - 1].close, "prevClose")
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
    return trs


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
        raise ValueError(
            "Insufficient history: need at least 101 days for ATR(100) and 90D High."
        )

    trs = calc_tr_series(data)
    atr10_series = wilder_atr(trs, 10)
    atr100_series = wilder_atr(trs, 100)

    if len(atr10_series) < 1 or len(atr100_series) < 1:
        raise ValueError("Failed to calculate ATR(10) or ATR(100) - insufficient data.")

    atr10 = num(atr10_series[-1], "ATR(10)")
    atr100 = num(atr100_series[-1], "ATR(100)")

    last90 = data[-91:-1]
    high90 = max(num(d.high, "high") for d in last90)
    if not np.isfinite(high90) or high90 <= 0:
        raise ValueError("Invalid 90D High value.")

    last_close = num(data[n - 1].close, "close")
    drawdown_pct = ((high90 - last_close) / high90) * 100

    cond_vol = atr10 > 2.6 * atr100
    cond_dd = drawdown_pct > 5

    return cond_vol and cond_dd


def s11(ohlcv, buy_date, buy_price):
    data = sorted(ohlcv, key=lambda x: to_ts(x.date))
    n = len(data)

    if n < 250:
        raise ValueError(
            "Insufficient history: need at least 250 days to build Fibo Top/Bottom."
        )

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

    if days_since_buy < 300:
        return False

    window250 = data[-250:]
    top = max(num(d.high, "high") for d in window250)
    bottom = min(num(d.low, "low") for d in window250)
    if not np.isfinite(top) or not np.isfinite(bottom) or top <= bottom:
        raise ValueError("Invalid 250D High/Low range for Fibo.")

    level0382 = bottom + 0.382 * (top - bottom)

    streak_below = 0
    for i in range(last_idx, -1, -1):
        c = num(data[i].close, "close")
        if c < level0382:
            streak_below += 1
        else:
            break

    return streak_below >= 3


def s12(ohlcv, buy_date, buy_price):
    data = sorted(ohlcv, key=lambda x: to_ts(x.date))
    n = len(data)

    if n < 250:
        raise ValueError(
            "Insufficient history: need at least 250 days for Fibo Top/Bottom."
        )

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

    if days_since_buy < 240:
        return False

    window250 = data[-250:]
    top = max(num(d.high, "high") for d in window250)
    bottom = min(num(d.low, "low") for d in window250)
    if not np.isfinite(top) or not np.isfinite(bottom) or top <= bottom:
        raise ValueError("Invalid 250D High/Low range.")

    level0236 = bottom + 0.236 * (top - bottom)

    streak_below = 0
    for i in range(last_idx, -1, -1):
        c = num(data[i].close, "close")
        if c < level0236:
            streak_below += 1
        else:
            break

    return streak_below >= 23


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
    data = sorted(ohlcv, key=lambda x: to_ts(x.date))
    n = len(data)

    if n < 5:
        raise ValueError("Insufficient history: need at least 5 trading days for S15.")

    last_idx = n - 1
    last_close = num(data[last_idx].close, "close[last]")
    base_close = num(data[last_idx - 4].close, "close[t-4]")
    if base_close <= 0:
        raise ValueError("Invalid base close[t-4] value.")

    ret4d = (last_close / base_close) - 1
    return ret4d < -0.25


def s16(ohlcv, buy_date, buy_price):
    data = sorted(ohlcv, key=lambda x: to_ts(x.date))
    n = len(data)

    if n < 35:
        raise ValueError("Insufficient history: need at least 35 trading days for S16.")

    last_idx = n - 1
    last_close = num(data[last_idx].close, "close[last]")
    base10_close = num(data[last_idx - 10].close, "close[t-10]")
    if base10_close <= 0:
        raise ValueError("Invalid base close[t-10] value.")

    trs = calc_tr_series(data)
    atr22 = sma(trs, 22)
    if len(atr22) < 13:
        raise ValueError("Too few ATR(22) values for comparison with t-12.")

    atr_now = num(atr22[-1], "ATR22[now]")
    atr_lag12 = num(atr22[-1 - 12], "ATR22[t-12]")

    vol_spike = atr_now > 1.5 * atr_lag12

    ret10 = last_close / base10_close - 1
    big_drop = ret10 < -0.15

    return vol_spike and big_drop


def s17(ohlcv, buy_date, buy_price):
    data = sorted(ohlcv, key=lambda x: to_ts(x.date))
    n = len(data)

    if n < 150:
        raise ValueError("Insufficient history: need at least 150 days for S17.")

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

    if days_since_buy < 150:
        return False

    window150 = data[-150:]
    high150 = max(num(d.high, "high") for d in window150)
    low150 = min(num(d.low, "low") for d in window150)
    if not np.isfinite(high150) or not np.isfinite(low150) or high150 <= low150:
        raise ValueError("Invalid 150-day High/Low range.")

    wide_range = high150 > 1.6 * low150

    if not wide_range:
        return False

    last_close = num(data[last_idx].close, "close")
    near_bottom = last_close < 1.3 * low150

    return near_bottom


def runAllSellConditions(ohlcv, spy_data, buy_date, buy_price, stop_loss, trade_date):
    # спочатку рахуємо S5
    s5_exit, new_stop = s5(ohlcv, buy_date, buy_price, stop_loss)

    conditions = {
        "S1": exit_by_stop_loss(ohlcv, stop_loss),
        "S4": s4(ohlcv, buy_date, buy_price),
        "S5": s5_exit,
        "S6": s6(ohlcv, buy_date, buy_price),
        "S7": s7(ohlcv, buy_date, buy_price),
        "S8": s8(ohlcv, buy_date, buy_price),
        "S9": s9(trade_date, ohlcv, spy_data),
        "S10": s10(ohlcv, buy_date, buy_price),
        "S11": s11(ohlcv, buy_date, buy_price),
        "S12": s12(ohlcv, buy_date, buy_price),
        "S13": s13(ohlcv, buy_date, buy_price),
        "S14": s14(ohlcv, spy_data, buy_date, buy_price),
        "S15": s15(ohlcv, buy_date, buy_price),
        "S16": s16(ohlcv, buy_date, buy_price),
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
            raise ValueError(f"Field {name} must be a number.")
        return n
    except (ValueError, TypeError):
        raise ValueError(f"Field {name} must be a number.")


def wilder_atr(trs, period):
    if len(trs) < period:
        return []

    atr = [None] * len(trs)
    # перше значення – це проста середня TR за весь період
    atr[period - 1] = sum(trs[:period]) / period

    # далі йде рекурсивна формула Вайлдера
    for i in range(period, len(trs)):
        atr[i] = (atr[i - 1] * (period - 1) + trs[i]) / period

    return atr
