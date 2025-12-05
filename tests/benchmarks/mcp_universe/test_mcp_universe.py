"""MCP-Universe repository management evaluation tests using pytest."""

import json
import os
from dataclasses import dataclass
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


def _find_tool_name(messages: list[Any], tool_id: str) -> str:
    """Find tool name from messages by tool_id."""
    for msg in messages:
        if hasattr(msg, "tool_calls") and msg.tool_calls and tool_id in msg.tool_calls:
            return str(msg.tool_calls[tool_id].params.name)
    return "unknown"


def _get_final_assistant_message(messages: list[Any]) -> str | None:
    """Extract the final assistant text message from message history."""
    for msg in reversed(messages):
        if hasattr(msg, "role") and msg.role == "assistant" and hasattr(msg, "content"):
            for content_item in msg.content:
                if hasattr(content_item, "text") and content_item.text:
                    return str(content_item.text)
    return None


def _determine_completion_status(
    total_tool_calls: int, errors: list[dict[str, Any]], final_msg: str | None
) -> tuple[str, str]:
    """Determine completion status and reason based on execution results."""
    if total_tool_calls >= MAX_ITERATIONS:
        return "max_iterations", f"Agent reached maximum iteration limit ({total_tool_calls} tool calls)"
    if errors and not final_msg:
        return "error", f"Agent encountered {len(errors)} error(s) and did not complete"
    if errors:
        return "completed", f"Agent completed with {len(errors)} recoverable error(s) during execution"
    return "completed", "Agent completed all requested tasks"


@dataclass
class LoggingContext:
    """Context for logging during test execution."""

    structured: StructuredEventLogger
    human: HumanReadableLogger
    errors: list[dict[str, Any]]


def _process_message_logs(
    msg_obj: Any, turn_idx: int, new_messages: list[Any], ctx: LoggingContext
) -> int:
    """Process and log tool calls, results, and assistant responses. Returns tool call count."""
    tool_call_count = 0

    # Log tool calls
    if hasattr(msg_obj, "tool_calls") and msg_obj.tool_calls:
        for tool_id, call in msg_obj.tool_calls.items():
            tool_call_count += 1
            args = call.params.arguments or {}
            ctx.structured.log_tool_call(turn_idx, call.params.name, args, tool_id)
            ctx.human.log_tool_call(turn_idx, call.params.name, args)

    # Log tool results
    if hasattr(msg_obj, "tool_results") and msg_obj.tool_results:
        for tool_id, result in msg_obj.tool_results.items():
            result_content = _extract_text_content(result.content) if hasattr(result, "content") else []
            is_error = result.isError if hasattr(result, "isError") else False
            tool_name = _find_tool_name(new_messages, tool_id)
            result_data = result_content if result_content else str(result)

            ctx.structured.log_tool_result(turn_idx, tool_id, result_data, is_error)
            ctx.human.log_tool_result(turn_idx, tool_name, result_data, is_error)

            if is_error:
                ctx.errors.append({
                    "turn_id": turn_idx,
                    "tool_id": tool_id,
                    "tool_name": tool_name,
                    "error_message": str(result_data),
                })

    # Log assistant text responses
    if hasattr(msg_obj, "role") and msg_obj.role == "assistant" and hasattr(msg_obj, "content"):
        for text in _extract_text_content(msg_obj.content):
            ctx.structured.log_assistant_response(turn_idx, text)
            ctx.human.log_assistant_response(turn_idx, text)

    return tool_call_count


def _setup_environment(model: str, temperature: float) -> None:
    """Validate and set up environment variables for test execution."""
    if not os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN"):
        raise ValueError(
            "GITHUB_PERSONAL_ACCESS_TOKEN environment variable not set. Please set it before running tests."
        )
    github_account_name = os.getenv("GITHUB_PERSONAL_ACCOUNT_NAME", "vinamra-test")
    os.environ.update({
        "DEFAULT_MODEL": model,
        "TEMPERATURE": str(temperature),
        "GITHUB_PERSONAL_ACCOUNT_NAME": github_account_name,
    })


def _get_task_description(task: dict[str, Any]) -> str:
    """Extract task description from task data."""
    task_description = task.get("question", "")
    if isinstance(task_description, list):
        return "\n".join(str(q) for q in task_description)
    return str(task_description)


