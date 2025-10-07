"""Tests for TodoServer."""

import pytest
from fastmcp.client import Client

from wags.middleware.todo import TodoServer


class TestTodoServer:
    """Test TodoServer initialization and configuration."""

    def test_server_creation(self) -> None:
        """Test that TodoServer can be created."""
        server = TodoServer()
        assert server.name == "todo-server"
        assert server.instructions is not None
        assert "TodoWrite" in server.instructions
        assert "Task Management" in server.instructions

    def test_server_has_instructions(self) -> None:
        """Test that instructions are set."""
        server = TodoServer()
        assert server.instructions
        assert len(server.instructions) > 100  # Should be substantial

    @pytest.mark.asyncio
    async def test_todo_write_basic(self) -> None:
        """Test basic TodoWrite functionality."""
        server = TodoServer()

        # Create initial todos
        todos = [
            {"content": "First task", "status": "pending", "activeForm": "First task"},
            {"content": "Second task", "status": "pending", "activeForm": "Second task"},
        ]

        # Use MCP client to properly interact with server
        async with Client(server) as client:
            result = await client.call_tool("TodoWrite", {"todos": todos})
            assert result.is_error is False
            assert "2 todos" in str(result.content)


    @pytest.mark.asyncio
    async def test_in_progress_message(self) -> None:
        """Test that message includes in_progress task."""
        server = TodoServer()

        todos = [
            {"content": "First", "status": "completed", "activeForm": "First"},
            {"content": "Second", "status": "in_progress", "activeForm": "Second"},
            {"content": "Third", "status": "pending", "activeForm": "Third"},
        ]

        async with Client(server) as client:
            result = await client.call_tool("TodoWrite", {"todos": todos})
            assert "In progress: Second" in str(result.content)

    @pytest.mark.asyncio
    async def test_no_in_progress_message(self) -> None:
        """Test message when no task is in_progress."""
        server = TodoServer()

        todos = [
            {"content": "First", "status": "pending", "activeForm": "First"},
            {"content": "Second", "status": "pending", "activeForm": "Second"},
        ]

        async with Client(server) as client:
            result = await client.call_tool("TodoWrite", {"todos": todos})
            content_text = str(result.content)
            assert "Updated 2 todos" in content_text
            assert "In progress" not in content_text
