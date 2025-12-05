"""AppWorld evaluation tests using pytest."""

import asyncio
import os
from pathlib import Path

import pytest
from appworld import load_task_ids
from appworld.evaluator import evaluate_task
from appworld.task import Task
from fast_agent import FastAgent
from fast_agent.llm.request_params import RequestParams

from tests.benchmarks.appworld import api_predictor, prompts
from tests.benchmarks.appworld.conftest import get_experiment_name, parse_datasets
from tests.benchmarks.appworld.reporting import (
    find_evaluation_report,
    generate_failure_report,
    load_complete_json,
    parse_evaluation_report,
)
from tests.utils.fastagent_helpers import MessageSerializer
from tests.utils.logger import StructuredEventLogger

# ========================================
# Pytest Configuration
# ========================================


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Dynamically generate test cases from AppWorld dataset(s)."""
    if "task_id" not in metafunc.fixturenames:
        return

    validate_only = metafunc.config.getoption("--validate-only", False)

    if validate_only:
        # Auto-detect log directory from experiment_name
        exp_name = get_experiment_name(metafunc.config)
        log_dir = Path("results") / exp_name / "outputs" / "raw"

        # Find existing log files to validate
        log_files = list(log_dir.glob("*_complete.json")) if log_dir.exists() else []
        task_ids = [f.stem.replace("_complete", "") for f in log_files]

        if not task_ids:
            pytest.exit(
                f"\nError: No test results found in {log_dir}\n"
                f"Expected to find *_complete.json files for validation.\n"
                f"Run tests first or check --appworld-experiment-name."
            )
    else:
        # Load task IDs from AppWorld dataset(s)
        datasets_str = metafunc.config.getoption("--datasets", "train,dev")
        datasets = parse_datasets(datasets_str)

        # Collect task IDs from all specified datasets
        task_ids = []
        for dataset in datasets:
            task_ids.extend(load_task_ids(dataset))

        # Apply --start-from filter first (before --limit)
        start_from = metafunc.config.getoption("--start-from", None)
        if start_from:
            try:
                start_index = task_ids.index(start_from)
                task_ids = task_ids[start_index:]
                print(f"\nStarting from task '{start_from}' (index {start_index}, {len(task_ids)} tasks remaining)")
            except ValueError:
                # Task ID not found - provide helpful error
                pytest.exit(
                    f"\nError: Task ID '{start_from}' not found in datasets {datasets}.\n"
                    f"Available task IDs (first 10): {', '.join(task_ids[:10])}\n"
                    f"Total tasks: {len(task_ids)}\n"
                    f"Use: pytest tests/benchmarks/appworld/test_appworld.py --datasets {datasets_str} "
                    f"--collect-only to see all task IDs."
                )

        # Apply --limit filter (after --start-from)
        limit = metafunc.config.getoption("--limit", None)
        if limit and limit > 0:
            task_ids = task_ids[:limit]

    metafunc.parametrize("task_id", task_ids if task_ids else [], ids=[])


# ========================================
# Main Test
# ========================================


@pytest.mark.asyncio
async def test_appworld(
    task_id: str,
    model: str,
    temperature: float,
    output_dir: Path,
    api_mode: str,
    experiment_name: str,
    use_few_shot: bool,
    request: pytest.FixtureRequest,
) -> None:
    """Run or validate an AppWorld test."""
    validate_only = request.config.getoption("--validate-only", False)

    # Run test if not in validate-only mode
    if not validate_only:
        await _run_appworld_test(task_id, model, temperature, output_dir, api_mode, experiment_name, use_few_shot)

    # Get complete.json path (always in output_dir/raw now)
    complete_path = output_dir / "raw" / f"{task_id}_complete.json"

    # Skip if complete.json doesn't exist
    if not complete_path.exists():
        pytest.skip(f"Complete JSON not found: {complete_path}")

    # Check if database directory exists before evaluation
    # If the agent didn't call complete_task, the database won't be saved and evaluate_task will fail
    from appworld.apps.lib.models.db import get_db_home_path
    from appworld.evaluator import TestTracker

    db_path = get_db_home_path(
        storage_type="disk",
        type="task_output",
        task_id=task_id,
        experiment_name=experiment_name,
    )

    if not Path(db_path).exists():
        # Database not saved - agent didn't complete the task
        # Create a failed test tracker without calling evaluate_task
        from appworld.evaluator import Failure

        test_tracker = TestTracker()
        failure: Failure = {
            "requirement": "Agent must call complete_task to save results",
            "trace": f"Database not found at {db_path}",
            "label": None,
        }
        test_tracker.failures.append(failure)
    else:
        # Evaluate and assert success
        # NOTE: Use suppress_errors=True to ensure evaluate_task() completes and saves the report
        # even when the task fails. With suppress_errors=False, it raises an exception before
        # saving the report or stopping the time_freezer, causing subsequent tests to hang.
        #
        # IMPORTANT: evaluate_task() can still raise exceptions during setup (e.g., missing database files)
        # BEFORE stopping the time_freezer. We use try/finally to ensure cleanup always happens.
        try:
            test_tracker = evaluate_task(
                task_id=task_id,
                experiment_name=experiment_name,
                suppress_errors=True,
                save_report=True,
            )
        finally:
            # Always ensure time is unfrozen, even if evaluate_task fails during setup
            # This prevents subsequent tests from hanging
            # Note: We manually restore datetime because we don't have access to the freezer instance
            # created inside evaluate_task(). Just clearing tz_offsets isn't enough - we must also
            # restore the real datetime module, otherwise datetime.now() crashes with IndexError.
            try:
                import datetime
                import sys

                from freezegun import api

                api.tz_offsets.clear()
                # Restore real datetime classes in both the datetime module and the global namespace
                setattr(datetime, "datetime", api.real_datetime)
                setattr(datetime, "date", api.real_date)
                # Also restore in sys.modules to ensure all imports see the real datetime
                sys.modules["datetime"].datetime = api.real_datetime  # type: ignore[attr-defined]
                sys.modules["datetime"].date = api.real_date  # type: ignore[attr-defined]
            except Exception:
                pass  # If freeze_time cleanup fails, continue anyway

        # Generate failure report if test failed validation
        if not test_tracker.success:
            _generate_failure_report_inline(task_id, output_dir, model, experiment_name, request)

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
    experiment_name: str,
    use_few_shot: bool,
) -> None:
    """Run AppWorld test using the provided experiment name."""

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
    system_instruction = prompts.load_system_instruction(task, use_few_shot=use_few_shot)

    @agent.agent(
        name="test_agent",
        model=model,
        servers=["appworld"],
        instruction=system_instruction,
        request_params=RequestParams(maxTokens=16000, max_iterations=500),
    )
    async def run_test() -> None:
        async with agent.run() as agent_app:
            try:
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
            finally:
                # ALWAYS disconnect MCP servers before exiting, even on failure
                # FastAgent's cleanup doesn't disconnect servers, causing them to hang
                connection_manager = getattr(agent.context, "_connection_manager", None)
                if connection_manager is None:
                    raise RuntimeError("MCP connection manager not found - cannot disconnect servers")
                await connection_manager.disconnect_all()

    await run_test()


def _generate_failure_report_inline(
    task_id: str,
    output_dir: Path,
    model: str,
    experiment_name: str,
    request: pytest.FixtureRequest,
) -> None:
    """Generate failure report immediately after test fails validation."""
    # Find evaluation report using precise path
    report_path = find_evaluation_report(task_id, experiment_name)
    if not report_path:
        print(f"⚠️  {task_id}: No evaluation report found, skipping failure report generation")
        return

    # Parse evaluation data
    eval_data = parse_evaluation_report(report_path)

    # Only generate report if test actually failed validation
    if eval_data["success"]:
        return

    # Load task with ground truth
    task = Task.load(
        task_id=task_id,
        storage_type="memory",
        load_ground_truth=True,
        ground_truth_mode="full",
    )

    # Load complete.json
    complete_data = load_complete_json(output_dir, task_id)

    # Derive failure_report_dir from output_dir (same parent directory)
    # output_dir: results/{model}/{datasets}/outputs
    # failure_report_dir: results/{model}/{datasets}/failure_reports
    failure_report_dir = output_dir.parent / "failure_reports"
    failure_report_dir.mkdir(parents=True, exist_ok=True)

    # Generate failure report
    output_path = failure_report_dir / f"failure_report_{task_id}.md"
    generate_failure_report(task_id, task, eval_data, complete_data, output_path)
    print(f"📝 Generated failure report: {output_path}")


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
