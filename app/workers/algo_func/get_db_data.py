import os
import aiomysql
import asyncio
from dotenv import load_dotenv




import requests
from datetime import datetime, date
from typing import Any, Dict, List, Optional

load_dotenv()

# API configuration
API_KEY = os.getenv('API_KEY')

# dbconfig = {

# dbconfig = {
#     "host": "poc-kl.cluster-cgbcqc4g9atp.ap-southeast-1.rds.amazonaws.com",
#     "user": "reader",
#     "password": "OuWoje3zea",
#     "db": "derivates_crawler",
#     "port": 3306,
# }


# #! CHEN
dbconfig = {
    "host": 'mdbinstance-cluster.cluster-cgbcqc4g9atp.ap-southeast-1.rds.amazonaws.com',
    "user": 'mdb_admin',
    "password": 'Gc5H9EEevfhbo16n',
    "db": 'mdb_v2',
    "port": 3306,
}




# Глобальний пул, створюється один раз
pool: aiomysql.Pool | None = None


async def init_db_pool():
    """Ініціалізує глобальний пул з'єднань."""
    global pool
    if pool is None:
        pool = await aiomysql.create_pool(
            minsize=1,
            maxsize=20,
            **dbconfig,
        )
        print("✅ MySQL connection pool initialized")

async def get_stock_data_from_db(code: str, end_date: str | None = None):
    """Отримати дані про акції з API."""
    if not API_KEY:
        raise RuntimeError("STOCKFISHER_API_KEY not found in environment variables")
    
    API_URL = f'http://ete.stockfisher.com.hk/v1.1/debugHKEX/verifyData?TradeDay=&Code={code}&verifyType=price'
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
