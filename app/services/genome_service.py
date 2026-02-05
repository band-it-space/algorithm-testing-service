import itertools
import csv
from typing import List, Dict, Any, Optional
from pathlib import Path

from app.models.algorithm_models import AlgorithmParameters, ParameterRange


def parse_parameter_ranges(data: List[Dict[str, Any]]) -> List[ParameterRange]:
    """Parse input data (from CSV or Google Sheets) into ParameterRange objects."""
    ranges = []
    for row in data:
        try:
            param_range = ParameterRange.from_dict(row)
            if param_range.name:  # Skip empty rows
                ranges.append(param_range)
        except (ValueError, KeyError) as e:
            continue  # Skip invalid rows
    return ranges


def parse_parameter_ranges_from_csv(file_path: str) -> List[ParameterRange]:
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


def calculate_total_combinations(ranges: List[ParameterRange]) -> int:
    """Calculate total number of genome combinations."""
    variable_ranges = [r for r in ranges if r.change]
    if not variable_ranges:
        return 1  # Only BASE genome
    
    total = 1
    for r in variable_ranges:
        total *= len(r.generate_values())
    return total + 1  # +1 for BASE genome


def generate_genomes(
    ranges: List[ParameterRange],
    base_params: Optional[AlgorithmParameters] = None
) -> List[Dict[str, Any]]:
    """
    Generate all parameter combinations (genomes).
    
    Returns list of dicts with:
    - genome_id: "G_000" for BASE, "G_001", "G_002", etc.
    - parameters: dict of all parameter values
    """
    if base_params is None:
        base_params = AlgorithmParameters()
    
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


def get_genome_by_id(genomes: List[Dict[str, Any]], genome_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve specific genome by ID."""
    for genome in genomes:
        if genome.get("genome_id") == genome_id:
            return genome
    return None


def get_variable_parameter_names(ranges: List[ParameterRange]) -> List[str]:
    """Get list of parameter names that are being varied."""
    return [r.name for r in ranges if r.change]


def create_genome_summary(genomes: List[Dict[str, Any]], ranges: List[ParameterRange]) -> Dict[str, Any]:
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
