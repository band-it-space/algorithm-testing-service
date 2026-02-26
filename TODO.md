# TODO — Code Standardization

> Audit date: 2026-02-26  
> Reference: [AGENTS.md](AGENTS.md), [.github/copilot-instructions.md](.github/copilot-instructions.md)

---

## Phase 1 — Critical (Fix First)

### 1.1 Rename camelCase functions → snake_case

**Files:** `app/workers/algo_func/buy_signals.py`, `app/workers/algo_func/buy_king.py`, `app/workers/algo_func/sell_king.py`, `app/workers/algo_func/sell_signals.py`

#### `buy_signals.py`

- [x] `checkB1` → `check_b1`
- [x] `checkB3` → `check_b3`
- [x] `checkB8` → `check_b8`
- [x] `checkB9` → `check_b9`
- [x] `checkB10` → `check_b10`
- [x] `checkB11` → `check_b11`
- [x] `checkB12` → `check_b12`
- [x] `checkB13` → `check_b13`
- [x] `checkB18` → `check_b18`
- [x] `calcS1Stop` → `calc_s1_stop`
- [x] `runAllBuyConditions` → `run_all_buy_conditions`
- [x] `isBuy` → `is_buy`

#### `buy_king.py`

- [x] `checkB1_US` → `check_b1_us`
- [x] `checkB8_US` → `check_b8_us`
- [x] `checkB9_US` → `check_b9_us`
- [x] `checkB11_US` → `check_b11_us`
- [x] `checkB18_US` → `check_b18_us`
- [x] `checkB20_US` → `check_b20_us`
- [x] `checkB21_US` → `check_b21_us`
- [x] `checkB22_US` → `check_b22_us`
- [x] `calcS1Stop_US` → `calc_s1_stop_us`
- [x] `runAllBuyConditions_US` → `run_all_buy_conditions_us`
- [x] `isBuy_US` → `is_buy_us`

#### `sell_king.py`

- [x] `checkS1_US` → `check_s1_us`
- [x] `checkS4_US` → `check_s4_us`
- [x] `checkS5_US` → `check_s5_us`
- [x] `checkS6_US` → `check_s6_us`
- [x] `checkS7_US` → `check_s7_us`
- [x] `checkS8_US` → `check_s8_us`
- [x] `checkS9_US` → `check_s9_us`
- [x] `checkS13_US` → `check_s13_us`
- [x] `checkS14_US` → `check_s14_us`
- [x] `checkS18_US` → `check_s18_us`
- [x] `checkS19_US` → `check_s19_us`
- [x] `checkS20_US` → `check_s20_us`
- [x] `runAllSellConditions_US` → `run_all_sell_conditions_us`
- [x] `isSell_US` → `is_sell_us`

#### `sell_signals.py`

- [x] `runAllSellConditions` → `run_all_sell_conditions`
- [x] `isSell` → `is_sell`

> **Note:** After renaming — update all call sites in `algorithm_worker.py` and `us_king_worker.py`.

---

### 1.2 Remove duplicate `OHLCV` definition

**File:** `app/workers/algo_func/sell_signals.py`

- [ ] Remove local `OHLCV` class definition from `sell_signals.py`
- [ ] Add import: `from app.workers.algo_func.types import OHLCV`
- [ ] Verify `types.py` exports `OHLCV` correctly

---

### 1.3 Replace `print()` with `logger`

**File:** `app/workers/algorithm_worker.py` — 10 occurrences

- [x] Line 114: `print("start")` → `logger.info("Starting algorithm worker task")`
- [x] Line 147: `print(f"Немає сигналу для коду {code}")` → `logger.warning(f"No signal for code {code}")`
- [x] Line 348: `print(f"Немає записів у файлі data/{file_name}.csv")` → `logger.warning(...)` (translate to English)
- [x] Line 353: `print(f"Немає записів для коду {code}")` → `logger.warning(f"No records for code {code}")`
- [x] Line 364: `print(f"Немає валідних дат tradeday для коду {code}")` → `logger.warning(f"No valid tradeday dates for code {code}")`
- [x] Remove commented-out `print()` lines (158, 163, 177, 230, 231, 272)

**File:** `app/workers/algo_func/get_db_data.py` — 4 occurrences

- [x] Line 27: `print(f"❌ Error fetching data from API: {e}")` → `logger.error(...)`
- [x] Line 63: `print("⚠️ Empty records found at dates: ...")` → `logger.warning(...)`
- [x] Line 81: `print(f"❌ Error fetching data from API: {e}")` → `logger.error(...)`
- [x] Line 118: `print("⚠️ Empty records found at dates: ...")` → `logger.warning(...)`

---

## Phase 2 — Type Hints

### 2.1 Replace legacy `typing` imports

Affects **13 files** (confirmed by audit):

