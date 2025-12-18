import pytest
import numpy as np
from app.workers.algo_func.buy_signals import OHLCV, checkB1


def _mk(day, o, h, l, c, v=1000):
    return OHLCV(date=f"2024-01-{day:02d}", open=o, high=h, low=l, close=c, volume=v)


def test_b1_new_20day_high_and_close_in_upper_range_true():
    data = []
    for i in range(1, 51):
        high = 9 + i  # 10..59
        low = high - 2
        close = low + 1.2
        open_ = low + 1.0
        data.append(_mk(i, open_, high, low, close))

    prev20_high = max([b.high for b in data[-20:]])
    new_high = prev20_high + 1.0
    day_low = new_high - 5.0
    upper_threshold = day_low + 0.65 * (new_high - day_low)
    close = upper_threshold + 0.1
    open_ = day_low + 1.0
    data.append(_mk(51, open_, new_high, day_low, close))

    assert checkB1(data) is True


def test_b1_false_when_no_new_high_and_close_not_in_upper_range():
    data = []
    for i in range(1, 51):
        high = 50.0
        low = 45.0
        close = 46.0  # нижня частина діапазону
        open_ = 45.5
        data.append(_mk(i, open_, high, low, close))

    # День 51: high не перевищує попередні 20 днів, і закриття низько
    data.append(_mk(51, 45.5, 50.0, 45.0, 45.2))

    assert checkB1(data) is False

def test_B1_rule():
    # 51 попередній день: монотонне зростання high, стабільний діапазон
    data = []
    for i in range(1, 52):  # 51 бар
        high = 9 + i           # 10..60
        low = high - 3.0
        close = low + 1.5
        open_ = low + 1.0
        data.append(_mk(i, open_, high, low, close))

    # День 52: новий 20-денний максимум та закриття у верхніх 35% діапазону
    prev20_high = max([b.high for b in data[-20:]])
    new_high = prev20_high + 1.0
    day_low = new_high - 5.0
    close = day_low + 0.7 * (new_high - day_low)  # > 0.65*range
    open_ = day_low + 1.0
    data.append(_mk(52, open_, new_high, day_low, close))

    # Довжини достатньо для BB(51) та SMA(51): bb матиме >=2 елементи
    assert checkB1(data) is True