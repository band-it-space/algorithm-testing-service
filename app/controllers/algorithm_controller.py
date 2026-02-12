from app.services.get_all_stoccks import get_stocks_codes
from fastapi import APIRouter, HTTPException
from app.models.algorithm_models import AlgorithmRequest, AlgorithmResponse
from app.services.queue_service import QueueService
from app.services.file_service import FileService
algorithm_router = APIRouter()

@algorithm_router.get("/hkex")
async def init_algo_testing():
    """
    Запускає тестування алгоритму, додаючи завдання до першої черги
    """
    try:
        #Робимо запит за всими стоками 
        #stocks  = await get_stocks_codes()

        file_service = FileService()
        stocks = await file_service.read_data_from_csv("screener")
        
        if len(stocks) == 0:
            return {
                "message": "No stocks found",
                "status": "error",
            }
        exist = await file_service.read_data_from_csv("results")

        existing_codes = {str(item.get("stock_code")) for item in exist}
        
        done = []
        added = []
        for stock in stocks:
            code = str(stock.get("Code")).strip()

            if code in existing_codes:
                done.append(code)
                continue
            added.append(code)

            task_id = QueueService.add_to_algorithm_queue(code)
            if task_id is None:
                return {
                    "message": "Failed to add stock to queue",
                    "status": "error",
                }

        return {
            "message": f'Done: {len(done)}, Added to queue: {len(added)}',
            "done": done,
            'added': added,
            "status": "queued",
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start algorithm testing: {str(e)}")


@algorithm_router.get("/us-king")
async def init_us_king_testing():
    """
    Запускає тестування алгоритму US King
    """
    try:
        #Need testing stocks

        file_service = FileService()
        stocks = await file_service.read_data_from_csv("us_king_screener")
        
        if len(stocks) == 0:
            return {
                "message": "No stocks found",
                "status": "error",
            }
        added =[]
        for stock in stocks:
            code = str(stock.get("Code")).strip()
            
            task_id = QueueService.add_to_king_algorithm_queue(code)
            if task_id is None:
                return {
                    "message": "Failed to add stock to queue",
                    "status": "error",
                }
            added.append(code)
        return {
            "message": f'Added to queue: {len(added)}',
            'added': added,
            "status": "queued",
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start algorithm testing: {str(e)}")
