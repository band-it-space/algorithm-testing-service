# US King Algorithm Implementation Guide

## Overview

This document provides a comprehensive guide to the US King trading algorithm implementation. It describes the project structure, signal implementations, and key differences from the HK Algo.

## Project Structure

```
algorithm-testing-service/
├── app/
│   └── workers/
│       └── algo_func/
│           ├── buy_signals.py      # Shared buy signals (B10, B12, B13)
│           ├── buy_king.py         # US King-specific buy signals
│           ├── sell_signals.py     # Shared sell signals (S10-S17)
│           ├── sell_king.py        # US King-specific sell signals
│           ├── helpers.py          # Utility functions (sma, lewis_atr, etc.)
│           └── types.py            # Data types (OHLCV)
├── docs/
│   ├── HK_Algo/
│   │   ├── hk_algo_terms.md       # HK Algo specifications
│   │   └── mc_hk.txt              # MultiCharts HK code
│   └── US_King/
│       ├── us_king_terms.md       # US King specifications
│       ├── mc_us_king.els         # MultiCharts US King code
│       ├── energy_signals.md      # Energy level calculations
│       └── implementation_guide.md # This file
└── tests/
    └── algo_func/
        ├── test_b*.py             # Buy signal tests
        └── test_sell_signals.py   # Sell signal tests
```

## Buy Signal Implementation

### Buy Rule Formula

```
Buy = ([B1 AND B8] OR [B18]) AND B9 AND B10 AND B11 AND B12 AND B13 AND B20 AND B21 AND B22
```

### Signal Categories

#### 1. Core Breakout Signals (B1, B8)

- **B1**: Bollinger Band breakout with position validation
    - Location: `buy_king.py::checkB1_US()`
    - Bollinger Band: (22, 0.89)
    - Deviation check: 50MA, 25% max
    - Close ratio: 0.65 (upper range of day)

- **B8**: Higher low pattern
    - Location: `buy_king.py::checkB8_US()`
    - Recent period: 85 days
    - Lookback: 150 days
    - Logic: 85D low > T-86 to T-150 low

#### 2. VCP Pattern (B18)

- **B18**: Mark Minervini's Volatility Contraction Pattern
    - Location: `buy_king.py::checkB18_US()`
    - Four conditions (all must be TRUE):
        1. NearHigh: Price below 252D high but above 60%
        2. VolDecreasing: 50D volume SMA has negative slope (50 periods)
        3. IsPivot: 5D range < 10% AND 5D high at start
        4. VolDryUp: Each of last 5 days volume < its 50D MA

#### 3. Risk Management Filters (B9-B13)

- **B9**: Weak price action filter
    - Location: `buy_king.py::checkB9_US()`
    - Lookback: 105 days
    - Cancel if: close < midpoint AND high earlier than low

- **B10**: Recent low filter (SHARED with HK)
    - Location: `buy_signals.py::checkB10()`
    - Cancel if 250D low within 68 days
    - **Same parameters for both HK and US**

- **B11**: High volatility filter
    - Location: `buy_king.py::checkB11_US()`
    - Cancel if: ATR(22) > 67% of max ATR(22) in 215 days
    - **Different from HK**: HK uses 126 days, 87%

- **B12**: Overheated stock filter (SHARED with HK)
    - Location: `buy_signals.py::checkB12()`
    - Cancel if: 150MA grew 16% in 50 days AND high > 20% above 150MA
    - **Same parameters for both HK and US**

- **B13**: Index underperformance filter (SHARED with HK)
    - Location: `buy_signals.py::checkB13()`
    - Cancel if: stock underperforms index in BOTH periods
    - **US parameters**: 19-day AND 100-day (HK: 19 and 60)
    - **Index**: SPY for US, HSI for HK
    - **Rounding**: Round ratios to 1 decimal place

#### 4. Volume and Range Filters (B20-B22)

