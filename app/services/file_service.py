"""
File Service

Provides optimized file I/O operations including:
- Buffered CSV writing for reduced I/O overhead
- Atomic file writes to prevent corruption
- Dual storage (Google Sheets + CSV backup)
"""

import csv
import os
import json
import logging
from typing import Any
from pathlib import Path
from contextlib import contextmanager
import tempfile
import shutil
import threading

from app.utils.performance_profiler import timed, TimingContext

logger = logging.getLogger(__name__)

DEFAULT_CSV_FILENAME = "Automated Results.csv"
DEFAULT_BUFFER_SIZE = 1000


class BufferedCSVWriter:
    """
    Buffered CSV writer for efficient file I/O.
    
    Accumulates rows in memory and flushes to disk in batches
    to reduce I/O overhead.
    
    Args:
        filepath: Path to the CSV file
        buffer_size: Number of rows to buffer before flushing (default: 1000)
        fieldnames: Column headers (required for new files)
        append: Whether to append to existing file (default: True)
    
    Example:
        with BufferedCSVWriter("results.csv", fieldnames=["a", "b"]) as writer:
            for row in data:
                writer.write_row(row)
    """
    
    def __init__(
        self, 
        filepath: str, 
        buffer_size: int = DEFAULT_BUFFER_SIZE,
        fieldnames: list[str] | None = None,
        append: bool = True
    ):
        self.filepath = filepath
        self.buffer_size = buffer_size
        self.fieldnames = fieldnames
        self.append = append
        self.buffer: list[dict[str, Any]] = []
        self._file_handle = None
        self._writer = None
        self._rows_written = 0
        self._flush_count = 0
    
    def __enter__(self) -> 'BufferedCSVWriter':
        self._open()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
    
    def _open(self) -> None:
        """Open the file for writing."""
        file_exists = os.path.exists(self.filepath)
        mode = 'a' if self.append and file_exists else 'w'
        
        self._file_handle = open(self.filepath, mode, newline='', encoding='utf-8')
        self._writer = csv.DictWriter(self._file_handle, fieldnames=self.fieldnames or [])
        
        # Write header for new files
        if mode == 'w' and self.fieldnames:
            self._writer.writeheader()
            logger.debug(f"Created new CSV file: {self.filepath}")
        elif mode == 'a':
            logger.debug(f"Appending to existing CSV file: {self.filepath}")
    
    def write_row(self, row: dict[str, Any]) -> None:
        """
        Add a row to the buffer.
        
        Automatically flushes when buffer is full.
        """
        # Infer fieldnames from first row if not provided
        if not self.fieldnames and row:
            self.fieldnames = list(row.keys())
            self._writer = csv.DictWriter(self._file_handle, fieldnames=self.fieldnames)
            self._writer.writeheader()
        
        self.buffer.append(row)
        
        if len(self.buffer) >= self.buffer_size:
            self.flush()
    
    def write_rows(self, rows: list[dict[str, Any]]) -> None:
        """Add multiple rows to the buffer."""
        for row in rows:
            self.write_row(row)
    
    @timed("csv_buffer_flush")
    def flush(self) -> None:
        """Flush the buffer to disk."""
        if not self.buffer:
            return
        
        self._writer.writerows(self.buffer)
        self._file_handle.flush()
        
        self._rows_written += len(self.buffer)
        self._flush_count += 1
        
        logger.debug(f"Flushed {len(self.buffer)} rows to CSV (total: {self._rows_written})")
        self.buffer.clear()
    
    def close(self) -> None:
        """Flush remaining buffer and close the file."""
        self.flush()
        if self._file_handle:
            self._file_handle.close()
            self._file_handle = None
        
        logger.info(
            f"CSV write complete: {self._rows_written} rows in {self._flush_count} flushes"
        )
    
    @property
    def stats(self) -> dict[str, int]:
        """Get write statistics."""
        return {
            "rows_written": self._rows_written,
            "flush_count": self._flush_count,
            "buffer_size": len(self.buffer)
        }


