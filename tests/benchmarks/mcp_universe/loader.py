"""MCP-Universe data loading utilities."""

import json
from contextlib import suppress
from importlib import resources
from importlib.abc import Traversable
from pathlib import Path
from typing import Any, cast

_PACKAGE_SUBPATH = ("benchmark", "configs", "test", "repository_management")
_LOCAL_DATA_DIR = (
    Path(__file__).parent / "data" / "mcpuniverse" / "benchmark" / "configs" / "test" / "repository_management"
)


def _package_data_root() -> Traversable | None:
    """Return repository-management configs from the installed MCP-Universe package if available."""
    with suppress(ModuleNotFoundError):
        resource = resources.files("mcpuniverse")
        for part in _PACKAGE_SUBPATH:
            resource = resource.joinpath(part)
        if resource.is_dir():
            return resource
    return None


def _local_data_root() -> Path | None:
    """Return repository-management configs from an optional vendored checkout."""
    if _LOCAL_DATA_DIR.exists():
        return _LOCAL_DATA_DIR
    return None


def _collect_task_ids(root: Any) -> list[str]:
    """Collect GitHub task identifiers from a directory-like resource."""
    task_ids: list[str] = []
    for entry in root.iterdir():
        name = entry.name
        if entry.is_file() and name.startswith("github_task_") and name.endswith(".json"):
            task_ids.append(name.removesuffix(".json"))
    return task_ids


def load_task(task_id: str) -> dict[str, Any]:
    """
    Load repository management task definition.

    Args:
        task_id: Task identifier (e.g., "github_task_0001")

    Returns:
        Task dictionary with question, evaluators, etc.

    Raises:
        FileNotFoundError: If the task cannot be found in any configured source
        json.JSONDecodeError: If the task file contains invalid JSON
    """
    task_filename = f"{task_id}.json"

    package_root = _package_data_root()
    if package_root:
        task_resource = package_root.joinpath(task_filename)
        if task_resource.is_file():
            with task_resource.open("r", encoding="utf-8") as fh:
                return cast(dict[str, Any], json.load(fh))

    local_root = _local_data_root()
    if local_root:
        task_path = local_root / task_filename
        if task_path.is_file():
            with open(task_path, encoding="utf-8") as fh:
                return cast(dict[str, Any], json.load(fh))

    raise FileNotFoundError(
        f"Task file not found for {task_id!r}. Install the eval extras with 'uv sync --extra evals' "
        "to pull the MCP-Universe package, or provide a local copy under "
        f"{_LOCAL_DATA_DIR}."
    )


def find_all_task_ids() -> list[str]:
    """
    Find all repository management task IDs.

    Returns:
        Sorted list of task IDs

    Raises:
        FileNotFoundError: If no task data sources are available
    """
    package_root = _package_data_root()
    if package_root:
        task_ids = _collect_task_ids(package_root)
        if task_ids:
            return sorted(task_ids)

    local_root = _local_data_root()
    if local_root:
        task_ids = _collect_task_ids(local_root)
        if task_ids:
            return sorted(task_ids)

    raise FileNotFoundError(
        "MCP-Universe repository management data not available. Run 'uv sync --extra evals' to install "
        "the MCP-Universe package, or vendor the configs under "
        f"{_LOCAL_DATA_DIR}."
    )
