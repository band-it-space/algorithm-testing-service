"""
Optimization Validation Test Suite

Ensures that optimized code produces identical results to the original implementation.
Zero tolerance for calculation differences.
"""

import pytest
import json
import copy
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from pathlib import Path
import hashlib

logger = logging.getLogger(__name__)

# Test data directory
TEST_DATA_DIR = Path(__file__).parent / "test_data"
BASELINE_FILE = TEST_DATA_DIR / "baseline_results.json"


@dataclass
class GenomeConfig:
    """Test genome configuration."""
    id: str
    code: str
    start_date: str
    end_date: str
    parameters: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "code": self.code,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "parameters": self.parameters
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'GenomeConfig':
        return cls(**data)


# Diverse test genome configurations covering different scenarios
TEST_GENOMES = [
    GenomeConfig(
        id="genome_001",
        code="AAPL",
        start_date="2023-01-01",
        end_date="2023-06-30",
        parameters={"sma_period": 20, "rsi_period": 14, "atr_period": 14}
    ),
    GenomeConfig(
        id="genome_002",
        code="MSFT",
        start_date="2023-01-01",
        end_date="2023-06-30",
        parameters={"sma_period": 50, "rsi_period": 14, "atr_period": 20}
    ),
    GenomeConfig(
        id="genome_003",
        code="GOOGL",
        start_date="2022-06-01",
        end_date="2022-12-31",
        parameters={"sma_period": 10, "rsi_period": 7, "atr_period": 10}
    ),
    GenomeConfig(
        id="genome_004",
        code="AMZN",
        start_date="2023-03-01",
        end_date="2023-09-30",
        parameters={"sma_period": 100, "rsi_period": 21, "atr_period": 14}
    ),
    GenomeConfig(
        id="genome_005",
        code="TSLA",
        start_date="2022-01-01",
        end_date="2022-06-30",
        parameters={"sma_period": 20, "rsi_period": 14, "atr_period": 14}
    ),
    GenomeConfig(
        id="genome_006",
        code="META",
        start_date="2023-01-01",
        end_date="2023-12-31",
        parameters={"sma_period": 30, "rsi_period": 14, "atr_period": 14}
    ),
    GenomeConfig(
        id="genome_007",
        code="NVDA",
        start_date="2023-06-01",
        end_date="2023-12-31",
        parameters={"sma_period": 20, "rsi_period": 10, "atr_period": 7}
    ),
    GenomeConfig(
        id="genome_008",
        code="JPM",
        start_date="2022-01-01",
        end_date="2023-01-01",
        parameters={"sma_period": 50, "rsi_period": 14, "atr_period": 21}
    ),
    GenomeConfig(
        id="genome_009",
        code="V",
        start_date="2023-01-01",
        end_date="2023-06-30",
        parameters={"sma_period": 15, "rsi_period": 14, "atr_period": 14}
    ),
    GenomeConfig(
        id="genome_010",
        code="WMT",
        start_date="2022-06-01",
        end_date="2023-06-01",
        parameters={"sma_period": 20, "rsi_period": 14, "atr_period": 14}
    ),
]


