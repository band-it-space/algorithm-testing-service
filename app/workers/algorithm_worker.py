import pandas as pd
import numpy as np
import logging
import os
import csv
import requests
from datetime import datetime
from bisect import bisect_right
from typing import Optional, Dict, Any, List, Union

from app.services.queue_service import QueueService
from app.workers.algo_func.get_db_data import get_stock_data_from_db, init_db_pool, warm_spy_cache
from app.services.file_service import FileService
from app.workers.algo_func.buy_signals import runAllBuyConditions, isBuy, OHLCV
from app.workers.algo_func.sell_signals import runAllSellConditions, isSell
from app.workers.algo_func.get_code_energy import calculate_energy_indicators_last_16_days
from app.workers.algo_func.precomputed_indicators import PrecomputedIndicators, is_buy_fast
from app.models.algorithm_models import AlgorithmParameters
from app.config.logging_config import get_algorithm_debug_mode, get_log_progress_interval
from app.utils.performance_profiler import timed, TimingContext, get_profiler

logger = logging.getLogger(__name__)
API_KEY = os.getenv('API_KEY')

# Date range from environment (with fallback defaults)
START_DATE = os.getenv('OPTIMIZATION_START_DATE', '2016-01-01')
END_DATE = os.getenv('OPTIMIZATION_END_DATE', '2026-02-02')

# Module-level debug settings
ALGORITHM_DEBUG = get_algorithm_debug_mode()
LOG_INTERVAL = get_log_progress_interval()


def _build_date_index(data: List[OHLCV]) -> Dict[str, int]:
    """
    Build a date-to-index mapping for O(1) lookups.
    
    Args:
        data: List of OHLCV objects sorted by date ascending
        
    Returns:
        Dictionary mapping date strings to their index in the list
    """
    return {bar.date: i for i, bar in enumerate(data)}


def _find_end_index(date_index: Dict[str, int], sorted_dates: List[str], target_date: str, data_len: int) -> int:
    """
    Find the index for slicing data up to target_date inclusive.
    
    Uses the date index for O(1) lookup when date exists,
    falls back to binary search for O(log n) when date doesn't exist.
    
    Args:
        date_index: Mapping of dates to indices
        sorted_dates: Sorted list of date strings
        target_date: The target date string (YYYY-MM-DD)
        data_len: Length of the data list
        
    Returns:
        End index for slicing (inclusive)
    """
    # O(1) lookup if date exists in data
    if target_date in date_index:
        return date_index[target_date]
    
    # Binary search fallback for dates not in the dataset
    # bisect_right gives us the insertion point, subtract 1 to get last date <= target
    idx = bisect_right(sorted_dates, target_date)
    if idx == 0:
        return -1  # No data before target date
    return idx - 1


@timed("algorithm_task_total")
async def process_algorithm_task(task_data):
    """
    Воркер для обробки алгоритмів (перша черга)
    Optimized with data caching and pre-processing.
    """
    try:
        stock_code = task_data['stock']
        genome_id = task_data.get('genome_id', 'G_000')
        optimization_id = task_data.get('optimization_id')
        params_dict = task_data.get('parameters', {})
        params = AlgorithmParameters.from_dict(params_dict)
        
        logger.info(f"Processing algorithm task: {stock_code}, genome: {genome_id}, optimization: {optimization_id}")
        
        with TimingContext("db_pool_init"):
            await init_db_pool()

        # Warm SPY cache once per batch (idempotent)
        with TimingContext("spy_cache_warm"):
            await warm_spy_cache(END_DATE)

        # Use genome-specific CSV filename to avoid concurrency issues
        genome_file_name = f"{stock_code}_{genome_id}"

        # Step 3.2.1 — Fetch data once, reuse across all steps
        with TimingContext("fetch_all_data"):
            code_data_raw = await get_stock_data_from_db(stock_code, END_DATE)
            spy_data_raw = await get_stock_data_from_db("2800", END_DATE)

        logger.info('Starting get_data_and_save_to_csv')
        seed_row = await get_data_and_save_to_csv(stock_code, START_DATE, genome_id,
                                                    file_name=genome_file_name,
                                                    code_data_raw=code_data_raw)
        logger.info('Finished get_data_and_save_to_csv')

        logger.info('Starting signals_for_the_period')
        await signals_for_the_period(stock_code, END_DATE, params, genome_id,
                                      file_name=genome_file_name,
                                      code_data_raw=code_data_raw,
                                      spy_data_raw=spy_data_raw,
                                      initial_signal=seed_row)
        logger.info('Finished signals_for_the_period')

        logger.info('Starting format_signals_csv_inplace')
        await format_signals_csv_inplace(file_service=FileService(), file_name=genome_file_name, genome_id=genome_id)
        logger.info('Finished format_signals_csv_inplace')

        processing_task_id = QueueService.add_to_result_processing_queue(
            stock_code, 
            genome_id=genome_id, 
            parameters=params.to_dict(),
            optimization_id=optimization_id,
            results={"genome_file_name": genome_file_name}
        )
        
        logger.info(f"Algorithm task {task_data['task_id']} completed, genome: {genome_id}, added to processing queue: {processing_task_id}")
        
        # Log profiling summary periodically
        profiler = get_profiler()
        if ALGORITHM_DEBUG:
            profiler.log_summary()
        
        return task_data
        
    except Exception as e:
        logger.error(f"Error processing algorithm task {task_data['task_id']}: {str(e)}")
        raise e


