import logging
import os
from dataclasses import dataclass
from typing import  Dict, Any, List, Literal
from datetime import datetime, timedelta

from app.services.queue_service import QueueService
from app.workers.algo_func.get_db_data import us_api_stocks_data
from app.workers.algo_func.types import OHLCV
from app.services.file_service import FileService
from app.workers.algo_func.get_code_energy import (
    calculate_E1,
    calculate_E2,
    calculate_E3,
    calculate_E4,
    calculate_E5
)
from app.workers.algo_func.buy_king import runAllBuyConditions_US, isBuy_US
from app.workers.algo_func.sell_king import runAllSellConditions_US, isSell_US


logger = logging.getLogger(__name__)
API_KEY = os.getenv('API_KEY')

START_DATE = "2023-04-17"
END_DATE = "2023-09-15;"
BENCHMARK_CODE = "SPY"

@dataclass
class DailyTradingState:
    trade_date: str
    day_index: int
    
    # === ENERGY ===
    E1: str
    E2: str
    E3: str
    E4: str
    E5: str
    
    position_status: str    # "I" or "F"
    next_open_action: str   # "B" or "S" or "N"
    today_open_action: str  # "B" or "S" or "N"
    
    entry_date: str | None
    entry_price: float
    exit_price: float
    exit1: float = 0.0


