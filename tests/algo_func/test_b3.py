import numpy as np
import pytest
import numpy as np

from app.workers.algo_func.buy_signals import OHLCV, checkB3


def _mk(day, o, h, l, c, v=1000):
    return OHLCV(date=f"2024-02-{day:02d}", open=o, high=h, low=l, close=c, volume=v)


def _gen_ohlcv_from_closes(closes):
    data = []
    for i, c in enumerate(closes, start=1):
    
        low = c * 0.995 if c > 0 else c - 0.5
        high = c * 1.005 if c > 0 else c + 0.5
        open_ = (low + high) / 2.0
        data.append(_mk(i, open_, high, low, c))
    return data

def test_b3_detects_decreasing_bbw_sma_slope_true():
    n = 160
    x = np.arange(n)

    trend = 50 + 0.05 * x

    amp = np.linspace(3.0, 0.2, n)
    noise = amp * np.sin(2 * np.pi * x / 10.0)

    closes = (trend + noise).tolist()

    ohlcv = _gen_ohlcv_from_closes(closes)

    
    assert checkB3(ohlcv) is True

def test_b3_returns_false_when_insufficient_data():
    closes = [10 + i * 0.1 for i in range(120)]
    ohlcv = _gen_ohlcv_from_closes(closes)
    assert checkB3(ohlcv) is False

def test_b3_increasing_volatility_slope_non_negative():

    n = 160
    x = np.arange(n)

    trend = 50 + 0.05 * x
    amp = np.linspace(0.2, 3.0, n)
    noise = amp * np.sin(2 * np.pi * x / 10.0)

    closes = (trend + noise).tolist()
    ohlcv = _gen_ohlcv_from_closes(closes)

    assert checkB3(ohlcv) is False

def test_B3_rule():
    np.random.seed(42)
    days = 160
    x = np.arange(days)
    base = 100 + 0.05 * x
    amp = np.linspace(3.0, 0.2, days)
    noise = amp * np.sin(2 * np.pi * x / 10.0)
    closes = (base + noise).tolist()

    ohlcv = _gen_ohlcv_from_closes(closes)

    assert checkB3(ohlcv) is True