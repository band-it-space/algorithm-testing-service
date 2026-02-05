# Docker Startup Guide

This guide explains how to configure and run the project in Docker with the dynamic parameters integration.

---

## Prerequisites

1. **Docker** and **Docker Compose** installed
2. **Google Cloud Service Account** (for Sheets integration)
3. **MySQL Database** accessible from Docker network

---

## Step 1: Environment Configuration

### 1.1 Create `.env` File

Copy the example and fill in your values:

```bash
cp .env.example .env
```

If `.env.example` doesn't exist, create `.env` with these variables:

```env
# =================================
# Redis Configuration
# =================================
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=

# =================================
# API Service Configuration
# =================================
API_PORT=8000
ENVIRONMENT=development
DEBUG=true
LOG_LEVEL=INFO
LOG_JSON=false

# =================================
# Database Configuration
# =================================
DB_HOST=your-database-host
DB_PORT=3306
DB_USER=your-db-user
DB_PASSWORD=your-db-password
DB_NAME=your-db-name

# =================================
# Google Sheets Configuration
# =================================
# Path to service account JSON file (inside container)
GOOGLE_SHEETS_CREDENTIALS_PATH=/app/credentials/google_sheets.json

# Google Sheet ID for reading parameter ranges
# (Extract from sheet URL: https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit)
INPUT_SHEET_ID=your-input-sheet-id

# Google Sheet ID for writing results
OUTPUT_SHEET_ID=your-output-sheet-id

# =================================
# Worker Configuration
# =================================
ALGORITHM_WORKER_TIMEOUT=1000
ALGORITHM_WORKER_MAX_RETRIES=3
RESULT_WORKER_TIMEOUT=300
RESULT_WORKER_MAX_RETRIES=3
FILE_WRITE_WORKER_TIMEOUT=60
FILE_WRITE_WORKER_MAX_RETRIES=3

# =================================
# Dashboard Configuration
# =================================
DASHBOARD_PORT=9181
DASHBOARD_USERNAME=
DASHBOARD_PASSWORD=

# =================================
# Health Check Configuration
# =================================
HEALTH_CHECK_INTERVAL=30
HEALTH_CHECK_TIMEOUT=10
```

---

## Step 2: Google Sheets Setup

### 2.1 Create Service Account

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing
3. Enable **Google Sheets API** and **Google Drive API**
4. Navigate to **IAM & Admin** → **Service Accounts**
5. Create service account:
   - Name: `hk-algo-sheets`
   - Role: None required at project level
6. Generate JSON key:
   - Click on the service account
   - Go to **Keys** tab
   - **Add Key** → **Create new key** → **JSON**
   - Download the JSON file

### 2.2 Place Credentials

Create the credentials directory and place the file:

```bash
mkdir -p credentials
mv ~/Downloads/your-service-account-key.json credentials/google_sheets.json
```

**Important:** The file must be named `google_sheets.json` to match the Docker volume mount.

### 2.3 Share Sheets with Service Account

Share your Google Sheets with the service account email:

1. Open your Input Parameter Google Sheet
2. Click **Share**
3. Add the service account email (found in the JSON file: `client_email`)
4. Grant **Viewer** permission for Input Sheet
5. Grant **Editor** permission for Output Sheet

---

## Step 3: Prepare Input Google Sheet

Create a Google Sheet with the following structure:

### Sheet Name: `Parameter Tuning`

| Rule | Parameter Variable | Base | Min | Max | Step | Combs | Change |
|------|-------------------|------|-----|-----|------|-------|--------|
| B1 | input_B1_lookback | 20 | 1 | 1 | 1 | 1 | FALSE |
| B1 | input_B1_upper_range | 0.65 | 0.55 | 0.75 | 0.1 | 3 | TRUE |
| B3 | input_B3_LR_lookback | 58 | 40 | 80 | 10 | 5 | TRUE |
| ... | ... | ... | ... | ... | ... | ... | ... |

**Key Columns:**
- **Parameter Variable**: Must match `AlgorithmParameters` field names exactly
- **Change**: Set to `TRUE` for parameters to optimize, `FALSE` for fixed values
- **Min/Max/Step**: Define the range for optimization
- **Base**: Default value used in BASE genome (G_000)

**How to Modify Parameters:**

1. Open your Google Sheet
2. Go to the `Parameter Tuning` tab
3. Find the parameter you want to optimize
4. Change the **Change** column to `TRUE`
5. Set **Min**, **Max**, and **Step** values
6. Save (Google Sheets auto-saves)

**Example: Optimize B1_upper_range:**
```
Change "Change" from FALSE to TRUE
Set Min: 0.55
Set Max: 0.75
Set Step: 0.1
Result: Will test values [0.55, 0.65, 0.75]
```

Refer to [docs/Input Rule Parameter IDs Sample.csv](./Input%20Rule%20Parameter%20IDs%20Sample.csv) for full list.

