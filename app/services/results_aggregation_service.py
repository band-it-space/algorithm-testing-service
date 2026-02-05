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
            result.profit_delta = round(result.profit_percent - base.profit_percent, 2)
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
