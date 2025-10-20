# Algorithm Testing Service

A distributed service for testing algorithms with a queue-based architecture and worker system, specifically designed for processing Hong Kong stock market data.

## Architecture

```
API Request → Queue 1 (algorithm_calculation) → Worker 1 → Queue 2 (result_processing) → Worker 2
```

The service implements a two-stage processing pipeline:

1. **Algorithm Calculation Queue**: Processes individual stock codes from HKEX
2. **Result Processing Queue**: Performs final calculations and result aggregation

## Components

-   **FastAPI** - REST API server
-   **Redis** - Queue system and caching
-   **RQ (Redis Queue)** - Background job processing workers
-   **Docker** - Containerization
-   **RQ Dashboard** - Web interface for queue monitoring
-   **Pandas & OpenPyXL** - Data processing for stock market data

## Features

-   **Stock Data Integration**: Automatically fetches and processes Hong Kong stock codes from HKEX
-   **Distributed Processing**: Two-stage queue system for scalable algorithm testing
-   **Real-time Monitoring**: Comprehensive monitoring endpoints and web dashboard
-   **Docker Support**: Full containerization with health checks
-   **Logging**: Structured logging with configurable levels
-   **Error Handling**: Robust error handling and retry mechanisms

## Quick Start

### Using Docker Compose (Recommended)

```bash
docker-compose up --build
```

This will start:

-   Redis server
-   FastAPI application
-   Algorithm worker
-   Result processing worker
-   RQ Dashboard

### Local Development

1. Install Redis locally
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Start the API server:

```bash
uvicorn app.main:app --reload
```

4. Start workers (in separate terminals):

```bash
python workers/start_algorithm_worker.py
python workers/start_result_worker.py
```

## API Endpoints

### Core Endpoints

-   `GET /` - Service status
-   `GET /health` - Health check
-   `GET /api/v1/start-testing/` - Initialize algorithm testing (fetches stock codes and queues them)

### Monitoring Endpoints

-   `GET /api/v1/monitoring/queues` - Detailed queue information
-   `GET /api/v1/monitoring/workers` - Worker status and statistics
-   `GET /api/v1/monitoring/jobs/{queue_name}` - Jobs in specific queue
-   `GET /api/v1/monitoring/stats` - Overall system statistics

## Usage Examples

### Initialize Algorithm Testing

```bash
curl -X GET "http://localhost:8000/api/v1/start-testing/"
```

This endpoint:

1. Fetches current Hong Kong stock codes from HKEX
2. Filters out excluded ranges (derivatives, bonds, etc.)
3. Queues the first 3 stock codes for processing (configurable)

### Monitor System Status

```bash
curl -X GET "http://localhost:8000/api/v1/monitoring/stats"
```

### Check Queue Status

```bash
curl -X GET "http://localhost:8000/api/v1/monitoring/queues"
```

## Project Structure

