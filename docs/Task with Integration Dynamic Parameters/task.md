# Dynamic Parameters Integration - Implementation Tasks

## Phase 1: Models & Core Logic

### Task 1.1: Create AlgorithmParameters Dataclass
**File:** `app/models/algorithm_models.py`

**Status:** ✅ COMPLETED

**Steps:**
1. Add import for `dataclass` from `dataclasses`
2. Create `AlgorithmParameters` dataclass with all 33 parameters as fields with default values
3. Add `to_dict()` method for serialization
4. Add `from_dict(data: dict)` class method for deserialization

**Code Structure:**
```python
@dataclass
class AlgorithmParameters:
    # B1 parameters
    input_B1_lookback: int = 20
    input_B1_bb_len: int = 51
    input_B1_bb_std: float = 1.9
    input_B1_ma_dev: float = 0.25
    input_B1_upper_range: float = 0.65
    # ... all other parameters
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "AlgorithmParameters":
        return cls(**{k: v for k, v in data.items() if hasattr(cls, k)})
```

**Acceptance:** Unit test creates instance with defaults and custom values.

---

### Task 1.2: Create ParameterRange Model
**File:** `app/models/algorithm_models.py`

**Status:** ✅ COMPLETED

**Steps:**
1. Create `ParameterRange` dataclass
2. Add `generate_values()` method that returns list of values from min to max by step
3. Handle edge case where `change=False` returns only base value

**Code Structure:**
```python
@dataclass
class ParameterRange:
    name: str
    base: float
    min_val: float
    max_val: float
    step: float
    change: bool
    
    def generate_values(self) -> List[float]:
        if not self.change:
            return [self.base]
        values = []
        current = self.min_val
        while current <= self.max_val + 1e-9:  # float precision
            values.append(round(current, 6))
            current += self.step
        return values
```

**Acceptance:** `generate_values()` returns correct list for sample parameters.

---

### Task 1.3: Create Genome Service
**File:** `app/services/genome_service.py` (NEW)

**Status:** ✅ COMPLETED

**Steps:**
1. Create new file `app/services/genome_service.py`
2. Implement `parse_parameter_ranges(rows: List[dict]) -> List[ParameterRange]`
3. Implement `generate_genomes(ranges: List[ParameterRange], base_params: AlgorithmParameters) -> List[dict]`
4. Implement `calculate_total_combinations(ranges: List[ParameterRange]) -> int`
5. Implement `get_genome_by_id(genomes: List[dict], genome_id: str) -> dict`

**Key Logic:**
```python
def generate_genomes(ranges: List[ParameterRange], base_params: AlgorithmParameters) -> List[dict]:
    # 1. Separate variable params (change=True) from fixed params
    variable_ranges = [r for r in ranges if r.change]
    
    # 2. Generate all combinations using itertools.product
    value_lists = [r.generate_values() for r in variable_ranges]
    combinations = list(itertools.product(*value_lists))
    
    # 3. Create genome for each combination
    genomes = []
    
    # G_000 is always BASE
    base_genome = {
        "genome_id": "G_000",
        "parameters": base_params.to_dict()
    }
    genomes.append(base_genome)
    
    # G_001+ are variations
    for i, combo in enumerate(combinations):
        params = base_params.to_dict()
        for r, val in zip(variable_ranges, combo):
            params[r.name] = val
        genomes.append({
            "genome_id": f"G_{i+1:03d}",
            "parameters": params
        })
    
    return genomes
```

**Acceptance:** Given sample input CSV, generates 7200 combinations (3×5×5×4×6×4).

---

## Phase 2: Signal Functions Refactoring

### Task 2.1: Update Buy Signal Functions
**File:** `app/workers/algo_func/buy_signals.py`

**Status:** ✅ COMPLETED

**Steps for each function:**

