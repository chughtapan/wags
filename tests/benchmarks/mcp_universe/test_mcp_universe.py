"""MCP-Universe repository management evaluation tests using pytest."""

import asyncio
import os
from pathlib import Path
from typing import Any

import pytest
from fast_agent import FastAgent
from mcpuniverse.common.context import Context

from tests.benchmarks.mcp_universe import evaluator, loader
from tests.utils.fastagent_helpers import MessageSerializer
from tests.utils.logger import StructuredEventLogger


def _parse_question(question: Any) -> str:
    """Parse question from various formats into a string."""
    if isinstance(question, list) and question:
        return question[0] if isinstance(question[0], str) else str(question[0])
    elif isinstance(question, str):
        return question
    elif isinstance(question, dict) and "content" in question:
        return str(question["content"])
    return ""


async def _run_mcp_universe_test(test_id: str, model: str, temperature: float, output_dir: Path) -> Path:
    """Run MCP-Universe test and return path to results."""

    task = loader.load_task(test_id)

    instruction_path = Path(__file__).parent / "instruction.txt"
    structured_log_path = output_dir / "raw" / f"{test_id}_structured.jsonl"
    structured_log_path.parent.mkdir(parents=True, exist_ok=True)

    structured_logger = StructuredEventLogger(structured_log_path)

    output_path = output_dir / "raw" / f"{test_id}_complete.json"

    # Set environment variables for the test
    test_dir = Path(__file__).parent
    os.environ.update(
        {
            "DEFAULT_MODEL": model,
            "TEMPERATURE": str(temperature),
        }
    )

    # Create FastAgent
    config_path = test_dir / "fastagent.config.yaml"
    agent = FastAgent("MCP-Universe Test", config_path=str(config_path), ignore_unknown_args=True)

    # Determine which servers to use (currently only github for repository management)
    server_names = ["github"]

    @agent.agent(
        name="test_agent",
        model=model,
        servers=server_names,
        instruction=instruction_path,
    )
    async def run_test() -> Path:
        async with agent.run() as agent_app:
            questions = task.get("question", [])

            # Handle both single string and list formats
            if isinstance(questions, str):
                questions = [questions]
            elif not isinstance(questions, list):
                questions = []

            for turn_idx, question in enumerate(questions, 1):
                msg = _parse_question(question)
                if not msg:
                    continue

                structured_logger.log_turn(turn_idx, "start", msg)
                await agent_app.send(msg)
                structured_logger.log_turn(turn_idx, "end")
                await asyncio.sleep(0)

            # Get messages for output
            messages = agent_app._agent(None).message_history
            structured_logger.log_message_summary(messages)

            # Save output using MessageSerializer (BFCL pattern)
            complete_json = MessageSerializer.serialize_complete(messages)
            output_path.write_text(complete_json)

            return output_path

    return await run_test()


async def _validate_from_output(test_id: str, complete_path: Path) -> dict[str, Any]:
    """Validate test from complete.json file."""
    if not complete_path.exists():
        pytest.skip(f"Complete JSON file not found: {complete_path}")

    # Create context with environment variables
    context = Context()
    context.env = dict(os.environ)

    # Run evaluation
    return await evaluator.run_evaluation(test_id, context=context)


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Dynamically generate test cases."""
    if "test_id" in metafunc.fixturenames:
        validate_only = metafunc.config.getoption("--validate-only")

        if validate_only:
            # Find existing output files to validate
            log_dir = Path(metafunc.config.getoption("--log-dir"))
            if log_dir.exists():
                output_files = list(log_dir.glob("**/*_complete.json"))
                test_ids = [f.stem.replace("_complete", "") for f in output_files]
            else:
                test_ids = []
        else:
            # Generate test IDs for repository management tasks
            test_ids = loader.find_all_task_ids()

        if test_ids:
            metafunc.parametrize("test_id", test_ids)
        else:
            metafunc.parametrize("test_id", [], ids=[])


@pytest.mark.asyncio
async def test_mcp_universe(
    test_id: str, model: str, temperature: float, output_dir: Path, request: pytest.FixtureRequest
) -> None:
    """Run or validate a MCP-Universe repository management test based on mode."""
    if request.config.getoption("--validate-only"):
        log_dir = Path(request.config.getoption("--log-dir"))
    else:
        await _run_mcp_universe_test(test_id, model, temperature, output_dir)
        log_dir = output_dir / "raw"

    complete_path = log_dir / f"{test_id}_complete.json"
    evaluation = await _validate_from_output(test_id, complete_path)

    # Create detailed failure message if evaluation failed
    if not evaluation["passed"]:
        failure_details = [
            f"  - {result['func']} {result['op']}: {result['reason'] or result['error']}"
            for result in evaluation["evaluation_results"]
            if not result["passed"]
        ]
        failure_msg = f"Evaluation failed for {test_id}:\n" + "\n".join(failure_details)
        assert evaluation["passed"], failure_msg
    else:
        assert evaluation["passed"], f"Validation failed for {test_id}"
