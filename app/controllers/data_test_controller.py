# import os
# import logging
# import requests
# from datetime import datetime

# from openpyxl import Workbook, load_workbook
# from openpyxl.utils import get_column_letter

# from app.services.file_service import FileService
# from app.workers.algo_func.get_db_data import get_stock_data_from_db

# logger = logging.getLogger(__name__)
# file_service = FileService()

# API_KEY = os.getenv('API_KEY')

# def parse_date(d):
#         try:
#             return datetime.strptime(d, "%Y-%m-%d")
#         except:
#             return datetime.strptime(d.split("T")[0], "%Y-%m-%d")

# def compare_stock_data(stock_data_db, stock_data_api, stock_code):

#     db_dict = {
#         parse_date(item["date"]).strftime("%Y-%m-%d"): item
#         for item in stock_data_db
#         if parse_date(item["date"]).year >= 2019
#     }
#     api_dict = {
#         parse_date(item["TradeDay"]).strftime("%Y-%m-%d"): item
#         for item in stock_data_api
#         if parse_date(item["TradeDay"]).year >= 2019
#     }

#     all_dates = sorted(
#         set(db_dict.keys()) | set(api_dict.keys()),
#         reverse=True
#     )

#     mismatched_dates = []

#     for d in all_dates:
#         db_res = db_dict.get(d)
#         api_res = api_dict.get(d)

#         if not db_res or not api_res:
#             # mismatched_dates.append({
#             #     "date": d,
#             #     "type": "Missing Data",
#             #     "message": f"No data for stock {stock_code} on {d}"
#             # })
#             continue

#         mismatches = []
#         for key_db, key_api in [
#             ("open", "adj_open"),
#             ("high", "adj_high"),
#             ("low", "adj_low"),
#             ("close", "adj_close"),
#             # ("volume", "adj_volume"),
#         ]:
#             v_db = db_res.get(key_db)
#             v_api = api_res.get(key_api)

#             if v_db is None or v_api is None:
#                 continue
#             if abs(v_db - v_api) > 0.01:
#                 mismatches.append(f"{key_db}: DB={v_db}, API={v_api}")

#         if mismatches:
#             mismatched_dates.append({
#                 "date": d,
#                 "type": "Mismatch",
#                 "message": ", ".join(mismatches)
#             })

#     # --- логіка замовника ---
#     # Повертаємо тільки якщо є mismatch саме на 2025-05-02 і немає на інших датах
#     only_mismatch_20250502 = (
#         any(m["date"] == "2025-05-02" for m in mismatched_dates)
#         and all(m["date"] == "2025-05-02" for m in mismatched_dates)
#     )

#     if only_mismatch_20250502:
#         return {
#             "date": "2025-05-02",
#             "type": "Mismatch only on 2025-05-02",
#             "message": next(m["message"] for m in mismatched_dates if m["date"] == "2025-05-02")
#         }

#     return None

# def compare_stock_data_percent(stock_data_db, stock_data_api, stock_code):
#     db_dict = {
#         parse_date(item["date"]).strftime("%Y-%m-%d"): item
#         for item in stock_data_db
#         if parse_date(item["date"]).year >= 2019
#     }
#     api_dict = {
#         parse_date(item["TradeDay"]).strftime("%Y-%m-%d"): item
#         for item in stock_data_api
#         if parse_date(item["TradeDay"]).year >= 2019
#     }

#     all_dates = sorted(set(db_dict.keys()) | set(api_dict.keys()))
#     percent_diff_by_day = {}

#     for d in all_dates:
#         db_res = db_dict.get(d)
#         api_res = api_dict.get(d)

#         v_db_close = db_res.get("close") if db_res and db_res.get("close") is not None else 0
#         v_api_close = api_res.get("adj_close") if api_res and api_res.get("adj_close") is not None else 0

#         if v_db_close == 0 or v_api_close == 0:
#             diff_pct = 100.0
#         else:
#             diff_pct = abs(v_db_close - v_api_close) / v_api_close * 100

#         percent_diff_by_day[d] = diff_pct

#     enlarged_diff_results = []
#     sorted_dates = sorted(percent_diff_by_day.keys())

#     for i in range(1, len(sorted_dates)):
#         prev_date = sorted_dates[i - 1]
#         curr_date = sorted_dates[i]
#         prev_diff = percent_diff_by_day[prev_date]
#         curr_diff = percent_diff_by_day[curr_date]
#         change = abs(curr_diff - prev_diff)

#         if change > 0.5:
#             db_curr = db_dict.get(curr_date, {}).get("close", 0)
#             api_curr = api_dict.get(curr_date, {}).get("adj_close", 0)
#             enlarged_diff_results.append({
#                 "Prev_date": prev_date,
#                 "Prev_dif": round(prev_diff, 3),
#                 "Curr_date": curr_date,
#                 "Curr_dif": round(curr_diff, 3),
#                 "Change": round(change, 3),
#                 "DB_close": db_curr,
#                 "API_close": api_curr,
#                 "type": "Enlarged % Difference >0.5%"
#             })

#     if enlarged_diff_results:
#         return enlarged_diff_results

#     return None


# async def data_test_controller():
#     try:
#         logger.info("Starting data test...")
        
#         screener_stocks = await file_service.read_data_from_csv("data_test")
#         if len(screener_stocks) == 0:
#             return {"message": "No stocks found", "status": "error"}

#         all_results = []

#         for stock in screener_stocks:
#             if stock is None:
#                 continue
#             stock_code = stock.get('Code')
#             stock_data_db = await get_stock_data_from_db(stock_code)
#             logger.info(f"Data length for stock: {stock_code} is {len(stock_data_db)} from Sergio DB")
            
#             API_URL = f'http://ete.stockfisher.com.hk/v1.1/debugHKEX/verifyData?TradeDay=&Code={stock_code}&verifyType=price'
#             headers = {'x-api-key': API_KEY}
#             response = requests.get(API_URL, headers=headers)
#             response.raise_for_status()
#             stock_data_api = response.json()
    
#             if not stock_data_api:
#                 logger.warning(f"Empty result for stock {stock_code}")
#                 continue
#             logger.info(f"Data length for stock: {stock_code} is {len(stock_data_api)} from API")

#             compare_results = compare_stock_data_percent(stock_data_db, stock_data_api, stock_code)
            
#             if compare_results:
#                 for r in compare_results:
#                     all_results.append({'code': stock_code, **r})
#             else: 
#                 logger.info(f"No enlarged % difference >0.5% for stock: {stock_code}")
#         if all_results:
#             field_names = ["code", "Prev_date", "Prev_dif", "Curr_date", "Curr_dif", "Change", "DB_close", "API_close", "type"]
#             await file_service.add_data_to_csv("mismatch_price_percent", all_results, field_names)

#         return {"message": "Data test successful"}

#     except Exception as e:
#         logger.exception("Data test failed")
#         return {"message": f"Data test failed: {str(e)}"}
