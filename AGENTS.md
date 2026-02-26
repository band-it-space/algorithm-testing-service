# AGENTS.md - Algorithm Testing Service

> **For AI Agents:** This file is your technical source of truth. Read this before any coding task.

---

## 1. Project Overview

**What is this?**  
Algorithm Testing Service is a **Python-based FastAPI microservice** for backtesting trading algorithms using a Redis queue-based worker architecture. It processes stock market data, generates buy/sell signals using technical indicators, and produces detailed trading performance reports.

**Tech Stack:**

- **Language:** Python 3.11
- **Framework:** FastAPI 0.104.1
- **ASGI Server:** Uvicorn 0.24.0
- **Data Models:** Pydantic 2.5.0
- **Message Queue:** Redis 5.0.1 (redis-py)
- **Task Queue:** RQ (Redis Queue) 1.15.1
- **Monitoring:** RQ Dashboard 0.8.5
- **Data Processing:** pandas 2.1.3, numpy, python-dateutil
- **Database:** MySQL (mysql-connector-python 8.3.0, aiomysql)
- **HTTP Client:** requests 2.32.3, aiohttp
- **Excel Support:** openpyxl 3.1.5
- **Configuration:** python-dotenv 1.0.1
- **Containerization:** Docker, docker-compose

**Architecture:**

Multi-layer queue-based asynchronous processing system:

```
API Layer (FastAPI Controllers)
    ↓ Enqueue Tasks
Queue Layer (Redis + RQ)
    ↓ Process Jobs
Worker Layer (Background Workers)
    ↓ Call Business Logic
Service Layer (FileService, QueueService)
    ↓ Access Data
Data Layer (CSV Files, External APIs)
```

**Core Algorithms:**

- **HK Algorithm:** Hong Kong stock market signal generation (B1-B18 buy signals, S1-S18 sell signals)
- **US King Algorithm:** US market trading with energy indicators (E1-E5)

**Queue Workflow:**

1. `us_king_calculation_queue` → US King Algorithm Worker
2. `algorithm_calculation_queue` → HK Algorithm Worker
3. `result_processing_queue` → Result Worker (validation & aggregation)
4. `file_write_queue` → File Write Worker (CSV persistence)

---

## 2. Operational Commands

**Critical:** Always use these exact commands. Do not guess alternatives.

### Setup & Start

```bash
# Initial setup
cp .env.example .env
# Edit .env with your API keys

# Start all services
docker-compose up -d --build

# Stop all services
docker-compose down
```

**Services:** API (port 8000), Redis (6379), Algorithm Worker, US King Worker, Result Worker, File Write Worker

### Common Commands

```bash
# View logs
docker-compose logs -f api
docker-compose logs -f algorithm-worker

# Check status
docker-compose ps
curl http://localhost:8000/health

# Restart service after code changes
docker-compose restart api
docker-compose up -d --build api

# Access container shell
docker-compose exec api /bin/bash

```

## 3. Development Rules

**Critical rules that linters CANNOT catch. Follow these strictly.**

### Naming Conventions

#### Files & Directories

- **Python files:** `snake_case.py` (e.g., `algorithm_worker.py`, `file_service.py`)
- **Directories:** `snake_case/` (e.g., `controllers/`, `algo_func/`)
- **Data files:** `snake_case.csv` (e.g., `us_king_results.csv`)

#### Classes & Types

- **Classes:** `PascalCase` (e.g., `FileService`, `AlgorithmRequest`, `OHLCV`)
- **Dataclasses:** `PascalCase` (e.g., `DailyTradingState`, `ProfitRecord`)
- **Pydantic models:** `PascalCase` (e.g., `AlgorithmRequest`, `TaskResponse`)

#### Functions & Variables

- **Functions:** `snake_case` - **ALWAYS** (e.g., `process_algorithm_task`, `check_b1`, `calculate_rsi`)
    - ⚠️ **NEVER use camelCase** for function names (no `checkB1`, `isBuy`, etc.)
- **Async functions:** `async def snake_case` (e.g., `async def get_stock_data`)
- **Private helpers:** `_leading_underscore` (e.g., `_read_existing_header`, `_to_float_or_zero`)
- **Local variables:** `snake_case` (e.g., `stock_code`, `task_id`, `file_path`)
- **Module constants:** `UPPER_SNAKE_CASE` (e.g., `HK_STOCKS_FILE`, `API_KEY`, `START_DATE`)

#### API Routes

- **Endpoints:** `kebab-case` (e.g., `/api/v1/start-testing/hkex`, `/api/v1/us-king`)
- **Router variables:** `snake_case` with `_router` suffix (e.g., `algorithm_router`)

### Type Hints Standard

**Critical:** Use modern Python 3.10+ syntax exclusively.

✅ **Correct (Modern Python 3.10+):**

```python
def process_data(items: list[str]) -> dict[str, int] | None:
    """Process items and return result dictionary."""
    pass

async def fetch_stock(code: str, start_date: str) -> OHLCV | None:
    """Fetch stock data from API."""
    pass

def calculate_indicators(values: list[float], period: int = 20) -> list[dict[str, float]]:
    """Calculate technical indicators."""
    pass
```

❌ **Forbidden (Legacy typing module):**

```python
from typing import List, Dict, Optional  # DO NOT USE

def process_data(items: List[str]) -> Optional[Dict[str, int]]:  # Legacy syntax
    pass
```

**Requirements:**

- **All functions/methods** must have type hints for parameters and return values
- Use `| None` instead of `Optional[...]`
- Use `list[...]` instead of `List[...]`
- Use `dict[..., ...]` instead of `Dict[..., ...]`
- Use `tuple[...]` instead of `Tuple[...]`

### Code Style & Language

#### Language

- **English only** for all code elements:
    - Docstrings
    - Comments
    - Variable names
    - Function names
    - Commit messages
    - Documentation
- **Never mix** Ukrainian/Russian with English in code

#### Import Organization

Follow PEP 8 import order:

