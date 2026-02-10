# Time Optimization Requirements

## Overview

Optimize the trading algorithm to reduce genome processing time from ~15 minutes to <1 minute, enabling 7,200 genomes to be processed in under 2 hours instead of the current 22.5 hours projection.

## Functional Requirements

### FR-1: Performance Targets

| Metric | Current | Target |
|--------|---------|--------|
| Time per genome | ~15 minutes | <1 minute |
| 7,200 genomes processing | ~22.5 hours | <2 hours |
| Overall speedup | baseline | >15x |

### FR-2: Mathematical Accuracy

- All optimized code MUST produce identical output to the original implementation
- Zero tolerance for calculation differences - even minor deviations are unacceptable
- Validation framework required to verify accuracy before deployment

### FR-3: Data Caching

- Implement Redis-based caching for stock OHLCV data
- Cache SPY reference data (code 2800) to eliminate redundant API calls
- Cache individual stock data with configurable TTL (default: 1 hour)
- Cache hit/miss metrics must be logged for monitoring

### FR-4: Google Sheets Integration

- Input: Read command parameters and genome configurations from Google Sheets API
- Output: Write results to Google Sheets with proper rate limit handling
- Handle API quotas: 100 requests per 100 seconds
- Implement exponential backoff for rate limit errors
- Batch updates to minimize API calls

### FR-5: Dual Storage System

- All results saved to Google Sheets (primary)
- Local CSV backup: `Automated Results.csv` (default filename)
- Atomic writes to prevent data corruption
- Resume capability if process interrupts

## Technical Requirements

### TR-1: Optimization Techniques

#### Loop Optimization
- Eliminate O(n²) cumulative filtering in main day loop
- Replace list comprehension filters with index-based slicing
- Pre-compute index mappings between aligned data series

#### Data Pre-processing
- Sort all OHLCV data once at job start
- Parse all date strings to datetime objects once using vectorized operations
- Pre-compute rolling windows for energy indicators

#### Vectorization
- Convert pure Python indicator calculations to NumPy:
  - SMA (Simple Moving Average) → `np.convolve()` or `np.cumsum()`
  - ATR (Average True Range) → vectorized true range calculation
  - RSI (Relative Strength Index) → vectorized gain/loss with `np.where()`
  - Bollinger Bands → vectorized standard deviation

#### Sorting Optimization
- Remove redundant `sorted()` calls from signal functions (S1-S17, B1-B18)
- Guarantee sorted input via pre-processing
- Add assertion guards for sorted data assumption

### TR-2: Architecture Constraints

- Python-native implementation only
- Use existing dependencies from requirements.txt
- Maintain compatibility with existing RQ worker architecture
- No changes to API contract or data models

### TR-3: Infrastructure Requirements

- Redis server (already available via queue_config.py)
- Sufficient memory for data caching (~100MB per worker estimated)
- Existing Google Sheets API credentials

## Non-Functional Requirements

### NFR-1: Code Quality

- All new code must follow existing project conventions
- Add type hints to new functions
- Comprehensive docstrings for optimization modules
- Performance profiling instrumentation

### NFR-2: Logging & Monitoring

- Timing logs for each optimization phase
- Cache hit rate metrics
- API call counters for Google Sheets
- Error tracking with stack traces

### NFR-3: Testing

- Validation test suite comparing original vs optimized output
- Benchmark tests with configurable genome counts
- Unit tests for vectorized indicator functions

## Files to Modify

| File | Changes |
|------|---------|
| `app/workers/algorithm_worker.py` | Main loop optimization, data pre-processing |
| `app/workers/algo_func/buy_signals.py` | Vectorize indicators, remove sorting |
| `app/workers/algo_func/sell_signals.py` | Vectorize ATR, remove sorting |
| `app/workers/algo_func/get_code_energy.py` | Vectorize RSI, batch calculations |
| `app/workers/algo_func/get_db_data.py` | Integrate with cache layer |
| `app/workers/result_worker.py` | Replace iterrows() with vectorized ops |
| `app/services/file_service.py` | Buffered file writes |
| `app/services/sheets_service.py` | Rate limiting, batch optimization |

## New Files to Create

| File | Purpose |
|------|---------|
| `app/services/data_cache_service.py` | Redis caching layer for stock data |
| `app/utils/performance_profiler.py` | Timing decorators and metrics |
| `tests/test_optimization_validation.py` | Accuracy validation framework |

## Acceptance Criteria

1. **Performance**: Process single genome in <1 minute (average across 100 genomes)
2. **Accuracy**: 100% match between original and optimized output for all test cases
3. **Stability**: No crashes or data loss during 7,200 genome batch run
4. **Caching**: >95% cache hit rate for SPY data after warmup
5. **API Compliance**: Zero rate limit errors with Google Sheets API
6. **Backup**: All results saved to both Google Sheets and local CSV

## Identified Bottlenecks (from Research)

| Bottleneck | Location | Impact | Solution |
|------------|----------|--------|----------|
| O(n²) cumulative filtering | algorithm_worker.py:186-210 | 60-70% | Index-based slicing |
| Redundant API calls | algorithm_worker.py:142-143 | 7,200x calls | Redis caching |
| Repeated sorting | sell_signals.py (15+ locations) | 10-15% | Pre-sort once |
| Non-vectorized indicators | buy_signals.py:41-73 | 10-15% | NumPy vectorization |
| Energy recalculation | algorithm_worker.py:198-200 | 5-10% | Pre-compute lookup |
| Date parsing in loop | algorithm_worker.py:175-190 | 5% | Batch parse once |
| DataFrame.iterrows() | result_worker.py:66 | 2-3% | Vectorized operations |

## Deliverables

1. Refactored Python code with all optimizations implemented
2. Optimization report documenting bottlenecks and solutions
3. Data logging module with API quota management
4. Validation test suite
5. Updated documentation
