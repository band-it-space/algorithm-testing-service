# API Documentation

Base URL: `http://localhost:8000`

---

## Table of Contents

1. [Health & Status Endpoints](#health--status-endpoints)
2. [Algorithm Testing Endpoints](#algorithm-testing-endpoints)
3. [Optimization Endpoints (Dynamic Parameters)](#optimization-endpoints-dynamic-parameters)
4. [Monitoring Endpoints](#monitoring-endpoints)
5. [Summary Endpoints](#summary-endpoints)
6. [Test Endpoints](#test-endpoints)

---

## Health & Status Endpoints

### `GET /`
**Description:** Root endpoint that returns service status message.

**Response:**
```json
{
  "message": "Algorithm Testing Service is running"
}
```

**Example:**
```bash
curl http://localhost:8000/
```

---

### `GET /health`
**Description:** Health check endpoint for Docker container monitoring.

**Response:**
```json
{
  "status": "healthy"
}
```

**Example:**
```bash
curl http://localhost:8000/health
```

---

## Algorithm Testing Endpoints

### `GET /api/v1/start-testing/`
**Description:** Start algorithm testing for all stocks in `screener.csv`. Automatically skips stocks that are already processed (exist in `results.csv`) and queues the remaining stocks to the algorithm queue.

**Process:**
1. Reads stock list from `data/screener.csv`
2. Reads existing results from `data/results.csv`
3. Skips already processed stocks
4. Adds new stocks to algorithm queue
5. Workers process each stock with default parameters

**Response:**
```json
{
  "message": "Done: 10, Added to queue: 5",
  "done": ["3888", "2800", "1234"],
  "added": ["5678", "9012"],
  "status": "queued"
}
```

**Example:**
```bash
curl http://localhost:8000/api/v1/start-testing/
```

**Use Case:** Traditional algorithm testing with default parameters for all stocks.

---

## Optimization Endpoints (Dynamic Parameters)

### `POST /api/v1/run-optimization`
**Description:** Start a new optimization run that tests multiple parameter combinations (genomes) across one or more stocks. This is the main endpoint for dynamic parameters integration.

**Request Body:**
```json
{
  "stock_codes": ["3888", "2800"],
  "use_google_sheets": true,
  "sheet_id": "11a3m0AlIGsZ5O1HRVgjCP3zSCds-b_5OJGXmHKCP56U"
}
```

**OR with manual parameter ranges:**
```json
{
  "stock_codes": ["3888"],
  "parameter_ranges": [
    {
      "Rule": "B1",
      "Parameter Variable": "input_B1_upper_range",
      "Base": 0.65,
      "Min": 0.55,
      "Max": 0.75,
      "Step": 0.1,
      "Change": true
    },
    {
      "Rule": "B3",
      "Parameter Variable": "input_B3_LR_lookback",
      "Base": 58,
      "Min": 40,
      "Max": 80,
      "Step": 10,
      "Change": true
    }
  ]
}
```

**Response:**
```json
{
  "optimization_id": "opt_abc123def456",
  "total_genomes": 15,
  "total_tasks": 30,
  "stock_codes": ["3888", "2800"],
  "status": "pending",
  "message": "Optimization created. Queuing 30 tasks..."
}
```

**Example:**
```bash
# PowerShell
Invoke-WebRequest -Uri "http://localhost:8000/api/v1/run-optimization" `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"stock_codes": ["3888"], "use_google_sheets": true}'

# Bash
curl -X POST http://localhost:8000/api/v1/run-optimization \
  -H "Content-Type: application/json" \
  -d '{"stock_codes": ["3888"], "use_google_sheets": true}'
```

---

### `GET /api/v1/optimization/{optimization_id}/status`
**Description:** Get the current status and progress of a running optimization.

**Path Parameters:**
- `optimization_id` - The optimization ID returned from `/run-optimization`

**Response:**
```json
{
  "optimization_id": "opt_abc123def456",
  "status": "running",
  "total_tasks": 30,
  "completed_tasks": 15,
  "failed_tasks": 0,
  "progress_percent": 50.0,
  "total_genomes": 15,
  "stock_codes": ["3888", "2800"],
  "created_at": "2026-02-04T15:30:00",
  "updated_at": "2026-02-04T15:35:00"
}
```

**Status Values:**
- `pending` - Optimization created, not yet started
- `queued` - Tasks queued to workers
- `running` - Currently processing
- `completed` - All tasks finished
- `failed` - Optimization failed
- `cancelled` - Manually cancelled

**Example:**
```bash
curl http://localhost:8000/api/v1/optimization/opt_abc123def456/status
```

---

### `GET /api/v1/optimization/{optimization_id}/results`
**Description:** Get all genome results for a completed optimization.

**Response:**
```json
{
  "optimization_id": "opt_abc123def456",
  "status": "completed",
  "total_results": 30,
  "results": [
    {
      "genome_id": "G_000",
      "stock_code": "3888",
      "trade_count": 10,
      "profit_delta": 0,
      "win_rate_delta": 0,
      "total_win": 21580,
      "total_loss": 8045,
      "trades_win": 5,
      "trades_loss": 5,
      "avg_win": 4316,
      "avg_loss": 1609,
      "payoff_ratio": 2.68,
      "parameters": {
        "input_B1_upper_range": 0.65,
        "input_B3_LR_lookback": 58
      }
    },
    {
      "genome_id": "G_001",
      "stock_code": "3888",
      "profit_delta": 15.89,
      "win_rate_delta": -5.56,
      "...": "..."
    }
  ]
}
```

**Example:**
```bash
curl http://localhost:8000/api/v1/optimization/opt_abc123def456/results
```

---

### `POST /api/v1/optimization/{optimization_id}/cancel`
**Description:** Cancel a running optimization. Cannot cancel already completed optimizations.

**Response:**
```json
{
  "message": "Optimization opt_abc123def456 cancelled"
}
```

**Example:**
```bash
# PowerShell
Invoke-WebRequest -Uri "http://localhost:8000/api/v1/optimization/opt_abc123def456/cancel" -Method POST

# Bash
curl -X POST http://localhost:8000/api/v1/optimization/opt_abc123def456/cancel
```

---

### `GET /api/v1/optimizations`
**Description:** List recent optimizations with their status.

**Query Parameters:**
- `limit` (optional) - Maximum number of results (default: 50)

**Response:**
```json
[
  {
    "optimization_id": "opt_abc123def456",
    "status": "completed",
    "total_tasks": 30,
    "completed_tasks": 30,
    "failed_tasks": 0,
    "progress_percent": 100.0,
    "total_genomes": 15,
    "stock_codes": ["3888", "2800"],
    "created_at": "2026-02-04T15:30:00",
    "updated_at": "2026-02-04T15:45:00"
  }
]
```

**Example:**
```bash
curl http://localhost:8000/api/v1/optimizations?limit=10
```

---

### `POST /api/v1/preview-genomes`
**Description:** Preview the number of genome combinations that would be generated before starting an optimization. Useful for estimating computational cost.

**Request Body:**
```json
{
  "use_google_sheets": true,
  "sheet_id": "11a3m0AlIGsZ5O1HRVgjCP3zSCds-b_5OJGXmHKCP56U"
}
```

**OR:**
```json
{
  "parameter_ranges": [
    {
      "Rule": "B1",
      "Parameter Variable": "input_B1_upper_range",
      "Base": 0.65,
      "Min": 0.55,
      "Max": 0.75,
      "Step": 0.1,
      "Change": true
    }
  ]
}
```

**Response:**
```json
{
  "total_combinations": 16,
  "variable_parameters": [
    {
      "name": "input_B1_upper_range",
      "rule": "B1",
      "base": 0.65,
      "min": 0.55,
      "max": 0.75,
      "step": 0.1,
      "values_count": 3
    },
    {
      "name": "input_B3_LR_lookback",
      "rule": "B3",
      "base": 58,
      "min": 40,
      "max": 80,
      "step": 10,
      "values_count": 5
    }
  ],
  "fixed_parameters_count": 31
}
```

**Calculation:** Total = (3 values × 5 values) + 1 BASE = 16 genomes

**Example:**
```bash
curl -X POST http://localhost:8000/api/v1/preview-genomes \
  -H "Content-Type: application/json" \
  -d '{"use_google_sheets": true}'
```

---

## Monitoring Endpoints

### `GET /api/v1/monitoring/queues`
**Description:** Get detailed information about all queues (pending, failed, scheduled, started jobs).

**Response:**
```json
{
  "queues": [
    {
      "name": "algorithm_calculation",
      "pending_jobs": 15,
      "failed_jobs": 2,
      "scheduled_jobs": 0,
      "started_jobs": 1
    },
    {
      "name": "result_processing",
      "pending_jobs": 8,
      "failed_jobs": 0,
      "scheduled_jobs": 0,
      "started_jobs": 1
    }
  ],
  "redis_connection": {
    "host": "redis",
    "port": 6379,
    "db": 0,
    "connected": true
  }
}
```

**Example:**
```bash
curl http://localhost:8000/api/v1/monitoring/queues
```

---

### `GET /api/v1/monitoring/workers`
**Description:** Get information about active workers (their state, current job, success/failure counts).

**Response:**
```json
{
  "workers": [
    {
      "name": "algorithm-worker.1",
      "queues": ["algorithm_calculation"],
      "state": "busy",
      "current_job": "abc-123-def",
      "last_heartbeat": "2026-02-04T15:30:45",
      "successful_job_count": 152,
      "failed_job_count": 3
    },
    {
      "name": "result-worker.1",
      "queues": ["result_processing"],
      "state": "idle",
      "current_job": null,
      "last_heartbeat": "2026-02-04T15:30:50",
      "successful_job_count": 148,
      "failed_job_count": 1
    }
  ],
  "total_workers": 2
}
```

**Worker States:**
- `busy` - Currently processing a job
- `idle` - Waiting for jobs
- `suspended` - Worker paused

**Example:**
```bash
curl http://localhost:8000/api/v1/monitoring/workers
```

---

### `GET /api/v1/monitoring/jobs/{queue_name}`
**Description:** List jobs in a specific queue.

**Path Parameters:**
- `queue_name` - Either `algorithm_calculation` or `result_processing`

**Query Parameters:**
- `limit` (optional) - Maximum number of jobs to return (default: 10)

**Response:**
```json
{
  "queue_name": "algorithm_calculation",
  "jobs": [
    {
      "id": "abc-123-def",
      "status": "queued",
      "created_at": "2026-02-04T15:30:00",
      "enqueued_at": "2026-02-04T15:30:01",
      "data": "Stock: 3888, Genome: G_001"
    }
  ],
  "total_pending": 15
}
```

**Example:**
```bash
curl http://localhost:8000/api/v1/monitoring/jobs/algorithm_calculation?limit=20
```

---

### `GET /api/v1/monitoring/stats`
**Description:** Get overall system statistics (all queues and workers).

**Response:**
```json
{
  "algorithm_queue": {
    "pending": 15,
    "failed": 2,
    "scheduled": 0,
    "started": 1
  },
  "result_queue": {
    "pending": 8,
    "failed": 0,
    "scheduled": 0,
    "started": 1
  },
  "workers": {
    "total_workers": 3,
    "active_workers": 2,
    "idle_workers": 1
  },
  "total_jobs": 24
}
```

**Example:**
```bash
curl http://localhost:8000/api/v1/monitoring/stats
```

---

## Summary Endpoints

### `GET /api/v1/summary/`
**Description:** Generate trading summary from `general_results.csv`. Calculates win/loss statistics for closed trades only and saves to `summary.csv`.

**Process:**
1. Reads `data/general_results.csv`
2. Separates open/closed trades
3. Calculates statistics on closed trades only
4. Saves results to `data/summary.csv`

**Response:**
```json
{
  "message": "Summary generated successfully",
  "file": "summary.csv",
  "stats": {
    "Total # of Trades (Closed)": 150,
    "Total # of Open Trades": 5,
    "Number Winning Trades": 98,
    "Number Losing Trades": 52,
    "Percent Profitable": "65.33%",
    "Avg Trade (win & loss) ($)": "125.45",
    "Average Winning Trade ($)": "245.80",
    "Average Losing Trade ($)": "-85.23",
    "Ratio Avg Win / Avg Loss": "2.88"
  }
}
```

**Example:**
```bash
curl http://localhost:8000/api/v1/summary/
```

---

## Test Endpoints

### `GET /data-test`
**Description:** Test endpoint for data operations (development only).

**Response:**
```json
{
  "message": "Data test endpoint"
}
```

---

### `GET /test`
**Description:** Test endpoint for result processing worker (development only).

**Response:**
```json
{
  "message": "Ok"
}
```

---

### `GET /test-algo`
**Description:** Test endpoint for algorithm worker with stock 2800 (development only).

**Response:**
Returns algorithm processing results for stock 2800.

---

## Workflow Examples

### Traditional Algorithm Testing

```bash
# 1. Start testing all stocks with default parameters
curl http://localhost:8000/api/v1/start-testing/

# 2. Monitor queue status
curl http://localhost:8000/api/v1/monitoring/stats

# 3. Generate summary when complete
curl http://localhost:8000/api/v1/summary/
```

### Dynamic Parameters Optimization

```bash
# 1. Preview genome combinations
curl -X POST http://localhost:8000/api/v1/preview-genomes \
  -H "Content-Type: application/json" \
  -d '{"use_google_sheets": true}'

# 2. Start optimization
curl -X POST http://localhost:8000/api/v1/run-optimization \
  -H "Content-Type: application/json" \
  -d '{"stock_codes": ["3888", "2800"], "use_google_sheets": true}'

# Response: {"optimization_id": "opt_abc123def456", ...}

# 3. Monitor progress
curl http://localhost:8000/api/v1/optimization/opt_abc123def456/status

# 4. Get results when complete
curl http://localhost:8000/api/v1/optimization/opt_abc123def456/results

# 5. Check worker activity
curl http://localhost:8000/api/v1/monitoring/workers
```

---

## Google Sheets Integration

For optimization endpoints using Google Sheets:

**Required Environment Variables:**
```env
GOOGLE_SHEETS_CREDENTIALS_PATH=/app/credentials/google_sheets.json
INPUT_SHEET_ID=11a3m0AlIGsZ5O1HRVgjCP3zSCds-b_5OJGXmHKCP56U
OUTPUT_SHEET_ID=11a3m0AlIGsZ5O1HRVgjCP3zSCds-b_5OJGXmHKCP56U
```

**Sheet Structure:**
- **Input Tab:** `Parameter Tuning` - Contains parameter ranges
- **Output Tab:** `Automated Results` - Receives optimization results

**Input Tab Columns:**
| Column | Description |
|--------|-------------|
| Rule | Rule identifier (B1, B3, S1, etc.) |
| Parameter Variable | Parameter name (e.g., input_B1_upper_range) |
| Base | Base value for the parameter |
| Min | Minimum value for optimization |
| Max | Maximum value for optimization |
| Step | Step size for value generation |
| Change | TRUE to vary, FALSE to keep fixed |

---

## Error Responses

All endpoints return standard error responses:

```json
{
  "detail": "Error message description"
}
```

**Common HTTP Status Codes:**
- `200` - Success
- `400` - Bad Request (invalid input)
- `404` - Not Found (resource doesn't exist)
- `500` - Internal Server Error

---

## Interactive API Documentation

Access the auto-generated Swagger UI documentation:

**Swagger UI:** `http://localhost:8000/docs`  
**ReDoc:** `http://localhost:8000/redoc`

These provide interactive API testing capabilities directly in your browser.

---

*For detailed setup instructions, see [start_guideline.md](./start_guideline.md)*