```python
# 1. Standard library imports
import csv
import logging
import os
from datetime import datetime
from typing import Any

# 2. Third-party imports
import pandas as pd
import numpy as np
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# 3. Local application imports
from app.services.queue_service import QueueService
from app.services.file_service import FileService
from app.config.config import HK_STOCKS_FILE
from app.workers.algo_func.types import OHLCV
```

### Service Classes Pattern

**Standard:** Instance-based services with `__init__` for dependency injection.

✅ **Correct Pattern:**

```python
class FileService:
    """Service for CSV file operations."""

    def __init__(self, data_dir: str = "data"):
        """Initialize FileService with data directory.

        Args:
            data_dir: Path to data directory (default: "data")
        """
        self.data_dir = data_dir
        self.logger = logging.getLogger(__name__)

    async def add_data_to_csv(self, file_name: str, data: list[dict], fieldnames: list[str]) -> bool:
        """Add data to CSV file."""
        file_path = f"{self.data_dir}/{file_name}.csv"
        # Implementation
        return True
```

**Usage in Controllers:**

```python
@algorithm_router.get("/hkex")
async def init_algo_testing():
    file_service = FileService()  # Instantiate service
    stocks = await file_service.read_data_from_csv(HK_STOCKS_FILE)
    # ...
```

❌ **Avoid Static Methods (unless truly stateless):**

```python
class QueueService:
    @staticmethod  # Avoid this pattern for services with state
    def add_to_queue(data):
        pass
```

### Async/Await Guidelines

**Critical:** Async functions must not block the event loop.

❌ **Bad (Blocking I/O in async function):**

```python
async def process_file(file_path: str):
    # WRONG: Blocking file I/O
    with open(file_path, 'r') as f:
        data = f.read()

    # WRONG: Blocking HTTP request
    response = requests.get(API_URL)

    return data
```

✅ **Correct (Non-blocking I/O):**

```python
import aiofiles
import aiohttp

async def process_file(file_path: str):
    # Use aiofiles for async file I/O
    async with aiofiles.open(file_path, 'r') as f:
        data = await f.read()

    # Use aiohttp for async HTTP requests
    async with aiohttp.ClientSession() as session:
        async with session.get(API_URL) as response:
            result = await response.json()

    return data
```

**⚠️ Current Technical Debt:**  
Many async functions currently use blocking I/O (`open()`, `requests.get()`). This is documented for future refactoring. For new code, use `aiofiles` and `aiohttp`.

**Alternative for CPU-bound operations:**

```python
import asyncio

async def process_heavy_calculation(data: list):
    # Offload blocking CPU work to thread pool
    result = await asyncio.to_thread(heavy_calculation_function, data)
    return result
```

#### Controllers (API Layer)

Raise `HTTPException` with appropriate status codes:

```python
from fastapi import HTTPException

@algorithm_router.get("/hkex")
async def init_algo_testing():
    try:
        file_service = FileService()
        stocks = await file_service.read_data_from_csv(HK_STOCKS_FILE)

        if not stocks:
            raise HTTPException(status_code=404, detail="No stocks found in screener file")

        # Process stocks...
        return {"status": "success", "count": len(stocks)}

    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"File not found: {str(e)}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid data: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error in init_algo_testing: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
```

#### Workers (Background Tasks)

Log error and re-raise for RQ failure handling:

```python
async def process_algorithm_task(task_data: dict[str, Any]) -> dict[str, str]:
    """Process algorithm task."""
    try:
        stock_code = task_data['stock']
        logger.info(f"Processing algorithm task for stock: {stock_code}")

        # Multi-step processing
        await get_data_and_save_to_csv(stock_code, START_DATE)
        await signals_for_the_period(stock_code, END_DATE)

        # Chain to next queue
        processing_task_id = QueueService.add_to_result_processing_queue(stock_code)
        logger.info(f"Task {task_data['task_id']} completed, chained to {processing_task_id}")

        return task_data

    except Exception as e:
        logger.error(f"Error processing task {task_data.get('task_id', 'unknown')}: {str(e)}", exc_info=True)
        raise e  # Re-raise for RQ to mark job as failed
```

**Why re-raise:** RQ needs the exception to mark the job as failed and potentially retry it.

#### Services (Business Logic)

Return `False` / `None` / empty collections, log warnings:

```python
async def add_data_to_csv(self, file_name: str, data: list[dict], fieldnames: list[str]) -> bool:
    """Add data to CSV file."""
    try:
        file_path = f"{self.data_dir}/{file_name}.csv"
        # File operations...
        logger.info(f"Successfully wrote {file_path} with {len(data)} records")
        return True

    except PermissionError as e:
        logger.warning(f"Permission denied writing to {file_path}: {e}")
        return False
    except Exception as e:
        logger.error(f"Error creating CSV file {file_path}: {e}")
        return False
```

**Why not raise:** Services are called by workers that handle their own error logic.

#### Algorithm Functions (Pure Logic)

Raise descriptive exceptions or return early:

```python
def check_b1(ohlcv: list[OHLCV], target_date: str) -> bool:
    """Check B1 buy signal condition.

    Raises:
        ValueError: If date is outside data range
    """
    if len(ohlcv) < 51:
        return False  # Insufficient data, not an error

    buy_idx = next((i for i, candle in enumerate(ohlcv) if candle.date == target_date), -1)
    if buy_idx == -1:
        raise ValueError(f"Target date {target_date} is outside data range")

    # Algorithm logic...
    return signal_detected
```

### Logging Standard

**Pattern:** Use Python's standard logging module, never `print()`.

✅ **Correct:**

```python
import logging

logger = logging.getLogger(__name__)

async def process_task(task_id: str, stock_code: str):
    logger.info(f"Starting task {task_id} for stock {stock_code}")

    try:
        result = await fetch_data(stock_code)
        logger.debug(f"Fetched {len(result)} records for {stock_code}")

        if not result:
            logger.warning(f"No data found for stock {stock_code}")
            return None

        logger.info(f"Task {task_id} completed successfully")
        return result

    except Exception as e:
        logger.error(f"Task {task_id} failed: {str(e)}", exc_info=True)
        raise
```

❌ **Forbidden:**

```python
print(f"Processing task {task_id}")  # NEVER use print()
print("Debug:", stock_code)  # Use logger.debug() instead
```

