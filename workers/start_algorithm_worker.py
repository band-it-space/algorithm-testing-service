#!/usr/bin/env python3
"""
Скрипт для запуску воркера алгоритмів (перша черга)
With support for concurrent tasks per worker using ThreadPoolExecutor
"""
import sys
import os
import logging
import multiprocessing
import signal
import time
import asyncio
import inspect
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rq import Worker, Connection, SimpleWorker
from rq.job import Job
from app.config.logging_config import setup_logging
from app.config.queue_config import (
    redis_conn, 
    algorithm_calculation_queue, 
    get_worker_count,
    get_concurrent_tasks
)
from app.workers.concurrent_worker import ConcurrentWorker


def run_concurrent_worker(worker_id: int, concurrent_tasks: int):
    """
    Run a concurrent worker that processes multiple jobs simultaneously.
    """
    setup_logging()
    worker = ConcurrentWorker(
        queue=algorithm_calculation_queue,
        concurrent_tasks=concurrent_tasks,
        worker_id=worker_id,
        logger_name="app.workers.algorithm_worker"
    )
    worker.work()


def run_standard_worker():
    """
    Запускає стандартного воркера RQ для обробки алгоритмів (fallback when concurrent_tasks=1)
    """
    setup_logging()
    logger = logging.getLogger("app.workers.algorithm_worker")
    from rq import Worker
    from redis import Redis
    worker = Worker([algorithm_calculation_queue], connection=redis_conn)
    worker.work()


processes = []


def main():
    worker_count = get_worker_count("algorithm")
    concurrent_tasks = get_concurrent_tasks("algorithm")

    logger = logging.getLogger("app.workers.algorithm_worker")
    logger.info(
        f"Starting {worker_count} algorithm worker(s) "
        f"with {concurrent_tasks} concurrent tasks each"
    )

    for i in range(worker_count):
        if concurrent_tasks > 1:
            # Use concurrent worker for multiple tasks per worker
            p = multiprocessing.Process(
                target=run_concurrent_worker,
                args=(i, concurrent_tasks),
                name=f"algorithm-worker-{i}"
            )
        else:
            # Use standard RQ worker for single task processing
            p = multiprocessing.Process(
                target=run_standard_worker,
                name=f"algorithm-worker-{i}"
            )
        p.start()
        processes.append(p)

    def signal_handler(sig, frame):
        logger.info("Shutting down algorithm workers...")
        for p in processes:
            p.terminate()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    for p in processes:
        p.join()


if __name__ == "__main__":
    setup_logging()
    main()