#### 2.1.1 Update `checkB1()`
```python
# FROM:
def checkB1(ohlcv: List[OHLCV], targetDate) -> bool:
    # hardcoded: 20, 51, 1.9, 0.75

# TO:
def checkB1(ohlcv: List[OHLCV], targetDate, params: AlgorithmParameters = None) -> bool:
    if params is None:
        params = AlgorithmParameters()
    
    lookback = params.input_B1_lookback  # was 20
    bb_len = params.input_B1_bb_len      # was 51
    bb_std = params.input_B1_bb_std      # was 1.9
    upper_range = params.input_B1_upper_range  # was 0.75
```

#### 2.1.2 Update `checkB3()`
```python
# Replace hardcoded:
SMA_BBW_LEN = 72  # -> params.input_B3_sma_bbw
LR_LEN = 40       # -> params.input_B3_LR_lookback
# BB period 21    # -> params.input_B3_bbw_len
```

#### 2.1.3 Update `checkB8()`
```python
# Replace hardcoded:
recent46Low = min(lows[-46:])     # -> params.input_B8_recent_low
pastRange = lows[-270:-47]        # -> params.input_B8_past_low
```

#### 2.1.4 Update `checkB9()`
```python
# Replace hardcoded:
last50 = ohlcv[-50:]  # -> params.input_B9_ma_len
```

#### 2.1.5 Update `checkB10()`
```python
# Replace hardcoded:
last250 = ohlcv[-250:]           # -> params.input_B10_low_window
minLow not in lows[-68:]         # -> params.input_B10_prox_days
```

#### 2.1.6 Update `checkB11()`
```python
# Replace hardcoded:
atr = lewis_atr(..., 22)         # -> params.input_B11_atr_len
prev_window = atr[-127:-1]       # -> params.input_B11_history + 1
current > 0.8 * max_prev         # -> params.input_B11_atr_threshold
```

#### 2.1.7 Update `checkB12()` (already has some params)
```python
# Update signature to use AlgorithmParameters
def checkB12(ohlcv, params: AlgorithmParameters = None) -> bool:
    if params is None:
        params = AlgorithmParameters()
    # Use params.input_B12_long_ma, params.input_B12_rise_pct
```

#### 2.1.8 Update `checkB13()` (already has some params)
```python
# Update to use AlgorithmParameters
def checkB13(ohlcvStock, ohlcvIndex, params: AlgorithmParameters = None) -> bool:
    # Use params.input_B13_rel_days
```

#### 2.1.9 Update `checkB18()` and `condition8_b18()`
```python
# In condition8_b18:
input_BBW_len = 21   # -> params.input_B18_bbw_len
input_B18_Y = 82     # -> params.input_B18_history
input_B18_X = 15.0   # -> derived from params.input_B18_bbw_ratio
```

#### 2.1.10 Update `calcS1Stop()`
```python
# Replace hardcoded:
factor = 3.7         # -> params.input_S1_atr_mult
# Add hard stop logic with params.input_S1_hard_stop
```

#### 2.1.11 Update `runAllBuyConditions()`
```python
# FROM:
def runAllBuyConditions(ohlcv, targetDate, spyData):

# TO:
def runAllBuyConditions(ohlcv, targetDate, spyData, params: AlgorithmParameters = None):
    if params is None:
        params = AlgorithmParameters()
    
    return {
        'B1':  checkB1(ohlcv, targetDate, params),
        'B3':  checkB3(ohlcv, params),
        'B8':  checkB8(ohlcv, params),
        # ... pass params to all
        'stopLoss': calcS1Stop(ohlcv, params)
    }
```

**Acceptance:** All existing tests pass with default params.

---

### Task 2.2: Update Sell Signal Functions
**File:** `app/workers/algo_func/sell_signals.py`

**Status:** ✅ COMPLETED

**Steps:**

#### 2.2.1 Update `s4()`
```python
# Replace hardcoded:
day50_idx = buy_idx + 50    # -> params.input_S4_max_days
sma(closes, 150)            # -> use appropriate SMA
```

#### 2.2.2 Update `s5()`
```python
# Replace hardcoded:
days_since_buy == 45        # -> derived from params
step = 25                   # -> params.input_S5_step_days
atr_mult = 0.40             # -> params.input_S5_push_up_atr
```

