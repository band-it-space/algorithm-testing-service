# Multithreading Fix — Implementation Plan

## Problem Statement

Currently, only the **algorithm worker** supports concurrent job processing via `ConcurrentWorker` + `ThreadPoolExecutor`. The **result worker** and **file-write worker** use standard `rq.Worker`, which:

1. Processes **1 job at a time** per process (no concurrency within a process).
2. **Does not handle `async` functions** properly — the task functions (`process_result_task`, `process_file_write_task`) are `async def`, but standard `rq.Worker` may not `await` them, meaning the work silently never executes.
3. Ignores `WORKER_CONCURRENT_TASKS` env var entirely.

### Current Behavior (broken)

```
Algorithm workers:  10 processes × 8 threads = 80 concurrent tasks  ✅
Result workers:      2 processes × 1 (sequential) = 2 tasks          ❌
File-write workers:  1 process  × 1 (sequential) = 1 task            ❌
```

### `.env` Configuration

The number of worker **processes** and **threads per process** are controlled by `.env` variables:

| Variable | Description | Default |
|---|---|---|
| `ALGORITHM_WORKER_COUNT` | Number of worker **processes** spawned by `start_algorithm_worker.py`. Each process is an independent OS process competing for jobs from the same Redis queue. | `1` |
| `WORKER_CONCURRENT_TASKS` | Number of **threads** inside each worker process (`ThreadPoolExecutor(max_workers=N)`). Each thread processes one genome task concurrently. | `1` |

**Total concurrent capacity** = `ALGORITHM_WORKER_COUNT` × `WORKER_CONCURRENT_TASKS`.

Example with `ALGORITHM_WORKER_COUNT=4`, `WORKER_CONCURRENT_TASKS=10`:
- 4 OS processes are spawned.
- Each process runs a `ThreadPoolExecutor` with 10 threads.
- Total: up to **40 genome tasks** processed simultaneously.
- Workers pull jobs from the shared Redis queue on demand (no pre-assignment).

### Expected Behavior (after fix)

With config: `ALGORITHM_WORKER_COUNT=4`, `WORKER_CONCURRENT_TASKS=10`, 33 genomes:

```
WORKER 1: Process G_000, G_001, G_002, G_003, G_004, G_005, G_006, G_007, G_008;
WORKER 2: Process G_009, G_010, G_011, G_012, G_013, G_014, G_015, G_016;
WORKER 3: Process G_017, G_018, G_019, G_020, G_021, G_022, G_023, G_024;
WORKER 4: Process G_025, G_026, G_027, G_028, G_029, G_030, G_031, G_032;
```

All genomes processed **simultaneously** across workers, each worker handling up to 10 concurrent tasks via threads.

Same pattern must apply to **all three worker types** (algorithm, result, file-write).

---

## Architecture Overview

```
┌─────────────────────┐
│  API / Optimization  │
│     Service          │
└────────┬────────────┘
         │ enqueue tasks
         ▼
┌─────────────────────┐     ┌──────────────────────────────────────────┐
│  Redis Queue:        │     │  Algorithm Workers (N processes)         │
│  algorithm_calculation│────►│  Each: ThreadPoolExecutor(M threads)    │
└─────────────────────┘     │  Total capacity: N × M concurrent tasks  │
                            └────────┬─────────────────────────────────┘
                                     │ enqueue results
                                     ▼
┌─────────────────────┐     ┌──────────────────────────────────────────┐
│  Redis Queue:        │     │  Result Workers (N processes)            │
│  result_processing   │────►│  Each: ThreadPoolExecutor(M threads)    │
└─────────────────────┘     │  Total capacity: N × M concurrent tasks  │
                            └────────┬─────────────────────────────────┘
                                     │ enqueue file writes
                                     ▼
┌─────────────────────┐     ┌──────────────────────────────────────────┐
│  Redis Queue:        │     │  File-Write Workers (N processes)        │
│  file_write          │────►│  Each: ThreadPoolExecutor(M threads)    │
└─────────────────────┘     │  Total capacity: N × M concurrent tasks  │
                            └────────┬─────────────────────────────────┘
                                     │
                                     ▼
                              Automated Results.csv
```

Workers pull jobs from a **shared Redis queue** using atomic `lpop`. No pre-assignment needed — each worker grabs the next available job when it has a free thread slot.

---

## Implementation Steps

### Step 1: Extract `ConcurrentWorker` into a shared module

**File:** `app/workers/concurrent_worker.py` (new)

Extract the `ConcurrentWorker` class from `workers/start_algorithm_worker.py` into a reusable module so all three worker types can use the same logic.

