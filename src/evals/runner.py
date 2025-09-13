"""Generic test execution logic."""

import asyncio
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mcp_agent.core.fastagent import FastAgent
from mcp_agent.logging.logger import get_logger


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


async def run_test_async(config: TestConfig) -> dict[str, Any]:
    """Run test - single async function with configuration object."""
    from .logging import clear_log, save_conversation, save_test_data

    test_id = config.test_case["id"]
    log_file = config.output_dir / "raw" / f"{test_id}_fastagent.jsonl"

    # Prepare files
    clear_log(log_file)
    test_data_path = config.output_dir / f"{test_id}_test.json"
    save_test_data(test_data_path, config.test_case)

    # Environment setup
    os.environ.update(
        {
            "DEFAULT_MODEL": config.model,
            "TEMPERATURE": str(config.temperature),
            "TEST_DATA_PATH": str(test_data_path),
            "LOG_PATH": str(log_file),
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

    logger = get_logger(f"test.{test_id}")

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

            logger.info(f"TURN_START:{turn_idx}", turn_number=turn_idx)
            await agent_app.send(msg)
            logger.info(f"TURN_END:{turn_idx}", turn_number=turn_idx)

            # Small yield to let logger flush
            await asyncio.sleep(0)

        # Save results
        save_conversation(
            agent_app._agent(None).message_history,
            config.output_dir / "raw" / f"{test_id}_detailed.json",
        )

    return {"success": True, "test_id": test_id, "output_file": str(log_file)}


def run_test(config: TestConfig) -> dict[str, Any]:
    """Sync wrapper for async test execution."""
    try:
        return asyncio.run(run_test_async(config))
    except Exception as e:
        test_id = config.test_case.get("id", "unknown")
        return {"success": False, "error": str(e), "test_id": test_id}
