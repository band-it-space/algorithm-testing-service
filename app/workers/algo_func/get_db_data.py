import os
from dotenv import load_dotenv

import requests
from datetime import datetime

load_dotenv()

# API configuration
API_KEY = os.getenv('API_KEY')
US_KING_API_KEY = os.getenv('US_KING_API_KEY')
STOCKFISHER_URL = os.getenv('STOCKFISHER_URL')


async def get_stock_data_from_db(code: str, end_date: str | None = None):
    if not API_KEY or not STOCKFISHER_URL:
        raise RuntimeError("STOCKFISHER_API_KEY or STOCKFISHER_URL not found in environment variables")
    
    API_URL = f'{STOCKFISHER_URL}/v1.1/debugHKEX/verifyData?TradeDay=&Code={code}&verifyType=price'
    headers = {'x-api-key': API_KEY}
    
    try:
        response = requests.get(API_URL, headers=headers)
        response.raise_for_status()
        stock_data_api = response.json()
    except requests.RequestException as e:
        print(f"❌ Error fetching data from API: {e}")
        return []
    
    stock_records = []
    for row in stock_data_api:
        trade_date = datetime.fromisoformat(row["TradeDay"].replace('Z', '+00:00')).strftime("%Y-%m-%d")
        
        if end_date and trade_date > end_date:
            continue
            
        adj_open = row.get("adj_open") or 0
        adj_high = row.get("adj_high") or 0
        adj_low = row.get("adj_low") or 0
        adj_close = row.get("adj_close") or 0
        adj_volume = row.get("adj_volume") or 0
        
        if (adj_open > 0 and 
            adj_high > 0 and 
            adj_low > 0 and 
            adj_close > 0 and 
            adj_volume > 0):
            
            stock_records.append({
                "date": trade_date,
                "time": "00:00:00",
                "open": float(adj_open),
                "high": float(adj_high),
                "low": float(adj_low),
                "close": float(adj_close),
                "volume": int(adj_volume),
            })
    
    stock_records.sort(key=lambda x: x["date"])
    
    empty_records = [rec for rec in stock_records if rec["open"] == 0]
    if empty_records:
        print("⚠️ Empty records found at dates:", ", ".join(rec["date"] for rec in empty_records))
    
    stock_records = [rec for rec in stock_records if rec not in empty_records]
        
    return stock_records

async def us_api_stocks_data(code: str, end_date: str | None = None, verify_type: str = "price", trade_day: str = ""):
    if not US_KING_API_KEY or not STOCKFISHER_URL:
        raise RuntimeError("US_KING_API_KEY or STOCKFISHER_URL not found in environment variables")
    
    API_URL = f'{STOCKFISHER_URL}/v1.1/debugUSStock/verifyData?TradeDay={trade_day}&Code={code}&verifyType={verify_type}'
    headers = {'x-api-key': US_KING_API_KEY}
    
    try:
        response = requests.get(API_URL, headers=headers)
        response.raise_for_status()
        stock_data_api = response.json()
    except requests.RequestException as e:
        print(f"❌ Error fetching data from API: {e}")
        return []
    
    stock_records = []
    if verify_type == "price":
        for row in stock_data_api:
            trade_date = datetime.fromisoformat(row["TradeDay"].replace('Z', '+00:00')).strftime("%Y-%m-%d")
        
            if end_date and trade_date > end_date:
                continue
                
            adj_open = row.get("Open") or 0
            adj_high = row.get("High") or 0
            adj_low = row.get("Low") or 0
            adj_close = row.get("Close") or 0
            adj_volume = row.get("Volume") or 0
            
            if (adj_open > 0 and 
                adj_high > 0 and 
                adj_low > 0 and 
                adj_close > 0 and 
                adj_volume > 0):
                
                stock_records.append({
                    "date": trade_date,
                    "time": "00:00:00",
                    "open": float(adj_open),
                    "high": float(adj_high),
                    "low": float(adj_low),
                    "close": float(adj_close),
                    "volume": int(adj_volume),
                })
    
        stock_records.sort(key=lambda x: x["date"])
    
        empty_records = [rec for rec in stock_records if rec["open"] == 0]
        if empty_records:
            print("⚠️ Empty records found at dates:", ", ".join(rec["date"] for rec in empty_records))
    
        stock_records = [rec for rec in stock_records if rec not in empty_records]
    else:
        for row in stock_data_api:
            
            trade_date = datetime.fromisoformat(row["tradeday"].replace('Z', '+00:00')).strftime("%Y-%m-%d")

            if end_date and trade_date > end_date:
                continue
            
            entry_date = None
            if row.get("entry_date"):
                entry_date = datetime.fromisoformat(row["entry_date"].replace('Z', '+00:00')).strftime("%Y-%m-%d")


            stock_records.append({
                "date": trade_date,
                "time": "00:00:00",
                "position_status": row.get("position_status", ""),
                "entry_date": entry_date,

                "next_open_action": row.get("next_open_action", ""),
                "today_open_action": row.get("today_open_action", ""),
                
                "exit1": row.get("exit1", ""),
                "entry_price": row.get("entry_price", 0),
            })
    
        stock_records.sort(key=lambda x: x["date"])
    return stock_records
