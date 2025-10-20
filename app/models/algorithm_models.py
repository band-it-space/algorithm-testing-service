from pydantic import BaseModel
from typing import Any, Dict, Optional
from datetime import datetime

class AlgorithmRequest(BaseModel):
    stock_kod: str
    
    class Config:
        schema_extra = {
            "example": {
                "stock": 2800,
            }
        }

class AlgorithmResponse(BaseModel):
    algorithm_name: str
    input_data: Dict[str, Any]
    execution_time_ms: float
    result: Any
    status: str
    
    class Config:
        schema_extra = {
            "example": {
                "algorithm_name": "quicksort",
                "input_data": {
                    "array": [64, 34, 25, 12, 22, 11, 90]
                },
                "execution_time_ms": 150.5,
                "result": [11, 12, 22, 25, 34, 64, 90],
                "status": "success"
            }
        }

# Моделі для черг
class QueueTask(BaseModel):
    task_id: str
    algorithm_name: str
    input_data: Dict[str, Any]
    parameters: Optional[Dict[str, Any]] = None
    created_at: datetime
    queue_name: str

class WorkerResult(BaseModel):
    task_id: str
    algorithm_name: str
    result: Any
    processing_time_ms: float
    worker_id: str
    completed_at: datetime
