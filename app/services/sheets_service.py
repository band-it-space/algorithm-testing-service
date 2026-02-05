import os
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# Lazy import to avoid issues when gspread is not installed
gspread = None
ServiceAccountCredentials = None


def _ensure_gspread():
    """Lazy import gspread and related modules."""
    global gspread, ServiceAccountCredentials
    if gspread is None:
        try:
            import gspread as gs
            from google.oauth2.service_account import Credentials
            gspread = gs
            ServiceAccountCredentials = Credentials
        except ImportError as e:
            logger.error(f"Failed to import gspread: {e}")
            raise ImportError(
                "gspread is required for Google Sheets integration. "
                "Install it with: pip install gspread google-auth"
            )


class SheetsService:
    """Service for reading/writing Google Sheets."""
    
    _client = None
    
    @classmethod
    def authenticate(cls):
        """Authenticate with Google Sheets API using service account."""
        _ensure_gspread()
        
        if cls._client is not None:
            return cls._client
        
        creds_path = os.getenv("GOOGLE_SHEETS_CREDENTIALS_PATH")
        if not creds_path:
            raise ValueError("GOOGLE_SHEETS_CREDENTIALS_PATH environment variable not set")
        
        if not os.path.exists(creds_path):
            raise FileNotFoundError(f"Credentials file not found: {creds_path}")
        
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        
        credentials = ServiceAccountCredentials.from_service_account_file(
            creds_path, scopes=scopes
        )
        cls._client = gspread.authorize(credentials)
        
        logger.info("Successfully authenticated with Google Sheets API")
        return cls._client
    
    @classmethod
    def read_parameter_ranges(
        cls,
        sheet_id: str,
        worksheet_name: str = "Parameter Tuning"
    ) -> List[Dict[str, Any]]:
        """Read parameter ranges from a Google Sheet."""
        client = cls.authenticate()
        
        try:
            spreadsheet = client.open_by_key(sheet_id)
            worksheet = spreadsheet.worksheet(worksheet_name)
            records = worksheet.get_all_records()
            
            logger.info(f"Read {len(records)} parameter ranges from sheet {sheet_id}")
            return records
            
        except gspread.exceptions.SpreadsheetNotFound:
            raise ValueError(f"Spreadsheet not found: {sheet_id}")
        except gspread.exceptions.WorksheetNotFound:
            raise ValueError(f"Worksheet not found: {worksheet_name}")
        except Exception as e:
            logger.error(f"Error reading from Google Sheets: {e}")
            raise
    
    @classmethod
    def write_genome_results(
        cls,
        sheet_id: str,
        data: List[Dict[str, Any]],
        worksheet_name: str = "Automated Results"
    ) -> bool:
        """Write genome results to a Google Sheet."""
        if not data:
            logger.warning("No data to write to Google Sheets")
            return False
        
        client = cls.authenticate()
        
        try:
            spreadsheet = client.open_by_key(sheet_id)
            
            # Get or create worksheet
            try:
                worksheet = spreadsheet.worksheet(worksheet_name)
                worksheet.clear()
            except gspread.exceptions.WorksheetNotFound:
                worksheet = spreadsheet.add_worksheet(
                    title=worksheet_name,
                    rows=len(data) + 1,
                    cols=len(data[0])
                )
            
            # Prepare data
            headers = list(data[0].keys())
            rows = [[row.get(h, "") for h in headers] for row in data]
            
            # Write headers and data
            worksheet.update("A1", [headers])
            if rows:
                worksheet.update("A2", rows)
            
            logger.info(f"Wrote {len(data)} rows to sheet {sheet_id}/{worksheet_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error writing to Google Sheets: {e}")
            raise
    
    @classmethod
    def append_genome_result(
        cls,
        sheet_id: str,
        result: Dict[str, Any],
        worksheet_name: str = "Automated Results"
    ) -> bool:
        """Append a single genome result to a Google Sheet."""
        client = cls.authenticate()
        
        try:
            spreadsheet = client.open_by_key(sheet_id)
            
            try:
                worksheet = spreadsheet.worksheet(worksheet_name)
            except gspread.exceptions.WorksheetNotFound:
                # Create worksheet with headers
                headers = list(result.keys())
                worksheet = spreadsheet.add_worksheet(
                    title=worksheet_name,
                    rows=1000,
                    cols=len(headers)
                )
                worksheet.update("A1", [headers])
            
            # Append row
            headers = worksheet.row_values(1)
            row = [result.get(h, "") for h in headers]
            worksheet.append_row(row)
            
            return True
            
        except Exception as e:
            logger.error(f"Error appending to Google Sheets: {e}")
            raise
    
    @classmethod
    def get_or_create_output_sheet(
        cls,
        sheet_id: str,
        worksheet_name: str = "Automated Results",
        headers: Optional[List[str]] = None
    ):
        """Ensure output worksheet exists with proper headers."""
        client = cls.authenticate()
        
        default_headers = [
            "Genome ID", "Stock Code", "Trade Count", "Profit Delta (%)",
            "Win Rate Delta (%)", "Total Win ($)", "Total Loss ($)",
            "Trades Win", "Trades Loss", "Avg Win ($)", "Avg Loss ($)",
            "Payoff Ratio", "input_B1_upper_range", "input_B3_LR_lookback",
            "input_B11_atr_threshold", "input_B18_bbw_ratio",
            "input_S1_atr_mult", "input_S5_push_up_atr"
        ]
        
        headers = headers or default_headers
        
        try:
            spreadsheet = client.open_by_key(sheet_id)
            
            try:
                worksheet = spreadsheet.worksheet(worksheet_name)
                # Check if headers exist
                existing_headers = worksheet.row_values(1)
                if not existing_headers:
                    worksheet.update("A1", [headers])
            except gspread.exceptions.WorksheetNotFound:
                worksheet = spreadsheet.add_worksheet(
                    title=worksheet_name,
                    rows=1000,
                    cols=len(headers)
                )
                worksheet.update("A1", [headers])
            
            return worksheet
            
        except Exception as e:
            logger.error(f"Error creating output sheet: {e}")
            raise


def read_parameter_ranges_from_sheets(
    sheet_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Convenience function to read parameter ranges from configured sheet."""
    sheet_id = sheet_id or os.getenv("INPUT_SHEET_ID")
    if not sheet_id:
        raise ValueError("Sheet ID not provided and INPUT_SHEET_ID not set")
    
    return SheetsService.read_parameter_ranges(sheet_id)


def write_results_to_sheets(
    data: List[Dict[str, Any]],
    sheet_id: Optional[str] = None
) -> bool:
    """Convenience function to write results to configured sheet."""
    sheet_id = sheet_id or os.getenv("OUTPUT_SHEET_ID")
    if not sheet_id:
        raise ValueError("Sheet ID not provided and OUTPUT_SHEET_ID not set")
    
    return SheetsService.write_genome_results(sheet_id, data)