```python
"""
Reusable concurrent worker that processes multiple RQ jobs via ThreadPoolExecutor.
Handles both sync and async task functions.
"""
import logging
import time
import asyncio
import inspect
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

from rq.job import Job


class ConcurrentWorker:
    """
    Custom worker that processes multiple RQ jobs concurrently using ThreadPoolExecutor.
    Properly handles async task functions by creating per-thread event loops.
    """

    def __init__(self, queue, concurrent_tasks: int, worker_id: int, logger_name: str):
        self.queue = queue
        self.concurrent_tasks = concurrent_tasks
        self.worker_id = worker_id
        self.logger = logging.getLogger(logger_name)
        self.running = True
        self.lock = Lock()

    def process_job(self, job: Job):
        """Process a single job, handling both sync and async functions."""
        try:
            self.logger.info(f"Worker {self.worker_id}: Starting job {job.id}")
            func = job.func
            args = job.args
            kwargs = job.kwargs

            if inspect.iscoroutinefunction(func):
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    result = loop.run_until_complete(func(*args, **kwargs))
                finally:
                    loop.close()
            else:
                result = func(*args, **kwargs)

            job.set_status('finished')
            self.logger.info(f"Worker {self.worker_id}: Job {job.id} completed")
            return job.id, "success", None
        except Exception as e:
            self.logger.error(f"Worker {self.worker_id}: Job {job.id} failed: {e}")
            job.set_status('failed')
            return job.id, "failed", str(e)

    def fetch_jobs(self, count: int):
        """Fetch up to `count` jobs from the queue atomically via Redis lpop."""
        jobs = []
        for _ in range(count):
            result = self.queue.connection.lpop(self.queue.key)
            if result:
                job_id = result.decode() if isinstance(result, bytes) else result
                try:
                    job = Job.fetch(job_id, connection=self.queue.connection)
                    jobs.append(job)
                except Exception as e:
                    self.logger.warning(
                        f"Worker {self.worker_id}: Could not fetch job {job_id}: {e}"
                    )
            else:
                break
        return jobs

    def work(self):
        """Main work loop — fetches and processes jobs concurrently."""
        self.logger.info(
            f"Concurrent Worker {self.worker_id} started "
            f"with {self.concurrent_tasks} threads"
        )

        with ThreadPoolExecutor(max_workers=self.concurrent_tasks) as executor:
            active_futures = {}

            while self.running:
                try:
                    slots_available = self.concurrent_tasks - len(active_futures)

                    if slots_available > 0:
                        new_jobs = self.fetch_jobs(slots_available)
                        for job in new_jobs:
                            future = executor.submit(self.process_job, job)
                            active_futures[future] = job

                    if not active_futures:
                        time.sleep(0.5)
                        continue

                    done_futures = [f for f in active_futures if f.done()]
                    for future in done_futures:
                        job = active_futures.pop(future)
                        try:
                            job_id, status, error = future.result()
                        except Exception as e:
                            self.logger.error(
                                f"Worker {self.worker_id}: Job execution error: {e}"
                            )

                    time.sleep(0.1)

                except KeyboardInterrupt:
                    self.running = False
                    break
                except Exception as e:
                    self.logger.error(f"Worker {self.worker_id} error: {e}")
                    time.sleep(1)

        self.logger.info(f"Concurrent Worker {self.worker_id} stopped")

    def stop(self):
        """Signal the worker to stop."""
        self.running = False
```

---

### Step 2: Refactor `start_algorithm_worker.py`

Replace the inline `ConcurrentWorker` class with an import from the shared module:

```python
# Remove the entire ConcurrentWorker class definition
# Replace with:
from app.workers.concurrent_worker import ConcurrentWorker

def run_concurrent_worker(worker_id: int, concurrent_tasks: int):
    setup_logging()
    worker = ConcurrentWorker(
        queue=algorithm_calculation_queue,
        concurrent_tasks=concurrent_tasks,
        worker_id=worker_id,
        logger_name="app.workers.algorithm_worker"
    )
    worker.work()
```

The rest of `main()` stays the same.

---

### Step 3: Refactor `start_result_worker.py`

Replace the standard `rq.Worker` with `ConcurrentWorker`:

```python
from app.workers.concurrent_worker import ConcurrentWorker
from app.config.queue_config import (
    redis_conn, result_processing_queue,
    get_worker_count, get_concurrent_tasks
)

def run_concurrent_worker(worker_id: int, concurrent_tasks: int):
    setup_logging()
    worker = ConcurrentWorker(
        queue=result_processing_queue,
        concurrent_tasks=concurrent_tasks,
        worker_id=worker_id,
        logger_name="app.workers.result_worker"
    )
    worker.work()

def run_standard_worker():
    setup_logging()
    logger = logging.getLogger("app.workers.result_worker")
    with Connection(redis_conn):
        worker = Worker([result_processing_queue])
        worker.work()

def main():
    worker_count = get_worker_count("result")
    concurrent_tasks = get_concurrent_tasks()

    for i in range(worker_count):
        if concurrent_tasks > 1:
            p = multiprocessing.Process(
                target=run_concurrent_worker,
                args=(i, concurrent_tasks),
                name=f"result-worker-{i}"
            )
        else:
            p = multiprocessing.Process(
                target=run_standard_worker,
                name=f"result-worker-{i}"
            )
        p.start()
        processes.append(p)
```

---