**Log Levels:**

- `logger.debug()` - Verbose diagnostic information (disabled in production)
- `logger.info()` - General informational messages (task started, completed)
- `logger.warning()` - Recoverable issues (missing optional data, retries)
- `logger.error()` - Errors that prevent task completion
- `logger.critical()` - System-level failures

**Log Formatting:**

- Use f-strings with context: `f"Processing stock {stock_code} for task {task_id}"`
- Include identifiers: task IDs, stock codes, file paths
- Use `exc_info=True` for stack traces: `logger.error("Error", exc_info=True)`

**Logger Naming:**

```python
# At module level
logger = logging.getLogger(__name__)  # Recommended: uses module path

# In main.py or special cases
logger = logging.getLogger("app.api")  # Custom name
```

**Configuration:** Logging is centralized in `app/config/logging_config.py` with:

- Daily rotating file handlers (7-day retention)
- Separate log files per component (api, algorithm-worker, result-worker)
- Configurable log level via `LOG_LEVEL` environment variable

---

## 4. Architecture Patterns

### Layer Responsibilities

#### Controllers (API Layer)

**Location:** `app/controllers/`  
**Files:** `algorithm_controller.py`, `summary_controller.py`, `monitoring_controller.py`

**Responsibilities:**

- Define API endpoints with FastAPI routers
- Validate request data (Pydantic models)
- Call services to perform business logic
- Enqueue tasks to Redis queues
- Return HTTP responses
- Handle HTTP exceptions

**Pattern:**

```python
from fastapi import APIRouter, HTTPException
from app.services.queue_service import QueueService
from app.services.file_service import FileService
from app.models.algorithm_models import AlgorithmRequest
from app.config.config import HK_STOCKS_FILE

algorithm_router = APIRouter()

@algorithm_router.get("/hkex", tags=["Algorithm Testing"])
async def init_algo_testing():
    """Initiate HK algorithm testing for all stocks in screener."""
    try:
        # Instantiate services
        file_service = FileService()

        # Read input data
        stocks = await file_service.read_data_from_csv(HK_STOCKS_FILE)
        exist = await file_service.read_data_from_csv("results")
        existing_codes = {str(item.get("stock_code")) for item in exist}

        # Enqueue tasks for processing
        added = []
        for stock in stocks:
            code = str(stock.get("Code")).strip()
            if code not in existing_codes:
                task_id = QueueService.add_to_algorithm_queue(code)
                added.append({"stock": code, "task_id": task_id})

        return {
            "message": f"Added {len(added)} stocks to processing queue",
            "status": "queued",
            "tasks": added
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to initialize testing: {str(e)}")
```

**Key Points:**

- No business logic in controllers (delegate to services)
- Always use try-except with HTTPException
- Return clear, structured responses
- Use Pydantic models for request validation

#### Services (Business Logic)

**Location:** `app/services/`  
**Files:** `file_service.py`, `queue_service.py`

**Responsibilities:**

- Implement business logic
- Abstract data access (CSV files, external APIs)
- Provide reusable methods for controllers and workers
- Handle errors gracefully (return False/None, log warnings)

**FileService Pattern:**

```python
import csv
import logging
import os

class FileService:
    """Service for CSV file operations."""

    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        self.logger = logging.getLogger(__name__)

    async def read_data_from_csv(self, file_name: str) -> list[dict]:
        """Read data from CSV file.

        Args:
            file_name: Name of CSV file (without .csv extension)

        Returns:
            List of dictionaries representing CSV rows
        """
        try:
            file_path = f"{self.data_dir}/{file_name}.csv"

            if not os.path.exists(file_path):
                self.logger.warning(f"File {file_path} does not exist")
                return []

            with open(file_path, mode='r', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                data = list(reader)

            self.logger.debug(f"Read {len(data)} records from {file_path}")
            return data

        except Exception as e:
            self.logger.error(f"Error reading CSV file {file_path}: {e}")
            return []

    async def add_data_to_csv(self, file_name: str, data: list[dict], fieldnames: list[str]) -> bool:
        """Add data to CSV file with schema validation.

        If header matches existing file, appends data.
        If header differs, rewrites file with new schema.
        """
        try:
            file_path = f"{self.data_dir}/{file_name}.csv"
            os.makedirs(os.path.dirname(file_path), exist_ok=True)

            # Check if existing header matches
            existing_header = self._read_existing_header(file_path)
            if existing_header == list(fieldnames):
                mode = 'a'  # Append
                write_header = False
            else:
                mode = 'w'  # Overwrite with new schema
                write_header = True

            with open(file_path, mode, newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                if write_header:
                    writer.writeheader()
                for row in data:
                    writer.writerow(row)

            self.logger.info(f"Successfully wrote {len(data)} records to {file_path}")
            return True

        except Exception as e:
            self.logger.error(f"Error writing to CSV file {file_path}: {e}")
            return False

    def _read_existing_header(self, file_path: str) -> list[str] | None:
        """Read existing CSV header."""
        try:
            if not os.path.exists(file_path):
                return None
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                return next(reader, None)
        except Exception:
            return None
```

**QueueService Pattern:**

```python
import uuid
import logging
from datetime import datetime
from app.config.queue_config import (
    algorithm_calculation_queue,
    result_processing_queue,
    us_king_calculation_queue
)

class QueueService:
    """Service for task queue management."""

    @staticmethod
    def add_to_algorithm_queue(stock_code: str) -> str:
        """Add HK algorithm task to queue.

        Args:
            stock_code: Stock code to process

        Returns:
            Unique task ID
        """
        task_id = str(uuid.uuid4())

        task_data = {
            "task_id": task_id,
            "stock": stock_code,
            "created_at": datetime.now().isoformat(),
            "queue_name": "algorithm_calculation"
        }

        job = algorithm_calculation_queue.enqueue(
            'app.workers.algorithm_worker.process_algorithm_task',
            task_data,
            job_id=task_id
        )

        logger = logging.getLogger(__name__)
        logger.info(f"Enqueued algorithm task {task_id} for stock {stock_code}")

        return task_id

    @staticmethod
    def add_to_result_processing_queue(stock_code: str) -> str:
        """Chain task to result processing queue."""
        # Similar implementation...
        pass
```

