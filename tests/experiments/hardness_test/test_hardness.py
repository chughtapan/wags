"""Hardness Test: Rate task difficulty across benchmarks without tool knowledge."""

import json
from pathlib import Path
from typing import Any

import pytest
from fast_agent import FastAgent
from pydantic import BaseModel, Field

# ========================================
# BFCL Data Loading (Multi-Turn Support)
# ========================================


def _format_multi_turn_task(questions: list[list[dict[str, Any]]]) -> str:
    """Format all turns from BFCL into a single task description.

    Unlike humanity test which only uses first turn, hardness evaluation
    needs ALL turns to properly assess task complexity.
    """
    lines = []
    for i, turn in enumerate(questions, start=1):
        for msg in turn:
            if msg.get("role") == "user":
                content = str(msg.get("content", ""))
                if content:
                    lines.append(f"Turn {i}: {content}")
    return "\n\n".join(lines)


def _get_bfcl_test_ids(limit: int | None = None) -> list[str]:
    """Get multi_turn_base test IDs from BFCL."""
    from tests.benchmarks.bfcl.loader import find_tests_in_category

    test_ids = find_tests_in_category("multi_turn_base")
    if limit:
        test_ids = test_ids[:limit]
    return test_ids


def _get_bfcl_instruction(test_id: str) -> tuple[str, int]:
    """Get instruction from BFCL test entry.

    Returns:
        Tuple of (formatted_task, num_turns)
    """
    from tests.benchmarks.bfcl.loader import load_test_entry

    entry = load_test_entry(test_id)
    questions = entry.get("question", [])
    formatted = _format_multi_turn_task(questions)
    return formatted, len(questions)


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


def _get_appworld_instruction(task_id: str) -> tuple[str, int]:
    """Get instruction from AppWorld task."""
    from appworld.task import Task  # type: ignore[import-not-found,unused-ignore]

    task = Task.load(task_id=task_id, storage_type="memory")
    instruction: str = task.instruction
    return instruction, 1  # AppWorld tasks are single-turn


# ========================================
# MCP Universe Data Loading
# ========================================


def _load_mcp_universe_data() -> dict[str, str]:
    """Load MCP Universe data from JSONL file."""
    data_file = Path(__file__).parent.parent / "humanity_test" / "assets" / "mcp_universe_repository_management.jsonl"
    _data = {}
    if data_file.exists():
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


def _get_mcp_universe_instruction(test_id: str) -> tuple[str, int]:
    """Get instruction from MCP Universe task."""
    data = _load_mcp_universe_data()
    return data.get(test_id, ""), 1  # Single-turn


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


def _get_instruction_for_benchmark(benchmark: str, test_id: str) -> tuple[str, int]:
    """Get instruction for a test ID from a benchmark.

    Returns:
        Tuple of (instruction_text, num_turns)
    """
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

    benchmarks = metafunc.config.getoption("--benchmarks") or ["bfcl"]
    limit = metafunc.config.getoption("--limit")

    # Collect (benchmark, test_id) pairs
    test_cases: list[tuple[str, str]] = []
    for benchmark in benchmarks:
        test_ids = _get_test_ids_for_benchmark(benchmark, limit)
        test_cases.extend((benchmark, tid) for tid in test_ids)

    metafunc.parametrize(["benchmark", "test_id"], test_cases)


# ========================================
# Hardness Evaluation
# ========================================


class HardnessResult(BaseModel):
    """Result of hardness evaluation."""

    hardness: int = Field(ge=1, le=10, description="Hardness rating 1-10")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence in rating")
    explanation: str = Field(description="Explanation of hardness factors")
    primary_factors: list[str] = Field(min_length=1, max_length=5, description="Main factors affecting difficulty")


async def test_hardness(benchmark: str, test_id: str, model: str, output_dir: Path) -> None:
    """Evaluate task hardness without tool knowledge."""

    instruction, num_turns = _get_instruction_for_benchmark(benchmark, test_id)

    if not instruction:
        pytest.skip(f"No instruction found in {test_id}")

    # Run hardness evaluation
    config_path = Path(__file__).parent / "fastagent.config.yaml"
    instruction_path = Path(__file__).parent / "instruction.txt"

    fast = FastAgent("Hardness Test", config_path=str(config_path), ignore_unknown_args=True)

    @fast.agent(name="evaluator", model=model, instruction=instruction_path)
    async def run_evaluator() -> HardnessResult | None:
        async with fast.run() as agent:
            # Format the task for evaluation
            task_prompt = f"Rate the difficulty of this task:\n\n{instruction}"
            result, _ = await agent.evaluator.structured(task_prompt, model=HardnessResult)
            return result

    result = await run_evaluator()

    # Log result
    output_dir.mkdir(parents=True, exist_ok=True)

    result_data = {
        "test_id": test_id,
        "benchmark": benchmark,
        "instruction": instruction,
        "num_turns": num_turns,
        "hardness": result.hardness if result else None,
        "confidence": result.confidence if result else None,
        "explanation": result.explanation if result else None,
        "primary_factors": result.primary_factors if result else None,
    }

    results_file = output_dir / f"results_{benchmark}_{model.replace('/', '_')}.jsonl"
    with open(results_file, "a") as f:
        f.write(json.dumps(result_data) + "\n")