---

## Step 4: Build and Run

### 4.1 Build Docker Images

```bash
docker-compose build
```

### 4.2 Start All Services

```bash
docker-compose up -d
```

This starts:
- **redis** - Message queue
- **algorithm-service** - FastAPI server (port 8000)
- **algorithm-worker** - Processes algorithm tasks
- **result-worker** - Processes results
- **file-write-worker** - Writes output files
- **rq-dashboard** - Job monitoring (port 9181)

### 4.3 View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f algorithm-service
docker-compose logs -f algorithm-worker
```

---

## Step 5: Verify Deployment

### 5.1 Health Check

```bash
curl http://localhost:8000/health
```

Expected response:
```json
{"status": "healthy"}
```

### 5.2 Access Dashboard

Open in browser: [http://localhost:9181](http://localhost:9181)

### 5.3 Check API Documentation

Open in browser: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## Step 6: Run Optimization

### 6.1 Preview Genome Combinations (Optional)

Before starting, preview how many genome combinations will be generated:

**PowerShell:**
```powershell
$body = @{
    use_google_sheets = $true
    sheet_id = "11a3m0AlIGsZ5O1HRVgjCP3zSCds-b_5OJGXmHKCP56U"
} | ConvertTo-Json

Invoke-WebRequest -Uri "http://localhost:8000/api/v1/preview-genomes" `
  -Method POST `
  -ContentType "application/json" `
  -Body $body `
  -UseBasicParsing | Select-Object -ExpandProperty Content
```

**Response:**
```json
{
  "total_combinations": 16,
  "variable_parameters": [
    {
      "name": "input_B1_upper_range",
      "values_count": 3
    },
    {
      "name": "input_B3_LR_lookback",
      "values_count": 5
    }
  ],
  "fixed_parameters_count": 31
}
```

### 6.2 Start Optimization with Google Sheets

**PowerShell:**
```powershell
$body = @{
    stock_codes = @("3888")
    use_google_sheets = $true
    sheet_id = "11a3m0AlIGsZ5O1HRVgjCP3zSCds-b_5OJGXmHKCP56U"
} | ConvertTo-Json

Invoke-WebRequest -Uri "http://localhost:8000/api/v1/run-optimization" `
  -Method POST `
  -ContentType "application/json" `
  -Body $body `
  -UseBasicParsing | Select-Object -ExpandProperty Content
```

**Response:**
```json
{
  "optimization_id": "opt_abc123def456",
  "total_genomes": 5,
  "total_tasks": 5,
  "stock_codes": ["3888"],
  "status": "pending",
  "message": "Optimization created and 5 tasks queued successfully"
}
```

**Save the `optimization_id` for checking status!**

### 6.3 Start Optimization with Manual Parameters

If you don't want to use Google Sheets:

**PowerShell:**
```powershell
$body = @{
    stock_codes = @("3888")
    parameter_ranges = @(
        @{
            Rule = "B1"
            "Parameter Variable" = "input_B1_upper_range"
            Base = 0.65
            Min = 0.55
            Max = 0.75
            Step = 0.1
            Change = $true
        },
        @{
            Rule = "B3"
            "Parameter Variable" = "input_B3_LR_lookback"
            Base = 58
            Min = 40
            Max = 80
            Step = 10
            Change = $true
        }
    )
} | ConvertTo-Json -Depth 5

Invoke-WebRequest -Uri "http://localhost:8000/api/v1/run-optimization" `
  -Method POST `
  -ContentType "application/json" `
  -Body $body `
  -UseBasicParsing | Select-Object -ExpandProperty Content
```

---

## Step 7: Monitor Optimization Progress

### 7.1 Check Optimization Status

Replace `opt_abc123def456` with your actual optimization ID:

**PowerShell:**
```powershell
$optId = "opt_abc123def456"
Invoke-WebRequest -Uri "http://localhost:8000/api/v1/optimization/$optId/status" `
  -UseBasicParsing | Select-Object -ExpandProperty Content | ConvertFrom-Json | ConvertTo-Json
```

**Response:**
```json
{
  "optimization_id": "opt_abc123def456",
  "status": "running",
  "total_tasks": 5,
  "completed_tasks": 3,
  "progress_percent": 60.0,
  "total_genomes": 5,
  "stock_codes": ["3888"],
  "created_at": "2026-02-05T15:30:00",
  "updated_at": "2026-02-05T15:35:00"
}
```

### 7.2 Watch Worker Logs in Real-Time

```powershell
# Watch algorithm worker processing
docker compose logs -f algorithm-worker

# Watch all workers
docker compose logs -f algorithm-worker result-worker file-write-worker
```

### 7.3 Check Queue Status