@timed("atomic_csv_write")
def write_csv_atomic(
    filepath: str, 
    data: list[dict[str, Any]], 
    fieldnames: list[str] | None = None
) -> bool:
    """
    Write data to CSV atomically using temp file + rename.
    
    Ensures no partial writes on failure.
    
    Args:
        filepath: Destination file path
        data: List of row dictionaries
        fieldnames: Column headers (inferred from first row if not provided)
    
    Returns:
        True on success, False on failure
    """
    if not data:
        logger.warning("No data to write")
        return False
    
    fieldnames = fieldnames or list(data[0].keys())
    temp_path = f"{filepath}.tmp.{os.getpid()}"
    
    try:
        with open(temp_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)
        
        # Atomic rename
        os.replace(temp_path, filepath)
        logger.info(f"Atomically wrote {len(data)} rows to {filepath}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to write CSV: {e}")
        # Clean up temp file
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return False


def read_csv_to_dicts(filepath: str) -> list[dict[str, Any]]:
    """
    Read CSV file into list of dictionaries.
    
    Args:
        filepath: Path to CSV file
    
    Returns:
        List of row dictionaries
    """
    if not os.path.exists(filepath):
        logger.warning(f"CSV file not found: {filepath}")
        return []
    
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        return list(reader)


def get_last_written_row(filepath: str) -> int:
    """
    Get the number of rows already written to a CSV file.
    
    Useful for resume capability.
    
    Args:
        filepath: Path to CSV file
    
    Returns:
        Number of data rows (excluding header), 0 if file doesn't exist
    """
    if not os.path.exists(filepath):
        return 0
    
    with open(filepath, 'r', encoding='utf-8') as f:
        # Count lines minus header
        return sum(1 for _ in f) - 1


class DualStorageManager:
    """
    Manager for dual storage (Google Sheets + local CSV).
    
    Ensures data is saved to both destinations with proper error handling.
    
    Args:
        csv_path: Path for local CSV backup (default: "Automated Results.csv")
        sheets_service: Google Sheets service instance (optional)
        buffer_size: Buffer size for CSV writer
    """
    
    def __init__(
        self,
        csv_path: str = DEFAULT_CSV_FILENAME,
        sheets_service: Any | None = None,
        buffer_size: int = DEFAULT_BUFFER_SIZE
    ):
        self.csv_path = csv_path
        self.sheets_service = sheets_service
        self.buffer_size = buffer_size
        self._csv_writer: BufferedCSVWriter | None = None
        self._pending_sheets_rows: list[dict[str, Any]] = []
        self._sheets_batch_size = 100
    
    def __enter__(self) -> 'DualStorageManager':
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
    
    @timed("dual_storage_save_row")
    def save_row(self, row: dict[str, Any]) -> None:
        """
        Save a single result row to both storages.
        
        CSV is written immediately (buffered), Sheets is batched.
        """
        # Write to CSV first (local backup takes priority)
        if self._csv_writer is None:
            fieldnames = list(row.keys())
            self._csv_writer = BufferedCSVWriter(
                self.csv_path, 
                buffer_size=self.buffer_size,
                fieldnames=fieldnames
            )
            self._csv_writer._open()
        
        self._csv_writer.write_row(row)
        
        # Queue for Google Sheets
        if self.sheets_service:
            self._pending_sheets_rows.append(row)
            if len(self._pending_sheets_rows) >= self._sheets_batch_size:
                self._flush_to_sheets()
    
    def save_rows(self, rows: list[dict[str, Any]]) -> None:
        """Save multiple rows to both storages."""
        for row in rows:
            self.save_row(row)
    
    @timed("sheets_batch_update")
    def _flush_to_sheets(self) -> bool:
        """Flush pending rows to Google Sheets."""
        if not self._pending_sheets_rows or not self.sheets_service:
            return True
        
        try:
            # Convert to values format for Sheets API
            if self._pending_sheets_rows:
                headers = list(self._pending_sheets_rows[0].keys())
                values = [
                    [row.get(h, '') for h in headers] 
                    for row in self._pending_sheets_rows
                ]
                
                # Call sheets service batch update
                self.sheets_service.batch_append_rows(values)
                
            logger.debug(f"Flushed {len(self._pending_sheets_rows)} rows to Google Sheets")
            self._pending_sheets_rows.clear()
            return True
            
        except Exception as e:
            logger.error(f"Failed to flush to Google Sheets: {e}")
            # Keep rows for retry
            return False
    
    def flush(self) -> None:
        """Flush all pending writes."""
        if self._csv_writer:
            self._csv_writer.flush()
        self._flush_to_sheets()
    
    def close(self) -> None:
        """Close all resources and flush pending data."""
        if self._csv_writer:
            self._csv_writer.close()
            self._csv_writer = None
        
        self._flush_to_sheets()
        
        logger.info(f"Dual storage closed. CSV saved to: {self.csv_path}")
    
    def get_resume_position(self) -> int:
        """Get the row count for resume capability."""
        return get_last_written_row(self.csv_path)


