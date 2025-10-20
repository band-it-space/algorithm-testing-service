from fastapi import FastAPI
import logging
from app.config.logging_config import setup_logging
from app.controllers.algorithm_controller import algorithm_router
from app.controllers.monitoring_controller import monitoring_router

setup_logging()
app = FastAPI(title="Algorithm Testing Service", version="1.0.0")
logger = logging.getLogger("app.api")

app.include_router(algorithm_router, prefix="/api/v1/start-testing", tags=["algorithms-testing"])

app.include_router(monitoring_router, prefix="/api/v1/monitoring", tags=["monitoring"])


@app.get("/")
async def root():
    return {"message": "Algorithm Testing Service is running"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
