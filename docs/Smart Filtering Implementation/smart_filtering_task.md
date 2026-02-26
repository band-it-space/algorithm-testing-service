# Smart Filtering — Step-by-Step Implementation Task

> **Reference:** `docs/Smart Filtering Implementation/smart_filtering_requirements.md`
> **Scope:** 2 new files, 6 modified files, 4 new env vars

---

## Step 1: Add Environment Variables

### 1.1 Update `.env.example`

Add a new section at the end of the file:

```dotenv
# =================================
# Smart Filtering Configuration
# =================================
SMART_FILTERING_ENABLED=true
MIN_PAYOFF_RATIO=2
OUT_PAYOFF_RATIO=1
MIN_OBSERVATIONS=2
```

### 1.2 Update `.env`

Add the same 4 variables to the local `.env` file.

### 1.3 Update `docker-compose.yml`

Pass the smart filtering env vars to services that need them:

**`algorithm-worker` service** — add under `environment:`:
```yaml
- SMART_FILTERING_ENABLED=${SMART_FILTERING_ENABLED:-true}
- MIN_PAYOFF_RATIO=${MIN_PAYOFF_RATIO:-2}
- OUT_PAYOFF_RATIO=${OUT_PAYOFF_RATIO:-1}
- MIN_OBSERVATIONS=${MIN_OBSERVATIONS:-2}
```

**`result-worker` service** — add under `environment:`:
```yaml
- SMART_FILTERING_ENABLED=${SMART_FILTERING_ENABLED:-true}
- MIN_PAYOFF_RATIO=${MIN_PAYOFF_RATIO:-2}
- OUT_PAYOFF_RATIO=${OUT_PAYOFF_RATIO:-1}
- MIN_OBSERVATIONS=${MIN_OBSERVATIONS:-2}
```

---

## Step 2: Create `app/config/smart_filtering_config.py` ✅

New file. Loads all smart filtering env vars with defaults.

```python
import os


SMART_FILTERING_ENABLED = os.getenv('SMART_FILTERING_ENABLED', 'true').lower() == 'true'
MIN_PAYOFF_RATIO = float(os.getenv('MIN_PAYOFF_RATIO', '2'))
OUT_PAYOFF_RATIO = float(os.getenv('OUT_PAYOFF_RATIO', '1'))
MIN_OBSERVATIONS = int(os.getenv('MIN_OBSERVATIONS', '2'))
```

**No classes, no functions** — just module-level constants read at import time. Other modules import these directly:
```python
from app.config.smart_filtering_config import SMART_FILTERING_ENABLED, MIN_PAYOFF_RATIO
```

---

## Step 3: Create `app/services/smart_filtering_service.py` ✅

New file. This is the core filtering logic. All state lives in Redis (shared between workers).

### 3.1 Redis Key Patterns

```python
GENOMES_KEY      = "smart_filter:genomes:{opt_id}"       # STRING (JSON) — genome→params mapping
STATS_KEY        = "smart_filter:stats:{opt_id}"          # HASH — field: "param:value", value: JSON list of avg PRs
CLEARED_KEY      = "smart_filter:cleared:{opt_id}"        # SET — cleared "param:value" strings
SKIP_LIST_KEY    = "smart_filter:skip_list:{opt_id}"      # SET — genome_ids to skip
SKIP_INCR_KEY    = "smart_filter:skip_incremented:{opt_id}" # SET — genome_ids already counter-incremented
ELIMINATED_KEY   = "smart_filter:eliminated:{opt_id}"     # HASH — field: "param:value", value: JSON evidence
```

### 3.2 Class Structure