async def _run_mcp_universe_test(test_id: str, model: str, temperature: float, output_dir: Path) -> Path:
    """Run MCP-Universe test and return path to results."""
    # Initialize loggers
    raw_dir = output_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    structured_logger = StructuredEventLogger(raw_dir / f"{test_id}_structured.jsonl")
    human_logger = HumanReadableLogger(raw_dir / f"{test_id}_readable.log")

    _setup_environment(model, temperature)
    task_file = _DATA_DIR.joinpath(f"{test_id}.json")
    with task_file.open("r", encoding="utf-8") as f:
        task = cast(dict[str, Any], json.load(f))
    human_logger.log_test_start(test_id, model, _get_task_description(task))

    output_path = raw_dir / f"{test_id}_complete.json"
    test_dir = Path(__file__).parent
    config_path = str(test_dir / "fastagent.config.yaml")
    agent = FastAgent("MCP-Universe Test", config_path=config_path, ignore_unknown_args=True)

    @agent.agent(
        name="test_agent",
        model=model,
        servers=["github"],
        instruction=test_dir / "instruction.txt",
        request_params=RequestParams(maxTokens=MAX_TOKENS, max_iterations=MAX_ITERATIONS),
    )
    async def run_test() -> Path:
        async with agent.run() as agent_app:
            questions = task.get("question", [])

            # Handle both single string and list formats
            if isinstance(questions, str):
                questions = [questions]
            elif not isinstance(questions, list):
                questions = []

            prev_message_count = 0
            total_tool_calls = 0
            log_ctx = LoggingContext(structured=structured_logger, human=human_logger, errors=[])

            for turn_idx, question in enumerate(questions, 1):
                user_msg = _parse_question(question)
                if not user_msg:
                    continue

                structured_logger.log_turn(turn_idx, "start", user_msg)
                human_logger.log_turn_start(turn_idx, user_msg)
                await agent_app.send(user_msg)

                # Extract messages added in this turn for detailed logging
                messages = agent_app._agent(None).message_history
                new_messages = messages[prev_message_count:]
                prev_message_count = len(messages)

                # Log tool calls, results, and assistant responses
                for msg_obj in new_messages:
                    total_tool_calls += _process_message_logs(msg_obj, turn_idx, new_messages, log_ctx)

                structured_logger.log_turn(turn_idx, "end")
                human_logger.log_turn_end(turn_idx)

            # Get messages for output
            messages = agent_app._agent(None).message_history
            structured_logger.log_message_summary(messages)

            # Log error summary if any errors occurred
            if log_ctx.errors:
                human_logger.log_errors(log_ctx.errors)

            # Determine completion status
            final_assistant_msg = _get_final_assistant_message(messages)
            status, reason = _determine_completion_status(total_tool_calls, log_ctx.errors, final_assistant_msg)

            human_logger.log_execution_summary(
                status=status,
                reason=reason,
                total_tool_calls=total_tool_calls,
                error_count=len(log_ctx.errors),
                total_turns=len(questions),
            )

            # Save output using MessageSerializer (BFCL pattern)
            complete_json = MessageSerializer.serialize_complete(messages)
            output_path.write_text(complete_json)

            return output_path

    return await run_test()


async def _validate_test(test_id: str, log_dir: Path) -> dict[str, Any]:
    """Validate test results and log to human-readable file."""
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

    # Log to human-readable file if it exists
    human_log_path = log_dir / f"{test_id}_readable.log"
    if human_log_path.exists():
        _log_evaluation_results(human_log_path, evaluation)

    return evaluation


def _log_evaluation_results(log_path: Path, evaluation: dict[str, Any]) -> None:
    """Log evaluation results to human-readable log."""
    human_logger = HumanReadableLogger(log_path)
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
            test_ids = sorted(
                e.name.removesuffix(".json")
                for e in _DATA_DIR.iterdir()
                if e.is_file() and e.name.startswith("github_task_") and e.name.endswith(".json")
            )

        metafunc.parametrize("test_id", test_ids)


@pytest.mark.asyncio
async def test_mcp_universe(
    test_id: str, model: str, temperature: float, output_dir: Path, request: pytest.FixtureRequest
) -> None:
    """Run or validate a MCP-Universe repository management test."""
    validate_only = request.config.getoption("--validate-only")

    # Run test if not in validate-only mode
    if not validate_only:
        await _run_mcp_universe_test(test_id, model, temperature, output_dir)

    # Determine log directory
    log_dir = Path(request.config.getoption("--log-dir")) if validate_only else output_dir / "raw"

    # Validate and get results
    evaluation = await _validate_test(test_id, log_dir)

    # Fail test with detailed message if evaluation failed
    if not evaluation["passed"]:
        failures = [
            f"  - {r['func']} {r['op']}: {r.get('reason') or r.get('error')}"
            for r in evaluation["evaluation_results"]
            if not r["passed"]
        ]
        pytest.fail(f"Evaluation failed for {test_id}:\n" + "\n".join(failures))
