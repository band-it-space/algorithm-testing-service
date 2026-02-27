import csv
import json
import logging
import os
from datetime import datetime
from typing import Any, TypedDict

import numpy as np
import pandas as pd
import requests

from app.config.smart_filtering_config import SMART_FILTERING_ENABLED
from app.models.algorithm_models import AlgorithmParameters, UnifiedTradeSignal
from app.services.file_service import FileService
from app.services.optimization_service import OptimizationService
from app.services.queue_service import QueueService
from app.services.results_aggregation_service import (
    calculate_genome_metrics,
    format_results_for_output,
    get_output_fieldnames,
    get_per_genome_output_fieldnames,
    get_averaged_output_fieldnames,
    compute_averaged_metrics,
    calculate_averaged_deltas,
)
from app.services.smart_filtering_service import SmartFilteringService

# --- CONFIGURATION ---
FIXED_DEPOSIT_AMOUNT = 10000.0
GENERAL_RESULTS_FILE = "general_results"
OPTIMIZATION_RESULTS_FILE = "optimization_results"
AUTOMATED_RESULTS_FILE = os.getenv('OUTPUT_SHEET_NAME', 'Automated Results')
AUTOMATED_RESULTS_PER_GENOME_FILE = os.getenv('OUTPUT_PER_GENOME_SHEET_NAME', 'Automated Results Per Genome')

class ErrorResponse(TypedDict):
    error: str
    detail: str | None

logger = logging.getLogger(__name__)

API_KEY = os.getenv('API_KEY')
# Date range from environment (with fallback defaults)
START_DATE = os.getenv('OPTIMIZATION_START_DATE', '2009-01-01')
END_DATE = os.getenv('OPTIMIZATION_END_DATE', '2016-01-01')

file_service = FileService()


def _load_trade_pairs_from_redis(
    optimization_id: str | None,
    stock_code: str,
    genome_id: str,
) -> list[dict[str, Any]]:
    """Load trade pairs stored by algorithm worker and delete the key after read."""
    client = QueueService.get_redis_client()
    key = f"trade_pairs:{optimization_id or 'single'}:{stock_code}:{genome_id}"
    raw = client.get(key)
    if raw is None:
        logger.warning(f"No trade pairs found in Redis for key={key}")
        return []
    client.delete(key)
    return json.loads(raw)


# --- HELPERS ---
def _to_float_or_zero(value: Any) -> float:
    try:
        if value in (None, "", "Open position"):
            return 0.0
        return float(value)
    except Exception:
        return 0.0

def _to_float_or_open(value: Any) -> float | str:
    try:
        if value in (None, "", "Open position"):
            return "Open position"
        return float(value)
    except Exception:
        return "Open position"


async def save_financial_results(
    stock_code: str, 
    algo_data: list[dict[str, Any]], 
    file_service: FileService,
    genome_id: str = "G_000",
    parameters: dict[str, Any] | None = None
) -> None:
    """
    Save financial results including genome information.
    
    OPTIMIZED: Uses vectorized pandas operations instead of iterrows() (Task 7.1)
    """
    if not algo_data:
        return
    
    df = pd.DataFrame(algo_data)
    
    # OPTIMIZATION: Vectorized profit calculation instead of iterrows()
    # Convert Gain/Lose to numeric, handling non-numeric values
    df['profit_pct'] = pd.to_numeric(df.get('Gain/Lose', pd.Series(dtype=float)), errors='coerce').fillna(0.0)
    
    # Vectorized profit USD calculation
    df['profit_usd'] = (FIXED_DEPOSIT_AMOUNT * (df['profit_pct'] / 100.0)).round(2)
    
    # Vectorized open position detection
    stop_signal_col = df.get('Stop Signal', pd.Series([''] * len(df), dtype=str)).astype(str)
    exit_price_col = df.get('Exit price', pd.Series([''] * len(df), dtype=str)).astype(str)
    
    df['is_open'] = (
        stop_signal_col.str.contains('Open position', na=False) |
        exit_price_col.str.contains('Open position', na=False)
    )
    
    # Vectorized exit day calculation using np.where
    df['exit_day_val'] = np.where(df['is_open'], '', stop_signal_col)
    
    # Build result records using vectorized column access
    mapped_rows = []
    
    # Use numpy arrays for faster iteration
    buy_signals = df.get('Buy Signal', pd.Series([''] * len(df))).values
    entry_prices = df.get('Entry price', pd.Series([''] * len(df))).values
    exit_prices = df.get('Exit price', pd.Series([''] * len(df))).values
    exit_days = df['exit_day_val'].values
    profit_usds = df['profit_usd'].values
    profit_pcts = df['profit_pct'].values
    
    for idx in range(len(df)):
        record = {
            "symbol": stock_code,
            "genome_id": genome_id,
            "entryDay": buy_signals[idx] if pd.notna(buy_signals[idx]) else "",
            "entryPrice": entry_prices[idx] if pd.notna(entry_prices[idx]) else "",
            "exitDay": exit_days[idx],
            "exitPrice": exit_prices[idx] if pd.notna(exit_prices[idx]) else "",
            "profit": profit_usds[idx],
            "Profit %": profit_pcts[idx],
            "Invested": FIXED_DEPOSIT_AMOUNT
        }
        mapped_rows.append(record)

    if not mapped_rows:
        return

    fieldnames = [
        "symbol", "genome_id", "entryDay", "entryPrice", 
        "exitDay", "exitPrice", 
        "profit", "Profit %", "Invested"
    ]
    
    await file_service.add_data_to_csv(GENERAL_RESULTS_FILE, mapped_rows, fieldnames)