```
algorithm-testing-service/
├── app/
│   ├── main.py                          # FastAPI application
│   ├── controllers/                     # API controllers
│   │   ├── algorithm_controller.py      # Algorithm testing endpoints
│   │   └── monitoring_controller.py     # Monitoring endpoints
│   ├── models/                          # Pydantic models
│   │   └── algorithm_models.py          # Data models
│   ├── services/                        # Business logic
│   │   ├── get_all_stoccks.py          # Stock data fetching
│   │   └── queue_service.py             # Queue management
│   ├── config/                          # Configuration
│   │   ├── logging_config.py           # Logging setup
│   │   └── queue_config.py             # Queue configuration
│   └── workers/                         # Background workers
│       ├── algorithm_worker.py          # First-stage processing
│       └── result_worker.py             # Second-stage processing
├── workers/                             # Worker startup scripts
│   ├── start_algorithm_worker.py
│   └── start_result_worker.py
├── dashboard/                           # RQ Dashboard
│   └── start_dashboard.py
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

## Data Sources

The service integrates with Hong Kong Exchanges and Clearing Limited (HKEX):

-   **Source**: https://www.hkex.com.hk/eng/services/trading/securities/securitieslists/ListOfSecurities.xlsx
-   **Data Format**: Excel file with stock codes and trading information
-   **Processing**: Automatically filters out derivatives, bonds, and other non-equity securities

## Configuration

### Environment Variables

| Variable         | Default     | Description               |
| ---------------- | ----------- | ------------------------- |
| `REDIS_HOST`     | redis       | Redis server hostname     |
| `REDIS_PORT`     | 6379        | Redis server port         |
| `REDIS_PASSWORD` | -           | Redis password (optional) |
| `API_PORT`       | 8000        | FastAPI server port       |
| `DASHBOARD_PORT` | 9181        | RQ Dashboard port         |
| `LOG_LEVEL`      | INFO        | Logging level             |
| `ENVIRONMENT`    | development | Environment name          |
| `DEBUG`          | true        | Debug mode                |

### Worker Configuration

-   `ALGORITHM_WORKER_TIMEOUT` - Algorithm worker timeout (default: 300s)
-   `ALGORITHM_WORKER_MAX_RETRIES` - Max retries for algorithm worker (default: 3)
-   `RESULT_WORKER_TIMEOUT` - Result worker timeout (default: 300s)
-   `RESULT_WORKER_MAX_RETRIES` - Max retries for result worker (default: 3)

## Monitoring

### Web Interfaces

-   **API Documentation**: http://localhost:8000/docs
-   **RQ Dashboard**: http://localhost:9181 - Queue monitoring interface
-   **Redis**: localhost:6379

### API Monitoring

-   `GET /api/v1/monitoring/queues` - Queue status and job counts
-   `GET /api/v1/monitoring/workers` - Worker status and statistics
-   `GET /api/v1/monitoring/stats` - Overall system statistics
-   `GET /api/v1/monitoring/jobs/{queue_name}` - Detailed job information

### Logging

-   **Structured Logging**: JSON format with configurable levels
-   **Log Directory**: `/app/logs` (mounted volume in Docker)
-   **Log Rotation**: Automatic log rotation and cleanup
-   **Docker Logs**: `docker-compose logs -f` for real-time monitoring

## Development

### Adding Custom Logic

#### Algorithm Worker (First Queue)

File: `app/workers/algorithm_worker.py`
Function: `process_algorithm_task()`

This worker receives stock codes and performs initial algorithm calculations.

#### Result Worker (Second Queue)

File: `app/workers/result_worker.py`
Function: `process_result_task()`

This worker receives processed results and performs final calculations.

### Stock Code Processing

The service automatically:

1. Fetches stock codes from HKEX
2. Filters out excluded ranges (derivatives, bonds, etc.)
3. Validates numeric codes (≤ 9999)
4. Queues valid codes for processing

### Error Handling

-   **Retry Logic**: Configurable retry attempts for failed jobs
-   **Timeout Handling**: Worker timeouts prevent hanging processes
-   **Error Logging**: Comprehensive error logging and monitoring
-   **Graceful Degradation**: Service continues operating despite individual job failures

## Dependencies

-   **FastAPI 0.104.1** - Web framework
-   **Uvicorn 0.24.0** - ASGI server
-   **Redis 5.0.1** - Queue and caching
-   **RQ 1.15.1** - Job queue system
-   **RQ Dashboard 0.8.5** - Monitoring interface
-   **Pandas 2.1.3** - Data processing
-   **OpenPyXL 3.1.5** - Excel file handling
-   **Requests 2.32.3** - HTTP client

## Production Considerations

-   **Scaling**: Add more worker instances for increased throughput
-   **Monitoring**: Set up external monitoring for Redis and application health
-   **Security**: Configure Redis authentication and network security
-   **Backup**: Implement Redis persistence and backup strategies
-   **Logging**: Configure centralized logging for production environments

## Troubleshooting

### Common Issues

1. **Redis Connection**: Ensure Redis is running and accessible
2. **Worker Startup**: Check worker logs for configuration issues
3. **Stock Data**: Verify network connectivity to HKEX
4. **Memory Usage**: Monitor Redis memory usage for large job queues

### Health Checks

-   **API Health**: `GET /health`
-   **Redis Health**: Automatic health checks in Docker Compose
-   **Worker Health**: Monitor via RQ Dashboard or API endpoints
