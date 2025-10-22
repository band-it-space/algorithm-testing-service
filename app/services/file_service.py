import csv
import os
import logging

logger = logging.getLogger(__name__)

class FileService:
    def __init__(self):
        self.data_dir =  "data"
    
    def add_data_to_csv(self, file_name: str, data: list, fieldnames: list):
        try:
            file_path = f"{self.data_dir}/{file_name}.csv"
            os.makedirs(os.path.dirname(file_path), exist_ok=True)

            with open(file_path, 'a', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                
                if os.stat(file_path).st_size == 0:
                    writer.writeheader()
                for row in data:
                    writer.writerow(row)
            
            logger.info(f"Successfully created {file_path} with {len(data)} records")
            return True
            
        except Exception as e:
            logger.error(f"Error creating CSV file {file_path}: {e}")
            return False

    async def clear_file_content(self, file_name: str):
        try:
            file_path = f"{self.data_dir}/{file_name}.csv"
            if os.path.exists(file_path):
                with open(file_path, 'w') as file:
                    pass
                logger.info(f"Successfully cleared content of {file_path}")
                return True
            else:
                logger.warning(f"File {file_path} does not exist")
                return False
                
        except Exception as e:
            logger.error(f"Error clearing file {file_path}: {e}")
            return False
    
    async def read_data_from_csv(self, file_name: str) -> list:
        try:
            file_path = f"{self.data_dir}/{file_name}.csv"
            
            if not os.path.exists(file_path):
                logger.warning(f"File {file_path} does not exist")
                return []
            
            data = []
            with open(file_path, 'r', newline='', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    data.append(row)
            
            logger.info(f"Successfully read {len(data)} records from {file_path}")
            return data
        except Exception as e:
            logger.error(f"Error reading CSV file {file_path}: {e}")
            return []