#### 2.2.3 Update `s9()`
```python
# Replace hardcoded:
energy_thresh = 0.22        # -> params.input_S9_energy_thresh
```

#### 2.2.4 Update `s10()`
```python
# Replace hardcoded:
atr_ratio = 2.6             # -> params.input_S10_atr_ratio
drawdown = 0.05             # -> params.input_S10_drawdown
```

#### 2.2.5 Update `s11()`
```python
# Replace hardcoded:
level = 0.382               # -> params.input_S11_fib_level
```

#### 2.2.6 Update `s12()`
```python
# Replace hardcoded:
level = 0.236               # -> params.input_S12_fib_level
```

#### 2.2.7 Update `s15()`
```python
# Replace hardcoded:
crash_drop = -0.25          # -> params.input_S15_crash_drop
```

#### 2.2.8 Update `runAllSellConditions()`
```python
# FROM:
def runAllSellConditions(ohlcv, spy_data, buy_date, buy_price, stop_loss, trade_date):

# TO:
def runAllSellConditions(ohlcv, spy_data, buy_date, buy_price, stop_loss, trade_date, 
                          params: AlgorithmParameters = None):
    if params is None:
        params = AlgorithmParameters()
    # Pass params to all sell functions
```

**Acceptance:** All existing tests pass with default params.

---

## Phase 3: Worker Pipeline Modifications

### Task 3.1: Update Algorithm Worker
**File:** `app/workers/algorithm_worker.py`

**Status:** ✅ COMPLETED

**Steps:**

1. Add import for `AlgorithmParameters`
```python
from app.models.algorithm_models import AlgorithmParameters
```

2. Update `process_algorithm_task()` to extract parameters:
```python
async def process_algorithm_task(task_data):
    stock_code = task_data['stock']
    genome_id = task_data.get('genome_id', 'G_000')
    params_dict = task_data.get('parameters', {})
    params = AlgorithmParameters.from_dict(params_dict)
    
    # Pass params through the pipeline
    await signals_for_the_period(stock_code, END_DATE, params, genome_id)
```

3. Update `signals_for_the_period()` signature:
```python
async def signals_for_the_period(code, trade_date, params: AlgorithmParameters = None, 
                                  genome_id: str = "G_000"):
```

4. Update calls to `runAllBuyConditions` and `runAllSellConditions`:
```python
buySignals = runAllBuyConditions(filtered_code, tradeday_str, filtered_spy, params)
sellSignals = runAllSellConditions(..., params)
```

5. Include `genome_id` in result queue data:
```python
QueueService.add_to_result_processing_queue(stock_code, genome_id=genome_id, 
                                             parameters=params.to_dict())
```

**Acceptance:** Worker processes task with custom parameters.

---

### Task 3.2: Update Result Worker
**File:** `app/workers/result_worker.py`

**Status:** ✅ COMPLETED

**Steps:**

1. Accept `genome_id` and `parameters` from queue
2. Include in output CSV columns
3. Calculate delta vs BASE (if available)
4. Update optimization progress tracking

**Acceptance:** Output includes genome_id and parameter columns.

---

### Task 3.3: Update File Write Worker
**File:** `app/workers/file_write_worker.py`

**Status:** ✅ COMPLETED

**Steps:**

1. Update fieldnames to include genome columns
2. Create separate output file for optimization results: `data/optimization_results.csv`
3. Support optimization-specific output files

**Acceptance:** Results written with all required columns.

---

### Task 3.4: Update Queue Service
**File:** `app/services/queue_service.py`

**Status:** ✅ COMPLETED

**Steps:**

1. Update `add_to_algorithm_queue()` to accept `genome_id` and `parameters`:
```python
@staticmethod
def add_to_algorithm_queue(stock_code: str, genome_id: str = "G_000", 
                           parameters: dict = None) -> str:
    task_data = {
        "task_id": str(uuid.uuid4()),
        "stock": stock_code,
        "genome_id": genome_id,
        "parameters": parameters or {},
        "created_at": datetime.now().isoformat(),
    }
```

2. Update `add_to_result_processing_queue()` similarly

**Acceptance:** Queue tasks include genome data.

