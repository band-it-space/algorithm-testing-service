import logging
import os
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

from app.services.optimization_service import OptimizationService, OptimizationStatus
from app.services.sheets_service import read_parameter_ranges_from_sheets
from app.services.genome_service import calculate_total_combinations, parse_parameter_ranges

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["optimization"])


class ParameterRangeInput(BaseModel):
    """Input model for a single parameter range."""
    name: str = Field(alias="Parameter Variable")
    base: float = Field(alias="Base")
    min_val: float = Field(alias="Min")
    max_val: float = Field(alias="Max")
    step: float = Field(alias="Step")
    change: bool = Field(alias="Change")
    rule: Optional[str] = Field(default="", alias="Rule")
    
    class Config:
        populate_by_name = True


class OptimizationRequest(BaseModel):
    """Request model for starting an optimization."""
    stock_codes: List[str] = Field(..., description="List of stock codes to optimize")
    parameter_ranges: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Parameter ranges. If not provided, reads from Google Sheets"
    )
    use_google_sheets: bool = Field(
        default=False,
        description="Read parameter ranges from Google Sheets"
    )
    sheet_id: Optional[str] = Field(
        default=None,
        description="Google Sheet ID for parameter ranges"
    )


class OptimizationResponse(BaseModel):
    """Response model for optimization creation."""
    optimization_id: str
    total_genomes: int
    total_tasks: int
    stock_codes: List[str]
    status: str
    message: str


class SmartFilteringProgress(BaseModel):
    """Smart filtering progress info."""
    enabled: bool = False
    genomes_skipped: int = 0
    eliminated_params: List[Dict[str, Any]] = Field(default_factory=list)
    error: Optional[str] = None


class OptimizationProgressResponse(BaseModel):
    """Response model for optimization progress."""
    optimization_id: str
    status: str
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    progress_percent: float
    total_genomes: int
    stock_codes: List[str]
    created_at: str
    updated_at: str
    elapsed_seconds: float = 0.0
    eta_seconds: Optional[float] = None
    eta_formatted: Optional[str] = None
    smart_filtering: Optional[SmartFilteringProgress] = None


class GenomeCombinationsResponse(BaseModel):
    """Response model for genome combinations preview."""
    total_combinations: int
    variable_parameters: List[Dict[str, Any]]
    fixed_parameters_count: int


