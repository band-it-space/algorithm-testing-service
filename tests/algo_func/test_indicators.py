import math
import pytest

from app.workers.algo_func.buy_signals import (
    sma,
    bollinger_bands,
    atr,
    wilder_atr,
    linear_regression_slope,
    average,
    mean,
)


def test_sma_basic_and_bounds():
    # 1. Basic example — standard 3-period SMA
    assert sma([1, 2, 3, 4, 5], 3) == [2.0, 3.0, 4.0]

    # 2. Not enough data points (n > len(data)) — should return an empty list
    assert sma([1, 2], 3) == []

    # 3. Constant series — SMA should remain constant
    assert sma([10, 10, 10, 10], 2) == [10.0, 10.0, 10.0]

    # 4. Window size = 1 — output should match the input values
    assert sma([1, 2, 3, 4], 1) == [1, 2, 3, 4]

    # 5. Window size = length of data — only one average value
    assert sma([1, 2, 3, 4], 4) == [2.5]

    # 6. Empty input series — should return an empty list
    assert sma([], 3) == []

    # 7. Float data — should handle decimal values correctly
    assert sma([1.5, 2.5, 3.5], 2) == [2.0, 3.0]

    # 8. Large dataset — check output length and last average value
    data = list(range(1000))
    res = sma(data, 50)
    assert len(res) == len(data) - 50 + 1
    assert abs(res[-1] - 974.5) < 1e-6

    # 9. Ensure all results are floats
    res = sma([1, 2, 3, 4, 5], 3)
    assert all(isinstance(x, float) for x in res)

def test_atr_bounds_and_monotonic_example():
    # bounds: not enough data (requires period+1 highs at minimum)
    assert atr([1, 2], [0.5, 1.5], [0.8, 1.2], 14) == []
    # construct a simple linearly increasing channel
    highs = [i + 1.0 for i in range(30)]
    lows = [i * 1.0 for i in range(30)]
    closes = [i + 0.5 for i in range(30)]
    vals = atr(highs, lows, closes, 14)
    # first ATR list element is the average of first 14 TRs, then rolling SMA
    assert len(vals) == (30 - 1) - 14 + 1
    assert all(v > 0 for v in vals)

def test_wilder_atr_bounds_and_values():
    # not enough data
    assert wilder_atr([1, 2], [0.5, 1.5], [0.8, 1.2], 14) == []
    highs = [i + 1.0 for i in range(30)]
    lows = [i * 1.0 for i in range(30)]
    closes = [i + 0.5 for i in range(30)]
    vals = wilder_atr(highs, lows, closes, 14)
    # first value equals SMA of first 'period' TRs; subsequent follow Wilder smoothing
    assert len(vals) == (30 - 1) - 14 + 1
    assert all(v > 0 for v in vals)
    # Wilder ATR should be smooth (no erratic negatives or NaNs)
    assert not any(math.isnan(v) or math.isinf(v) for v in vals)

def test_linear_regression_slope_sign_and_bounds():
    # bounds
    assert linear_regression_slope([]) == 0.0
    assert linear_regression_slope([10]) == 0.0
    # increasing
    assert linear_regression_slope([1, 2, 3, 4, 5]) > 0
    # decreasing
    assert linear_regression_slope([5, 4, 3, 2, 1]) < 0
    # flat
    assert linear_regression_slope([7, 7, 7, 7]) == pytest.approx(0.0)

def test_average_and_mean_bounds_and_values():
    assert average([]) == 0.0
    assert mean([]) == 0.0
    assert average([1, 2, 3, 4]) == 2.5
    assert mean([1, 2, 3, 4]) == 2.5

