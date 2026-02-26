# Smart Filtering — Requirements & Implementation Plan

## 1. Problem Statement

When running 7200+ genome combinations, approximately 50% produce Payoff Ratio < 2 due to a few toxic parameter values. These bad genomes waste ~40% of computation time. On larger scales, the waste grows proportionally.

**Goal:** Detect toxic parameter values early during optimization and remove all remaining genomes containing them from the processing queue — reducing total runtime by ~40% without losing good candidates.

## 2. Core Concept

### 2.1 Multi-Stock Averaging

Each genome is evaluated across **all specified stock_codes**. A genome's quality is judged by its **averaged** metrics (across stocks), not per-stock metrics. This eliminates noise from individual stock behavior and ensures a parameter is only deemed toxic if it performs poorly **universally**.

### 2.2 Two-Threshold Elimination

| Threshold | Env Variable | Default | Purpose |
|---|---|---|---|
| Quality bar | `MIN_PAYOFF_RATIO` | `2` | Minimum acceptable average Payoff Ratio for a genome |
| Instant kill | `OUT_PAYOFF_RATIO` | `1` | Payoff Ratio so bad it triggers immediate process-of-elimination |
| Min evidence | `MIN_OBSERVATIONS` | `2` | Minimum genomes observed before judging a parameter value |
| Feature toggle | `SMART_FILTERING_ENABLED` | `true` | Enable/disable smart filtering |

### 2.3 Toxic Parameter Identification Algorithm

**Per-parameter-value tracking:**
- For every completed genome, record its averaged Payoff Ratio against each `(param_name, param_value)` it contains.
- A `(param_name, param_value)` that appeared in **any** genome with `avg_payoff_ratio >= MIN_PAYOFF_RATIO` is marked as **"cleared"** (proven not universally toxic).

**Gradual elimination (`MIN_PAYOFF_RATIO` path):**
- A `(param_name, param_value)` is **toxic** when:
  - It has `>= MIN_OBSERVATIONS` observations, AND
  - **ALL** observations have `avg_payoff_ratio < MIN_PAYOFF_RATIO`
- On detection: remove all remaining genomes containing this value from the queue.

**Instant elimination (`OUT_PAYOFF_RATIO` path — process-of-elimination):**
- When a genome completes with `avg_payoff_ratio < OUT_PAYOFF_RATIO`:
  - Check which `(param_name, param_value)` pairs in this genome are **not yet cleared**.
  - If exactly **ONE** non-cleared param-value remains → it is the toxic cause → eliminate it **immediately** (bypass `MIN_OBSERVATIONS`).
  - If multiple non-cleared params remain → cannot isolate the cause yet → wait for more data (the gradual path will handle it).

**Multiple candidates:** If two or more param values qualify as toxic simultaneously via the gradual path, eliminate the one with the **most bad observations** (strongest evidence). The rest will resolve as more genomes complete.

**Example walkthrough:**
```
Genome G_001 (B1=0.55, B3=40, S5=0.9) → avg PR = 0.5 (< OUT_PAYOFF_RATIO)
  → B1=0.55: not cleared, B3=40: not cleared, S5=0.9: not cleared
  → 3 non-cleared params → cannot isolate → record stats, continue

Genome G_002 (B1=0.55, B3=40, S5=0.7) → avg PR = 3.5 (>= MIN_PAYOFF_RATIO)
  → B1=0.55: CLEARED ✓, B3=40: CLEARED ✓, S5=0.7: CLEARED ✓

Now re-evaluate G_001's param stats:
  → B1=0.55: cleared, B3=40: cleared, S5=0.9: NOT cleared, 1 observation < MIN_PAYOFF_RATIO
  → S5=0.9 has only 1 observation (< MIN_OBSERVATIONS=2) → not eliminated yet

Genome G_003 (B1=0.65, B3=58, S5=0.9) → avg PR = 1.5 (< MIN_PAYOFF_RATIO)
  → S5=0.9 now has 2 observations, ALL < MIN_PAYOFF_RATIO → TOXIC
  → Eliminate all remaining genomes with S5=0.9 from queue
```

