import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import pandas as pd

from app.models.algorithm_models import GenomeResult, AlgorithmParameters

logger = logging.getLogger(__name__)

FIXED_DEPOSIT_AMOUNT = 10000.0


def calculate_genome_metrics(
    trades: List[Dict[str, Any]],
    genome_id: str,
    stock_code: str,
    parameters: Dict[str, Any]
) -> GenomeResult:
    """
    Calculate financial metrics for a genome's trades.
    
    Args:
        trades: List of trade dictionaries with Gain/Lose, Entry price, Exit price
        genome_id: The genome identifier
        stock_code: Stock symbol
        parameters: Algorithm parameters used for this genome
    
    Returns:
        GenomeResult with calculated metrics
    """
    if not trades:
        return GenomeResult(
            genome_id=genome_id,
            stock_code=stock_code,
            trade_count=0,
            total_win=0.0,
            total_loss=0.0,
            trades_win=0,
            trades_loss=0,
            avg_win=0.0,
            avg_loss=0.0,
            payoff_ratio=0.0,
            win_rate=0.0,
            total_profit=0.0,
            profit_percent=0.0,
            parameters=parameters,
        )
    
    wins = []
    losses = []
    
    for trade in trades:
        gain_lose = trade.get("Gain/Lose")
        
        # Skip open positions
        if trade.get("Stop Signal") == "Open position":
            continue
        if trade.get("Exit price") == "Open position":
            continue
            
        if gain_lose is None or gain_lose == "":
            continue
            
        try:
            profit_pct = float(gain_lose)
        except (ValueError, TypeError):
            continue
        
        # Calculate dollar amount
        profit_usd = FIXED_DEPOSIT_AMOUNT * (profit_pct / 100.0)
        
        if profit_usd >= 0:
            wins.append(profit_usd)
        else:
            losses.append(abs(profit_usd))
    
    trades_win = len(wins)
    trades_loss = len(losses)
    trade_count = trades_win + trades_loss
    
    total_win = sum(wins)
    total_loss = sum(losses)
    
    avg_win = total_win / trades_win if trades_win > 0 else 0.0
    avg_loss = total_loss / trades_loss if trades_loss > 0 else 0.0
    
    payoff_ratio = avg_win / avg_loss if avg_loss > 0 else 0.0
    win_rate = (trades_win / trade_count * 100) if trade_count > 0 else 0.0
    
    total_profit = total_win - total_loss
    profit_percent = (total_profit / FIXED_DEPOSIT_AMOUNT * 100) if FIXED_DEPOSIT_AMOUNT > 0 else 0.0
    
    # Extract only variable parameters for output
    params = AlgorithmParameters.from_dict(parameters)
    output_params = params.get_variable_params_for_output()
    
    return GenomeResult(
        genome_id=genome_id,
        stock_code=stock_code,
        trade_count=trade_count,
        total_win=total_win,
        total_loss=total_loss,
        trades_win=trades_win,
        trades_loss=trades_loss,
        avg_win=avg_win,
        avg_loss=avg_loss,
        payoff_ratio=payoff_ratio,
        win_rate=win_rate,
        total_profit=total_profit,
        profit_percent=profit_percent,
        parameters=output_params,
    )


def calculate_profit_delta(result, base) -> float:
    """
    Calculate profit delta as percentage relative to base algorithm.
    Formula: ((genome_profit - base_profit) / |base_profit|) × 100
    """
    if base.total_profit != 0:
        return round(
            ((result.total_profit - base.total_profit) / abs(base.total_profit)) * 100, 2
        )
    return 0.0


def calculate_win_rate(trades_win: int, trade_count: int) -> float:
    """
    Calculate win rate as ratio of profitable trades to total trades.
    A trade is profitable when sell_price > buy_price.
    """
    if trade_count > 0:
        return round((trades_win / trade_count) * 100, 2)
    return 0.0


