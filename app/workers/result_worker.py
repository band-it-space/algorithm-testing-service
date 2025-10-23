import os
from datetime import timedelta
import logging
from datetime import datetime
from typing import List, Optional, TypedDict, Union, Tuple
import requests

from app.services.file_service import FileService
from app.models.algorithm_models import UnifiedTradeSignal
from app.config.queue_config import file_write_queue
from app.services.queue_service import QueueService

class ErrorResponse(TypedDict):
    error: str
    detail: Optional[str]


logger = logging.getLogger(__name__)

API_KEY = os.getenv('API_KEY')
START_FROM = '2019'

file_service = FileService()

# helpers
def _to_float_or_zero(value) -> float:
    try:
        if value in (None, "", "Open position"):
            return 0.0
        return float(value)
    except Exception:
        return 0.0

def _to_float_or_open(value) -> Union[float, str]:
    try:
        if value in (None, "", "Open position"):
            return "Open position"
        return float(value)
    except Exception:
        return "Open position"

async def load_server_data(stock_code:str)-> Union[Tuple[List[UnifiedTradeSignal], List[Optional[datetime]]], ErrorResponse]:
    """Завантажує дані з API, повертає підготовлений масив сигналів та масив торгових днів"""

    try:
        API_URL =f'http://ete.stockfisher.com.hk/v1.1/debugHKEX/verifyData?TradeDay=&Code={stock_code}&verifyType=signal'
        headers = {
            'x-api-key': API_KEY,
        }
        response = requests.get(API_URL, headers=headers)
        response.raise_for_status()

        result_data = response.json()
    
        if not result_data:
            logger.warning(f"Empty result for stock {stock_code}")
            return {"error": "Empty response", "detail": f"There is not any data in API for stock {stock_code}"
        }
        #TODO форуємо вихідний масив
        trade_days = []
        response_data: List[UnifiedTradeSignal] = []
        current_position = None
        
        for  day in result_data: 
            trade_day = day.get("tradeday") or ""
            trade_days.append(datetime.fromisoformat(trade_day.replace('Z', '+00:00')).replace(tzinfo=None) if trade_day else None)
            entry_date = day.get("entry_date") or ""
    
        #TODO Не доаю значення раніше 2019
            date_to_check = trade_day if trade_day else entry_date
            if date_to_check and date_to_check[:4] >= START_FROM:
                pass
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

    except requests.HTTPError as e:
        logger.error(f"HTTP error for stock {stock_code}: {e}, status=    {response.status_code}")
        return { "error": "API error", "detail": str(e)}
    except Exception as e:
        logger.error(f'Error while loading data from API, stock: {stock_code}, {e}')
        return { "error": "API error", "detail": "API error"}

def convert_csv_to_unified(csv_row: dict) -> UnifiedTradeSignal:
    """Конвертує CSV рядок до UnifiedTradeSignal"""
    try:
        # Парсинг дат з різних форматів
        buy_signal_str = csv_row.get('Buy Signal', '')
        stop_signal_str = csv_row.get('Stop Signal', '')
        
        # Парсинг buy_signal (формат: 2016-12-08)
        buy_signal = datetime.strptime(buy_signal_str, '%Y-%m-%d') if buy_signal_str else None
        
        # Парсинг stop_signal (формат: 2017-08-07 00:00:00 або "Open position")
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
        
        # Конвертація цін
        entry_price = float(csv_row.get('Entry price', '0'))
        exit_price_str = csv_row.get('Exit price', '0')
        exit_price = float(exit_price_str) if exit_price_str != "Open position" else "Open position"
        
        # Парсинг gain_lose
        gain_lose_str = csv_row.get('Gain/Lose', '')
        gain_lose = float(gain_lose_str) if gain_lose_str else None
        
        return UnifiedTradeSignal(
            buy_signal=buy_signal,
            stop_signal=stop_signal,
            entry_price=entry_price,
            exit_price=exit_price,
            day_before_buy=None,  # CSV не має цих полів
            day_before_sell=None,
            gain_lose=gain_lose,
            source="csv"
        )
    except Exception as e:
        logger.error(f"Error converting CSV signal: {e}")
        raise