```python
class SmartFilteringService:
    """Redis-backed smart filtering for genome optimization."""

    @staticmethod
    def get_redis_client() -> redis.Redis:
        # Reuse QueueService.get_redis_client()

    # --- Setup ---

    @classmethod
    def store_genome_params(cls, optimization_id, genomes, variable_param_names):
        """
        Called once during optimization creation.
        Stores {genome_id: {param: value, ...}} for all genomes (variable params only).
        
        Args:
            optimization_id: str
            genomes: list of dicts [{"genome_id": "G_001", "parameters": {...}}, ...]
            variable_param_names: list of str — names of params with change=True
        """
        # Build mapping: {genome_id: {param_name: param_value}} for variable params only
        # Store as JSON string in Redis key smart_filter:genomes:{opt_id}

    # --- Skip Check (called by algorithm worker) ---

    @classmethod
    def is_genome_skipped(cls, optimization_id, genome_id) -> bool:
        """O(1) check — SISMEMBER on skip_list SET."""

    @classmethod
    def mark_skip_incremented(cls, optimization_id, genome_id) -> bool:
        """
        Atomically mark genome as counter-incremented. Returns True if newly added
        (first call), False if already existed (duplicate).
        Uses SADD — returns 1 if new, 0 if already member.
        """

    # --- Result Recording (called by result worker after cross-stock averaging) ---

    @classmethod
    def record_genome_result(cls, optimization_id, genome_id, avg_payoff_ratio, param_values):
        """
        Record averaged Payoff Ratio for a completed genome.
        
        For each (param, value) in param_values:
            1. Append avg_payoff_ratio to stats hash
            2. If avg_payoff_ratio >= MIN_PAYOFF_RATIO → add "param:value" to cleared SET
        
        Args:
            optimization_id: str
            genome_id: str
            avg_payoff_ratio: float
            param_values: dict {param_name: param_value}
        """

    # --- Toxic Parameter Identification (called after record_genome_result) ---

    @classmethod
    def check_and_eliminate(cls, optimization_id, genome_id, avg_payoff_ratio, param_values):
        """
        Check if any parameter value should be eliminated.
        
        Two paths:
        
        1. OUT_PAYOFF_RATIO instant kill (process-of-elimination):
           - If avg_payoff_ratio < OUT_PAYOFF_RATIO:
             - Find non-cleared params in this genome
             - If exactly ONE non-cleared → eliminate immediately
        
        2. Gradual elimination (MIN_PAYOFF_RATIO + MIN_OBSERVATIONS):
           - For each (param, value) in stats:
             - Skip if cleared
             - If count >= MIN_OBSERVATIONS AND all observations < MIN_PAYOFF_RATIO → eliminate
           - If multiple candidates → eliminate the one with most observations
        
        On elimination:
           - Call _eliminate_param_value(optimization_id, param, value, evidence)
        
        Args:
            optimization_id: str
            genome_id: str — the genome that triggered this check
            avg_payoff_ratio: float
            param_values: dict {param_name: param_value}
        
        Returns:
            list of eliminated (param, value) tuples (usually 0 or 1)
        """

    @classmethod
    def _eliminate_param_value(cls, optimization_id, param_name, param_value, evidence):
        """
        Eliminate a toxic parameter value:
        1. Load genome-params mapping from Redis
        2. Find all genome_ids containing this (param, value)
        3. Add them all to skip_list SET
        4. Store evidence in eliminated HASH
        5. Log the elimination event
        
        Args:
            optimization_id: str
            param_name: str — e.g. "input_S5_push_up_atr"
            param_value: float — e.g. 0.9
            evidence: dict — {observations: [...], genome_id: str, ...}
        """

    # --- Monitoring ---

    @classmethod
    def get_filtering_summary(cls, optimization_id):
        """
        Return summary dict for progress API:
        {
            "enabled": True,
            "genomes_skipped": int,
            "eliminated_params": [
                {"param": str, "value": float, "after_genome": str, "observations": int},
                ...
            ]
        }
        """
```

### 3.3 Implementation Notes

- **All Redis operations must handle `bytes` responses** — the Redis client uses `decode_responses=False`.
- **`_eliminate_param_value` must be idempotent** — if called twice for the same param-value, the second call should be a no-op (SADD is naturally idempotent).
- **Float comparison:** Use string representation for Redis keys to avoid floating-point issues. Store param values as `str(round(value, 6))` in the key format `"param_name:value_str"`.
- **Thread safety:** Redis operations are atomic. Multiple result workers calling `record_genome_result` concurrently is safe because:
  - Stats updates use `HGET` + `HSET` (last-writer-wins on the stats list, but since each genome_id is unique, records are appended correctly)
  - Consider using a Lua script for atomic read-modify-write on stats if race conditions are a concern
- **G_000 (BASE) genome should be recorded but never trigger elimination** — it sets the baseline.

---

## Step 4: Modify `app/models/algorithm_models.py`

### 4.1 Make `get_variable_params_for_output()` accept dynamic param list