- **B20**: Volume accumulation pattern
    - Location: `buy_king.py::checkB20_US()`
    - Up volume > down volume in 20 days
    - Highest volume is 1st or 2nd highest

- **B21**: Range expansion check
    - Location: `buy_king.py::checkB21_US()`
    - R3 (3M range) > 1.09 \* R1 (1M range)
    - Price < 4.2% below 3M high

- **B22**: Hard stop validation
    - Location: `buy_king.py::checkB22_US()`
    - Validates hard stop can be found
    - Lookback: 41 days
    - ATR multiplier: 2.45

### Signal Usage

```python
from app.workers.algo_func.buy_king import runAllBuyConditions_US, isBuy_US

# Calculate all buy signals
signals = runAllBuyConditions_US(
    stock_prices=stock_ohlcv,  # List[OHLCV]
    spy_prices=spy_ohlcv,       # List[OHLCV] for B13
    targetDate="2023-04-18"     # str
)

# Check if buy signal is valid
is_buy = isBuy_US(signals)

# Signals dictionary contains:
# {
#     'B1': bool,
#     'B8': bool,
#     'B9': bool,
#     'B10': bool,
#     'B11': bool,
#     'B12': bool,
#     'B13': bool,
#     'B18': bool,
#     'B20': bool,
#     'B21': bool,
#     'B22': bool,
#     'stopLoss': float  # S1 stop loss level
# }
```

## Sell Signal Implementation

### Sell Rule Formula

```
Sell = S1 OR S4 OR S5 OR S6 OR S7 OR S8 OR S9 OR
       S10 OR S11 OR S12 OR S13 OR S14 OR S15 OR
       S16 OR S17 OR S18 OR S19 OR S20
```

### Signal Categories

#### 1. Stop Loss Signals (S1, S5, S19)

- **S1**: Initial ATR-based stop loss
    - Location: `sell_king.py::checkS1_US()`
    - Formula: close - 3.4 \* ATR(22)
    - Adjusted: 7.2% if risk > 20%

- **S5**: Trailing stop (after 50 days)
    - Location: `sell_king.py::checkS5_US()`
    - Initial: entry + 0.7 \* ATR(20)
    - Increment: +0.7 \* ATR(10) every 30 days

- **S19**: Hard stop from high volume day
    - Location: `sell_king.py::checkS19_US()`
    - Based on highest volume UP day in 41 days
    - Stop: low - 2.45 \* ATR(10)

#### 2. Performance-Based Exits (S4, S6, S13, S14, S18)

- **S4**: Weak performance (after 50 days)
    - Location: `sell_king.py::checkS4_US()`
    - Exit if: <45% days above 50MA AND gain < 7%

- **S6**: Stalled momentum (after 50 days)
    - Location: `sell_king.py::checkS6_US()`
    - Exit if: no 90D high in last 76 days

- **S13**: Close below 80-day low (after 238 days)
    - Location: `sell_king.py::checkS13_US()`

- **S14**: Index underperformance (after 300 days)
    - Location: `sell_king.py::checkS14_US()`
    - Underperforms SPY for 65, 130, and 195 days

- **S18**: Close below 120-day low (first 20 days only)
    - Location: `sell_king.py::checkS18_US()`

#### 3. Volatility-Based Exits (S7, S8, S20)

- **S7**: Large bearish candles
    - Location: `sell_king.py::checkS7_US()`
    - Exit if: (open-close) > 2 \* ATR(22) for 2 consecutive days

- **S8**: Extreme volatility (after day 2)
    - Location: `sell_king.py::checkS8_US()`
    - Condition 1: ATR(100) > 74% of max ATR(22) in 126 days
    - Condition 2: 3+ out of 5 days have large dark candles

- **S20**: Rapid price drop
    - Location: `sell_king.py::checkS20_US()`
    - Exit if: drops 5.4 \* avgATR(100,20,5) in 5 days

#### 4. Energy-Based Exit (S9)

