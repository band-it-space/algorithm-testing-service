import time
import logging
import aiohttp
from datetime import datetime
from app.services.queue_service import QueueService
from app.workers.algo_func.get_db_data import get_stock_data_from_db, init_db_pool
from app.services.file_service import FileService
import os
import csv
from app.workers.algo_func.buy_signals import runAllBuyConditions, isBuy, OHLCV
from typing import Optional, Dict, Any, List, Union
from app.workers.algo_func.sell_signals import runAllSellConditions, isSell
from app.workers.algo_func.get_code_energy import calculate_energy_indicators_last_16_days
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

async def process_algorithm_task(task_data):
    """
    Воркер для обробки алгоритмів (перша черга)
    Тут ви додасте свою логіку розрахунків
    """

    try:
        logger.info(f"Processing algorithm task: {task_data['task_id']}")
        # await init_db_pool()
        stock_code = task_data['stock']

        # await get_stock_data_from_db(stock_code)
        
        await get_data_and_save_to_csv(stock_code, "2019-01-02")
        await signals_for_the_period(stock_code, "2025-10-16")
        await format_signals_csv_inplace(file_service=FileService(), file_name=stock_code)
        
        # Додаємо результат до другої черги
        processing_task_id = QueueService.add_to_result_processing_queue(stock_code)
        
        logger.info(f"Algorithm task {task_data['task_id']} completed, added to processing queue: {processing_task_id}")
        
        return task_data
        
    except Exception as e:
        logger.error(f"Error processing algorithm task {task_data['task_id']}: {str(e)}")
        raise e


async def get_data_and_save_to_csv(code: str, trade_date: str, file_service: "FileService" = None):
    if file_service is None:
        file_service = FileService()

    code_data_raw = await get_stock_data_from_db(code, "2025-10-16")

    first_date = code_data_raw[0]["date"] if code_data_raw else None
    effective_date = first_date if (first_date and first_date > trade_date) else trade_date

    fieldnames = [
        "code",
        "tradeday",
        "position_status",
        "next_open_action",
        "E1",
        "E2",
        "E3",
        "E4",
        "E5",
        "exit1",
        "close",
        "entry_price",
        "entry_date",
        "exit_price",
    ]

    csv_row = {
        "code": code,
        "tradeday": effective_date,
        "position_status": "F",
        "next_open_action": "N",
        "E1": 0,
        "E2": 0,
        "E3": 0,
        "E4": 0,
        "E5": 0,
        "exit1": 0,
        "close": 0,
        "entry_price": 0,
        "entry_date": 0,
        "exit_price": 0,
    }

    try:
        saved = file_service.add_data_to_csv(
            file_name=code,         
            data=[csv_row],
            fieldnames=fieldnames,
        )
        if saved:
            print(f"Дані успішно записано у файл data/{code}.csv")
            return csv_row
        else:
            print("Помилка під час запису CSV через FileService")
            return None

    except Exception as e:
        print(f"Помилка при записі CSV: {e}")
        return None