@router.post("/run-optimization", response_model=OptimizationResponse)
async def run_optimization(
    request: OptimizationRequest,
    background_tasks: BackgroundTasks
):
    """
    Start a new optimization run.
    
    This endpoint creates an optimization job that will:
    1. Parse parameter ranges (from request or Google Sheets)
    2. Generate all parameter combinations (genomes)
    3. Queue tasks for each stock × genome combination
    4. Track progress and store results
    """
    try:
        # Get parameter ranges
        if request.parameter_ranges:
            parameter_ranges = request.parameter_ranges
        elif request.use_google_sheets:
            parameter_ranges = read_parameter_ranges_from_sheets(request.sheet_id)
        else:
            raise HTTPException(
                status_code=400,
                detail="Either parameter_ranges or use_google_sheets must be provided"
            )
        
        if not parameter_ranges:
            raise HTTPException(
                status_code=400,
                detail="No parameter ranges provided or found"
            )
        
        if not request.stock_codes:
            raise HTTPException(
                status_code=400,
                detail="At least one stock code is required"
            )
        
        # Determine sheet_id for results output
        # Use request.sheet_id if provided, otherwise use OUTPUT_SHEET_ID from env when use_google_sheets is True
        output_sheet_id = None
        if request.use_google_sheets:
            output_sheet_id = request.sheet_id or os.getenv("OUTPUT_SHEET_ID")
        
        # Create optimization
        metadata = OptimizationService.create_optimization(
            stock_codes=request.stock_codes,
            parameter_ranges=parameter_ranges,
            sheet_id=output_sheet_id,
        )
        
        # Queue tasks immediately (synchronously for now to ensure it works)
        try:
            queued_count = OptimizationService.queue_optimization_tasks(
                metadata.optimization_id
            )
            logger.info(f"Successfully queued {queued_count} tasks for optimization {metadata.optimization_id}")
        except Exception as e:
            logger.error(f"Failed to queue tasks for optimization {metadata.optimization_id}: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to queue tasks: {str(e)}")
        
        return OptimizationResponse(
            optimization_id=metadata.optimization_id,
            total_genomes=metadata.total_genomes,
            total_tasks=metadata.total_tasks,
            stock_codes=metadata.stock_codes,
            status=metadata.status,
            message=f"Optimization created and {queued_count} tasks queued successfully"
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        import traceback
        logger.error(f"Error creating optimization: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/optimization/{optimization_id}/status", response_model=OptimizationProgressResponse)
async def get_optimization_status(optimization_id: str):
    """Get the current status and progress of an optimization."""
    progress = OptimizationService.get_progress(optimization_id)
    
    if not progress:
        raise HTTPException(
            status_code=404,
            detail=f"Optimization {optimization_id} not found"
        )
    
    return OptimizationProgressResponse(**progress)


@router.get("/optimization/{optimization_id}/results")
async def get_optimization_results(optimization_id: str):
    """Get all results for a completed optimization."""
    metadata = OptimizationService.get_optimization(optimization_id)
    
    if not metadata:
        raise HTTPException(
            status_code=404,
            detail=f"Optimization {optimization_id} not found"
        )
    
    results = OptimizationService.get_optimization_results(optimization_id)
    
    return {
        "optimization_id": optimization_id,
        "status": metadata.status,
        "total_results": len(results),
        "results": results
    }


@router.post("/optimization/{optimization_id}/cancel")
async def cancel_optimization(optimization_id: str):
    """Cancel a running optimization."""
    metadata = OptimizationService.get_optimization(optimization_id)
    
    if not metadata:
        raise HTTPException(
            status_code=404,
            detail=f"Optimization {optimization_id} not found"
        )
    
    if metadata.status == OptimizationStatus.COMPLETED.value:
        raise HTTPException(
            status_code=400,
            detail="Cannot cancel a completed optimization"
        )
    
    OptimizationService.update_optimization_status(
        optimization_id,
        OptimizationStatus.CANCELLED
    )
    
    return {"message": f"Optimization {optimization_id} cancelled"}


@router.get("/optimizations", response_model=List[OptimizationProgressResponse])
async def list_optimizations(limit: int = 50):
    """List recent optimizations."""
    optimizations = OptimizationService.list_optimizations(limit=limit)
    return [OptimizationProgressResponse(**opt) for opt in optimizations]


@router.post("/preview-genomes", response_model=GenomeCombinationsResponse)
async def preview_genome_combinations(
    parameter_ranges: Optional[List[Dict[str, Any]]] = None,
    use_google_sheets: bool = False,
    sheet_id: Optional[str] = None
):
    """
    Preview the number of genome combinations that would be generated.
    
    Useful for estimating the total number of tasks before starting an optimization.
    """
    try:
        if parameter_ranges:
            ranges_data = parameter_ranges
        elif use_google_sheets:
            ranges_data = read_parameter_ranges_from_sheets(sheet_id)
        else:
            raise HTTPException(
                status_code=400,
                detail="Either parameter_ranges or use_google_sheets must be provided"
            )
        
        ranges = parse_parameter_ranges(ranges_data)
        total = calculate_total_combinations(ranges)
        
        variable_params = [
            {
                "name": r.name,
                "rule": r.rule,
                "base": r.base,
                "min": r.min_val,
                "max": r.max_val,
                "step": r.step,
                "values_count": len(r.generate_values())
            }
            for r in ranges if r.change
        ]
        
        fixed_count = len([r for r in ranges if not r.change])
        
        return GenomeCombinationsResponse(
            total_combinations=total,
            variable_parameters=variable_params,
            fixed_parameters_count=fixed_count
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error previewing genomes: {e}")
        raise HTTPException(status_code=500, detail=str(e))
