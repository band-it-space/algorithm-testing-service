"""
Google Sheets Service

Provides rate-limited access to Google Sheets API with:
- Request rate limiting (100 requests per 100 seconds)
- Exponential backoff for rate limit errors
- Batch operations for efficiency
- Payload optimization for large datasets
"""

import os
import time
import logging
from typing import List, Dict, Any, Optional
from collections import deque
from functools import wraps
import math

from app.utils.performance_profiler import timed, CacheCounter

logger = logging.getLogger(__name__)

# Google Sheets API limits
MAX_REQUESTS_PER_WINDOW = 100
WINDOW_SECONDS = 100
MAX_CELLS_PER_REQUEST = 50000  # Google Sheets limit
MAX_ROWS_PER_BATCH = 1000


class RateLimiter:
    """
    Token bucket rate limiter for API requests.

    Ensures compliance with Google Sheets API rate limits
    (100 requests per 100 seconds by default).

    Args:
        max_requests: Maximum requests allowed in window
        window_seconds: Time window in seconds
    """
    
    def __init__(
        self, 
        max_requests: int = MAX_REQUESTS_PER_WINDOW, 
        window_seconds: int = WINDOW_SECONDS
    ):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: deque = deque()
    
    def acquire(self) -> float:
        """
        Acquire permission to make a request.

        Blocks if rate limit would be exceeded.

        Returns:
            Time waited in seconds (0 if no wait needed)
        """
        now = time.time()
        
        # Remove requests outside the window
        while self.requests and now - self.requests[0] >= self.window_seconds:
            self.requests.popleft()
        
        wait_time = 0.0
        
        # Check if we need to wait
        if len(self.requests) >= self.max_requests:
            # Calculate how long to wait
            oldest_request = self.requests[0]
            wait_time = oldest_request + self.window_seconds - now
            
            if wait_time > 0:
                logger.debug(f"Rate limit: waiting {wait_time:.2f}s")
                time.sleep(wait_time)
                now = time.time()
                
                # Clean up again after waiting
                while self.requests and now - self.requests[0] >= self.window_seconds:
                    self.requests.popleft()
        
        self.requests.append(now)
        return wait_time
    
    def get_remaining(self) -> int:
        """Get number of requests remaining in current window."""
        now = time.time()
        while self.requests and now - self.requests[0] >= self.window_seconds:
            self.requests.popleft()
        return max(0, self.max_requests - len(self.requests))
    
    def reset(self) -> None:
        """Reset the rate limiter."""
        self.requests.clear()


def with_rate_limit(func):
    """Decorator to apply rate limiting to a method."""
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        if hasattr(self, 'rate_limiter'):
            self.rate_limiter.acquire()
        return func(self, *args, **kwargs)
    return wrapper