**Current code:**
```python
def get_variable_params_for_output(self) -> Dict[str, Any]:
    return {
        "input_B1_upper_range": self.input_B1_upper_range,
        "input_B3_LR_lookback": self.input_B3_LR_lookback,
        "input_B11_atr_threshold": self.input_B11_atr_threshold,
        "input_B18_bbw_ratio": self.input_B18_bbw_ratio,
        "input_S1_atr_mult": self.input_S1_atr_mult,
        "input_S5_push_up_atr": self.input_S5_push_up_atr,
    }
```

**New code:**
```python
def get_variable_params_for_output(self, variable_param_names: Optional[List[str]] = None) -> Dict[str, Any]:
    if variable_param_names:
        params_dict = self.to_dict()
        return {name: params_dict[name] for name in variable_param_names if name in params_dict}
    # Fallback to hardcoded defaults for backward compatibility
    return {
        "input_B1_upper_range": self.input_B1_upper_range,
        "input_B3_LR_lookback": self.input_B3_LR_lookback,
        "input_B11_atr_threshold": self.input_B11_atr_threshold,
        "input_B18_bbw_ratio": self.input_B18_bbw_ratio,
        "input_S1_atr_mult": self.input_S1_atr_mult,
        "input_S5_push_up_atr": self.input_S5_push_up_atr,
    }
```

### 4.2 Add `variable_param_names` to `OptimizationMetadata`

In `app/services/optimization_service.py`, modify `OptimizationMetadata`:

**Add field:**
```python
variable_param_names: Optional[List[str]] = None
```

**Update `from_dict()`** to handle the new optional field:
```python
@classmethod
def from_dict(cls, data: Dict[str, Any]) -> "OptimizationMetadata":
    if 'sheet_id' not in data:
        data['sheet_id'] = None
    if 'variable_param_names' not in data:
        data['variable_param_names'] = None
    return cls(**data)
```

---

## Step 5: Modify `app/services/results_aggregation_service.py`

### 5.1 Add per-genome output fieldnames (no params, with Stock Code)

```python
def get_per_genome_output_fieldnames() -> List[str]:
    """Fieldnames for 'Automated Results Per Genome.csv' — per-stock, no param columns."""
    return [
        "Genome ID",
        "Stock Code",
        "Trade Count",
        "Profit Delta (%)",
        "Win Rate Delta (%)",
        "Total Win ($)",
        "Total Loss ($)",
        "Trades Win",
        "Trades Loss",
        "Avg Win ($)",
        "Avg Loss ($)",
        "Payoff Ratio",
    ]
```

### 5.2 Add averaged output fieldnames (with params, no Stock Code)

```python
def get_averaged_output_fieldnames(variable_param_names: Optional[List[str]] = None) -> List[str]:
    """Fieldnames for 'Automated Results.csv' — averaged across stocks, with param columns."""
    base_fields = [
        "Genome ID",
        "Trade Count",
        "Profit Delta (%)",
        "Win Rate Delta (%)",
        "Total Win ($)",
        "Total Loss ($)",
        "Trades Win",
        "Trades Loss",
        "Avg Win ($)",
        "Avg Loss ($)",
        "Payoff Ratio",
    ]
    if variable_param_names:
        return base_fields + variable_param_names
    # Fallback to hardcoded defaults
    return base_fields + [
        "input_B1_upper_range",
        "input_B3_LR_lookback",
        "input_B11_atr_threshold",
        "input_B18_bbw_ratio",
        "input_S1_atr_mult",
        "input_S5_push_up_atr",
    ]
```

### 5.3 Add `compute_averaged_metrics()`

