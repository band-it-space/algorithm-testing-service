#!/usr/bin/env python3
"""
Скрипт для запуску воркера запису файлів
"""
import sys
import os
import logging

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rq import Worker, Connection
from app.config.logging_config import setup_logging
from app.config.queue_config import redis_conn, file_write_queue
from app.workers.file_write_worker import process_file_write_task

def main():
    """
    Запускає воркера для запису файлів
    """
    setup_logging()
    logger = logging.getLogger("app.workers.file_write_worker")
    logger.info("Starting File Write Worker...")
    logger.info(f"Redis connection: {redis_conn}")
    logger.info("Queue: file_write")
    
    with Connection(redis_conn):
        worker = Worker([file_write_queue])
        logger.info("File write worker started. Press Ctrl+C to stop.")
        worker.work()

if __name__ == '__main__':
    main()