```powershell
Invoke-WebRequest -Uri "http://localhost:8000/api/v1/monitoring/queues" `
  -UseBasicParsing | Select-Object -ExpandProperty Content | ConvertFrom-Json | ConvertTo-Json -Depth 5
```

### 7.4 Check Worker Status

```powershell
Invoke-WebRequest -Uri "http://localhost:8000/api/v1/monitoring/workers" `
  -UseBasicParsing | Select-Object -ExpandProperty Content | ConvertFrom-Json | ConvertTo-Json -Depth 5
```

---

## Step 8: View Results

### 8.1 Get Results via API

When optimization completes, retrieve all results:

```powershell
$optId = "opt_abc123def456"
Invoke-WebRequest -Uri "http://localhost:8000/api/v1/optimization/$optId/results" `
  -UseBasicParsing | Select-Object -ExpandProperty Content | ConvertFrom-Json | ConvertTo-Json -Depth 5
```

### 8.2 View Results in Files

Results are automatically saved to CSV files in the `data/` folder:

**Result Files:**
```powershell
# List all optimization result files
Get-ChildItem data\optimization_*.csv

# View specific optimization summary
Get-Content data\optimization_opt_abc123def456_summary.csv | Select-Object -First 10
```

**File Locations:**
- `data/optimization_{optimization_id}_results.csv` - Individual trade results for each genome
- `data/optimization_{optimization_id}_summary.csv` - Aggregated genome comparison
- `data/results.csv` - Traditional (non-optimization) results

### 8.3 View Results in Google Sheets

If Google Sheets integration is configured, results are written to the **"Automated Results"** tab:

1. Open your Google Sheet
2. Go to the **"Automated Results"** tab
3. Results include:
   - Genome ID (G_000, G_001, G_002...)
   - Stock Code
   - Trade Count
   - Profit Delta (%) - compared to BASE genome
   - Win Rate Delta (%) - compared to BASE genome
   - All variable parameter values

**Result Format Example:**

| Genome ID | Stock Code | Trade Count | Profit Delta (%) | Win Rate Delta (%) | Total Win ($) | input_B1_upper_range | input_B3_LR_lookback |
|-----------|------------|-------------|------------------|-------------------|---------------|---------------------|---------------------|
| G_000 (BASE) | 3888 | 10 | 0.00 | 0.00 | 21580 | 0.65 | 58 |
| G_001 | 3888 | 9 | 15.89 | -5.56 | 20525 | 0.75 | 40 |
| G_002 | 3888 | 11 | -3.25 | 9.09 | 18930 | 0.55 | 80 |

### 8.4 Analyze Best Genome

**Find best performing genome:**
1. Look for highest **Profit Delta (%)** 
2. Check **Win Rate Delta (%)**
3. Compare **Payoff Ratio**
4. Verify **Trade Count** (ensure sufficient trades)

**Use best parameters:**
1. Note the parameter values from best genome
2. Update your Google Sheet with these as new BASE values
3. Run new optimization around these values

---

## Step 9: Traditional Algorithm Testing (Non-Optimization)

If you want to run the traditional algorithm with default parameters:

### 9.1 Prepare Stock List

Ensure `data/screener.csv` contains your stock codes:

```csv
Code
3888
2800
1234
```

### 9.2 Run Traditional Testing

```powershell
Invoke-WebRequest -Uri "http://localhost:8000/api/v1/start-testing/" `
  -UseBasicParsing | Select-Object -ExpandProperty Content | ConvertFrom-Json | ConvertTo-Json
```

**Response:**
```json
{
  "message": "Done: 10, Added to queue: 5",
  "done": ["3888", "2800"],
  "added": ["1234", "5678"],
  "status": "queued"
}
```

### 9.3 Monitor Traditional Testing

```powershell
# Check queue status
Invoke-WebRequest -Uri "http://localhost:8000/api/v1/monitoring/stats" `
  -UseBasicParsing | Select-Object -ExpandProperty Content | ConvertFrom-Json | ConvertTo-Json

# Watch logs
docker compose logs -f algorithm-worker
```

### 9.4 Generate Summary

After testing completes:

```powershell
Invoke-WebRequest -Uri "http://localhost:8000/api/v1/summary/" `
  -UseBasicParsing | Select-Object -ExpandProperty Content | ConvertFrom-Json | ConvertTo-Json
```

Results saved to:
- `data/results.csv`
- `data/general_results.csv`
- `data/summary.csv`

---

## Step 10: Troubleshooting

### 10.1 Service Not Starting

**Check container status:**
```powershell
docker compose ps
```

**View startup logs:**
```powershell
docker compose logs algorithm-service
docker compose logs algorithm-worker
```

**Common errors:**
- **ImportError**: Check requirements.txt dependencies installed
- **Connection refused**: Ensure Redis and MySQL containers are healthy
- **Port already in use**: Change port in docker-compose.yml

### 10.2 Tasks Not Processing

