"""MCP-Universe repository management evaluation tests using pytest."""

import asyncio
import os
from pathlib import Path
from typing import Any

import pytest
import yaml
from fast_agent import FastAgent
from fast_agent.llm.request_params import RequestParams
from mcpuniverse.common.context import Context

# Load secrets from root-level fastagent.secrets.yaml and populate environment
_SECRETS_LOADED = False


def _load_secrets_once() -> None:
    """Load secrets from fastagent.secrets.yaml into environment variables (once)."""
    global _SECRETS_LOADED  # noqa: PLW0603
    if _SECRETS_LOADED:
        return

    secrets_path = Path(__file__).parent.parent.parent.parent / "fastagent.secrets.yaml"
    if secrets_path.exists():
        with open(secrets_path) as f:
            secrets = yaml.safe_load(f)

        # Extract GitHub credentials from MCP server config
        if "mcp" in secrets and "servers" in secrets["mcp"] and "github" in secrets["mcp"]["servers"]:
            github_env = secrets["mcp"]["servers"]["github"].get("env", {})
            if "GITHUB_PERSONAL_ACCESS_TOKEN" in github_env:
                os.environ["GITHUB_PERSONAL_ACCESS_TOKEN"] = github_env["GITHUB_PERSONAL_ACCESS_TOKEN"]
            if "GITHUB_PERSONAL_ACCOUNT_NAME" in github_env:
                os.environ["GITHUB_PERSONAL_ACCOUNT_NAME"] = github_env["GITHUB_PERSONAL_ACCOUNT_NAME"]

        # Extract OpenAI API key
        if "openai" in secrets and "api_key" in secrets["openai"]:
            os.environ["OPENAI_API_KEY"] = secrets["openai"]["api_key"]

        # Extract Anthropic API key
        if "anthropic" in secrets and "api_key" in secrets["anthropic"]:
            os.environ["ANTHROPIC_API_KEY"] = secrets["anthropic"]["api_key"]

    _SECRETS_LOADED = True


# Load secrets FIRST, before anything else
_load_secrets_once()

# CRITICAL: Apply patch BEFORE importing evaluator to ensure it works
from tests.benchmarks.mcp_universe.evaluator_patch import apply_patch  # noqa: E402

apply_patch()

