"""Tests for proxy server with todo support."""

import pytest
from fastmcp import FastMCP

from wags.proxy import create_proxy


class TestProxyTodoIntegration:
    """Test todo integration with proxy server."""

    def test_create_proxy_without_todos_no_instructions(self) -> None:
        """Test creating proxy without todo support or target instructions."""
        server = FastMCP("test-server")

        @server.tool()
        def test_tool() -> str:
            """A test tool."""
            return "success"

        proxy = create_proxy(server, enable_todos=False)

        assert proxy.name == "wags-proxy"
        assert proxy.instructions is None

    def test_create_proxy_inherits_target_instructions(self) -> None:
        """Test that proxy inherits instructions from target server."""
        server = FastMCP("test-server", instructions="Target instructions")

        proxy = create_proxy(server, enable_todos=False)

        assert proxy.instructions == "Target instructions"

    @pytest.mark.asyncio
    async def test_create_proxy_with_todos(self) -> None:
        """Test creating proxy with todo support."""
        # Create a simple server without instructions
        server = FastMCP("test-server")

        @server.tool()
        def test_tool() -> str:
            """A test tool."""
            return "success"

        # Create proxy with todos
        proxy = create_proxy(server, enable_todos=True)

        assert proxy.name == "wags-proxy"
        # Should have todo instructions
        assert proxy.instructions is not None
        assert "TodoWrite" in proxy.instructions
        assert "Task Management" in proxy.instructions

        # Should have todo tools available
        tools = await proxy._tool_manager.get_tools()
        assert "TodoWrite" in tools
        # Should also have original tool
        assert "test_tool" in tools

    def test_create_proxy_with_todos_rejects_instructions(self) -> None:
        """Test that enable_todos=True raises error if server has instructions."""
        # Create a server WITH instructions
        server = FastMCP("test-server", instructions="Some instructions")

        # Should raise NotImplementedError
        with pytest.raises(NotImplementedError) as exc_info:
            create_proxy(server, enable_todos=True)

        assert "Instruction merging not yet supported" in str(exc_info.value)
        assert "Target server must not have instructions" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_todo_tools_no_prefix(self) -> None:
        """Test that todo tools are mounted without prefix."""
        server = FastMCP("test-server")
        proxy = create_proxy(server, enable_todos=True)

        tools = await proxy._tool_manager.get_tools()

        # Tools should be TodoWrite, not todo_TodoWrite
        assert "TodoWrite" in tools
        assert "todo_TodoWrite" not in tools

    def test_custom_server_name(self) -> None:
        """Test creating proxy with custom name."""
        server = FastMCP("test-server")
        proxy = create_proxy(server, server_name="custom-proxy", enable_todos=True)

        assert proxy.name == "custom-proxy"
        assert proxy.instructions is not None
