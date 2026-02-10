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
