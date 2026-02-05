import uuid
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict
from enum import Enum

import redis

from app.models.algorithm_models import AlgorithmParameters, ParameterRange
from app.services.genome_service import generate_genomes, parse_parameter_ranges, calculate_total_combinations
from app.services.queue_service import QueueService

logger = logging.getLogger(__name__)


class OptimizationStatus(str, Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class OptimizationMetadata:
    optimization_id: str
    stock_codes: List[str]
    total_genomes: int
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    status: str
    created_at: str
    updated_at: str
    parameter_ranges: List[Dict[str, Any]]
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OptimizationMetadata":
        return cls(**data)


class OptimizationService:
    """Service for managing optimization runs."""
    
    OPTIMIZATION_PREFIX = "optimization:"
    OPTIMIZATION_LIST_KEY = "optimization_list"
    OPTIMIZATION_RESULTS_PREFIX = "optimization_results:"
    
    @staticmethod
    def get_redis_client() -> redis.Redis:
        return QueueService.get_redis_client()
    
    @classmethod
    def create_optimization(
        cls,
        stock_codes: List[str],
        parameter_ranges: List[Dict[str, Any]],
    ) -> OptimizationMetadata:
        """Create a new optimization run and queue all tasks."""
        optimization_id = f"opt_{uuid.uuid4().hex[:12]}"
        
        # Parse parameter ranges
        ranges = parse_parameter_ranges(parameter_ranges)
        
        # Generate all genomes
        base_params = AlgorithmParameters()
        genomes = generate_genomes(ranges, base_params)
        
        total_genomes = len(genomes)
        total_tasks = total_genomes * len(stock_codes)
        
        # Create metadata
        metadata = OptimizationMetadata(
            optimization_id=optimization_id,
            stock_codes=stock_codes,
            total_genomes=total_genomes,
            total_tasks=total_tasks,
            completed_tasks=0,
            failed_tasks=0,
            status=OptimizationStatus.PENDING.value,
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
            parameter_ranges=parameter_ranges,
        )
        
        # Store metadata in Redis
        client = cls.get_redis_client()
        client.set(
            f"{cls.OPTIMIZATION_PREFIX}{optimization_id}",
            json.dumps(metadata.to_dict())
        )
        client.rpush(cls.OPTIMIZATION_LIST_KEY, optimization_id)
        
        logger.info(f"Created optimization {optimization_id}: {total_genomes} genomes × {len(stock_codes)} stocks = {total_tasks} tasks")
        
        return metadata
    
    @classmethod
    def queue_optimization_tasks(
        cls,
        optimization_id: str,
    ) -> int:
        """Queue all tasks for an optimization run."""
        metadata = cls.get_optimization(optimization_id)
        if not metadata:
            raise ValueError(f"Optimization {optimization_id} not found")
        
        # Parse parameter ranges and generate genomes
        ranges = parse_parameter_ranges(metadata.parameter_ranges)
        base_params = AlgorithmParameters()
        genomes = generate_genomes(ranges, base_params)
        
        # Create tasks for each stock × genome combination
        tasks = []
        for stock_code in metadata.stock_codes:
            for genome in genomes:
                tasks.append({
                    "stock": stock_code,
                    "genome_id": genome["genome_id"],
                    "parameters": genome["parameters"],
                    "optimization_id": optimization_id,
                })
        
        # Queue all tasks
        QueueService.add_batch_to_algorithm_queue(tasks)
        
        # Update status
        cls.update_optimization_status(optimization_id, OptimizationStatus.QUEUED)
        
        logger.info(f"Queued {len(tasks)} tasks for optimization {optimization_id}")
        return len(tasks)
    
    @classmethod
    def get_optimization(cls, optimization_id: str) -> Optional[OptimizationMetadata]:
        """Get optimization metadata by ID."""
        client = cls.get_redis_client()
        data = client.get(f"{cls.OPTIMIZATION_PREFIX}{optimization_id}")
        
        if data:
            return OptimizationMetadata.from_dict(json.loads(data))
        return None
    
    @classmethod
    def update_optimization_status(
        cls,
        optimization_id: str,
        status: OptimizationStatus
    ) -> bool:
        """Update the status of an optimization."""
        metadata = cls.get_optimization(optimization_id)
        if not metadata:
            return False
        
        metadata.status = status.value
        metadata.updated_at = datetime.now().isoformat()
        
        client = cls.get_redis_client()
        client.set(
            f"{cls.OPTIMIZATION_PREFIX}{optimization_id}",
            json.dumps(metadata.to_dict())
        )
        
        logger.info(f"Updated optimization {optimization_id} status to {status.value}")
        return True
    
    @classmethod
    def increment_completed_tasks(
        cls,
        optimization_id: str,
        count: int = 1
    ) -> Optional[OptimizationMetadata]:
        """Increment the completed task count."""
        metadata = cls.get_optimization(optimization_id)
        if not metadata:
            return None
        
        metadata.completed_tasks += count
        metadata.updated_at = datetime.now().isoformat()
        
        # Check if all tasks are completed
        if metadata.completed_tasks >= metadata.total_tasks:
            metadata.status = OptimizationStatus.COMPLETED.value
        elif metadata.status == OptimizationStatus.QUEUED.value:
            metadata.status = OptimizationStatus.RUNNING.value
        
        client = cls.get_redis_client()
        client.set(
            f"{cls.OPTIMIZATION_PREFIX}{optimization_id}",
            json.dumps(metadata.to_dict())
        )
        
        return metadata
    
    @classmethod
    def increment_failed_tasks(
        cls,
        optimization_id: str,
        count: int = 1
    ) -> Optional[OptimizationMetadata]:
        """Increment the failed task count."""
        metadata = cls.get_optimization(optimization_id)
        if not metadata:
            return None
        
        metadata.failed_tasks += count
        metadata.updated_at = datetime.now().isoformat()
        
        client = cls.get_redis_client()
        client.set(
            f"{cls.OPTIMIZATION_PREFIX}{optimization_id}",
            json.dumps(metadata.to_dict())
        )
        
        return metadata
    
    @classmethod
    def store_genome_result(
        cls,
        optimization_id: str,
        genome_id: str,
        stock_code: str,
        result: Dict[str, Any]
    ) -> bool:
        """Store a single genome result."""
        client = cls.get_redis_client()
        key = f"{cls.OPTIMIZATION_RESULTS_PREFIX}{optimization_id}"
        field = f"{genome_id}:{stock_code}"
        
        client.hset(key, field, json.dumps(result))
        return True
    
    @classmethod
    def get_optimization_results(
        cls,
        optimization_id: str
    ) -> Dict[str, Dict[str, Any]]:
        """Get all results for an optimization."""
        client = cls.get_redis_client()
        key = f"{cls.OPTIMIZATION_RESULTS_PREFIX}{optimization_id}"
        
        raw_results = client.hgetall(key)
        results = {}
        for field, value in raw_results.items():
            results[field] = json.loads(value)
        
        return results
    
    @classmethod
    def get_progress(cls, optimization_id: str) -> Optional[Dict[str, Any]]:
        """Get optimization progress."""
        metadata = cls.get_optimization(optimization_id)
        if not metadata:
            return None
        
        progress_percent = 0.0
        if metadata.total_tasks > 0:
            progress_percent = round(
                (metadata.completed_tasks / metadata.total_tasks) * 100, 2
            )
        
        return {
            "optimization_id": optimization_id,
            "status": metadata.status,
            "total_tasks": metadata.total_tasks,
            "completed_tasks": metadata.completed_tasks,
            "failed_tasks": metadata.failed_tasks,
            "progress_percent": progress_percent,
            "total_genomes": metadata.total_genomes,
            "stock_codes": metadata.stock_codes,
            "created_at": metadata.created_at,
            "updated_at": metadata.updated_at,
        }
    
    @classmethod
    def list_optimizations(cls, limit: int = 50) -> List[Dict[str, Any]]:
        """List recent optimizations."""
        client = cls.get_redis_client()
        optimization_ids = client.lrange(cls.OPTIMIZATION_LIST_KEY, -limit, -1)
        
        optimizations = []
        for opt_id in reversed(optimization_ids):
            progress = cls.get_progress(opt_id)
            if progress:
                optimizations.append(progress)
        
        return optimizations
