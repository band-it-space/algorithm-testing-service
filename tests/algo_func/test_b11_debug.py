"""
Test B11 logic to debug the issue with extra signals
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from app.workers.algo_func.buy_king import checkB11_US
from app.workers.algo_func.helpers import lewis_atr
from app.workers.algo_func.types import OHLCV

def test_b11_manual_calculation():
    """
    Test B11 with manual ATR calculation to find the issue
    """
    print("\n=== B11 Manual Debug Test ===\n")
    
    # Create test data: 250 days with varying volatility
    # Last 215 days will be used for max ATR calculation
    dates = [f"2024-{(i//30)+1:02d}-{(i%30)+1:02d}" for i in range(250)]
    
    # Scenario: High ATR in past, current ATR moderate
    # Days 0-100: Low volatility (TR=2)
    # Days 101-220: High volatility (TR=10) - THIS WILL BE IN THE 215-DAY WINDOW
    # Days 221-249: Current period, moderate volatility (TR=3)
    
    data = []
    base_price = 100.0
    
    for i in range(250):
        if i < 100:
            tr = 2.0  # Low volatility
        elif i < 220:
            tr = 10.0  # High volatility - should be in lookback window
        else:
            tr = 3.0  # Current period
        
        high = base_price + tr/2
        low = base_price - tr/2
        close = base_price
        
        data.append(OHLCV(
            date=dates[i],
            open=base_price,
            high=high,
            low=low,
            close=close,
            volume=1000
        ))
    
    # Calculate ATR manually
    highs = [bar.high for bar in data]
    lows = [bar.low for bar in data]
    closes = [bar.close for bar in data]
    
    atr_values = lewis_atr(highs, lows, closes, 22)
    
    current_atr = atr_values[-1]
    
    # Method 1: Exclude current day (original logic)
    prev_window_exclude = atr_values[-216:-1]
    prev_window_exclude = [x for x in prev_window_exclude if x is not None]
    max_atr_exclude = max(prev_window_exclude) if prev_window_exclude else 0
    
    # Method 2: Include current day
    prev_window_include = atr_values[-215:]
    prev_window_include = [x for x in prev_window_include if x is not None]
    max_atr_include = max(prev_window_include) if prev_window_include else 0
    
    threshold_exclude = max_atr_exclude * 0.67
    threshold_include = max_atr_include * 0.67
    
    print(f"Current ATR (day 249): {current_atr:.4f}")
    print(f"\nMethod 1 (EXCLUDE current day from max search):")
    print(f"  Window: atr_values[-216:-1] (days 34-248)")
    print(f"  Max ATR: {max_atr_exclude:.4f}")
    print(f"  Threshold (67%): {threshold_exclude:.4f}")
    print(f"  Current > Threshold? {current_atr > threshold_exclude}")
    print(f"  Result: {not (current_atr > threshold_exclude)} (True = allow buy)")
    
    print(f"\nMethod 2 (INCLUDE current day in max search):")
    print(f"  Window: atr_values[-215:] (days 35-249)")
    print(f"  Max ATR: {max_atr_include:.4f}")
    print(f"  Threshold (67%): {threshold_include:.4f}")
    print(f"  Current > Threshold? {current_atr > threshold_include}")
    print(f"  Result: {not (current_atr > threshold_include)} (True = allow buy)")
    
    # Show ATR values in the critical range
    print(f"\nATR values for last 10 days:")
    for i in range(10):
        idx = -10 + i
        print(f"  Day {250+idx}: ATR = {atr_values[idx]:.4f}")
    
    # Test the function
    result = checkB11_US(data)
    print(f"\ncheckB11_US() returned: {result}")
    
    print("\n" + "="*60)
    print("EXPECTED BEHAVIOR:")
    print("MC code: if _lewis_ATR(22) > highest(_lewis_ATR(22), 215)[1] * 67/100")
    print("         then cond17_highest_ATR = false")
    print("\nThe [1] offset means: 'max of last 215 bars, calculated 1 bar ago'")
    print("This EXCLUDES the current bar from the max calculation")
    print("="*60)

if __name__ == "__main__":
    test_b11_manual_calculation()
