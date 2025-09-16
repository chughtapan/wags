"""Generic test execution logic."""

import asyncio
import json
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fast_agent import FastAgent


@dataclass
class TestConfig:
    """Configuration for test execution."""

    test_case: dict[str, Any]
    config_path: Path
    instruction_path: Path
    model: str = "gpt-4o"
    temperature: float = 0.001
    output_dir: Path = field(default_factory=lambda: Path("outputs"))
    elicitation_handler: Callable | None = None
    server_names: list[str] | None = None
    structured_logger: Any = None  # Optional StructuredEventLogger instance


async def run_test_async(config: TestConfig) -> dict[str, Any]:
    """Run test - single async function with configuration object."""
    from .serializer import MessageSerializer
    from .logger import StructuredEventLogger

    test_id = config.test_case["id"]

    # Setup structured logger (use provided or create new)
    if config.structured_logger:
        structured_logger = config.structured_logger
        structured_log_path = structured_logger.log_path
    else:
        structured_log_path = config.output_dir / "raw" / f"{test_id}_structured.jsonl"
        structured_logger = StructuredEventLogger(structured_log_path)

    test_data_path = config.output_dir / f"{test_id}_test.json"
    test_data_path.parent.mkdir(parents=True, exist_ok=True)
    test_data_path.write_text(json.dumps(config.test_case))

    # Environment setup
    os.environ.update(
        {
            "DEFAULT_MODEL": config.model,
            "TEMPERATURE": str(config.temperature),
            "TEST_DATA_PATH": str(test_data_path),
            "TEST_ID": test_id,
            "SERVER_SCRIPT_PATH": str(Path(__file__).parent / "bfcl" / "mcp_server.py"),
        }
    )

    # Create FastAgent and define agent inline
    fast = FastAgent("Test", config_path=str(config.config_path))

    @fast.agent(
        name="test_agent",
        model=config.model,
        servers=config.server_names or [],
        instruction=config.instruction_path,
        elicitation_handler=config.elicitation_handler,
    )
    async def test_agent():
        pass  # No implementation needed

    # Run conversation
    async with fast.run() as agent_app:
        questions = config.test_case.get("question", [])

        for turn_idx, question in enumerate(questions, 1):
            # Handle different question formats
            if isinstance(question, list) and question:
                msg = (
                    question[0] if isinstance(question[0], str) else question[0].get("content", "")
                )
            elif isinstance(question, str):
                msg = question
            elif isinstance(question, dict) and "content" in question:
                msg = question["content"]
            else:
                continue

            structured_logger.log_turn(turn_idx, "start", msg)
            await agent_app.send(msg)
            structured_logger.log_turn(turn_idx, "end")

            # Small yield to let logger flush
            await asyncio.sleep(0)

        messages = agent_app._agent(None).message_history
        structured_logger.log_message_summary(messages)

        # Save complete serialization
        complete_json = MessageSerializer.serialize_complete(messages)
        complete_path = config.output_dir / "raw" / f"{test_id}_complete.json"
        complete_path.write_text(complete_json)

    return {
        "success": True,
        "test_id": test_id,
        "structured_log": str(structured_log_path),
        "complete_messages": str(complete_path)
    }


def run_test(config: TestConfig) -> dict[str, Any]:
    """Sync wrapper for async test execution."""
    try:
        return asyncio.run(run_test_async(config))
    except Exception as e:
        test_id = config.test_case.get("id", "unknown")
        return {"success": False, "error": str(e), "test_id": test_id}