---

## Phase 4: API & Orchestration

### Task 4.1: Add Optimization Endpoints
**File:** `app/controllers/optimization_controller.py`

**Status:** ✅ COMPLETED

**Steps:**

1. Add new endpoint `POST /api/v1/run-optimization`:
```python
@router.post("/run-optimization")
async def run_optimization(request: OptimizationRequest):
    # 1. Read parameter ranges (from request or Google Sheets)
    # 2. Generate all genomes
    # 3. For each stock × genome combination, add to queue
    # 4. Store optimization_id with metadata
    # 5. Return optimization_id and counts
```

2. Add progress endpoint `GET /api/v1/optimization/{optimization_id}/status`

3. Create request/response models:
```python
class OptimizationRequest(BaseModel):
    stock_codes: List[str]
    parameter_ranges: Optional[List[dict]] = None
    use_google_sheets: bool = False
    sheet_id: Optional[str] = None

class OptimizationResponse(BaseModel):
    optimization_id: str
    total_genomes: int
    total_tasks: int
    status: str
```

**Acceptance:** Endpoint queues all genome combinations.

---

### Task 4.2: Add Progress Tracking
**File:** `app/services/optimization_service.py` (NEW)

**Status:** ✅ COMPLETED

**Steps:**

1. Create service to track optimization progress
2. Store in Redis or file:
   - `optimization_id`
   - `total_tasks`
   - `completed_tasks`
   - `status` (queued, running, completed, failed)
3. Update workers to increment `completed_tasks`

**Acceptance:** Progress endpoint returns accurate counts.

---

## Phase 5: Google Sheets Integration

### Task 5.1: Add Dependencies
**File:** `requirements.txt`

**Status:** ✅ COMPLETED

**Steps:**
Add:
```
gspread>=5.12.0
google-auth>=2.22.0
google-auth-oauthlib>=1.0.0
```

---

### Task 5.2: Create Sheets Service
**File:** `app/services/sheets_service.py` (NEW)

**Status:** ✅ COMPLETED

**Steps:**

1. Implement authentication:
```python
def authenticate():
    creds_path = os.getenv("GOOGLE_SHEETS_CREDENTIALS_PATH")
    gc = gspread.service_account(filename=creds_path)
    return gc
```

2. Implement read function:
```python
def read_parameter_ranges(sheet_id: str, worksheet_name: str = "Parameter Tuning") -> List[dict]:
    gc = authenticate()
    sheet = gc.open_by_key(sheet_id)
    worksheet = sheet.worksheet(worksheet_name)
    return worksheet.get_all_records()
```

3. Implement write function:
```python
def write_genome_results(sheet_id: str, data: List[dict], worksheet_name: str = "Automated Results"):
    gc = authenticate()
    sheet = gc.open_by_key(sheet_id)
    try:
        worksheet = sheet.worksheet(worksheet_name)
    except:
        worksheet = sheet.add_worksheet(worksheet_name, rows=1000, cols=20)
    
    # Write headers + data
    if data:
        headers = list(data[0].keys())
        worksheet.update('A1', [headers])
        rows = [[row.get(h, '') for h in headers] for row in data]
        worksheet.update('A2', rows)
```

**Note:** Input and output use the same Google Sheet (configured via `INPUT_SHEET_ID` / `OUTPUT_SHEET_ID`) but different tabs:
- **Input tab:** `Parameter Tuning` - contains parameter ranges
- **Output tab:** `Automated Results` - genome optimization results

**Acceptance:** Read from sample sheet, write results back.

---

### Task 5.3: Update Docker Configuration
**File:** `docker-compose.yml`

**Status:** ✅ COMPLETED

**Steps:**

1. Add volume for credentials:
```yaml
volumes:
  - ./credentials:/app/credentials:ro
```

2. Add environment variables:
```yaml
environment:
  - GOOGLE_SHEETS_CREDENTIALS_PATH=/app/credentials/google_sheets.json
  - INPUT_SHEET_ID=${INPUT_SHEET_ID}
  - OUTPUT_SHEET_ID=${OUTPUT_SHEET_ID}
```

