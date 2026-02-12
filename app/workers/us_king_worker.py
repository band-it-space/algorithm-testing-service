import logging
import os

from app.services.queue_service import QueueService
from app.workers.algo_func.get_db_data import get_api_stocks_data
from app.services.file_service import FileService
from typing import Optional, Dict, Any, List, Union
from app.workers.algo_func.get_code_energy import calculate_energy_indicators_last_16_days, StockRecord, calculate_rsi, calculate_energy_indicators_single_day


logger = logging.getLogger(__name__)
API_KEY = os.getenv('API_KEY')

START_DATE = "2009-01-01"
END_DATE = "2019-03-06"
BENCHMARK_CODE = "SPY"


async def process_us_king_task(task_data):
    """
    Worker function to process US King algorithm task. This function will perform the following steps:
    """
    try:
        stock_code = task_data['stock']
        logger.info(f"Processing US_King task: {stock_code}")

        # First stage 1
        stock_data = await get_api_stocks_data(stock_code)
        benchmark_data = await get_api_stocks_data(BENCHMARK_CODE)

        if not stock_data or len(stock_data) < 300 or not benchmark_data or len(benchmark_data) < 300:
            logger.warning(f"Not enough data retrieved for stock {stock_code}")
            return
        
        aligned_data = align_stock_and_benchmark_data(stock_data, benchmark_data)
        
        if not aligned_data["dates"]:
            logger.error(f"No aligned data found for {stock_code}")
            return
        
        logger.info('Stage 1 completed: Data aligned')
        
        # Stage 2
        energy_indicators_all_days = calculate_energy_indicators_for_all_days(stock_code, aligned_data)
        
        if energy_indicators_all_days:
            sample_results = energy_indicators_all_days[-5:]
            logger.info(f"Sample energy indicators (last 5 days): {sample_results}")
        
        # TODO: Stage 3 
        
        
    except Exception as e:
        logger.error(f"Error processing US King task {task_data['task_id']}: {str(e)}")
        raise e
    
async def calculate_us_king_energy(stock_data: List[Dict], benchmark_data: List[Dict], trade_date: str):
    """
    Розрахунок енергетичних показників US King для конкретної дати
    """
    # Конвертуємо дані у формат OHLCV
    stock_ohlcv = [
        StockRecord(bar["date"], bar["open"], bar["high"], bar["low"], bar["close"], bar["volume"])
        for bar in stock_data
    ]
    benchmark_ohlcv = [
        StockRecord(bar["date"], bar["open"], bar["high"], bar["low"], bar["close"], bar["volume"])
        for bar in benchmark_data
    ]
    
    # Використовуємо існуючу функцію для розрахунку енергії
    energy_result = calculate_energy_indicators_last_16_days(
        trade_date, stock_ohlcv, benchmark_ohlcv
    )
    
    return energy_result


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


def calculate_energy_indicators_for_all_days(stock_code: str, aligned_data: Dict[str, List]) -> List[Dict]:
    """
    Stage 2: Calculate energy indicators E1-E5 for all aligned trading days.
    """
    stock_data = aligned_data["stock"]
    benchmark_data = aligned_data["benchmark"]
    dates = aligned_data["dates"]
    
    logger.info(f"Calculating energy indicators for {len(dates)} trading days...")
    
    energy_results = []
    
    for day_index in range(len(dates)):
        trade_day = dates[day_index]
        
        # Конвертуємо дані до поточного дня у формат StockRecord
        stock_slice = stock_data[:day_index + 1]
        benchmark_slice = benchmark_data[:day_index + 1]
        
        stock_records = [StockRecord(bar["date"], bar["open"], bar["high"], bar["low"], bar["close"], bar["volume"]) for bar in stock_slice]
        benchmark_records = [StockRecord(bar["date"], bar["open"], bar["high"], bar["low"], bar["close"], bar["volume"]) for bar in benchmark_slice]
        
        # Використовуємо існуючу функцію
        result = calculate_energy_indicators_last_16_days(trade_day, stock_records, benchmark_records)
        
        if "E1" in result and "E2" in result:
                # Успішний результат
                energy_indicators = {
                    "date": trade_day,
                    "E1": result["E1"],
                    "E2": result["E2"],
                    "E3": result["E3"],
                    "E4": result["E4"], 
                    "E5": result["E5"],
                    "day_index": day_index
                }
                energy_results.append(energy_indicators)
        
        
    
    logger.info(f"Energy indicators calculated for all {len(dates)} trading days")
    
    return energy_results