### Step 4: Refactor `start_file_write_worker.py`

Same pattern as result worker:

```python
from app.workers.concurrent_worker import ConcurrentWorker
from app.config.queue_config import (
    redis_conn, file_write_queue,
    get_worker_count, get_concurrent_tasks
)

def run_concurrent_worker(worker_id: int, concurrent_tasks: int):
    setup_logging()
    worker = ConcurrentWorker(
        queue=file_write_queue,
        concurrent_tasks=concurrent_tasks,
        worker_id=worker_id,
        logger_name="app.workers.file_write_worker"
    )
    worker.work()

def main():
    worker_count = get_worker_count("file")
    concurrent_tasks = get_concurrent_tasks()
    # Same process spawning logic as algorithm/result workers
```

---

### Step 5: Add per-worker-type concurrent task settings

**File:** `app/config/queue_config.py`

Currently there is a single `WORKER_CONCURRENT_TASKS` env var for all workers. Add separate settings so each worker type can be tuned independently:

```python
def get_concurrent_tasks(worker_type: str = "algorithm") -> int:
    """Get number of concurrent tasks per worker process."""
    env_map = {
        "algorithm": "ALGORITHM_CONCURRENT_TASKS",
        "result": "RESULT_CONCURRENT_TASKS",
        "file": "FILE_CONCURRENT_TASKS"
    }
    env_var = env_map.get(worker_type, "ALGORITHM_CONCURRENT_TASKS")
    # Fall back to generic WORKER_CONCURRENT_TASKS, then to 1
    return int(os.getenv(env_var, os.getenv("WORKER_CONCURRENT_TASKS", "1")))
```

---

### Step 6: Update `.env` with recommended defaults

```dotenv
# Worker Process Counts
ALGORITHM_WORKER_COUNT=4
RESULT_WORKER_COUNT=2
FILE_WORKER_COUNT=1

# Concurrent Tasks Per Process (threads)
WORKER_CONCURRENT_TASKS=10          # generic fallback
ALGORITHM_CONCURRENT_TASKS=10       # per algorithm worker process
RESULT_CONCURRENT_TASKS=5           # per result worker process
FILE_CONCURRENT_TASKS=3             # per file-write worker process
```

---

### Step 7: Update `docker-compose.yml`

Pass the new env vars to result-worker and file-write-worker services:

```yaml
result-worker:
    environment:
      - RESULT_WORKER_COUNT=${RESULT_WORKER_COUNT:-2}
      - RESULT_CONCURRENT_TASKS=${RESULT_CONCURRENT_TASKS:-5}
      # ... existing vars ...

file-write-worker:
    environment:
      - FILE_WORKER_COUNT=${FILE_WORKER_COUNT:-1}
      - FILE_CONCURRENT_TASKS=${FILE_CONCURRENT_TASKS:-3}
      # ... existing vars ...
```

---

### Step 8: Thread-safety audit for file writes

`FileService.add_data_to_csv()` will be called concurrently from multiple threads/processes writing to the same `Automated Results.csv`. Ensure:

- File writes use a **file lock** (e.g., `threading.Lock` for threads within a process, `fcntl.flock` or a Redis-based lock for cross-process safety).
- CSV append operations are atomic — open in append mode with proper locking.

If `FileService` doesn't already handle this, add a Redis-based distributed lock:

```python
import redis

class FileService:
    _write_lock = threading.Lock()  # thread-level lock

    async def add_data_to_csv(self, file_name, data, fieldnames):
        with self._write_lock:
            # ... existing write logic ...
```

---

## File Change Summary

| File | Action |
|------|--------|
| `app/workers/concurrent_worker.py` | **Create** — shared `ConcurrentWorker` class |
| `workers/start_algorithm_worker.py` | **Edit** — remove inline class, import shared one |
| `workers/start_result_worker.py` | **Edit** — replace `rq.Worker` with `ConcurrentWorker` |
| `workers/start_file_write_worker.py` | **Edit** — replace `rq.Worker` with `ConcurrentWorker` |
| `app/config/queue_config.py` | **Edit** — add per-type `get_concurrent_tasks()` |
| `docker-compose.yml` | **Edit** — pass new env vars |
| `.env` | **Edit** — add per-type concurrent task settings |
| `app/services/file_service.py` | **Audit** — ensure thread-safe CSV writes |

---

## Verification Checklist

- [ ] All 3 worker types use `ConcurrentWorker` when `concurrent_tasks > 1`
- [ ] Async task functions (`async def`) are properly awaited in all workers
- [ ] Each worker process spawns `concurrent_tasks` threads via `ThreadPoolExecutor`
- [ ] Multiple worker processes for the same queue safely compete for jobs via `lpop`
- [ ] File writes to `Automated Results.csv` are thread/process-safe
- [ ] Logs show `"Concurrent Worker X started with Y threads"` for each worker type
- [ ] With 33 genomes / 4 workers / 10 threads: all 33 tasks start processing immediately
- [ ] Fallback to standard `rq.Worker` when `concurrent_tasks=1`