async def save_genome_optimization_results(
    stock_code: str,
    algo_data: list[dict[str, Any]],
    genome_id: str,
    parameters: dict[str, Any],
    optimization_id: str | None = None
) -> Any:
    """
    Calculate and save optimization results for a genome.
    Writes per-stock results to Per Genome CSV and triggers averaging when all stocks done.
    """
    if not algo_data:
        logger.warning(f"No algo data for {stock_code}/{genome_id}")
        return None
    
    # Calculate metrics for this genome
    result = calculate_genome_metrics(
        trades=algo_data,
        genome_id=genome_id,
        stock_code=stock_code,
        parameters=parameters
    )
    
    # Format for output
    output_row = result.to_output_row()
    
    # 1. Write to optimization_results.csv (unchanged)
    if optimization_id:
        opt_row = {**output_row, "optimization_id": optimization_id}
        opt_fieldnames = ["optimization_id"] + get_output_fieldnames()
        await file_service.add_data_to_csv(OPTIMIZATION_RESULTS_FILE, [opt_row], opt_fieldnames)
    
    # 2. Write to "Automated Results Per Genome.csv" (per-stock, no params)
    per_genome_row = {k: v for k, v in output_row.items() if k in get_per_genome_output_fieldnames()}
    if genome_id == "G_000":
        per_genome_row["Genome ID"] = "G_000 (BASE)"
    await file_service.add_data_to_csv(
        AUTOMATED_RESULTS_PER_GENOME_FILE,
        [per_genome_row],
        get_per_genome_output_fieldnames()
    )
    
    # 3. Store per-stock result in Redis
    if optimization_id:
        try:
            OptimizationService.store_genome_result(
                optimization_id=optimization_id,
                genome_id=genome_id,
                stock_code=stock_code,
                result=output_row
            )
            logger.debug(f"Stored result in Redis for {genome_id}/{stock_code}")
        except Exception as e:
            logger.error(f"Failed to store result in Redis: {e}")
        
        # 4. Track per-genome stock completion
        try:
            await _check_genome_completion(optimization_id, genome_id, parameters)
        except Exception as e:
            logger.error(f"Failed genome completion check for {genome_id}: {e}")
    
    logger.info(
        f"Saved optimization result for {genome_id}/{stock_code}: "
        f"{result.trade_count} trades, PR: {result.payoff_ratio:.2f}"
    )
    return result


