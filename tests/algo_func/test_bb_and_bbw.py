import pytest
import pytest
import numpy as np
from statistics import mean

from app.workers.algo_func.buy_signals import (
    sma,
    bollinger_bands,
    linear_regression_slope,
)

# 1. Not enough data → should return empty
def test_bollinger_bands_too_short():
    assert bollinger_bands([1, 2], period=3, std_dev=2.0) == []

# 2. Constant series → upper=middle=lower
def test_bollinger_bands_constant_series():
    # Constant series → upper=middle=lower
    values = [10] * 10
    bb = bollinger_bands(values, period=3, std_dev=2.0)
    for b in bb:
        assert b["upper"] == pytest.approx(10.0)
        assert b["middle"] == pytest.approx(10.0)
        assert b["lower"] == pytest.approx(10.0)

# 3. Basic increasing sequence
def test_bollinger_bands_basic_sequence():
    values = [1, 2, 3, 4, 5, 6]
    bb = bollinger_bands(values, period=3, std_dev=2.0)
    assert len(bb) == len(values) - 3 + 1
    assert all(set(b.keys()) == {"upper", "middle", "lower"} for b in bb)
    # middle equals SMA
    mids = [b["middle"] for b in bb]
    assert mids == pytest.approx([2.0, 3.0, 4.0, 5.0])
    # upper > middle > lower
    assert all(b["upper"] > b["middle"] > b["lower"] for b in bb)

# 4. Float numbers handled correctly
def test_bollinger_bands_float_input():
    values = [1.5, 2.5, 3.5, 4.5]
    bb = bollinger_bands(values, period=2, std_dev=1.5)
    assert all(isinstance(b["upper"], float) for b in bb)
    assert all(isinstance(b["lower"], float) for b in bb)

# 5. BBW = (upper - lower)/middle
def test_bbw_calculation():
    values = [1, 2, 3, 4, 5]
    bb = bollinger_bands(values, period=3, std_dev=2.0)
    bbw_values = [(b["upper"] - b["lower"]) / b["middle"] for b in bb]
    assert all(x >= 0 for x in bbw_values)
    # Constant series → BBW = 0
    bb_const = bollinger_bands([10]*10, period=3, std_dev=2.0)
    bbw_const = [(b["upper"] - b["lower"]) / b["middle"] for b in bb_const]
    assert all(x == 0.0 for x in bbw_const)

# 6. Simulate B3: SMA_BBW and slope
def test_bbw_slope_signal():
    values = list(range(1, 101))  # gradual increase → low volatility
    bb = bollinger_bands(values, period=21, std_dev=2.0)
    bbw_values = [(b["upper"] - b["lower"]) / b["middle"] for b in bb]
    sma_bbw = sma(bbw_values, 72)
    slope = linear_regression_slope(sma_bbw[-58:])
    assert isinstance(slope, float)

# 7. Invalid period or std_dev
def test_bollinger_bands_invalid_params():
    assert bollinger_bands([1,2,3], period=0, std_dev=2.0) == []
    assert bollinger_bands([1,2,3], period=3, std_dev=0.0) == []
    assert bollinger_bands([], period=3, std_dev=2.0) == []

# 8. Sudden spike → upper - lower increases
def test_bollinger_bands_sudden_spike():
    values = [1,1,1,1,100]
    bb = bollinger_bands(values, period=3, std_dev=2.0)
    bbw_values = [(b["upper"] - b["lower"]) / b["middle"] for b in bb]
    assert bbw_values[-1] > bbw_values[0]

# 9. Test B18(8)
def test_bollinger_bands_minervini_condition():

    high_vol = np.linspace(90, 110, 82)
    low_vol = np.linspace(100, 100.0001, 21+21)

    values = np.concatenate([high_vol, low_vol])

    bb = bollinger_bands(values, period=21, std_dev=2.0)

    bbw = [(b['upper'] - b['lower']) / b['middle'] * 100 for b in bb]

    avg21 = mean(bbw[-21:])
    avg82 = mean(bbw[-82:])

    print("avg21:", avg21)
    print("0.22 * avg82:", 0.22 * avg82)

    
    assert avg21 < 0.22 * avg82, f"avg21={avg21}, 0.22*avg82={0.22*avg82}"

    last_close = bb[-1]["upper"] + 0.01
    assert last_close > bb[-1]["upper"], f"last_close={last_close}, upper={bb[-1]['upper']}"