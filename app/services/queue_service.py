import os
import uuid
from datetime import datetime
from typing import Dict, Any
from app.config.queue_config import algorithm_calculation_queue, result_processing_queue
from app.models.algorithm_models import AlgorithmRequest, QueueTask

class QueueService:

    @staticmethod
    def add_to_algorithm_queue(stock_code: str) -> str:
        """
        Додає завдання до першої черги (algorithm_calculation)
        """
        task_id = str(uuid.uuid4())
        
        task_data = {
            "task_id": task_id,
            "stock": stock_code,
            "created_at": datetime.now().isoformat(),
            "queue_name": "algorithm_calculation"
        }
        
        job = algorithm_calculation_queue.enqueue(
            'app.workers.algorithm_worker.process_algorithm_task',
            task_data,
            job_id=task_id
        )
        
        return task_id
    
    @staticmethod
    def add_to_result_processing_queue(stock_code: str) -> str:
        """
        Додає результат до другої черги (result_processing)
        """
        task_id = str(uuid.uuid4())
        
        processing_data = {
            "task_id": task_id,
            "stock_code": stock_code,
        }
        
        # Додаємо завдання до черги обробки результатів
        job = result_processing_queue.enqueue(
            'app.workers.result_worker.process_result_task',
            processing_data,
            job_id=task_id
        )
        
        return task_id
    
    @staticmethod
    def add_to_file_write_queue(stock_code: str, results_data, field_names) -> str:
        """
        Додає результат до другої черги (file_write)
        """
        task_id = str(uuid.uuid4())
        
        processing_data = {
            "task_id": task_id,
            "stock_code": stock_code,
            "results_data": results_data,
            "field_names": field_names,
        }
        
        # Додаємо завдання до черги обробки результатів
        job = result_processing_queue.enqueue(
            'app.workers.file_write_worker.process_file_write_task',
            processing_data,
            job_id=task_id
        )
        
        return task_id
    
    

    @staticmethod
    def get_queue_status():
        """
        Повертає статус черг
        """
        return {
            "algorithm_calculation_queue": {
                "pending_jobs": len(algorithm_calculation_queue),
                "failed_jobs": len(algorithm_calculation_queue.failed_job_registry),
                "completed_jobs": len(algorithm_calculation_queue.completed_job_registry)
            },
            "result_processing_queue": {
                "pending_jobs": len(result_processing_queue),
                "failed_jobs": len(result_processing_queue.failed_job_registry),
                "completed_jobs": len(result_processing_queue.completed_job_registry)
            }
        }
