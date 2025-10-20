#!/usr/bin/env python3
"""
Скрипт для запуску воркера алгоритмів (перша черга)
"""
import sys
import os
import logging

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rq import Worker, Connection
from app.config.logging_config import setup_logging
from app.config.queue_config import redis_conn, algorithm_calculation_queue

def main():
    """
    Запускає воркера для обробки алгоритмів
    """
    setup_logging()
    logger = logging.getLogger("app.workers.algorithm_worker")
    logger.info("Starting Algorithm Worker...")
    logger.info(f"Redis connection: {redis_conn}")
    logger.info("Queue: algorithm_calculation")
    
    with Connection(redis_conn):
        worker = Worker([algorithm_calculation_queue])
        logger.info("Algorithm worker started. Press Ctrl+C to stop.")
        worker.work()

if __name__ == '__main__':
    main()
