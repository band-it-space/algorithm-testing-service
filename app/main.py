import logging

from fastapi import FastAPI

from app.config.logging_config import setup_logging
from app.controllers.algorithm_controller import algorithm_router
from app.controllers.monitoring_controller import monitoring_router
from app.controllers.summary_controller import generate_summary_file
from app.controllers.optimization_controller import router as optimization_router
from app.controllers.sheets_controller import router as sheets_router
from app.controllers.genome_controller import router as genome_router
from app.controllers.dashboard_controller import dashboard_router

setup_logging()
app = FastAPI(title="Algorithm Testing Service", version="1.0.0")
logger = logging.getLogger("app.api")

# --- Routers ---
app.include_router(algorithm_router, prefix="/api/v1/start-testing", tags=["algorithms-testing"])
app.include_router(monitoring_router, prefix="/api/v1/monitoring", tags=["monitoring"])
app.include_router(generate_summary_file, prefix="/api/v1/summary", tags=["summary"])
app.include_router(optimization_router)
app.include_router(sheets_router)
app.include_router(genome_router)
app.include_router(dashboard_router)


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