def calculate_deltas_vs_base(
    results: List[GenomeResult],
    base_genome_id: str = "G_000"
) -> List[GenomeResult]:
    """
    Calculate profit and win rate deltas relative to BASE genome.
    
    Args:
        results: List of GenomeResult objects
        base_genome_id: The genome ID to use as baseline (default: G_000)
    
    Returns:
        Updated list with delta values calculated
    """
    # Find BASE result for each stock
    base_by_stock: Dict[str, GenomeResult] = {}
    for result in results:
        if result.genome_id == base_genome_id:
            base_by_stock[result.stock_code] = result
    
    # Calculate deltas
    for result in results:
        base = base_by_stock.get(result.stock_code)
        
        if base and result.genome_id != base_genome_id:
            # Profit delta (percentage points difference)
            result.profit_delta = calculate_profit_delta(result, base)
            # Win rate delta (percentage points difference)
            result.win_rate_delta = round(result.win_rate - base.win_rate, 2)
        elif result.genome_id == base_genome_id:
            # BASE always has 0 delta
            result.profit_delta = 0.0
            result.win_rate_delta = 0.0
        else:
            # No BASE found
            result.profit_delta = None
            result.win_rate_delta = None
    
    return results


def aggregate_optimization_results(
    all_trades: Dict[str, List[Dict[str, Any]]],
    genome_parameters: Dict[str, Dict[str, Any]]
) -> List[GenomeResult]:
    """
    Aggregate trades by genome and calculate metrics.
    
    Args:
        all_trades: Dict mapping "genome_id:stock_code" to list of trades
        genome_parameters: Dict mapping genome_id to parameters dict
    
    Returns:
        List of GenomeResult with all metrics calculated
    """
    results = []
    
    for key, trades in all_trades.items():
        parts = key.split(":", 1)
        if len(parts) != 2:
            logger.warning(f"Invalid trade key format: {key}")
            continue
            
        genome_id, stock_code = parts
        parameters = genome_parameters.get(genome_id, {})
        
        result = calculate_genome_metrics(trades, genome_id, stock_code, parameters)
        results.append(result)
    
    # Calculate deltas vs BASE
    results = calculate_deltas_vs_base(results)
    
    return results


def format_results_for_output(results: List[GenomeResult]) -> List[Dict[str, Any]]:
    """
    Format results for CSV/Google Sheets output.
    
    Returns list of dicts matching Output Results Sample.csv format.
    """
    output = []
    for result in results:
        row = result.to_output_row()
        output.append(row)
    
    # Sort by Genome ID, then Stock Code
    output.sort(key=lambda x: (x.get("Genome ID", ""), x.get("Stock Code", "")))
    
    return output


def get_output_fieldnames() -> List[str]:
    """Get ordered list of field names for output CSV."""
    base_fields = [
        "Genome ID",
        "Stock Code", 
        "Trade Count",
        "Profit Delta (%)",
        "Win Rate Delta (%)",
        "Total Win ($)",
        "Total Loss ($)",
        "Trades Win",
        "Trades Loss",
        "Avg Win ($)",
        "Avg Loss ($)",
        "Payoff Ratio",
    ]
    
    # Add variable parameter columns
    param_fields = [
        "input_B1_upper_range",
        "input_B3_LR_lookback",
        "input_B11_atr_threshold",
        "input_B18_bbw_ratio",
        "input_S1_atr_mult",
        "input_S5_push_up_atr",
    ]
    
    return base_fields + param_fields


def get_per_genome_output_fieldnames() -> List[str]:
    """Fieldnames for 'Automated Results Per Genome.csv' — per-stock, no param columns."""
    return [
        "Genome ID",
        "Stock Code",
        "Trade Count",
        "Profit Delta (%)",
        "Win Rate Delta (%)",
        "Total Win ($)",
        "Total Loss ($)",
        "Trades Win",
        "Trades Loss",
        "Avg Win ($)",
        "Avg Loss ($)",
        "Payoff Ratio",
    ]


