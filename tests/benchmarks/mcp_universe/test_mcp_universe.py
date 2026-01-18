"""MCP-Universe repository management evaluation tests using pytest."""

import json
import os
from importlib import resources
from pathlib import Path
from typing import Any, cast

import pytest
from fast_agent import FastAgent
from fast_agent.llm.request_params import RequestParams
from mcpuniverse.common.context import Context

# Import evaluator_patch first to apply patches before evaluator imports mcpuniverse functions
import tests.benchmarks.mcp_universe.evaluator_patch  # noqa: F401
from tests.benchmarks.mcp_universe import evaluator
from tests.benchmarks.mcp_universe.reporting import EvaluationCheck, HumanReadableLogger
from tests.utils.fastagent_helpers import MessageSerializer
from tests.utils.logger import StructuredEventLogger

# MCP-Universe data directory
_DATA_DIR = resources.files("mcpuniverse").joinpath("benchmark/configs/test/repository_management")

# Agent execution limits
MAX_ITERATIONS = 500
MAX_TOKENS = 16000

# Minimal toolset: union of all distinct tools used by successful runs
# Source: why-agents-fail-dataset/mcp_universe/checkpoint-2025-11-06/mcp_universe_tool_stats.csv
MINIMAL_TOOLSET = [
    "add_issue_comment",
    "create_branch",
    "create_issue",
    "create_or_update_file",
    "create_pull_request",
    "create_repository",
    "fork_repository",
    "get_file_contents",
    "get_issue",
    "get_issue_comments",
    "get_me",
    "get_pull_request",
    "list_branches",
    "list_issues",
    "push_files",
    "run_workflow",
    "search_code",
    "search_issues",
    "search_repositories",
]


def _parse_question(question: Any) -> str:
    """Parse question from various formats into a string."""
    if isinstance(question, list) and question:
        return question[0] if isinstance(question[0], str) else str(question[0])
    elif isinstance(question, str):
        return question
    elif isinstance(question, dict) and "content" in question:
        return str(question["content"])
    return ""


def _extract_text_content(content_items: Any) -> list[str]:
    """Extract text from content items that have a text attribute."""
    return [item.text for item in content_items if hasattr(item, "text")]


def _log_message(msg: Any, turn_idx: int, logger: StructuredEventLogger) -> int:
    """Log tool calls, results, and assistant responses. Returns tool call count."""
    tool_call_count = 0

    if hasattr(msg, "tool_calls") and msg.tool_calls:
        for tool_id, call in msg.tool_calls.items():
            tool_call_count += 1
            logger.log_tool_call(turn_idx, call.params.name, call.params.arguments or {}, tool_id)

    if hasattr(msg, "tool_results") and msg.tool_results:
        for tool_id, result in msg.tool_results.items():
            content = _extract_text_content(result.content) if hasattr(result, "content") else []
            is_error = getattr(result, "is_error", False)
            logger.log_tool_result(turn_idx, tool_id, content or str(result), is_error)

    if getattr(msg, "role", None) == "assistant" and hasattr(msg, "content"):
        for text in _extract_text_content(msg.content):
            logger.log_assistant_response(turn_idx, text)

    return tool_call_count


def _setup_environment(model: str, temperature: float) -> None:
    """Validate and set up environment variables for test execution."""
    if not os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN"):
        raise ValueError(
            "GITHUB_PERSONAL_ACCESS_TOKEN environment variable not set. Please set it before running tests."
        )
    if not os.getenv("GITHUB_PERSONAL_ACCOUNT_NAME"):
        raise ValueError(
            "GITHUB_PERSONAL_ACCOUNT_NAME environment variable not set. Please set it before running tests."
        )
    os.environ.update(
        {
            "DEFAULT_MODEL": model,
            "TEMPERATURE": str(temperature),
        }
    )


def _get_task_description(task: dict[str, Any]) -> str:
    """Extract task description from task data."""
    task_description = task.get("question", "")
    if isinstance(task_description, list):
        return "\n".join(str(q) for q in task_description)
    return str(task_description)


