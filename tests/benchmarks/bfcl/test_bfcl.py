"""BFCL evaluation tests using pytest."""

import asyncio
import json
import os
from pathlib import Path
from typing import Any, cast

import pytest

from tests.benchmarks.bfcl import evaluator, loader
from tests.benchmarks.bfcl.elicitation import create_elicitation_handler
from tests.utils.fastagent_helpers import MessageSerializer
from tests.utils.logger import StructuredEventLogger


def _parse_question(question: Any) -> str:
    """Parse question from various formats into a string."""
    if isinstance(question, list) and question:
        return question[0] if isinstance(question[0], str) else cast(str, question[0].get("content", ""))
    elif isinstance(question, str):
        return question
    elif isinstance(question, dict) and "content" in question:
        return cast(str, question["content"])
    return ""


async def _run_bfcl_test(test_id: str, model: str, temperature: float, output_dir: Path) -> Path:
    """Run BFCL test and return path to complete.json."""
    from fast_agent import FastAgent

    test_case = loader.load_test_entry(test_id)
    ground_truth = loader.load_ground_truth(test_id)

    instruction_path = Path(__file__).parent / "instruction.txt"
    structured_log_path = output_dir / "raw" / f"{test_id}_structured.jsonl"
    structured_log_path.parent.mkdir(parents=True, exist_ok=True)

    structured_logger = StructuredEventLogger(structured_log_path)
    elicitation_handler = create_elicitation_handler(ground_truth, structured_logger)

    test_data_path = output_dir / f"{test_id}_test.json"
    test_data_path.write_text(json.dumps(test_case))

    # Set environment variables BEFORE creating FastAgent
    test_dir = Path(__file__).parent
    os.environ.update(
        {
            "DEFAULT_MODEL": model,
            "TEMPERATURE": str(temperature),
            "TEST_DATA_PATH": str(test_data_path.absolute()),
            "TEST_ID": test_id,
            "SERVER_SCRIPT_PATH": str(test_dir / "mcp_server.py"),
        }
    )

    # Create FastAgent after environment variables are set
    config_path = test_dir / "fastagent.config.yaml"
    agent = FastAgent("BFCL Test", config_path=str(config_path), ignore_unknown_args=True)

    server_names = [cls.lower().replace("_", "") for cls in test_case.get("involved_classes", [])]

    @agent.agent(
        name="test_agent",
        model=model,
        servers=server_names,
        instruction=instruction_path,
        elicitation_handler=elicitation_handler,  # type: ignore[arg-type]
    )
    async def run_test() -> Path:
        async with agent.run() as agent_app:
            questions = test_case.get("question", [])

            for turn_idx, question in enumerate(questions, 1):
                msg = _parse_question(question)
                if not msg:
                    continue

                structured_logger.log_turn(turn_idx, "start", msg)
                await agent_app.send(msg)
                structured_logger.log_turn(turn_idx, "end")
                await asyncio.sleep(0)

            messages = agent_app._agent(None).message_history
            structured_logger.log_message_summary(messages)

            complete_json = MessageSerializer.serialize_complete(messages)
            complete_path = output_dir / "raw" / f"{test_id}_complete.json"
            complete_path.write_text(complete_json)

            return complete_path

    return await run_test()


def _validate_from_complete_json(test_id: str, complete_path: Path) -> dict[str, Any]:
    """Validate test from complete.json file."""
    if not complete_path.exists():
        pytest.skip(f"Complete JSON file not found: {complete_path}")

    with open(complete_path) as f:
        complete_data = json.load(f)

    tool_calls = MessageSerializer.extract_tool_calls_by_turn(complete_data)
    executable_format = MessageSerializer.format_to_executable(tool_calls)
    return evaluator._run_evaluation(test_id, tool_calls, executable_format)


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Dynamically generate test cases."""
    if "test_id" in metafunc.fixturenames:
        validate_only = metafunc.config.getoption("--validate-only")

        if validate_only:
            # Find existing log files to validate
            log_dir = Path(metafunc.config.getoption("--log-dir"))
            if log_dir.exists():
                log_files = list(log_dir.glob("**/*_fastagent.jsonl"))
                test_ids = [f.stem.replace("_fastagent", "") for f in log_files]
            else:
                test_ids = []
        else:
            # Generate all test IDs for running
            test_ids = loader.find_all_test_ids()

        if test_ids:
            metafunc.parametrize("test_id", test_ids)
        else:
            # No tests found, skip
            metafunc.parametrize("test_id", [], ids=[])


@pytest.mark.asyncio
async def test_bfcl(
    test_id: str, model: str, temperature: float, output_dir: Path, request: pytest.FixtureRequest
) -> None:
    """Run or validate a BFCL test based on mode."""
    if request.config.getoption("--validate-only"):
        log_dir = Path(request.config.getoption("--log-dir"))
    else:
        await _run_bfcl_test(test_id, model, temperature, output_dir)
        log_dir = output_dir / "raw"

    complete_path = log_dir / f"{test_id}_complete.json"
    evaluation = _validate_from_complete_json(test_id, complete_path)
    assert evaluation["validation"]["valid"], f"Validation failed for {test_id}"