async def process_us_king_task(task_data):
    """
    Worker function to process US King algorithm task. This function will perform the following steps:
    """
    try:
        stock_code = task_data['stock']
        logger.info(f"Processing US_King task: {stock_code}")

        # Stage 1 - Get and align data
        stock_data = await us_api_stocks_data(stock_code, END_DATE)
        benchmark_data = await us_api_stocks_data(BENCHMARK_CODE, END_DATE)

        if not stock_data or len(stock_data) < 300 or not benchmark_data or len(benchmark_data) < 300:
            logger.warning(f"Not enough data retrieved for stock {stock_code}")
            return
        
        aligned_data = align_stock_and_benchmark_data(stock_data, benchmark_data)
        
        if not aligned_data["dates"]:
            logger.error(f"No aligned data found for {stock_code}")
            return
        
        logger.info('Stage 1 completed: Data aligned')

        #========================================
        #Stage 2 - Prepare indexes
        dates = aligned_data["dates"]
        
        start_idx = next((i for i, date in enumerate(dates) if date >= START_DATE), None)
        end_idx = next((i for i in range(len(dates) - 1, -1, -1) if dates[i] <= END_DATE), None)
        
        if start_idx is None or end_idx is None or start_idx > end_idx:
            logger.error(f"No data in range {START_DATE} to {END_DATE}")
            return
    
        logger.info(f"Stage 2 completed")

        #========================================
        #Stage 3 - Calculate buy/sell signals
        historical_data: List[DailyTradingState] = []
        
        # Initialize state variables
        current_position_status = "F"
        next_open_action = "N"
        today_open_action = "N"
        position_status = "F"
        entry_date = None
        entry_index = None
        entry_price = 0
        exit_price = 0
        exit1 = 0
        
        # Separate stop loss tracking
        s1_stop = 0  # Static stop
        s5_stop = 0  # Trailing stop
        

        first_day_data = await us_api_stocks_data(stock_code, END_DATE, verify_type="signal", trade_day=dates[start_idx] )
        first_signal_data = first_day_data[0] if first_day_data else {}
        
        current_position_status = first_signal_data.get("position_status", "F")
        
        # Using just to get position where entry_date is set, to start calculations from that day if already in position
        if current_position_status == "I":
            api_entry_date = first_signal_data.get("entry_date")
            entry_idx = dates.index(api_entry_date)
            start_idx = entry_idx - 1 
            current_position_status = "F"

            logger.info(f"Position already open. Starting calculations from entry_date: {api_entry_date} (idx={entry_idx})")

        # Calculate energy signals for the entire period first to have them ready for buy/sell signal calculations
        energy_signals = calculate_energy_signals_for_period(aligned_data, start_idx, end_idx)

        logger.info(f"Calculation range: {dates[start_idx]} to {dates[end_idx]}")
        
        for day_idx in range(start_idx, end_idx + 1):
            trade_date = dates[day_idx]
            
            energy_idx = next((i for i, e in enumerate(energy_signals) if e["idx"] == day_idx), None)
            if energy_idx is None:
                logger.error(f"Energy signals not found for day_idx {day_idx}")
                continue
            energy_data = energy_signals[energy_idx]
            
            #! === SIGNALS CALCULATION ===

            stock_ohlcv = [ 
                OHLCV(
                    date=bar["date"],
                    open=bar["open"],
                    high=bar["high"],
                    low=bar["low"],
                    close=bar["close"],
                    volume=bar.get("volume")
                ) for bar in aligned_data["stock"][:day_idx + 1]  # ← aligned_data["stock"]
            ]

            benchmark_ohlcv = [ 
                OHLCV(
                    date=bar["date"],
                    open=bar["open"],
                    high=bar["high"],
                    low=bar["low"],
                    close=bar["close"],
                    volume=bar.get("volume")
                ) for bar in aligned_data["benchmark"][:day_idx + 1]  # ← aligned_data["benchmark"]
            ]
            

            if current_position_status == "I":
                # Open position on today's open if signaled yesterday
                if next_open_action == "B":
                    entry_date = trade_date
                    entry_index = day_idx
                    entry_price = stock_ohlcv[-1].open
                
                # Safety check: entry_date must be set when in position
                if entry_date is None or entry_index is None:
                    logger.error(f"Entry date/index is None while in position on {trade_date}. Skipping sell checks.")
                    continue
                
                # Ми В позиції -> перевіряємо Sell сигнали
                logger.info(f"------- Running US King Sell conditions for {trade_date} -------")
                logger.info(f"Entry date: {entry_date}, Entry index: {entry_index}, Entry price: {entry_price}, exit1: {exit1}")
                
                sell_results = runAllSellConditions_US(
                    stock_ohlcv, 
                    benchmark_ohlcv, 
                    entry_index,
                    entry_price, 
                    s1_stop,
                    s5_stop,
                    energy_signals=energy_signals,
                    current_day_idx=day_idx
                )
                
                sell_signals = sell_results["conditions"]
                s1_stop = sell_results["s1_stop"]
                s5_stop = sell_results["s5_stop"]
                exit1 = sell_results["exit1"]
                
                sell_results_formatted = ", ".join(
                    f"{key}:1" if sell_signals.get(key, False) else f"{key}:0" 
                    for key in ['S1', 'S4', 'S5', 'S6', 'S7', 'S8', 'S9', 'S10', 'S11', 'S12', 'S13', 'S14', 'S15', 'S16', 'S17', 'S18', 'S19', 'S20']
                )
                logger.info(f"Sell results: {sell_results_formatted}")
                
                is_sell = isSell_US(sell_signals)
                
                position_status = current_position_status
                today_open_action = next_open_action
                next_open_action = "S" if is_sell else "N"
                
                # If selling, reset entry info for next iteration
                if is_sell:
                    current_position_status = "F"
                    # Set exit price as next day's open price
                    if day_idx + 1 < len(aligned_data["stock"]):
                        exit_price = aligned_data["stock"][day_idx + 1]["open"]
                    else:
                        #TODO Fallback to current day close if next day data is not available 
                        logger.info(f"No next day data for exit price on {trade_date}")
                        exit_price = stock_ohlcv[-1].close
                else:
                    current_position_status = "I"
                
                logger.info(f"For date {trade_date}, is_sell_signal: {is_sell}")

            elif current_position_status == "F":
                # Ми НЕ в позиції -> перевіряємо BUY сигнали
                logger.info(f"------- Running US King Buy conditions for {trade_date} -------")
                
                buy_results = runAllBuyConditions_US(stock_ohlcv, benchmark_ohlcv, trade_date)
                buy_results_formatted = ",".join(
                    "1" if buy_results.get(key, False) else "0" 
                    for key in ['B1', 'B8', 'B9', 'B10', 'B11', 'B12', 'B13', 'B18', 'B20', 'B21', 'B22']
                )
                logger.info(f"Buy results: {buy_results_formatted}, stop_loss: {buy_results.get('stop_loss')}")

                is_buy = isBuy_US(buy_results)
                
                position_status = current_position_status
                today_open_action = next_open_action
                
                if is_buy:
                    exit1 = s1_stop = buy_results.get("stop_loss", 0)
                    current_position_status = "I"
                    next_open_action = "B"
                else:
                    current_position_status = "F"
                    next_open_action = "N"

                logger.info(f"For date {trade_date}, is_buy_signal: {is_buy}")

            
            daily_state = DailyTradingState(
                trade_date=trade_date,
                day_index=day_idx,
                E1=energy_data["E1"],
                E2=energy_data["E2"],
                E3=energy_data["E3"],
                E4=energy_data["E4"],
                E5=energy_data["E5"],
                position_status=position_status,
                next_open_action=next_open_action,
                today_open_action=today_open_action,
                exit1=exit1,
                entry_date=entry_date,
                entry_price=entry_price,
                exit_price=exit_price
            )

            historical_data.append(daily_state)
            
            # Position was closed, reset for next buy
            if position_status == "I" and next_open_action == "S":
                entry_date = None
                entry_index = None
                entry_price = 0
                s1_stop = 0
                s5_stop = 0
                exit1 = 0

            exit_price=0

        logger.info(f"Stage 3 completed!")

        #========================================
        # Stage 4 - Signal comparison
        logger.info("Starting Stage 4: Signal comparison")
        
        api_data = await us_api_stocks_data(stock_code, END_DATE, verify_type="signal")
        filtered_api_data = [ 
            row for row in api_data if START_DATE <= datetime.fromisoformat(row["date"].replace('Z', '+00:00')).strftime("%Y-%m-%d") <= END_DATE
        ]
        
        comparison_results = compare_signals_with_tolerance(historical_data, filtered_api_data)

        # Log detailed results
        logger.info(f"=== Signal Comparison Results ===")
        logger.info(f"Total API signals: {comparison_results['total_api']}")
        logger.info(f"Total Algo signals: {comparison_results['total_algo']}")
        logger.info(f"Exact matches: {comparison_results['total_exact']}")
        logger.info(f"Deviation matches (±2 days): {comparison_results['with_deviation']}")
        logger.info(f"Unmatched API: {comparison_results['unmatched_api']}")
        logger.info(f"Unmatched Algo: {comparison_results['unmatched_algo']}")
        logger.info(f"Match percent: {comparison_results['match_percent']}%")

        # Save comparison report
        await save_comparison_report(stock_code, comparison_results)

        logger.info(f"Stage 4 completed: Signal comparison finished")
    except Exception as e:
        logger.error(f"Error processing US King task {task_data['task_id']}: {str(e)}")
        raise e


