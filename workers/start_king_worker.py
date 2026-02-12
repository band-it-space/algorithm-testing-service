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
from app.config.queue_config import redis_conn, us_king_calculation_queue

def main():
    """
    Запускає воркера для обробки алгоритмів US_King
    """
    setup_logging()
    logger = logging.getLogger("app.workers.us_king_calculation_queue")
    logger.info("Starting US_King Calculation Worker...")
    logger.info(f"Redis connection: {redis_conn}")
    logger.info("Queue: us_king_calculation")

    with Connection(redis_conn):
        worker = Worker([us_king_calculation_queue])
        logger.info("US_King Calculation Worker started. Press Ctrl+C to stop.")
        worker.work()

if __name__ == '__main__':
    main()