```python
def compute_averaged_metrics(
    per_stock_results: List[Dict[str, Any]],
    genome_id: str,
    parameters: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Average per-stock result dicts into one averaged result dict.
    
    Method: mean of raw totals, then derive ratios.
    
    Args:
        per_stock_results: list of output_row dicts (one per stock_code)
        genome_id: str
        parameters: dict of variable param values
    
    Returns:
        dict matching averaged output format (no Stock Code)
    """
    n = len(per_stock_results)
    if n == 0:
        return {}

    avg_trade_count = sum(float(r.get("Trade Count", 0)) for r in per_stock_results) / n
    avg_total_win = sum(float(r.get("Total Win ($)", 0)) for r in per_stock_results) / n
    avg_total_loss = sum(float(r.get("Total Loss ($)", 0)) for r in per_stock_results) / n
    avg_trades_win = sum(float(r.get("Trades Win", 0)) for r in per_stock_results) / n
    avg_trades_loss = sum(float(r.get("Trades Loss", 0)) for r in per_stock_results) / n

    avg_win = avg_total_win / avg_trades_win if avg_trades_win > 0 else 0.0
    avg_loss = avg_total_loss / avg_trades_loss if avg_trades_loss > 0 else 0.0
    payoff_ratio = avg_win / avg_loss if avg_loss > 0 else 0.0

    row = {
        "Genome ID": genome_id,
        "Trade Count": round(avg_trade_count, 2),
        "Profit Delta (%)": 0,    # Calculated later vs averaged BASE
        "Win Rate Delta (%)": 0,  # Calculated later vs averaged BASE
        "Total Win ($)": round(avg_total_win, 2),
        "Total Loss ($)": round(avg_total_loss, 2),
        "Trades Win": round(avg_trades_win, 2),
        "Trades Loss": round(avg_trades_loss, 2),
        "Avg Win ($)": round(avg_win, 2),
        "Avg Loss ($)": round(avg_loss, 2),
        "Payoff Ratio": round(payoff_ratio, 2),
    }

    # Add parameter values
    for key, value in parameters.items():
        row[key] = value

    return row
```

### 5.4 Add `calculate_averaged_deltas()`

```python
def calculate_averaged_deltas(result: Dict[str, Any], base: Dict[str, Any]) -> Dict[str, Any]:
    """Calculate Profit Delta and Win Rate Delta vs averaged BASE."""
    base_profit = float(base.get("Total Win ($)", 0)) - float(base.get("Total Loss ($)", 0))
    genome_profit = float(result.get("Total Win ($)", 0)) - float(result.get("Total Loss ($)", 0))

    if result.get("Genome ID") == "G_000":
        result["Profit Delta (%)"] = 0.0
        result["Win Rate Delta (%)"] = 0.0
        return result

    if base_profit != 0:
        result["Profit Delta (%)"] = round(((genome_profit - base_profit) / abs(base_profit)) * 100, 2)
    else:
        result["Profit Delta (%)"] = 0.0

    base_trades_win = float(base.get("Trades Win", 0))
    base_trade_count = float(base.get("Trade Count", 0))
    genome_trades_win = float(result.get("Trades Win", 0))
    genome_trade_count = float(result.get("Trade Count", 0))

    base_win_rate = (base_trades_win / base_trade_count * 100) if base_trade_count > 0 else 0.0
    genome_win_rate = (genome_trades_win / genome_trade_count * 100) if genome_trade_count > 0 else 0.0

    result["Win Rate Delta (%)"] = round(genome_win_rate - base_win_rate, 2)
    return result
```

---

## Step 6: Modify `app/services/optimization_service.py`

### 6.1 Store genome-param mapping and variable param names during optimization creation

In `create_optimization()`, **after** `genomes = generate_genomes(ranges, base_params)`:

```python
# Extract variable param names (params with change=True)
variable_param_names = [r.name for r in ranges if r.change]

# Store in metadata
metadata = OptimizationMetadata(
    ...
    variable_param_names=variable_param_names,  # NEW field
)

# Store genome-param mapping for smart filtering
from app.config.smart_filtering_config import SMART_FILTERING_ENABLED
if SMART_FILTERING_ENABLED:
    from app.services.smart_filtering_service import SmartFilteringService
    SmartFilteringService.store_genome_params(optimization_id, genomes, variable_param_names)
```

### 6.2 Clear "Automated Results Per Genome.csv" alongside "Automated Results.csv"

In `_clear_results_file()`, also clear the new per-genome file:

```python
@classmethod
def _clear_results_file(cls) -> None:
    for filename in [AUTOMATED_RESULTS_FILE, "Automated Results Per Genome.csv"]:
        results_path = os.path.join(DATA_DIR, filename)
        try:
            if os.path.exists(results_path):
                os.remove(results_path)
                logger.info(f"Cleared previous results file: {results_path}")
        except Exception as e:
            logger.warning(f"Could not clear results file {filename}: {e}")
```

### 6.3 Store averaged results in separate Redis hash

Add new class-level constant and methods:

```python
OPTIMIZATION_AVG_RESULTS_PREFIX = "optimization_avg_results:"
GENOME_DONE_PREFIX = "genome_done:"

@classmethod
def store_averaged_result(cls, optimization_id, genome_id, result):
    """Store averaged result for a genome."""
    client = cls.get_redis_client()
    key = f"{cls.OPTIMIZATION_AVG_RESULTS_PREFIX}{optimization_id}"
    client.hset(key, genome_id, json.dumps(result))

@classmethod
def get_averaged_results(cls, optimization_id):
    """Get all averaged results for an optimization."""
    client = cls.get_redis_client()
    key = f"{cls.OPTIMIZATION_AVG_RESULTS_PREFIX}{optimization_id}"
    raw = client.hgetall(key)
    results = {}
    for field, value in raw.items():
        field_str = field.decode() if isinstance(field, bytes) else field
        results[field_str] = json.loads(value)
    return results

@classmethod
def increment_genome_stock_done(cls, optimization_id, genome_id):
    """Atomically increment per-genome stock counter. Returns new count."""
    client = cls.get_redis_client()
    key = f"{cls.GENOME_DONE_PREFIX}{optimization_id}"
    return client.hincrby(key, genome_id, 1)
```

### 6.4 Update `_write_results_to_sheets()` to use averaged results

Replace the body of `_write_results_to_sheets()`:

```python
@classmethod
def _write_results_to_sheets(cls, optimization_id, metadata):
    if not metadata.sheet_id:
        logger.info(f"No sheet_id for {optimization_id}, skipping Sheets write")
        return False
    try:
        from app.services.sheets_service import SheetsService
        from app.services.results_aggregation_service import get_averaged_output_fieldnames

        # Use averaged results instead of per-stock results
        results = cls.get_averaged_results(optimization_id)
        if not results:
            logger.warning(f"No averaged results for {optimization_id}")
            return False

        variable_param_names = metadata.variable_param_names
        fieldnames = get_averaged_output_fieldnames(variable_param_names)

        output_data = []
        for genome_id, result in results.items():
            if not isinstance(result, dict):
                continue
            clean_row = {}
            for field in fieldnames:
                clean_row[field] = result.get(field, '')
            if clean_row.get('Genome ID') == 'G_000':
                clean_row['Genome ID'] = 'G_000 (BASE)'
            output_data.append(clean_row)

        if not output_data:
            logger.warning(f"No formatted averaged results for {optimization_id}")
            return False

        output_data.sort(key=lambda x: x.get('Genome ID', ''))

        success = SheetsService.write_genome_results(
            sheet_id=metadata.sheet_id,
            data=output_data,
            worksheet_name="Automated Results",
            fieldnames=fieldnames
        )

        if success:
            logger.info(f"Wrote {len(output_data)} averaged results to Sheets for {optimization_id}")

            # Log smart filtering summary
            if SMART_FILTERING_ENABLED:
                from app.services.smart_filtering_service import SmartFilteringService
                summary = SmartFilteringService.get_filtering_summary(optimization_id)
                if summary.get("eliminated_params"):
                    logger.info(
                        f"SMART FILTER SUMMARY for {optimization_id}: "
                        f"Skipped {summary['genomes_skipped']} genomes, "
                        f"Eliminated: {summary['eliminated_params']}"
                    )
        else:
            logger.error(f"Failed to write to Sheets for {optimization_id}")

        return success
    except ImportError as e:
        logger.warning(f"Google Sheets not available: {e}")
        return False
    except Exception as e:
        logger.error(f"Sheets write error for {optimization_id}: {e}")
        return False
```

### 6.5 Update `get_progress()` to include smart filtering stats

At the end of `get_progress()`, **before** `return`:

```python
# Add smart filtering info
from app.config.smart_filtering_config import SMART_FILTERING_ENABLED
if SMART_FILTERING_ENABLED:
    try:
        from app.services.smart_filtering_service import SmartFilteringService
        progress["smart_filtering"] = SmartFilteringService.get_filtering_summary(optimization_id)
    except Exception:
        progress["smart_filtering"] = {"enabled": True, "error": "unavailable"}
else:
    progress["smart_filtering"] = {"enabled": False}
```

---

## Step 7: Modify `app/workers/algorithm_worker.py`

### 7.1 Add skip check at start of `process_algorithm_task()`

At the very beginning of the `try` block, **after** extracting `stock_code`, `genome_id`, `optimization_id`, and **before** the `init_db_pool()` call:

```python
# Smart filtering — skip check
from app.config.smart_filtering_config import SMART_FILTERING_ENABLED
if SMART_FILTERING_ENABLED and optimization_id and genome_id != "G_000":
    from app.services.smart_filtering_service import SmartFilteringService
    if SmartFilteringService.is_genome_skipped(optimization_id, genome_id):
        # Atomically mark as incremented (prevent double-counting across stock tasks)
        newly_added = SmartFilteringService.mark_skip_incremented(optimization_id, genome_id)
        if newly_added:
            from app.services.optimization_service import OptimizationService
            metadata = OptimizationService.get_optimization(optimization_id)
            stock_count = len(metadata.stock_codes) if metadata else 1
            OptimizationService.increment_completed_tasks(optimization_id, count=stock_count)
        logger.info(f"SMART FILTER: Skipped genome {genome_id} for {stock_code} (eliminated)")
        return task_data
```

**Key details:**
- `G_000` (BASE) is never skipped — it's the reference.
- `mark_skip_incremented` uses `SADD` which returns `True` only on first call for that genome. This prevents double-counting when multiple stock tasks exist for the same genome.
- When a genome IS the first to be skipped, increment `completed_tasks` by `len(stock_codes)` to account for ALL stock tasks of that genome.
- The skip check is **before** any DB calls, cache warming, or computation — zero wasted work.

---

## Step 8: Modify `app/workers/result_worker.py`

This is the most complex modification. Three changes:

### 8.1 Update `save_genome_optimization_results()`

**Current behavior:**
1. Calculate metrics → write to `optimization_results.csv` → write to `Automated Results.csv` → store in Redis

**New behavior:**
1. Calculate metrics → write to `Automated Results Per Genome.csv` (per-stock, no params) → write to `optimization_results.csv` → store in Redis → track per-genome stock completion → if all stocks done, trigger averaging & filtering

**Modified function:**

```python
AUTOMATED_RESULTS_PER_GENOME_FILE = "Automated Results Per Genome"

async def save_genome_optimization_results(
    stock_code, algo_data, genome_id, parameters, optimization_id=None
):
    if not algo_data:
        logger.warning(f"No algo data for {stock_code}/{genome_id}")
        return None

    result = calculate_genome_metrics(
        trades=algo_data, genome_id=genome_id,
        stock_code=stock_code, parameters=parameters
    )
    output_row = result.to_output_row()

    # 1. Write to optimization_results.csv (unchanged)
    if optimization_id:
        opt_row = {**output_row, "optimization_id": optimization_id}
        opt_fieldnames = ["optimization_id"] + get_output_fieldnames()
        await file_service.add_data_to_csv(OPTIMIZATION_RESULTS_FILE, [opt_row], opt_fieldnames)

    # 2. Write to "Automated Results Per Genome.csv" (NEW — per-stock, no params)
    per_genome_row = {k: v for k, v in output_row.items() if k in get_per_genome_output_fieldnames()}
    if genome_id == "G_000":
        per_genome_row["Genome ID"] = "G_000 (BASE)"
    await file_service.add_data_to_csv(
        AUTOMATED_RESULTS_PER_GENOME_FILE,
        [per_genome_row],
        get_per_genome_output_fieldnames()
    )

    # 3. Store per-stock result in Redis (unchanged)
    if optimization_id:
        try:
            from app.services.optimization_service import OptimizationService
            OptimizationService.store_genome_result(
                optimization_id, genome_id, stock_code, output_row
            )
        except Exception as e:
            logger.error(f"Failed to store result in Redis: {e}")

        # 4. Track per-genome stock completion (NEW)
        try:
            await _check_genome_completion(optimization_id, genome_id, parameters)
        except Exception as e:
            logger.error(f"Failed genome completion check for {genome_id}: {e}")

    logger.info(
        f"Saved optimization result for {genome_id}/{stock_code}: "
        f"{result.trade_count} trades, PR: {result.payoff_ratio:.2f}"
    )
    return result
```

**Note:** Remove the existing write to `AUTOMATED_RESULTS_FILE` (`Automated Results.csv`) from this function. That file is now written only in `_check_genome_completion()` after cross-stock averaging.

**Add import at top of file:**
```python
from app.services.results_aggregation_service import (
    calculate_genome_metrics,
    format_results_for_output,
    get_output_fieldnames,
    get_per_genome_output_fieldnames,     # NEW
    get_averaged_output_fieldnames,        # NEW
    compute_averaged_metrics,              # NEW
    calculate_averaged_deltas,             # NEW
)
```

### 8.2 Add `_check_genome_completion()` function

New async function in `result_worker.py`:

```python
async def _check_genome_completion(optimization_id, genome_id, parameters):
    """
    Check if all stock_codes for this genome are done.
    If so, compute averaged metrics and trigger smart filtering.
    """
    from app.services.optimization_service import OptimizationService
    from app.config.smart_filtering_config import SMART_FILTERING_ENABLED

    metadata = OptimizationService.get_optimization(optimization_id)
    if not metadata:
        return

    stock_count = len(metadata.stock_codes)
    done_count = OptimizationService.increment_genome_stock_done(optimization_id, genome_id)

    if done_count < stock_count:
        return  # Not all stocks done yet

    # --- All stocks for this genome are complete ---
    logger.info(f"All {stock_count} stocks completed for genome {genome_id}, computing average")

    # 1. Fetch all per-stock results from Redis
    all_results = OptimizationService.get_optimization_results(optimization_id)
    per_stock_results = []
    for key, result in all_results.items():
        if key.startswith(f"{genome_id}:"):
            per_stock_results.append(result)

    if not per_stock_results:
        logger.warning(f"No per-stock results found for {genome_id}")
        return

    # 2. Get variable param names and values
    variable_param_names = metadata.variable_param_names
    params = AlgorithmParameters.from_dict(parameters)
    output_params = params.get_variable_params_for_output(variable_param_names)

    # 3. Compute averaged metrics
    averaged = compute_averaged_metrics(per_stock_results, genome_id, output_params)
    if not averaged:
        return

    # 4. Compute deltas vs averaged BASE
    base_result = OptimizationService.get_averaged_results(optimization_id).get("G_000")
    if base_result:
        averaged = calculate_averaged_deltas(averaged, base_result)

    # 5. Write to "Automated Results.csv" (averaged format)
    if genome_id == "G_000":
        averaged["Genome ID"] = "G_000 (BASE)"

    fieldnames = get_averaged_output_fieldnames(variable_param_names)
    await file_service.add_data_to_csv(AUTOMATED_RESULTS_FILE, [averaged], fieldnames)

    # Restore genome_id for Redis storage (without " (BASE)" suffix)
    storage_row = {**averaged}
    if genome_id == "G_000":
        storage_row["Genome ID"] = "G_000"

    # 6. Store averaged result in Redis
    OptimizationService.store_averaged_result(optimization_id, genome_id, storage_row)

    # 7. Smart filtering trigger
    if SMART_FILTERING_ENABLED and genome_id != "G_000":
        try:
            from app.services.smart_filtering_service import SmartFilteringService

            avg_payoff_ratio = float(averaged.get("Payoff Ratio", 0))

            # Get param values for this genome from the stored mapping
            param_values = output_params

            SmartFilteringService.record_genome_result(
                optimization_id, genome_id, avg_payoff_ratio, param_values
            )
            eliminated = SmartFilteringService.check_and_eliminate(
                optimization_id, genome_id, avg_payoff_ratio, param_values
            )
            if eliminated:
                for param, value in eliminated:
                    logger.info(
                        f"SMART FILTER: Eliminated {param}={value} "
                        f"after genome {genome_id} (avg PR: {avg_payoff_ratio:.2f})"
                    )
        except Exception as e:
            logger.error(f"Smart filtering error for {genome_id}: {e}")
```

### 8.3 Update `AUTOMATED_RESULTS_FILE` constant

No change to the constant name, but the write to this file is now **only** in `_check_genome_completion()`, not in `save_genome_optimization_results()`.

---

## Step 9: Verify `increment_completed_tasks` Handles Skipped Genomes

The existing Lua script in `optimization_service.py` already supports `count > 1`:

```python
OptimizationService.increment_completed_tasks(optimization_id, count=stock_count)
```

This is called from the algorithm worker (Step 7) when a genome is skipped. The `count=stock_count` accounts for all stock tasks of that genome at once.

**Verify:** The Lua script already accepts `inc = tonumber(ARGV[1])` — no change needed.

**One edge case to handle:** When skipped genomes push `completed_tasks >= total_tasks`, the Lua script will set status to `completed` and trigger `_write_results_to_sheets()`. This is correct behavior — the optimization may complete while some result worker tasks are still processing the last few genomes, but `_write_results_to_sheets()` reads from the averaged-results Redis hash, which should have all data by then.

---

## Step 10: Run Tests

### 10.1 Unit test for `SmartFilteringService`

Create `tests/test_smart_filtering.py`:

Test cases:
1. **`test_record_and_clear`** — Record a genome with PR >= MIN_PAYOFF_RATIO → verify its param values are cleared.
2. **`test_gradual_elimination`** — Record MIN_OBSERVATIONS genomes with PR < MIN_PAYOFF_RATIO for the same param value (not cleared) → verify it's eliminated.
3. **`test_cleared_param_not_eliminated`** — Record a good genome (clears params), then bad genomes with the same params → verify cleared params are not eliminated.
4. **`test_out_payoff_ratio_instant_kill`** — Set up: clear all but one param for a genome. Record it with PR < OUT_PAYOFF_RATIO → verify the single non-cleared param is eliminated immediately.
5. **`test_out_payoff_ratio_multiple_non_cleared`** — PR < OUT_PAYOFF_RATIO but 2+ non-cleared params → verify no instant elimination (needs more data).
6. **`test_skip_list_populated`** — After elimination, verify all genomes containing the toxic param-value are in skip list.
7. **`test_skip_incremented_idempotent`** — Call `mark_skip_incremented` twice → verify returns `True` then `False`.
8. **`test_base_genome_not_skipped`** — G_000 should never be added to skip list.

### 10.2 Unit test for `compute_averaged_metrics`

Create test cases in `tests/test_results_aggregation.py`:
1. Single stock → averaged == original.
2. Two stocks → verify mean of totals and derived ratios.
3. Zero trades in one stock → verify safe division.

### 10.3 Integration test

Run a small optimization:
- 2 stock_codes
- 3 variable params, 3 values each = 27 genomes + 1 BASE = 28 genomes
- Inject one known-bad param value
- Verify:
  - "Automated Results Per Genome.csv" has `28 × 2 = 56` rows (minus skipped)
  - "Automated Results.csv" has ≤ 28 rows (averaged, some skipped)
  - Smart filtering summary shows the bad param eliminated
  - Skip count matches expected

---

## Execution Order Summary

```
Step 1:  .env.example, .env, docker-compose.yml         — config
Step 2:  app/config/smart_filtering_config.py            — new file
Step 3:  app/services/smart_filtering_service.py         — new file (core logic)
Step 4:  app/models/algorithm_models.py                  — dynamic params
         app/services/optimization_service.py             — OptimizationMetadata field
Step 5:  app/services/results_aggregation_service.py     — new functions
Step 6:  app/services/optimization_service.py            — store mapping, clear files, Sheets, progress
Step 7:  app/workers/algorithm_worker.py                 — skip check
Step 8:  app/workers/result_worker.py                    — per-genome CSV, averaging, filtering trigger
Step 9:  Verify Lua script compatibility                 — no code change expected
Step 10: tests/                                          — unit + integration tests
```

**Dependencies between steps:**
- Step 3 depends on Step 2 (imports config)
- Step 6 depends on Steps 3, 4, 5 (imports SmartFilteringService, uses variable_param_names, uses new aggregation functions)
- Step 7 depends on Steps 2, 3 (imports config and service)
- Step 8 depends on Steps 3, 4, 5, 6 (imports everything)
- Steps 1, 2, 4, 5 can be done in parallel

---

## Files Changed — Final Checklist

| # | File | Action | What |
|---|---|---|---|
| 1 | `.env.example` | MODIFY | Add 4 smart filtering vars |
| 2 | `.env` | MODIFY | Add 4 smart filtering vars |
| 3 | `docker-compose.yml` | MODIFY | Pass vars to algorithm-worker, result-worker |
| 4 | `app/config/smart_filtering_config.py` | CREATE | Load env vars |
| 5 | `app/services/smart_filtering_service.py` | CREATE | Core filtering service (~200 lines) |
| 6 | `app/models/algorithm_models.py` | MODIFY | `get_variable_params_for_output()` accepts optional param list |
| 7 | `app/services/optimization_service.py` | MODIFY | New field, store mapping, averaged results, Sheets, progress |
| 8 | `app/services/results_aggregation_service.py` | MODIFY | 4 new functions |
| 9 | `app/workers/algorithm_worker.py` | MODIFY | Skip check (~15 lines at top of process_algorithm_task) |
| 10 | `app/workers/result_worker.py` | MODIFY | Per-genome CSV, remove old Automated Results write, add `_check_genome_completion()` |
| 11 | `tests/test_smart_filtering.py` | CREATE | Unit tests |