def calculate_energy_signals_for_period(
    aligned_data: Dict[str, List], 
    start_idx: int, 
    end_idx: int
) -> List[Dict[str, Any]]:
    """
    Calculate E1-E5 energy signals for each day in the period.
    Starts 16 days earlier than start_idx to have history for S9 calculation.
    
    Args:
        aligned_data: Aligned stock and benchmark data
        start_idx: Start index of testing period
        end_idx: End index of testing period
        
    Returns:
        List of dictionaries with E1-E5 signals for each day
    """
    stock_data = aligned_data["stock"]
    benchmark_data = aligned_data["benchmark"]
    dates = aligned_data["dates"]
    
    # Start 16 days earlier for S9 calculation (needs 16-day average)
    calc_start_idx = max(0, start_idx - 15)
    
    logger.info(f"Calculating energy signals from index {calc_start_idx} to {end_idx}")
    logger.info(f"Date range: {dates[calc_start_idx]} to {dates[end_idx]}")
    
    # Convert to arrays for efficient calculation
    close = [bar["close"] for bar in stock_data]
    high = [bar["high"] for bar in stock_data]
    low = [bar["low"] for bar in stock_data]
    sdate = dates
    
    close_spy = [bar["close"] for bar in benchmark_data]
    sdate_spy = dates  # Already aligned
    
    energy_signals = []
    
    for idx in range(calc_start_idx, end_idx + 1):
        current_date = dates[idx]
        
        # Calculate energy indicators for this day
        if idx >= 66:  # Minimum data required
            E1 = calculate_E1(high, low, close, idx)
            E2 = calculate_E2(close, idx)
            E3 = calculate_E3(close, idx)
            E4 = calculate_E4(close, close_spy, sdate, sdate_spy, idx)
            E5 = calculate_E5(high, low, close, idx)
            
            # Calculate total Energy (sum of E1-E5)
            energy_sum = sum([
                1 if E1 == "1" else 0,
                1 if E2 == "1" else 0,
                1 if E3 == "1" else 0,
                1 if E4 == "1" else 0,
                1 if E5 == "1" else 0
            ])
        else:
            E1 = E2 = E3 = E4 = E5 = "N/A"
            energy_sum = 0
        
        energy_signals.append({
            "date": current_date,
            "idx": idx,
            "E1": E1,
            "E2": E2,
            "E3": E3,
            "E4": E4,
            "E5": E5,
            "energy": energy_sum,
            "is_test_period": idx >= start_idx
        })
    
    logger.info(f"Calculated energy signals for {len(energy_signals)} days")
    logger.info(f"Test period days: {sum(1 for s in energy_signals if s['is_test_period'])}")
    
    return energy_signals