async def signals_for_the_period(code, trade_date):
    print("start")
    spy_data_raw = await get_stock_data_from_db("2800", trade_date)
    code_data_raw = await get_stock_data_from_db(code, trade_date)

    print(spy_data_raw[0])

    spy_data = [
        OHLCV(
            bar["date"],
            bar["open"],
            bar["high"],
            bar["low"],
            bar["close"],
            bar["volume"],
        )
        for bar in spy_data_raw
    ]
    code_data = [
        OHLCV(
            bar["date"],
            bar["open"],
            bar["high"],
            bar["low"],
            bar["close"],
            bar["volume"],
        )
        for bar in code_data_raw
    ]
    
    print(code_data[0])

    latest_signal = await get_latest_signal(code)
    logger.info(f"latest_signal {latest_signal}")

    if latest_signal is None:
        print(f"Немає сигналу для коду {code}")
        latest_signal = await get_data_and_save_to_csv(code, trade_date)

    # print(latest_signal)

    latest_date = pd.to_datetime(latest_signal["tradeday"]).tz_localize(None)

    filtered_code_data = []
    for bar in code_data:
        bar_date = pd.to_datetime(bar.date)
        if bar_date > latest_date:
            filtered_code_data.append(bar)

    print(len(filtered_code_data))
    
    results_batch: List[Dict[str, Any]] = []

    for bar in filtered_code_data:
        # print(bar)
        tradeday = pd.to_datetime(bar.date).tz_localize(None)

        filtered_spy = [
            bar for bar in spy_data if bar.date <= tradeday.strftime("%Y-%m-%d")
        ]
        filtered_code = [
            bar for bar in code_data if bar.date <= tradeday.strftime("%Y-%m-%d")
        ]

        energy_data = calculate_energy_indicators_last_16_days(
            tradeday.strftime("%Y-%m-%d"), filtered_code, filtered_spy
        )

        print(latest_signal)

        position_status = latest_signal["position_status"]

        if position_status == "F":
            buySignals = runAllBuyConditions(
                filtered_code, tradeday.strftime("%Y-%m-%d"), filtered_spy
            )
            buy = isBuy(buySignals)

            exit_price = 0
            if latest_signal['next_open_action'] == "S":
                exit_price = bar.open

            result = {
                "code": code,
                "tradeday": tradeday,
                "position_status": position_status,
                "next_open_action": "B" if buy else "N",
                "E1": energy_data["E1"],
                "E2": energy_data["E2"],
                "E3": energy_data["E3"],
                "E4": energy_data["E4"],
                "E5": energy_data["E5"],
                "exit1": buySignals.get("stopLoss"),
                "entry_price": filtered_code[-1].close if filtered_code else None,
                "close": filtered_code[-1].close if filtered_code else None,
                "entry_date": 0,
                "exit_price": exit_price 
            }
            latest_signal = {
                "entry_date": tradeday,
                "entry_price": filtered_code[-1].close if filtered_code else 0,
                "exit1": buySignals.get("stopLoss"),
                "position_status": "I" if buy else "F",
                "next_open_action": "B" if buy else "N",
            }
            results_batch.append(result)
            print(result)
            # return result

        elif position_status == "I":
            entry_date = latest_signal.get("entry_date")
            entry_price = latest_signal.get("entry_price")

            print(entry_date)
            print(entry_price)

            if latest_signal["next_open_action"] == "B":
                entry_date = tradeday.strftime("%Y-%m-%d")
                entry_price = bar.open
                print(entry_date)
                print(entry_price)


            # next_open_action = latest_signal.get("next_open_action")
            exit1 = to_float_or_none(latest_signal.get("exit1"))
            sellSignals = runAllSellConditions(
                filtered_code,
                filtered_spy,
                entry_date,
                to_float_or_none(entry_price),
                exit1,
                tradeday.strftime("%Y-%m-%d"),
            )
            sell = isSell(sellSignals['conditions'])
            new_stop_loss = sellSignals['stop_loss']
            result = {
                "code": code,
                "tradeday": tradeday,
                "position_status": position_status,
                "next_open_action": "S" if sell else "N",
                "E1": energy_data["E1"],
                "E2": energy_data["E2"],
                "E3": energy_data["E3"],
                "E4": energy_data["E4"],
                "E5": energy_data["E5"],
                "exit1": new_stop_loss,
                "entry_price": entry_price,
                "close": filtered_code[-1].close if filtered_code else None,
                "entry_date": entry_date,
                "exit_price": 0
            }
            latest_signal = {
                "entry_date": entry_date,
                "entry_price": entry_price,
                "exit1": new_stop_loss,
                "position_status": "F" if sell else "I",
                "next_open_action": "S" if sell else "N",
            }
            results_batch.append(result)
            print(result)
            # return result
            
    if results_batch:
        ok = append_to_signals_csv(results_batch, code)
        logger.info(f"Appended {len(results_batch)} rows to {code}.csv: {'OK' if ok else 'FAILED'}")        
            
