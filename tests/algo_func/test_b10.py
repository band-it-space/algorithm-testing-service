import pytest

from app.workers.algo_func.buy_signals import OHLCV, checkB10


def _mk(day, o, h, l, c, v=1000):
    return OHLCV(date=f"2024-05-{day:02d}", open=o, high=h, low=l, close=c, volume=v)


def _gen_series_with_lows(lows):
    data = []
    for i, lo in enumerate(lows, start=1):
        low = float(lo)
        high = low + 2.0
        close = low + 1.0
        open_ = low + 0.8
        data.append(_mk(i, open_, high, low, close))
    return data


def test_b10_true_when_days_since_min_low_is_68_or_more():
    past_50 = [50.0] * 50
    last_250 = [10.0] + [20.0 for _ in range(249)]
    lows = past_50 + last_250
    ohlcv = _gen_series_with_lows(lows)

    assert len(ohlcv) == 300
    assert checkB10(ohlcv) is True  # 249 >= 68


def test_b10_false_when_days_since_min_low_less_than_68():
    prefix = [20.0 for _ in range(250 - 10)]
    last_10 = [15.0 for _ in range(9)] + [10.0]  
    lows = prefix + last_10
    ohlcv = _gen_series_with_lows(lows)

    assert len(ohlcv) == 250
    assert checkB10(ohlcv) is False


def test_b10_false_when_not_enough_bars():
    lows = [20.0 for _ in range(200)]
    ohlcv = _gen_series_with_lows(lows)
    assert len(ohlcv) == 200
    assert checkB10(ohlcv) is False

