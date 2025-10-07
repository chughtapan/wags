"""Integration tests for middleware functionality and notification handling."""

import asyncio
from collections.abc import Callable
from typing import Any

import pytest
from fastmcp import FastMCP
from fastmcp.client import Client
from fastmcp.server.middleware.middleware import CallNext, Middleware, MiddlewareContext
from mcp.client.session import ClientSession
from mcp.shared.context import RequestContext
from mcp.types import CallToolRequestParams

from wags import create_proxy
from wags.middleware.base import WagsMiddlewareBase


class TestHandlers:
    """Test handlers for middleware integration tests."""

    async def simple_tool(self, name: str, value: int) -> dict[str, Any]:
        """Simple tool for testing basic functionality."""
        return {"name": name, "value": value * 2}


class LoggingMiddleware(Middleware):
    """Test middleware that logs all calls."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[dict[str, Any]] = []

    async def on_call_tool(
        self, context: MiddlewareContext[CallToolRequestParams], call_next: CallNext[CallToolRequestParams, Any]
    ) -> Any:
        """Log tool calls."""
        self.calls.append({"method": context.method, "tool": context.message.name, "args": context.message.arguments})
        return await call_next(context)


class NotificationTracker(Middleware):
    """Test middleware that records notification events."""

    def __init__(self) -> None:
        super().__init__()
        self.notifications: list[dict[str, str]] = []

    async def on_notification(self, context: MiddlewareContext[Any], call_next: CallNext[Any, Any]) -> Any:
        """Record notification method and source for verification."""
        self.notifications.append({"method": context.method or "unknown", "source": context.source or "unknown"})
        return await call_next(context)


class ModifyingMiddleware(WagsMiddlewareBase):
    """Test middleware that modifies arguments."""

    def __init__(self) -> None:
        super().__init__(handlers=TestHandlers())
        self.modified_tools: list[str] = []

    async def handle_on_tool_call(
        self, context: MiddlewareContext[CallToolRequestParams], handler: Callable[..., Any]
    ) -> MiddlewareContext[CallToolRequestParams]:
        """Modify tool arguments."""
        # Track what we modified
        self.modified_tools.append(context.message.name)

        # Add a suffix to any string 'name' argument
        if context.message.arguments and "name" in context.message.arguments:
            arguments = dict(context.message.arguments)
            arguments["name"] = f"{arguments['name']}_modified"
            updated_message = CallToolRequestParams(name=context.message.name, arguments=arguments)
            return context.copy(message=updated_message)

        return context


@pytest.mark.asyncio
class TestBasicMiddleware:
    """Integration tests for basic middleware functionality."""

    async def test_base_middleware_handler_routing(self) -> None:
        """Test that WagsMiddlewareBase correctly routes to handlers."""
        # Create server with middleware
        mcp = FastMCP("test-server")
        handlers = TestHandlers()

        middleware = WagsMiddlewareBase(handlers=handlers)
        mcp.add_middleware(middleware)

        # Register the actual tool
        @mcp.tool
        async def simple_tool(name: str, value: int) -> dict[str, Any]:
            return await handlers.simple_tool(name, value)

        # Test with client
        async with Client(mcp) as client:
            result = await client.call_tool("simple_tool", {"name": "test", "value": 5})
            assert result.data == {"name": "test", "value": 10}

    async def test_middleware_chain_ordering(self) -> None:
        """Test that multiple middleware execute in correct order."""
        mcp = FastMCP("test-server")

        # Add multiple middleware
        logging_mw = LoggingMiddleware()
        modifying_mw = ModifyingMiddleware()

        mcp.add_middleware(logging_mw)  # First - logs original
        mcp.add_middleware(modifying_mw)  # Second - modifies

        # Register tool
        @mcp.tool
        async def simple_tool(name: str, value: int) -> dict[str, Any]:
            return {"name": name, "value": value}

        async with Client(mcp) as client:
            result = await client.call_tool("simple_tool", {"name": "test", "value": 42})

            # Check that logging saw the original arguments
            assert len(logging_mw.calls) == 1
            assert logging_mw.calls[0]["args"]["name"] == "test"

            # Check that modification happened
            assert result.data["name"] == "test_modified"
            assert "simple_tool" in modifying_mw.modified_tools

    async def test_proxy_server_with_middleware(self) -> None:
        """Test creating a proxy server with middleware."""
        # Create a backend server first
        backend_server = FastMCP("backend-server")

        @backend_server.tool
        async def backend_tool(message: str) -> dict[str, str]:
            return {"response": f"Backend processed: {message}"}

        # Create proxy server that forwards to the backend
        # Note: as_proxy with in-memory backend server
        proxy_server = FastMCP.as_proxy(
            backend=backend_server,  # Use the FastMCP server directly as backend
            name="test-proxy",
        )

        # Add logging middleware to proxy
        logging_mw = LoggingMiddleware()
        proxy_server.add_middleware(logging_mw)

        # Test the proxy
        async with Client(proxy_server) as client:
            result = await client.call_tool("backend_tool", {"message": "Hello from test"})

            # Verify middleware intercepted the call
            assert len(logging_mw.calls) == 1
            assert logging_mw.calls[0]["tool"] == "backend_tool"
            assert logging_mw.calls[0]["args"]["message"] == "Hello from test"

            # Verify response came through
            assert "response" in result.data
            assert "Backend processed" in result.data["response"]

    async def test_middleware_context_preservation(self) -> None:
        """Test that context is properly preserved through middleware chain."""
        mcp = FastMCP("test-server")

        context_values: list[dict[str, Any]] = []

        class ContextCheckMiddleware(Middleware):
            def __init__(self, name: str):
                super().__init__()
                self.name = name

            async def on_call_tool(
                self, context: MiddlewareContext[CallToolRequestParams], call_next: CallNext[CallToolRequestParams, Any]
            ) -> Any:
                # Record context state
                context_values.append(
                    {
                        "middleware": self.name,
                        "method": context.method,
                        "tool": context.message.name,
                        "args": dict(context.message.arguments or {}),
                    }
                )

                # Modify context if this is middleware B
                if self.name == "B":
                    arguments = dict(context.message.arguments or {})
                    arguments["modified_by"] = "B"
                    updated_message = CallToolRequestParams(name=context.message.name, arguments=arguments)
                    context = context.copy(message=updated_message)

                return await call_next(context)

        # Add middleware in order
        mcp.add_middleware(ContextCheckMiddleware("A"))
        mcp.add_middleware(ContextCheckMiddleware("B"))
        mcp.add_middleware(ContextCheckMiddleware("C"))

        @mcp.tool
        async def test_tool(value: str, modified_by: str = "") -> dict[str, str]:
            return {"value": value, "modified_by": modified_by}

        async with Client(mcp) as client:
            result = await client.call_tool("test_tool", {"value": "test"})

            # Check that all middleware saw the call
            assert len(context_values) == 3

            # A sees original
            assert context_values[0]["middleware"] == "A"
            assert "modified_by" not in context_values[0]["args"]

            # B sees original and modifies
            assert context_values[1]["middleware"] == "B"
            assert "modified_by" not in context_values[1]["args"]

            # C sees modified version
            assert context_values[2]["middleware"] == "C"
            assert context_values[2]["args"].get("modified_by") == "B"

            # Final result has modification
            assert result.data["modified_by"] == "B"

    async def test_middleware_error_handling(self) -> None:
        """Test that middleware properly handles and propagates errors."""
        mcp = FastMCP("test-server")

        class ErrorMiddleware(Middleware):
            async def on_call_tool(
                self, context: MiddlewareContext[CallToolRequestParams], call_next: CallNext[CallToolRequestParams, Any]
            ) -> Any:
                if context.message.name == "error_tool":
                    raise ValueError("Middleware error")
                return await call_next(context)

        mcp.add_middleware(ErrorMiddleware())

        @mcp.tool
        async def error_tool() -> str:
            return "should not reach here"

        @mcp.tool
        async def normal_tool() -> str:
            return "success"

        async with Client(mcp) as client:
            # Error tool should raise the middleware error
            with pytest.raises(Exception) as exc_info:
                await client.call_tool("error_tool", {})
            assert "Middleware error" in str(exc_info.value)

            # Normal tool should work fine
            result = await client.call_tool("normal_tool", {})
            assert result.data == "success"


@pytest.mark.asyncio
class TestNotificationHandling:
    """Integration tests for notification handling through middleware."""

    async def test_notification_routing_through_proxy(self) -> None:
        """Test that notifications are properly routed through proxy middleware."""
        # Set up basic MCP server
        server = FastMCP("mcp-server")

        @server.tool
        async def test_tool() -> str:
            return "test"

        # Create proxy using overloaded create_proxy with FastMCP server
        proxy = create_proxy(server, server_name="test-proxy")
        tracker = NotificationTracker()
        proxy.add_middleware(tracker)

        current_roots = ["https://github.com/org1/"]

        async def dynamic_roots(context: RequestContext[ClientSession, Any]) -> list[str]:
            return current_roots

        async with Client(proxy, roots=dynamic_roots) as client:
            # Send notification from client
            await client.send_roots_list_changed()

            # Allow async notification processing
            await asyncio.sleep(0.1)

            # Verify middleware received the notification
            assert len(tracker.notifications) == 1
            assert tracker.notifications[0] == {"method": "notifications/roots/list_changed", "source": "client"}

    async def test_notification_middleware_chain(self) -> None:
        """Test that notifications flow through middleware chain correctly."""
        server = FastMCP("mcp-server")

        @server.tool
        async def dummy_tool() -> str:
            return "dummy"

        # Create proxy with notification support
        proxy = create_proxy(server, server_name="test-proxy")

        # Create multiple notification tracking middleware
        tracker1 = NotificationTracker()
        tracker2 = NotificationTracker()

        # Add middleware in order to proxy
        proxy.add_middleware(tracker1)
        proxy.add_middleware(tracker2)

        current_roots = ["https://example.com/"]

        async def dynamic_roots(context: RequestContext[ClientSession, Any]) -> list[str]:
            return current_roots

        async with Client(proxy, roots=dynamic_roots) as client:
            await client.send_roots_list_changed()

            # Allow processing time
            await asyncio.sleep(0.1)

            # Both middleware should have received the notification
            assert len(tracker1.notifications) == 1
            assert len(tracker2.notifications) == 1

            # Both should have same notification data
            expected = {"method": "notifications/roots/list_changed", "source": "client"}
            assert tracker1.notifications[0] == expected
            assert tracker2.notifications[0] == expected