- **S9**: Low energy level
    - Location: `sell_king.py::checkS9_US()`
    - Exit if: 16-day avg energy < 0.22
    - Energy based on E1-E5 signals

#### 5. Fibonacci-Based Exits (S10-S12, S15-S17) - SHARED with HK

- **S10**: Drawdown + high volatility
- **S11**: Below Fibo 0.382 (after 300 days)
- **S12**: Below Fibo 0.236 (after 240 days)
- **S15**: Rapid decline (>25% in 4 days)
- **S16**: ATR spike + decline (>14% in 10 days)
- **S17**: Loss of range (after 150 days)

### Signal Usage

```python
from app.workers.algo_func.sell_king import runAllSellConditions_US, isSell_US

# Calculate all sell signals
sell_signals = runAllSellConditions_US(
    stock_prices=stock_ohlcv,      # List[OHLCV] - full history
    spy_data=spy_ohlcv,             # List[OHLCV] - for S14
    entry_index=100,                # int - index of entry day
    buy_price=298.54,               # float - entry price
    s1_stop_loss=275.23,            # float - S1 stop level
    s5_stop_loss=280.50,            # float - S5 stop (0 if not initialized)
    energy_signals=energy_history,  # Optional[List[Dict]] - for S9
    current_day_idx=150             # Optional[int] - current position in energy list
)

# Check if sell signal is triggered
should_exit = isSell_US(sell_signals)

# Sell signals dictionary contains:
# {
#     'S1': bool,
#     'S4': bool,
#     'S5': bool,
#     'S5_new_stop': float,  # Updated S5 stop level
#     'S6': bool,
#     'S7': bool,
#     'S8': bool,
#     'S9': bool,
#     'S10': bool,
#     'S11': bool,
#     'S12': bool,
#     'S13': bool,
#     'S14': bool,
#     'S15': bool,
#     'S16': bool,
#     'S17': bool,
#     'S18': bool,
#     'S19': bool,
#     'S20': bool
# }
```

## Key Differences: HK Algo vs US King

### Buy Signals

| Signal  | HK Algo                      | US King                       | Shared? |
| ------- | ---------------------------- | ----------------------------- | ------- |
| B1      | 20D high + BB(51,1.9)        | BB(22,0.89) + 50MA check      | ❌      |
| B3      | BBW slope check              | N/A (not used)                | ❌      |
| B8      | 46D low > T-46 to T-270 low  | 85D low > T-86 to T-150 low   | ❌      |
| B9      | 50D midpoint check           | 105D midpoint check           | ❌      |
| B10     | 250D low within 68 days      | Same                          | ✅      |
| B11     | ATR > 87% of 126D max        | ATR > 67% of 215D max         | ❌      |
| B12     | 150MA growth + deviation     | Same                          | ✅      |
| B13     | Underperforms HSI (19D, 60D) | Underperforms SPY (19D, 100D) | ⚠️      |
| B18     | BBW contraction              | Minervini VCP pattern         | ❌      |
| B20-B22 | N/A                          | Volume/range filters          | ❌      |

### Sell Signals

| Signal  | HK Algo                              | US King                            | Shared? |
| ------- | ------------------------------------ | ---------------------------------- | ------- |
| S1      | 3.7 \* ATR(22), 14.25%/9.5% adjusted | 3.4 \* ATR(22), 7.2% adjusted      | ❌      |
| S4      | Day 50 only, 150MA, 50%, 5% gain     | Daily after 50, 50MA, 45%, 7% gain | ❌      |
| S5      | Day 45, every 25D, 0.62 factor       | Day 50, every 30D, 0.7 factor      | ❌      |
| S6      | 70D high in 58 days                  | 90D high in 76 days                | ❌      |
| S7      | Same                                 | Same                               | ✅      |
| S8      | Similar logic, different params      | ATR(100) > 74% of max ATR(22)      | ⚠️      |
| S9      | Energy < 0.22 (16D)                  | Same                               | ✅      |
| S10-S17 | Shared signals                       | Same                               | ✅      |
| S18-S20 | N/A                                  | US King specific                   | ❌      |

