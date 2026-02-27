import json
import logging
import os
from bisect import bisect_right
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from app.config.logging_config import get_algorithm_debug_mode, get_log_progress_interval
from app.config.smart_filtering_config import SMART_FILTERING_ENABLED
from app.models.algorithm_models import AlgorithmParameters
from app.services.optimization_service import OptimizationService
from app.services.queue_service import QueueService
from app.services.smart_filtering_service import SmartFilteringService
from app.utils.performance_profiler import timed, TimingContext, get_profiler
from app.workers.algo_func.buy_signals import runAllBuyConditions, isBuy, OHLCV
from app.workers.algo_func.get_code_energy import calculate_energy_indicators_last_16_days
from app.workers.algo_func.get_db_data import get_stock_data_from_db, init_db_pool, warm_spy_cache
from app.workers.algo_func.precomputed_indicators import (
    OHLCV as PrecompOHLCV,
    PrecomputedIndicators,
    is_buy_fast,
)
from app.workers.algo_func.sell_signals import runAllSellConditions, isSell

logger = logging.getLogger(__name__)
API_KEY = os.getenv('API_KEY')

# Date range from environment (with fallback defaults)
START_DATE = os.getenv('OPTIMIZATION_START_DATE', '2009-01-01')
END_DATE = os.getenv('OPTIMIZATION_END_DATE', '2016-01-01')

# Module-level debug settings
ALGORITHM_DEBUG = get_algorithm_debug_mode()
LOG_INTERVAL = get_log_progress_interval()


def _build_date_index(data: list[OHLCV]) -> dict[str, int]:
    """Build a date-to-index mapping for O(1) lookups."""
    return {bar.date: i for i, bar in enumerate(data)}


def _find_end_index(date_index: dict[str, int], sorted_dates: list[str], target_date: str, data_len: int) -> int:
    """Find the index for slicing data up to target_date inclusive."""
    if target_date in date_index:
        return date_index[target_date]
    idx = bisect_right(sorted_dates, target_date)
    if idx == 0:
        return -1
    return idx - 1


@timed("algorithm_task_total")
async def process_algorithm_task(task_data: dict[str, Any]) -> dict[str, Any]:
    """Worker for algorithm processing (first queue)."""
    try:
        stock_code = task_data['stock']
        genome_id = task_data.get('genome_id', 'G_000')
        optimization_id = task_data.get('optimization_id')
        params_dict = task_data.get('parameters', {})
        params = AlgorithmParameters.from_dict(params_dict)
        
        logger.info(f"Processing algorithm task: {stock_code}, genome: {genome_id}, optimization: {optimization_id}")
        
        # Smart filtering — skip check (before any DB/computation)
        if SMART_FILTERING_ENABLED and optimization_id and genome_id != "G_000":
            if SmartFilteringService.is_genome_skipped(optimization_id, genome_id):
                # Increment by 1 per task (not batch) to avoid over-counting
                # when some stocks already completed through the result worker.
                try:
                    OptimizationService.increment_completed_tasks(optimization_id, count=1)
                except Exception as e:
                    logger.warning(f"Failed to increment tasks for skipped genome {genome_id}: {e}")
                logger.info(f"SMART FILTER: Skipped genome {genome_id} for {stock_code} (eliminated)")
                return task_data

        with TimingContext("db_pool_init"):
            await init_db_pool()

        with TimingContext("spy_cache_warm"):
            await warm_spy_cache(END_DATE)

        with TimingContext("fetch_all_data"):
            code_data_raw = await get_stock_data_from_db(stock_code, END_DATE)
            spy_data_raw = await get_stock_data_from_db("2800", END_DATE)

        seed_row = compute_seed_row(stock_code, START_DATE, genome_id, code_data_raw)

        logger.info('Starting signals_for_the_period')
        signals_batch = await signals_for_the_period(stock_code, END_DATE, params, genome_id,
                                      code_data_raw=code_data_raw,
                                      spy_data_raw=spy_data_raw,
                                      initial_signal=seed_row)
        logger.info('Finished signals_for_the_period')

        logger.info('Starting format_signals_in_memory')
        trade_pairs = format_signals_in_memory(signals_batch, genome_id=genome_id)
        logger.info(f'Formatted {len(trade_pairs)} trade pairs in memory')

        # Store trade pairs in Redis for result worker (no temp files)
        _store_trade_pairs_in_redis(optimization_id, stock_code, genome_id, trade_pairs)

        processing_task_id = QueueService.add_to_result_processing_queue(
            stock_code, 
            genome_id=genome_id, 
            parameters=params.to_dict(),
            optimization_id=optimization_id,
            results={}
        )
        
        logger.info(f"Algorithm task {task_data['task_id']} completed, genome: {genome_id}, added to processing queue: {processing_task_id}")
        
        profiler = get_profiler()
        if ALGORITHM_DEBUG:
            profiler.log_summary()
        
        return task_data
        
    except Exception as e:
        logger.error(f"Error processing algorithm task {task_data['task_id']}: {str(e)}")
        raise e


