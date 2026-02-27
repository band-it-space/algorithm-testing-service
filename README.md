# Algorithm Testing Service

A Python-based FastAPI microservice for backtesting trading algorithms using a Redis queue-based worker architecture. Processes stock market data, generates buy/sell signals via technical indicators, and produces detailed trading performance reports.

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [API Endpoints](#api-endpoints)
- [Workers](#workers)
- [Testing](#testing)
- [Signal System](#signal-system)

## Overview

The service tests, validates, and executes trading algorithms in a distributed environment. It supports multiple buy/sell signals, risk management rules, and provides monitoring and Google Sheets integration for parameter tuning and result output.

## Features

- **Multi-Signal Trading System**: 18 buy signals (B1–B18) and 17 exit strategies (S1–S17)
- **Optimization Engine**: Parameter range optimization with genome-based testing
- **Smart Filtering**: Toxic parameter elimination during optimization runs
- **Queue-Based Processing**: Asynchronous task processing via Redis + RQ
- **Google Sheets Integration**: Read parameter ranges and write results to Sheets
- **Real-Time Monitoring**: Dashboard and API endpoints for queue/worker tracking
- **Docker Deployment**: Fully containerized with docker-compose

## Project Structure

```
algorithm-testing-service/
├── app/
│   ├── main.py                    # FastAPI application entry point
│   ├── controllers/               # API route handlers
│   │   ├── algorithm_controller.py
│   │   ├── optimization_controller.py
│   │   ├── monitoring_controller.py
│   │   ├── summary_controller.py
│   │   ├── sheets_controller.py
│   │   ├── genome_controller.py
│   │   └── dashboard_controller.py
│   ├── models/
│   │   └── algorithm_models.py    # Pydantic models
│   ├── services/
│   │   ├── file_service.py
│   │   ├── queue_service.py
│   │   ├── optimization_service.py
│   │   ├── genome_service.py
│   │   ├── sheets_service.py
│   │   ├── data_cache_service.py
│   │   ├── smart_filtering_service.py
│   │   ├── results_aggregation_service.py
│   │   └── get_all_stocks.py
│   ├── workers/
│   │   ├── algorithm_worker.py
│   │   ├── result_worker.py
│   │   ├── file_write_worker.py
│   │   ├── concurrent_worker.py
│   │   └── algo_func/            # Algorithm implementation
│   │       ├── buy_signals.py
│   │       ├── sell_signals.py
│   │       ├── precomputed_indicators.py
│   │       ├── get_code_energy.py
│   │       ├── get_db_data.py
│   │       ├── helpers.py
│   │       └── types.py
│   ├── config/
│   │   ├── logging_config.py
│   │   ├── queue_config.py
│   │   └── smart_filtering_config.py
│   └── utils/
│       └── performance_profiler.py
├── workers/                       # Worker entry scripts
│   ├── start_algorithm_worker.py
│   ├── start_result_worker.py
│   └── start_file_write_worker.py
├── scripts/                       # Utility scripts (not part of runtime)
├── dashboard/
│   └── start_dashboard.py
├── tests/                         # Test suite
├── data/                          # Runtime data (gitignored)
├── credentials/                   # Google Sheets credentials (gitignored)
├── docs/                          # Documentation
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── .env.example
└── AGENTS.md                      # AI agent coding guidelines
```

## Prerequisites

- Python 3.11+
- Docker and Docker Compose
- Redis 7+

## Quick Start

### 1. Configure environment

```bash
cp .env.example .env
```

Open `.env` and fill in the **required** values:

```env
# --- Minimum required settings ---
API_KEY=your_stockfisher_api_key

# Google Sheets (for parameter input and result output)
INPUT_SHEET_ID=your_google_sheet_id
OUTPUT_SHEET_ID=your_google_sheet_id

# Backtest date range
OPTIMIZATION_START_DATE=2025-01-01
OPTIMIZATION_END_DATE=2026-02-02

# --- Optional tuning ---
ALGORITHM_WORKER_COUNT=1          # Worker processes
WORKER_CONCURRENT_TASKS=1          # Threads per worker
SMART_FILTERING_ENABLED=true       # Eliminate bad parameter combos early
ALGORITHM_DEBUG=false              # Verbose logging
```

See [.env.example](.env.example) for the full list of variables.

### 2. Place Google Sheets credentials

```bash
mkdir -p credentials
# Copy your service account JSON key:
cp ~/path-to-key.json credentials/google_sheets.json
```

Share both input and output Google Sheets with the service account email (found in `client_email` field of the JSON).

### 3. Start with Docker

```bash
docker-compose up -d --build
```

This starts 6 services: **redis**, **algorithm-service** (port 8000), **algorithm-worker**, **result-worker**, **file-write-worker**, and **rq-dashboard** (port 9181).

### 4. Verify

```bash
curl http://localhost:8000/health
# {"status": "healthy"}
```

### 5. Run an optimization

```bash
curl -X POST http://localhost:8000/api/v1/run-optimization \
  -H "Content-Type: application/json" \
  -d '{
    "stock_codes": ["3888"],
    "use_google_sheets": true,
    "sheet_id": "YOUR_SHEET_ID"
  }'
```

Response:
```json
{
  "optimization_id": "opt_abc123def456",
  "total_genomes": 16,
  "total_tasks": 16,
  "stock_codes": ["3888"],
  "status": "pending",
  "message": "Optimization created and 16 tasks queued successfully"
}
```

Check progress:
```bash
curl http://localhost:8000/api/v1/optimization/opt_abc123def456/status
```

Monitor queues:
```bash
curl http://localhost:8000/api/v1/monitoring/queues
```

Or open the dashboard at [http://localhost:9181](http://localhost:9181).

### Local Development (without Docker)

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Start Redis separately, then:
uvicorn app.main:app --reload --port 8000
```

## Configuration

All configuration is managed via environment variables in `.env`. See `.env.example` for the full list.

Key settings:

| Variable | Description | Default |
|----------|-------------|---------|
| `API_KEY` | StockFisher API key | — |
| `REDIS_HOST` | Redis hostname | `localhost` |
| `INPUT_SHEET_ID` | Google Sheet ID for parameter input | — |
| `OUTPUT_SHEET_ID` | Google Sheet ID for result output | — |
| `INPUT_SHEET_NAME` | Worksheet tab for parameter ranges | `Parameter Tuning` |
| `OUTPUT_SHEET_NAME` | Worksheet tab for results | `Automated Results` |
| `OUTPUT_PER_GENOME_SHEET_NAME` | Worksheet tab for per-genome results | `Automated Results Per Genome` |
| `OPTIMIZATION_START_DATE` | Backtest start date | `2025-01-01` |
| `OPTIMIZATION_END_DATE` | Backtest end date | `2026-02-02` |
| `SMART_FILTERING_ENABLED` | Enable toxic parameter filtering | `true` |
| `ALGORITHM_WORKER_COUNT` | Number of algorithm worker processes | `1` |

## API Endpoints

### Core

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/api/v1/run-optimization` | Start optimization run |
| `GET` | `/api/v1/optimization/{id}/status` | Get optimization status |
| `GET` | `/api/v1/optimization/{id}/results` | Get optimization results |
| `POST` | `/api/v1/optimization/{id}/cancel` | Cancel optimization |
| `GET` | `/api/v1/optimizations` | List recent optimizations |
| `POST` | `/api/v1/preview-genomes` | Preview genome count |

### Additional

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/start-testing/` | Start HK algorithm testing |
| `GET` | `/api/v1/summary/` | Generate results summary |
| `GET` | `/api/v1/monitoring/queues` | Queue statistics |
| `GET` | `/api/v1/monitoring/workers` | Worker status |
| `GET` | `/api/v1/monitoring/stats` | Overall system stats |
| `GET` | `/api/v1/sheets/health` | Google Sheets connectivity |
| `GET` | `/api/v1/genome/{genome_id}/parameters` | Genome parameters |
| `GET` | `/dashboard` | Web monitoring dashboard |

## Workers

| Worker | Queue | Purpose |
|--------|-------|---------|
| Algorithm Worker | `algorithm_calculation_queue` | Run buy/sell signal detection |
| Result Worker | `result_processing_queue` | Validate signals, calculate profits |
| File Write Worker | `file_write_queue` | Persist results to CSV |

## Testing

```bash
# Run all tests
python -m pytest tests/

# Run specific test
python -m pytest tests/algo_func/test_b1.py

# Run with coverage
python -m pytest --cov=app tests/
```

## Signal System

### Buy Signals (B1–B18)

| Signal | Description |
|--------|-------------|
| B1 | New high with closing price condition |
| B3 | Bollinger Band width slope |
| B8 | Higher lows pattern |
| B9 | Price above mid-range condition |
| B10 | Recent 250-day low check |
| B11 | ATR not at highest level |
| B12 | 150-day moving average growth |
| B13 | Comparative price performance |
| B18 | Market Trend Template (MMT) |

### Exit Signals (S1–S17)

| Signal | Description |
|--------|-------------|
| S1 | ATR-based stop loss |
| S4 | Profitable days ratio |
| S5 | Moving stop |
| S6 | No new high in N days |
| S7 | Dark candle pattern |
| S8 | ATR volatility expansion |
| S10 | ATR ratio and high retracement |
| S11 | Fibonacci 0.382 level |
| S12 | Fibonacci 0.236 level |
| S13 | Lowest low condition |
| S14 | Comparative price decline |
| S15 | Price pullback percentage |
| S16 | ATR increase with pullback |
| S17 | Range ratio |

---

**Last Updated:** February 2026  
**Python Version:** 3.11+  
**Framework:** FastAPI 0.104.1