**Acceptance:** Container can access credentials.

---

## Phase 6: Testing & Validation

### Task 6.1: Unit Tests for Genome Service
**File:** `tests/test_genome_service.py` (NEW)

**Status:** ✅ COMPLETED

**Test Cases:**
- `test_parse_parameter_ranges()` - parses CSV correctly
- `test_generate_values_with_change()` - generates range values
- `test_generate_values_without_change()` - returns only base
- `test_generate_genomes_count()` - correct number of combinations
- `test_genome_base_is_g000()` - G_000 has base values

---

### Task 6.2: Integration Tests
**File:** `tests/test_optimization_flow.py` (NEW)

**Status:** ⚠️ IN PROGRESS

**Test Cases:**
- `test_optimization_endpoint_queues_tasks()`
- `test_worker_processes_with_params()`
- `test_output_format_matches_sample()`

---

### Task 6.3: Validate Existing Tests
**Steps:**
1. Run all existing tests in `tests/algo_func/`
2. Fix any failures caused by signature changes
3. Update test calls to pass `params=None` or default params

---

## Summary Checklist

### Phase 1 - Models & Core Logic
- [x] 1.1 Create `AlgorithmParameters` dataclass
- [x] 1.2 Create `ParameterRange` model
- [x] 1.3 Create `genome_service.py`

### Phase 2 - Signal Refactoring
- [x] 2.1.1 Update `checkB1()`
- [x] 2.1.2 Update `checkB3()`
- [x] 2.1.3 Update `checkB8()`
- [x] 2.1.4 Update `checkB9()`
- [x] 2.1.5 Update `checkB10()`
- [x] 2.1.6 Update `checkB11()`
- [x] 2.1.7 Update `checkB12()`
- [x] 2.1.8 Update `checkB13()`
- [x] 2.1.9 Update `checkB18()` and `condition8_b18()`
- [x] 2.1.10 Update `calcS1Stop()`
- [x] 2.1.11 Update `runAllBuyConditions()`
- [x] 2.2.1 Update `s4()`
- [x] 2.2.2 Update `s5()`
- [x] 2.2.3 Update `s9()`
- [x] 2.2.4 Update `s10()`
- [x] 2.2.5 Update `s11()`
- [x] 2.2.6 Update `s12()`
- [x] 2.2.7 Update `s15()`
- [x] 2.2.8 Update `runAllSellConditions()`

### Phase 3 - Worker Pipeline
- [x] 3.1 Update `algorithm_worker.py`
- [x] 3.2 Update `result_worker.py`
- [x] 3.3 Update `file_write_worker.py`
- [x] 3.4 Update `queue_service.py`

### Phase 4 - API & Orchestration
- [x] 4.1 Add optimization endpoints
- [x] 4.2 Add progress tracking service

### Phase 5 - Google Sheets
- [x] 5.1 Add dependencies to `requirements.txt`
- [x] 5.2 Create `sheets_service.py`
- [x] 5.3 Update Docker configuration

### Phase 6 - Testing
- [x] 6.1 Unit tests for genome service
- [ ] 6.2 Integration tests
- [ ] 6.3 Validate existing tests pass

---

## Remaining Work

### Integration Tests (Task 6.2)
Create `tests/test_optimization_flow.py` with:
- `test_optimization_endpoint_queues_tasks()`
- `test_worker_processes_with_params()`
- `test_output_format_matches_sample()`

### Validate Existing Tests (Task 6.3)
1. Run all existing tests in `tests/algo_func/`
2. Fix any failures caused by signature changes
3. Update test calls to pass `params=None` or default params

---

## Estimated Effort

| Phase | Tasks | Estimated Hours |
|-------|-------|-----------------|
| Phase 1 | 3 | 4-6 |
| Phase 2 | 19 | 8-12 |
| Phase 3 | 4 | 4-6 |
| Phase 4 | 2 | 3-4 |
| Phase 5 | 3 | 3-4 |
| Phase 6 | 3 | 4-6 |
| **Total** | **34** | **26-38** |