async def process_result_task(processing_data):
    """
    Воркер для обробки результатів (друга черга)
    Тут ви додасте свою логіку фінальних розрахунків
    """

    try:
        logger.info(f"Starting processing data for stock_code: {processing_data['stock_code']}")
        
        #TODO Отримую дані 
        stock_code = processing_data['stock_code']

        api_result = await load_server_data(stock_code)

        new_algo_data = await file_service.read_data_from_csv(stock_code)

        #TODO Підготовка 
        if isinstance(api_result, dict):
            logger.error(f"API error for stock {stock_code}: {api_result}")
            unified_api_data: List[UnifiedTradeSignal] = []
            trade_days: List[Optional[datetime]] = []
        else:
            unified_api_data, trade_days = api_result
                
        unified_algo_data = []
        for csv_row in new_algo_data:
            try:
                unified_signal = convert_csv_to_unified(csv_row)
                unified_algo_data.append(unified_signal)
            except Exception as e:
                logger.error(f"Error converting CSV signal to unified: {e}")

        #TODO Обробка даних
        match_count = 0
        deviations_signals = 0
        unmatched_api_data = []

        for api_item in unified_api_data:
            found_match = False
            i = 0
            while i < len(unified_algo_data):
                csv_item = unified_algo_data[i]
                
                if (api_item.buy_signal == csv_item.buy_signal and
                    api_item.stop_signal == csv_item.stop_signal):
                    match_count += 1

                    unified_algo_data.pop(i)
                    found_match = True
                    break
                
                else:
                    #buy_signal
                    api_buy_index = None
                    csv_buy_index = None
                    
                    if api_item.buy_signal:
                        try:
                            api_buy_index = trade_days.index(api_item.buy_signal)
                        except ValueError:
                            logger.info(f"API buy_signal {api_item.buy_signal} не знайдено в trade_days")
                    
                    if csv_item.buy_signal:
                        try:
                            csv_buy_index = trade_days.index(csv_item.buy_signal)
                        except ValueError:
                            logger.info(f"CSV buy_signal {csv_item.buy_signal} не знайдено в trade_days")
                    
                    if api_buy_index is not None and csv_buy_index is not None:
                        index_diff = abs(api_buy_index - csv_buy_index)
                        buy_match = index_diff <= 2
                    else:
                        buy_match = False
                    
                    #stop_signal
                    api_stop_index = None
                    csv_stop_index = None
                    
                    if (api_item.stop_signal and csv_item.stop_signal and 
                        api_item.stop_signal != "Open position" and csv_item.stop_signal != "Open position"):
                        try:
                            if isinstance(api_item.stop_signal, datetime):
                                api_stop_index = trade_days.index(api_item.stop_signal)
                        except ValueError:
                            logger.info(f"API stop_signal {api_item.stop_signal} не знайдено в trade_days")
                        
                        try:
                            if isinstance(csv_item.stop_signal, datetime):
                                csv_stop_index = trade_days.index(csv_item.stop_signal)
                        except ValueError:
                            logger.info(f"CSV stop_signal {csv_item.stop_signal} не знайдено в trade_days")
                        
                        if api_stop_index is not None and csv_stop_index is not None:
                            index_diff = abs(api_stop_index - csv_stop_index)

                            stop_match = index_diff <= 2
                        else:
                            stop_match = False

                    elif api_item.stop_signal == csv_item.stop_signal:
                        stop_match = True
                    else:
                        stop_match = False
                
                    if buy_match and stop_match:
                        deviations_signals += 1

                        unified_algo_data.pop(i)
                        found_match = True
                        break
                    else:
                        i += 1
            
            if not found_match:
                unmatched_api_data.append(api_item)  

        
        logger.info("------------------------------" )
        logger.info(f"Stock: {stock_code}")
        logger.info(f"Total API signals: {len(unified_api_data)}")
        logger.info(f"Total CSV signals: {len(new_algo_data)}")
        logger.info(f"Total exact matches: {match_count}" )
        logger.info(f"Deviations matches (±2 trading days): {deviations_signals}")
        logger.info(f"Unmatched CSV signals: {len(unified_algo_data)}")
        logger.info(f"Unmatched CSV values: {unified_algo_data}")
        logger.info(f"Unmatched API signals: {len(unmatched_api_data)}")
        logger.info(f"Unmatched API values: {unmatched_api_data}")
   
        # TODO Зберігаємо в черзі для безпечного додавання в файл
        results_data = [{
            'stock_code': stock_code,
            'timestamp': datetime.now().isoformat(),
            'total_api': f'{len(unified_api_data)}',
            'total_algo': f'{len(new_algo_data)}',
            'total_exact': f'{match_count}',
            'with_deviation': f'{deviations_signals}',
            'unmatched_api': f'{len(unmatched_api_data)}',
            'unmatched_algo': f'{len(unified_algo_data)}',
        }]
        
        field_names = ['stock_code', 'timestamp', 'total_api','total_algo', 'total_exact', 'with_deviation', 'unmatched_api', 'unmatched_algo' ]
        
        # Додаємо результат до третьої черги
        QueueService.add_to_file_write_queue(stock_code, results_data, field_names)
        logger.info(f"File write task queued for stock: {stock_code}")
        logger.info(f"Processing for {stock_code} compited")

        return {
            "final_result": {
            "stock_code": stock_code,
            "final_result": "Final result",
        },
        }
        
    except Exception as e:
        logger.error(f"Error processing result task {processing_data['task_id']}: {str(e)}")
        raise e