**Key Points:**

- Instance-based services with `__init__` (preferred pattern)
- Static methods allowed for truly stateless operations (QueueService)
- Return success/failure indicators (bool, None, [])
- Log all operations with context

#### Workers (Background Processing)

**Location:** `app/workers/`  
**Files:** `algorithm_worker.py`, `us_king_worker.py`, `result_worker.py`, `file_write_worker.py`

**Responsibilities:**

- Process tasks from Redis queues
- Perform long-running calculations
- Chain tasks to subsequent queues
- Handle errors and log failures

**Worker Pattern:**

```python
import logging
from app.services.queue_service import QueueService
from app.services.file_service import FileService
from app.workers.algo_func.buy_signals import check_all_buy_signals
from app.workers.algo_func.sell_signals import check_all_sell_signals
from app.config.config import START_DATE, END_DATE

logger = logging.getLogger(__name__)

async def process_algorithm_task(task_data: dict[str, Any]) -> dict[str, str]:
    """Process HK algorithm calculation task.

    This worker:
    1. Fetches stock data from external API
    2. Generates buy/sell signals
    3. Formats results for CSV output
    4. Chains to result processing queue

    Args:
        task_data: Task metadata from queue

    Returns:
        Task data with processing status

    Raises:
        Exception: Re-raised for RQ failure handling
    """
    try:
        stock_code = task_data['stock']
        task_id = task_data['task_id']

        logger.info(f"Processing algorithm task {task_id} for stock {stock_code}")

        # Step 1: Fetch and save stock data
        await get_data_and_save_to_csv(stock_code, START_DATE)

        # Step 2: Generate signals
        await signals_for_the_period(stock_code, END_DATE)

        # Step 3: Format results
        file_service = FileService()
        await format_signals_csv_inplace(file_service=file_service, file_name=stock_code)

        # Step 4: Chain to next queue
        processing_task_id = QueueService.add_to_result_processing_queue(stock_code)

        logger.info(f"Task {task_id} completed successfully, chained to {processing_task_id}")

        return task_data

    except Exception as e:
        logger.error(
            f"Error processing algorithm task {task_data.get('task_id', 'unknown')}: {str(e)}",
            exc_info=True
        )
        raise e  # Re-raise for RQ to mark as failed
```

**Worker Startup Script:**

```python
#!/usr/bin/env python3
# File: workers/start_algorithm_worker.py

import sys
import os
import logging

# Add project root to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rq import Worker, Connection
from app.config.logging_config import setup_logging
from app.config.queue_config import redis_conn, algorithm_calculation_queue

def main():
    setup_logging()
    logger = logging.getLogger("app.workers.algorithm_worker")

    logger.info("Starting Algorithm Worker...")
    logger.info(f"Connected to Redis at {redis_conn.connection_pool.connection_kwargs['host']}")

    with Connection(redis_conn):
        worker = Worker([algorithm_calculation_queue])
        logger.info("Worker ready to process tasks")
        worker.work()

if __name__ == '__main__':
    main()
```

**Key Points:**

- Top-level async functions (not classes)
- Clear multi-step processing with logging
- Queue chaining for multi-stage workflows
- Re-raise exceptions for RQ failure handling
- Standalone startup scripts in `workers/` directory

#### Models (Data Validation)

**Location:** `app/models/`  
**Files:** `algorithm_models.py`

**Responsibilities:**

- Define Pydantic models for API requests/responses
- Provide automatic validation
- Generate OpenAPI schemas

**Pattern:**

```python
from pydantic import BaseModel, Field

class AlgorithmRequest(BaseModel):
    """Request model for algorithm testing."""
    stock_code: str = Field(..., min_length=1, max_length=20, description="Stock code to test")
    start_date: str = Field(..., pattern=r'^\d{4}-\d{2}-\d{2}$', description="Start date (YYYY-MM-DD)")
    end_date: str = Field(..., pattern=r'^\d{4}-\d{2}-\d{2}$', description="End date (YYYY-MM-DD)")

class TaskResponse(BaseModel):
    """Response model for task submission."""
    task_id: str = Field(..., description="Unique task identifier")
    status: str = Field(..., description="Task status (queued, processing, completed, failed)")
    message: str = Field(..., description="Human-readable status message")
```

#### Algorithm Functions (Pure Logic)

**Location:** `app/workers/algo_func/`  
**Files:** `buy_signals.py`, `sell_signals.py`, `get_code_energy.py`, `helpers.py`, `types.py`

**Responsibilities:**

- Implement technical indicator calculations
- Pure functions with no side effects
- Signal detection logic (buy/sell conditions)

**Pattern:**

```python
from app.workers.algo_func.types import OHLCV
from app.workers.algo_func.helpers import bollinger_bands, calculate_rsi

def check_b1(ohlcv: list[OHLCV], target_date: str) -> bool:
    """Check B1 buy signal: Price within BB and oversold RSI.

    Condition:
    - Close price within Bollinger Bands (20, 2)
    - RSI(14) < 30 (oversold)
    - Volume above 20-day average

    Args:
        ohlcv: List of OHLCV data (must include at least 51 candles)
        target_date: Date to check signal (YYYY-MM-DD format)

    Returns:
        True if B1 signal detected, False otherwise

    Raises:
        ValueError: If target_date not found in data
    """
    if len(ohlcv) < 51:
        return False  # Insufficient data for indicators

    # Find target date index
    buy_idx = next((i for i, candle in enumerate(ohlcv) if candle.date == target_date), -1)
    if buy_idx == -1:
        raise ValueError(f"Target date {target_date} is outside data range")

    # Calculate indicators
    closes = [c.close for c in ohlcv[:buy_idx + 1]]
    bb = bollinger_bands(closes, period=20, std_dev=2.0)
    rsi = calculate_rsi(closes, period=14)

    # Check conditions
    current_close = ohlcv[buy_idx].close
    current_bb = bb[-1]
    current_rsi = rsi[-1]

    within_bb = current_bb['lower'] <= current_close <= current_bb['upper']
    oversold = current_rsi < 30

    return within_bb and oversold
```

