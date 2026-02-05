# Dynamic Parameters Integration - Requirements

## Overview

Enable the trading algorithm to run with dynamically configurable parameters, iterate through parameter combinations (genomes), and output comparative results to identify best-performing configurations.

---

## 1. Parameter Models

### 1.1 Create `AlgorithmParameters` Dataclass

**Location:** `app/models/algorithm_models.py`

Define a dataclass containing all configurable parameters with base values as defaults:

| Rule | Parameter Variable | Base Value | Type |
|------|-------------------|------------|------|
| B1 | `input_B1_lookback` | 20 | int |
| B1 | `input_B1_bb_len` | 51 | int |
| B1 | `input_B1_bb_std` | 1.9 | float |
| B1 | `input_B1_ma_dev` | 0.25 | float |
| B1 | `input_B1_upper_range` | 0.65 | float |
| B3 | `input_B3_bbw_len` | 21 | int |
| B3 | `input_B3_sma_bbw` | 72 | int |
| B3 | `input_B3_LR_lookback` | 58 | int |
| B8 | `input_B8_recent_low` | 46 | int |
| B8 | `input_B8_past_low` | 270 | int |
| B9 | `input_B9_ma_len` | 50 | int |
| B10 | `input_B10_low_window` | 250 | int |
| B10 | `input_B10_prox_days` | 68 | int |
| B11 | `input_B11_atr_len` | 22 | int |
| B11 | `input_B11_history` | 126 | int |
| B11 | `input_B11_atr_threshold` | 0.87 | float |
| B12 | `input_B12_long_ma` | 150 | int |
| B12 | `input_B12_rise_pct` | 0.16 | float |
| B13 | `input_B13_rel_days` | 19 | int |
| B18 | `input_B18_bbw_len` | 21 | int |
| B18 | `input_B18_history` | 82 | int |
| B18 | `input_B18_bbw_ratio` | 0.22 | float |
| S1 | `input_S1_atr_mult` | 3.7 | float |
| S1 | `input_S1_hard_stop` | 9.5 | float |
| S4 | `input_S4_max_days` | 50 | int |
| S5 | `input_S5_step_days` | 25 | int |
| S5 | `input_S5_push_up_atr` | 0.62 | float |
| S9 | `input_S9_energy_thresh` | 0.22 | float |
| S10 | `input_S10_atr_ratio` | 2.6 | float |
| S10 | `input_S10_drawdown` | 0.05 | float |
| S11 | `input_S11_fib_level` | 0.382 | float |
| S12 | `input_S12_fib_level` | 0.236 | float |
| S15 | `input_S15_crash_drop` | 0.25 | float |

### 1.2 Create `ParameterRange` Model

**Location:** `app/models/algorithm_models.py`

Model for defining parameter optimization ranges:

```python
@dataclass
class ParameterRange:
    name: str           # e.g., "input_B1_upper_range"
    base: float
    min_val: float
    max_val: float
    step: float
    change: bool        # Whether to iterate this parameter
```

---

## 2. Genome Generator Service

### 2.1 Create `genome_service.py`

**Location:** `app/services/genome_service.py`

**Responsibilities:**
- Parse parameter ranges from input (Google Sheets or CSV)
- Generate all parameter combinations using `itertools.product`
- Assign unique `genome_id` (G_000 for BASE, G_001, G_002, etc.)
- Calculate total number of combinations

**Key Functions:**

| Function | Description |
|----------|-------------|
| `parse_parameter_ranges(data)` | Parse input data into `ParameterRange` objects |
| `generate_genomes(ranges)` | Generate all parameter combinations |
| `get_genome_by_id(genome_id)` | Retrieve specific genome parameters |
| `calculate_total_combinations(ranges)` | Return total genome count |

**Example Output:**
```python
{
    "genome_id": "G_001",
    "parameters": {
        "input_B1_upper_range": 0.75,
        "input_B3_LR_lookback": 40,
        "input_B11_atr_threshold": 0.80,
        ...
    }
}
```

---

## 3. Signal Functions Refactoring

### 3.1 Buy Signals (`app/workers/algo_func/buy_signals.py`)

Update functions to accept optional `params: AlgorithmParameters` argument:

| Function | Parameters to Inject |
|----------|---------------------|
| `checkB1()` | `input_B1_lookback`, `input_B1_bb_len`, `input_B1_bb_std`, `input_B1_ma_dev`, `input_B1_upper_range` |
| `checkB3()` | `input_B3_bbw_len`, `input_B3_sma_bbw`, `input_B3_LR_lookback` |
| `checkB8()` | `input_B8_recent_low`, `input_B8_past_low` |
| `checkB9()` | `input_B9_ma_len` |
| `checkB10()` | `input_B10_low_window`, `input_B10_prox_days` |
| `checkB11()` | `input_B11_atr_len`, `input_B11_history`, `input_B11_atr_threshold` |
| `checkB12()` | `input_B12_long_ma`, `input_B12_rise_pct` |
| `checkB13()` | `input_B13_rel_days` |
| `checkB18()` | `input_B18_bbw_len`, `input_B18_history`, `input_B18_bbw_ratio` |
| `calcS1Stop()` | `input_S1_atr_mult`, `input_S1_hard_stop` |
| `runAllBuyConditions()` | Pass `params` to all check functions |

### 3.2 Sell Signals (`app/workers/algo_func/sell_signals.py`)

| Function | Parameters to Inject |
|----------|---------------------|
| `s4()` | `input_S4_max_days` |
| `s5()` | `input_S5_step_days`, `input_S5_push_up_atr` |
| `s9()` | `input_S9_energy_thresh` |
| `s10()` | `input_S10_atr_ratio`, `input_S10_drawdown` |
| `s11()` | `input_S11_fib_level` |
| `s12()` | `input_S12_fib_level` |
| `s15()` | `input_S15_crash_drop` |
| `runAllSellConditions()` | Pass `params` to all sell functions |

---

## 4. Worker Pipeline Modifications

### 4.1 Algorithm Worker (`app/workers/algorithm_worker.py`)

**Changes:**
1. Accept `parameters` dict from queue task data
2. Create `AlgorithmParameters` instance from dict (or use defaults)
3. Pass parameters to `runAllBuyConditions()` and `runAllSellConditions()`
4. Include `genome_id` in result data passed to next queue

**Modified Task Data Structure:**
```python
task_data = {
    "task_id": str,
    "stock": str,
    "genome_id": str,           # NEW
    "parameters": dict,         # NEW
    "created_at": str
}
```

### 4.2 Result Worker (`app/workers/result_worker.py`)

**Changes:**
1. Include `genome_id` and parameter values in financial results
2. Calculate delta metrics vs BASE genome (G_000)
3. Write extended results to output

### 4.3 File Write Worker (`app/workers/file_write_worker.py`)

**Changes:**
1. Support new output format with genome columns
2. Aggregate results by `genome_id`

---

## 5. Google Sheets Integration

### 5.1 Create `sheets_service.py`

**Location:** `app/services/sheets_service.py`

**Dependencies:** Add to `requirements.txt`:
```
gspread>=5.12.0
oauth2client>=4.1.3
```

**Functions:**

| Function | Description |
|----------|-------------|
| `authenticate()` | OAuth2 authentication with Google API |
| `read_parameter_ranges(sheet_id, range)` | Read input parameters from sheet |
| `write_genome_results(sheet_id, data)` | Write results to output sheet |
| `get_or_create_output_sheet()` | Ensure output sheet exists |

### 5.2 Environment Configuration

Add to `.env` and `docker-compose.yml`:
```
GOOGLE_SHEETS_CREDENTIALS_PATH=/app/credentials/google_sheets.json
INPUT_SHEET_ID=<spreadsheet_id>
OUTPUT_SHEET_ID=<spreadsheet_id>
```

---

## 6. Orchestration Controller

### 6.1 New Endpoint

**Location:** `app/controllers/algorithm_controller.py`

**Endpoint:** `POST /api/v1/run-optimization`

**Request Body:**
```json
{
    "stock_codes": ["3888", "0001"],
    "use_google_sheets": true,
    "sheet_id": "optional_override"
}
```

**Response:**
```json
{
    "optimization_id": "opt_123",
    "total_genomes": 1800,
    "total_tasks": 3600,
    "status": "queued"
}
```

### 6.2 Progress Endpoint

**Endpoint:** `GET /api/v1/optimization/{optimization_id}/status`

