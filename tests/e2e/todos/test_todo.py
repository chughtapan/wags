"""E2E tests for TodoServer integration."""

import json

import pytest
from fast_agent import FastAgent

from tests.utils.fastagent_helpers import MessageSerializer


class TestTodoServer:
    """Test TodoServer workflow with file operations.

    Tests are verified to work with gpt-4o and gpt-4.1. Other models may fail
    (e.g., gpt-4o-mini mimics instruction examples instead of calling tools).
    """

    @pytest.mark.asyncio
    @pytest.mark.verified_models(["gpt-4o", "gpt-4.1"])
    async def test_todo_workflow_with_file_operations(self, fast_agent: FastAgent, model: str) -> None:
        """Verify TodoServer tracks tasks during file operations.

        Verified models: gpt-4o, gpt-4.1
        Other models will run but failures are expected (xfail).
        """

        fast = fast_agent

        @fast.agent(
            name="todo_test",
            model=model,
            servers=["mock-files-todo"],
            instruction="You are a helpful agent.\n\n{{serverInstructions}}",
        )
        async def test_function() -> None:
            async with fast.run() as agent:
                await agent.send(
                    "Move 'final_report.pdf' to 'temp' directory. "
                    "Create directory first. Grep for 'budget'. "
                    "Sort file. Move 'previous_report.pdf' to temp. "
                    "Compare both files."
                )

                # Extract tool calls
                messages = agent._agent(None).message_history
                complete_json = MessageSerializer.serialize_complete(messages)
                complete_data = json.loads(complete_json)
                tool_calls = MessageSerializer.extract_tool_calls_by_turn(complete_data)
                all_calls = [c for turn in tool_calls for c in turn]

                # Find TodoWrite calls (with server prefix)
                todo_writes = [c for c in all_calls if c["function"].endswith("TodoWrite")]

                # Validate TodoWrite was called with reasonable todos
                assert len(todo_writes) > 0, "TodoWrite was never called"
                initial_todos = todo_writes[0]["arguments"]["todos"]
                assert len(initial_todos) >= 3, f"Expected at least 3 todos, got {len(initial_todos)}"

                # Validate todos progress from pending to completed
                if len(todo_writes) > 1:
                    final_todos = todo_writes[-1]["arguments"]["todos"]
                    completed = sum(1 for t in final_todos if t["status"] == "completed")
                    assert completed > 0, "No todos were marked as completed"

        await test_function()
