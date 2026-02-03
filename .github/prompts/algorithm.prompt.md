---
agent: agent
description: This is a trading algorithm testing service built with FastAPI, Redis queue system, and distributed workers for backtesting and executing trading signals on Hong Kong stock market data.
model: GPT-4.1
tools:
    [
        "vscode",
        "execute",
        "read",
        "edit",
        "search",
        "web",
        "github/*",
        "agent",
        "todo",
    ]
---

## Architecture Patterns

### Queue-Based Processing Flow

-   **Entry Point**: [`app/controllers/algorithm_controller.py`](app/controllers/algorithm_controller.py) → [`app/services/queue_service.py`](app/services/queue_service.py)
-   **Three-Queue System**: algorithm_calculation → result_processing → file_write
-   **Worker Pattern**: Each queue has dedicated worker processes in [`workers/`](workers/) directory
-   **Data Flow**: Stock code → Algorithm calculation → Results processing → CSV file output

### Signal-Based Trading Logic

-   **Buy Signals**: 18 signals (B1-B18) in [`app/workers/algo_func/buy_signals.py`](app/workers/algo_func/buy_signals.py)
-   **Sell Signals**: Multiple exit strategies in [`app/workers/algo_func/sell_signals.py`](app/workers/algo_func/sell_signals.py)
-   **OHLCV Pattern**: All functions expect `OHLCV` dataclass with date, open, high, low, close, volume
-   **Indicator Functions**: Technical indicators follow naming pattern `sma()`, `bollinger_bands()`, `calculate_energy_indicators_*()`

### Data Handling Conventions

-   **CSV Format**: All market data in `data/` directory uses OHLCV format
-   **Stock Codes**: Hong Kong exchange codes (e.g., "2800", "838") as strings
-   **Date Format**: ISO format strings "YYYY-MM-DD" throughout codebase
-   **File Naming**: Results files follow pattern `results_{stock_code}_{timestamp}.csv`

## Development Workflows

### Running the Service

```bash
# Development
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Docker environment
docker compose up -d
docker compose logs -f algorithm-service
```

### Worker Management

```bash
# Start individual workers
python workers/start_algorithm_worker.py
python workers/start_result_worker.py
python workers/start_file_write_worker.py

# Monitor queue status via RQ Dashboard at http://localhost:9181
```

### Testing Trading Signals

-   **Unit Tests**: [`tests/algo_func/`](tests/algo_func/) contains comprehensive signal tests
-   **Test Pattern**: Use `_mk(day, o, h, l, c, v)` helper to create OHLCV test data
-   **Signal Testing**: Each buy/sell signal has dedicated test file (`test_b1.py`, `test_sell_signals.py`)
-   **Indicator Testing**: [`tests/algo_func/test_indicators.py`](tests/algo_func/test_indicators.py) for technical indicators

## Integration Points

### Database Connection

-   **MySQL Pool**: Initialized via `init_db_pool()` in [`app/workers/algo_func/get_db_data.py`](app/workers/algo_func/get_db_data.py)
-   **Stock Data**: `get_stock_data_from_db(stock_code, date)` returns historical OHLCV data
-   **Connection Pattern**: Always call `await init_db_pool()` before database operations

### External API Integration

-   **API_KEY**: Environment variable for StockFisher API access
-   **Data Verification**: Endpoints in `http://ete.stockfisher.com.hk/v1.1/debugHKEX/`
-   **Rate Limiting**: Handle API limits in worker functions

### File Processing

-   **Service Pattern**: [`app/services/file_service.py`](app/services/file_service.py) handles all CSV operations
-   **Output Location**: Results written to `data/` directory
-   **Async I/O**: File operations are async-aware for worker compatibility

## Configuration Management

-   **Environment**: Use `.env` file for local development
-   **Redis**: Configuration in [`app/config/queue_config.py`](app/config/queue_config.py)
-   **Logging**: Structured logging setup in [`app/config/logging_config.py`](app/config/logging_config.py)
-   **Docker**: Environment variables injected via [`docker-compose.yml`](docker-compose.yml)

## Code Conventions

### Signal Implementation

-   **Function Signature**: `def checkB1(data: List[OHLCV]) -> bool:`
-   **Return Pattern**: Boolean for buy/sell decisions, dict for complex results
-   **Error Handling**: Log warnings for insufficient data, return False for edge cases
-   **Numpy Usage**: Prefer numpy arrays for mathematical calculations over pure Python lists

### Worker Functions

-   **Async Pattern**: All worker functions are `async def process_*_task(task_data)`
-   **Logging**: Use `logger = logging.getLogger(__name__)` pattern
-   **Error Recovery**: Catch exceptions and log, don't let worker crash
-   **Task Data**: Access via `task_data['stock']`, `task_data['task_id']`

### API Endpoints

-   **Router Pattern**: Group related endpoints in controller files with FastAPI router
-   **Versioning**: All endpoints under `/api/v1/` prefix
-   **Response Models**: Use Pydantic models from [`app/models/algorithm_models.py`](app/models/algorithm_models.py)