def compute_seed_row(code: str, trade_date: str, genome_id: str = "G_000",
                     code_data_raw: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Compute the initial seed row in memory (no file I/O)."""
    effective_date = trade_date
    if code_data_raw and code_data_raw[0]["date"] > trade_date:
        effective_date = code_data_raw[0]["date"]

    return {
        "code": code,
        "genome_id": genome_id,
        "tradeday": effective_date,
        "position_status": "F",
        "next_open_action": "N",
        "E1": 0, "E2": 0, "E3": 0, "E4": 0, "E5": 0,
        "exit1": 0, "close": 0, "entry_price": 0, "entry_date": 0, "exit_price": 0,
    }


def _store_trade_pairs_in_redis(
    optimization_id: str | None,
    stock_code: str,
    genome_id: str,
    trade_pairs: list[dict[str, Any]],
) -> None:
    """Store formatted trade pairs in Redis for the result worker to consume."""
    client = QueueService.get_redis_client()
    key = f"trade_pairs:{optimization_id or 'single'}:{stock_code}:{genome_id}"
    client.set(key, json.dumps(trade_pairs), ex=3600)  # TTL 1 hour


@timed("signals_for_the_period")
async def signals_for_the_period(
    code: str,
    trade_date: str,
    params: AlgorithmParameters | None = None, 
    genome_id: str = "G_000",
    code_data_raw: list[dict[str, Any]] | None = None,
    spy_data_raw: list[dict[str, Any]] | None = None,
    initial_signal: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Main signal calculation loop. Returns signals batch in memory (no file I/O)."""
    if params is None:
        params = AlgorithmParameters()
    
    logger.debug("Starting signal calculation for %s", code)
    
    if spy_data_raw is None:
        with TimingContext("fetch_spy_data"):
            spy_data_raw = await get_stock_data_from_db("2800", trade_date)
    
    if code_data_raw is None:
        with TimingContext("fetch_code_data"):
            code_data_raw = await get_stock_data_from_db(code, trade_date)
    
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

    with TimingContext("build_date_index"):
        spy_date_index = _build_date_index(spy_data)
        code_date_index = _build_date_index(code_data)
        spy_dates_sorted = [bar.date for bar in spy_data]
        code_dates_sorted = [bar.date for bar in code_data]
    
    with TimingContext("precompute_indicators"):
        precomp_code = [PrecompOHLCV(b.date, b.open, b.high, b.low, b.close, b.volume) for b in code_data]
        precomp_spy = [PrecompOHLCV(b.date, b.open, b.high, b.low, b.close, b.volume) for b in spy_data]
        precomputed = PrecomputedIndicators(precomp_code, precomp_spy, params)
        precomputed.compute_all()
    
    if initial_signal is not None:
        latest_signal = initial_signal
    else:
        raise ValueError(f"initial_signal is required for genome {genome_id} — no file fallback")

    _raw_td = str(latest_signal["tradeday"]).split("T")[0]

    filtered_code_data = []
    for bar in code_data:
        if bar.date > _raw_td:
            filtered_code_data.append(bar)

    results_batch: list[dict[str, Any]] = []
    total_days = len(filtered_code_data)

    with TimingContext("main_signal_loop"):
        for day_index, bar in enumerate(filtered_code_data):
            if day_index % LOG_INTERVAL == 0 and day_index > 0:
                logger.info(f'Progress: {day_index}/{total_days} days processed for {code}, genome: {genome_id}')
            
            tradeday_str = bar.date

            spy_end_idx = _find_end_index(spy_date_index, spy_dates_sorted, tradeday_str, len(spy_data))
            code_end_idx = _find_end_index(code_date_index, code_dates_sorted, tradeday_str, len(code_data))

            position_status = latest_signal["position_status"]

            if position_status == "F":
                # logger.info(f"Buy - {tradeday_str}")
                buy_signals = precomputed.run_all_buy_conditions_fast(code_end_idx)
                buy = is_buy_fast(buy_signals)

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
                    "exit1": buy_signals.get("stopLoss"),
                    "entry_price": code_data[code_end_idx].close if code_end_idx >= 0 else None,
                    "close": code_data[code_end_idx].close if code_end_idx >= 0 else None,
                    "entry_date": 0,
                    "exit_price": exit_price 
                }
                latest_signal = {
                    "entry_date": tradeday_str,
                    "entry_price": code_data[code_end_idx].close if code_end_idx >= 0 else 0,
                    "exit1": buy_signals.get("stopLoss"),
                    "position_status": "I" if buy else "F",
                    "next_open_action": "B" if buy else "N",
                }
                results_batch.append(result)

            elif position_status == "I":
                entry_date = latest_signal.get("entry_date")
                entry_price = latest_signal.get("entry_price")

                if latest_signal["next_open_action"] == "B":
                    entry_date = tradeday_str
                    entry_price = bar.open

                # O(1) buy-index lookup via pre-computed date map
                buy_idx = precomputed.date_to_idx.get(entry_date, -1)
                exit1 = to_float_or_none(latest_signal.get("exit1"))

                # Pre-computed sell evaluation — all O(1) lookups
                sell_signals = precomputed.run_all_sell_conditions_fast(
                    code_end_idx, buy_idx, to_float_or_none(entry_price), exit1
                )

                # Pre-computed energy data for CSV output
                energy_data = precomputed.get_energy_data(code_end_idx)

                if ALGORITHM_DEBUG:
                    logger.debug(f'Trade day: {tradeday_str}, stock: {code}, genome: {genome_id}')
                    logger.debug(f'Sell signals: {sell_signals}')

                sell = isSell(sell_signals['conditions'])
                new_stop_loss = sell_signals['stop_loss']

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
                    "close": code_data[code_end_idx].close if code_end_idx >= 0 else None,
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

    return results_batch


def to_float_or_none(v: Any) -> float | None:
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


def _to_float_or_none(v: Any) -> float | None:
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


def _to_date_str_or_none(v: Any) -> str | None:
    if v is None:
        return None
    try:
        return pd.to_datetime(v).strftime("%Y-%m-%d")
    except Exception:
        return None


def format_signals_in_memory(
    rows_raw: list[dict[str, Any]],
    genome_id: str = "G_000",
) -> list[dict[str, Any]]:
    """
    Format raw signal rows into trade-pair summaries, entirely in memory.
    Returns list of dicts with keys: Genome ID, Buy Signal, Stop Signal,
    Entry price, Exit price, Gain/Lose.
    """
    if not rows_raw:
        return []

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

    result_rows: list[dict[str, Any]] = []

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

    return out_df.to_dict(orient="records")