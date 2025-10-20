import requests
import pandas as pd
import io
import re
from datetime import datetime
from typing import List, Dict


def extract_date_from_text(text: str) -> str | None:
    date_pattern = r'(\d{2}/\d{2}/\d{4})'
    match = re.search(date_pattern, text)
    if match:
        return match.group(1)
    return None

def is_date_today(date_str: str) -> bool:
    try:
        file_date = datetime.strptime(date_str, "%d/%m/%Y")
        today = datetime.now()
        
        return file_date.date() == today.date()
    except ValueError:
        return False

def is_numeric_code(value: str) -> bool:
    try:
        code = int(value.strip())
        return code <= 9999
    except ValueError:
        return False

exclude_ranges = [
    (2900, 2999),
    (4000, 4199),
    (4200, 4299),
    (4300, 4329),
    (4400, 4599),
    (4600, 4699),
    (4700, 4799),
    (4800, 4999),
    (5000, 6029),
    (6200, 6299),
    (6750, 7699),
    (7800, 7999),
    (8510, 8600),
]

async def get_stocks_codes() -> list[str]:
    try:
        url = "https://www.hkex.com.hk/eng/services/trading/securities/securitieslists/ListOfSecurities.xlsx"
        
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        excel_content = io.BytesIO(response.content)
        
        df = pd.read_excel(excel_content, skiprows=1, header=None)
        
        if len(df.columns) > 0:
    
            
            first_column = df.iloc[:, 0]
            
            stock_codes = []
            for value in first_column:
                if pd.notna(value) and str(value).strip() and is_numeric_code(value.strip()):
                    stock_codes.append(str(value).strip())
            
            return [code for code in stock_codes if not any(start <= int(code) <= end for start, end in exclude_ranges)]
            
        else:
            return []
            
    except requests.RequestException as e:
        return  []
    except Exception as e:
        return []
        