**Response:**
```json
{
    "optimization_id": "opt_123",
    "status": "running",
    "completed_genomes": 450,
    "total_genomes": 1800,
    "progress_percent": 25.0
}
```

---

## 7. Output Format

### 7.1 Genome Results CSV/Sheet

**Columns (matching Output Results Sample.csv):**

| Column | Description |
|--------|-------------|
| `Genome ID` | Unique identifier (G_000, G_001, ...) |
| `Stock Code` | Stock symbol |
| `Trade Count` | Number of trades |
| `Profit Delta (%)` | % change vs BASE |
| `Win Rate Delta (%)` | % change vs BASE |
| `Total Win ($)` | Sum of winning trades |
| `Total Loss ($)` | Sum of losing trades |
| `Trades Win` | Count of winning trades |
| `Trades Loss` | Count of losing trades |
| `Avg Win ($)` | Average winning trade |
| `Avg Loss ($)` | Average losing trade |
| `Payoff Ratio` | Avg Win / Avg Loss |
| `input_B1_upper_range` | Parameter value |
| `input_B3_LR_lookback` | Parameter value |
| `input_B11_atr_threshold` | Parameter value |
| `input_B18_bbw_ratio` | Parameter value |
| `input_S1_atr_mult` | Parameter value |
| `input_S5_push_up_atr` | Parameter value |

---

## 8. File Structure Changes

```
app/
├── models/
│   └── algorithm_models.py     # Add AlgorithmParameters, ParameterRange
├── services/
│   ├── genome_service.py       # NEW - genome generation
│   └── sheets_service.py       # NEW - Google Sheets integration
├── controllers/
│   └── algorithm_controller.py # Add optimization endpoints
├── workers/
│   ├── algorithm_worker.py     # Modify to accept parameters
│   ├── result_worker.py        # Modify output format
│   └── algo_func/
│       ├── buy_signals.py      # Parameterize functions
│       └── sell_signals.py     # Parameterize functions
data/
├── genomes/                    # NEW - per-genome results
│   └── G_001_3888.csv
└── optimization_results.csv    # NEW - aggregated results
```

---

## 9. Docker Considerations

### 9.1 Volume Mounts

Add credentials volume in `docker-compose.yml`:
```yaml
volumes:
  - ./credentials:/app/credentials:ro
  - ./data:/app/data
```

### 9.2 Environment Variables

```yaml
environment:
  - GOOGLE_SHEETS_CREDENTIALS_PATH=/app/credentials/google_sheets.json
  - INPUT_SHEET_ID=${INPUT_SHEET_ID}
  - OUTPUT_SHEET_ID=${OUTPUT_SHEET_ID}
```

---

## 10. Implementation Order

1. **Phase 1 - Models & Core Logic**
   - [ ] Create `AlgorithmParameters` dataclass
   - [ ] Create `ParameterRange` model
   - [ ] Create `genome_service.py`

2. **Phase 2 - Signal Refactoring**
   - [ ] Update buy signal functions
   - [ ] Update sell signal functions
   - [ ] Update `runAllBuyConditions` / `runAllSellConditions`

3. **Phase 3 - Worker Pipeline**
   - [ ] Modify `algorithm_worker.py`
   - [ ] Modify `result_worker.py`
   - [ ] Modify `file_write_worker.py`

4. **Phase 4 - API & Orchestration**
   - [ ] Add optimization endpoints
   - [ ] Add progress tracking

5. **Phase 5 - Google Sheets Integration**
   - [ ] Create `sheets_service.py`
   - [ ] Configure OAuth credentials
   - [ ] Test read/write operations

6. **Phase 6 - Testing & Validation**
   - [ ] Unit tests for genome generation
   - [ ] Integration tests for full pipeline
   - [ ] Validate output format matches sample

---

## 11. Acceptance Criteria

- [ ] All parameters from Input Sample CSV are configurable
- [ ] Genome combinations generate correctly (product of all `Change=TRUE` parameters)
- [ ] BASE genome (G_000) uses default parameter values
- [ ] Output matches format in Output Results Sample.csv
- [ ] Delta calculations are relative to BASE genome
- [ ] Google Sheets read/write works correctly
- [ ] Docker deployment maintains functionality
- [ ] Existing tests continue to pass