**Key Points:**

- Pure functions with explicit inputs/outputs
- No global state or side effects
- Descriptive function names (`check_b1`, not `checkB1`)
- Clear docstrings explaining conditions
- Type hints for all parameters

### Queue Workflow & Chaining

**Multi-stage processing through RQ queues:**

```
1. API Request
   ↓
2. QueueService.add_to_algorithm_queue(stock_code)
   ↓
3. algorithm_calculation_queue → algorithm_worker.py
   ├─ Fetch stock data
   ├─ Generate signals
   └─ QueueService.add_to_result_processing_queue(stock_code)
   ↓
4. result_processing_queue → result_worker.py
   ├─ Validate signals
   ├─ Calculate profit metrics
   └─ QueueService.add_to_file_write_queue(data)
   ↓
5. file_write_queue → file_write_worker.py
   └─ Write aggregated results to CSV
```

**Implementation Example:**

```python
# Step 1: Controller enqueues task
@algorithm_router.get("/hkex")
async def init_algo_testing():
    task_id = QueueService.add_to_algorithm_queue(stock_code)
    return {"task_id": task_id, "status": "queued"}

# Step 2: Worker 1 processes and chains
async def process_algorithm_task(task_data):
    # ... processing logic ...
    next_task_id = QueueService.add_to_result_processing_queue(stock_code)
    logger.info(f"Chained to result queue: {next_task_id}")
    return task_data

# Step 3: Worker 2 processes and chains
async def process_result_task(task_data):
    # ... validation logic ...
    file_task_id = QueueService.add_to_file_write_queue(result_data)
    return task_data

# Step 4: Worker 3 finalizes
async def write_file_task(task_data):
    # ... write to CSV ...
    return task_data
```

**Queue Configuration:**

```python
# app/config/queue_config.py
from redis import Redis
from rq import Queue

REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
REDIS_PASSWORD = os.getenv('REDIS_PASSWORD', None)

redis_conn = Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=0,
    password=REDIS_PASSWORD,
    decode_responses=False
)

# Define queues with timeouts
us_king_calculation_queue = Queue('us_king_calculation', connection=redis_conn, default_timeout=1000)
algorithm_calculation_queue = Queue('algorithm_calculation', connection=redis_conn, default_timeout=1000)
result_processing_queue = Queue('result_processing', connection=redis_conn)
file_write_queue = Queue('file_write', connection=redis_conn)
```

**Key Points:**

- Each queue has dedicated worker process
- String-based function references for RQ (e.g., `'app.workers.algorithm_worker.process_algorithm_task'`)
- UUID-based task IDs for tracking
- Explicit queue chaining with logging
- Configurable timeouts per queue

---

## 5. Project Structure

```
algorithm-testing-service/
├── app/                           # Main application package
│   ├── __init__.py
│   ├── main.py                    # FastAPI app, lifespan management, health endpoint
│   │
│   ├── controllers/               # API route handlers (FastAPI routers)
│   │   ├── __init__.py
│   │   ├── algorithm_controller.py   # /api/v1/start-testing/hkex, /us-king
│   │   ├── summary_controller.py     # /api/v1/summary (aggregated results)
│   │   ├── monitoring_controller.py  # /api/v1/queue-status
│   │   └── data_test_controller.py   # /api/v1/data-test (debugging)
│   │
│   ├── models/                    # Pydantic data models
│   │   ├── __init__.py
│   │   └── algorithm_models.py    # AlgorithmRequest, TaskResponse
│   │
│   ├── services/                  # Business logic layer
│   │   ├── __init__.py
│   │   ├── file_service.py        # CSV read/write operations
│   │   ├── queue_service.py       # Task enqueueing to RQ
│   │   └── get_all_stocks.py      # External API stock data fetching
│   │
│   ├── workers/                   # Background task processors
│   │   ├── __init__.py
│   │   ├── algorithm_worker.py    # HK algorithm processing
│   │   ├── us_king_worker.py      # US King algorithm processing
│   │   ├── result_worker.py       # Result validation & aggregation
│   │   ├── file_write_worker.py   # CSV write finalization
│   │   │
│   │   └── algo_func/            # Algorithm implementation (pure functions)
│   │       ├── __init__.py
│   │       ├── buy_signals.py     # B1-B18 buy signal detection
│   │       ├── sell_signals.py    # S1-S18 sell signal detection
│   │       ├── buy_king.py        # US King buy logic
│   │       ├── sell_king.py       # US King sell logic
│   │       ├── get_code_energy.py # E1-E5 energy indicators
│   │       ├── get_db_data.py     # External API data fetching
│   │       ├── helpers.py         # Technical indicators (RSI, BB, ATR)
│   │       └── types.py           # Data types (OHLCV, ProfitRecord, etc.)
│   │
│   └── config/                    # Configuration modules
│       ├── __init__.py
│       ├── config.py              # Algorithm parameters, constants
│       ├── logging_config.py      # Logging setup (rotating file handlers)
│       └── queue_config.py        # Redis connection, queue definitions
│
├── workers/                       # Worker entry point scripts
│   ├── start_algorithm_worker.py  # Start HK algorithm worker
│   ├── start_king_worker.py       # Start US King worker
│   ├── start_result_worker.py     # Start result processing worker
│   └── start_file_write_worker.py # Start file write worker
│
├── dashboard/                     # RQ dashboard (optional monitoring)
│   └── start_dashboard.py         # Launch RQ Dashboard UI
│
├── data/                          # CSV data storage
│   ├── screener.csv               # Input: HK stocks to test
│   ├── us_king_screener.csv       # Input: US stocks to test
│   ├── results.csv                # Output: HK algorithm signals
│   ├── us_king_results.csv        # Output: US King signals
│   ├── general_results.csv        # Output: Aggregated HK results
│   ├── summary.csv                # Output: HK profit summary
│   ├── summary_us.csv             # Output: US King summary
│   ├── us_king_profit_records.csv # Output: US King trade records
│   └── lewis_results/             # Detailed signal breakdowns
│       ├── hk_signal_dtl.csv
│       └── us_king_dtl.csv
│
├── logs/                          # Application logs (daily rotation, 7-day retention)
│   ├── algorithm-worker.log
│   ├── us-king-worker.log
│   ├── result-worker.log
│   ├── file-write-worker.log
│   └── api.log
│
├── docs/                          # Documentation
│   ├── README.md                  # Documentation overview
│   ├── HK_Algo/                   # HK algorithm documentation
│   │   ├── hk_algo_terms.md       # Signal definitions (B1-B18, S1-S18)
│   │   └── mc_hk.txt              # Algorithm context
│   └── US_King/                   # US King algorithm documentation
│       ├── README.md
│       ├── energy_signals.md      # Energy indicator definitions (E1-E5)
│       ├── implementation_guide.md
│       ├── us_king_terms.md       # Signal definitions
│       └── mc_us_king.els
│
├── .github/                       # GitHub configuration
│   ├── copilot-instructions.md    # Instructions for GitHub Copilot
│   └── instructions/
│       ├── style.instructions.md  # Code style guidelines
│       ├── backend.instructions.md
│       └── frontend.instructions.md
│
├── docker-compose.yml             # Multi-service Docker orchestration
├── Dockerfile                     # Container definition
├── requirements.txt               # Python dependencies
├── README.md                      # Project overview
├── AGENTS.md                      # This file (technical documentation for AI)
└── EXAMPLE AGENTS.md              # Template for AGENTS.md
```