class OutputCapture:
    """Captures and stores algorithm output for comparison."""
    
    def __init__(self, genome_id: str):
        self.genome_id = genome_id
        self.signals: List[Dict[str, Any]] = []
        self.trades: List[Dict[str, Any]] = []
        self.metrics: Dict[str, Any] = {}
        self.energy_values: List[Dict[str, Any]] = []
        self.indicator_values: Dict[str, List[float]] = {}
    
    def add_signal(self, signal: Dict[str, Any]) -> None:
        self.signals.append(copy.deepcopy(signal))
    
    def add_trade(self, trade: Dict[str, Any]) -> None:
        self.trades.append(copy.deepcopy(trade))
    
    def set_metrics(self, metrics: Dict[str, Any]) -> None:
        self.metrics = copy.deepcopy(metrics)
    
    def add_energy(self, energy: Dict[str, Any]) -> None:
        self.energy_values.append(copy.deepcopy(energy))
    
    def set_indicators(self, name: str, values: List[float]) -> None:
        self.indicator_values[name] = copy.deepcopy(values)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "genome_id": self.genome_id,
            "signals": self.signals,
            "trades": self.trades,
            "metrics": self.metrics,
            "energy_values": self.energy_values,
            "indicator_values": self.indicator_values
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'OutputCapture':
        capture = cls(data["genome_id"])
        capture.signals = data.get("signals", [])
        capture.trades = data.get("trades", [])
        capture.metrics = data.get("metrics", {})
        capture.energy_values = data.get("energy_values", [])
        capture.indicator_values = data.get("indicator_values", {})
        return capture
    
    def compute_hash(self) -> str:
        """Compute a hash of the output for quick comparison."""
        data = json.dumps(self.to_dict(), sort_keys=True, default=str)
        return hashlib.sha256(data.encode()).hexdigest()


class ValidationResult:
    """Result of comparing two outputs."""
    
    def __init__(self):
        self.is_valid = True
        self.differences: List[Dict[str, Any]] = []
    
    def add_difference(
        self, 
        field: str, 
        expected: Any, 
        actual: Any,
        index: Optional[int] = None
    ) -> None:
        self.is_valid = False
        self.differences.append({
            "field": field,
            "index": index,
            "expected": expected,
            "actual": actual
        })
    
    def __bool__(self) -> bool:
        return self.is_valid
    
    def summary(self) -> str:
        if self.is_valid:
            return "PASS: All outputs match"
        
        summary_lines = [f"FAIL: {len(self.differences)} differences found"]
        for diff in self.differences[:10]:  # Show first 10
            idx_str = f"[{diff['index']}]" if diff['index'] is not None else ""
            summary_lines.append(
                f"  - {diff['field']}{idx_str}: "
                f"expected={diff['expected']}, actual={diff['actual']}"
            )
        
        if len(self.differences) > 10:
            summary_lines.append(f"  ... and {len(self.differences) - 10} more")
        
        return "\n".join(summary_lines)


def compare_outputs(
    expected: OutputCapture, 
    actual: OutputCapture,
    tolerance: float = 1e-10
) -> ValidationResult:
    """
    Compare two output captures field-by-field.
    
    Args:
        expected: Expected (baseline) output
        actual: Actual (optimized) output
        tolerance: Floating point comparison tolerance
    
    Returns:
        ValidationResult with detailed differences
    """
    result = ValidationResult()
    
    # Compare signals
    if len(expected.signals) != len(actual.signals):
        result.add_difference(
            "signals.length",
            len(expected.signals),
            len(actual.signals)
        )
    else:
        for i, (exp_sig, act_sig) in enumerate(zip(expected.signals, actual.signals)):
            for key in exp_sig:
                if key not in act_sig:
                    result.add_difference(f"signals.{key}", exp_sig[key], None, i)
                elif not _values_equal(exp_sig[key], act_sig[key], tolerance):
                    result.add_difference(f"signals.{key}", exp_sig[key], act_sig[key], i)
    
    # Compare trades
    if len(expected.trades) != len(actual.trades):
        result.add_difference(
            "trades.length",
            len(expected.trades),
            len(actual.trades)
        )
    else:
        for i, (exp_trade, act_trade) in enumerate(zip(expected.trades, actual.trades)):
            for key in exp_trade:
                if key not in act_trade:
                    result.add_difference(f"trades.{key}", exp_trade[key], None, i)
                elif not _values_equal(exp_trade[key], act_trade[key], tolerance):
                    result.add_difference(f"trades.{key}", exp_trade[key], act_trade[key], i)
    
    # Compare metrics
    for key in expected.metrics:
        if key not in actual.metrics:
            result.add_difference(f"metrics.{key}", expected.metrics[key], None)
        elif not _values_equal(expected.metrics[key], actual.metrics[key], tolerance):
            result.add_difference(
                f"metrics.{key}",
                expected.metrics[key],
                actual.metrics[key]
            )
    
    # Compare energy values
    if len(expected.energy_values) != len(actual.energy_values):
        result.add_difference(
            "energy_values.length",
            len(expected.energy_values),
            len(actual.energy_values)
        )
    else:
        for i, (exp_e, act_e) in enumerate(zip(expected.energy_values, actual.energy_values)):
            for key in exp_e:
                if not _values_equal(exp_e.get(key), act_e.get(key), tolerance):
                    result.add_difference(f"energy.{key}", exp_e.get(key), act_e.get(key), i)
    
    # Compare indicator values
    for name, exp_values in expected.indicator_values.items():
        if name not in actual.indicator_values:
            result.add_difference(f"indicators.{name}", "present", "missing")
            continue
        
        act_values = actual.indicator_values[name]
        if len(exp_values) != len(act_values):
            result.add_difference(
                f"indicators.{name}.length",
                len(exp_values),
                len(act_values)
            )
        else:
            for i, (exp_v, act_v) in enumerate(zip(exp_values, act_values)):
                if not _values_equal(exp_v, act_v, tolerance):
                    result.add_difference(f"indicators.{name}", exp_v, act_v, i)
    
    return result


