# Algorithm Testing Service

A comprehensive Python-based trading algorithm testing and execution service with support for multiple trading signals, backtesting capabilities, and real-time monitoring.

## Table of Contents

-   [Overview](#overview)
-   [Features](#features)
-   [Project Structure](#project-structure)
-   [Prerequisites](#prerequisites)
-   [Installation](#installation)
-   [Configuration](#configuration)
-   [Usage](#usage)
-   [API Endpoints](#api-endpoints)
-   [Workers](#workers)
-   [Testing](#testing)
-   [Docker Deployment](#docker-deployment)
-   [Contributing](#contributing)

## Overview

The Algorithm Testing Service is designed to test, validate, and execute trading algorithms in a distributed environment. It supports multiple buy/sell signals, risk management rules, and provides comprehensive logging and monitoring capabilities.

## Features

-   **Multi-Signal Trading System**: Support for 18+ buy signals (B1-B18) and multiple exit strategies (S1-S18)
-   **Queue-Based Processing**: Asynchronous task processing using a queue system
-   **Real-Time Monitoring**: Dashboard and monitoring endpoints for trade tracking
-   **Backtesting Framework**: Historical data testing capabilities
-   **Data Management**: CSV-based data input/output with signal logging
-   **Worker Architecture**: Distributed worker processes for algorithm execution and file processing
-   **Docker Support**: Containerized deployment with docker-compose
-   **Comprehensive Logging**: Signal logs, cash flow logs, and detailed trade records

## Project Structure

```
algorithm-testing-service/
├── app/                          # Main application package
│   ├── controllers/             # API route handlers
│   │   ├── algorithm_controller.py
│   │   ├── data_test_controller.py
│   │   └── monitoring_controller.py
│   ├── models/                  # Data models
│   │   └── algorithm_models.py
│   ├── services/                # Business logic
│   │   ├── file_service.py
│   │   ├── get_all_stoccks.py
│   │   └── queue_service.py
│   ├── workers/                 # Background workers
│   │   ├── algorithm_worker.py
│   │   ├── file_write_worker.py
│   │   ├── result_worker.py
│   │   └── algo_func/           # Algorithm functions
│   │       ├── buy_signals.py
│   │       ├── sell_signals.py
│   │       ├── get_code_energy.py
│   │       └── get_db_data.py
│   ├── config/                  # Configuration files
│   │   ├── logging_config.py
│   │   └── queue_config.py
│   └── main.py                  # Application entry point
├── workers/                      # Worker entry points
│   ├── start_algorithm_worker.py
│   ├── start_file_write_worker.py
│   └── start_result_worker.py
├── dashboard/                    # Dashboard application
│   └── start_dashboard.py
├── tests/                        # Test suite
│   └── algo_func/               # Algorithm function tests
├── data/                         # Data files (CSV)
├── docs/                         # Documentation
├── Dockerfile                    # Docker image configuration
├── docker-compose.yml           # Docker compose orchestration
└── requirements.txt             # Python dependencies
```

## Prerequisites

-   Python 3.8 or higher
-   Docker and Docker Compose (optional, for containerized deployment)
-   Redis (for queue processing)
-   pandas, numpy (for data processing)

## Installation

### Local Installation

1. **Clone the repository**

    ```bash
    git clone <repository-url>
    cd algorithm-testing-service
    ```

2. **Create a virtual environment**

    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```

3. **Install dependencies**

    ```bash
    pip install -r requirements.txt
    ```

4. **Configure the application**
    - Update `app/config/logging_config.py` for logging settings
    - Update `app/config/queue_config.py` for queue settings

### Docker Installation

```bash
docker-compose build
docker-compose up
```

## Configuration

### Logging Configuration

Edit `app/config/logging_config.py` to configure:

-   Log level
-   Log file paths
-   Log format

### Queue Configuration

Edit `app/config/queue_config.py` to configure:

-   Queue backend (Redis)
-   Queue name and settings
-   Worker concurrency

### Algorithm Parameters

Algorithm parameters are defined in the individual signal functions:

-   **Buy Signals** (B1-B18): In `app/workers/algo_func/buy_signals.py`
-   **Sell Signals** (S1-S18): In `app/workers/algo_func/sell_signals.py`

Key parameters include:

-   ATR periods and factors
-   Moving average lengths
-   Bollinger Band settings
-   Entry and exit thresholds

## Usage

### Starting the Application

```bash
python app/main.py
```

### Starting Workers

In separate terminals:

```bash
# Start algorithm worker
python workers/start_algorithm_worker.py

# Start file write worker
python workers/start_file_write_worker.py

# Start result worker
python workers/start_result_worker.py
```

### Starting the Dashboard

```bash
python dashboard/start_dashboard.py
```

## API Endpoints

### Algorithm Controller

-   `POST /api/algorithm/run` - Run algorithm on specified data
-   `GET /api/algorithm/status` - Get algorithm status
-   `POST /api/algorithm/stop` - Stop running algorithm

### Data Test Controller

-   `POST /api/test/data` - Test data validation
-   `GET /api/test/results` - Get test results
-   `POST /api/test/backtest` - Run backtest on historical data

### Monitoring Controller

-   `GET /api/monitor/trades` - Get active trades
-   `GET /api/monitor/performance` - Get performance metrics
-   `GET /api/monitor/signals` - Get signal log
-   `GET /api/monitor/health` - Service health status

## Workers

### Algorithm Worker

Processes algorithm execution tasks from the queue:

-   Evaluates buy/sell signals
-   Manages trade entries and exits
-   Calculates energy levels and indicators
-   Logs signal activity

### File Write Worker

Handles file operations:

-   Writing signal logs to CSV
-   Writing cash flow records
-   Managing data output files

### Result Worker

Processes and aggregates results:

-   Compiles trade results
-   Calculates performance metrics
-   Generates reports

## Testing

Run the test suite:

```bash
# Run all tests
python -m pytest tests/

# Run specific test file
python -m pytest tests/algo_func/test_buy_signals.py

# Run with coverage
python -m pytest --cov=app tests/
```

### Key Test Files

-   `test_b1.py` - Buy signal B1 tests
-   `test_b3.py` - Buy signal B3 tests
-   `test_b8.py` - Buy signal B8 tests
-   `test_sell_signals.py` - Exit signal tests
-   `test_indicators.py` - Technical indicator tests
-   `test_bb_and_bbw.py` - Bollinger Band tests

## Docker Deployment

### Build and Run

```bash
# Build images
docker-compose build

# Start services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

### Environment Variables

Configure in `.env` file or in `docker-compose.yml`:

-   `LOG_LEVEL` - Logging level (DEBUG, INFO, WARNING, ERROR)
-   `QUEUE_HOST` - Redis host
-   `QUEUE_PORT` - Redis port
-   `WORKER_CONCURRENCY` - Number of worker processes

## Signal System

### Buy Signals (B1-B18)

| Signal | Description                           |
| ------ | ------------------------------------- |
| B1     | New high with closing price condition |
| B3     | Bollinger Band width slope            |
| B8     | Higher lows pattern                   |
| B9     | Price above mid-range condition       |
| B10    | Recent 250-day low check              |
| B11    | ATR not at highest level              |
| B12    | 150-day moving average growth         |
| B13    | Comparative price performance         |
| B18    | Market Trend Template (MMT)           |

### Exit/Stop Signals (S1-S18)

| Signal | Description                    |
| ------ | ------------------------------ |
| S1     | ATR-based stop loss            |
| S4     | Profitable days ratio          |
| S5     | Moving stop                    |
| S6     | No new high in XX days         |
| S7     | Dark candle pattern            |
| S8     | ATR volatility expansion       |
| S10    | ATR ratio and high retracement |
| S11    | Fibonacci 0.382 level          |
| S12    | Fibonacci 0.236 level          |
| S13    | Lowest low condition           |
| S14    | Comparative price decline      |
| S15    | Price pullback percentage      |
| S16    | ATR increase with pullback     |
| S17    | Range ratio                    |
| S18    | RSI and lowest low condition   |

## Data Files

The `data/` directory contains CSV files with:

-   OHLC data (Open, High, Low, Close)
-   Stock codes (Hong Kong stocks)
-   Trading dates
-   Test data for backtesting

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit changes (`git commit -m 'Add AmazingFeature'`)
4. Push to branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## License

[Specify your license here]

## Support

For issues, questions, or contributions, please contact the development team or create an issue in the repository.

---

**Last Updated**: January 2026