### Key Directories

| Directory                | Purpose                  | Critical Files                                      |
| ------------------------ | ------------------------ | --------------------------------------------------- |
| `app/controllers/`       | API endpoints            | `algorithm_controller.py` (main entry points)       |
| `app/services/`          | Business logic           | `file_service.py`, `queue_service.py`               |
| `app/workers/`           | Background processing    | `algorithm_worker.py`, `result_worker.py`           |
| `app/workers/algo_func/` | Algorithm implementation | `buy_signals.py`, `sell_signals.py`, `helpers.py`   |
| `app/config/`            | Configuration            | `config.py`, `logging_config.py`, `queue_config.py` |
| `workers/`               | Worker launchers         | `start_algorithm_worker.py`, etc.                   |
| `data/`                  | CSV I/O                  | Input screeners, output results                     |
| `logs/`                  | Application logs         | Rotated daily, 7-day retention                      |

---

## 6. Configuration Management

### Required Environment Variables

Create a `.env` file in project root (DO NOT commit to git):

```bash
# External API Configuration
API_KEY=<your-stockfisher-api-key>
US_KING_API_KEY=<your-us-king-api-key>
STOCKFISHER_URL=https://api.stockfisher.example.com

# Redis Configuration
REDIS_HOST=localhost          # Use 'redis' in Docker
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=               # Optional: leave empty for no auth

# Logging Configuration
LOG_LEVEL=INFO                # DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_DIR=logs                  # Directory for log files

# Application Configuration
PYTHONPATH=/app               # Set automatically in Docker
DATA_DIR=data                 # Directory for CSV files
```

**⚠️ Security:**

- Never commit `.env` to version control
- Add `.env` to `.gitignore`
- Use different credentials for development/production
- Rotate API keys periodically

### Algorithm Configuration

Edit `app/config/config.py` for algorithm parameters:

```python
# --- HK Algorithm Configuration ---
HT_START_DAY = "2019-01-01"         # Historical data start date
HT_END_DAY = "2026-01-01"           # Historical data end date
HK_STOCKS_FILE = "screener"         # Input screener file name (without .csv)
HK_RESULTS_FILE = "results"         # Output results file name
FIXED_DEPOSIT_AMOUNT = 10000.0      # Initial capital per stock (HKD)

# --- US King Configuration ---
US_KING_START_DATE = "2019-01-01"   # Historical data start date
US_KING_END_DATE = "2026-01-01"     # Historical data end date
US_KING_SCREENER_FILE = "us_king_screener"
US_KING_RESULTS_FILE = "us_king_results"
US_KING_INITIAL_CAPITAL = 10000.0   # Initial capital per stock (USD)

# --- Technical Indicator Parameters ---
RSI_PERIOD = 14                     # RSI calculation period
BB_PERIOD = 20                      # Bollinger Bands period
BB_STD_DEV = 2.0                    # Bollinger Bands standard deviation
ATR_PERIOD = 14                     # Average True Range period

# --- Trading Parameters ---
STOP_LOSS_PERCENT = 0.08            # 8% stop loss
TAKE_PROFIT_PERCENT = 0.20          # 20% take profit
MAX_HOLDING_DAYS = 90               # Maximum holding period
```

### Queue Configuration

Redis and RQ queue settings in `app/config/queue_config.py`:

```python
import os
from redis import Redis
from rq import Queue

# Redis connection from environment
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
REDIS_DB = int(os.getenv('REDIS_DB', 0))
REDIS_PASSWORD = os.getenv('REDIS_PASSWORD', None)

redis_conn = Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=REDIS_DB,
    password=REDIS_PASSWORD,
    decode_responses=False
)

# Queue definitions with timeouts (seconds)
us_king_calculation_queue = Queue('us_king_calculation', connection=redis_conn, default_timeout=1000)
algorithm_calculation_queue = Queue('algorithm_calculation', connection=redis_conn, default_timeout=1000)
result_processing_queue = Queue('result_processing', connection=redis_conn, default_timeout=600)
file_write_queue = Queue('file_write', connection=redis_conn, default_timeout=300)
```

### Logging Configuration

Centralized logging setup in `app/config/logging_config.py`:

```python
def setup_logging() -> None:
    """Configure application-wide logging with rotating file handlers."""
    log_dir = os.getenv('LOG_DIR', 'logs')
    os.makedirs(log_dir, exist_ok=True)

    log_level = os.getenv('LOG_LEVEL', 'INFO').upper()

    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S"
            }
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "default",
                "level": log_level
            },
            "algo_file": {
                "class": "logging.handlers.TimedRotatingFileHandler",
                "filename": os.path.join(log_dir, "algorithm-worker.log"),
                "when": "midnight",
                "backupCount": 7,
                "formatter": "default",
                "level": log_level
            },
            # ... other handlers for each component
        },
        "loggers": {
            "app.workers.algorithm_worker": {
                "handlers": ["algo_file", "console"],
                "level": log_level,
                "propagate": False
            },
            # ... other loggers
        },
        "root": {
            "handlers": ["console"],
            "level": log_level
        }
    }

    dictConfig(config)
```