@timed("save_with_backup")
def save_with_backup(
    results: list[dict[str, Any]],
    sheets_service: Any | None = None,
    csv_path: str = DEFAULT_CSV_FILENAME
) -> bool:
    """
    Save results to both Google Sheets and local CSV.
    
    CSV is written first atomically to ensure local backup exists.
    
    Args:
        results: List of result dictionaries
        sheets_service: Optional Google Sheets service
        csv_path: Path for CSV backup
    
    Returns:
        True if both saves successful, False if either failed
    """
    if not results:
        logger.warning("No results to save")
        return False
    
    csv_success = False
    sheets_success = False
    
    # Save to CSV first (atomic write)
    with TimingContext("csv_backup_write"):
        csv_success = write_csv_atomic(csv_path, results)
    
    if not csv_success:
        logger.error("Failed to save CSV backup")
    
    # Then upload to Google Sheets
    if sheets_service:
        with TimingContext("sheets_upload"):
            try:
                sheets_service.batch_update(results)
                sheets_success = True
                logger.info(f"Uploaded {len(results)} results to Google Sheets")
            except Exception as e:
                logger.error(f"Failed to upload to Google Sheets: {e}")
    else:
        sheets_success = True  # No sheets service = skip
    
    return csv_success and sheets_success


class FileService:
    """
    File service for CSV operations.
    
    Provides async methods for reading and writing CSV files
    in the data directory.
    """
    
    DATA_DIR = "data"
    
    def __init__(self):
        """Initialize FileService and ensure data directory exists."""
        os.makedirs(self.DATA_DIR, exist_ok=True)
    
    @property
    def data_dir(self) -> str:
        """Get the data directory path (for backward compatibility)."""
        return self.DATA_DIR
    
    def _get_filepath(self, file_name: str) -> str:
        """Get full file path for a file name."""
        if not file_name.endswith('.csv'):
            file_name = f"{file_name}.csv"
        return os.path.join(self.DATA_DIR, file_name)
    
    async def add_data_to_csv(
        self, 
        file_name: str, 
        data: list[dict[str, Any]], 
        fieldnames: list[str] | None = None
    ) -> bool:
        """
        Add data to a CSV file (append if exists, create if not).
        
        Args:
            file_name: Name of the CSV file (without .csv extension)
            data: List of dictionaries to write
            fieldnames: Column headers (inferred from first row if not provided)
        
        Returns:
            True on success, False on failure
        """
        if not data:
            logger.warning(f"No data to write to {file_name}")
            return False
        
        filepath = self._get_filepath(file_name)
        fieldnames = fieldnames or list(data[0].keys())
        
        try:
            file_exists = os.path.exists(filepath)
            mode = 'a' if file_exists else 'w'
            
            with self._write_lock:
                with open(filepath, mode, newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    
                    # Write header only for new files
                    if not file_exists:
                        writer.writeheader()
                    
                    writer.writerows(data)
            
            logger.debug(f"Added {len(data)} rows to {filepath}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to write to {filepath}: {e}")
            return False
    
    async def read_data_from_csv(self, file_name: str) -> list[dict[str, Any]]:
        """
        Read data from a CSV file.
        
        Args:
            file_name: Name of the CSV file (without .csv extension)
        
        Returns:
            List of row dictionaries, empty list if file not found
        """
        filepath = self._get_filepath(file_name)
        
        if not os.path.exists(filepath):
            logger.warning(f"CSV file not found: {filepath}")
            return []
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                return list(reader)
        except Exception as e:
            logger.error(f"Failed to read from {filepath}: {e}")
            return []
    
    async def clear_csv(self, file_name: str) -> bool:
        """
        Clear/delete a CSV file.
        
        Args:
            file_name: Name of the CSV file
        
        Returns:
            True if deleted or didn't exist, False on error
        """
        filepath = self._get_filepath(file_name)
        
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
                logger.info(f"Cleared CSV file: {filepath}")
            return True
        except Exception as e:
            logger.error(f"Failed to clear {filepath}: {e}")
            return False
    
    async def file_exists(self, file_name: str) -> bool:
        """Check if a CSV file exists."""
        filepath = self._get_filepath(file_name)
        return os.path.exists(filepath)

    _write_lock = threading.Lock()