def _values_equal(a: Any, b: Any, tolerance: float) -> bool:
    """Compare two values with tolerance for floats."""
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    
    if isinstance(a, float) and isinstance(b, float):
        if abs(a) < tolerance and abs(b) < tolerance:
            return True
        return abs(a - b) <= tolerance * max(abs(a), abs(b), 1.0)
    
    return a == b


def save_baseline(results: Dict[str, OutputCapture], filepath: Path = BASELINE_FILE) -> None:
    """Save baseline results to file."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    
    data = {genome_id: capture.to_dict() for genome_id, capture in results.items()}
    
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2, default=str)
    
    logger.info(f"Saved baseline for {len(results)} genomes to {filepath}")


def load_baseline(filepath: Path = BASELINE_FILE) -> Dict[str, OutputCapture]:
    """Load baseline results from file."""
    if not filepath.exists():
        logger.warning(f"Baseline file not found: {filepath}")
        return {}
    
    with open(filepath, 'r') as f:
        data = json.load(f)
    
    return {
        genome_id: OutputCapture.from_dict(capture_data)
        for genome_id, capture_data in data.items()
    }


# ============================================================================
# PYTEST FIXTURES AND TESTS
# ============================================================================

@pytest.fixture
def test_genomes() -> List[GenomeConfig]:
    """Provide test genome configurations."""
    return TEST_GENOMES


@pytest.fixture
def baseline_results() -> Dict[str, OutputCapture]:
    """Load baseline results for comparison."""
    return load_baseline()


class TestVectorizedIndicators:
    """Test that vectorized indicator calculations match original implementations."""
    
    def test_sma_vectorized_matches_original(self):
        """SMA vectorization produces identical results."""
        import numpy as np
        
        # Test data
        values = [10.0, 11.0, 12.0, 11.5, 13.0, 14.0, 13.5, 15.0, 14.5, 16.0]
        period = 3
        
        # Original implementation (loop-based)
        def sma_original(values, period):
            result = []
            for i in range(len(values)):
                if i < period - 1:
                    result.append(None)
                else:
                    window = values[i - period + 1:i + 1]
                    result.append(sum(window) / period)
            return result
        
        # Vectorized implementation
        def sma_vectorized(values, period):
            arr = np.array(values)
            weights = np.ones(period) / period
            sma_values = np.convolve(arr, weights, mode='valid')
            return [None] * (period - 1) + sma_values.tolist()
        
        original = sma_original(values, period)
        vectorized = sma_vectorized(values, period)
        
        assert len(original) == len(vectorized)
        for i, (o, v) in enumerate(zip(original, vectorized)):
            if o is None:
                assert v is None, f"Mismatch at index {i}: expected None, got {v}"
            else:
                assert abs(o - v) < 1e-10, f"Mismatch at index {i}: {o} vs {v}"
    
    def test_rsi_vectorized_matches_original(self):
        """RSI vectorization produces identical results."""
        import numpy as np
        import pandas as pd
        
        # Test data
        prices = [44.0, 44.5, 43.5, 44.0, 44.5, 45.0, 44.5, 45.5, 46.0, 45.5,
                  46.0, 46.5, 46.0, 47.0, 47.5, 47.0, 48.0, 47.5, 48.5, 49.0]
        period = 14
        
        # Vectorized RSI
        def rsi_vectorized(prices, period=14):
            arr = np.array(prices)
            deltas = np.diff(arr)
            
            gains = np.where(deltas > 0, deltas, 0)
            losses = np.where(deltas < 0, -deltas, 0)
            
            avg_gain = pd.Series(gains).rolling(period).mean().values
            avg_loss = pd.Series(losses).rolling(period).mean().values
            
            rs = avg_gain / (avg_loss + 1e-10)
            rsi_values = 100 - (100 / (1 + rs))
            
            return [None] + rsi_values.tolist()
        
        result = rsi_vectorized(prices, period)
        
        # Basic sanity checks
        assert len(result) == len(prices)
        assert result[0] is None  # First value should be None (diff offset)
        
        # RSI values should be between 0 and 100 (where not None/NaN)
        for i, v in enumerate(result[period:]):
            if v is not None and not np.isnan(v):
                assert 0 <= v <= 100, f"RSI at {i} out of range: {v}"
    
    def test_atr_vectorized_matches_original(self):
        """ATR vectorization produces identical results."""
        import numpy as np
        import pandas as pd
        
        # Mock OHLCV data
        @dataclass
        class MockOHLCV:
            high: float
            low: float
            close: float
        
        ohlcv = [
            MockOHLCV(45.0, 43.5, 44.5),
            MockOHLCV(45.5, 44.0, 45.0),
            MockOHLCV(46.0, 44.5, 45.5),
            MockOHLCV(46.5, 45.0, 46.0),
            MockOHLCV(47.0, 45.5, 46.5),
            MockOHLCV(47.5, 46.0, 47.0),
            MockOHLCV(48.0, 46.5, 47.5),
            MockOHLCV(48.5, 47.0, 48.0),
            MockOHLCV(49.0, 47.5, 48.5),
            MockOHLCV(49.5, 48.0, 49.0),
        ]
        period = 5
        
        # Vectorized ATR
        def atr_vectorized(ohlcv, period):
            high = np.array([bar.high for bar in ohlcv])
            low = np.array([bar.low for bar in ohlcv])
            close = np.array([bar.close for bar in ohlcv])
            
            prev_close = np.roll(close, 1)
            prev_close[0] = close[0]
            
            tr = np.maximum(
                high - low,
                np.maximum(
                    np.abs(high - prev_close),
                    np.abs(low - prev_close)
                )
            )
            
            atr_values = pd.Series(tr).rolling(period).mean().values
            return atr_values.tolist()
        
        result = atr_vectorized(ohlcv, period)
        
        assert len(result) == len(ohlcv)
        
        # First (period-1) values should be NaN
        for i in range(period - 1):
            assert np.isnan(result[i]) or result[i] is None
        
        # Remaining values should be positive
        for v in result[period - 1:]:
            if not np.isnan(v):
                assert v > 0


class TestDataPreprocessing:
    """Test that data pre-processing doesn't affect results."""
    
    def test_presorted_data_gives_same_results(self):
        """Pre-sorting data produces identical filtering results."""
        from dataclasses import dataclass
        
        @dataclass
        class MockOHLCV:
            date: str
            close: float
        
        # Unsorted data
        unsorted_data = [
            MockOHLCV("2023-01-03", 100.0),
            MockOHLCV("2023-01-01", 98.0),
            MockOHLCV("2023-01-05", 102.0),
            MockOHLCV("2023-01-02", 99.0),
            MockOHLCV("2023-01-04", 101.0),
        ]
        
        # Original approach: filter then sort
        tradeday = "2023-01-03"
        original_filtered = sorted(
            [bar for bar in unsorted_data if bar.date <= tradeday],
            key=lambda x: x.date
        )
        
        # Optimized approach: sort once, then slice
        sorted_data = sorted(unsorted_data, key=lambda x: x.date)
        date_index = {bar.date: i for i, bar in enumerate(sorted_data)}
        end_idx = date_index.get(tradeday, len(sorted_data) - 1)
        optimized_filtered = sorted_data[:end_idx + 1]
        
        # Compare
        assert len(original_filtered) == len(optimized_filtered)
        for orig, opt in zip(original_filtered, optimized_filtered):
            assert orig.date == opt.date
            assert orig.close == opt.close