**Check queue has tasks:**
```powershell
docker compose exec redis redis-cli LLEN algorithm_calculation
```

**Check workers are running:**
```powershell
Invoke-WebRequest -Uri "http://localhost:8000/api/v1/monitoring/workers" `
  -UseBasicParsing | Select-Object -ExpandProperty Content
```

**Restart workers:**
```powershell
docker compose restart algorithm-worker result-worker file-write-worker
```

### 10.3 Google Sheets Issues

**Error: "Credentials file not found"**
```powershell
# Ensure credentials exist
Test-Path credentials\service_account.json
```

**Error: "Permission denied"**
- Share Google Sheet with service account email
- Check email in service_account.json: `client_email`
- Grant Editor permissions in Google Sheets

**Error: "Worksheet not found"**
- Check sheet has tabs: "Parameter Tuning" and "Automated Results"
- Verify sheet_id is correct

### 10.4 Database Connection Issues

**Check MySQL connection:**
```powershell
docker compose logs mysql
```

**Test database access:**
```powershell
docker compose exec mysql mysql -uuser -ppass -e "SHOW DATABASES;"
```

**Update .env if needed:**
```
DB_HOST=mysql
DB_PORT=3306
DB_USER=your_user
DB_PASSWORD=your_pass
DB_NAME=your_db
```

### 10.5 Optimization Not Starting

**Check API response:**
- Look for `optimization_id` in response
- Check `total_tasks` > 0
- Verify `status: "pending"`

**If total_tasks = 0:**
- No parameter ranges have `Change=true`
- Check Google Sheets "Parameter Tuning" tab
- At least one parameter must have Change=TRUE

**If optimization stalls:**
```powershell
# Check worker logs
docker compose logs algorithm-worker --tail 50

# Check queue status
Invoke-WebRequest -Uri "http://localhost:8000/api/v1/monitoring/queues" `
  -UseBasicParsing | Select-Object -ExpandProperty Content
```

### 10.6 Clear Redis Queue (Emergency Reset)

**WARNING: This deletes all queued tasks!**

```powershell
docker compose exec redis redis-cli FLUSHALL
docker compose restart algorithm-worker result-worker file-write-worker
```

### 10.7 View All Logs

```powershell
# All services
docker compose logs --tail 100

# Specific service with follow
docker compose logs -f algorithm-worker

# Save logs to file
docker compose logs > logs\docker-logs.txt
```

---

## Common Issues

### Issue: "gspread is required for Google Sheets integration"

**Solution:** Ensure `requirements.txt` includes:
```
gspread>=5.12.0
google-auth>=2.22.0
```

Rebuild images:
```bash
docker-compose build --no-cache
```

### Issue: "Credentials file not found"

**Solution:** Verify credentials placement:
```bash
ls -la credentials/
# Should show: google_sheets.json
```

### Issue: "Spreadsheet not found"

**Solution:** 
1. Verify sheet ID in `.env`
2. Ensure sheet is shared with service account email
3. Check service account permissions

### Issue: Redis connection refused

**Solution:** Ensure Redis is running:
```bash
docker-compose ps redis
docker-compose logs redis
```

### Issue: Database connection error

**Solution:** 
1. Verify `DB_*` environment variables
2. Ensure database is accessible from Docker network
3. Check firewall rules

---

## Stopping Services

```bash
# Stop all services
docker-compose down

# Stop and remove volumes
docker-compose down -v
```

---

## Development Mode

For local development without Docker:

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
.\venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export REDIS_HOST=localhost
export GOOGLE_SHEETS_CREDENTIALS_PATH=./credentials/google_sheets.json
# ... other variables

# Run API server
uvicorn app.main:app --reload --port 8000

# Run workers (in separate terminals)
python workers/start_algorithm_worker.py
python workers/start_result_worker.py
python workers/start_file_write_worker.py
```

---

## Architecture Overview

```
┌─────────────────┐     ┌──────────────────┐
│  Google Sheets  │────▶│ algorithm-service │
│   (Input)       │     │    (FastAPI)      │
└─────────────────┘     └────────┬──────────┘
                                 │
                                 ▼
                        ┌───────────────┐
                        │     Redis     │
                        │  (Queues)     │
                        └───────┬───────┘
                                │
         ┌──────────────────────┼──────────────────────┐
         ▼                      ▼                      ▼
┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐
│algorithm-worker │   │ result-worker   │   │file-write-worker│
│  (Buy/Sell)     │   │ (Aggregation)   │   │  (Output)       │
└─────────────────┘   └─────────────────┘   └─────────────────┘
                                │
                                ▼
                        ┌───────────────┐
                        │ Google Sheets │
                        │   (Output)    │
                        └───────────────┘
```

---

*For issues or questions, check the logs first:*
```bash
docker-compose logs -f 2>&1 | grep -i error
```
