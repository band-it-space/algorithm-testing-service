import os
import uuid
from datetime import datetime, date
from typing import Dict, List
from app.config.queue_config import algorithm_calculation_queue, result_processing_queue,us_king_calculation_queue

class QueueService:
    @staticmethod
    def add_to_king_algorithm_queue(stock_code: str) -> str:
        """
        US King Algorithm
        """
        task_id = str(uuid.uuid4())
        
        task_data = {
            "task_id": task_id,
            "stock": stock_code,
            "created_at": datetime.now().isoformat(),
            "queue_name": "us_king_calculation"
        }
        
        job = us_king_calculation_queue.enqueue(
            'app.workers.us_king_worker.process_us_king_task',
            task_data,
            job_id=task_id
        )
        
        return task_id

    @staticmethod
    def add_to_algorithm_queue(stock_code: str) -> str:
        """
        HK Algorithm
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
        Result Processing
        """
        task_id = str(uuid.uuid4())
        
        processing_data = {
            "task_id": task_id,
            "stock_code": stock_code,
        }
        
        job = result_processing_queue.enqueue(
            'app.workers.result_worker.process_result_task',
            processing_data,
            job_id=task_id
        )
        
        return task_id

    @staticmethod
    def add_to_file_write_queue(stock_code: str, results_data, field_names) -> str:
        """
        File Write
        """
        task_id = str(uuid.uuid4())
        
        processing_data = {
            "task_id": task_id,
            "stock_code": stock_code,
            "results_data": results_data,
            "field_names": field_names,
        }
        
        job = result_processing_queue.enqueue(
            'app.workers.file_write_worker.process_file_write_task',
            processing_data,
            job_id=task_id
        )
        
        return task_id