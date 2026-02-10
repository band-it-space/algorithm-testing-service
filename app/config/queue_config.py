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

def get_worker_count(worker_type: str = "algorithm") -> int:
    """Get number of worker processes for a given worker type."""
    env_map = {
        "algorithm": "ALGORITHM_WORKER_COUNT",
        "result": "RESULT_WORKER_COUNT",
        "file": "FILE_WORKER_COUNT",
    }
    env_var = env_map.get(worker_type, "ALGORITHM_WORKER_COUNT")
    return int(os.getenv(env_var, "1"))


def get_concurrent_tasks(worker_type: str = "algorithm") -> int:
    """Get number of concurrent tasks (threads) per worker process."""
    env_map = {
        "algorithm": "ALGORITHM_CONCURRENT_TASKS",
        "result": "RESULT_CONCURRENT_TASKS",
        "file": "FILE_CONCURRENT_TASKS",
    }
    env_var = env_map.get(worker_type, "ALGORITHM_CONCURRENT_TASKS")
    # Fall back to generic WORKER_CONCURRENT_TASKS, then to 1
    return int(os.getenv(env_var, os.getenv("WORKER_CONCURRENT_TASKS", "1")))

algorithm_calculation_queue = Queue('algorithm_calculation', connection=redis_conn, default_timeout=ALGORITHM_WORKER_TIMEOUT)

result_processing_queue = Queue('result_processing', connection=redis_conn)

file_write_queue = Queue('file_write', connection=redis_conn)
