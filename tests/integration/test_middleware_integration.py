"""Integration tests for middleware functionality with FastMCP."""

from enum import Enum
from typing import Annotated, Any

import pytest
from fastmcp import FastMCP
from fastmcp.client import Client
from fastmcp.client.elicitation import ElicitResult
from fastmcp.server.middleware.middleware import CallNext, Middleware, MiddlewareContext
from mcp.types import CallToolRequestParams

from wags.middleware.base import BaseMiddleware
from wags.middleware.elicitation import ElicitationMiddleware, RequiresElicitation


class Priority(Enum):
    """Test enum for priority levels."""
    LOW = 1
    MEDIUM = 2
    HIGH = 3


class TestHandlers:
    """Test handlers for middleware integration tests."""

    async def simple_tool(self, name: str, value: int) -> dict:
        """Simple tool without elicitation."""
        return {"name": name, "value": value * 2}

    async def elicitation_tool(
        self,
        name: str,
        description: Annotated[str, RequiresElicitation("Enter a description")],
        priority: Annotated[Priority, RequiresElicitation("Select priority level")]
    ) -> dict:
        """Tool with elicitation parameters."""
        return {
            "name": name,
            "description": description,
            "priority": priority.value if isinstance(priority, Priority) else priority
        }

    async def multi_elicitation_tool(
        self,
        base_value: int,
        multiplier: Annotated[int, RequiresElicitation("Enter multiplier (1-10)")],
        notes: Annotated[str, RequiresElicitation("Add any notes")]
    ) -> dict:
        """Tool with multiple elicitation fields."""
        return {
            "result": base_value * multiplier,
            "notes": notes
        }


class LoggingMiddleware(Middleware):
    """Test middleware that logs all calls."""

    def __init__(self):
        super().__init__()
        self.calls = []

    async def on_call_tool(
        self,
        context: MiddlewareContext[CallToolRequestParams],
        call_next: CallNext[CallToolRequestParams, Any]
    ) -> Any:
        """Log tool calls."""
        self.calls.append({
            "method": context.method,
            "tool": context.message.name,
            "args": context.message.arguments
        })
        return await call_next(context)


class ModifyingMiddleware(BaseMiddleware):
    """Test middleware that modifies arguments."""

    def __init__(self):
        super().__init__(handlers=TestHandlers())
        self.modified_tools = []

    async def handle_on_tool_call(
        self,
        context: MiddlewareContext[CallToolRequestParams],
        handler
    ) -> MiddlewareContext[CallToolRequestParams]:
        """Modify tool arguments."""
        # Track what we modified
        self.modified_tools.append(context.message.name)

        # Add a suffix to any string 'name' argument
        if context.message.arguments and "name" in context.message.arguments:
            arguments = dict(context.message.arguments)
            arguments["name"] = f"{arguments['name']}_modified"
            updated_message = CallToolRequestParams(
                name=context.message.name,
                arguments=arguments
            )
            return context.copy(message=updated_message)

        return context