def align_stock_and_benchmark_data(stock_data: List[Dict], benchmark_data: List[Dict]) -> Dict[str, List]:
    """
    Stage 1: Align stock and benchmark data by date.
    """
    
    stock_dict = {bar["date"]: bar for bar in stock_data}
    benchmark_dict = {bar["date"]: bar for bar in benchmark_data}
    
    stock_dates = set(stock_dict.keys())
    benchmark_dates = set(benchmark_dict.keys())
    common_dates = sorted(stock_dates & benchmark_dates)
    
    if not common_dates:
        logger.error("No common dates found between stock and benchmark data")
        return {"dates": [], "stock": [], "benchmark": []}
    
    aligned_stock = []
    aligned_benchmark = []
    
    for date in common_dates:
        aligned_stock.append(stock_dict[date])
        aligned_benchmark.append(benchmark_dict[date])
    
    return {
        "dates": common_dates,
        "stock": aligned_stock,
        "benchmark": aligned_benchmark
    }


def compare_signals_with_tolerance(
    historical_data: List[DailyTradingState], 
    api_data: List[Dict],
    tolerance_days: int = 2
) -> Dict[str, Any]:
    """
    Compare calculated signals with API data, allowing ±2 trading days tolerance.
    
    Args:
        historical_data: Calculated trading states
        api_data: Filtered API signal data
        tolerance_days: Number of trading days tolerance for signal matching
        
    Returns:
        Dictionary with comparison statistics
    """
    
    # Trading days from filtered API data (already sorted)
    trade_days = [row['date'] for row in api_data]
    date_to_index = {date: idx for idx, date in enumerate(trade_days)}
    
    # Extract buy/sell signals from calculated data
    calc_buy_signals = [state.trade_date for state in historical_data if state.next_open_action == "B"]
    calc_sell_signals = [state.trade_date for state in historical_data if state.next_open_action == "S"]
    
    # Extract buy/sell signals from API data
    api_buy_signals = [row['date'] for row in api_data if row['next_open_action'] == "B"]
    api_sell_signals = [row['date'] for row in api_data if row['next_open_action'] == "S"]
    
    # Compare signals
    buy_results = _compare_signal_lists(
        calc_buy_signals.copy(), 
        api_buy_signals, 
        trade_days,
        date_to_index,
        tolerance_days,
        "Buy"
    )
    
    sell_results = _compare_signal_lists(
        calc_sell_signals.copy(), 
        api_sell_signals, 
        trade_days,
        date_to_index,
        tolerance_days,
        "Sell"
    )
    
    # Combine results
    total_api = len(api_buy_signals) + len(api_sell_signals)
    total_algo = len(calc_buy_signals) + len(calc_sell_signals)
    total_exact = buy_results['exact'] + sell_results['exact']
    with_deviation = buy_results['deviation'] + sell_results['deviation']
    unmatched_api = buy_results['unmatched_api'] + sell_results['unmatched_api']
    unmatched_algo = buy_results['unmatched_algo'] + sell_results['unmatched_algo']
    
    deviations_data = buy_results['deviations_data'] + sell_results['deviations_data']
    unmatched_api_data = buy_results['unmatched_api_data'] + sell_results['unmatched_api_data']
    unmatched_algo_data = buy_results['unmatched_algo_data'] + sell_results['unmatched_algo_data']
    
    # Calculate match percentage
    total_unmatched = unmatched_api
    if max(total_api, total_algo) > 0:
        match_percent = round(((total_exact + with_deviation) / max(total_api, total_algo)) * 100, 2)
    else:
        match_percent = 0.0
    
    return {
        'total_api': total_api,
        'total_algo': total_algo,
        'total_exact': total_exact,
        'total_unmatched': total_unmatched,
        'with_deviation': with_deviation,
        'deviations_data': deviations_data,
        'unmatched_api': unmatched_api,
        'unmatched_api_data': unmatched_api_data,
        'unmatched_algo': unmatched_algo,
        'unmatched_algo_data': unmatched_algo_data,
        'match_percent': match_percent
    }


