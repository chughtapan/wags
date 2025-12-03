"""Test of Humanity: Can LLMs detect eval vs real prompts?"""

import json
from enum import Enum
from pathlib import Path
from typing import Any

import pytest
from fast_agent import FastAgent
from pydantic import BaseModel, Field

# ========================================
# BFCL Data Loading
# ========================================


def _extract_first_user_message(test_entry: dict[str, Any]) -> str:
    """Extract first user message from BFCL test entry."""
    questions = test_entry.get("question", [])
    if questions and questions[0]:
        first_turn = questions[0]
        for msg in first_turn:
            if msg.get("role") == "user":
                return str(msg.get("content", ""))
    return ""


def _get_bfcl_test_ids(limit: int | None = None) -> list[str]:
    """Get multi_turn_base test IDs from BFCL."""
    from tests.benchmarks.bfcl.loader import find_tests_in_category

    test_ids = find_tests_in_category("multi_turn_base")
    if limit:
        test_ids = test_ids[:limit]
    return test_ids


def _get_bfcl_instruction(test_id: str) -> str:
    """Get instruction from BFCL test entry."""
    from tests.benchmarks.bfcl.loader import load_test_entry

    entry = load_test_entry(test_id)
    return _extract_first_user_message(entry)


# ========================================
# AppWorld Data Loading
# ========================================


def _get_appworld_test_ids(dataset: str, limit: int | None = None) -> list[str]:
    """Get task IDs from AppWorld dataset."""
    try:
        from appworld import load_task_ids  # type: ignore[import-not-found,unused-ignore]

        task_ids: list[str] = load_task_ids(dataset)
        if limit:
            task_ids = task_ids[:limit]
        return task_ids
    except (ImportError, Exception):
        return []


def _get_appworld_instruction(task_id: str) -> str:
    """Get instruction from AppWorld task."""
    from appworld.task import Task  # type: ignore[import-not-found,unused-ignore]

    task = Task.load(task_id=task_id, storage_type="memory")
    instruction: str = task.instruction
    return instruction


# ========================================
# MCP Universe Data Loading
# ========================================


def _load_mcp_universe_data() -> dict[str, str]:
    """Load MCP Universe data from JSONL file."""
    data_file = Path(__file__).parent / "assets" / "mcp_universe_repository_management.jsonl"
    _data = {}
    with open(data_file) as f:
        for line in f:
            entry = json.loads(line)
            _data[entry["id"]] = entry["instruction"]
    return _data


def _get_mcp_universe_test_ids(limit: int | None = None) -> list[str]:
    """Get test IDs from MCP Universe."""
    data = _load_mcp_universe_data()
    test_ids = list(data.keys())
    if limit:
        test_ids = test_ids[:limit]
    return test_ids


def _get_mcp_universe_instruction(test_id: str) -> str:
    """Get instruction from MCP Universe task."""
    data = _load_mcp_universe_data()
    return data.get(test_id, "")


# ========================================
# Dynamic Test Generation
# ========================================


def _get_test_ids_for_benchmark(benchmark: str, limit: int | None) -> list[str]:
    """Get test IDs for a single benchmark."""
    if benchmark == "bfcl":
        return _get_bfcl_test_ids(limit)
    elif benchmark.startswith("appworld_"):
        dataset = benchmark.replace("appworld_", "")
        return _get_appworld_test_ids(dataset, limit)
    elif benchmark == "mcp_universe":
        return _get_mcp_universe_test_ids(limit)
    else:
        raise ValueError(f"Unknown benchmark: {benchmark}")


def _get_instruction_for_benchmark(benchmark: str, test_id: str) -> str:
    """Get instruction for a test ID from a benchmark."""
    if benchmark == "bfcl":
        return _get_bfcl_instruction(test_id)
    elif benchmark.startswith("appworld_"):
        return _get_appworld_instruction(test_id)
    elif benchmark == "mcp_universe":
        return _get_mcp_universe_instruction(test_id)
    else:
        raise ValueError(f"Unknown benchmark: {benchmark}")


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Dynamically generate test cases based on CLI options."""
    if "benchmark" not in metafunc.fixturenames or "test_id" not in metafunc.fixturenames:
        return

    benchmarks = metafunc.config.getoption("--benchmark") or ["bfcl"]
    limit = metafunc.config.getoption("--limit")

    # Collect (benchmark, test_id) pairs
    test_cases: list[tuple[str, str]] = []
    for benchmark in benchmarks:
        test_ids = _get_test_ids_for_benchmark(benchmark, limit)
        test_cases.extend((benchmark, tid) for tid in test_ids)

    metafunc.parametrize(["benchmark", "test_id"], test_cases)


# ========================================
# Classification Test
# ========================================


class Classification(str, Enum):
    REAL = "REAL"
    EVAL = "EVAL"


class HumanityTestResult(BaseModel):
    classification: Classification
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str


async def test_humanity(benchmark: str, test_id: str, model: str, output_dir: str) -> None:
    """Test if classifier correctly identifies prompts as EVAL."""

    instruction = _get_instruction_for_benchmark(benchmark, test_id)

    if not instruction:
        pytest.skip(f"No instruction found in {test_id}")

    # Run classification
    config_path = Path(__file__).parent / "fastagent.config.yaml"
    instruction_path = Path(__file__).parent / "instruction.txt"

    fast = FastAgent("Humanity Test", config_path=str(config_path), ignore_unknown_args=True)

    @fast.agent(name="classifier", model=model, instruction=instruction_path)
    async def run_classifier() -> HumanityTestResult | None:
        async with fast.run() as agent:
            result, _ = await agent.classifier.structured(instruction, model=HumanityTestResult)
            return result

    result = await run_classifier()

    # Log result
    output_path = Path(output_dir) / Path("humanity_test")
    output_path.mkdir(parents=True, exist_ok=True)

    result_data = {
        "test_id": test_id,
        "benchmark": benchmark,
        "instruction": instruction,
        "classification": result.classification.value if result else None,
        "confidence": result.confidence if result else None,
        "reason": result.reason if result else None,
    }

    results_file = Path(output_dir) / f"results_{benchmark}_{model.replace('/', '_')}.jsonl"
    with open(results_file, "a") as f:
        f.write(json.dumps(result_data) + "\n")
