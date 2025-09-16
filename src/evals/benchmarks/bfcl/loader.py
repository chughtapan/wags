"""BFCL data loading utilities."""

import json
from pathlib import Path
from typing import Any

import bfcl_eval


def load_test_entry(test_id: str) -> dict[str, Any]:
    """
    Load test entry from BFCL data.

    Args:
        test_id: Test case identifier

    Returns:
        Test case dictionary
    """
    # Extract category from test_id (e.g., "multi_turn_base_62" -> "multi_turn_base")
    parts = test_id.rsplit("_", 1)
    if len(parts) == 2 and parts[1].isdigit():
        category = parts[0]
    else:
        # Handle cases without numeric suffix
        category = test_id

    # Find the data file for this category using installed package
    bfcl_module_dir = Path(bfcl_eval.__file__).parent
    data_file = bfcl_module_dir / "data" / f"BFCL_v4_{category}.json"

    if not data_file.exists():
        # Try to find any file that might contain this test
        data_dir = bfcl_module_dir / "data"
        for file_path in data_dir.glob("BFCL_v4_*.json"):
            with open(file_path) as f:
                for line in f:
                    entry = json.loads(line)
                    if entry["id"] == test_id:
                        return entry
        raise ValueError(f"Test {test_id} not found in any BFCL data file")

    with open(data_file) as f:
        for line in f:
            if line.strip():
                entry = json.loads(line)
                if entry["id"] == test_id:
                    return entry

    raise ValueError(f"Test {test_id} not found in {data_file}")


def load_ground_truth(test_id: str) -> list[list[str]]:
    """
    Load ground truth from BFCL.

    Args:
        test_id: Test case identifier

    Returns:
        Ground truth as list of turns with expected function calls
    """
    # Extract category from test_id
    parts = test_id.rsplit("_", 1)
    if len(parts) == 2 and parts[1].isdigit():
        category = parts[0]
    else:
        category = test_id

    # Load ground truth file using installed package
    bfcl_module_dir = Path(bfcl_eval.__file__).parent
    gt_file = bfcl_module_dir / "data" / "possible_answer" / f"BFCL_v4_{category}.json"

    if not gt_file.exists():
        # Try to find in any possible_answer file
        answer_dir = bfcl_module_dir / "data" / "possible_answer"
        for file_path in answer_dir.glob("BFCL_v4_*.json"):
            with open(file_path) as f:
                for line in f:
                    entry = json.loads(line)
                    if entry["id"] == test_id:
                        return entry["ground_truth"]
        raise ValueError(f"Ground truth for {test_id} not found")

    with open(gt_file) as f:
        for line in f:
            if line.strip():
                entry = json.loads(line)
                if entry["id"] == test_id:
                    return entry["ground_truth"]

    raise ValueError(f"Ground truth for {test_id} not found in {gt_file}")


def find_tests_in_category(category: str, limit: int | None = None) -> list[str]:
    """
    Find all test IDs in a BFCL category.

    Args:
        category: Test category (e.g., "multi_turn_base")
        limit: Maximum number of tests to return

    Returns:
        List of test IDs
    """
    # Find BFCL data directory using installed package
    bfcl_module_dir = Path(bfcl_eval.__file__).parent
    data_dir = bfcl_module_dir / "data"

    # Find data file for this category
    test_ids = []
    for file_path in data_dir.glob(f"*{category}*.json"):
        with open(file_path) as f:
            for line in f:
                if line.strip():
                    entry = json.loads(line)
                    if category in entry.get("id", ""):
                        test_ids.append(entry["id"])
                        if limit and len(test_ids) >= limit:
                            return test_ids

    return test_ids


def find_all_test_ids() -> list[str]:
    """
    Find all test IDs across all BFCL categories.

    Returns:
        List of all test IDs sorted
    """
    bfcl_module_dir = Path(bfcl_eval.__file__).parent
    data_dir = bfcl_module_dir / "data"

    test_ids = []
    for file_path in data_dir.glob("BFCL_v4_multi_turn*.json"):
        # Skip files that aren't test data
        if "possible_answer" in str(file_path):
            continue

        with open(file_path) as f:
            for line in f:
                if line.strip():
                    entry = json.loads(line)
                    test_ids.append(entry["id"])

    return sorted(test_ids)
