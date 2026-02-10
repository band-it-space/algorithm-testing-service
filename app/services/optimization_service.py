import uuid
import json
import logging
import os
from datetime import datetime
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict
from enum import Enum

import redis

from app.models.algorithm_models import AlgorithmParameters, ParameterRange
from app.services.genome_service import generate_genomes, parse_parameter_ranges, calculate_total_combinations
from app.services.queue_service import QueueService

logger = logging.getLogger(__name__)

# Single output file for optimization results
AUTOMATED_RESULTS_FILE = "Automated Results.csv"
DATA_DIR = os.getenv('DATA_DIR', 'data')


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
    sheet_id: Optional[str] = None  # Google Sheet ID for output
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OptimizationMetadata":
        # Handle missing sheet_id for backwards compatibility
        if 'sheet_id' not in data:
            data['sheet_id'] = None
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
    def _clear_results_file(cls) -> None:
        """Clear the Automated Results.csv file for a fresh optimization run."""
        results_path = os.path.join(DATA_DIR, AUTOMATED_RESULTS_FILE)
        try:
            if os.path.exists(results_path):
                os.remove(results_path)
                logger.info(f"Cleared previous results file: {results_path}")
        except Exception as e:
            logger.warning(f"Could not clear results file: {e}")
    
    @classmethod
    def create_optimization(
        cls,
        stock_codes: List[str],
        parameter_ranges: List[Dict[str, Any]],
        sheet_id: Optional[str] = None,
    ) -> OptimizationMetadata:
        """Create a new optimization run and queue all tasks."""
        optimization_id = f"opt_{uuid.uuid4().hex[:12]}"
        
        # Clear previous results file for fresh optimization
        cls._clear_results_file()
        
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
            sheet_id=sheet_id,
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
    
    # Lua script for atomic increment of completed_tasks in Redis.
    # Prevents race conditions when multiple workers finish simultaneously.
    _INCREMENT_COMPLETED_LUA = """
    local key = KEYS[1]
    local inc = tonumber(ARGV[1])
    local now = ARGV[2]

    local raw = redis.call('GET', key)
    if not raw then return nil end

    local data = cjson.decode(raw)
    data['completed_tasks'] = data['completed_tasks'] + inc
    data['updated_at'] = now

    if data['completed_tasks'] >= data['total_tasks'] then
        data['status'] = 'completed'
    elseif data['status'] == 'queued' then
        data['status'] = 'running'
    end

    local encoded = cjson.encode(data)
    redis.call('SET', key, encoded)
    return encoded
    """

    @classmethod
    def increment_completed_tasks(
        cls,
        optimization_id: str,
        count: int = 1
    ) -> Optional[OptimizationMetadata]:
        """Atomically increment the completed task count using a Lua script."""
        client = cls.get_redis_client()
        key = f"{cls.OPTIMIZATION_PREFIX}{optimization_id}"
        now = datetime.now().isoformat()

        result = client.eval(
            cls._INCREMENT_COMPLETED_LUA, 1, key, str(count), now
        )

        if result is None:
            return None

        metadata = OptimizationMetadata.from_dict(json.loads(result))

        # If completed, write results to Google Sheets
        if metadata.status == OptimizationStatus.COMPLETED.value:
            cls._write_results_to_sheets(optimization_id, metadata)

        return metadata
    
    # Lua script for atomic increment of failed_tasks.
    _INCREMENT_FAILED_LUA = """
    local key = KEYS[1]
    local inc = tonumber(ARGV[1])
    local now = ARGV[2]

    local raw = redis.call('GET', key)
    if not raw then return nil end

    local data = cjson.decode(raw)
    data['failed_tasks'] = data['failed_tasks'] + inc
    data['updated_at'] = now

    local encoded = cjson.encode(data)
    redis.call('SET', key, encoded)
    return encoded
    """

    @classmethod
    def increment_failed_tasks(
        cls,
        optimization_id: str,
        count: int = 1
    ) -> Optional[OptimizationMetadata]:
        """Atomically increment the failed task count using a Lua script."""
        client = cls.get_redis_client()
        key = f"{cls.OPTIMIZATION_PREFIX}{optimization_id}"
        now = datetime.now().isoformat()

        result = client.eval(
            cls._INCREMENT_FAILED_LUA, 1, key, str(count), now
        )

        if result is None:
            return None

        return OptimizationMetadata.from_dict(json.loads(result))
    
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
    def get_optimization_results(cls, optimization_id: str) -> Dict[str, Dict[str, Any]]:
        """Get all results for an optimization with recalculated deltas."""
        client = cls.get_redis_client()
        key = f"{cls.OPTIMIZATION_RESULTS_PREFIX}{optimization_id}"
        
        raw_results = client.hgetall(key)
        results = {}
        for field, value in raw_results.items():
            field_str = field.decode() if isinstance(field, bytes) else field
            results[field_str] = json.loads(value)
        
        # Recalculate deltas using BASE genome (G_000)
        results = cls._recalculate_deltas(results)
        
        return results
    
    @classmethod
    def _recalculate_deltas(cls, results: Dict[str, Dict]) -> Dict[str, Dict]:
        """Recalculate Profit Delta and Win Rate Delta relative to G_000 (BASE)."""
        if not results:
            return results
        
        # Group by stock_code
        by_stock: Dict[str, Dict[str, Dict]] = {}
        for key, result in results.items():
            stock_code = result.get("Stock Code")
            if stock_code not in by_stock:
                by_stock[stock_code] = {}
            by_stock[stock_code][key] = result
        
        # Calculate deltas for each stock
        for stock_code, stock_results in by_stock.items():
            # Find BASE genome (G_000)
            base_key = f"G_000:{stock_code}"
            base = stock_results.get(base_key)
            
            if not base:
                # Try to find any G_000 entry for this stock
                for k, v in stock_results.items():
                    if v.get("Genome ID") == "G_000":
                        base = v
                        break
            
            if not base:
                continue
            
            # Calculate base metrics
            base_total_win = float(base.get("Total Win ($)", 0) or 0)
            base_total_loss = float(base.get("Total Loss ($)", 0) or 0)
            base_profit = base_total_win - base_total_loss
            
            base_trades_win = int(base.get("Trades Win", 0) or 0)
            base_trade_count = int(base.get("Trade Count", 0) or 0)
            base_win_rate = (base_trades_win / base_trade_count * 100) if base_trade_count > 0 else 0.0
            
            for key, result in stock_results.items():
                # Calculate genome metrics
                genome_total_win = float(result.get("Total Win ($)", 0) or 0)
                genome_total_loss = float(result.get("Total Loss ($)", 0) or 0)
                genome_profit = genome_total_win - genome_total_loss
                
                genome_trades_win = int(result.get("Trades Win", 0) or 0)
                genome_trade_count = int(result.get("Trade Count", 0) or 0)
                genome_win_rate = (genome_trades_win / genome_trade_count * 100) if genome_trade_count > 0 else 0.0
                
                if result.get("Genome ID") == "G_000":
                    # BASE genome always has 0 delta
                    result["Profit Delta (%)"] = 0.0
                    result["Win Rate Delta (%)"] = 0.0
                else:
                    # Profit Delta: ((genome_profit - base_profit) / |base_profit|) × 100
                    if base_profit != 0:
                        result["Profit Delta (%)"] = round(
                            ((genome_profit - base_profit) / abs(base_profit)) * 100, 2
                        )
                    else:
                        result["Profit Delta (%)"] = 0.0
                        
                    # Win Rate Delta: percentage point difference
                    result["Win Rate Delta (%)"] = round(genome_win_rate - base_win_rate, 2)
        
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
    
    @classmethod
    def _write_results_to_sheets(
        cls,
        optimization_id: str,
        metadata: OptimizationMetadata
    ) -> bool:
        """Write optimization results to Google Sheets when completed."""
        if not metadata.sheet_id:
            logger.info(f"No sheet_id configured for optimization {optimization_id}, skipping Google Sheets write")
            return False
        
        try:
            from app.services.sheets_service import SheetsService
            from app.services.results_aggregation_service import get_output_fieldnames
            
            # Get all results from Redis (with recalculated deltas)
            results = cls.get_optimization_results(optimization_id)
            
            if not results:
                logger.warning(f"No results found for optimization {optimization_id}")
                return False
            
            # Ordered fieldnames matching Output Results Sample.csv
            fieldnames = get_output_fieldnames()
            
            # Format results for output
            output_data = []
            for key, result in results.items():
                if not isinstance(result, dict):
                    continue
                
                # Filter to only expected fields (remove optimization_id, etc.)
                clean_row = {}
                for field in fieldnames:
                    clean_row[field] = result.get(field, '')
                
                # Add "(BASE)" suffix for G_000
                if clean_row.get('Genome ID') == 'G_000':
                    clean_row['Genome ID'] = 'G_000 (BASE)'
                
                output_data.append(clean_row)
            
            if not output_data:
                logger.warning(f"No formatted results for optimization {optimization_id}")
                return False
            
            # Sort by Genome ID
            output_data.sort(key=lambda x: x.get('Genome ID', ''))
            
            # Write to Google Sheets with ordered fieldnames
            success = SheetsService.write_genome_results(
                sheet_id=metadata.sheet_id,
                data=output_data,
                worksheet_name="Automated Results",
                fieldnames=fieldnames
            )
            
            if success:
                logger.info(f"Successfully wrote {len(output_data)} results to Google Sheets for optimization {optimization_id}")
            else:
                logger.error(f"Failed to write results to Google Sheets for optimization {optimization_id}")
            
            return success
            
        except ImportError as e:
            logger.warning(f"Google Sheets not available: {e}")
            return False
        except Exception as e:
            logger.error(f"Error writing results to Google Sheets for optimization {optimization_id}: {e}")
            return False