@pytest.mark.asyncio
class TestMiddlewareIntegration:
    """Integration tests for middleware with FastMCP."""

    async def test_base_middleware_handler_routing(self):
        """Test that BaseMiddleware correctly routes to handlers."""
        # Create server with middleware
        mcp = FastMCP("test-server")
        handlers = TestHandlers()
        middleware = BaseMiddleware(handlers=handlers)
        mcp.add_middleware(middleware)

        # Register the actual tool
        @mcp.tool
        async def simple_tool(name: str, value: int) -> dict:
            return await handlers.simple_tool(name, value)

        # Test with client
        async with Client(mcp) as client:
            result = await client.call_tool(
                "simple_tool",
                {"name": "test", "value": 5}
            )
            assert result.data == {"name": "test", "value": 10}

    async def test_middleware_chain_ordering(self):
        """Test that multiple middleware execute in correct order."""
        mcp = FastMCP("test-server")

        # Add multiple middleware
        logging_mw = LoggingMiddleware()
        modifying_mw = ModifyingMiddleware()

        mcp.add_middleware(logging_mw)  # First - logs original
        mcp.add_middleware(modifying_mw)  # Second - modifies

        # Register tool
        @mcp.tool
        async def simple_tool(name: str, value: int) -> dict:
            return {"name": name, "value": value}

        async with Client(mcp) as client:
            result = await client.call_tool(
                "simple_tool",
                {"name": "test", "value": 42}
            )

            # Check that logging saw the original arguments
            assert len(logging_mw.calls) == 1
            assert logging_mw.calls[0]["args"]["name"] == "test"

            # Check that modification happened
            assert result.data["name"] == "test_modified"
            assert "simple_tool" in modifying_mw.modified_tools

    async def test_elicitation_middleware_with_accepted_response(self):
        """Test ElicitationMiddleware with accepted elicitation using real client flow."""
        mcp = FastMCP("test-server")
        handlers = TestHandlers()

        # Add elicitation middleware
        elicitation_mw = ElicitationMiddleware(handlers=handlers)
        mcp.add_middleware(elicitation_mw)

        # Track elicitation requests
        elicitation_requests = []

        # Create elicitation handler that accepts and provides values
        async def test_elicitation_handler(message, response_type, params, context):
            """Auto-accept elicitation with test values."""
            elicitation_requests.append({
                "message": message,
                "response_type": response_type.__name__ if response_type else None
            })

            # Return accepted values based on the response type
            if response_type:
                # The response_type will have fields like description and priority
                return {
                    "description": "Test description",
                    "priority": Priority.HIGH
                }
            return {}

        # Register tool with all required parameters
        @mcp.tool
        async def elicitation_tool(name: str, description: str, priority: Priority) -> dict:
            return await handlers.elicitation_tool(name, description, priority)

        # Test with client using elicitation handler
        async with Client(mcp, elicitation_handler=test_elicitation_handler) as client:
            result = await client.call_tool(
                "elicitation_tool",
                {
                    "name": "test",
                    "description": "original description",  # Provided but will be edited
                    "priority": Priority.LOW  # Provided but will be edited
                }
            )

            # Verify elicitation happened and values were EDITED
            assert len(elicitation_requests) > 0
            assert result.data["name"] == "test"  # Not elicited, stays same
            assert result.data["description"] == "Test description"  # EDITED via elicitation
            assert result.data["priority"] == Priority.HIGH.value  # EDITED via elicitation

    async def test_elicitation_middleware_with_declined_response(self):
        """Test ElicitationMiddleware with declined elicitation using real client flow."""
        mcp = FastMCP("test-server")
        handlers = TestHandlers()

        # Add elicitation middleware
        elicitation_mw = ElicitationMiddleware(handlers=handlers)
        mcp.add_middleware(elicitation_mw)

        # Create elicitation handler that declines
        async def declining_elicitation_handler(message, response_type, params, context):
            """Decline all elicitation requests."""
            # Return ElicitResult with action="decline"
            return ElicitResult(action="decline")

        # Register tool with all required parameters
        @mcp.tool
        async def elicitation_tool(name: str, description: str, priority: Priority) -> dict:
            return await handlers.elicitation_tool(name, description, priority)

        # Test with client using declining handler
        async with Client(mcp, elicitation_handler=declining_elicitation_handler) as client:
            # Should get an error when elicitation is declined
            with pytest.raises(Exception) as exc_info:
                await client.call_tool(
                    "elicitation_tool",
                    {
                        "name": "test",
                        "description": "original",  # All parameters provided
                        "priority": Priority.LOW  # But user declines to edit
                    }
                )

            # Verify the error is about declined elicitation
            assert "declined" in str(exc_info.value).lower() or "elicitation" in str(exc_info.value).lower()

    async def test_elicitation_middleware_multiple_fields(self):
        """Test ElicitationMiddleware collecting multiple fields in one elicitation."""
        mcp = FastMCP("test-server")
        handlers = TestHandlers()

        # Add elicitation middleware
        elicitation_mw = ElicitationMiddleware(handlers=handlers)
        mcp.add_middleware(elicitation_mw)

        # Track elicitation details
        elicitation_count = []

        # Create elicitation handler
        async def multi_field_handler(message, response_type, params, context):
            """Provide multiple field values."""
            elicitation_count.append(1)

            # Return all required fields at once
            return {
                "multiplier": 5,
                "notes": "Test notes from elicitation"
            }

        # Register tool with all required parameters
        @mcp.tool
        async def multi_elicitation_tool(base_value: int, multiplier: int, notes: str) -> dict:
            return await handlers.multi_elicitation_tool(base_value, multiplier, notes)

        # Test with client
        async with Client(mcp, elicitation_handler=multi_field_handler) as client:
            result = await client.call_tool(
                "multi_elicitation_tool",
                {
                    "base_value": 10,
                    "multiplier": 2,  # Provided but will be edited to 5
                    "notes": "original notes"  # Provided but will be edited
                }
            )

            # Should have elicited both fields in ONE call
            assert len(elicitation_count) == 1
            assert result.data["result"] == 50  # 10 * 5 (edited multiplier)
            assert result.data["notes"] == "Test notes from elicitation"  # Edited notes

    async def test_proxy_server_with_middleware(self):
        """Test creating a proxy server with middleware."""
        # Create a backend server first
        backend_server = FastMCP("backend-server")

        @backend_server.tool
        async def backend_tool(message: str) -> dict:
            return {"response": f"Backend processed: {message}"}

        # Create proxy server that forwards to the backend
        # Note: as_proxy with in-memory backend server
        proxy_server = FastMCP.as_proxy(
            backend=backend_server,  # Use the FastMCP server directly as backend
            name="test-proxy"
        )

        # Add logging middleware to proxy
        logging_mw = LoggingMiddleware()
        proxy_server.add_middleware(logging_mw)

        # Test the proxy
        async with Client(proxy_server) as client:
            result = await client.call_tool(
                "backend_tool",
                {"message": "Hello from test"}
            )

            # Verify middleware intercepted the call
            assert len(logging_mw.calls) == 1
            assert logging_mw.calls[0]["tool"] == "backend_tool"
            assert logging_mw.calls[0]["args"]["message"] == "Hello from test"

            # Verify response came through
            assert "response" in result.data
            assert "Backend processed" in result.data["response"]

    async def test_middleware_context_preservation(self):
        """Test that context is properly preserved through middleware chain."""
        mcp = FastMCP("test-server")

        context_values = []

        class ContextCheckMiddleware(Middleware):
            def __init__(self, name: str):
                super().__init__()
                self.name = name

            async def on_call_tool(
                self,
                context: MiddlewareContext[CallToolRequestParams],
                call_next: CallNext[CallToolRequestParams, Any]
            ) -> Any:
                # Record context state
                context_values.append({
                    "middleware": self.name,
                    "method": context.method,
                    "tool": context.message.name,
                    "args": dict(context.message.arguments or {})
                })

                # Modify context if this is middleware B
                if self.name == "B":
                    arguments = dict(context.message.arguments or {})
                    arguments["modified_by"] = "B"
                    updated_message = CallToolRequestParams(
                        name=context.message.name,
                        arguments=arguments
                    )
                    context = context.copy(message=updated_message)

                return await call_next(context)

        # Add middleware in order
        mcp.add_middleware(ContextCheckMiddleware("A"))
        mcp.add_middleware(ContextCheckMiddleware("B"))
        mcp.add_middleware(ContextCheckMiddleware("C"))

        @mcp.tool
        async def test_tool(value: str, modified_by: str | None = None) -> dict:
            return {"value": value, "modified_by": modified_by}

        async with Client(mcp) as client:
            result = await client.call_tool(
                "test_tool",
                {"value": "test"}
            )

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

    async def test_middleware_without_elicitation_passthrough(self):
        """Test that tools without elicitation annotations work normally."""
        mcp = FastMCP("test-server")
        handlers = TestHandlers()

        # Add elicitation middleware
        elicitation_mw = ElicitationMiddleware(handlers=handlers)
        mcp.add_middleware(elicitation_mw)

        # Track if elicitation was called
        elicitation_called = []

        async def tracking_handler(message, response_type, params, context):
            elicitation_called.append(1)
            return {}

        # Register simple tool (no elicitation annotations)
        @mcp.tool
        async def simple_tool(name: str, value: int) -> dict:
            return await handlers.simple_tool(name, value)

        # Test with client
        async with Client(mcp, elicitation_handler=tracking_handler) as client:
            result = await client.call_tool(
                "simple_tool",
                {"name": "test", "value": 10}
            )

            # No elicitation should have been triggered
            assert len(elicitation_called) == 0
            assert result.data == {"name": "test", "value": 20}