import csv
import os
import logging

from app.services.file_service import FileService
logger = logging.getLogger(__name__)
file_service = FileService()

async def process_file_write_task(task_data):
    """
    Обробляє завдання запису файлу з черги
    """
    try:
        stock_code = task_data.get('stock_code')
        results_data = task_data.get('results_data', [])
        field_names = task_data.get('field_names', [])

        logger.info("------------------------------" )
        logger.info(f"Processing file write task for stock: {stock_code}")
        
        success = await file_service.add_data_to_csv("results", results_data, field_names)
        
        if success:
            logger.info(f"File write task completed successfully for stock: {stock_code}")
        else:
            logger.error(f"File write task failed for stock: {stock_code}")
            
        return {"success": success, "stock_code": stock_code}
        
    except Exception as e:
        logger.error(f"Error processing file write task: {str(e)}")
        return {"success": False, "error": str(e)}