def get_averaged_output_fieldnames(variable_param_names: Optional[List[str]] = None) -> List[str]:
    """Fieldnames for 'Automated Results.csv' — averaged across stocks, with param columns."""
    base_fields = [
        "Genome ID",
        "Trade Count",
        "Profit Delta (%)",
        "Win Rate Delta (%)",
        "Total Win ($)",
        "Total Loss ($)",
        "Trades Win",
        "Trades Loss",
        "Avg Win ($)",
        "Avg Loss ($)",
        "Payoff Ratio",
    ]
    if variable_param_names:
        return base_fields + variable_param_names
    # Fallback to hardcoded defaults
    return base_fields + [
        "input_B1_upper_range",
        "input_B3_LR_lookback",
        "input_B11_atr_threshold",
        "input_B18_bbw_ratio",
        "input_S1_atr_mult",
        "input_S5_push_up_atr",
    ]


def compute_averaged_metrics(
    per_stock_results: List[Dict[str, Any]],
    genome_id: str,
    parameters: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Average per-stock result dicts into one averaged result dict.
    
    Method: mean of raw totals, then derive ratios.
    """
    n = len(per_stock_results)
    if n == 0:
        return {}

    avg_trade_count = sum(float(r.get("Trade Count", 0)) for r in per_stock_results) / n
    avg_total_win = sum(float(r.get("Total Win ($)", 0)) for r in per_stock_results) / n
    avg_total_loss = sum(float(r.get("Total Loss ($)", 0)) for r in per_stock_results) / n
    avg_trades_win = sum(float(r.get("Trades Win", 0)) for r in per_stock_results) / n
    avg_trades_loss = sum(float(r.get("Trades Loss", 0)) for r in per_stock_results) / n

    avg_win = avg_total_win / avg_trades_win if avg_trades_win > 0 else 0.0
    avg_loss = avg_total_loss / avg_trades_loss if avg_trades_loss > 0 else 0.0
    payoff_ratio = avg_win / avg_loss if avg_loss > 0 else 0.0

    row = {
        "Genome ID": genome_id,
        "Trade Count": round(avg_trade_count, 2),
        "Profit Delta (%)": 0,
        "Win Rate Delta (%)": 0,
        "Total Win ($)": round(avg_total_win, 2),
        "Total Loss ($)": round(avg_total_loss, 2),
        "Trades Win": round(avg_trades_win, 2),
        "Trades Loss": round(avg_trades_loss, 2),
        "Avg Win ($)": round(avg_win, 2),
        "Avg Loss ($)": round(avg_loss, 2),
        "Payoff Ratio": round(payoff_ratio, 2),
    }

    # Add parameter values
    for key, value in parameters.items():
        row[key] = value

    return row


def calculate_averaged_deltas(result: Dict[str, Any], base: Dict[str, Any]) -> Dict[str, Any]:
    """Calculate Profit Delta and Win Rate Delta vs averaged BASE."""
    base_profit = float(base.get("Total Win ($)", 0)) - float(base.get("Total Loss ($)", 0))
    genome_profit = float(result.get("Total Win ($)", 0)) - float(result.get("Total Loss ($)", 0))

    if result.get("Genome ID") == "G_000":
        result["Profit Delta (%)"] = 0.0
        result["Win Rate Delta (%)"] = 0.0
        return result

    if base_profit != 0:
        result["Profit Delta (%)"] = round(((genome_profit - base_profit) / abs(base_profit)) * 100, 2)
    else:
        result["Profit Delta (%)"] = 0.0

    base_trades_win = float(base.get("Trades Win", 0))
    base_trade_count = float(base.get("Trade Count", 0))
    genome_trades_win = float(result.get("Trades Win", 0))
    genome_trade_count = float(result.get("Trade Count", 0))

    base_win_rate = (base_trades_win / base_trade_count * 100) if base_trade_count > 0 else 0.0
    genome_win_rate = (genome_trades_win / genome_trade_count * 100) if genome_trade_count > 0 else 0.0

    result["Win Rate Delta (%)"] = round(genome_win_rate - base_win_rate, 2)
    return result