async def _check_genome_completion(optimization_id: str, genome_id: str, parameters: dict[str, Any]) -> None:
    """
    Check if all stock_codes for this genome are done.
    If so, compute averaged metrics and trigger smart filtering.
    """
    metadata = OptimizationService.get_optimization(optimization_id)
    if not metadata:
        return

    stock_count = len(metadata.stock_codes)
    done_count = OptimizationService.increment_genome_stock_done(optimization_id, genome_id)

    if done_count < stock_count:
        return  # Not all stocks done yet

    # --- All stocks for this genome are complete ---
    logger.info(f"All {stock_count} stocks completed for genome {genome_id}, computing average")

    # 1. Fetch all per-stock results from Redis
    all_results = OptimizationService.get_optimization_results(optimization_id)
    per_stock_results = []
    for key, result in all_results.items():
        if key.startswith(f"{genome_id}:"):
            per_stock_results.append(result)

    if not per_stock_results:
        logger.warning(f"No per-stock results found for {genome_id}")
        return

    # 2. Get variable param names and values
    variable_param_names = metadata.variable_param_names
    params = AlgorithmParameters.from_dict(parameters)
    output_params = params.get_variable_params_for_output(variable_param_names)

    # 3. Compute averaged metrics
    averaged = compute_averaged_metrics(per_stock_results, genome_id, output_params)
    if not averaged:
        return

    # 4. Compute deltas vs averaged BASE
    base_result = OptimizationService.get_averaged_results(optimization_id).get("G_000")
    if base_result:
        averaged = calculate_averaged_deltas(averaged, base_result)

    # 5. Write to "Automated Results.csv" (averaged format)
    if genome_id == "G_000":
        averaged["Genome ID"] = "G_000 (BASE)"

    fieldnames = get_averaged_output_fieldnames(variable_param_names)
    await file_service.add_data_to_csv(AUTOMATED_RESULTS_FILE, [averaged], fieldnames)

    # Restore genome_id for Redis storage (without " (BASE)" suffix)
    storage_row = {**averaged}
    if genome_id == "G_000":
        storage_row["Genome ID"] = "G_000"

    # 6. Store averaged result in Redis
    OptimizationService.store_averaged_result(optimization_id, genome_id, storage_row)

    # 7. Smart filtering trigger
    if SMART_FILTERING_ENABLED and genome_id != "G_000":
        try:
            avg_payoff_ratio = float(averaged.get("Payoff Ratio", 0))
            param_values = output_params

            SmartFilteringService.record_genome_result(
                optimization_id, genome_id, avg_payoff_ratio, param_values
            )
            eliminated = SmartFilteringService.check_and_eliminate(
                optimization_id, genome_id, avg_payoff_ratio, param_values
            )
            if eliminated:
                for param, value in eliminated:
                    logger.info(
                        f"SMART FILTER: Eliminated {param}={value} "
                        f"after genome {genome_id} (avg PR: {avg_payoff_ratio:.2f})"
                    )
        except Exception as e:
            logger.error(f"Smart filtering error for {genome_id}: {e}")