## 3. Output File Restructuring

### 3.1 Current State

- **"Automated Results.csv"** — one row per `(genome, stock_code)` pair, includes parameter columns.
- **"Automated Results Per Genome.csv"** — does not exist.

### 3.2 New Structure

#### "Automated Results Per Genome.csv" (NEW)

Per-stock results. Written as each genome+stock completes.

| Column | Description |
|---|---|
| Genome ID | `G_000 (BASE)`, `G_001`, ... |
| Stock Code | e.g. `3888` |
| Trade Count | Number of completed trades |
| Profit Delta (%) | vs BASE for this stock |
| Win Rate Delta (%) | vs BASE for this stock |
| Total Win ($) | Sum of winning trades |
| Total Loss ($) | Sum of losing trades |
| Trades Win | Count of winning trades |
| Trades Loss | Count of losing trades |
| Avg Win ($) | Average winning trade |
| Avg Loss ($) | Average losing trade |
| Payoff Ratio | Avg Win / Avg Loss |

**Unique key:** `Genome ID` + `Stock Code`

**No parameter columns** in this file.

#### "Automated Results.csv" (CHANGED)

Averaged results across all stock_codes. Written only after a genome completes for **all** stock_codes.

| Column | Description |
|---|---|
| Genome ID | `G_000 (BASE)`, `G_001`, ... |
| Trade Count | Average across stocks |
| Profit Delta (%) | vs averaged BASE |
| Win Rate Delta (%) | vs averaged BASE |
| Total Win ($) | Average across stocks |
| Total Loss ($) | Average across stocks |
| Trades Win | Average across stocks |
| Trades Loss | Average across stocks |
| Avg Win ($) | Derived from averaged totals |
| Avg Loss ($) | Derived from averaged totals |
| Payoff Ratio | Derived from averaged totals |
| `<param_1>` | Dynamic — only changed parameters |
| `<param_2>` | Dynamic — only changed parameters |
| ... | ... |

**Unique key:** `Genome ID`

**No `Stock Code` column** in this file.

#### Google Sheets

Same format as "Automated Results.csv" (averaged, no Stock Code). Written on optimization completion.

### 3.3 Averaging Method

Metrics are averaged by computing the **mean of the raw totals**, then deriving ratios:

```
avg_total_win   = mean(total_win across stocks)
avg_total_loss  = mean(total_loss across stocks)
avg_trades_win  = mean(trades_win across stocks)
avg_trades_loss = mean(trades_loss across stocks)

avg_win  = avg_total_win / avg_trades_win    (if avg_trades_win > 0)
avg_loss = avg_total_loss / avg_trades_loss   (if avg_trades_loss > 0)
payoff_ratio = avg_win / avg_loss             (if avg_loss > 0)
```

This is more statistically sound than averaging Payoff Ratios directly (avoids distortion from stocks with few trades).

## 4. Execution Flow Changes

### 4.1 Optimization Creation (Step 1–2 unchanged)

In `OptimizationService.create_optimization()`:
1. Generate genomes (unchanged).
2. **NEW:** Store genome-parameter mapping in Redis: `smart_filter:genomes:{opt_id}` = `{genome_id: {param: value, ...}}` for variable params only.
3. **NEW:** Store list of variable parameter names in `OptimizationMetadata` (for dynamic column headers).
4. Queue tasks (unchanged).

### 4.2 Algorithm Worker — Skip Check (NEW)

At the **start** of `process_algorithm_task()`, before any DB/computation:

```
if SMART_FILTERING_ENABLED:
    if SmartFilteringService.is_genome_skipped(optimization_id, genome_id):
        # Skip all stock tasks for this genome
        # Use Redis SET to prevent double-counting across stock tasks
        if not already_skip_incremented(optimization_id, genome_id):
            increment_completed_tasks(optimization_id, count=len(stock_codes))
            mark_skip_incremented(optimization_id, genome_id)
        log "Skipped genome {genome_id} (eliminated by smart filter)"
        return
```

### 4.3 Result Worker — Per-Stock Processing (MODIFIED)

