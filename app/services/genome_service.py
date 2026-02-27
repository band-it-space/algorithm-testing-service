import csv
import itertools
import logging
from pathlib import Path
from typing import Any

from app.models.algorithm_models import AlgorithmParameters, ParameterRange

logger = logging.getLogger(__name__)


def parse_parameter_ranges(data: list[dict[str, Any]]) -> list[ParameterRange]:
    """Parse input data (from CSV or Google Sheets) into ParameterRange objects."""
    ranges = []
    for row in data:
        try:
            # Debug: Log the row being parsed
            change_val = row.get("Change", row.get("change", "NOT_FOUND"))
            logger.debug(f"Parsing row: name={row.get('Parameter Variable', row.get('name', 'N/A'))}, Change={change_val} (type={type(change_val).__name__})")
            
            param_range = ParameterRange.from_dict(row)
            if param_range.name:  # Skip empty rows
                logger.debug(f"  -> Parsed: name={param_range.name}, change={param_range.change}")
                ranges.append(param_range)
        except (ValueError, KeyError) as e:
            logger.warning(f"Failed to parse row: {row}, error: {e}")
            continue  # Skip invalid rows
    return ranges


def parse_parameter_ranges_from_csv(file_path: str) -> list[ParameterRange]:
    """Parse parameter ranges from a CSV file."""
    ranges = []
    with open(file_path, 'r', encoding='utf-8') as f:
        # Try to detect delimiter
        sample = f.read(1024)
        f.seek(0)
        
        if '\t' in sample:
            reader = csv.DictReader(f, delimiter='\t')
        else:
            reader = csv.DictReader(f)
        
        for row in reader:
            try:
                param_range = ParameterRange.from_dict(row)
                if param_range.name:
                    ranges.append(param_range)
            except (ValueError, KeyError):
                continue
    return ranges


def calculate_total_combinations(ranges: list[ParameterRange]) -> int:
    """Calculate total number of genome combinations."""
    variable_ranges = [r for r in ranges if r.change]
    if not variable_ranges:
        return 1  # Only BASE genome
    
    total = 1
    for r in variable_ranges:
        total *= len(r.generate_values())
    return total + 1  # +1 for BASE genome


def generate_genomes(
    ranges: list[ParameterRange],
    base_params: AlgorithmParameters | None = None
) -> list[dict[str, Any]]:
    """
    Generate all parameter combinations (genomes).
    
    Returns list of dicts with:
    - genome_id: "G_000" for BASE, "G_001", "G_002", etc.
    - parameters: dict of all parameter values
    """
    if base_params is None:
        base_params = AlgorithmParameters()
    
    # Debug: Log all parameters and their change flag
    logger.info(f"generate_genomes: Received {len(ranges)} parameter ranges")
    for r in ranges:
        logger.info(f"  Parameter: {r.name}, change={r.change}, min={r.min_val}, max={r.max_val}, step={r.step}")
    
    genomes = []
    
    # G_000 is always BASE with default parameters
    base_genome = {
        "genome_id": "G_000",
        "is_base": True,
        "parameters": base_params.to_dict()
    }
    genomes.append(base_genome)
    
    # Get variable parameters (change=True)
    variable_ranges = [r for r in ranges if r.change]
    
    logger.info(f"Variable parameters (change=True): {[r.name for r in variable_ranges]}")
    
    if not variable_ranges:
        return genomes  # Only BASE genome
    
    # Generate all value combinations
    value_lists = [r.generate_values() for r in variable_ranges]
    combinations = list(itertools.product(*value_lists))
    
    # Create genome for each combination
    for i, combo in enumerate(combinations):
        params = base_params.to_dict()
        
        # Apply variable parameter values
        for r, val in zip(variable_ranges, combo):
            if r.name in params:
                # Convert to int if original is int
                if isinstance(params[r.name], int):
                    params[r.name] = int(val)
                else:
                    params[r.name] = val
        
        genomes.append({
            "genome_id": f"G_{i+1:03d}",
            "is_base": False,
            "parameters": params
        })
    
    return genomes


def get_genome_by_id(genomes: list[dict[str, Any]], genome_id: str) -> dict[str, Any] | None:
    """Retrieve specific genome by ID."""
    for genome in genomes:
        if genome.get("genome_id") == genome_id:
            return genome
    return None


def get_variable_parameter_names(ranges: list[ParameterRange]) -> list[str]:
    """Get list of parameter names that are being varied."""
    return [r.name for r in ranges if r.change]


def create_genome_summary(genomes: list[dict[str, Any]], ranges: list[ParameterRange]) -> dict[str, Any]:
    """Create summary of genome generation for logging/reporting."""
    variable_ranges = [r for r in ranges if r.change]
    
    return {
        "total_genomes": len(genomes),
        "base_genome_id": "G_000",
        "variable_parameters": [
            {
                "name": r.name,
                "rule": r.rule,
                "base": r.base,
                "min": r.min_val,
                "max": r.max_val,
                "step": r.step,
                "values_count": len(r.generate_values())
            }
            for r in variable_ranges
        ],
        "fixed_parameters_count": len([r for r in ranges if not r.change])
    }

def get_genome_parameters(genome_id: str, optimization_id: str | None = None) -> dict | None:
    """
    Get genome parameters by ID.
    
    Args:
        genome_id: The genome identifier (e.g., 'G_001')
        optimization_id: Optional optimization ID to scope the search
    
    Returns:
        Dictionary with genome parameters or None if not found
    """
    # Import here to avoid circular imports
    from app.services.optimization_service import OptimizationService
    
    if optimization_id:
        # Get specific optimization
        metadata = OptimizationService.get_optimization(optimization_id)
        if not metadata:
            return None
        
        # Regenerate genomes from parameter ranges
        ranges = parse_parameter_ranges(metadata.parameter_ranges)
        base_params = AlgorithmParameters()
        genomes = generate_genomes(ranges, base_params)
        
        # Find the genome by ID
        genome = get_genome_by_id(genomes, genome_id)
        if genome:
            return {
                "genome_id": genome_id,
                "optimization_id": optimization_id,
                "parameters": genome.get("parameters", {})
            }
        return None
    else:
        # Search through recent optimizations
        client = OptimizationService.get_redis_client()
        optimization_ids = client.lrange(OptimizationService.OPTIMIZATION_LIST_KEY, 0, 50)
        
        for opt_id in optimization_ids:
            opt_id_str = opt_id.decode() if isinstance(opt_id, bytes) else opt_id
            metadata = OptimizationService.get_optimization(opt_id_str)
            if not metadata:
                continue
                
            ranges = parse_parameter_ranges(metadata.parameter_ranges)
            base_params = AlgorithmParameters()
            genomes = generate_genomes(ranges, base_params)
            
            genome = get_genome_by_id(genomes, genome_id)
            if genome:
                return {
                    "genome_id": genome_id,
                    "optimization_id": opt_id_str,
                    "parameters": genome.get("parameters", {})
                }
        
        return None
