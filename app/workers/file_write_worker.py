import csv
import os
import logging

from app.services.file_service import FileService
logger = logging.getLogger(__name__)
file_service = FileService()
# def write_results_to_csv(stock_code: str, results_data: List[Dict[str, Any]], fieldnames: List[str]):
#     """
#     Безпечно записує результати в CSV файл
#     """
#     try:
#         data_dir = "data"
#         file_path = f"{data_dir}/results.csv"
#         os.makedirs(os.path.dirname(file_path), exist_ok=True)

#         with open(file_path, 'a', newline='', encoding='utf-8') as csvfile:
#             writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
#             # Записуємо заголовок тільки якщо файл порожній
#             if os.stat(file_path).st_size == 0:
#                 writer.writeheader()
            
#             # Записуємо дані
#             for row in results_data:
#                 writer.writerow(row)
        
#         logger.info(f"Successfully wrote {len(results_data)} records to {file_path} for stock {stock_code}")
#         return True
        
#     except Exception as e:
#         logger.error(f"Error writing results to CSV for stock {stock_code}: {e}")
#         return False

def process_file_write_task(task_data):
    """
    Обробляє завдання запису файлу з черги
    """
    try:
        stock_code = task_data.get('stock_code')
        results_data = task_data.get('results_data', [])
        field_names = task_data.get('field_names', [])

        logger.info("------------------------------" )
        logger.info(f"Processing file write task for stock: {stock_code}")
        logger.info(f"results_data: {results_data}")
        logger.info(f"field_names: {field_names}")
        
        success = file_service.add_data_to_csv("results", results_data, field_names)
        
        if success:
            logger.info(f"File write task completed successfully for stock: {stock_code}")
        else:
            logger.error(f"File write task failed for stock: {stock_code}")
            
        return {"success": success, "stock_code": stock_code}
        
    except Exception as e:
        logger.error(f"Error processing file write task: {str(e)}")
        return {"success": False, "error": str(e)}
