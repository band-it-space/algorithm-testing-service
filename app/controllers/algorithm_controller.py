from app.services.get_all_stoccks import get_stocks_codes
from fastapi import APIRouter, HTTPException
from app.models.algorithm_models import AlgorithmRequest, AlgorithmResponse
from app.services.queue_service import QueueService

algorithm_router = APIRouter()

@algorithm_router.get("/")
async def init_algo_testing():
    """
    Запускає тестування алгоритму, додаючи завдання до першої черги
    """
    try:

        #Робимо запит за всими стоками 
        stocks  = await get_stocks_codes()

        if len(stocks) == 0:
            return {
                "message": "No stocks found",
                "status": "error",
            }
        stocks = ["838", "2800", '981'] #! remove this after testing
        for stock in stocks:
            task_id = QueueService.add_to_algorithm_queue(stock)
            if task_id is None:
                return {
                    "message": "Failed to add stock to queue",
                    "status": "error",
                }

        return {
            "message": "Algorithm testing started successfully",
            "stocks": stocks,
            "status": "queued",
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start algorithm testing: {str(e)}")

# @algorithm_router.post("/start", response_model=dict)
# async def start_algorithm_testing(request: AlgorithmRequest):
#     """
#     Запускає тестування алгоритму, додаючи завдання до першої черги
#     """
#     try:
#         task_id = QueueService.add_to_algorithm_queue(request)
        
#         return {
#             "message": "Algorithm testing started successfully",
#             "task_id": task_id,
#             "status": "queued",
#         }
    
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Failed to start algorithm testing: {str(e)}")

# @algorithm_router.get("/status")
# async def get_queues_status():
#     """
#     Повертає статус черг
#     """
#     try:
#         status = QueueService.get_queue_status()
#         return {
#             "message": "Queue status retrieved successfully",
#             "queues": status
#         }
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Failed to get queue status: {str(e)}")