# Now import evaluator and loader AFTER patch is applied
from tests.benchmarks.mcp_universe import evaluator, loader  # noqa: E402
from tests.benchmarks.mcp_universe.reporting import HumanReadableLogger  # noqa: E402
from tests.utils.fastagent_helpers import MessageSerializer  # noqa: E402
from tests.utils.logger import StructuredEventLogger  # noqa: E402


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

    # Initialize loggers FIRST to capture all events
    structured_log_path = output_dir / "raw" / f"{test_id}_structured.jsonl"
    human_log_path = output_dir / "raw" / f"{test_id}_readable.log"
    structured_log_path.parent.mkdir(parents=True, exist_ok=True)

    structured_logger = StructuredEventLogger(structured_log_path)
    human_logger = HumanReadableLogger(human_log_path)

    # Log infrastructure setup phase
    structured_logger.log_infrastructure_event(
        "test_initialization",
        "test_framework",
        "started",
        {"test_id": test_id, "model": model, "temperature": temperature},
    )
    human_logger.log_infrastructure_event(
        "test_initialization",
        "test_framework",
        "started",
        f"Starting test {test_id} with model {model} (temp={temperature})",
    )

    # Validate GitHub token is available
    if not os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN"):
        structured_logger.log_infrastructure_event(
            "github_auth", "github-api", "failed", {"error": "GITHUB_PERSONAL_ACCESS_TOKEN not set"}
        )
        human_logger.log_infrastructure_event(
            "github_auth", "github-api", "failed", "GITHUB_PERSONAL_ACCESS_TOKEN environment variable not set"
        )
        raise ValueError(
            "GITHUB_PERSONAL_ACCESS_TOKEN environment variable not set. Please set it before running tests."
        )

    # Set GitHub account name (required for evaluators)
    # Evaluators use {{GITHUB_PERSONAL_ACCOUNT_NAME}} placeholder
    github_account_name = os.getenv("GITHUB_PERSONAL_ACCOUNT_NAME", "vinamra-test")

    # Set environment variables FIRST, before any FastAgent initialization
    os.environ.update(
        {
            "DEFAULT_MODEL": model,
            "TEMPERATURE": str(temperature),
            "GITHUB_PERSONAL_ACCOUNT_NAME": github_account_name,
            # GITHUB_PERSONAL_ACCESS_TOKEN should already be in environment
        }
    )

    # Log GitHub authentication success
    structured_logger.log_infrastructure_event("github_auth", "github-api", "success", {"account": github_account_name})
    human_logger.log_infrastructure_event(
        "github_auth", "github-api", "success", f"GitHub authenticated as {github_account_name}"
    )

    # Load task
    structured_logger.log_infrastructure_event("task_loading", "test_framework", "started", {"test_id": test_id})
    task = loader.load_task(test_id)
    structured_logger.log_infrastructure_event(
        "task_loading",
        "test_framework",
        "success",
        {"test_id": test_id, "evaluator_count": len(task.get("evaluators", []))},
    )

    instruction_path = Path(__file__).parent / "instruction.txt"

    # Log test initialization
    task_description = task.get("question", "")
    if isinstance(task_description, list):
        task_description = "\n".join(str(q) for q in task_description)
    human_logger.log_test_start(test_id, model, str(task_description))

    output_path = output_dir / "raw" / f"{test_id}_complete.json"

    # Create FastAgent
    structured_logger.log_infrastructure_event(
        "fastagent_init", "fast-agent", "started", {"config_path": str(Path(__file__).parent / "fastagent.config.yaml")}
    )
    human_logger.log_infrastructure_event(
        "fastagent_init", "fast-agent", "started", "Initializing FastAgent with MCP server configuration"
    )

    test_dir = Path(__file__).parent
    config_path = test_dir / "fastagent.config.yaml"
    agent = FastAgent("MCP-Universe Test", config_path=str(config_path), ignore_unknown_args=True)

    structured_logger.log_infrastructure_event("fastagent_init", "fast-agent", "success", {})
    human_logger.log_infrastructure_event(
        "fastagent_init", "fast-agent", "success", "FastAgent initialized successfully"
    )

    # Determine which servers to use (currently only github for repository management)
    server_names = ["github"]

    structured_logger.log_infrastructure_event("mcp_servers", "mcp", "configuring", {"servers": server_names})
    human_logger.log_infrastructure_event(
        "mcp_servers", "mcp", "configuring", f"Configuring MCP servers: {', '.join(server_names)}"
    )

    @agent.agent(
        name="test_agent",
        model=model,
        servers=server_names,
        instruction=instruction_path,
        request_params=RequestParams(maxTokens=16000, max_iterations=500),
    )
    async def run_test() -> Path:
        structured_logger.log_infrastructure_event(
            "agent_execution", "fast-agent", "starting", {"max_tokens": 16000, "max_iterations": 500}
        )
        human_logger.log_infrastructure_event(
            "agent_execution",
            "fast-agent",
            "starting",
            "Agent execution starting (max_tokens=16000, max_iterations=500)",
        )

        async with agent.run() as agent_app:
            structured_logger.log_infrastructure_event("agent_execution", "fast-agent", "running", {})
            human_logger.log_infrastructure_event(
                "agent_execution", "fast-agent", "running", "Agent is now running and ready to process requests"
            )
            questions = task.get("question", [])

            # Handle both single string and list formats
            if isinstance(questions, str):
                questions = [questions]
            elif not isinstance(questions, list):
                questions = []

            prev_message_count = 0
            total_tool_calls = 0
            errors = []

            for turn_idx, question in enumerate(questions, 1):
                msg = _parse_question(question)
                if not msg:
                    continue

                structured_logger.log_turn(turn_idx, "start", msg)
                human_logger.log_turn_start(turn_idx, msg)
                await agent_app.send(msg)

                # Extract messages added in this turn for detailed logging
                messages = agent_app._agent(None).message_history
                new_messages = messages[prev_message_count:]
                prev_message_count = len(messages)

                # Log tool calls and results from this turn
                for msg_obj in new_messages:
                    # Log tool calls
                    if hasattr(msg_obj, "tool_calls") and msg_obj.tool_calls:
                        for tool_id, call in msg_obj.tool_calls.items():
                            total_tool_calls += 1
                            structured_logger.log_tool_call(turn_idx, call.params.name, call.params.arguments, tool_id)
                            human_logger.log_tool_call(turn_idx, call.params.name, call.params.arguments)

                    # Log tool results
                    if hasattr(msg_obj, "tool_results") and msg_obj.tool_results:
                        for tool_id, result in msg_obj.tool_results.items():
                            # Extract result content
                            result_content = []
                            if hasattr(result, "content"):
                                for item in result.content:
                                    if hasattr(item, "text"):
                                        result_content.append(item.text)

                            is_error = result.isError if hasattr(result, "isError") else False

                            # Find the corresponding tool call to get tool name
                            tool_name = "unknown"
                            for msg_check in new_messages:
                                if hasattr(msg_check, "tool_calls") and msg_check.tool_calls:
                                    if tool_id in msg_check.tool_calls:
                                        tool_name = msg_check.tool_calls[tool_id].params.name
                                        break

                            structured_logger.log_tool_result(
                                turn_idx, tool_id, result_content if result_content else str(result), is_error
                            )

                            human_logger.log_tool_result(
                                turn_idx, tool_name, result_content if result_content else str(result), is_error
                            )

                            # Track errors for summary
                            if is_error:
                                error_msg = str(result_content) if result_content else str(result)

                                errors.append(
                                    {
                                        "turn_id": turn_idx,
                                        "tool_id": tool_id,
                                        "tool_name": tool_name,
                                        "error_message": error_msg,
                                    }
                                )

                    # Log assistant text responses
                    if hasattr(msg_obj, "role") and msg_obj.role == "assistant":
                        if hasattr(msg_obj, "content"):
                            for content_item in msg_obj.content:
                                if hasattr(content_item, "text") and content_item.text:
                                    structured_logger.log_assistant_response(turn_idx, content_item.text)
                                    human_logger.log_assistant_response(turn_idx, content_item.text)

                structured_logger.log_turn(turn_idx, "end")
                human_logger.log_turn_end(turn_idx)
                await asyncio.sleep(0)

            # Get messages for output
            messages = agent_app._agent(None).message_history
            structured_logger.log_message_summary(messages)

            # Log error summary if any errors occurred
            if errors:
                structured_logger.log_error_summary(errors)
                human_logger.log_errors(errors)

            # Determine completion status
            final_assistant_msg = None
            for msg in reversed(messages):
                if hasattr(msg, "role") and msg.role == "assistant":
                    if hasattr(msg, "content"):
                        for content_item in msg.content:
                            if hasattr(content_item, "text") and content_item.text:
                                final_assistant_msg = content_item.text
                                break
                    if final_assistant_msg:
                        break

            # Check if agent hit max_iterations or completed normally
            status = "completed"
            reason = "Agent completed all requested tasks"

            # Look for max_iterations warning in logs (FastAgent behavior)
            if total_tool_calls >= 500:
                status = "max_iterations"
                reason = f"Agent reached maximum iteration limit ({total_tool_calls} tool calls)"
            elif errors and not final_assistant_msg:
                # Only mark as error if there were errors AND no final response
                # (agents can recover from errors - final completion message is what matters)
                status = "error"
                reason = f"Agent encountered {len(errors)} error(s) and did not complete"
            elif errors:
                # Had errors but completed - note this in reason but don't fail
                reason = f"Agent completed with {len(errors)} recoverable error(s) during execution"

            # Calculate error breakdown by classification
            infrastructure_errors = sum(1 for e in errors if e.get("classification") == "infrastructure")
            model_errors = sum(1 for e in errors if e.get("classification") == "model_failure")
            unknown_errors = sum(1 for e in errors if e.get("classification") == "unknown")

            structured_logger.log_completion_status(
                status=status,
                reason=reason,
                total_tool_calls=total_tool_calls,
                error_count=len(errors),
                final_message=final_assistant_msg,
            )

            # Log detailed error breakdown
            if errors:
                structured_logger.log_infrastructure_event(
                    "error_breakdown",
                    "test_framework",
                    "analyzed",
                    {
                        "total_errors": len(errors),
                        "infrastructure_errors": infrastructure_errors,
                        "model_errors": model_errors,
                        "unknown_errors": unknown_errors,
                    },
                )
                human_logger.log_infrastructure_event(
                    "error_breakdown",
                    "test_framework",
                    "analyzed",
                    f"Errors: {infrastructure_errors} infrastructure, {model_errors} model, {unknown_errors} unknown",
                )

            human_logger.log_execution_summary(
                status=status,
                reason=reason,
                total_tool_calls=total_tool_calls,
                error_count=len(errors),
                total_turns=len(questions),
            )

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

    # Save evaluation results to file
    eval_path = log_dir / f"{test_id}_evaluation.json"
    import json

    eval_path.write_text(json.dumps(evaluation, indent=2, default=str))

    # Log evaluation results to human-readable log
    human_log_path = log_dir / f"{test_id}_readable.log"
    if human_log_path.exists():
        human_logger = HumanReadableLogger.__new__(HumanReadableLogger)
        human_logger.log_path = human_log_path

        human_logger.log_evaluation_start()

        # Log each evaluation check
        failed_checks = 0
        for idx, result in enumerate(evaluation["evaluation_results"], 1):
            if not result["passed"]:
                failed_checks += 1

            # Try to extract expected value from evaluator data
            expected = None
            if (
                "value" in evaluation.get("task_data", {}).get("evaluators", [{}])[idx - 1]
                if idx - 1 < len(evaluation.get("task_data", {}).get("evaluators", []))
                else {}
            ):
                expected = evaluation["task_data"]["evaluators"][idx - 1].get("value")

            human_logger.log_evaluation_check(
                check_num=idx,
                operation=result["op"],
                passed=result["passed"],
                reason=result.get("reason", "") or result.get("error", ""),
                expected=expected,
                actual=None,  # We don't have actual values in evaluation results
            )

        human_logger.log_evaluation_summary(
            passed=evaluation["passed"], total_checks=len(evaluation["evaluation_results"]), failed_checks=failed_checks
        )

        verdict = (
            "TEST PASSED"
            if evaluation["passed"]
            else f"TEST FAILED ({failed_checks}/{len(evaluation['evaluation_results'])} checks failed)"
        )
        human_logger.log_final_verdict(verdict)

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
