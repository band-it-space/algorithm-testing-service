from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Any

from pydantic import BaseModel


@dataclass
class AlgorithmParameters:
    """All configurable algorithm parameters with base values as defaults."""
    
    # B1 parameters
    input_B1_lookback: int = 20
    input_B1_bb_len: int = 51
    input_B1_bb_std: float = 1.9
    input_B1_ma_dev: float = 0.25
    input_B1_upper_range: float = 0.65
    
    # B3 parameters
    input_B3_bbw_len: int = 21
    input_B3_sma_bbw: int = 72
    input_B3_LR_lookback: int = 58
    
    # B8 parameters
    input_B8_recent_low: int = 46
    input_B8_past_low: int = 270
    
    # B9 parameters
    input_B9_ma_len: int = 50
    
    # B10 parameters
    input_B10_low_window: int = 250
    input_B10_prox_days: int = 68
    
    # B11 parameters
    input_B11_atr_len: int = 22
    input_B11_history: int = 126
    input_B11_atr_threshold: float = 0.87
    
    # B12 parameters
    input_B12_long_ma: int = 150
    input_B12_rise_pct: float = 0.16
    input_B12_deviation: float = 0.2
    
    # B13 parameters
    input_B13_XX: int = 19
    input_B13_YY: int = 60
    
    # B18 parameters
    input_B18_bbw_len: int = 21
    input_B18_history: int = 82
    input_B18_bbw_ratio: float = 0.22
    input_B18_Z: int = 21
    
    # S1 parameters (stop loss)
    input_S1_atr_mult: float = 3.7
    input_S1_atr_period: int = 22
    input_S1_hard_stop: float = 0.30  # 30% as decimal
    input_S1_medium_risk: float = 0.20
    input_S1_medium_stop: float = 0.095
    input_S1_high_stop: float = 0.1425
    
    # S4 parameters
    input_S4_max_days: int = 50
    input_S4_sma_period: int = 150
    input_S4_ratio_threshold: float = 0.5
    input_S4_gain_threshold: float = 5.0
    
    # S5 parameters
    input_S5_initial_days: int = 45
    input_S5_step_days: int = 25
    input_S5_push_up_atr: float = 0.62
    input_S5_atr_period: int = 20
    
    # S6 parameters
    input_S6_min_days: int = 50
    input_S6_high_window: int = 90
    input_S6_days_threshold: int = 76
    
    # S7 parameters
    input_S7_atr_period: int = 22
    input_S7_body_mult: float = 2.0
    
    # S8 parameters
    input_S8_atr22_window: int = 126
    input_S8_atr100_threshold: float = 0.74
    input_S8_body_mult: float = 2.4
    input_S8_bear_count: int = 3
    
    # S9 parameters
    input_S9_energy_thresh: float = 0.22
    
    # S10 parameters
    input_S10_atr_ratio: float = 2.6
    input_S10_drawdown: float = 0.05
    
    # S11 parameters
    input_S11_xx_days: int = 300
    input_S11_fib_level: float = 0.382
    input_S11_yy_days: int = 3  # original: streak_below >= 3
    
    # S12 parameters
    input_S12_xx_days: int = 240
    input_S12_fib_level: float = 0.236
    input_S12_yy_days: int = 23  # original: streak_below >= 23
    
    # S13 parameters
    input_S13_min_days: int = 238
    input_S13_lookback: int = 80
    
    # S14 parameters
    input_S14_min_days: int = 300
    input_S14_horizons: list[int] = field(default_factory=lambda: [35, 70, 105])
    
    # S15 parameters
    input_S15_crash_drop: float = 0.25
    input_S15_lookback: int = 4
    
    # S16 parameters
    input_S16_xx: float = 15.0
    input_S16_yy: int = 10
    input_S16_effective: int = 0
    input_S16_atr_inc: float = 50.0
    input_S16_atr_day: int = 12
    
    # S17 parameters
    input_S17_min_days: int = 150
    input_S17_wide_range: float = 1.6
    input_S17_near_bottom: float = 1.3

    def to_dict(self) -> dict[str, Any]:
        """Serialize parameters to dictionary."""
        result = asdict(self)
        if 'input_S14_horizons' in result:
            result['input_S14_horizons'] = list(result['input_S14_horizons'])
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AlgorithmParameters":
        """Deserialize parameters from dictionary."""
        if not data:
            return cls()
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered_data = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered_data)
    
    def get_variable_params_for_output(self, variable_param_names: list[str] | None = None) -> dict[str, Any]:
        """Get subset of parameters typically varied in optimization."""
        if variable_param_names:
            params_dict = self.to_dict()
            return {name: params_dict[name] for name in variable_param_names if name in params_dict}
        # Fallback to hardcoded defaults for backward compatibility
        return {
            "input_B1_upper_range": self.input_B1_upper_range,
            "input_B3_LR_lookback": self.input_B3_LR_lookback,
            "input_B11_atr_threshold": self.input_B11_atr_threshold,
            "input_B18_bbw_ratio": self.input_B18_bbw_ratio,
            "input_S1_atr_mult": self.input_S1_atr_mult,
            "input_S5_push_up_atr": self.input_S5_push_up_atr,
        }