# Step 3.2.2 — Update get_data_and_save_to_csv() signature to accept pre-fetched data
async def get_data_and_save_to_csv(code: str, trade_date: str, genome_id: str = "G_000",
                                    file_service: "FileService" = None,
                                    file_name: str = None,
                                    code_data_raw=None):
    if file_service is None:
        file_service = FileService()

    # Use genome-specific file name if provided, otherwise fall back to stock code
    csv_file_name = file_name or code

    # Replace the internal fetch with:
    if code_data_raw is None:
        code_data_raw = await get_stock_data_from_db(code, END_DATE)

    code_data = code_data_raw

    # For initial signal, use START_DATE or first available date
    # This ensures the main loop processes all dates from START_DATE to END_DATE
    effective_date = START_DATE
    if code_data and code_data[0]["date"] > START_DATE:
        effective_date = code_data[0]["date"]

    fieldnames = [
        "code", "genome_id", "tradeday", "position_status", "next_open_action",
        "E1", "E2", "E3", "E4", "E5",
        "exit1", "close", "entry_price", "entry_date", "exit_price",
    ]

    csv_row = {
        "code": code,
        "genome_id": genome_id,
        "tradeday": effective_date,
        "position_status": "F",
        "next_open_action": "N",
        "E1": 0, "E2": 0, "E3": 0, "E4": 0, "E5": 0,
        "exit1": 0, "close": 0, "entry_price": 0, "entry_date": 0, "exit_price": 0,
    }

    try:
        saved = await file_service.add_data_to_csv(
            file_name=csv_file_name, data=[csv_row], fieldnames=fieldnames,
        )
        return csv_row if saved else None
    except Exception as e:
        print(f"Помилка при записі CSV: {e}")
        return None