## Implementation Details

### ATR Calculation

The project uses Lewis ATR (Wilder's smoothing method):

```python
from app.workers.algo_func.helpers import lewis_atr

atr_values = lewis_atr(
    highs=[bar.high for bar in ohlcv],
    lows=[bar.low for bar in ohlcv],
    closes=[bar.close for bar in ohlcv],
    period=22
)
```

### MultiCharts Index Translation

**CRITICAL**: Python uses negative indexing, MC uses offset indexing:

```
MultiCharts:        Python:
close[0]     →     closes[-1]        (current/today)
close[1]     →     closes[-2]        (1 day ago)
close[19]    →     closes[-20]       (19 days ago)
close[N]     →     closes[-(N+1)]    (N days ago)
```

**Formula**: `MC close[N]` = `Python array[-(N+1)]`

This is why B13 uses `stock[-(input_B13_XX + 1)]` for `close[input_B13_XX]`.

### B13 Rounding Logic

B13 rounds performance ratios to **1 decimal place** to match MultiCharts precision:

```python
stock_ratio_x = round(s_today / s_x_ago, 1)  # e.g., 1.027736 → 1.0
index_ratio_x = round(i_today / i_x_ago, 1)  # e.g., 1.038354 → 1.0
```

This prevents false negatives due to tiny performance differences.

### Data Requirements

Minimum data points needed for US King:

**Buy Signals:**

- B1: 50 bars (BB + SMA checks)
- B8: 150 bars
- B9: 105 bars
- B10: 250 bars
- B11: 237 bars (215 + 22 for ATR)
- B12: 200 bars (150 + 50)
- B13: max(19, 100) + 1 = 101 bars
- B18: 302 bars (252 + 50 for volume MA)
- B20-B22: 41-60 bars

**Recommended minimum**: 302 bars (for B18)

**Sell Signals:**

- Most signals: 50-300 bars depending on activation
- S8: 226 bars (100 ATR + 126 lookback)
- S14: 495 bars (300 activation + 195 lookback)

### Testing

Tests are located in `tests/algo_func/`:

```bash
# Test specific buy signal
pytest tests/algo_func/test_b1.py -v

# Test all buy signals
pytest tests/algo_func/ -k "test_b" -v

# Test sell signals
pytest tests/algo_func/test_sell_signals.py -v
```

## Common Pitfalls

1. **Index Mismatch**: Always verify MC index translation (use `+1` for lookback)

2. **Data Sorting**: Ensure OHLCV data is sorted by date ascending before processing

3. **B13 Index Alignment**: Stock and SPY data must have aligned dates

4. **Volume Data**: B18 requires volume; will fail if volume is None

5. **Entry Index**: For sell signals, entry_index must be valid position in stock_prices array

6. **S5 State**: S5 stop must be persisted between days (not recalculated from scratch)

7. **ATR Warmup**: ATR calculations need warmup period (e.g., ATR(22) needs 23+ bars)

## Reference Files

- **Specifications**: `docs/US_King/us_king_terms.md`
- **Original MultiCharts Code**: `docs/US_King/mc_us_king.els`
- **Energy Signals**: `docs/US_King/energy_signals.md`
- **HK Algo Specs**: `docs/HK_Algo/hk_algo_terms.md`
- **HK MultiCharts Code**: `docs/HK_Algo/mc_hk.txt`

## Support

For questions about signal implementation:

1. Check the docstrings in `buy_king.py` and `sell_king.py`
2. Refer to `us_king_terms.md` for parameter documentation
3. Compare with MultiCharts code in `mc_us_king.els`
4. Review test cases in `tests/algo_func/`

---

Last Updated: February 24, 2026
