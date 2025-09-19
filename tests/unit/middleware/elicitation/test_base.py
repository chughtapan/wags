"""Tests for elicitation middleware."""
from enum import Enum
from typing import Annotated, Literal
from unittest.mock import AsyncMock, Mock

import pytest
from fastmcp.server.context import Context
from fastmcp.server.elicitation import AcceptedElicitation
from fastmcp.server.middleware.middleware import MiddlewareContext
from mcp.types import CallToolRequestParams
from pydantic import BaseModel

from src.wags.middleware.base import tool_handler
from src.wags.middleware.elicitation import ElicitationMiddleware, RequiresElicitation


class Priority(Enum):
    """Test enum for priority levels."""
    LOW = 1
    MEDIUM = 2
    HIGH = 3


class TestElicitationMiddleware(ElicitationMiddleware):
    """Test middleware with tool handlers."""

    @tool_handler
    async def simple_tool(
        self,
        name: str,
        description: Annotated[
            Literal["short", "detailed"],
            RequiresElicitation("Choose description format")
        ],
        priority: Annotated[
            Priority,
            RequiresElicitation("Select priority level")
        ],
        ctx: Context | None = None,
    ):
        """Simple tool for testing with multiple elicitation fields."""
        return {
            "name": name,
            "description": description,
            "priority": priority.value if isinstance(priority, Priority) else priority,
            "has_context": ctx is not None,
        }

    @tool_handler
    async def string_elicitation_tool(
        self,
        value: str,
        notes: Annotated[str, RequiresElicitation("Add notes")],
        ctx: Context | None = None,
    ):
        """Tool with open-ended string elicitation."""
        return {"value": value, "notes": notes, "has_context": ctx is not None}

    @tool_handler
    async def no_elicitation_tool(self, value: str, ctx: Context | None = None):
        """Tool without elicitation annotations."""
        return {"value": value, "has_context": ctx is not None}


@pytest.mark.asyncio
async def test_middleware_registration():
    """Test that tool handlers are auto-registered."""
    middleware = TestElicitationMiddleware()

    # Should have all @tool_handler decorated methods registered
    assert "simple_tool" in middleware.tool_handlers
    assert "string_elicitation_tool" in middleware.tool_handlers
    assert "no_elicitation_tool" in middleware.tool_handlers


@pytest.mark.asyncio
async def test_get_tool_handler():
    """Test getting tool handler from request."""
    middleware = TestElicitationMiddleware()

    request = CallToolRequestParams(
        name="simple_tool",
        arguments={"name": "test"}
    )

    handler = middleware.get_tool_handler(request)
    assert handler is not None
    assert handler.__name__ == "simple_tool"

    # Test non-existent handler
    request = CallToolRequestParams(name="unknown_tool", arguments={})
    handler = middleware.get_tool_handler(request)
    assert handler is None


@pytest.mark.asyncio
async def test_single_elicitation_with_mock_context():
    """Test that multiple fields are elicited in a single call."""
    middleware = TestElicitationMiddleware()

    # Create mock FastMCP context
    mock_fastmcp_context = Mock(spec=Context)

    # Create a mock response that simulates the Pydantic model
    class MockElicitResponse:
        description = "short"
        priority = Priority.HIGH

    mock_fastmcp_context.elicit = AsyncMock(
        return_value=AcceptedElicitation(data=MockElicitResponse())
    )

    # Create middleware context
    message = CallToolRequestParams(
        name="simple_tool",
        arguments={"name": "test"}  # description and priority not provided
    )
    context = MiddlewareContext(
        message=message, fastmcp_context=mock_fastmcp_context, method="tools/call"
    )

    # Create mock call_next that returns the arguments
    async def call_next(ctx):
        return ctx.message.arguments

    result = await middleware.on_call_tool(context, call_next)

    # Should have elicited both description and priority in ONE call
    assert result["description"] == "short"
    assert result["priority"] == Priority.HIGH
    assert result["name"] == "test"

    # Verify only ONE elicit call was made (not multiple)
    mock_fastmcp_context.elicit.assert_called_once()


