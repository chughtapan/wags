"""MCP-Universe repository management evaluation tests using pytest."""

import asyncio
import json
import os
from pathlib import Path
from typing import Any

import pytest
from fast_agent import FastAgent
from mcpuniverse.common.context import Context

from tests.benchmarks.mcp_universe import evaluator, loader


async def _run_mcp_universe_test(test_id: str, model: str, temperature: float, output_dir: Path) -> Path:
    """Run MCP-Universe test and return path to results."""

    task = loader.load_task(test_id)

    instruction_path = Path(__file__).parent / "instruction.txt"
    instruction_content = instruction_path.read_text(encoding="utf-8")
    output_path = output_dir / "raw" / f"{test_id}_output.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

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
        instruction=instruction_content,
    )
    async def run_test() -> Path:
        async with agent.run() as agent_app:
            question = task.get("question", "")

            if question:
                await agent_app.send(question)
                await asyncio.sleep(0)

            # Get messages for output
            messages = agent_app._agent(None).message_history

            # Save output
            output_data = {
                "task_id": test_id,
                "question": question,
                "messages": [
                    {
                        "role": msg.role,
                        "content": str(msg.content) if hasattr(msg, "content") else "",
                    }
                    for msg in messages
                ],
            }
            output_path.write_text(json.dumps(output_data, indent=2))

            return output_path

    return await run_test()


async def _validate_from_output(test_id: str, output_path: Path) -> dict[str, Any]:
    """Validate test from output file."""
    if not output_path.exists():
        pytest.skip(f"Output file not found: {output_path}")

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
                output_files = list(log_dir.glob("**/*_output.json"))
                test_ids = [f.stem.replace("_output", "") for f in output_files]
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

    output_path = log_dir / f"{test_id}_output.json"
    evaluation = await _validate_from_output(test_id, output_path)

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
