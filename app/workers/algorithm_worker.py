import time
import logging
from datetime import datetime
from app.services.queue_service import QueueService

logger = logging.getLogger(__name__)

def process_algorithm_task(task_data):
    """
    Воркер для обробки алгоритмів (перша черга)
    Тут ви додасте свою логіку розрахунків
    """

    try:
        logger.info(f"Processing algorithm task: {task_data['task_id']}")
        
        # ТУТ ЛОГІКА РОЗРАХУНКІВ
        # Приклад заглушки:
        stock_code = task_data['stock']
        
        # Симуляція роботи алгоритму
        time.sleep(2)  

        
        # Додаємо результат до другої черги
        processing_task_id = QueueService.add_to_result_processing_queue(stock_code)
        
        logger.info(f"Algorithm task {task_data['task_id']} completed, added to processing queue: {processing_task_id}")
        
        return task_data
        
    except Exception as e:
        logger.error(f"Error processing algorithm task {task_data['task_id']}: {str(e)}")
        raise e
