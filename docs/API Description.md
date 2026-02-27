# API Documentation

Base URL: `http://localhost:8000`

---

## Table of Contents

1. [Health & Status Endpoints](#health--status-endpoints)
2. [Algorithm Testing Endpoints](#algorithm-testing-endpoints)
3. [Optimization Endpoints (Dynamic Parameters)](#optimization-endpoints-dynamic-parameters)
4. [Genome Endpoints](#genome-endpoints)
5. [Google Sheets Endpoints](#google-sheets-endpoints)
6. [Monitoring Endpoints](#monitoring-endpoints)
7. [Summary Endpoints](#summary-endpoints)
8. [Dashboard](#dashboard)
9. [Workflow Examples](#workflow-examples)
10. [Google Sheets Integration](#google-sheets-integration)

---

## Health & Status Endpoints

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

**Description:** Start algorithm testing for all stocks in `screener.csv`. Automatically skips stocks already present in `results.csv` and enqueues the remaining stocks to the algorithm queue.

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
  "done": ["0001", "0005"],
  "added": ["3888", "2800", "0700"],
  "status": "queued"
}
```

**Example:**
```bash
curl http://localhost:8000/api/v1/start-testing/
```

---

## Optimization Endpoints (Dynamic Parameters)

### `POST /api/v1/run-optimization`

**Description:** Start a new optimization run that tests multiple parameter combinations (genomes) across one or more stocks.

**Request Body (Google Sheets):**
```json
{
  "stock_codes": ["3888", "2800"],
  "use_google_sheets": true,
  "sheet_id": "11a3m0AlIGsZ5O1HRVgjCP3zSCds-b_5OJGXmHKCP56U"
}
```

**Request Body (manual parameter ranges):**
```json
{
  "stock_codes": ["3888"],
  "parameter_ranges": [
    {
      "Parameter Variable": "input_B1_upper_range",
      "Base": 0.65,
      "Min": 0.55,
      "Max": 0.75,
      "Step": 0.1,
      "Change": true,
      "Rule": "B1"
    },
    {
      "Parameter Variable": "input_B3_LR_lookback",
      "Base": 58,
      "Min": 40,
      "Max": 80,
      "Step": 10,
      "Change": true,
      "Rule": "B3"
    }
  ]
}
```

**Response:**
```json
{
  "optimization_id": "opt_abc123def456",
  "total_genomes": 6,
  "total_tasks": 6,
  "stock_codes": ["3888"],
  "status": "queued",
  "message": "Optimization created and 6 tasks queued successfully"
}
```

**Example:**
```bash
curl -X POST http://localhost:8000/api/v1/run-optimization \
  -H "Content-Type: application/json" \
  -d '{"stock_codes": ["3888"], "use_google_sheets": true}'
```

---

### `GET /api/v1/optimization/{optimization_id}/status`

**Description:** Get the current status and progress of a running optimization.

**Path Parameters:**
- `optimization_id` — The optimization ID returned from `/run-optimization`

**Response:**
```json
{
  "optimization_id": "opt_abc123def456",
  "status": "running",
  "total_tasks": 30,
  "completed_tasks": 15,
  "failed_tasks": 0,
  "progress_percent": 50.0,
  "total_genomes": 6,
  "stock_codes": ["3888"],
  "created_at": "2026-02-04T15:30:00",
  "updated_at": "2026-02-04T15:35:00",
  "elapsed_seconds": 300.0,
  "eta_seconds": 300.0,
  "eta_formatted": "5m 0s",
  "smart_filtering": {
    "enabled": true,
    "genomes_skipped": 3,
    "eliminated_params": [],
    "error": null
  }
}
```

**Status Values:**
- `pending` — Optimization created, not yet started
- `queued` — Tasks queued to workers
- `running` — Currently processing
- `completed` — All tasks finished
- `failed` — Optimization failed
- `cancelled` — Manually cancelled

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
  "total_results": 6,
  "results": [
    {
      "genome_id": "G_000",
      "stock_code": "3888",
      "trade_count": 12,
      "profit_delta": 31.74,
      "win_rate_delta": 15.2,
      "payoff_ratio": 2.8
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
curl -X POST http://localhost:8000/api/v1/optimization/opt_abc123def456/cancel
```

---

### `GET /api/v1/optimizations`

**Description:** List recent optimizations with their status.

**Query Parameters:**
- `limit` (optional, default: 50) — Maximum number of results

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
    "total_genomes": 6,
    "stock_codes": ["3888"],
    "created_at": "2026-02-04T15:30:00",
    "updated_at": "2026-02-04T16:00:00",
    "elapsed_seconds": 1800.0
  }
]
```

**Example:**
```bash
curl http://localhost:8000/api/v1/optimizations?limit=10
```

---

### `POST /api/v1/preview-genomes`

**Description:** Preview the number of genome combinations that would be generated before starting an optimization.

**Request Body:**
```json
{
  "use_google_sheets": true,
  "sheet_id": "11a3m0AlIGsZ5O1HRVgjCP3zSCds-b_5OJGXmHKCP56U"
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
    }
  ],
  "fixed_parameters_count": 31
}
```

**Example:**
```bash
curl -X POST http://localhost:8000/api/v1/preview-genomes \
  -H "Content-Type: application/json" \
  -d '{"use_google_sheets": true}'
```

---

## Genome Endpoints

### `GET /api/v1/genome/{genome_id}/parameters`

**Description:** Get the parameter values for a specific genome.

**Path Parameters:**
- `genome_id` — The genome identifier (e.g., `G_001`)

**Query Parameters:**
- `optimization_id` (optional) — Scope search to a specific optimization

**Response:** Returns the genome parameters dictionary, or 404 if not found.

**Example:**
```bash
curl http://localhost:8000/api/v1/genome/G_001/parameters?optimization_id=opt_abc123def456
```

---

## Google Sheets Endpoints

### `GET /api/v1/sheets/health`

**Description:** Check Google Sheets connection, read/write permissions, and current configuration.

**Response:**
```json
{
  "connected": true,
  "read": true,
  "write": true,
  "config": {
    "input_sheet_id": "...",
    "output_sheet_id": "...",
    "input_sheet_name": "Parameter Tuning",
    "output_sheet_name": "Automated Results",
    "output_per_genome_sheet_name": "Automated Results Per Genome"
  },
  "error": null
}
```

**Example:**
```bash
curl http://localhost:8000/api/v1/sheets/health
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
      "pending_jobs": 5,
      "failed_jobs": 0,
      "scheduled_jobs": 0,
      "started_jobs": 2
    },
    {
      "name": "result_processing",
      "pending_jobs": 3,
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

**Description:** Get information about active workers (state, current job, success/failure counts).

**Response:**
```json
{
  "workers": [
    {
      "name": "worker-1",
      "queues": ["algorithm_calculation"],
      "state": "busy",
      "current_job": "job-uuid",
      "last_heartbeat": "2026-02-04T15:35:00",
      "successful_job_count": 100,
      "failed_job_count": 2
    }
  ],
  "total_workers": 2
}
```

**Worker States:** `busy`, `idle`, `suspended`

**Example:**
```bash
curl http://localhost:8000/api/v1/monitoring/workers
```

---

### `GET /api/v1/monitoring/jobs/{queue_name}`

**Description:** List jobs in a specific queue.

**Path Parameters:**
- `queue_name` — Either `algorithm_calculation` or `result_processing`

**Query Parameters:**
- `limit` (optional, default: 10) — Maximum number of jobs to return

**Response:**
```json
{
  "queue_name": "algorithm_calculation",
  "jobs": [
    {
      "id": "job-uuid",
      "status": "queued",
      "created_at": "2026-02-04T15:30:00",
      "enqueued_at": "2026-02-04T15:30:01",
      "data": "process_algorithm_task(stock=3888...)"
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
    "pending": 5,
    "failed": 0,
    "scheduled": 0,
    "started": 2
  },
  "result_queue": {
    "pending": 3,
    "failed": 0,
    "scheduled": 0,
    "started": 1
  },
  "workers": {
    "total": 4,
    "busy": 3,
    "idle": 1
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
    "Total # of Trades (Closed)": 50,
    "Total # of Open Trades": 3,
    "Number Winning Trades": 30,
    "Number Losing Trades": 20,
    "Percent Profitable": "60.00%",
    "Avg Trade (win & loss) ($)": "125.50",
    "Average Winning Trade ($)": "350.00",
    "Average Losing Trade ($)": "-210.00",
    "Ratio Avg Win / Avg Loss": "1.67"
  }
}
```

**Example:**
```bash
curl http://localhost:8000/api/v1/summary/
```

---

## Dashboard

### `GET /dashboard`

**Description:** HTML dashboard for monitoring optimization progress in real-time. Auto-polls the status API and displays progress, ETA, skipped genomes, and toxic parameters.

Open in browser: [http://localhost:8000/dashboard](http://localhost:8000/dashboard)

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
# 1. Check Google Sheets connection
curl http://localhost:8000/api/v1/sheets/health

# 2. Preview genome combinations
curl -X POST http://localhost:8000/api/v1/preview-genomes \
  -H "Content-Type: application/json" \
  -d '{"use_google_sheets": true}'

# 3. Start optimization
curl -X POST http://localhost:8000/api/v1/run-optimization \
  -H "Content-Type: application/json" \
  -d '{"stock_codes": ["3888", "2800"], "use_google_sheets": true}'

# Response: {"optimization_id": "opt_abc123def456", ...}

# 4. Monitor progress (API or dashboard)
curl http://localhost:8000/api/v1/optimization/opt_abc123def456/status
# Or open http://localhost:8000/dashboard in browser

# 5. Get results when complete
curl http://localhost:8000/api/v1/optimization/opt_abc123def456/results

# 6. Get specific genome parameters
curl http://localhost:8000/api/v1/genome/G_001/parameters?optimization_id=opt_abc123def456
```

---

## Google Sheets Integration

For optimization endpoints using Google Sheets:

**Required Environment Variables:**
```env
GOOGLE_SHEETS_CREDENTIALS_PATH=/app/credentials/google_sheets.json
INPUT_SHEET_ID=your-input-sheet-id
OUTPUT_SHEET_ID=your-output-sheet-id
INPUT_SHEET_NAME=Parameter Tuning
OUTPUT_SHEET_NAME=Automated Results
OUTPUT_PER_GENOME_SHEET_NAME=Automated Results Per Genome
```

**Sheet Structure:**
- **Input Tab** (`Parameter Tuning`) — Contains parameter ranges for optimization
- **Output Tab** (`Automated Results`) — Aggregated genome comparison results
- **Output Per Genome Tab** (`Automated Results Per Genome`) — Detailed per-genome results
