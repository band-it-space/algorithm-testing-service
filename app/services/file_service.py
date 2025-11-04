import csv
import os
import logging

logger = logging.getLogger(__name__)

class FileService:
    def __init__(self):
        self.data_dir =  "data"

    def _read_existing_header(self, file_path: str) -> list[str] | None:
        if not os.path.exists(file_path) or os.stat(file_path).st_size == 0:
            return None
        try:
            with open(file_path, 'r', newline='', encoding='utf-8') as f:
                reader = csv.reader(f)
                header = next(reader, None)
                return header
        except Exception:
            return None
        
    async def add_data_to_csv(self, file_name: str, data: list, fieldnames: list):
        try:
            logger.info(f"Data to be written to {file_name}.csv: {data}")
            file_path = f"{self.data_dir}/{file_name}.csv"
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            existing_header = self._read_existing_header(file_path)

            if existing_header is not None and existing_header == list(fieldnames):
                mode = 'a'
                write_header = False
            else:
                # No header or schema changed → rewrite with new header
                mode = 'w'
                write_header = True
                if existing_header is not None:
                    logger.warning(
                        f"Header mismatch in {file_path}. "
                        f"Old: {existing_header} -> New: {list(fieldnames)}. Rewriting file."
                    )

            with open(file_path, mode, newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                if write_header:
                    writer.writeheader()
                for row in data:
                    writer.writerow(row)

            action = "rewritten" if write_header else "appended"
            logger.info(f"Successfully {action} {file_path} with {len(data)} records")
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