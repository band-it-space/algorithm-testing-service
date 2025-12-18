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
        logger.info("------------------------------" )
        logger.info(f"Processing file write task: {task_data}")
        # stock_code = task_data.get('stock_code')
        # missed_db = task_data.get('missed_db', [])
        # missed_api = task_data.get('missed_api', [])
        # total_api = task_data.get('total_api', 0)
        # total_db = task_data.get('total_db', 0)
        # total_db_from_2019 = task_data.get('sorted_db', 0)
        # total_api_from_2019 = task_data.get('sorted_api', 0)
        
        

        # #TODO Version for missed data
        # fields_names_all = ['stock', 'total_api', 'total_db', "total_api_from_2019", "total_db_from_2019", 'missed_db', 'missed_api']

        # await file_service.add_data_to_csv("checked_all",
        #     [{
        #         'stock': stock_code,
        #         'total_api':total_api, 
        #         'total_db': total_db, 
        #         'missed_api': len(missed_api), 
        #         'missed_db': len(missed_db),
        #         "total_db_from_2019":total_db_from_2019,
        #         "total_api_from_2019": total_api_from_2019
        #     }], fields_names_all)

        # fields_names_with_dates = ['stock', 'missed_db', 'missed_api']

        # def format_dates(dates, stock, key):
        #     return [
        #         {"stock": stock, "missed_db": "-", "missed_api": "-",
        #             key: d.strftime("%Y-%m-%d")}
        #         for d in dates
        #     ]

        # updated_missed_api = format_dates(missed_api, stock_code, "missed_api")
        # updated_missed_db = format_dates(missed_db, stock_code, "missed_db")

        # await file_service.add_data_to_csv("checked_all_dates",
        #     updated_missed_api + updated_missed_db, 
        #     fields_names_with_dates)
        #!OLD
        results_data = task_data.get('results_data', [])
        field_names = task_data.get('field_names', [])
        stock_code = task_data.get('stock_code')
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