### Docker Environment

Configure `docker-compose.yml` environment variables:

```yaml
services:
    api:
        environment:
            - PYTHONPATH=/app
            - REDIS_HOST=redis
            - REDIS_PORT=6379
            - LOG_LEVEL=${LOG_LEVEL:-INFO}
            - LOG_DIR=/app/logs
            - API_KEY=${API_KEY}
            - US_KING_API_KEY=${US_KING_API_KEY}
            - STOCKFISHER_URL=${STOCKFISHER_URL}
```

**Load from .env file:**

```bash
# docker-compose automatically loads .env file from project root
docker-compose up --build
```

---

## 7. Known Issues & Technical Debt

### Critical Issues (Fix Before Next Refactor)

#### 1. Function Naming Inconsistency

**Problem:** Algorithm functions use camelCase instead of snake_case.

**Files affected:**

- `app/workers/algo_func/buy_signals.py`: `checkB1`, `checkB3`, `checkB5`, etc.
- `app/workers/algo_func/sell_signals.py`: Mixed naming (`s4`, `s5` vs `exit_by_stop_loss`)

**Fix required:**

```python
# Current (WRONG):
def checkB1(ohlcv: List[OHLCV], targetDate) -> bool:
    pass

# Required (CORRECT):
def check_b1(ohlcv: list[OHLCV], target_date: str) -> bool:
    pass
```

**Impact:** All imports and calls to these functions must be updated.

#### 2. OHLCV Class Duplication

**Problem:** `OHLCV` dataclass defined in two files.

**Files affected:**

- `app/workers/algo_func/types.py` (line 5-12) - Primary definition
- `app/workers/algo_func/sell_signals.py` (line 14-21) - Duplicate

**Fix required:**

```python
# In sell_signals.py: Remove duplicate definition
# Add import instead:
from app.workers.algo_func.types import OHLCV
```

#### 3. Print Statements in Production Code

**Problem:** Debug `print()` statements instead of proper logging.

**Files affected:**

- `app/workers/algorithm_worker.py`: `print("start")`
- Various algo_func files: Ukrainian debug messages

**Fix required:**

```python
# Replace:
print(f"Немає сигналу для коду {code}")

# With:
logger.debug(f"No signal found for code {code}")
```

#### 4. Missing Dependencies

**Problem:** Imported libraries not listed in requirements.txt.

**Missing from requirements.txt:**

- `numpy` (imported in multiple files)
- `python-dateutil` (imported in helpers.py)

**Fix required:** Add to requirements.txt:

```
numpy>=1.24.0
python-dateutil>=2.8.2
```

#### 5. Async Anti-pattern (Blocking I/O)

**Problem:** Async functions use blocking file I/O and HTTP requests.

**Files affected:**

- `app/services/file_service.py`: Uses synchronous `open()`
- `app/workers/algo_func/get_db_data.py`: Uses `requests.get()` (blocking)

**Current (blocks event loop):**

```python
async def add_data_to_csv(self, file_name: str, data: list[dict], fieldnames: list[str]):
    with open(file_path, mode, newline='', encoding='utf-8') as csvfile:  # Blocking!
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
```

**Future fix (non-blocking):**

```python
import aiofiles

async def add_data_to_csv(self, file_name: str, data: list[dict], fieldnames: list[str]):
    async with aiofiles.open(file_path, mode='w', encoding='utf-8') as csvfile:
        # Use async CSV writer or asyncio.to_thread()
```

**Note:** This is documented as technical debt. New code should use `aiofiles` and `aiohttp`.

### Non-Critical Improvements

#### 6. Incomplete Type Hints

**Problem:** Some function parameters lack type annotations.

**Example:**

```python
# Current:
async def process_algorithm_task(task_data):  # No types
    pass

# Should be:
async def process_algorithm_task(task_data: dict[str, Any]) -> dict[str, str]:
    pass
```

**Action:** Add type hints when modifying these functions.

#### 7. Inconsistent Type Hint Syntax

**Problem:** Mix of modern (`list[str]`) and legacy (`List[str]`) syntax.

**Action:** Standardize to modern Python 3.10+ syntax (see Development Rules).

#### 8. Missing Docstrings

**Problem:** Many algorithm functions lack docstrings.

**Example:** Functions in `buy_signals.py`, `sell_signals.py` have minimal docs.

**Action:** Add comprehensive docstrings when modifying these functions.

#### 9. Ukrainian/English Language Mix

**Problem:** Comments and strings mix Ukrainian and English.

**Files affected:** Various worker and algo_func files

**Action:** Translate all Ukrainian text to English for international collaboration.

#### 10. QueueService Design Inconsistency

**Problem:** QueueService uses static methods, while FileService uses instance methods.

**Current:**

```python
class QueueService:
    @staticmethod
    def add_to_algorithm_queue(stock_code: str) -> str:
        pass
```

**Preferred (for consistency):**

```python
class QueueService:
    def __init__(self, redis_conn: Redis):
        self.redis_conn = redis_conn

    def add_to_algorithm_queue(self, stock_code: str) -> str:
        pass
```

**Action:** Refactor QueueService to instance-based (low priority).

### Testing Gaps

#### 11. No Automated Tests

**Problem:** Project lacks unit and integration tests.

**Missing:**

- No `/tests` directory with actual test files
- No pytest/unittest configuration
- No test coverage reporting

**Future improvements:**

- Add pytest framework
- Create unit tests for algorithm functions (buy_signals, sell_signals)
- Create integration tests for workers
- Mock external API calls in tests

**Example test structure:**

```
tests/
├── __init__.py
├── conftest.py                    # Pytest fixtures
├── unit/
│   ├── test_buy_signals.py       # Test B1-B18 signals
│   ├── test_sell_signals.py      # Test S1-S18 signals
│   └── test_helpers.py           # Test technical indicators
├── integration/
│   ├── test_algorithm_worker.py  # Test worker flow
│   └── test_file_service.py      # Test CSV operations
└── fixtures/
    └── sample_ohlcv_data.json    # Test data
```

