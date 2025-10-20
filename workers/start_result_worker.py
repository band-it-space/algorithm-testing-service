#!/usr/bin/env python3
"""
Скрипт для запуску воркера обробки результатів (друга черга)
"""
import sys
import os
import logging

# Додаємо корінь проекту до Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rq import Worker, Connection
from app.config.logging_config import setup_logging
from app.config.queue_config import redis_conn, result_processing_queue

def main():
    """
    Запускає воркера для обробки результатів
    """
    setup_logging()
    logger = logging.getLogger("app.workers.result_worker")
    logger.info("Starting Result Processing Worker...")
    logger.info(f"Redis connection: {redis_conn}")
    logger.info("Queue: result_processing")
    
    with Connection(redis_conn):
        worker = Worker([result_processing_queue])
        logger.info("Result processing worker started. Press Ctrl+C to stop.")
        worker.work()

if __name__ == '__main__':
    main()