async def load_server_data(stock_code: str) -> tuple[list[UnifiedTradeSignal], list[datetime | None]] | ErrorResponse:
    """Load data from API, return prepared signal array and trading day array."""
    try:
        API_URL = f'http://ete.stockfisher.com.hk/v1.1/debugHKEX/verifyData?TradeDay=&Code={stock_code}&verifyType=signal'
        headers = {'x-api-key': API_KEY}
        
        response = requests.get(API_URL, headers=headers)
        response.raise_for_status()

        result_data = response.json()
    
        if not result_data:
            logger.warning(f"Empty result for stock {stock_code}")
            return {"error": "Empty response", "detail": f"There is not any data in API for stock {stock_code}"}
        
        trade_days = []
        response_data: list[UnifiedTradeSignal] = []
        current_position = None
        
        for day in result_data: 
            trade_day = day.get("tradeday") or ""
            entry_date = day.get("entry_date") or ""
    
            date_to_check = trade_day if trade_day else entry_date
            if date_to_check:
                try:
                    check_date = datetime.fromisoformat(date_to_check.replace('Z', '+00:00')).replace(tzinfo=None)
                    start_date = datetime.fromisoformat(START_DATE)
                    end_date = datetime.fromisoformat(END_DATE)
                    
                    if start_date <= check_date <= end_date:
                        trade_days.append(datetime.fromisoformat(trade_day.replace('Z', '+00:00')).replace(tzinfo=None) if trade_day else None)
                    else:
                        continue
                except ValueError as e:
                    logger.debug(f"Failed to parse date {date_to_check}: {e}")
                    continue
            else:
                continue 

            today_action = day.get("today_open_action")
            pos_status = day.get("position_status")

            if today_action == "B" and pos_status == "I":
                current_position = {
                    "buy_signal" : day.get("entry_date"),
                    "entry_price": day.get("entry_price"),
                    "day_before_buy": day.get("prev_tradeday")
                }

            elif today_action == "S" and pos_status == "F":
                if current_position:
                    try:
                        buy_ts = current_position.get("buy_signal")
                        stop_ts = day.get("tradeday")
                        prev_buy = current_position.get("day_before_buy")
                        prev_sell = day.get("prev_tradeday")

                        unified = UnifiedTradeSignal(
                            buy_signal=datetime.fromisoformat(buy_ts.replace('Z', '+00:00')).replace(tzinfo=None) if buy_ts else None,
                            stop_signal=datetime.fromisoformat(stop_ts.replace('Z', '+00:00')).replace(tzinfo=None) if stop_ts else "Open position",
                            entry_price=_to_float_or_zero(current_position.get("entry_price")),
                            exit_price=_to_float_or_open(day.get("exit_price")),
                            day_before_buy=datetime.fromisoformat(prev_buy.replace('Z', '+00:00')).replace(tzinfo=None) if prev_buy else None,
                            day_before_sell=datetime.fromisoformat(prev_sell.replace('Z', '+00:00')).replace(tzinfo=None) if prev_sell else None,
                            gain_lose=None,
                            source="api"
                        )
                        response_data.append(unified)
                    except Exception as e:
                        logger.error(f"Error building unified trade signal: {e}")
                    current_position = None 
                else:
                    try:
                        stop_ts = day.get("tradeday")
                        prev_sell = day.get("prev_tradeday")
                        unified = UnifiedTradeSignal(
                            buy_signal=None,
                            stop_signal=datetime.fromisoformat(stop_ts.replace('Z', '+00:00')).replace(tzinfo=None) if stop_ts else "Open position",
                            entry_price=0.0,
                            exit_price=_to_float_or_open(day.get("exit_price")),
                            day_before_buy=None,
                            day_before_sell=datetime.fromisoformat(prev_sell.replace('Z', '+00:00')).replace(tzinfo=None) if prev_sell else None,
                            gain_lose=None,
                            source="api"
                        )
                        response_data.append(unified)
                    except Exception as e:
                        logger.error(f"Error building unified open position signal: {e}")

        if current_position:
            try:
                buy_ts = current_position.get("buy_signal")
                prev_buy = current_position.get("day_before_buy")
                unified = UnifiedTradeSignal(
                    buy_signal=datetime.fromisoformat(buy_ts.replace('Z', '+00:00')).replace(tzinfo=None) if buy_ts else None,
                    stop_signal="Open position",
                    entry_price=_to_float_or_zero(current_position.get("entry_price")),
                    exit_price="Open position",
                    day_before_buy=datetime.fromisoformat(prev_buy.replace('Z', '+00:00')) if prev_buy else None,
                    day_before_sell=None,
                    gain_lose=None,
                    source="api"
                )
                response_data.append(unified)
            except Exception as e:
                logger.error(f"Error building unified final position signal: {e}")
                
        return response_data, trade_days

    except Exception as e:
        logger.error(f'Error while loading data from API, stock: {stock_code}, {e}')
        return { "error": "API error", "detail": "API error"}

