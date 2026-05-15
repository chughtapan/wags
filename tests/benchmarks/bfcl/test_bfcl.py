"""BFCL evaluation tests using pytest."""

import asyncio
import json
import os
from pathlib import Path
import sys
from typing import Any, cast

import pytest
from mcp.types import CallToolResult, TextContent

from fast_agent.types import PromptMessageExtended

from tests.benchmarks.bfcl import evaluator, loader
from tests.benchmarks.bfcl.elicitation import create_elicitation_handler
from tests.conftest import instruction_file
from tests.utils.fastagent_helpers import MessageSerializer
from tests.utils.logger import StructuredEventLogger


def _repair_unanswered_tool_calls(
    agent_app: Any, user_text: str
) -> Any:
    """Return a message payload that repairs any unanswered tool_call_ids.

    If the previous turn left an assistant tool_call without a matching
    tool_result (e.g. fast-agent hit max_iterations or a tool-loop error break),
    the next OpenAI request will 400 with "tool_call_ids did not have response
    messages". We synthesize error tool_results for each dangling id and bundle
    them with the outgoing user text into a single PromptMessageExtended so the
    OpenAI converter emits tool messages before the user turn.
    """
    agent = agent_app._agent(None)
    history = agent.message_history

    responded: set[str] = set()
    called: list[str] = []
    for m in history:
        tcs = getattr(m, "tool_calls", None)
        if tcs:
            called.extend(tcs.keys())
        trs = getattr(m, "tool_results", None)
        if trs:
            responded.update(trs.keys())

    unanswered = [cid for cid in called if cid not in responded]
    if not unanswered:
        return user_text

    print(
        f"[REPAIR] Synthesizing tool_results for {len(unanswered)} unanswered "
        f"tool_call_id(s): {unanswered}",
        flush=True,
        file=sys.stderr,
    )

    synthetic_results = {
        cid: CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=(
                        "[WAGS] No result available: the tool call did not "
                        "complete in the previous turn."
                    ),
                )
            ],
            isError=True,
        )
        for cid in unanswered
    }

    return PromptMessageExtended(
        role="user",
        content=[TextContent(type="text", text=user_text)],
        tool_results=synthetic_results,
    )


def _parse_question(question: Any) -> str:
    """Parse question from various formats into a string."""
    if isinstance(question, list) and question:
        return question[0] if isinstance(question[0], str) else cast(str, question[0].get("content", ""))
    elif isinstance(question, str):
        return question
    elif isinstance(question, dict) and "content" in question:
        return cast(str, question["content"])
    return ""


def _validate_openai_api_key_env() -> None:
    """Fail fast for missing/placeholder OpenAI API key in BFCL runs."""
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key is None or not api_key.strip():
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Export a valid key before running BFCL tests."
        )

    candidate = api_key.strip()
    if candidate.startswith("${") and candidate.endswith("}"):
        raise RuntimeError(
            "OPENAI_API_KEY is set to a placeholder value. Export the real key instead."
        )


