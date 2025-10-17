"""MCP-Universe data loading utilities."""

import json
from pathlib import Path
from typing import Any, cast


def _get_data_dir() -> Path:
    """Get MCP-Universe data directory from local submodule."""
    return (
        Path(__file__).parent
        / "data"
        / "mcpuniverse"
        / "benchmark"
        / "configs"
        / "test"
        / "repository_management"
    )


def load_task(task_id: str) -> dict[str, Any]:
    """
    Load task from MCP-Universe data.

    Args:
        task_id: Task identifier (e.g., "github_task_0001")

    Returns:
        Task dictionary with question, evaluators, etc.

    Raises:
        FileNotFoundError: If task file doesn't exist
        json.JSONDecodeError: If invalid JSON
    """
    data_dir = _get_data_dir()
    task_file = data_dir / f"{task_id}.json"

    if not task_file.exists():
        raise FileNotFoundError(f"Task file not found: {task_file}")

    with open(task_file) as f:
        task_data: dict[str, Any] = json.load(f)

    return task_data


def find_all_task_ids() -> list[str]:
    """
    Find all repository management task IDs.

    Returns:
        List of all task IDs sorted
    """
    data_dir = _get_data_dir()

    if not data_dir.exists():
        return []

    task_ids = []
    for file_path in data_dir.glob("github_task_*.json"):
        # Extract task ID from filename (e.g., "github_task_0001.json" -> "github_task_0001")
        task_ids.append(file_path.stem)

    return sorted(task_ids)


def find_tasks_by_pattern(pattern: str = "github_task_*", limit: int | None = None) -> list[str]:
    """
    Find task IDs matching a pattern.

    Args:
        pattern: Glob pattern for task files
        limit: Maximum number of tasks to return

    Returns:
        List of task IDs
    """
    data_dir = _get_data_dir()

    if not data_dir.exists():
        return []

    task_ids = []
    for file_path in data_dir.glob(f"{pattern}.json"):
        task_ids.append(file_path.stem)
        if limit and len(task_ids) >= limit:
            break

    return sorted(task_ids)