@timed("signals_for_the_period")
async def signals_for_the_period(code, trade_date, params: AlgorithmParameters = None, 
                                  genome_id: str = "G_000", file_name: str = None,
                                  code_data_raw=None, spy_data_raw=None,
                                  initial_signal=None):
    """
    Main signal calculation loop with optimized data handling.
    
    Key optimizations:
    1. Pre-sort data once at start
    2. Build date-to-index mappings for O(1) lookups
    3. Use index-based slicing instead of list comprehension filtering
    4. Pre-parse dates to avoid repeated pd.to_datetime() calls
    """
    # Use genome-specific file name if provided
    csv_file_name = file_name or code

    if params is None:
        params = AlgorithmParameters()
    
    print("start")
    
    # Fetch data (leverages cache if available)
    if spy_data_raw is None:
        with TimingContext("fetch_spy_data"):
            spy_data_raw = await get_stock_data_from_db("2800", trade_date)
    
    if code_data_raw is None:
        with TimingContext("fetch_code_data"):
            code_data_raw = await get_stock_data_from_db(code, trade_date)
    
    # Step 3.3.2 — Convert to OHLCV only if needed (might already be OHLCV from cache)
    with TimingContext("convert_to_ohlcv"):
        if code_data_raw and isinstance(code_data_raw[0], dict):
            code_data = [
                OHLCV(bar["date"], bar["open"], bar["high"], bar["low"], bar["close"], bar["volume"])
                for bar in code_data_raw
            ]
        else:
            code_data = code_data_raw

        if spy_data_raw and isinstance(spy_data_raw[0], dict):
            spy_data = [
                OHLCV(bar["date"], bar["open"], bar["high"], bar["low"], bar["close"], bar["volume"])
                for bar in spy_data_raw
            ]
        else:
            spy_data = spy_data_raw

    # Build date-to-index mappings for O(1) lookups (OPTIMIZATION: Task 3.1)
    with TimingContext("build_date_index"):
        spy_date_index = _build_date_index(spy_data)
        code_date_index = _build_date_index(code_data)
        
        # Also create sorted date lists for binary search fallback
        spy_dates_sorted = [bar.date for bar in spy_data]
        code_dates_sorted = [bar.date for bar in code_data]
    
    # Pre-compute all indicators once for O(1) lookups
    with TimingContext("precompute_indicators"):
        from app.workers.algo_func.precomputed_indicators import OHLCV as PrecompOHLCV
        precomp_code = [PrecompOHLCV(b.date, b.open, b.high, b.low, b.close, b.volume) for b in code_data]
        precomp_spy = [PrecompOHLCV(b.date, b.open, b.high, b.low, b.close, b.volume) for b in spy_data]
        precomputed = PrecomputedIndicators(precomp_code, precomp_spy, params)
        precomputed.compute_all()
    
    # Step 3.4.2 — Use initial_signal if provided, skip CSV re-read
    if initial_signal is not None:
        latest_signal = initial_signal
    else:
        latest_signal = await get_latest_signal(csv_file_name, genome_id=genome_id)
        if latest_signal is None:
            print(f"Немає сигналу для коду {code}, genome: {genome_id}")
            latest_signal = await get_data_and_save_to_csv(code, trade_date, genome_id, file_name=csv_file_name)

    # Step 3.1.1 — Replace pd.to_datetime with string comparison (YYYY-MM-DD sorts lexicographically)
    _raw_td = str(latest_signal["tradeday"]).split("T")[0]

    # Filter code_data for dates after latest_signal (only needed once)
    filtered_code_data = []
    for bar in code_data:
        if bar.date > _raw_td:
            filtered_code_data.append(bar)

    results_batch: List[Dict[str, Any]] = []
    total_days = len(filtered_code_data)

    # Main processing loop with optimized filtering
    with TimingContext("main_signal_loop"):
        for day_index, bar in enumerate(filtered_code_data):
            if day_index % LOG_INTERVAL == 0 and day_index > 0:
                logger.info(f'Progress: {day_index}/{total_days} days processed for {code}, genome: {genome_id}')
            
            tradeday_str = bar.date  # Already in "YYYY-MM-DD" format

            # OPTIMIZATION Task 3.2: O(1) index-based slicing instead of O(n) list comprehension
            spy_end_idx = _find_end_index(spy_date_index, spy_dates_sorted, tradeday_str, len(spy_data))
            code_end_idx = _find_end_index(code_date_index, code_dates_sorted, tradeday_str, len(code_data))
            
            # Slice up to and including the end index
            filtered_spy = spy_data[:spy_end_idx + 1] if spy_end_idx >= 0 else []
            filtered_code = code_data[:code_end_idx + 1] if code_end_idx >= 0 else []

            position_status = latest_signal["position_status"]

            if position_status == "F":
                # Skip expensive energy computation on buy-only days —
                # energy is only consumed by S9 (sell condition).
                # E1–E5 columns are not used downstream for buy rows.
                logger.info(f"Buy - {tradeday_str}")
                buySignals = precomputed.run_all_buy_conditions_fast(code_end_idx)
                buy = is_buy_fast(buySignals)

                exit_price = 0
                if latest_signal['next_open_action'] == "S":
                    exit_price = bar.open

                result = {
                    "code": code,
                    "genome_id": genome_id,
                    "tradeday": tradeday_str,
                    "position_status": position_status,
                    "next_open_action": "B" if buy else "N",
                    "E1": 0,
                    "E2": 0,
                    "E3": 0,
                    "E4": 0,
                    "E5": 0,
                    "exit1": buySignals.get("stopLoss"),
                    "entry_price": filtered_code[-1].close if filtered_code else None,
                    "close": filtered_code[-1].close if filtered_code else None,
                    "entry_date": 0,
                    "exit_price": exit_price 
                }
                latest_signal = {
                    "entry_date": tradeday_str,
                    "entry_price": filtered_code[-1].close if filtered_code else 0,
                    "exit1": buySignals.get("stopLoss"),
                    "position_status": "I" if buy else "F",
                    "next_open_action": "B" if buy else "N",
                }
                results_batch.append(result)

            elif position_status == "I":
                # Energy needed for sell evaluation (S9)
                energy_data = calculate_energy_indicators_last_16_days(
                    tradeday_str, filtered_code, filtered_spy
                )

                entry_date = latest_signal.get("entry_date")
                entry_price = latest_signal.get("entry_price")

                if latest_signal["next_open_action"] == "B":
                    entry_date = tradeday_str
                    entry_price = bar.open

                exit1 = to_float_or_none(latest_signal.get("exit1"))
                sellSignals = runAllSellConditions(
                    filtered_code,
                    filtered_spy,
                    entry_date,
                    to_float_or_none(entry_price),
                    exit1,
                    tradeday_str,
                    params,
                    energy_data=energy_data,
                )
                if ALGORITHM_DEBUG:
                    logger.debug(f'Trade day: {tradeday_str}, stock: {code}, genome: {genome_id}')
                    logger.debug(f'Sell signals: {sellSignals}')
                sell = isSell(sellSignals['conditions'])
                new_stop_loss = sellSignals['stop_loss']
                result = {
                    "code": code,
                    "genome_id": genome_id,
                    "tradeday": tradeday_str,
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
    
    logger.info(f'Task completed for {code}, genome: {genome_id} | Total days: {total_days} | Results: {len(results_batch)}')
            
    if len(results_batch) > 0:
        await append_to_signals_csv(results_batch, csv_file_name)


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


async def append_to_signals_csv(
    result_data: Union[Dict[str, Any], List[Dict[str, Any]]],
    file_name,
    file_service: "FileService" = None,
) -> bool:
   
    if file_service is None:
        file_service = FileService()

    fieldnames = [
        "code","genome_id","tradeday","position_status","next_open_action",
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

    return await file_service.add_data_to_csv(
        file_name=file_name,
        data=rows,
        fieldnames=fieldnames,
    )


async def get_latest_signal(
    code: str,
    file_service: "FileService" = None,
    genome_id: str = None,
) -> Optional[Dict[str, Any]]:
    file_name = code
    
    if file_service is None:
        file_service = FileService()

    rows: List[Dict[str, Any]] = await file_service.read_data_from_csv(file_name)
    if not rows:
        print(f"Немає записів у файлі data/{file_name}.csv")
        return None

    # Filter by code
    filtered = [r for r in rows if r.get("code") == code]
    
    # For optimization runs, filter by genome_id to get fresh start for each genome
    if genome_id:
        filtered = [r for r in filtered if r.get("genome_id") == genome_id]
    
    if not filtered:
        print(f"Немає записів для коду {code}" + (f", genome: {genome_id}" if genome_id else ""))
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
    genome_id: str = "G_000",
) -> Optional[pd.DataFrame]:
    if file_service is None:
        file_service = FileService()

    rows_raw: List[Dict[str, Any]] = await file_service.read_data_from_csv(file_name)
    if not rows_raw:
        return None

    df = pd.DataFrame(rows_raw)

    for col in ["next_open_action", "tradeday", "entry_date", "genome_id"]:
        if col not in df.columns:
            df[col] = np.nan if col != "genome_id" else genome_id

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
        row_genome_id = row.get("genome_id", genome_id)

        entry_f = _to_float_or_none(entry_price)
        exit_f = _to_float_or_none(exit_price)

        gain = None
        if entry_f and exit_f:
            try:
                gain = round(((exit_f - entry_f) / entry_f) * 100.0, 2)
            except ZeroDivisionError:
                gain = None

        result_rows.append({
            "Genome ID": row_genome_id,
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
        row_genome_id = b_row.get("genome_id", genome_id)

        gain_open = None
        if entry_price and last_close:
            try:
                gain_open = round(((last_close - entry_price) / entry_price) * 100.0, 2)
            except ZeroDivisionError:
                gain_open = None

        result_rows.append({
            "Genome ID": row_genome_id,
            "Buy Signal": _to_date_str_or_none(buy_signal_date) or "",
            "Stop Signal": "Open position",
            "Entry price": entry_price if entry_price is not None else "",
            "Exit price": "Open position",
            "Gain/Lose": gain_open if gain_open is not None else "",
        })

    out_df = pd.DataFrame(
        result_rows,
        columns=["Genome ID", "Buy Signal", "Stop Signal", "Entry price", "Exit price", "Gain/Lose"]
    )
    
    cutoff = pd.to_datetime(START_DATE)
    buy_dt = pd.to_datetime(out_df["Buy Signal"], errors="coerce")
    stop_dt = pd.to_datetime(out_df["Stop Signal"], errors="coerce")
    
    mask = (buy_dt >= cutoff) & (
        (out_df["Stop Signal"] == "Open position") | (stop_dt >= cutoff)
    )
    out_df = out_df[mask].reset_index(drop=True)

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
