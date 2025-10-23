"""AppWorld evaluation tests using pytest."""

import asyncio
import os
from datetime import datetime
from pathlib import Path

import pytest
from appworld import load_task_ids
from appworld.common.path_store import path_store
from appworld.evaluator import evaluate_task
from appworld.task import Task
from fast_agent import FastAgent

from tests.benchmarks.appworld import api_predictor, prompts
from tests.utils.fastagent_helpers import MessageSerializer
from tests.utils.logger import StructuredEventLogger

# ========================================
# Pytest Configuration
# ========================================


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Dynamically generate test cases from AppWorld dataset."""
    if "task_id" not in metafunc.fixturenames:
        return

    validate_only = metafunc.config.getoption("--validate-only", False)

    if validate_only:
        # Find existing log files to validate
        log_dir = Path(metafunc.config.getoption("--log-dir", "outputs/raw"))
        log_files = list(log_dir.glob("**/*_complete.json")) if log_dir.exists() else []
        task_ids = [f.stem.replace("_complete", "") for f in log_files]
    else:
        # Load task IDs from AppWorld dataset
        dataset = metafunc.config.getoption("--dataset", "train")
        limit = metafunc.config.getoption("--limit", None)
        task_ids = load_task_ids(dataset)
        if limit and limit > 0:
            task_ids = task_ids[:limit]

    metafunc.parametrize("task_id", task_ids if task_ids else [], ids=[])


# ========================================
# Main Test
# ========================================


@pytest.mark.asyncio
@pytest.mark.timeout(300)
async def test_appworld(
    task_id: str,
    model: str,
    temperature: float,
    output_dir: Path,
    api_mode: str,
    request: pytest.FixtureRequest,
) -> None:
    """Run or validate an AppWorld test."""
    validate_only = request.config.getoption("--validate-only", False)

    # Run test if not in validate-only mode
    if not validate_only:
        experiment_name = await _run_appworld_test(task_id, model, temperature, output_dir, api_mode)
    else:
        experiment_name = _get_latest_experiment_name()

    # Get log directory and complete.json path
    log_dir = Path(request.config.getoption("--log-dir", "outputs/raw")) if validate_only else output_dir / "raw"
    complete_path = log_dir / f"{task_id}_complete.json"

    # Skip if complete.json doesn't exist
    if not complete_path.exists():
        pytest.skip(f"Complete JSON not found: {complete_path}")

    # Evaluate and assert success
    test_tracker = evaluate_task(
        task_id=task_id,
        experiment_name=experiment_name,
        suppress_errors=False,
        save_report=True,
    )

    assert test_tracker.success, (
        f"Task {task_id} failed: {test_tracker.failures[0] if test_tracker.failures else 'Unknown'}"
    )


# ========================================
# Test Implementation Helpers
# ========================================


async def _run_appworld_test(
    task_id: str,
    model: str,
    temperature: float,
    output_dir: Path,
    api_mode: str,
) -> str:
    """Run AppWorld test and return experiment name."""
    # Generate unique experiment name
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    experiment_name = f"wags-appworld-benchmark-{timestamp}"

    # Load task
    task = Task.load(
        task_id=task_id,
        storage_type="memory",
        load_ground_truth=True,
        ground_truth_mode="minimal",
        include_api_response_schemas=True,
    )

    # Setup logging
    log_dir = output_dir / "raw"
    log_dir.mkdir(parents=True, exist_ok=True)
    structured_logger = StructuredEventLogger(log_dir / f"{task_id}_structured.jsonl")

    # Setup MCP environment
    _setup_mcp_environment(task_id, model, temperature, experiment_name, api_mode)

    # Create and run FastAgent
    config_path = Path(__file__).parent / "fastagent.config.yaml"
    agent = FastAgent("AppWorld Test", config_path=str(config_path), ignore_unknown_args=True)
    system_instruction = prompts.load_system_instruction(task)

    @agent.agent(
        name="test_agent",
        model=model,
        servers=["appworld"],
        instruction=system_instruction,
    )
    async def run_test() -> None:
        async with agent.run() as agent_app:
            # Send task instruction
            structured_logger.log_turn(1, "start", task.instruction)
            await agent_app.send(task.instruction)
            structured_logger.log_turn(1, "end")
            await asyncio.sleep(0)

            # Save conversation
            messages = agent_app._agent(None).message_history
            structured_logger.log_message_summary(messages)
            complete_json = MessageSerializer.serialize_complete(messages)
            (log_dir / f"{task_id}_complete.json").write_text(complete_json)

    await run_test()
    return experiment_name


def _setup_mcp_environment(
    task_id: str,
    model: str,
    temperature: float,
    experiment_name: str,
    api_mode: str,
) -> None:
    """Configure environment variables for MCP server."""
    # Predict which APIs are needed
    try:
        predicted_apis = api_predictor.predict_apis(task_id, mode=api_mode, model_name=model)
        print(f"API mode: {api_mode}, predicted {len(predicted_apis)} APIs")
    except NotImplementedError:
        print(f"Warning: {api_mode} mode not supported, falling back to ground_truth")
        predicted_apis = api_predictor.predict_apis(task_id, mode="ground_truth", model_name=model)

    # Set environment variables
    os.environ.update(
        {
            "DEFAULT_MODEL": model,
            "TEMPERATURE": str(temperature),
            "TASK_ID": task_id,
            "SERVER_SCRIPT_PATH": str(Path(__file__).parent / "mcp_server.py"),
            "EXPERIMENT_NAME": experiment_name,
            "ALLOWED_APIS": ",".join(predicted_apis),
        }
    )


def _get_latest_experiment_name() -> str:
    """Find the most recent experiment directory."""
    experiment_dirs = sorted(
        Path(path_store.experiment_outputs).glob("wags-appworld-benchmark-*"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return experiment_dirs[0].name if experiment_dirs else "wags-appworld-benchmark"
