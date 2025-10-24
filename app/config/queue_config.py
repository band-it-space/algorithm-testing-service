import os
from redis import Redis
from rq import Queue

# Redis configuration
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
REDIS_DB = int(os.getenv('REDIS_DB', 0))
REDIS_PASSWORD = os.getenv('REDIS_PASSWORD', None)

# Create Redis connection
if REDIS_PASSWORD:
    redis_conn = Redis(
        host=REDIS_HOST, 
        port=REDIS_PORT, 
        db=REDIS_DB, 
        password=REDIS_PASSWORD
    )
else:
    redis_conn = Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB)

# Queue configuration
ALGORITHM_WORKER_TIMEOUT = int(os.getenv('ALGORITHM_WORKER_TIMEOUT', 1000))

algorithm_calculation_queue = Queue('algorithm_calculation', connection=redis_conn, default_timeout=ALGORITHM_WORKER_TIMEOUT)

result_processing_queue = Queue('result_processing', connection=redis_conn)

file_write_queue = Queue('file_write', connection=redis_conn)