@pytest.mark.asyncio
async def test_passthrough_unregistered():
    """Test that unregistered tools pass through."""
    middleware = TestElicitationMiddleware()

    # Create middleware context for unknown tool
    message = CallToolRequestParams(
        name="unknown_tool", arguments={"arg1": "value1", "arg2": "value2"}
    )
    context = MiddlewareContext(message=message, method="tools/call")

    # Mock call_next to return the arguments
    async def call_next(ctx):
        return ctx.message.arguments

    result = await middleware.on_call_tool(context, call_next)

    assert result == message.arguments  # Should pass through unchanged


@pytest.mark.asyncio
async def test_metadata_extraction():
    """Test extraction of elicitation metadata."""
    middleware = TestElicitationMiddleware()
    handler = middleware.tool_handlers["simple_tool"]

    import inspect

    sig = inspect.signature(handler)
    param = sig.parameters["description"]

    metadata = middleware._get_annotation_metadata(param, RequiresElicitation)

    assert metadata is not None
    assert metadata.prompt == "Choose description format"


@pytest.mark.asyncio
async def test_type_extraction():
    """Test extraction of base type from Annotated."""
    middleware = TestElicitationMiddleware()
    handler = middleware.tool_handlers["simple_tool"]

    import inspect

    sig = inspect.signature(handler)

    # Test Literal type extraction
    desc_param = sig.parameters["description"]
    desc_type = middleware._extract_base_type(desc_param.annotation)
    assert desc_type == Literal["short", "detailed"]

    # Test Enum type extraction
    priority_param = sig.parameters["priority"]
    priority_type = middleware._extract_base_type(priority_param.annotation)
    assert priority_type == Priority


@pytest.mark.asyncio
async def test_no_elicitation_metadata():
    """Test parameter without elicitation metadata."""
    middleware = TestElicitationMiddleware()
    handler = middleware.tool_handlers["simple_tool"]

    import inspect

    sig = inspect.signature(handler)
    param = sig.parameters["name"]  # This parameter has no annotation

    metadata = middleware._get_annotation_metadata(param, RequiresElicitation)
    assert metadata is None


@pytest.mark.asyncio
async def test_handler_without_elicitation():
    """Test handler without any elicitation annotations."""
    middleware = TestElicitationMiddleware()

    # Create middleware context
    message = CallToolRequestParams(
        name="no_elicitation_tool", arguments={"value": "test_value"}
    )
    context = MiddlewareContext(message=message, method="tools/call")

    # Mock call_next
    async def call_next(ctx):
        return ctx.message.arguments

    result = await middleware.on_call_tool(context, call_next)

    assert result["value"] == "test_value"


@pytest.mark.asyncio
async def test_passthrough_without_context():
    """Test that middleware passes through when no FastMCP context."""
    middleware = TestElicitationMiddleware()

    # Create middleware context without FastMCP context
    message = CallToolRequestParams(
        name="simple_tool",
        arguments={"name": "test", "description": "original", "priority": Priority.LOW}
    )
    context = MiddlewareContext(
        message=message, fastmcp_context=None, method="tools/call"
    )

    # Mock call_next
    async def call_next(ctx):
        return ctx.message.arguments

    result = await middleware.on_call_tool(context, call_next)

    # Should pass through unchanged when no context
    assert result["name"] == "test"
    assert result["description"] == "original"
    assert result["priority"] == Priority.LOW


@pytest.mark.asyncio
async def test_string_elicitation():
    """Test open-ended string elicitation."""
    middleware = TestElicitationMiddleware()

    # Create mock FastMCP context
    mock_fastmcp_context = Mock(spec=Context)

    class MockElicitResponse:
        notes = "These are my notes"

    mock_fastmcp_context.elicit = AsyncMock(
        return_value=AcceptedElicitation(data=MockElicitResponse())
    )

    # Create middleware context
    message = CallToolRequestParams(
        name="string_elicitation_tool",
        arguments={"value": "test"}  # notes not provided
    )
    context = MiddlewareContext(
        message=message, fastmcp_context=mock_fastmcp_context, method="tools/call"
    )

    async def call_next(ctx):
        return ctx.message.arguments

    result = await middleware.on_call_tool(context, call_next)

    assert result["value"] == "test"
    assert result["notes"] == "These are my notes"
    mock_fastmcp_context.elicit.assert_called_once()