async def _run_bfcl_test(
    test_id: str,
    model: str,
    temperature: float,
    output_dir: Path,
    instruction_file: Path | None,
    external_feedback_enabled: bool,
) -> Path:
    """Run BFCL test and return path to complete.json."""
    from fast_agent import FastAgent

    _validate_openai_api_key_env()

    test_case = loader.load_test_entry(test_id)
    ground_truth = loader.load_ground_truth(test_id)

    default_instruction = Path(__file__).parent / "instruction.txt"
    instruction_path = instruction_file if instruction_file is not None else default_instruction
    print(f"Using INSTRUCTION file: {instruction_path}", flush=True, file=sys.stderr)
    if not instruction_path.exists():
        raise FileNotFoundError(f"Instruction file not found: {instruction_path}")
    
    structured_log_path = output_dir / "raw" / f"{test_id}_structured.jsonl"
    structured_log_path.parent.mkdir(parents=True, exist_ok=True)

    structured_logger = StructuredEventLogger(structured_log_path)
    elicitation_handler = create_elicitation_handler(ground_truth, structured_logger)

    test_data_path = output_dir / f"{test_id}_test.json"
    test_data_path.write_text(json.dumps(test_case))

    # Set environment variables BEFORE creating FastAgent.
    # Save and restore to avoid state leaking into subsequent test cases
    # when multiple tests run in the same pytest session.
    test_dir = Path(__file__).parent
    _BFCL_ENV_KEYS = (
        "DEFAULT_MODEL",
        "TEMPERATURE",
        "TEST_DATA_PATH",
        "TEST_ID",
        "SERVER_SCRIPT_PATH",
        "BFCL_EXTERNAL_FEEDBACK_LOG_FILE",
    )
    _saved_env = {k: os.environ.get(k) for k in _BFCL_ENV_KEYS}
    env_updates = {
        "DEFAULT_MODEL": model,
        "TEMPERATURE": str(temperature),
        "TEST_DATA_PATH": str(test_data_path.absolute()),
        "TEST_ID": test_id,
        "SERVER_SCRIPT_PATH": str(test_dir / "mcp_server.py"),
    }
    # Only set a default log path if run_experiment.py didn't already provide one.
    if not os.environ.get("BFCL_EXTERNAL_FEEDBACK_LOG_FILE"):
        env_updates["BFCL_EXTERNAL_FEEDBACK_LOG_FILE"] = str(
            output_dir / "raw" / "external_feedback.jsonl"
        )
    os.environ.update(env_updates)

    # Create FastAgent after environment variables are set
    config_path = test_dir / "fastagent.config.yaml"
    agent = FastAgent("BFCL Test", config_path=str(config_path), ignore_unknown_args=True)

    server_names = [cls.lower().replace("_", "") for cls in test_case.get("involved_classes", [])]

    @agent.agent(
        name="test_agent",
        model=model,
        servers=server_names,
        instruction=instruction_path,
        elicitation_handler=elicitation_handler,
    )
    async def run_test() -> Path:
        async with agent.run() as agent_app:
            questions = test_case.get("question", [])

            for turn_idx, question in enumerate(questions, 1):
                msg = _parse_question(question)
                if not msg:
                    continue

                structured_logger.log_turn(turn_idx, "start", msg)
                send_payload = _repair_unanswered_tool_calls(agent_app, msg)
                await agent_app.send(send_payload)
                
                # Check for feedback/errors in the latest turn
                current_messages = agent_app._agent(None).message_history
                for m in current_messages[-10:]:  # Check recent messages
                    if hasattr(m, "tool_results") and m.tool_results:
                        for tr in m.tool_results:
                            is_err = getattr(tr, "is_error", False)
                            if is_err:
                                content = getattr(tr, "content", str(tr))
                                print(f"\n[FEEDBACK] Tool Error detected: {str(content)[:200]}...", flush=True)

                structured_logger.log_turn(turn_idx, "end")
                await asyncio.sleep(0)

            messages = agent_app._agent(None).message_history
            structured_logger.log_message_summary(messages)

            complete_json = MessageSerializer.serialize_complete(messages)
            complete_path = output_dir / "raw" / f"{test_id}_complete.json"
            complete_path.write_text(complete_json)

            return complete_path

    try:
        return await run_test()
    finally:
        for k, v in _saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


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
            # Auto-detect log directory from output-dir
            output_dir = Path(metafunc.config.getoption("--output-dir"))
            log_dir = output_dir / "raw"

            if log_dir.exists():
                log_files = list(log_dir.glob("**/*_structured.jsonl"))
                test_ids = [f.stem.replace("_structured", "") for f in log_files]
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
    test_id: str,
    model: str,
    temperature: float,
    output_dir: Path,
    instruction_file: Path | None,
    request: pytest.FixtureRequest,
) -> None:
    """Run or validate a BFCL test based on mode."""
    if request.config.getoption("--validate-only"):
        log_dir = Path(request.config.getoption("--log-dir"))
    else:
        external_feedback_enabled = bool(request.config.getoption("--external-feedback"))
        await _run_bfcl_test(
            test_id,
            model,
            temperature,
            output_dir,
            instruction_file,
            external_feedback_enabled,
        )
        log_dir = output_dir / "raw"
    complete_path = log_dir / f"{test_id}_complete.json"
    evaluation = _validate_from_complete_json(test_id, complete_path)
    assert evaluation["validation"]["valid"], f"Validation failed for {test_id}"
    eval_path = log_dir / f"{test_id}_evaluation.json"
    eval_path.write_text(json.dumps(evaluation, indent=2, default=str))
