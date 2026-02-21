# Energy Signals (E1-E5) in US King Algorithm

## Overview

Energy signals are a set of 5 indicators (E1-E5) used to assess the "energy" or strength of a stock's trend. Each signal returns `"1"` (active) or `"0"` (inactive).

**Total Energy (`Energy`)** = E1 + E2 + E3 + E4 + E5  
Range: from 0 (low energy) to 5 (high energy)

## Usage

### S9 Stop Rule

Energy signals are used in the **S9** exit rule:

```
IF average(Energy, 16) < 0.22, THEN EXIT
```

If the average energy over the last 16 days is less than 0.22 (4.4% of maximum), the algorithm exits the position.

---

## Detailed Description of Each Signal

### E1: New High + Close Position

**Activation Condition:**

```python
high[today] > highest(high, 20)[yesterday]  # New high over 20 days
AND
close > low + 0.65 * (high - low)  # Close in upper 65% of day's range
```

**MultiCharts equivalent:**

```easylanguage
E1 = iff(cond01a_NewHigh and cond01b_ClosevsHighLow, 1, 0)
```

**What it checks:**

- Stock reached a new high (upward momentum)
- Closing price shows strength (not a pullback from the high)

---

### E2: StochRSI

**Activation Condition:**

```python
StochRSI(10) > 0.5
```

**Calculation:**

1. Calculate RSI(10) with Wilder's Smoothing
2. Apply Stochastic to RSI over 10 periods
3. StochRSI = (RSI - min(RSI, 10)) / (max(RSI, 10) - min(RSI, 10))

**MultiCharts equivalent:**

```easylanguage
E2 = iff(_lewis_StochRSI(10) > 0.5, 1, 0)
```

**What it checks:**

- Price momentum in medium/strong range
- Absence of oversold conditions

---

### E3: Price Slope

**Activation Condition:**

```python
SLOPE(Close, 66) > 0
```

**Calculation:**

```python
slope = (close[today] - close[66 days ago]) / 66
```

**MultiCharts equivalent:**

```easylanguage
SLOPE = (close - close[66])/66
E3 = iff(cond06_SLOPE, 1, 0)
```

**What it checks:**

- Medium-term trend is upward
- Positive rate of price change over 66 days

---

### E4: Outperformance vs SPY

**Activation Condition:**

```python
(close / close[33]) > (SPY_close / SPY_close[33])
```

**MultiCharts equivalent:**

```easylanguage
E4 = iff(close/close[33] > close data(2)/close[33] data(2), 1, 0)
```

where `data(2)` = SPY

**What it checks:**

- Stock shows better performance over 33 days than the market (SPY)
- Relative strength of the stock

---

### E5: Position in Range + Momentum

**Activation Condition (all three conditions):**

```python
1. (close - lowest(low, 5)) / (highest(high, 5) - lowest(low, 5)) > 0.5
2. close > close[5]
3. (highest(high, 250) - close) / highest(high, 250) < 0.07
```

**MultiCharts equivalent:**

```easylanguage
E5 = iff(
    (close - lowest(low, 5))/(highest(high, 5) - lowest(low, 5)) > 0.5
    and close - close[5] > 0
    and (highest(high, 250) - close)/highest(high, 250) < 0.07, 1, 0)
```

**What it checks:**

1. Price is in the upper half of the 5-day range
2. Growth over the last 5 days
3. No more than 7% drawdown from the 250-day high

---

## Technical Implementation Details

### Minimum Data Requirements

For correct calculation, a minimum of **66 bars** of historical data is required (the longest period in E3).

### Functions in Code

```python
calculate_E1(high, low, close, idx) -> str  # "1", "0", "N/A"
calculate_E2(close, idx) -> str
calculate_E3(close, idx) -> str
calculate_E4(close, close_spy, sdate, sdate_spy, idx) -> str
calculate_E5(high, low, close, idx) -> str
```

### Period Calculation

The `calculate_energy_signals_for_period()` function calculates E1-E5 for each day:

- Starts **16 days earlier** than the test period (for S9)
- Returns an array with fields:
    - `E1`, `E2`, `E3`, `E4`, `E5` - signal values
    - `energy` - sum of all signals (0-5)
    - `is_test_period` - whether the day is in the test period

---

## Example

```python
# Day with high energy
{
    "date": "2019-03-15",
    "E1": "1",  # New high
    "E2": "1",  # StochRSI > 0.5
    "E3": "1",  # Positive slope
    "E4": "1",  # Better than SPY
    "E5": "1",  # Strong position
    "energy": 5  # Maximum energy
}

# Day with low energy
{
    "date": "2019-06-20",
    "E1": "0",
    "E2": "0",
    "E3": "1",
    "E4": "0",
    "E5": "0",
    "energy": 1  # Low energy
}
```

---

## Verification of Compliance with MultiCharts

The implementation fully corresponds to the original MultiCharts code (US King.els):

| Signal | Python function  | MultiCharts code   | Status       |
| ------ | ---------------- | ------------------ | ------------ |
| E1     | `calculate_E1()` | lines 302-319, 381 | ✅ Identical |
| E2     | `calculate_E2()` | line 381           | ✅ Identical |
| E3     | `calculate_E3()` | lines 331-339, 382 | ✅ Identical |
| E4     | `calculate_E4()` | line 382           | ✅ Identical |
| E5     | `calculate_E5()` | line 383           | ✅ Identical |

---

## Implementation Files

- **Signal calculation:** `app/workers/algo_func/get_code_energy.py`
- **Usage:** `app/workers/us_king_worker.py`
- **Original code:** `docs/US King.els` (lines 377-384, 649-653)