def to_float_or_none(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if s == "" or s.lower() in ("none", "nan"):
        return None
    
    s = s.replace(" ", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None            

def append_to_signals_csv(
    result_data: Union[Dict[str, Any], List[Dict[str, Any]]],
    file_name,
    file_service: "FileService" = None,
) -> bool:
   
    if file_service is None:
        file_service = FileService()

    fieldnames = [
        "code","tradeday","position_status","next_open_action",
        "E1","E2","E3","E4","E5",
        "exit1","close","entry_price","entry_date","exit_price",
    ]

    def _to_datestr(v):
        try:
            ts = pd.to_datetime(v)
            return ts.strftime("%Y-%m-%d")
        except Exception:
            return v

    def _normalize_row(r: Dict[str, Any]) -> Dict[str, Any]:
        row = dict(r)
        if "tradeday" in row and row["tradeday"] not in (None, ""):
            row["tradeday"] = _to_datestr(row["tradeday"])
        if "entry_date" in row and row["entry_date"] not in (None, 0, ""):
            row["entry_date"] = _to_datestr(row["entry_date"])
        for f in fieldnames:
            row.setdefault(f, "")
        return row

    if isinstance(result_data, dict):
        rows = [_normalize_row(result_data)]
    else:
        rows = [_normalize_row(r) for r in result_data]

    return file_service.add_data_to_csv(
        file_name=file_name,
        data=rows,
        fieldnames=fieldnames,
    )



async def get_latest_signal(
    code: str,
    file_service: "FileService" = None,
) -> Optional[Dict[str, Any]]:
    file_name = code
    
    if file_service is None:
        file_service = FileService()

    rows: List[Dict[str, Any]] = await file_service.read_data_from_csv(file_name)
    if not rows:
        print(f"Немає записів у файлі data/{file_name}.csv")
        return None

    filtered = [r for r in rows if r.get("code") == code]
    if not filtered:
        print(f"Немає записів для коду {code}")
        return None

    def _parse_dt(v) -> Optional[pd.Timestamp]:
        try:
            return pd.to_datetime(v)
        except Exception:
            return None

    filtered = [r for r in filtered if _parse_dt(r.get("tradeday")) is not None]
    if not filtered:
        print(f"Немає валідних дат tradeday для коду {code}")
        return None

    latest = max(filtered, key=lambda r: _parse_dt(r.get("tradeday")))
    return latest

def _to_float_or_none(v):
    if v is None:
        return None
    if isinstance(v, (int, float, np.floating)):
        return float(v)
    s = str(v).strip()
    if s == "" or s.lower() in ("none", "nan"):
        return None
    s = s.replace(" ", "").replace(",", ".")
    try:
        return float(s)
    except Exception:
        return None

def _to_date_str_or_none(v):
    if v is None:
        return None
    try:
        return pd.to_datetime(v).strftime("%Y-%m-%d")
    except Exception:
        return None

async def format_signals_csv_inplace(
    file_service: "FileService" = None,
    file_name: str = "signals",
) -> Optional[pd.DataFrame]:
    if file_service is None:
        file_service = FileService()

    rows_raw: List[Dict[str, Any]] = await file_service.read_data_from_csv(file_name)
    if not rows_raw:
        return None

    df = pd.DataFrame(rows_raw)

    for col in ["next_open_action", "tradeday", "entry_date"]:
        if col not in df.columns:
            df[col] = np.nan

    for col in ["entry_price", "exit_price", "close"]:
        if col not in df.columns:
            df[col] = np.nan

    for col in ["entry_price", "exit_price", "close"]:
        df[col] = df[col].apply(_to_float_or_none)

    df = df.reset_index(drop=True)

    result_rows: List[Dict[str, Any]] = []

    s_rows = df[df["next_open_action"] == "S"]

    for idx in s_rows.index:
        row = df.loc[idx]

        if idx + 1 < len(df):
            next_row = df.loc[idx + 1]
            exit_price = next_row.get("exit_price", row.get("exit_price"))
            stop_signal_date = next_row.get("tradeday", row.get("tradeday"))
        else:
            exit_price = row.get("exit_price")
            stop_signal_date = row.get("tradeday")

        entry_price = row.get("entry_price")
        buy_signal_date = row.get("entry_date")

        entry_f = _to_float_or_none(entry_price)
        exit_f = _to_float_or_none(exit_price)

        gain = None
        if entry_f and exit_f:
            try:
                gain = round(((exit_f - entry_f) / entry_f) * 100.0, 2)
            except ZeroDivisionError:
                gain = None

        result_rows.append({
            "Buy Signal": _to_date_str_or_none(buy_signal_date) or "",
            "Stop Signal": _to_date_str_or_none(stop_signal_date) or "",
            "Entry price": entry_f if entry_f is not None else "",
            "Exit price": exit_f if exit_f is not None else "",
            "Gain/Lose": gain if gain is not None else "",
        })

    last_s_index = df[df["next_open_action"] == "S"].index.max()
    last_s_index = int(last_s_index) if pd.notna(last_s_index) else -1

    last_b = df[(df.index > last_s_index) & (df["next_open_action"] == "B")]
    if not last_b.empty:
        b_row = last_b.iloc[-1]
        b_index = b_row.name

        if b_index + 1 < len(df):
            buy_signal_date = df.iloc[b_index + 1].get("entry_date", b_row.get("entry_date"))
        else:
            buy_signal_date = b_row.get("entry_date")

        entry_price = _to_float_or_none(b_row.get("entry_price"))
        last_close = _to_float_or_none(df.iloc[-1].get("close"))

        gain_open = None
        if entry_price and last_close:
            try:
                gain_open = round(((last_close - entry_price) / entry_price) * 100.0, 2)
            except ZeroDivisionError:
                gain_open = None

        result_rows.append({
            "Buy Signal": _to_date_str_or_none(buy_signal_date) or "",
            "Stop Signal": "Open position",
            "Entry price": entry_price if entry_price is not None else "",
            "Exit price": "Open position",
            "Gain/Lose": gain_open if gain_open is not None else "",
        })

    out_df = pd.DataFrame(
        result_rows,
        columns=["Buy Signal", "Stop Signal", "Entry price", "Exit price", "Gain/Lose"]
    )
    
    cutoff = pd.Timestamp(2019, 1, 1)
    buy_dt  = pd.to_datetime(out_df["Buy Signal"], errors="coerce")
    stop_dt = pd.to_datetime(out_df["Stop Signal"], errors="coerce")
    out_df = out_df[(buy_dt >= cutoff) | (stop_dt >= cutoff)].reset_index(drop=True)

    def _fmt_price(x):
        return f"{x:.3f}" if isinstance(x, (int, float, np.floating)) else x

    for col in ["Entry price", "Exit price"]:
        out_df[col] = out_df[col].apply(_fmt_price)

    file_path = f"{file_service.data_dir}/{file_name}.csv"
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(out_df.columns))
        writer.writeheader()
        for r in out_df.to_dict(orient="records"):
            writer.writerow(r)

    return out_df
