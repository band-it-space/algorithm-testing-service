
from fastapi import FastAPI
import logging
from app.config.logging_config import setup_logging

from app.controllers.algorithm_controller import algorithm_router
# from app.controllers.data_test_controller import data_test_controller
# from app.controllers.monitoring_controller import monitoring_router
from app.controllers.summary_controller import generate_summary_file

from app.workers.algorithm_worker import process_algorithm_task
from app.workers.result_worker import process_result_task


setup_logging()
app = FastAPI(title="Algorithm Testing Service", version="1.0.0")
logger = logging.getLogger("app.api")


app.include_router(algorithm_router, prefix="/api/v1/start-testing", tags=["algorithms-testing"])
app.include_router(generate_summary_file, prefix="/api/v1/summary", tags=["summary"])


@app.get("/health")
async def health_check():
    return {"status": "healthy"}