import pytest

from app.workers.algo_func.types import OHLCV
from app.workers.algo_func.buy_signals import checkB9


def _mk(day, o, h, l, c, v=1000):
    return OHLCV(date=f"2024-04-{day:02d}", open=o, high=h, low=l, close=c, volume=v)


def _gen_flat(last_n: int, high: float, low: float, close: float):
    data = []
    for i in range(1, last_n + 1):
        data.append(_mk(i, (high + low) / 2, high, low, close))
    return data


def test_b9_false_when_last_close_below_mid_and_high_before_low():
    data = []

    data += _gen_flat(20, high=50.0, low=45.0, close=47.0)

    data.append(_mk(21, 60.0, 60.0, 45.0, 46.0))

    data += _gen_flat(18, high=52.0, low=46.0, close=47.0)  # bars 22..39
    data.append(_mk(40, 50.0, 51.0, 30.0, 40.0))  # minLow = 30.0

    data += _gen_flat(9, high=52.0, low=46.0, close=47.0)  # bars 41..49

    data.append(_mk(50, 44.0, 50.0, 40.0, 44.0))

    assert len(data) == 50
    assert checkB9(data) is False


def test_b9_true_when_last_close_above_mid_even_if_high_before_low():
    data = []
    data += _gen_flat(20, high=50.0, low=45.0, close=47.0)
    data.append(_mk(21, 60.0, 60.0, 45.0, 46.0))  # maxHigh раніше
    data += _gen_flat(18, high=52.0, low=46.0, close=47.0)  # 22..39
    data.append(_mk(40, 50.0, 51.0, 30.0, 40.0))  # minLow пізніше
    data += _gen_flat(9, high=52.0, low=46.0, close=47.0)   # 41..49

    data.append(_mk(50, 46.0, 50.0, 40.0, 46.0))

    assert len(data) == 50
    assert checkB9(data) is True


def test_b9_true_when_low_before_high_even_if_close_below_mid():
    data = []
    data += _gen_flat(20, high=50.0, low=45.0, close=47.0)
    data.append(_mk(21, 50.0, 51.0, 30.0, 40.0)) 
    data += _gen_flat(18, high=52.0, low=46.0, close=47.0)  
    data.append(_mk(40, 60.0, 60.0, 45.0, 46.0)) 
    data += _gen_flat(9, high=52.0, low=46.0, close=44.0)   

    
    data.append(_mk(50, 44.0, 50.0, 40.0, 44.0))

    assert len(data) == 50
   
    assert checkB9(data) is True


def test_b9_false_when_not_enough_bars():
    data = _gen_flat(49, high=50.0, low=45.0, close=47.0)
    assert len(data) == 49
    assert checkB9(data) is False