In `save_genome_optimization_results()`:
1. Calculate per-stock metrics (unchanged logic).
2. Write to **"Automated Results Per Genome.csv"** (new file, per-stock format).
3. **Stop** writing to "Automated Results.csv" at this stage.
4. Store per-stock result in Redis hash `optimization_results:{opt_id}` field `{genome_id}:{stock_code}` (unchanged).
5. **NEW:** Atomically increment per-genome stock counter: `HINCRBY genome_done:{opt_id} {genome_id} 1`.
6. **NEW:** If returned count == `len(stock_codes)` → genome fully complete → trigger cross-stock averaging.

### 4.4 Cross-Stock Averaging & Smart Filtering (NEW)

When all stocks for a genome are complete:

1. Fetch all per-stock results for this genome from Redis.
2. Compute averaged metrics (Section 3.3).
3. Compute Profit Delta / Win Rate Delta vs averaged G_000 (BASE).
4. Write averaged result to **"Automated Results.csv"** (averaged format).
5. Store in Redis hash `optimization_avg_results:{opt_id}` field `{genome_id}`.
6. **Smart filtering trigger:**
   - Call `SmartFilteringService.record_genome_result(opt_id, genome_id, avg_payoff_ratio, param_values)`.
   - Call `SmartFilteringService.check_and_eliminate(opt_id, ...)`.
   - If any parameter value is eliminated → update skip list → log event.

### 4.5 Optimization Completion (MODIFIED)

In `_write_results_to_sheets()`:
- Read from `optimization_avg_results:{opt_id}` (averaged results).
- Write with averaged fieldnames (no `Stock Code` column, dynamic param columns).
- Include smart filtering summary in log output.

## 5. Redis Data Structures

| Key Pattern | Type | Purpose | TTL |
|---|---|---|---|
| `smart_filter:genomes:{opt_id}` | STRING (JSON) | `{genome_id: {param: val, ...}}` — full genome→params mapping | Same as optimization |
| `smart_filter:stats:{opt_id}` | HASH | Field: `{param}:{value}`, Value: JSON list of observed avg PRs | Same as optimization |
| `smart_filter:cleared:{opt_id}` | SET | Members: `{param}:{value}` strings that appeared in good genomes | Same as optimization |
| `smart_filter:skip_list:{opt_id}` | SET | Members: `genome_id` strings to skip | Same as optimization |
| `smart_filter:skip_incremented:{opt_id}` | SET | Members: `genome_id` strings already counter-incremented | Same as optimization |
| `smart_filter:eliminated:{opt_id}` | HASH | Field: `{param}:{value}`, Value: JSON evidence object | Same as optimization |
| `genome_done:{opt_id}` | HASH | Field: `genome_id`, Value: int count of completed stocks | Same as optimization |
| `optimization_avg_results:{opt_id}` | HASH | Field: `genome_id`, Value: JSON averaged result row | Same as optimization |

## 6. New/Modified Files

### New Files

| File | Purpose |
|---|---|
| `app/config/smart_filtering_config.py` | Load `MIN_PAYOFF_RATIO`, `OUT_PAYOFF_RATIO`, `MIN_OBSERVATIONS`, `SMART_FILTERING_ENABLED` from env |
| `app/services/smart_filtering_service.py` | Core filtering logic: tracking, identification, elimination, skip list |

### Modified Files

| File | Changes |
|---|---|
| `.env.example` | Add `MIN_PAYOFF_RATIO`, `OUT_PAYOFF_RATIO`, `MIN_OBSERVATIONS`, `SMART_FILTERING_ENABLED` |
| `app/services/optimization_service.py` | Store genome-param mapping, store variable param names in metadata, use averaged results for Sheets |
| `app/workers/algorithm_worker.py` | Add skip check at start of `process_algorithm_task()` |
| `app/workers/result_worker.py` | Write to Per Genome CSV, track per-genome stock completion, trigger averaging & filtering |
| `app/services/results_aggregation_service.py` | Add per-genome fieldnames, averaged fieldnames, `compute_averaged_metrics()` |
| `app/models/algorithm_models.py` | Make `get_variable_params_for_output()` accept dynamic param list; add variable param names to `OptimizationMetadata` |