| File                                       | Legacy imports                                          |
| ------------------------------------------ | ------------------------------------------------------- |
| `app/models/algorithm_models.py`           | `Optional, Union`                                       |
| `app/workers/result_worker.py`             | `List, Optional, TypedDict, Union, Tuple, Dict, Any`    |
| `app/workers/algorithm_worker.py`          | `Optional, Dict, Any, List, Union`                      |
| `app/workers/us_king_worker.py`            | `Dict, Any, List, Literal, Optional`                    |
| `app/workers/algo_func/buy_signals.py`     | `List, Dict, Optional, Union` (+ duplicate on line 312) |
| `app/workers/algo_func/sell_king.py`       | `List, Optional, Dict, Any`                             |
| `app/workers/algo_func/types.py`           | `Optional`                                              |
| `app/workers/algo_func/buy_king.py`        | `List, Dict, Optional, Union`                           |
| `app/workers/algo_func/sell_signals.py`    | `List, Optional`                                        |
| `app/workers/algo_func/helpers.py`         | `List, Optional`                                        |
| `app/workers/algo_func/get_code_energy.py` | `Dict, Any, List`                                       |
| `app/services/queue_service.py`            | `Dict, List`                                            |
| `app/services/get_all_stoccks.py`          | `List, Dict`                                            |

**Replacement rules:**

- [ ] `List[X]` → `list[X]`
- [ ] `Dict[K, V]` → `dict[K, V]`
- [ ] `Optional[X]` → `X | None`
- [ ] `Tuple[X, Y]` → `tuple[X, Y]`
- [ ] `Union[X, Y]` → `X | Y`
- [ ] Remove `from typing import ...` lines (keep only `TypedDict`, `Any`, `Literal` if still needed)

---

### 2.2 Add missing type hints

- [ ] `app/workers/algo_func/sell_signals.py` — `runAllSellConditions` and `isSell` have no type hints
- [ ] `app/workers/algo_func/get_db_data.py` — audit all functions
- [ ] `app/services/file_service.py` — audit all methods
- [ ] `app/services/get_all_stoccks.py` — audit all functions

---

## Phase 3 — Async / Blocking I/O

### 3.1 Replace blocking I/O in async functions

- [ ] `app/services/file_service.py` — replace `open()` with `aiofiles.open()`
- [ ] `app/workers/algo_func/get_db_data.py` — replace `requests.get()` with `aiohttp`

> Add `aiofiles` to `requirements.txt` if not present.

---

## Phase 4 — Language & Comments

### 4.1 Translate Ukrainian/Russian → English

**File:** `app/workers/algorithm_worker.py`

- [x] Line 147: `"Немає сигналу для коду {code}"` → `"No signal for code {code}"`
- [x] Line 348: `"Немає записів у файлі data/{file_name}.csv"` → `"No records in file data/{file_name}.csv"`
- [x] Line 353: `"Немає записів для коду {code}"` → `"No records for code {code}"`
- [x] Line 364: `"Немає валідних дат tradeday для коду {code}"` → `"No valid tradeday dates for code {code}"`
- [x] Audit all other files for remaining Ukrainian/Russian strings

---

### 4.2 Add missing docstrings

- [ ] All public functions in `app/workers/algo_func/buy_signals.py`
- [ ] All public functions in `app/workers/algo_func/sell_signals.py`
- [ ] All public functions in `app/services/queue_service.py`
- [ ] `app/main.py` — module-level docstring

---

## Phase 5 — Testing

### 5.1 Setup pytest

- [ ] Add to `requirements.txt`: `pytest>=8.0`, `pytest-asyncio>=0.23`, `pytest-cov>=4.0`
- [ ] Create `tests/` directory with `__init__.py`
- [ ] Create `pytest.ini` or `pyproject.toml` config

### 5.2 Write unit tests

- [ ] `tests/test_buy_signals.py` — test each `check_b*` function
- [ ] `tests/test_sell_signals.py` — test each `check_s*` function with known data
- [ ] `tests/test_file_service.py` — test CSV read/write
- [ ] `tests/test_helpers.py` — test RSI, ATR and other indicator calculations

---

## Progress Summary

| Phase                   | Tasks          | Done   |
| ----------------------- | -------------- | ------ |
| 1.1 Function naming     | 38 functions   | 38 ✅  |
| 1.2 OHLCV deduplication | 3 steps        | 0      |
| 1.3 Replace print()     | 14 occurrences | 14 ✅  |
| 2.1 Legacy typing       | 13 files       | 0      |
| 2.2 Missing type hints  | 4 files        | 0      |
| 3.1 Blocking I/O        | 2 files        | 0      |
| 4.1 Translate comments  | 4+ strings     | ✅ all |
| 4.2 Docstrings          | 4 files        | 0      |
