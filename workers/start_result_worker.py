#!/usr/bin/env python3
"""
Скрипт для запуску воркера обробки результатів (друга черга)
"""
import sys
import os
import logging
import multiprocessing
import signal
import rq

# Додаємо корінь проекту до Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.workers.concurrent_worker import ConcurrentWorker
from app.config.queue_config import (
    redis_conn, result_processing_queue,
    get_worker_count, get_concurrent_tasks
)

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
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
    logger.info("Starting standard result worker (single-threaded)")
    worker = Worker([result_processing_queue], connection=redis_conn)
    worker.work()

def main():
    worker_count = get_worker_count("result")
    concurrent_tasks = get_concurrent_tasks("result")

    logger = logging.getLogger("app.workers.result_worker")
    logger.info(
        f"Starting {worker_count} result worker(s) "
        f"with {concurrent_tasks} concurrent tasks each"
    )

    processes = []
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

    def signal_handler(sig, frame):
        logger.info("Shutting down result workers...")
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