async def _run_mcp_universe_test(test_id: str, model: str, temperature: float, output_dir: Path, toolset: str) -> Path:
    """Run MCP-Universe test and return path to results."""
    raw_dir = output_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    logger = StructuredEventLogger(raw_dir / f"{test_id}_structured.jsonl")

    _setup_environment(model, temperature)
    task_file = _DATA_DIR.joinpath(f"{test_id}.json")
    with task_file.open("r", encoding="utf-8") as f:
        task = cast(dict[str, Any], json.load(f))

    output_path = raw_dir / f"{test_id}_complete.json"
    test_dir = Path(__file__).parent
    config_path = str(test_dir / "fastagent.config.yaml")
    agent = FastAgent("MCP-Universe Test", config_path=config_path, ignore_unknown_args=True)

    # Apply tool filtering based on toolset parameter
    tools_config = {"github": MINIMAL_TOOLSET} if toolset == "minimal" else None

    @agent.agent(
        name="test_agent",
        model=model,
        servers=["github"],
        tools=tools_config,
        instruction=test_dir / "instruction.txt",
        request_params=RequestParams(max_tokens=MAX_TOKENS, max_iterations=MAX_ITERATIONS),
    )
    async def run_test() -> Path:
        async with agent.run() as agent_app:
            questions = task.get("question", [])

            if isinstance(questions, str):
                questions = [questions]
            elif not isinstance(questions, list):
                questions = []

            prev_message_count = 0
            total_tool_calls = 0

            for turn_idx, question in enumerate(questions, 1):
                user_msg = _parse_question(question)
                if not user_msg:
                    continue

                logger.log_turn(turn_idx, "start", user_msg)
                await agent_app.send(user_msg)

                messages = agent_app._agent(None).message_history
                new_messages = messages[prev_message_count:]
                prev_message_count = len(messages)

                for msg in new_messages:
                    total_tool_calls += _log_message(msg, turn_idx, logger)

                logger.log_turn(turn_idx, "end")

            messages = agent_app._agent(None).message_history
            logger.log_message_summary(messages)

            complete_json = MessageSerializer.serialize_complete(messages)
            output_path.write_text(complete_json)

            return output_path

    return await run_test()


async def _validate_test(test_id: str, model: str, log_dir: Path) -> dict[str, Any]:
    """Validate test results and generate human-readable log."""
    complete_path = log_dir / f"{test_id}_complete.json"
    if not complete_path.exists():
        pytest.skip(f"Complete JSON file not found: {complete_path}")

    # Run evaluation
    context = Context()
    context.env = dict(os.environ)
    evaluation = await evaluator.run_evaluation(test_id, context=context)

    # Save evaluation results
    eval_path = log_dir / f"{test_id}_evaluation.json"
    eval_path.write_text(json.dumps(evaluation, indent=2, default=str))

    # Generate human-readable log from structured log
    structured_path = log_dir / f"{test_id}_structured.jsonl"
    human_log_path = log_dir / f"{test_id}_readable.log"

    if structured_path.exists():
        task_file = _DATA_DIR.joinpath(f"{test_id}.json")
        with task_file.open("r", encoding="utf-8") as f:
            task = cast(dict[str, Any], json.load(f))

        HumanReadableLogger.from_structured_log(
            human_log_path, structured_path, test_id, model, _get_task_description(task)
        )
        _log_evaluation_results(human_log_path, evaluation)

    return evaluation


def _log_evaluation_results(log_path: Path, evaluation: dict[str, Any]) -> None:
    """Log evaluation results to human-readable log."""
    human_logger = HumanReadableLogger(log_path, append=True)
    human_logger.log_evaluation_start()

    failed_checks = 0
    for idx, result in enumerate(evaluation["evaluation_results"], 1):
        if not result["passed"]:
            failed_checks += 1

        expected = None
        evaluators = evaluation.get("task_data", {}).get("evaluators", [])
        if idx - 1 < len(evaluators) and "value" in evaluators[idx - 1]:
            expected = evaluators[idx - 1].get("value")

        human_logger.log_evaluation_check(
            EvaluationCheck(
                check_num=idx,
                operation=result["op"],
                passed=result["passed"],
                reason=result.get("reason", "") or result.get("error", ""),
                expected=expected,
            )
        )

    human_logger.log_evaluation_summary(
        passed=evaluation["passed"],
        total_checks=len(evaluation["evaluation_results"]),
        failed_checks=failed_checks,
    )

    verdict = (
        "TEST PASSED"
        if evaluation["passed"]
        else f"TEST FAILED ({failed_checks}/{len(evaluation['evaluation_results'])} checks failed)"
    )
    human_logger.log_final_verdict(verdict)


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Dynamically generate test cases from task JSON files."""
    if "test_id" in metafunc.fixturenames:
        test_ids = sorted(
            e.name.removesuffix(".json")
            for e in _DATA_DIR.iterdir()
            if e.is_file() and e.name.startswith("github_task_") and e.name.endswith(".json")
        )
        metafunc.parametrize("test_id", test_ids)


@pytest.mark.asyncio
async def test_mcp_universe(  # noqa: PLR0913
    test_id: str, model: str, temperature: float, output_dir: Path, toolset: str, request: pytest.FixtureRequest
) -> None:
    """Run or validate a MCP-Universe repository management test."""
    validate_only = request.config.getoption("--validate-only")

    # Run test if not in validate-only mode
    if not validate_only:
        await _run_mcp_universe_test(test_id, model, temperature, output_dir, toolset)

    # Validate and get results
    log_dir = output_dir / "raw"
    evaluation = await _validate_test(test_id, model, log_dir)

    # Fail test with detailed message if evaluation failed
    if not evaluation["passed"]:
        failures = [
            f"  - {r['func']} {r['op']}: {r.get('reason') or r.get('error')}"
            for r in evaluation["evaluation_results"]
            if not r["passed"]
        ]
        pytest.fail(f"Evaluation failed for {test_id}:\n" + "\n".join(failures))