def convert_csv_to_unified(csv_row: dict) -> UnifiedTradeSignal:
    """Convert a CSV row to UnifiedTradeSignal."""
    try:
        buy_signal_str = csv_row.get('Buy Signal', '')
        stop_signal_str = csv_row.get('Stop Signal', '')
        
        buy_signal = datetime.strptime(buy_signal_str, '%Y-%m-%d') if buy_signal_str else None
        
        if stop_signal_str == "Open position":
            stop_signal = "Open position"
        else:
            try:
                stop_signal = datetime.strptime(stop_signal_str, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                try:
                    stop_signal = datetime.strptime(stop_signal_str, '%Y-%m-%d')
                except ValueError:
                    stop_signal = "Open position"
        
        entry_price = float(csv_row.get('Entry price', '0'))
        exit_price_str = csv_row.get('Exit price', '0')
        exit_price = float(exit_price_str) if exit_price_str != "Open position" else "Open position"
        
        gain_lose_str = csv_row.get('Gain/Lose', '')
        gain_lose = float(gain_lose_str) if gain_lose_str else None
        
        return UnifiedTradeSignal(
            buy_signal=buy_signal,
            stop_signal=stop_signal,
            entry_price=entry_price,
            exit_price=exit_price,
            day_before_buy=None,
            day_before_sell=None,
            gain_lose=gain_lose,
            source="csv"
        )
    except Exception as e:
        logger.error(f"Error converting CSV signal: {e}")
        raise


async def process_result_task(processing_data):
    """
    Result Processing Worker (Second Stage)
    Updated to support genome_id and parameters.
    """
    try:
        stock_code = processing_data.get('stock_code') or processing_data.get('stock')
        genome_id = processing_data.get('genome_id', 'G_000')
        parameters = processing_data.get('parameters', {})
        optimization_id = processing_data.get('optimization_id')
        
        logger.info(f"Starting processing data for stock_code: {stock_code}, genome: {genome_id}")

        # Load trade pairs from Redis (stored by algorithm worker)
        new_algo_data = _load_trade_pairs_from_redis(optimization_id, stock_code, genome_id)
        logger.info(f"Loaded {len(new_algo_data) if new_algo_data else 0} trade pairs from Redis for stock {stock_code}, genome: {genome_id}")

        if new_algo_data:
            try:
                # Save standard financial results
                await save_financial_results(
                    stock_code, 
                    new_algo_data, 
                    file_service,
                    genome_id=genome_id,
                    parameters=parameters
                )
                
                # If this is part of an optimization, save genome-specific results
                if optimization_id or genome_id != "G_000":
                    await save_genome_optimization_results(
                        stock_code=stock_code,
                        algo_data=new_algo_data,
                        genome_id=genome_id,
                        parameters=parameters,
                        optimization_id=optimization_id
                    )
                    
            except Exception as e:
                logger.error(f"Failed to save financial summary for {stock_code}/{genome_id}: {e}")
        else:
            # No trade pairs — still track per-genome stock completion so
            # cross-stock averaging and smart filtering can trigger correctly.
            if optimization_id:
                logger.info(f"No trade pairs for {stock_code}/{genome_id}, tracking genome completion only")
                try:
                    await _check_genome_completion(optimization_id, genome_id, parameters)
                except Exception as e:
                    logger.error(f"Failed genome completion check for {genome_id}: {e}")

        # API comparison (existing logic)
        api_result = await load_server_data(stock_code)

        if isinstance(api_result, dict):
            logger.error(f"API error for stock {stock_code}: {api_result}")
            unified_api_data: list[UnifiedTradeSignal] = []
            trade_days: list[datetime | None] = []
        else:
            unified_api_data, trade_days = api_result
                
        unified_algo_data = []
        if new_algo_data:
            for csv_row in new_algo_data:
                try:
                    unified_signal = convert_csv_to_unified(csv_row)
                    unified_algo_data.append(unified_signal)
                except Exception as e:
                    logger.error(f"Error converting CSV signal to unified: {e}")

        # Comparison Logic
        match_count = 0
        deviations = 0
        deviations_data = []
        unmatched_api_data = []

        for api_item in unified_api_data:
            found_match = False
            i = 0
            while i < len(unified_algo_data):
                csv_item = unified_algo_data[i]
                exact_buy = api_item.buy_signal == csv_item.buy_signal
                except_sell = api_item.stop_signal == csv_item.stop_signal

                if (exact_buy and except_sell):
                    match_count += 2
                    unified_algo_data.pop(i)
                    found_match = True
                    break
                
                # Check buy_signal with tolerance
                api_buy_index = None
                csv_buy_index = None
                    
                if api_item.buy_signal:
                    try:
                        api_buy_index = trade_days.index(api_item.buy_signal)
                    except ValueError:
                        pass
                    
                if csv_item.buy_signal:
                    try:
                        csv_buy_index = trade_days.index(csv_item.buy_signal)
                    except ValueError:
                        pass
                    
                if api_buy_index is not None and csv_buy_index is not None:
                    index_diff = abs(api_buy_index - csv_buy_index)
                    buy_match = index_diff <= 2
                else:
                    buy_match = False

                # Check stop_signal with tolerance
                api_stop_index = None
                csv_stop_index = None
                stop_match = False
                    
                if (api_item.stop_signal and csv_item.stop_signal and 
                    api_item.stop_signal != "Open position" and csv_item.stop_signal != "Open position"):
                    try:
                        if isinstance(api_item.stop_signal, datetime):
                            api_stop_index = trade_days.index(api_item.stop_signal)
                    except ValueError:
                        pass
                        
                    try:
                        if isinstance(csv_item.stop_signal, datetime):
                            csv_stop_index = trade_days.index(csv_item.stop_signal)
                    except ValueError:
                        pass
                        
                    if api_stop_index is not None and csv_stop_index is not None:
                        index_diff = abs(api_stop_index - csv_stop_index)
                        stop_match = index_diff <= 2
                    else:
                        stop_match = False

                elif api_item.stop_signal == csv_item.stop_signal:
                    stop_match = True
                
                if buy_match and not exact_buy and stop_match and not except_sell:
                    deviations += 2
                    deviations_data.append(f'Buy: Algo - {csv_item.buy_signal} / API - {api_item.buy_signal};')
                    deviations_data.append(f'Sell: Algo - {csv_item.stop_signal} / API - {api_item.stop_signal};')
                    unified_algo_data.pop(i)
                    found_match = True
                    break

                if (exact_buy or except_sell):
                    match_count += 1

                if (buy_match and not exact_buy or stop_match and not except_sell):
                    deviations += 1
                    if stop_match and not except_sell:
                        deviations_data.append(f'Sell: Algo - {csv_item.stop_signal} / API - {api_item.stop_signal};')
                    if buy_match and not exact_buy: 
                        deviations_data.append(f'Buy: Algo - {csv_item.buy_signal} / API - {api_item.buy_signal};')
                        
                if ((exact_buy and stop_match) or (except_sell and buy_match)):
                    unified_algo_data.pop(i)
                    found_match = True
                    break
                
                i += 1
            
            if not found_match:
                unmatched_api_data.append(f'Buy:{api_item.buy_signal}, Sell:{api_item.stop_signal};')

        # Calculate Statistics
        total_api_count = len(unified_api_data) * 2
        total_algo = len(new_algo_data) * 2 if new_algo_data else 0
        total_unmatched = total_api_count - match_count - deviations
        total_signals_for_accuracy = max(total_api_count, total_algo)
        
        if total_signals_for_accuracy > 0:
            total_match_percent = round(((match_count + deviations) / total_signals_for_accuracy * 100), 2)
        elif total_algo == 0 and total_api_count == 0:
            total_match_percent = 100.0
        else:
            total_match_percent = 0.0

        logger.info("------------------------------")
        logger.info(f"Stock: {stock_code}, Genome: {genome_id} processed. Match: {total_match_percent}%")

        # Push Comparison Results to Queue
        results_data = [{
            'stock_code': stock_code,
            'genome_id': genome_id,
            'optimization_id': optimization_id or '',
            'timestamp': datetime.now().isoformat(),
            'total_api': f'{total_api_count}',
            'total_algo': f'{total_algo}',
            'total_exact': f'{match_count}',
            'total_unmatched': f'{total_unmatched}',
            'with_deviation': f'{deviations}',
            'deviations_data': ' | '.join(deviations_data) if deviations_data else '',
            'unmatched_api': f'{len(unmatched_api_data)}',
            'unmatched_api_data': ' | '.join(unmatched_api_data) if unmatched_api_data else '',
            'unmatched_algo': f'{len(unified_algo_data)}',
            'unmatched_algo_data': ' | '.join([f'Buy:{item.buy_signal}, Sell:{item.stop_signal};' for item in unified_algo_data]) if unified_algo_data else '',
            'match_percent': f'{total_match_percent}'
        }]
        
        field_names = [
            'stock_code', 'genome_id', 'optimization_id', 'timestamp', 
            'total_api', 'total_algo', 'total_exact', 'total_unmatched', 
            'with_deviation', 'deviations_data', 'unmatched_api', 
            'unmatched_api_data', 'unmatched_algo', 'unmatched_algo_data', 
            'match_percent'
        ]
        
        # Queue comparison data to a separate file (not Automated Results)
        QueueService.add_to_file_write_queue(
            stock_code, 
            genome_id=genome_id,
            data={
                'results_data': results_data,
                'field_names': field_names,
                'optimization_id': optimization_id,
                'output_type': 'comparison'  # Mark as comparison data
            }
        )
        logger.info(f"File write task queued for stock: {stock_code}, genome: {genome_id}")

        # NOTE: Trade statistics are already stored in Redis by save_genome_optimization_results()
        # The comparison data below is only logged, not stored to Redis (to preserve correct Output format)

        # Update optimization progress if applicable
        if optimization_id:
            try:
                OptimizationService.increment_completed_tasks(optimization_id)
            except Exception as e:
                logger.error(f"Failed to update optimization progress: {e}")

        return {
            "final_result": {
                "stock_code": stock_code,
                "genome_id": genome_id,
                "status": "Success",
                "match_percent": total_match_percent
            },
        }
        
    except Exception as e:
        logger.error(f"Error processing result task {processing_data.get('task_id', 'unknown')}: {str(e)}")
        
        # Update failed task count if part of optimization
        optimization_id = processing_data.get('optimization_id')
        if optimization_id:
            try:
                OptimizationService.increment_failed_tasks(optimization_id)
            except Exception:
                pass
        
        raise e