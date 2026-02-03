import os
import logging
from datetime import datetime
from typing import List, Optional, TypedDict, Union, Tuple, Dict, Any
import requests
import csv
import pandas as pd

from app.services.file_service import FileService
from app.models.algorithm_models import UnifiedTradeSignal
from app.services.queue_service import QueueService

# --- CONFIGURATION ---
FIXED_DEPOSIT_AMOUNT = 10000.0
GENERAL_RESULTS_FILE = "general_results"

class ErrorResponse(TypedDict):
    error: str
    detail: Optional[str]

logger = logging.getLogger(__name__)

API_KEY = os.getenv('API_KEY')
START_DATE = "2009-03-06"
END_DATE = "2019-03-06"

file_service = FileService()

# --- HELPERS ---
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

async def save_financial_results(stock_code: str, algo_data: List[Dict[str, Any]], file_service: FileService):
    if not algo_data:
        return
    df = pd.DataFrame(algo_data)
    
    mapped_rows = []
    
    for _, row in df.iterrows():
        raw_gain = row.get("Gain/Lose")
        profit_pct = 0.0
        
        if pd.notna(raw_gain) and raw_gain != "":
            try:
                profit_pct = float(raw_gain)
            except (ValueError, TypeError):
                profit_pct = 0.0

        profit_usd = round(FIXED_DEPOSIT_AMOUNT * (profit_pct / 100.0), 2)

        stop_signal_val = str(row.get("Stop Signal", ""))
        exit_price_val = str(row.get("Exit price", ""))
        
        is_open = "Open position" in stop_signal_val or "Open position" in exit_price_val

        if is_open:
            exit_day_val = "" 
        else:
            exit_day_val = stop_signal_val

        # 4. Формування запису
        record = {
            "symbol": stock_code,
            "entryDay": row.get("Buy Signal", ""),
            "entryPrice": row.get("Entry price", ""),
            "exitDay": exit_day_val,
            "exitPrice": row.get("Exit price", ""),
            "profit": profit_usd,
            "Profit %": profit_pct,
            "Invested": FIXED_DEPOSIT_AMOUNT
        }
        mapped_rows.append(record)

    if not mapped_rows:
        return

    fieldnames = [
        "symbol", "entryDay", "entryPrice", 
        "exitDay", "exitPrice", 
        "profit", "Profit %", "Invested"
    ]
    
    await file_service.add_data_to_csv(GENERAL_RESULTS_FILE, mapped_rows, fieldnames)



async def load_server_data(stock_code:str) -> Union[Tuple[List[UnifiedTradeSignal], List[Optional[datetime]]], ErrorResponse]:
    """Завантажує дані з API, повертає підготовлений масив сигналів та масив торгових днів"""
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
        response_data: List[UnifiedTradeSignal] = []
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
                    # Closing a position without known entry (in this range)
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
    """Конвертує CSV рядок до UnifiedTradeSignal"""
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
    """
    try:
        logger.info(f"Starting processing data for stock_code: {processing_data['stock_code']}")
        stock_code = processing_data['stock_code']

        api_result = await load_server_data(stock_code)

        new_algo_data = await file_service.read_data_from_csv(stock_code)
        logger.info(f"Loaded {len(new_algo_data) if new_algo_data else 0} algorithm signals from CSV for stock {stock_code}")

        if new_algo_data:
            try:
                await save_financial_results(stock_code, new_algo_data, file_service)
            except Exception as e:
                logger.error(f"Failed to save financial summary for {stock_code}: {e}")

        if isinstance(api_result, dict):
            logger.error(f"API error for stock {stock_code}: {api_result}")
            unified_api_data: List[UnifiedTradeSignal] = []
            trade_days: List[Optional[datetime]] = []
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

        # 4. Comparison Logic
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
                
                api_buy_index = None
                csv_buy_index = None
                if api_item.buy_signal and api_item.buy_signal in trade_days:
                    api_buy_index = trade_days.index(api_item.buy_signal)
                if csv_item.buy_signal and csv_item.buy_signal in trade_days:
                    csv_buy_index = trade_days.index(csv_item.buy_signal)
                
                buy_match = False
                if api_buy_index is not None and csv_buy_index is not None:
                    if abs(api_buy_index - csv_buy_index) <= 2:
                        buy_match = True

                stop_match = False
                if api_item.stop_signal == csv_item.stop_signal:
                    stop_match = True
                elif (api_item.stop_signal != "Open position" and csv_item.stop_signal != "Open position"):
                    pass # Тут ваш код перевірки індексів Stop Signal
                
                # Це місце для вашої повної логіки перевірки deviations...
                # Припустимо, логіка перевірки виконалася
                # --- END OF MATCHING LOGIC BLOCK ---

                # Відновлюємо ваш точний код порівняння для коректної роботи:
                # (Вставте сюди повний блок while з вашого оригінального коду)
                # Оскільки я пишу код повністю, ось він:
                
                # Перевірка buy_signal
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

                # Перевірка stop_signal
                api_stop_index = None
                csv_stop_index = None
                    
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
                else:
                    stop_match = False
                
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
                if ((exact_buy and  stop_match) or (except_sell and buy_match)):
                    unified_algo_data.pop(i)
                    found_match = True
                    break
                
                i += 1
            
            if not found_match:
                unmatched_api_data.append(f'Buy:{api_item.buy_signal}, Sell:{api_item.stop_signal};')

        # 5. Calculate Statistics
        total_api_count = len(unified_api_data)*2
        total_algo = len(new_algo_data)*2 if new_algo_data else 0
        total_unmatched = total_api_count - match_count - deviations
        total_signals_for_accuracy = max(total_api_count, total_algo)
        
        if total_signals_for_accuracy > 0:
            total_match_percent = round(((match_count + deviations) / total_signals_for_accuracy * 100), 2)
        elif total_algo == 0 and total_api_count == 0:
            total_match_percent = 100.0
        else:
             total_match_percent = 0.0

        logger.info("------------------------------" )
        logger.info(f"Stock: {stock_code} processed. Match: {total_match_percent}%")

        # 6. Push Comparison Results to Queue
        results_data = [{
            'stock_code': stock_code,
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
        
        field_names = ['stock_code', 'timestamp', 'total_api','total_algo', 'total_exact', 'total_unmatched', 'with_deviation', 'deviations_data', 'unmatched_api', 'unmatched_api_data', 'unmatched_algo', 'unmatched_algo_data', 'match_percent' ]
        
        QueueService.add_to_file_write_queue(stock_code, results_data, field_names)
        logger.info(f"File write task queued for stock: {stock_code}")

        return {
            "final_result": {
                "stock_code": stock_code,
                "status": "Success",
                "match_percent": total_match_percent
            },
        }
        
    except Exception as e:
        logger.error(f"Error processing result task {processing_data.get('task_id', 'unknown')}: {str(e)}")
        raise e