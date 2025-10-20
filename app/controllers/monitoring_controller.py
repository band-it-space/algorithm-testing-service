from fastapi import APIRouter, HTTPException
from app.config.queue_config import algorithm_calculation_queue, result_processing_queue, redis_conn
from rq import Worker
from typing import Dict, Any

monitoring_router = APIRouter()

@monitoring_router.get("/queues")
async def get_queues_info():
    """
    Повертає детальну інформацію про черги
    """
    try:
        # Отримуємо інформацію про черги
        algorithm_queue_info = {
            "name": "algorithm_calculation",
            "pending_jobs": len(algorithm_calculation_queue),
            "failed_jobs": len(algorithm_calculation_queue.failed_job_registry),
            "scheduled_jobs": len(algorithm_calculation_queue.scheduled_job_registry),
            "started_jobs": len(algorithm_calculation_queue.started_job_registry)
        }
        
        result_queue_info = {
            "name": "result_processing", 
            "pending_jobs": len(result_processing_queue),
            "failed_jobs": len(result_processing_queue.failed_job_registry),
            "scheduled_jobs": len(result_processing_queue.scheduled_job_registry),
            "started_jobs": len(result_processing_queue.started_job_registry)
        }
        
        return {
            "queues": [algorithm_queue_info, result_queue_info],
            "redis_connection": {
                "host": redis_conn.connection_pool.connection_kwargs.get('host', 'localhost'),
                "port": redis_conn.connection_pool.connection_kwargs.get('port', 6379),
                "db": redis_conn.connection_pool.connection_kwargs.get('db', 0),
                "connected": redis_conn.ping()
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get queues info: {str(e)}")

@monitoring_router.get("/workers")
async def get_workers_info():
    """
    Повертає інформацію про активних воркерів
    """
    try:
        workers = Worker.all(connection=redis_conn)
        
        workers_info = []
        for worker in workers:
            worker_info = {
                "name": worker.name,
                "queues": [queue.name for queue in worker.queues],
                "state": worker.get_state(),
                "current_job": worker.get_current_job_id(),
                "last_heartbeat": worker.last_heartbeat,
                "successful_job_count": worker.successful_job_count,
                "failed_job_count": worker.failed_job_count
            }
            workers_info.append(worker_info)
        
        return {
            "workers": workers_info,
            "total_workers": len(workers_info)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get workers info: {str(e)}")

@monitoring_router.get("/jobs/{queue_name}")
async def get_queue_jobs(queue_name: str, limit: int = 10):
    """
    Повертає список завдань з черги
    """
    try:
        if queue_name == "algorithm_calculation":
            queue = algorithm_calculation_queue
        elif queue_name == "result_processing":
            queue = result_processing_queue
        else:
            raise HTTPException(status_code=404, detail="Queue not found")
        
        # Отримуємо завдання з різних реєстрів
        pending_jobs = list(queue.get_jobs())[:limit]
        
        jobs_info = []
        for job in pending_jobs:
            job_info = {
                "id": job.id,
                "status": job.get_status(),
                "created_at": job.created_at,
                "enqueued_at": job.enqueued_at,
                "data": str(job.description)[:100] + "..." if len(str(job.description)) > 100 else str(job.description)
            }
            jobs_info.append(job_info)
        
        return {
            "queue_name": queue_name,
            "jobs": jobs_info,
            "total_pending": len(queue.get_jobs())
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get queue jobs: {str(e)}")

@monitoring_router.get("/stats")
async def get_overall_stats():
    """
    Повертає загальну статистику системи
    """
    try:
        # Статистика по чергах
        algorithm_stats = {
            "pending": len(algorithm_calculation_queue),
            "failed": len(algorithm_calculation_queue.failed_job_registry),
            "scheduled": len(algorithm_calculation_queue.scheduled_job_registry),
            "started": len(algorithm_calculation_queue.started_job_registry)
        }
        
        result_stats = {
            "pending": len(result_processing_queue),
            "failed": len(result_processing_queue.failed_job_registry), 
            "scheduled": len(result_processing_queue.scheduled_job_registry),
            "started": len(result_processing_queue.started_job_registry)
        }
        
        # Статистика по воркерах
        workers = Worker.all(connection=redis_conn)
        worker_stats = {
            "total_workers": len(workers),
            "active_workers": len([w for w in workers if w.get_state() == 'busy']),
            "idle_workers": len([w for w in workers if w.get_state() == 'idle'])
        }
        
        return {
            "algorithm_queue": algorithm_stats,
            "result_queue": result_stats,
            "workers": worker_stats,
            "total_jobs": sum([
                algorithm_stats["pending"] + algorithm_stats["scheduled"] + algorithm_stats["started"],
                result_stats["pending"] + result_stats["scheduled"] + result_stats["started"]
            ])
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get overall stats: {str(e)}")