## 7. Configuration

### .env additions

```dotenv
# Smart Filtering Configuration
SMART_FILTERING_ENABLED=true
MIN_PAYOFF_RATIO=2
OUT_PAYOFF_RATIO=1
MIN_OBSERVATIONS=2
```

### Notes

- `MIN_PAYOFF_RATIO` — user-adjustable quality threshold. Default `2` for visual testing, production target `3`.
- `OUT_PAYOFF_RATIO` — hard floor. Any genome averaging below this triggers instant process-of-elimination.
- `MIN_OBSERVATIONS` — set to `2` because with ~5 combinations per parameter value, higher values would never trigger.
- `SMART_FILTERING_ENABLED` — allows disabling filtering for baseline comparison runs.

## 8. Monitoring & Logging

### Log Output

Each elimination event (INFO level):
```
SMART FILTER: Eliminated input_S5_push_up_atr=0.9
  Evidence: 2 observations, all PR < 2.0 [0.5, 1.5]
  Skipping 48 remaining genomes (96 tasks)
```

Optimization completion summary (INFO level):
```
SMART FILTER SUMMARY for opt_abc123:
  Total genomes: 7200 | Processed: 4200 | Skipped: 3000
  Eliminated parameters:
    - input_S5_push_up_atr=0.9 (after genome G_003, 2 observations)
    - input_B18_bbw_ratio=0.15 (after genome G_087, 3 observations)
  Estimated time saved: ~40%
```

### Progress API

`GET /api/v1/optimization/{id}/progress` response extended with:
```json
{
  "smart_filtering": {
    "enabled": true,
    "genomes_skipped": 3000,
    "eliminated_params": [
      {"param": "input_S5_push_up_atr", "value": 0.9, "after_genome": "G_003", "observations": 2},
      {"param": "input_B18_bbw_ratio", "value": 0.15, "after_genome": "G_087", "observations": 3}
    ]
  }
}
```

## 9. Edge Cases & Design Decisions

| Decision | Rationale |
|---|---|
| Skip list (not queue removal) | Simpler architecture — all tasks stay in RQ queue, workers check Redis SET before processing. Avoids complex queue manipulation |
| Per-genome skip granularity | When a genome is skipped, ALL its stock tasks are skipped. A genome that's bad on average shouldn't run for any stock |
| Skipped genomes excluded from output | They don't appear in "Automated Results.csv". Partial per-stock results from already-started tasks may appear in "Automated Results Per Genome.csv" |
| Race condition accepted | A few genome tasks may start processing before the skip list is updated — this is acceptable since it affects at most a handful of genomes |
| No confirmation step | If a parameter value only works for one stock but fails the rest, the average reflects that, and it should be eliminated |
| Cleared params never un-cleared | Once a param-value is seen in a good genome, it's permanently cleared for this optimization run |
| Averaging uses mean of raw totals | More statistically sound than averaging ratios directly |
| Dynamic parameter columns | Output adapts to whichever parameters have `Change=TRUE`, not hardcoded to 6 params |

## 10. Testing Strategy

### Unit Tests (smart_filtering_service)
- Single toxic param correctly identified after MIN_OBSERVATIONS
- Process-of-elimination with OUT_PAYOFF_RATIO (single non-cleared param → instant kill)
- Cleared params are never eliminated
- Multiple toxic candidates → most-observed eliminated first
- Skipped genomes correctly tracked and not double-counted
- Averaging computation produces correct Payoff Ratio

### Integration Tests
- Small optimization (3 params × 3 values = 27 combos, 2 stocks) with one known-bad value → verify elimination triggers
- Verify both CSV files have correct format and content
- Verify Google Sheets output uses averaged format
- Verify skip counter correctly adjusts total_tasks tracking

### Manual Validation
- Run full 7200-genome optimization with `MIN_PAYOFF_RATIO=2`
- Confirm ~40% genome reduction
- Compare results quality vs unfiltered run (no good candidates lost)
