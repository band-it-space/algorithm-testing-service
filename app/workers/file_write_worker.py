import csv
import os
import logging
from typing import Dict, Any, List, Optional

from app.services.file_service import FileService

logger = logging.getLogger(__name__)
file_service = FileService()

# Output files
AUTOMATED_RESULTS_FILE = "Automated Results"
COMPARISON_RESULTS_FILE = "comparison_results"


async def process_file_write_task(task_data: Dict[str, Any]):
    """
    Process file write task from queue.
    Supports genome-based results and optimization data.
    
    Routes output based on 'output_type':
    - 'comparison': API vs Algo signal comparison -> comparison_results.csv
    - default: Trade statistics -> Automated Results.csv (matches Output Results Sample.csv)
    """
    try:
        logger.info("------------------------------")
        logger.info(f"Processing file write task: {task_data.get('stock_code', 'unknown')}")
        
        stock_code = task_data.get('stock_code')
        genome_id = task_data.get('genome_id', 'G_000')
        data = task_data.get('data', {})
        
        results_data = data.get('results_data', task_data.get('results_data', []))
        field_names = data.get('field_names', task_data.get('field_names', []))
        optimization_id = data.get('optimization_id', task_data.get('optimization_id'))
        output_type = data.get('output_type', 'default')
        
        logger.info(f"Processing file write for stock: {stock_code}, genome: {genome_id}, type: {output_type}")
        
        # Route output to correct file based on type
        if output_type == 'comparison':
            output_file = COMPARISON_RESULTS_FILE
        else:
            output_file = AUTOMATED_RESULTS_FILE
        
        success = await file_service.add_data_to_csv(output_file, results_data, field_names)
        
        if success:
            logger.info(f"File write completed for stock: {stock_code}, genome: {genome_id} -> {output_file}.csv")
        else:
            logger.error(f"File write failed for stock: {stock_code}, genome: {genome_id}")
            
        return {"success": success, "stock_code": stock_code, "genome_id": genome_id}
        
    except Exception as e:
        logger.error(f"Error processing file write task: {str(e)}")
        return {"success": False, "error": str(e)}


async def write_optimization_summary(
    optimization_id: str,
    results: List[Dict[str, Any]],
    output_file: Optional[str] = None
):
    """
    Write final optimization summary to CSV.
    Uses format matching Output Results Sample.csv.
    """
    try:
        from app.services.results_aggregation_service import get_output_fieldnames
        
        if not results:
            logger.warning(f"No results to write for optimization {optimization_id}")
            return False
        
        # Always write to single "Automated Results.csv" file
        output_file = AUTOMATED_RESULTS_FILE
        fieldnames = get_output_fieldnames()
        
        success = await file_service.add_data_to_csv(output_file, results, fieldnames)
        
        if success:
            logger.info(f"Optimization summary written to {output_file}.csv ({len(results)} rows)")
        
        return success
        
    except Exception as e:
        logger.error(f"Error writing optimization summary: {e}")
        return False
