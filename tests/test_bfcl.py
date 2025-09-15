"""BFCL evaluation tests using pytest."""

from pathlib import Path

import pytest
from fast_agent.core.logging.logger import get_logger

from src.evals.bfcl import evaluator, loader
from src.evals.bfcl.elicitation import create_elicitation_handler
from src.evals.runner import TestConfig, run_test_async


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
        # VALIDATE MODE: Just evaluate existing log
        log_dir = Path(request.config.getoption("--log-dir"))
        log_file = log_dir / f"{test_id}_fastagent.jsonl"

        if not log_file.exists():
            pytest.skip(f"Log file not found: {log_file}")

        evaluation = evaluator.evaluate_results(test_id, str(log_file))

        # ONLY CHECK VALIDATION - not irrelevance
        assert evaluation["validation"]["valid"], f"Validation failed for {test_id}"

    else:
        # RUN MODE: Execute test directly
        # Load data
        test_case = loader.load_test_entry(test_id)
        ground_truth = loader.load_ground_truth(test_id)

        # Setup paths
        config_path = Path(__file__).parent.parent / "src/evals/bfcl/config.yaml"
        instruction_path = Path(__file__).parent.parent / "src/evals/bfcl/instruction.txt"

        # Setup servers and elicitation
        server_names = [
            cls.lower().replace("_", "") for cls in test_case.get("involved_classes", [])
        ]
        logger = get_logger(f"bfcl.{test_id}")
        elicitation_handler = create_elicitation_handler(ground_truth, logger)

        # Run test DIRECTLY with async function
        config = TestConfig(
            test_case=test_case,
            config_path=config_path,
            instruction_path=instruction_path,
            model=model,
            temperature=0.001,
            output_dir=output_dir,
            elicitation_handler=elicitation_handler,
            server_names=server_names,
        )
        result = await run_test_async(config)

        if not result["success"]:
            pytest.fail(f"Test execution failed: {result.get('error')}")

        # Evaluate
        evaluation = evaluator.evaluate_results(test_id, result["output_file"])

        # ONLY CHECK VALIDATION - not irrelevance
        assert evaluation["validation"]["valid"], f"Validation failed for {test_id}"
