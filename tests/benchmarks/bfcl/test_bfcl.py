"""BFCL evaluation tests using pytest."""

import json
from pathlib import Path

import pytest

from src.evals.benchmarks.bfcl import evaluator, loader
from src.evals.benchmarks.bfcl.elicitation import create_elicitation_handler
from src.evals.core.logger import StructuredEventLogger
from src.evals.core.runner import TestConfig, run_test_async
from src.evals.core.serializer import MessageSerializer


def pytest_generate_tests(metafunc):
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
async def test_bfcl(test_id, model, output_dir, request):
    """Run or validate a BFCL test based on mode."""
    validate_only = request.config.getoption("--validate-only")

    if validate_only:
        # VALIDATE MODE: Extract from complete.json and evaluate
        log_dir = Path(request.config.getoption("--log-dir"))
        complete_file = log_dir / f"{test_id}_complete.json"

        if not complete_file.exists():
            pytest.skip(f"Complete JSON file not found for {test_id}")

        with open(complete_file) as f:
            complete_data = json.load(f)

        tool_calls = MessageSerializer.extract_tool_calls_by_turn(complete_data)
        executable_format = MessageSerializer.format_to_executable(tool_calls)
        evaluation = evaluator._run_evaluation(test_id, tool_calls, executable_format)

        # ONLY CHECK VALIDATION - not irrelevance
        assert evaluation["validation"]["valid"], f"Validation failed for {test_id}"

    else:
        # RUN MODE: Execute test directly
        test_case = loader.load_test_entry(test_id)
        ground_truth = loader.load_ground_truth(test_id)

        config_path = Path(__file__).parent.parent / "src/evals/bfcl/config.yaml"
        instruction_path = Path(__file__).parent.parent / "src/evals/bfcl/instruction.txt"

        server_names = [
            cls.lower().replace("_", "") for cls in test_case.get("involved_classes", [])
        ]

        structured_log_path = output_dir / "raw" / f"{test_id}_structured.jsonl"
        structured_logger = StructuredEventLogger(structured_log_path)

        elicitation_handler = create_elicitation_handler(ground_truth, structured_logger)

        config = TestConfig(
            test_case=test_case,
            config_path=config_path,
            instruction_path=instruction_path,
            model=model,
            temperature=0.001,
            output_dir=output_dir,
            elicitation_handler=elicitation_handler,
            server_names=server_names,
            structured_logger=structured_logger,
        )
        result = await run_test_async(config)

        if not result["success"]:
            pytest.fail(f"Test execution failed: {result.get('error')}")

        # Load complete.json, extract tool calls, and evaluate
        with open(result["complete_messages"]) as f:
            complete_data = json.load(f)

        tool_calls = MessageSerializer.extract_tool_calls_by_turn(complete_data)
        executable_format = MessageSerializer.format_to_executable(tool_calls)
        evaluation = evaluator._run_evaluation(test_id, tool_calls, executable_format)

        # ONLY CHECK VALIDATION - not irrelevance
        assert evaluation["validation"]["valid"], f"Validation failed for {test_id}"
