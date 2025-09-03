"""Evaluation logic for test results."""

import json
from pathlib import Path
from typing import Dict, Any, List

from bfcl_eval.eval_checker.multi_turn_eval.multi_turn_checker import (
    multi_turn_checker,
    multi_turn_irrelevance_checker
)

from .parser import parse_and_format
from .bfcl.data_loader import load_test_entry, load_ground_truth


def evaluate_results(test_id: str, log_file: str) -> Dict[str, Any]:
    """
    Parse log and evaluate with BFCL validators.
    
    Args:
        test_id: Test case identifier
        log_file: Path to JSONL log file
        
    Returns:
        Dictionary with evaluation results
    """
    # Parse tool calls from log
    raw_calls, executable_responses = parse_and_format(log_file)
    
    # Load test data and ground truth
    test_entry = load_test_entry(test_id)
    ground_truth = load_ground_truth(test_id)
    
    # Extract category for BFCL checker
    parts = test_id.rsplit("_", 1)
    if len(parts) == 2 and parts[1].isdigit():
        test_category = parts[0]
    else:
        test_category = test_id
    
    # Format for BFCL checker (needs nested list structure)
    # Each turn should be a list even if it contains only one call
    model_result_decoded = []
    for turn in executable_responses:
        if turn:
            model_result_decoded.append([turn])
        else:
            model_result_decoded.append([[]])
    
    # Run validation
    validation_result = multi_turn_checker(
        multi_turn_model_result_list_decoded=model_result_decoded,
        multi_turn_ground_truth_list=ground_truth,
        test_entry=test_entry,
        test_category=test_category,
        model_name="fast-agent"
    )
    
    # Run irrelevance check
    irrelevance_result = multi_turn_irrelevance_checker(
        multi_turn_model_result_list_decoded=model_result_decoded,
        multi_turn_ground_truth_list=ground_truth
    )
    
    # Convert validation results to be JSON serializable
    # BFCL returns sets in some cases, convert them to lists
    def make_json_serializable(obj):
        if isinstance(obj, dict):
            return {k: make_json_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [make_json_serializable(item) for item in obj]
        elif isinstance(obj, set):
            return list(obj)
        else:
            return obj
    
    return {
        "test_id": test_id,
        "validation": make_json_serializable(validation_result),
        "irrelevance_check": make_json_serializable(irrelevance_result),
        "model_responses": executable_responses,
        "ground_truth": ground_truth,
        "raw_tool_calls": raw_calls
    }