def _compare_signal_lists(
    calc_signals: List[str], 
    api_signals: List[str], 
    trade_days: List[str],
    date_to_index: Dict[str, int],
    tolerance_days: int,
    signal_type: str
) -> Dict[str, Any]:
    """
    Compare calculated and API signals with tolerance.
    
    Args:
        calc_signals: Calculated signal dates (will be modified)
        api_signals: API signal dates
        trade_days: All trading dates (sorted)
        date_to_index: Date to index mapping
        tolerance_days: Number of trading days tolerance
        signal_type: "Buy" or "Sell"
    
    Returns:
        Dictionary with comparison results
    """
    
    exact = 0
    deviation = 0
    unmatched_api = 0
    deviations_data = []
    unmatched_api_data = []
    
    # Step 1: Check each API signal
    for api_date in api_signals:
        # Check exact match
        if api_date in calc_signals:
            exact += 1
            calc_signals.remove(api_date)
            continue
        
        # Check deviation match (±tolerance_days)
        if api_date not in date_to_index:
            unmatched_api += 1
            unmatched_api_data.append(f"{signal_type}: {api_date};")
            continue
        
        api_idx = date_to_index[api_date]
        found_deviation = False
        
        for offset in range(-tolerance_days, tolerance_days + 1):
            if offset == 0:
                continue
            
            check_idx = api_idx + offset
            if 0 <= check_idx < len(trade_days):
                check_date = trade_days[check_idx]
                if check_date in calc_signals:
                    deviation += 1
                    deviations_data.append(f"{signal_type}: Algo - {check_date} / API - {api_date};")
                    calc_signals.remove(check_date)  # Remove matched signal
                    found_deviation = True
                    break
        
        if not found_deviation:
            unmatched_api += 1
            unmatched_api_data.append(f"{signal_type}: {api_date};")
    
    # Step 2: Remaining calc_signals are unmatched algo signals
    unmatched_algo = len(calc_signals)
    unmatched_algo_data = [f"{signal_type}: {date};" for date in calc_signals]
    
    
    return {
        'exact': exact,
        'deviation': deviation,
        'unmatched_api': unmatched_api,
        'unmatched_algo': unmatched_algo,
        'deviations_data': deviations_data,
        'unmatched_api_data': unmatched_api_data,
        'unmatched_algo_data': unmatched_algo_data
    }


async def save_comparison_report(stock_code: str, comparison_results: Dict[str, Any]):
    """Save comparison report to CSV file."""
    try:
        results_data = [{
            'stock_code': stock_code,
            'timestamp': datetime.now().isoformat(),
            'total_api': str(comparison_results['total_api']),
            'total_algo': str(comparison_results['total_algo']),
            'total_exact': str(comparison_results['total_exact']),
            'total_unmatched': str(comparison_results['total_unmatched']),
            'with_deviation': str(comparison_results['with_deviation']),
            'deviations_data': ' | '.join(comparison_results['deviations_data']) if comparison_results['deviations_data'] else '',
            'unmatched_api': str(comparison_results['unmatched_api']),
            'unmatched_api_data': ' | '.join(comparison_results['unmatched_api_data']) if comparison_results['unmatched_api_data'] else '',
            'unmatched_algo': str(comparison_results['unmatched_algo']),
            'unmatched_algo_data': ' | '.join(comparison_results['unmatched_algo_data']) if comparison_results['unmatched_algo_data'] else '',
            'match_percent': str(comparison_results['match_percent'])
        }]
        
        field_names = [
            'stock_code', 'timestamp', 'total_api', 'total_algo', 'total_exact', 
            'total_unmatched', 'with_deviation', 'deviations_data', 'unmatched_api', 
            'unmatched_api_data', 'unmatched_algo', 'unmatched_algo_data', 'match_percent'
        ]
        
        file_service = FileService()
        await file_service.add_data_to_csv('us_king_results', results_data, field_names)
        
        logger.info(f"Comparison report saved to us_king_results.csv")
    except Exception as e:
        logger.error(f"Failed to save comparison report: {str(e)}")

