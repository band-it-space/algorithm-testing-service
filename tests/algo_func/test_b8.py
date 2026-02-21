import pytest

from app.workers.algo_func.types import OHLCV
from app.workers.algo_func.buy_signals import checkB8


def _mk(day, o, h, l, c, v=1000):
    return OHLCV(date=f"2024-03-{day:02d}", open=o, high=h, low=l, close=c, volume=v)


def _gen_series_with_lows(lows):
    data = []
    for i, lo in enumerate(lows, start=1):
        low = float(lo)
        high = low + 2.0
        close = low + 1.0
        open_ = low + 0.8
        data.append(_mk(i, open_, high, low, close))
    return data


def test_b8_true_when_recent_46_low_above_past_min():
    past_224_lows = [12 + (i % 5) for i in range(224)]
    past_224_lows[37] = 10.0 

    recent_46_lows = [16.0 + (i % 3) * 0.2 for i in range(46)]  # усі > 15

    lows = past_224_lows + recent_46_lows
    ohlcv = _gen_series_with_lows(lows)

    assert len(ohlcv) == 270
    assert checkB8(ohlcv) is True


def test_b8_false_when_recent_46_contains_new_lower_low():
    past_224_lows = [12 + (i % 5) for i in range(224)]
    past_224_lows[100] = 10.0

    recent_46_lows = [16.0 + (i % 3) * 0.2 for i in range(45)] + [9.5]

    lows = past_224_lows + recent_46_lows
    ohlcv = _gen_series_with_lows(lows)

    assert len(ohlcv) == 270
    assert checkB8(ohlcv) is False


def test_b8_false_when_not_enough_bars():
    lows = [15.0 for _ in range(200)]
    ohlcv = _gen_series_with_lows(lows)
    assert len(ohlcv) == 200
    assert checkB8(ohlcv) is False

