"""Tests for TodoServer."""

import pytest

from wags.middleware.todo import TodoItem, TodoServer


class TestTodoServer:
    """Test TodoServer initialization and configuration."""

    def test_server_creation(self):
        """Test that TodoServer can be created."""
        server = TodoServer()
        assert server.name == "todo-server"
        assert server.instructions is not None
        assert "TodoWrite" in server.instructions
        assert "Task Management" in server.instructions

    def test_server_has_instructions(self):
        """Test that instructions are set."""
        server = TodoServer()
        assert server.instructions
        assert len(server.instructions) > 100  # Should be substantial

    @pytest.mark.asyncio
    async def test_todo_write_basic(self):
        """Test basic TodoWrite functionality."""
        server = TodoServer()

        # Create initial todos
        todos = [
            TodoItem(
                content="First task",
                status="pending",
            ),
            TodoItem(
                content="Second task",
                status="pending",
            ),
        ]

        # Get the tool
        tools = await server._tool_manager.get_tools()
        todo_write = tools["TodoWrite"]

        # Call TodoWrite
        result = await todo_write.fn(todos=todos)

        assert result["success"] is True
        assert "2 todos" in result["message"]

    @pytest.mark.asyncio
    async def test_todo_read(self):
        """Test TodoRead functionality."""
        server = TodoServer()

        # Get tools
        tools = await server._tool_manager.get_tools()
        todo_write = tools["TodoWrite"]
        todo_read = tools["TodoRead"]

        # Write some todos
        todos = [
            TodoItem(
                content="Task 1", status="pending"
            ),
            TodoItem(
                content="Task 2",
                status="in_progress",
            ),
        ]
        await todo_write.fn(todos=todos)

        # Read them back
        result = await todo_read.fn()

        assert "todos" in result
        assert len(result["todos"]) == 2
        assert result["todos"][0]["content"] == "Task 1"
        assert result["todos"][1]["status"] == "in_progress"

    @pytest.mark.asyncio
    async def test_todo_state_updates(self):
        """Test that todo state updates correctly."""
        server = TodoServer()

        tools = await server._tool_manager.get_tools()
        todo_write = tools["TodoWrite"]
        todo_read = tools["TodoRead"]

        # Initial state
        todos_v1 = [
            TodoItem(
                content="Task", status="pending"
            )
        ]
        await todo_write.fn(todos=todos_v1)

        # Update to in_progress
        todos_v2 = [
            TodoItem(
                content="Task", status="in_progress"
            )
        ]
        await todo_write.fn(todos=todos_v2)

        result = await todo_read.fn()
        assert result["todos"][0]["status"] == "in_progress"

        # Update to completed
        todos_v3 = [
            TodoItem(
                content="Task", status="completed"
            )
        ]
        await todo_write.fn(todos=todos_v3)

        result = await todo_read.fn()
        assert result["todos"][0]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_multiple_instances_isolated(self):
        """Test that multiple server instances have isolated state."""
        server1 = TodoServer()
        server2 = TodoServer()

        tools1 = await server1._tool_manager.get_tools()
        tools2 = await server2._tool_manager.get_tools()

        # Write to server1
        todos1 = [
            TodoItem(
                content="Server 1 task",
                status="pending",
            )
        ]
        await tools1["TodoWrite"].fn(todos=todos1)

        # Write to server2
        todos2 = [
            TodoItem(
                content="Server 2 task",
                status="pending",
            )
        ]
        await tools2["TodoWrite"].fn(todos=todos2)

        # Verify isolation
        result1 = await tools1["TodoRead"].fn()
        result2 = await tools2["TodoRead"].fn()

        assert result1["todos"][0]["content"] == "Server 1 task"
        assert result2["todos"][0]["content"] == "Server 2 task"

    @pytest.mark.asyncio
    async def test_in_progress_message(self):
        """Test that message includes in_progress task."""
        server = TodoServer()

        tools = await server._tool_manager.get_tools()
        todo_write = tools["TodoWrite"]

        todos = [
            TodoItem(
                content="First", status="completed"
            ),
            TodoItem(
                content="Second", status="in_progress"
            ),
            TodoItem(
                content="Third", status="pending"
            ),
        ]

        result = await todo_write.fn(todos=todos)

        assert "In progress: Second" in result["message"]

    @pytest.mark.asyncio
    async def test_no_in_progress_message(self):
        """Test message when no task is in_progress."""
        server = TodoServer()

        tools = await server._tool_manager.get_tools()
        todo_write = tools["TodoWrite"]

        todos = [
            TodoItem(
                content="First", status="pending"
            ),
            TodoItem(
                content="Second", status="pending"
            ),
        ]

        result = await todo_write.fn(todos=todos)

        assert "Updated 2 todos" in result["message"]
        assert "In progress" not in result["message"]
