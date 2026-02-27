import logging
import os

import pandas as pd
from fastapi import APIRouter, HTTPException

from app.services.file_service import FileService

generate_summary_file = APIRouter()
logger = logging.getLogger(__name__)

INPUT_FILE = "general_results"
OUTPUT_FILE = "summary"

EXPECTED_COLUMNS = [
    "symbol", "genome_id", "entryDay", "entryPrice",
    "exitDay", "exitPrice", "profit", "Profit %", "Invested"
]


@generate_summary_file.get("/")
async def generate_summary():
    """
    Reads general_results.csv using FileService, separates Open/Closed trades,
    calculates statistics on CLOSED trades only, and saves summary.csv.
    """
    file_service = FileService()
    filepath = file_service._get_filepath(INPUT_FILE)

    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail=f"File {INPUT_FILE}.csv not found or empty. Run tests first.")

    try:
        df = pd.read_csv(filepath)

        # If expected columns are missing, the file likely has no header row
        if 'exitDay' not in df.columns or 'profit' not in df.columns:
            # Determine column names based on number of columns
            peek = pd.read_csv(filepath, header=None, nrows=1)
            n_cols = peek.shape[1]
            if n_cols == len(EXPECTED_COLUMNS):
                col_names = EXPECTED_COLUMNS
            else:
                # Fallback for files without genome_id column
                col_names = [c for c in EXPECTED_COLUMNS if c != "genome_id"][:n_cols]
            df = pd.read_csv(filepath, header=None, names=col_names)

        if df.empty:
            raise HTTPException(status_code=404, detail=f"File {INPUT_FILE}.csv is empty. Run tests first.")

        df['profit'] = pd.to_numeric(df['profit'], errors='coerce').fillna(0.0)

        if 'exitDay' not in df.columns:
            df['exitDay'] = ""
        
        df['exitDay'] = df['exitDay'].fillna('').astype(str).str.strip()
        
        open_mask = (df['exitDay'] == '') | (df['exitDay'].str.lower() == 'nan')
        
        if 'exitPrice' in df.columns:
            open_mask = open_mask | (df['exitPrice'].astype(str) == "Open position")

        df_open = df[open_mask]
        df_closed = df[~open_mask]
        
        total_closed = len(df_closed)
        total_open = len(df_open)
        
        winning_trades = df_closed[df_closed['profit'] > 0]
        losing_trades = df_closed[df_closed['profit'] < 0]
        
        count_win = len(winning_trades)
        count_loss = len(losing_trades)
        
        pct_profitable = (count_win / total_closed * 100) if total_closed > 0 else 0.0

        avg_trade_all = df_closed['profit'].mean() if total_closed > 0 else 0.0
        avg_win = winning_trades['profit'].mean() if count_win > 0 else 0.0
        avg_loss = losing_trades['profit'].mean() if count_loss > 0 else 0.0

        ratio = 0.0
        if avg_loss != 0:
            ratio = avg_win / abs(avg_loss)

        summary_data = [
            {"Metric": "Total # of Trades (Closed)", "Value": total_closed},
            {"Metric": "Total # of Open Trades", "Value": total_open},
            {"Metric": "Number Winning Trades", "Value": count_win},
            {"Metric": "Number Losing Trades", "Value": count_loss},
            {"Metric": "Percent Profitable", "Value": f"{pct_profitable:.2f}%"},
            {"Metric": "Avg Trade (win & loss) ($)", "Value": f"{avg_trade_all:.2f}"},
            {"Metric": "Average Winning Trade ($)", "Value": f"{avg_win:.2f}"},
            {"Metric": "Average Losing Trade ($)", "Value": f"{avg_loss:.2f}"},
            {"Metric": "Ratio Avg Win / Avg Loss", "Value": f"{ratio:.2f}"}
        ]

        await file_service.clear_csv(OUTPUT_FILE)
        
        fieldnames = ["Metric", "Value"]
        await file_service.add_data_to_csv(OUTPUT_FILE, summary_data, fieldnames)
        
        logger.info(f"Summary generated successfully in {OUTPUT_FILE}.csv")

        return {
            "message": "Summary generated successfully",
            "file": f"{OUTPUT_FILE}.csv",
            "stats": {row["Metric"]: row["Value"] for row in summary_data}
        }

    except Exception as e:
        logger.error(f"Error generating summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))