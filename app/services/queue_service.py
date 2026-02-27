import os
import uuid
import json
import logging
from datetime import datetime
from typing import Any

import redis
from rq import Queue

logger = logging.getLogger(__name__)


class QueueService:
    """Service for managing task queues with Redis."""
    
    _redis_client: redis.Redis | None = None
    _algorithm_queue: Queue | None = None
    _result_queue: Queue | None = None
    _file_write_queue: Queue | None = None
    
    ALGORITHM_QUEUE = "algorithm_calculation"
    RESULT_PROCESSING_QUEUE = "result_processing"
    FILE_WRITE_QUEUE = "file_write"
    
    @classmethod
    def get_redis_client(cls) -> redis.Redis:
        if cls._redis_client is None:
            redis_host = os.getenv("REDIS_HOST", "localhost")
            redis_port = int(os.getenv("REDIS_PORT", 6379))
            redis_db = int(os.getenv("REDIS_DB", 0))
            cls._redis_client = redis.Redis(
                host=redis_host,
                port=redis_port,
                db=redis_db,
                decode_responses=False  # RQ needs bytes
            )
        return cls._redis_client
    
    @classmethod
    def get_algorithm_queue(cls) -> Queue:
        if cls._algorithm_queue is None:
            client = cls.get_redis_client()
            timeout = int(os.getenv("ALGORITHM_WORKER_TIMEOUT", 1000))
            cls._algorithm_queue = Queue(cls.ALGORITHM_QUEUE, connection=client, default_timeout=timeout)
        return cls._algorithm_queue
    
    @classmethod
    def get_result_queue(cls) -> Queue:
        if cls._result_queue is None:
            client = cls.get_redis_client()
            timeout = int(os.getenv("RESULT_WORKER_TIMEOUT", 300))
            cls._result_queue = Queue(cls.RESULT_PROCESSING_QUEUE, connection=client, default_timeout=timeout)
        return cls._result_queue
    
    @classmethod
    def get_file_write_queue(cls) -> Queue:
        if cls._file_write_queue is None:
            client = cls.get_redis_client()
            timeout = int(os.getenv("FILE_WRITE_WORKER_TIMEOUT", 60))
            cls._file_write_queue = Queue(cls.FILE_WRITE_QUEUE, connection=client, default_timeout=timeout)
        return cls._file_write_queue
    
    @classmethod
    def add_to_algorithm_queue(
        cls,
        stock_code: str,
        genome_id: str = "G_000",
        parameters: dict[str, Any] | None = None,
        optimization_id: str | None = None
    ) -> str:
        """Add a task to the algorithm processing queue."""
        from app.workers.algorithm_worker import process_algorithm_task
        
        task_data = {
            "task_id": str(uuid.uuid4()),
            "stock": stock_code,
            "genome_id": genome_id,
            "parameters": parameters or {},
            "optimization_id": optimization_id,
            "created_at": datetime.now().isoformat(),
        }
        
        queue = cls.get_algorithm_queue()
        job = queue.enqueue(process_algorithm_task, task_data)
        
        logger.info(f"Added task {task_data['task_id']} to algorithm queue: stock={stock_code}, genome={genome_id}")
        
        return job.id
    
    @classmethod
    def add_to_result_processing_queue(
        cls,
        stock_code: str,
        genome_id: str = "G_000",
        parameters: dict[str, Any] | None = None,
        optimization_id: str | None = None,
        results: dict[str, Any] | None = None
    ) -> str:
        """Add a task to the result processing queue."""
        from app.workers.result_worker import process_result_task
        
        task_id = str(uuid.uuid4())
        task_data = {
            "task_id": task_id,
            "stock": stock_code,
            "genome_id": genome_id,
            "parameters": parameters or {},
            "optimization_id": optimization_id,
            "results": results or {},
            "created_at": datetime.now().isoformat(),
        }
        
        queue = cls.get_result_queue()
        job = queue.enqueue(process_result_task, task_data)
        logger.info(f"Added task {task_id} to result processing queue: stock={stock_code}, genome={genome_id}")
        
        return task_id
    
    @classmethod
    def add_to_file_write_queue(
        cls,
        stock_code: str,
        genome_id: str = "G_000",
        data: dict[str, Any] | None = None,
        optimization_id: str | None = None
    ) -> str:
        """Add a task to the file write queue."""
        from app.workers.file_write_worker import process_file_write_task
        
        task_id = str(uuid.uuid4())
        task_data = {
            "task_id": task_id,
            "stock_code": stock_code,
            "genome_id": genome_id,
            "data": data or {},
            "optimization_id": optimization_id,
            "created_at": datetime.now().isoformat(),
        }
        
        queue = cls.get_file_write_queue()
        job = queue.enqueue(process_file_write_task, task_data)
        logger.info(f"Added task {task_id} to file write queue: stock={stock_code}, genome={genome_id}")
        
        return task_id
    
    @classmethod
    def get_from_queue(cls, queue_name: str, timeout: int = 0) -> dict[str, Any] | None:
        """Get a task from the specified queue."""
        client = cls.get_redis_client()
        
        if timeout > 0:
            result = client.blpop(queue_name, timeout=timeout)
            if result:
                _, data = result
                return json.loads(data)
        else:
            data = client.lpop(queue_name)
            if data:
                return json.loads(data)
        
        return None
    
    @classmethod
    def get_queue_length(cls, queue_name: str) -> int:
        """Get the number of tasks in a queue."""
        client = cls.get_redis_client()
        return client.llen(queue_name)
    
    @classmethod
    def add_batch_to_algorithm_queue(
        cls,
        tasks: list[dict[str, Any]]
    ) -> list[str]:
        """Add multiple tasks to the algorithm queue efficiently."""
        from app.workers.algorithm_worker import process_algorithm_task
        
        queue = cls.get_algorithm_queue()
        job_ids = []
        
        for task in tasks:
            task_data = {
                "task_id": str(uuid.uuid4()),
                "stock": task.get("stock"),
                "genome_id": task.get("genome_id", "G_000"),
                "parameters": task.get("parameters", {}),
                "optimization_id": task.get("optimization_id"),
                "created_at": datetime.now().isoformat(),
            }
            job = queue.enqueue(process_algorithm_task, task_data)
            job_ids.append(job.id)
        
        logger.info(f"Added {len(job_ids)} tasks to algorithm queue in batch")
        
        return job_ids
