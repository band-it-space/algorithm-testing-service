# Indicator Tests Overview

This README documents what is covered by `tests/algo_func/test_indicators.py` and how to run the tests in an isolated virtual environment.

## What is tested

-   `sma(values, period)`

    -   Validates expected SMA output on a simple sequence
    -   Returns empty list for sequences shorter than `period`
    -   Stable behavior on a constant series

-   `bollinger_bands(values, period, std_dev)`

    -   Returns empty list for insufficient length
    -   Output length equals `len(values) - period + 1`
    -   Each item has keys `upper`, `middle`, `lower`
    -   `middle` equals SMA of the window; ordering `upper > middle > lower`

-   `atr(highs, lows, closes, period)`

    -   Returns empty list when there isn’t enough history (needs at least `period + 1` highs/lows/closes)
    -   On a simple increasing channel, all values are positive and the output length is expected

-   `wilder_atr(highs, lows, closes, period)`

    -   Returns empty list for insufficient history
    -   Output has expected length; values are positive and contain no NaN/Inf (stable Wilder smoothing)

-   `linear_regression_slope(values)`

    -   Returns `0.0` for fewer than 2 points
    -   Positive on an increasing series, negative on a decreasing series, and ~0 on a flat series

-   `average(values)` and `mean(values)`
    -   Return `0.0` for empty input
    -   Return correct average for valid input

## How to run (with local virtual environment)

1. Create and activate a local venv:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install local test dependencies (venv only):

```bash
python3 -m pip install --upgrade pip
python3 -m pip install pytest numpy
```

3. Run the indicator tests:

```bash
python -m pytest -q tests/algo_func/test_indicators.py
```

## Notes

-   These are unit-level, synthetic-data tests focused on boundary conditions and correctness for the indicator helpers used by BUY signal checks.
-   Real, contract-style datasets are not required here; they will be introduced for BUY checks (B1..B13) validation against the product specification.

## Reference

-   Specification source shared by the client: `https://docs.google.com/document/d/1Uk6ANdOHigLnBXnHg1Uq4d-4SAIQSXz1dRs8MYmIP6A/edit?tab=t.0`
    \*\*\* End Patch