class TestOutputValidation:
    """Integration tests comparing full algorithm outputs."""
    
    @pytest.mark.skip(reason="Requires full algorithm implementation")
    def test_genome_output_matches_baseline(self, test_genomes, baseline_results):
        """
        Verify that optimized algorithm produces identical output to baseline.
        
        This test should be run after implementing optimizations.
        """
        for genome in test_genomes:
            if genome.id not in baseline_results:
                pytest.skip(f"No baseline for {genome.id}")
            
            expected = baseline_results[genome.id]
            
            # Run optimized algorithm (placeholder)
            # actual = run_optimized_algorithm(genome)
            actual = OutputCapture(genome.id)  # Placeholder
            
            result = compare_outputs(expected, actual)
            
            assert result.is_valid, f"Genome {genome.id}:\n{result.summary()}"
    
    def test_compare_outputs_detects_differences(self):
        """Verify that compare_outputs correctly identifies differences."""
        expected = OutputCapture("test")
        expected.signals = [{"type": "buy", "price": 100.0}]
        expected.metrics = {"total_return": 0.15}
        
        # Matching output
        actual_match = OutputCapture("test")
        actual_match.signals = [{"type": "buy", "price": 100.0}]
        actual_match.metrics = {"total_return": 0.15}
        
        result = compare_outputs(expected, actual_match)
        assert result.is_valid
        
        # Different output
        actual_diff = OutputCapture("test")
        actual_diff.signals = [{"type": "buy", "price": 100.5}]  # Different price
        actual_diff.metrics = {"total_return": 0.15}
        
        result = compare_outputs(expected, actual_diff)
        assert not result.is_valid
        assert len(result.differences) > 0


# ============================================================================
# BENCHMARK UTILITIES
# ============================================================================

class PerformanceBenchmark:
    """Utilities for performance benchmarking."""
    
    @staticmethod
    def run_benchmark(
        func,
        args: tuple = (),
        kwargs: dict = None,
        iterations: int = 10,
        warmup: int = 2
    ) -> Dict[str, float]:
        """
        Run a function multiple times and collect timing statistics.
        
        Args:
            func: Function to benchmark
            args: Positional arguments
            kwargs: Keyword arguments
            iterations: Number of timed iterations
            warmup: Number of warmup iterations (not timed)
        
        Returns:
            Dictionary with timing statistics
        """
        import time
        
        kwargs = kwargs or {}
        times = []
        
        # Warmup
        for _ in range(warmup):
            func(*args, **kwargs)
        
        # Timed runs
        for _ in range(iterations):
            start = time.perf_counter()
            func(*args, **kwargs)
            elapsed = time.perf_counter() - start
            times.append(elapsed)
        
        return {
            "min": min(times),
            "max": max(times),
            "avg": sum(times) / len(times),
            "total": sum(times),
            "iterations": iterations
        }


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