@dataclass
class ParameterRange:
    """Model for defining parameter optimization ranges."""
    
    name: str
    base: float
    min_val: float
    max_val: float
    step: float
    change: bool
    rule: str = ""
    
    def generate_values(self) -> list[float]:
        """Generate list of values from min to max by step."""
        if not self.change:
            return [self.base]
        
        values = []
        current = self.min_val
        while current <= self.max_val + 1e-9:
            values.append(round(current, 6))
            current += self.step
        return values
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ParameterRange":
        """Create ParameterRange from dictionary (e.g., from CSV row)."""
        return cls(
            name=data.get("Parameter Variable", data.get("name", "")),
            base=float(data.get("Base", data.get("base", 0))),
            min_val=float(data.get("Min", data.get("min_val", 0))),
            max_val=float(data.get("Max", data.get("max_val", 0))),
            step=float(data.get("Step", data.get("step", 1))),
            change=str(data.get("Change", data.get("change", "FALSE"))).upper() == "TRUE",
            rule=data.get("Rule", data.get("rule", ""))
        )


@dataclass
class UnifiedTradeSignal:
    """Unified representation of a trade signal."""
    buy_signal: datetime | None
    stop_signal: datetime | str
    entry_price: float
    exit_price: float | str
    day_before_buy: datetime | None
    day_before_sell: datetime | None
    gain_lose: float | None
    source: str


@dataclass
class GenomeResult:
    """Result metrics for a single genome."""
    genome_id: str
    stock_code: str
    trade_count: int
    total_win: float
    total_loss: float
    trades_win: int
    trades_loss: int
    avg_win: float
    avg_loss: float
    payoff_ratio: float
    win_rate: float
    total_profit: float
    profit_percent: float
    parameters: dict[str, Any]
    
    # Delta vs BASE (calculated separately)
    profit_delta: float | None = None
    win_rate_delta: float | None = None
    
    def to_output_row(self) -> dict[str, Any]:
        """Convert to output format matching Output Results Sample.csv"""
        row = {
            "Genome ID": self.genome_id,
            "Stock Code": self.stock_code,
            "Trade Count": self.trade_count,
            "Profit Delta (%)": self.profit_delta if self.profit_delta is not None else 0,
            "Win Rate Delta (%)": self.win_rate_delta if self.win_rate_delta is not None else 0,
            "Total Win ($)": round(self.total_win, 2),
            "Total Loss ($)": round(self.total_loss, 2),
            "Trades Win": self.trades_win,
            "Trades Loss": self.trades_loss,
            "Avg Win ($)": round(self.avg_win, 2),
            "Avg Loss ($)": round(self.avg_loss, 2),
            "Payoff Ratio": round(self.payoff_ratio, 2),
        }
        # Add parameter values
        for key, value in self.parameters.items():
            row[key] = value
        return row