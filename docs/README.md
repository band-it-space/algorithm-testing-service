# Trading Algorithm Documentation

This directory contains documentation for two trading algorithms: **HK Algo** and **US King**.

## Algorithms

### US King Algorithm

📁 **[US_King/](US_King/)**

American market trading system with emphasis on volatility contraction patterns and momentum.

- **[Quick Start](US_King/README.md)** - Overview and quick reference
- **[Implementation Guide](US_King/implementation_guide.md)** - Detailed developer guide
- **[Algorithm Specifications](US_King/us_king_terms.md)** - Buy/Sell rules
- **[Energy Signals](US_King/energy_signals.md)** - Energy calculations
- **[MultiCharts Code](US_King/mc_us_king.els)** - Original source

**Key Features:**

- VCP (Volatility Contraction Pattern) detection
- 11 buy signals + 16 sell signals
- SPY index comparison
- Volume-based filters

### HK Algo

📁 **[HK_Algo/](HK_Algo/)**

Hong Kong market trading system focused on Bollinger Band width and higher low patterns.

- **[Algorithm Specifications](HK_Algo/hk_algo_terms.md)** - Buy/Sell rules
- **[MultiCharts Code](HK_Algo/mc_hk.txt)** - Original source

**Key Features:**

- BBW (Bollinger Band Width) contraction
- 9 buy signals + 15 sell signals
- HSI index comparison
- Energy-based exits

## Implementation Structure

```
app/workers/algo_func/
├── buy_signals.py       # Shared: B10, B12, B13
├── buy_king.py          # US King buy signals
├── sell_signals.py      # Shared: S10-S17
├── sell_king.py         # US King sell signals
├── helpers.py           # ATR, SMA, utilities
└── types.py             # OHLCV data types
```

## Algorithm Comparison

| Feature             | HK Algo                   | US King                       |
| ------------------- | ------------------------- | ----------------------------- |
| **Market**          | Hong Kong                 | United States                 |
| **Index**           | HSI (2800)                | SPY                           |
| **Buy Signals**     | 9 (B1, B3, B8-B13, B18)   | 11 (B1, B8-B13, B18, B20-B22) |
| **Sell Signals**    | 15 (S1-S17)               | 16 (S1-S20)                   |
| **Primary Pattern** | BBW contraction           | VCP pattern                   |
| **B1 Logic**        | 20D high + BB(51,1.9)     | BB(22,0.89)                   |
| **B8 Lookback**     | 46D/270D                  | 85D/150D                      |
| **B13 Periods**     | 19D, 60D                  | 19D, 100D                     |
| **S1 Stop**         | 3.7x ATR, 14.25% adjusted | 3.4x ATR, 7.2% adjusted       |
| **S5 Activation**   | Day 45, every 25D         | Day 50, every 30D             |

## Shared Signals

### Buy Signals

- **B10**: 250D low filter (cancel if within 68 days)
- **B12**: Overheated filter (150MA growth + deviation)
- **B13**: Index underperformance filter (with rounding)

### Sell Signals

- **S10**: Drawdown + high volatility
- **S11**: Below Fibo 0.382 (after 300 days)
- **S12**: Below Fibo 0.236 (after 240 days)
- **S15**: Rapid decline (>25% in 4 days)
- **S16**: ATR spike + decline
- **S17**: Loss of range (after 150 days)

## Key Concepts

### ATR (Average True Range)

Used for volatility measurement and stop loss calculation. Implementation uses Wilder's smoothing method (Lewis ATR).

### Bollinger Bands

Used for breakout detection (B1) and volatility measurement (B3, B18).

### VCP (Volatility Contraction Pattern)

Mark Minervini's pattern for identifying breakout setups (US King B18).

### Energy Signals

Five criteria (E1-E5) measuring stock momentum and relative strength.

## Testing

```bash
# Test US King buy signals
pytest tests/algo_func/test_b*.py -v

# Test sell signals
pytest tests/algo_func/test_sell_signals.py -v

# Run all tests
pytest tests/algo_func/ -v
```

## Development Guidelines

### MultiCharts Index Translation

**CRITICAL**: Python uses different indexing than MultiCharts:

```python
# MultiCharts → Python
close[0]  → closes[-1]      # today
close[1]  → closes[-2]      # yesterday
close[N]  → closes[-(N+1)]  # N days ago
```

### Data Requirements

- **US King**: Minimum 302 bars (for B18 VCP)
- **HK Algo**: Minimum 270 bars (for B8)
- Must be sorted by date (ascending)
- Index data must be date-aligned

### Precision & Rounding

- **B13**: Rounds performance ratios to 1 decimal place
- Prevents false negatives from floating point precision issues

## Resources

### Documentation

- [US King Implementation Guide](US_King/implementation_guide.md)
- [HK Algo Terms](HK_Algo/hk_algo_terms.md)
- [US King Terms](US_King/us_king_terms.md)

### Source Code

- [US King MultiCharts](US_King/mc_us_king.els)
- [HK Algo MultiCharts](HK_Algo/mc_hk.txt)

### Implementation

- [Buy Signals (shared)](../app/workers/algo_func/buy_signals.py)
- [Buy King (US)](../app/workers/algo_func/buy_king.py)
- [Sell Signals (shared)](../app/workers/algo_func/sell_signals.py)
- [Sell King (US)](../app/workers/algo_func/sell_king.py)

---

**Last Updated**: February 24, 2026

**Note**: For detailed implementation instructions for another agent to understand the codebase, refer to [US King Implementation Guide](US_King/implementation_guide.md).
