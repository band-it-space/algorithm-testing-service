from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from app.services.genome_service import get_genome_parameters

router = APIRouter(prefix="/api/v1/genome", tags=["genome"])


@router.get("/{genome_id}/parameters")
async def get_genome_params(
    genome_id: str,
    optimization_id: Optional[str] = Query(None, description="Scope search to specific optimization")
):
    """Get parameters for a specific genome."""
    result = get_genome_parameters(genome_id, optimization_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Genome not found")
    return result
