import os
import aiomysql
import asyncio
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

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

# тут робимо запит за даними акцій 
async def get_stock_data_from_db(code: str, end_date: str | None = None):
    """Отримати дані про акції асинхронно з БД."""
    global pool
    if pool is None:
        raise RuntimeError("Database pool not initialized. Call init_d b_pool() first.")
    
    #query = f"CALL get_symbol_adjusted_data('{code}');"   #! sergio

    #! CHEN
    query = f"""
        SELECT tradeday,
            adj_open  AS open_price,
            adj_high  AS high_price,
            adj_low   AS low_price,
            adj_close AS close_price,
            adj_volume AS volume
        FROM signal_hkex_price
        WHERE code = '{code}'
            AND tradeday <= '{end_date}'
            AND adj_open  > 0
            AND adj_high  > 0
            AND adj_low   > 0
            AND adj_close > 0
            AND adj_volume > 0
        ORDER BY tradeday DESC;
    """

    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute(query)
            rows = await cursor.fetchall()

            # stock_records = [
            #     {
            #         "date": row["timestamp"].strftime("%Y-%m-%d"),
            #         "open": float(row["open_adj"]) if row["open_adj"] is not None else 0.0,
            #         "high": float(row["high_adj"]) if row["high_adj"] is not None else 0.0,
            #         "low": float(row["low_adj"]) if row["low_adj"] is not None else 0.0,
            #         "close": float(row["close_adj"]) if row["close_adj"] is not None else 0.0,
            #         "volume": int(row["volume_adj"]) if row["volume_adj"] is not None else 0,
            #     }
            #     for row in rows
            # ]

        #! CHEN
            stock_records = [
            {
                "date": row["tradeday"].strftime("%Y-%m-%d"),
                "time": "00:00:00",
                "open": float(row["open_price"])
                if row["open_price"] is not None
                else 0.0,
                "high": float(row["high_price"])
                if row["high_price"] is not None
                else 0.0,
                "low": float(row["low_price"]) if row["low_price"] is not None else 0.0,
                "close": float(row["close_price"])
                if row["close_price"] is not None
                else 0.0,
                "volume": int(row["volume"]) if row["volume"] is not None else 0,
            }
            for row in reversed(rows)
        ]

            empty_records = [rec for rec in stock_records if rec["open"] == 0]
            if empty_records:
                print("⚠️ Empty records found at dates:", ", ".join(rec["date"] for rec in empty_records))

            stock_records = [rec for rec in stock_records if rec not in empty_records]
            # if end_date:
            #     idx = next((i for i, rec in enumerate(stock_records) if rec["date"] == end_date), None)
            #     if idx is None:
            #         raise ValueError(f"Date {end_date} not found in stock records for {code}")
            #     stock_records = stock_records[: idx + 1]

            # print(
            #     f"Retrieved {len(stock_records)} records for stock {code}"
            #     + (f" up to {end_date}" if end_date else "")
            # )
            return stock_records


# Для локального тестування
# if __name__ == "__main__":
#     async def main():
#         await init_db_pool()
#         data = await get_stock_data_from_db("2800", "2025-09-15")
#         print(data[-1])

#         pool.close()
#         await pool.wait_closed()

#     asyncio.run(main())