### Documentation Improvements

#### 12. Missing .env.example

**Problem:** Required environment variables not documented in repository.

**Action:** Create `.env.example` with placeholder values:

```bash
API_KEY=your-api-key-here
US_KING_API_KEY=your-second-api-key-here
STOCKFISHER_URL=https://api.example.com
REDIS_HOST=localhost
REDIS_PORT=6379
LOG_LEVEL=INFO
```

#### 13. API Documentation

**Problem:** No comprehensive API documentation beyond basic README.

**Improvements:**

- FastAPI auto-generates OpenAPI docs at `/docs` (Swagger UI)
- Add description to endpoints using docstrings and `description` parameter
- Add request/response examples to Pydantic models

**Action:** Access built-in docs at `http://localhost:8000/docs` after starting API.

---

## 8. Quick Reference

### Key Files by Function

| Function                 | File                                       | Description                              |
| ------------------------ | ------------------------------------------ | ---------------------------------------- |
| **API Entry**            | `app/main.py`                              | FastAPI app initialization, health check |
| **HK Algorithm Start**   | `app/controllers/algorithm_controller.py`  | `/api/v1/start-testing/hkex` endpoint    |
| **US King Start**        | `app/controllers/algorithm_controller.py`  | `/api/v1/start-testing/us-king` endpoint |
| **Results API**          | `app/controllers/summary_controller.py`    | `/api/v1/summary` endpoint               |
| **HK Worker**            | `app/workers/algorithm_worker.py`          | HK algorithm processing                  |
| **US King Worker**       | `app/workers/us_king_worker.py`            | US King processing                       |
| **Buy Signals**          | `app/workers/algo_func/buy_signals.py`     | B1-B18 signal detection                  |
| **Sell Signals**         | `app/workers/algo_func/sell_signals.py`    | S1-S18 signal detection                  |
| **Energy Indicators**    | `app/workers/algo_func/get_code_energy.py` | E1-E5 calculations                       |
| **Technical Indicators** | `app/workers/algo_func/helpers.py`         | RSI, Bollinger Bands, ATR                |
| **External API**         | `app/workers/algo_func/get_db_data.py`     | Stock data fetching                      |
| **File Operations**      | `app/services/file_service.py`             | CSV read/write                           |
| **Queue Operations**     | `app/services/queue_service.py`            | Task enqueueing                          |
| **Config (Algo)**        | `app/config/config.py`                     | Algorithm parameters                     |
| **Config (Queue)**       | `app/config/queue_config.py`               | Redis & queue setup                      |
| **Config (Logging)**     | `app/config/logging_config.py`             | Logging setup                            |

### API Endpoints

| Method | Endpoint                        | Description                             |
| ------ | ------------------------------- | --------------------------------------- |
| `GET`  | `/health`                       | Health check (returns {"status": "ok"}) |
| `GET`  | `/api/v1/start-testing/hkex`    | Start HK algorithm for all stocks       |
| `GET`  | `/api/v1/start-testing/us-king` | Start US King algorithm                 |
| `POST` | `/api/v1/start-testing/hkex`    | Start HK algorithm for specific stock   |
| `GET`  | `/api/v1/summary`               | Get aggregated results summary          |
| `GET`  | `/api/v1/queue-status`          | Get queue lengths and worker status     |

### Common Tasks

#### Add New Buy Signal (e.g., B19)

1. Add function to `app/workers/algo_func/buy_signals.py`:
    ```python
    def check_b19(ohlcv: list[OHLCV], target_date: str) -> bool:
        """Check B19 signal condition."""
        # Implementation
        pass
    ```
2. Update signal checking logic in `algorithm_worker.py`
3. Add tests in `tests/unit/test_buy_signals.py`
4. Document signal in `docs/HK_Algo/hk_algo_terms.md`

#### Add New Technical Indicator

1. Add function to `app/workers/algo_func/helpers.py`:
    ```python
    def calculate_macd(values: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> list[dict[str, float]]:
        """Calculate MACD indicator."""
        # Implementation
        pass
    ```
2. Add type hints and docstring
3. Use in signal functions (buy_signals.py, sell_signals.py)
4. Add unit tests

#### Add New API Endpoint

1. Create/edit controller in `app/controllers/`:
    ```python
    @router.get("/new-endpoint")
    async def new_endpoint():
        """Endpoint description."""
        # Implementation
        pass
    ```
2. Register router in `app/main.py`:
    ```python
    app.include_router(new_controller.router, prefix="/api/v1", tags=["New Feature"])
    ```
3. Test at `http://localhost:8000/docs`

#### Debug Worker Issues

1. Check logs: `tail -f logs/algorithm-worker.log`
2. Check queue length: `redis-cli LLEN rq:queue:algorithm_calculation`
3. Check failed jobs: `redis-cli LLEN rq:queue:failed`
4. Access RQ Dashboard: `rq-dashboard` at `http://localhost:9181`

#### Clear All Queue Data

```bash
# WARNING: This deletes all queued and processed tasks
redis-cli FLUSHDB
```

---

## 9. External Services

### StockFisher API

**Purpose:** Fetch historical stock data for HK and US markets

**Configuration:**

```python
STOCKFISHER_URL = os.getenv('STOCKFISHER_URL')
API_KEY = os.getenv('API_KEY')
```

**Usage:** `app/workers/algo_func/get_db_data.py`

### US King API

**Purpose:** Secondary data source for US market stocks

**Configuration:**

```python
US_KING_API_KEY = os.getenv('US_KING_API_KEY')
```

### Redis

**Purpose:** Task queue and job management

**Default:** `localhost:6379` (local), `redis:6379` (Docker)

**Monitoring:** RQ Dashboard at `http://localhost:9181`

---

**Last Updated:** February 26, 2026  
**Maintained By:** Algorithm Testing Team  
**Python Version:** 3.11+  
**Framework:** FastAPI 0.104.1  
**Questions?** Refer to project documentation in `docs/` or open an issue.
