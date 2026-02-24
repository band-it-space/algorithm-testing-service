# US King Algorithm Documentation

## Quick Links

- **[Implementation Guide](implementation_guide.md)** - Comprehensive guide for developers
- **[Algorithm Specifications](us_king_terms.md)** - Buy/Sell rules and parameters
- **[Energy Signals](energy_signals.md)** - Energy level calculations (E1-E5)
- **[MultiCharts Source Code](mc_us_king.els)** - Original trading logic

## Quick Reference

### Buy Rule

```
Buy = ([B1 AND B8] OR [B18]) AND B9 AND B10 AND B11 AND B12 AND B13 AND B20 AND B21 AND B22
```

### Sell Rule

```
Sell = S1 OR S4 OR S5 OR S6 OR S7 OR S8 OR S9 OR S10 OR S11 OR S12 OR S13 OR S14 OR S15 OR S16 OR S17 OR S18 OR S19 OR S20
```

## Implementation Files

| Component      | File                                    | Description              |
| -------------- | --------------------------------------- | ------------------------ |
| Buy Signals    | `app/workers/algo_func/buy_king.py`     | US-specific buy signals  |
| Sell Signals   | `app/workers/algo_func/sell_king.py`    | US-specific sell signals |
| Shared Signals | `app/workers/algo_func/buy_signals.py`  | B10, B12, B13            |
| Shared Signals | `app/workers/algo_func/sell_signals.py` | S10-S17                  |
| Helpers        | `app/workers/algo_func/helpers.py`      | ATR, SMA, utilities      |

## Key Differences from HK Algo

### Buy Signals

- **B1**: Uses BB(22, 0.89) vs HK's BB(51, 1.9) + 20D high
- **B8**: 85D/150D lookback vs HK's 46D/270D
- **B11**: 67% threshold, 215D lookback vs HK's 87%, 126D
- **B13**: 100-day period vs HK's 60-day, SPY vs HSI
- **B18**: VCP pattern vs HK's BBW contraction
- **B20-B22**: US-only signals

### Sell Signals

- **S1**: 3.4x ATR, 7.2% adjusted vs HK's 3.7x, 14.25%
- **S4**: Different MA (50 vs 150), threshold (45% vs 50%)
- **S5**: Different activation (50 vs 45), interval (30 vs 25)
- **S18-S20**: US-only signals

## Usage Example

```python
from app.workers.algo_func.buy_king import runAllBuyConditions_US, isBuy_US
from app.workers.algo_func.sell_king import runAllSellConditions_US, isSell_US

# Buy signals
buy_signals = runAllBuyConditions_US(stock_ohlcv, spy_ohlcv, "2023-04-18")
if isBuy_US(buy_signals):
    print(f"Buy signal! Stop loss: {buy_signals['stopLoss']}")

# Sell signals
sell_signals = runAllSellConditions_US(
    stock_ohlcv, spy_ohlcv, entry_index, buy_price,
    s1_stop, s5_stop, energy_signals, current_idx
)
if isSell_US(sell_signals):
    print("Sell signal!")
```

## Testing

```bash
# Test buy signals
pytest tests/algo_func/test_b*.py -v

# Test sell signals
pytest tests/algo_func/test_sell_signals.py -v
```

## Important Notes

1. **Data Requirements**: Minimum 302 bars for B18 (VCP pattern)
2. **Index Alignment**: Stock and SPY data must be date-aligned
3. **Rounding**: B13 uses 1 decimal place rounding for ratios
4. **Volume Required**: B18 needs volume data
5. **MultiCharts Indexing**: `close[N]` in MC = `closes[-(N+1)]` in Python

---

For detailed implementation details, see [Implementation Guide](implementation_guide.md)
