#!/usr/bin/env python3
"""
Скрипт для запуску воркера запису файлів
"""
import sys
import os
import logging
import multiprocessing
import signal

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rq import Worker

from app.workers.concurrent_worker import ConcurrentWorker
from app.config.queue_config import (
    redis_conn, file_write_queue,
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
        queue=file_write_queue,
        concurrent_tasks=concurrent_tasks,
        worker_id=worker_id,
        logger_name="app.workers.file_write_worker"
    )
    worker.work()


def run_standard_worker():
    setup_logging()
    logger = logging.getLogger("app.workers.file_write_worker")
    logger.info("Starting standard file-write worker (single-threaded)")
    worker = Worker([file_write_queue], connection=redis_conn)
    worker.work()


processes = []


def main():
    worker_count = get_worker_count("file")
    concurrent_tasks = get_concurrent_tasks("file")

    logger = logging.getLogger("app.workers.file_write_worker")
    logger.info(
        f"Starting {worker_count} file-write worker(s) "
        f"with {concurrent_tasks} concurrent tasks each"
    )

    for i in range(worker_count):
        if concurrent_tasks > 1:
            p = multiprocessing.Process(
                target=run_concurrent_worker,
                args=(i, concurrent_tasks),
                name=f"file-write-worker-{i}"
            )
        else:
            p = multiprocessing.Process(
                target=run_standard_worker,
                name=f"file-write-worker-{i}"
            )
        p.start()
        processes.append(p)

    def signal_handler(sig, frame):
        logger.info("Shutting down file-write workers...")
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