def with_exponential_backoff(max_retries: int = 5, base_delay: float = 1.0):
    """
    Decorator for exponential backoff on rate limit errors.

    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay in seconds
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    error_str = str(e).lower()
                    
                    # Check if it's a rate limit error
                    if '429' in error_str or 'rate limit' in error_str or 'quota' in error_str:
                        last_exception = e
                        
                        if attempt < max_retries:
                            delay = base_delay * (2 ** attempt)
                            # Add jitter
                            delay += delay * 0.1 * (time.time() % 1)
                            
                            logger.warning(
                                f"Rate limit hit, attempt {attempt + 1}/{max_retries + 1}, "
                                f"waiting {delay:.2f}s"
                            )
                            time.sleep(delay)
                        else:
                            logger.error(f"Max retries exceeded for rate limit: {e}")
                            raise
                    else:
                        # Non-rate-limit error, re-raise immediately
                        raise
            
            if last_exception:
                raise last_exception
                
        return wrapper
    return decorator


class GoogleSheetsService:
    """
    Rate-limited Google Sheets API service.

    Provides methods for reading and writing data with automatic
    rate limiting and error handling.

    Args:
        credentials_path: Path to service account credentials JSON
        spreadsheet_id: ID of the target spreadsheet
        default_sheet: Default sheet name for operations
    """
    
    def __init__(
        self,
        credentials_path: Optional[str] = None,
        spreadsheet_id: Optional[str] = None,
        default_sheet: str = "Sheet1"
    ):
        self.credentials_path = credentials_path
        self.spreadsheet_id = spreadsheet_id
        self.default_sheet = default_sheet
        self.rate_limiter = RateLimiter()
        self.api_counter = CacheCounter("sheets_api")
        self._service = None
        self._initialized = False
    
    def _ensure_initialized(self) -> None:
        """Lazy initialization of the Sheets API service."""
        if self._initialized:
            return
        
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
            
            if self.credentials_path:
                credentials = service_account.Credentials.from_service_account_file(
                    self.credentials_path,
                    scopes=['https://www.googleapis.com/auth/spreadsheets']
                )
                self._service = build('sheets', 'v4', credentials=credentials)
                self._initialized = True
                logger.info("Google Sheets service initialized")
            else:
                logger.warning("No credentials path provided, running in mock mode")
                self._initialized = True
                
        except ImportError:
            logger.error("Google API client libraries not installed")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize Sheets service: {e}")
            raise
    
    @with_rate_limit
    @with_exponential_backoff(max_retries=5)
    @timed("sheets_read_values")
    def read_values(
        self, 
        range_name: str,
        sheet_name: Optional[str] = None
    ) -> List[List[Any]]:
        """
        Read values from a range in the spreadsheet.

        Args:
            range_name: A1 notation range (e.g., "A1:D10")
            sheet_name: Sheet name (uses default if not specified)

        Returns:
            2D list of cell values
        """
        self._ensure_initialized()
        
        if not self._service:
            logger.warning("Sheets service not available, returning empty")
            return []
        
        sheet = sheet_name or self.default_sheet
        full_range = f"{sheet}!{range_name}"
        
        try:
            result = self._service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=full_range
            ).execute()
            
            self.api_counter.hit()
            values = result.get('values', [])
            logger.debug(f"Read {len(values)} rows from {full_range}")
            return values
            
        except Exception as e:
            self.api_counter.miss()
            logger.error(f"Failed to read from Sheets: {e}")
            raise
    
    @with_rate_limit
    @with_exponential_backoff(max_retries=5)
    @timed("sheets_write_values")
    def write_values(
        self,
        range_name: str,
        values: List[List[Any]],
        sheet_name: Optional[str] = None
    ) -> int:
        """
        Write values to a range in the spreadsheet.

        Args:
            range_name: A1 notation range
            values: 2D list of values to write
            sheet_name: Sheet name (uses default if not specified)

        Returns:
            Number of cells updated
        """
        self._ensure_initialized()
        
        if not self._service:
            logger.warning("Sheets service not available, skipping write")
            return 0
        
        sheet = sheet_name or self.default_sheet
        full_range = f"{sheet}!{range_name}"
        
        try:
            body = {'values': values}
            result = self._service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=full_range,
                valueInputOption='USER_ENTERED',
                body=body
            ).execute()
            
            self.api_counter.hit()
            updated = result.get('updatedCells', 0)
            logger.debug(f"Wrote {updated} cells to {full_range}")
            return updated
            
        except Exception as e:
            self.api_counter.miss()
            logger.error(f"Failed to write to Sheets: {e}")
            raise
    
    @with_rate_limit
    @with_exponential_backoff(max_retries=5)
    @timed("sheets_append_rows")
    def append_rows(
        self,
        values: List[List[Any]],
        sheet_name: Optional[str] = None
    ) -> int:
        """
        Append rows to the end of the sheet.

        Args:
            values: 2D list of row values
            sheet_name: Sheet name (uses default if not specified)

        Returns:
            Number of rows appended
        """
        self._ensure_initialized()
        
        if not self._service:
            logger.warning("Sheets service not available, skipping append")
            return 0
        
        sheet = sheet_name or self.default_sheet
        
        try:
            body = {'values': values}
            result = self._service.spreadsheets().values().append(
                spreadsheetId=self.spreadsheet_id,
                range=f"{sheet}!A:A",
                valueInputOption='USER_ENTERED',
                insertDataOption='INSERT_ROWS',
                body=body
            ).execute()
            
            self.api_counter.hit()
            updates = result.get('updates', {})
            updated_rows = updates.get('updatedRows', len(values))
            logger.debug(f"Appended {updated_rows} rows to {sheet}")
            return updated_rows
            
        except Exception as e:
            self.api_counter.miss()
            logger.error(f"Failed to append to Sheets: {e}")
            raise
    
    @timed("sheets_batch_append")
    def batch_append_rows(
        self,
        values: List[List[Any]],
        sheet_name: Optional[str] = None
    ) -> int:
        """
        Append rows in batches to handle large datasets.

        Automatically chunks data to stay within API limits.

        Args:
            values: 2D list of row values
            sheet_name: Sheet name
        
        Returns:
            Total number of rows appended
        """
        if not values:
            return 0
        
        total_appended = 0
        
        # Calculate optimal batch size based on row width
        row_width = len(values[0]) if values else 1
        batch_size = min(MAX_ROWS_PER_BATCH, MAX_CELLS_PER_REQUEST // row_width)
        
        # Process in batches
        for i in range(0, len(values), batch_size):
            batch = values[i:i + batch_size]
            appended = self.append_rows(batch, sheet_name)
            total_appended += appended
            
            logger.debug(f"Batch {i // batch_size + 1}: appended {appended} rows")
        
        logger.info(f"Batch append complete: {total_appended} total rows")
        return total_appended
    
    @timed("sheets_batch_update")
    def batch_update(
        self,
        results: List[Dict[str, Any]],
        sheet_name: Optional[str] = None,
        include_header: bool = True
    ) -> int:
        """
        Batch update the sheet with result dictionaries.

        Handles conversion from dicts to row values and chunking.

        Args:
            results: List of result dictionaries
            sheet_name: Sheet name
            include_header: Whether to write header row
        
        Returns:
            Number of rows written
        """
        if not results:
            return 0
        
        # Convert dicts to 2D array
        headers = list(results[0].keys())
        values = []
        
        if include_header:
            values.append(headers)
        
        for result in results:
            row = [result.get(h, '') for h in headers]
            values.append(row)
        
        return self.batch_append_rows(values, sheet_name)
    
    def estimate_payload_size(self, values: List[List[Any]]) -> int:
        """
        Estimate the payload size for a values array.

        Args:
            values: 2D list of values

        Returns:
            Estimated size in bytes
        """
        import json
        return len(json.dumps(values).encode('utf-8'))
    
    def get_api_stats(self) -> Dict[str, Any]:
        """Get API usage statistics."""
        return {
            "requests_remaining": self.rate_limiter.get_remaining(),
            **self.api_counter.get_stats()
        }
    
    def reset_rate_limiter(self) -> None:
        """Reset the rate limiter (use with caution)."""
        self.rate_limiter.reset()
        logger.info("Rate limiter reset")


# Configuration from environment
CREDENTIALS_PATH = os.getenv('GOOGLE_SHEETS_CREDENTIALS', 'credentials/google_sheets.json')
DEFAULT_SPREADSHEET_ID = os.getenv('GOOGLE_SHEETS_SPREADSHEET_ID', '')
INPUT_SHEET_NAME = os.getenv('INPUT_SHEET_NAME', 'Parameter Tuning')
OUTPUT_SHEET_NAME = os.getenv('OUTPUT_SHEET_NAME', 'Automated Results')
OUTPUT_PER_GENOME_SHEET_NAME = os.getenv('OUTPUT_PER_GENOME_SHEET_NAME', 'Automated Results Per Genome')


class SheetsService:
    """
    Legacy-compatible SheetsService class.
    
    Provides the original API expected by controllers and services.
    """
    
    def __init__(self, sheet_id: Optional[str] = None):
        """Initialize SheetsService."""
        self.sheet_id = sheet_id or DEFAULT_SPREADSHEET_ID
        self._service = None
        self._gspread_client = None
    
    def _get_gspread_client(self):
        """Get or create gspread client."""
        if self._gspread_client is None:
            try:
                import gspread
                from google.oauth2.service_account import Credentials
                
                scopes = [
                    'https://www.googleapis.com/auth/spreadsheets',
                    'https://www.googleapis.com/auth/drive'
                ]
                
                if os.path.exists(CREDENTIALS_PATH):
                    credentials = Credentials.from_service_account_file(
                        CREDENTIALS_PATH,
                        scopes=scopes
                    )
                    self._gspread_client = gspread.authorize(credentials)
                else:
                    logger.warning(f"Credentials file not found: {CREDENTIALS_PATH}")
                    
            except Exception as e:
                logger.error(f"Failed to initialize gspread client: {e}")
        
        return self._gspread_client
    
    def check_read_permission(self) -> bool:
        """Check if read permission is available."""
        try:
            client = self._get_gspread_client()
            if client and self.sheet_id:
                sheet = client.open_by_key(self.sheet_id)
                # Try to read first worksheet
                worksheet = sheet.get_worksheet(0)
                worksheet.get('A1')
                return True
        except Exception as e:
            logger.debug(f"Read permission check failed: {e}")
        return False
    
    def check_write_permission(self) -> bool:
        """Check if write permission is available."""
        # For service accounts, read permission typically implies write
        return self.check_read_permission()
    
    def get_sheet_config(self) -> Dict[str, Any]:
        """Get sheet configuration."""
        return {
            "spreadsheet_id": self.sheet_id,
            "credentials_path": CREDENTIALS_PATH,
            "credentials_exist": os.path.exists(CREDENTIALS_PATH)
        }
    
    @staticmethod
    def write_genome_results(
        sheet_id: str,
        data: List[Dict[str, Any]],
        worksheet_name: str = OUTPUT_SHEET_NAME,
        fieldnames: Optional[List[str]] = None
    ) -> bool:
        """
        Write genome results to a Google Sheet.
        
        Args:
            sheet_id: Google Spreadsheet ID
            data: List of result dictionaries
            worksheet_name: Target worksheet name
            fieldnames: Optional ordered list of column names. If not provided, uses keys from first row.
        
        Returns:
            True on success, False on failure
        """
        if not data:
            logger.warning("No data to write")
            return False
        
        try:
            import gspread
            from google.oauth2.service_account import Credentials
            
            scopes = [
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive'
            ]
            
            if not os.path.exists(CREDENTIALS_PATH):
                logger.error(f"Credentials file not found: {CREDENTIALS_PATH}")
                return False
            
            credentials = Credentials.from_service_account_file(
                CREDENTIALS_PATH,
                scopes=scopes
            )
            client = gspread.authorize(credentials)
            
            spreadsheet = client.open_by_key(sheet_id)
            
            # Get or create worksheet
            try:
                worksheet = spreadsheet.worksheet(worksheet_name)
            except gspread.WorksheetNotFound:
                worksheet = spreadsheet.add_worksheet(
                    title=worksheet_name,
                    rows=len(data) + 100,
                    cols=(len(fieldnames) if fieldnames else len(data[0])) + 5
                )
            
            # Prepare data with ordered headers
            headers = fieldnames if fieldnames else list(data[0].keys())
            values = [headers]
            for row in data:
                values.append([row.get(h, '') for h in headers])
            
            # Clear and write
            worksheet.clear()
            worksheet.update('A1', values)
            
            logger.info(f"Wrote {len(data)} rows to {worksheet_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to write genome results: {e}")
            return False


def read_parameter_ranges_from_sheets(sheet_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Read parameter ranges from Google Sheets.
    
    Args:
        sheet_id: Google Spreadsheet ID (uses default if not provided)
    
    Returns:
        List of parameter range dictionaries
    """
    sheet_id = sheet_id or DEFAULT_SPREADSHEET_ID
    
    if not sheet_id:
        logger.error("No sheet_id provided and no default configured")
        return []
    
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        
        if not os.path.exists(CREDENTIALS_PATH):
            logger.error(f"Credentials file not found: {CREDENTIALS_PATH}")
            return []
        
        credentials = Credentials.from_service_account_file(
            CREDENTIALS_PATH,
            scopes=scopes
        )
        client = gspread.authorize(credentials)
        
        spreadsheet = client.open_by_key(sheet_id)
        
        # Look for parameter ranges worksheet
        worksheet_names = [INPUT_SHEET_NAME, "Parameter Tuning Example", "Parameter Ranges", "Parameters", "Input", "Sheet1"]
        worksheet = None
        found_name = None
        
        # Log available worksheets for debugging
        all_worksheets = [ws.title for ws in spreadsheet.worksheets()]
        logger.info(f"Available worksheets in sheet {sheet_id}: {all_worksheets}")
        
        for name in worksheet_names:
            try:
                worksheet = spreadsheet.worksheet(name)
                found_name = name
                break
            except gspread.WorksheetNotFound:
                continue
        
        if worksheet is None:
            # Try first worksheet
            worksheet = spreadsheet.get_worksheet(0)
            found_name = worksheet.title if worksheet else "None"
        
        logger.info(f"Using worksheet: {found_name}")
        
        # Get all values (handle duplicate/empty headers manually)
        all_values = worksheet.get_all_values()
        logger.info(f"Raw values shape: {len(all_values)} rows")
        
        if not all_values or len(all_values) < 2:
            logger.warning(f"No parameter ranges found in sheet {sheet_id}")
            return []
        
        # Get headers from first row, filter out empty ones
        raw_headers = all_values[0]
        logger.info(f"Raw headers: {raw_headers}")
        
        # Create unique headers (handle duplicates and empty cells)
        headers = []
        header_counts = {}
        for i, h in enumerate(raw_headers):
            h = str(h).strip()
            if not h:
                h = f"Column_{i}"
            if h in header_counts:
                header_counts[h] += 1
                h = f"{h}_{header_counts[h]}"
            else:
                header_counts[h] = 0
            headers.append(h)
        
        # Parse data rows
        records = []
        for row in all_values[1:]:
            if not any(cell.strip() for cell in row):
                continue  # Skip empty rows
            record = {}
            for i, value in enumerate(row):
                if i < len(headers):
                    record[headers[i]] = value
            records.append(record)
        
        if not records:
            logger.warning(f"No parameter range data rows found in sheet {sheet_id}")
            return []
        
        logger.info(f"Parsed {len(records)} records, first record keys: {list(records[0].keys()) if records else 'None'}")
        if records:
            logger.info(f"First record sample: {records[0]}")
        
        # Map to expected format
        parameter_ranges = []
        for record in records:
            try:
                # Try different possible column names
                param_var = (record.get("Parameter Variable") or 
                           record.get("name") or 
                           record.get("Parameter") or 
                           record.get("Variable") or "")
                
                if not param_var:
                    logger.debug(f"Skipping row without parameter name: {record}")
                    continue  # Skip rows without parameter name
                
                def safe_float(val, default=0.0):
                    try:
                        if val is None or str(val).strip() == '':
                            return default
                        return float(str(val).replace(',', '.'))
                    except (ValueError, TypeError):
                        return default
                
                def safe_bool(val):
                    if isinstance(val, bool):
                        return val
                    if isinstance(val, str):
                        return val.lower() in ('true', 'yes', '1', 'y')
                    return bool(val)
                
                param = {
                    "Parameter Variable": str(param_var).strip(),
                    "Base": safe_float(record.get("Base", record.get("base", 0))),
                    "Min": safe_float(record.get("Min", record.get("min", 0))),
                    "Max": safe_float(record.get("Max", record.get("max", 0))),
                    "Step": safe_float(record.get("Step", record.get("step", 1)), 1.0),
                    "Change": safe_bool(record.get("Change", record.get("change", False))),
                    "Rule": str(record.get("Rule", record.get("rule", ""))).strip()
                }
                parameter_ranges.append(param)
            except Exception as row_error:
                logger.warning(f"Failed to parse parameter row: {record}, error: {row_error}")
                continue
        
        logger.info(f"Read {len(parameter_ranges)} parameter ranges from Google Sheets")
        return parameter_ranges
        
    except Exception as e:
        logger.error(f"Failed to read parameter ranges from sheets: {e}")
        return []
