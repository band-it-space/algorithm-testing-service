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

---

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

# 2. Third-party imports
import pandas as pd

# 3. Local application imports
from app.services.queue_service import QueueService
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

### Error Handling by Layer

| Layer                   | Pattern                            | Example                                                    |
| ----------------------- | ---------------------------------- | ---------------------------------------------------------- |
| **Controllers**         | Raise `HTTPException`              | `raise HTTPException(status_code=404, detail="Not found")` |
| **Workers**             | Log + re-raise for RQ              | `logger.error(...); raise e`                               |
| **Services**            | Return `False`/`None`, log warning | `return False`                                             |
| **Algorithm Functions** | Raise `ValueError` or return early | `return False` if insufficient data                        |

### Logging Standard

**Pattern:** Use Python's standard logging module, never `print()`.

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
```

**Log Levels:**

- `logger.debug()` - Verbose diagnostic information
- `logger.info()` - General informational messages
- `logger.warning()` - Recoverable issues
- `logger.error()` - Errors that prevent task completion

---

## 4. Architecture Patterns

### Layer Responsibilities

| Layer                   | Location                 | Responsibility                                             |
| ----------------------- | ------------------------ | ---------------------------------------------------------- |
| **Controllers**         | `app/controllers/`       | API endpoints, validation, enqueue tasks, HTTPException    |
| **Services**            | `app/services/`          | Business logic, data access, return False/None on errors   |
| **Workers**             | `app/workers/`           | Background processing, queue chaining, re-raise exceptions |
| **Models**              | `app/models/`            | Pydantic request/response schemas                          |
| **Algorithm Functions** | `app/workers/algo_func/` | Pure functions, signal detection, technical indicators     |
| **Config**              | `app/config/`            | Constants, logging, queue definitions                      |

### Queue Workflow & Chaining

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

---

## 5. Project Structure

```
algorithm-testing-service/
├── app/
│   ├── main.py                    # FastAPI app, health endpoint
│   ├── controllers/               # API route handlers
│   │   ├── algorithm_controller.py
│   │   ├── summary_controller.py
│   │   └── monitoring_controller.py
│   ├── models/                    # Pydantic models
│   │   └── algorithm_models.py
│   ├── services/                  # Business logic
│   │   ├── file_service.py
│   │   └── queue_service.py
│   ├── workers/                   # Background processors
│   │   ├── algorithm_worker.py
│   │   ├── us_king_worker.py
│   │   ├── result_worker.py
│   │   ├── file_write_worker.py
│   │   └── algo_func/            # Algorithm implementation
│   │       ├── buy_signals.py
│   │       ├── sell_signals.py
│   │       ├── helpers.py
│   │       └── types.py
│   └── config/
│       ├── config.py
│       ├── logging_config.py
│       └── queue_config.py
├── workers/                       # Worker entry scripts
├── data/                          # CSV input/output
├── logs/                          # Application logs
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

---

## 6. Configuration Management

### Required Environment Variables

Create a `.env` file in project root (DO NOT commit to git):

```bash
# External API Configuration
API_KEY=your-stockfisher-api-key-here
US_KING_API_KEY=your-us-king-api-key-here
STOCKFISHER_URL=http://ete.stockfisher.com.hk/

# Redis Configuration
REDIS_HOST=localhost          # Use 'redis' in Docker
REDIS_PORT=6379
REDIS_DB=0

# Application Configuration
API_PORT=8000
DASHBOARD_PORT=9181
ENVIRONMENT=development       # development, production
DEBUG=true
AUTO_RELOAD=true

# Logging Configuration
LOG_LEVEL=INFO                # DEBUG, INFO, WARNING, ERROR, CRITICAL
```

**⚠️ Security:**

- Never commit `.env` to version control
- Add `.env` to `.gitignore`
- Use different credentials for development/production
- Rotate API keys periodically

---

## 7. Known Issues & Technical Debt

### Critical Issues

| Issue                     | Files                                  | Fix                                        |
| ------------------------- | -------------------------------------- | ------------------------------------------ |
| **Function Naming**       | `buy_signals.py`, `sell_signals.py`    | Rename `checkB1` → `check_b1` (snake_case) |
| **OHLCV Duplication**     | `types.py`, `sell_signals.py`          | Remove duplicate, import from `types.py`   |
| **Print Statements**      | `algorithm_worker.py`, algo_func files | Replace `print()` with `logger.debug()`    |
| **Blocking I/O in Async** | `file_service.py`, `get_db_data.py`    | Use `aiofiles` and `aiohttp` for new code  |

### Non-Critical Improvements

| Issue                            | Action                     |
| -------------------------------- | -------------------------- |
| Incomplete Type Hints            | Add when modifying         |
| Legacy Type Syntax (`List[str]`) | Standardize to `list[str]` |
| Missing Docstrings               | Add when modifying         |
| Ukrainian/English Mix            | Translate to English       |
| No Automated Tests               | Add pytest framework       |

---

## 8. Quick Reference

### Key Files by Function

| Function                 | File                                      |
| ------------------------ | ----------------------------------------- |
| **API Entry**            | `app/main.py`                             |
| **HK Algorithm Start**   | `app/controllers/algorithm_controller.py` |
| **Buy Signals**          | `app/workers/algo_func/buy_signals.py`    |
| **Sell Signals**         | `app/workers/algo_func/sell_signals.py`   |
| **Technical Indicators** | `app/workers/algo_func/helpers.py`        |
| **File Operations**      | `app/services/file_service.py`            |
| **Queue Operations**     | `app/services/queue_service.py`           |
| **Config**               | `app/config/config.py`                    |

### API Endpoints

| Method | Endpoint                        | Description             |
| ------ | ------------------------------- | ----------------------- |
| `GET`  | `/health`                       | Health check            |
| `GET`  | `/api/v1/start-testing/hkex`    | Start HK algorithm      |
| `GET`  | `/api/v1/start-testing/us-king` | Start US King algorithm |
| `GET`  | `/api/v1/summary`               | Get results summary     |
| `GET`  | `/api/v1/queue-status`          | Get queue status        |

---

**Last Updated:** February 26, 2026  
**Maintained By:** Algorithm Testing Team  
**Python Version:** 3.11+  
**Framework:** FastAPI 0.104.1  
**Questions?** Refer to project documentation in `docs/` or open an issue.
