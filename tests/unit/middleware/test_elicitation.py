"""Tests for elicitation middleware."""

from unittest.mock import AsyncMock, Mock

import pytest
from fastmcp.server.context import Context
from fastmcp.server.elicitation import AcceptedElicitation
from fastmcp.server.middleware.middleware import MiddlewareContext
from mcp.types import CallToolRequestParams

from src.wags.middleware.elicitation import ElicitationMiddleware, RequiresElicitation

from .conftest import MockHandlers, Priority


@pytest.mark.asyncio
async def test_middleware_registration():
    """Test that tool handlers are discoverable."""
    handlers = MockHandlers()
    middleware = ElicitationMiddleware(handlers=handlers)

    # Should be able to get tool handlers
    from mcp.types import CallToolRequestParams
    assert middleware.get_tool_handler(CallToolRequestParams(name="simple_tool", arguments={})) is not None
    assert middleware.get_tool_handler(CallToolRequestParams(name="string_elicitation_tool", arguments={})) is not None
    assert middleware.get_tool_handler(CallToolRequestParams(name="no_elicitation_tool", arguments={})) is not None


@pytest.mark.asyncio
async def test_get_tool_handler():
    """Test getting tool handler from request."""
    handlers = MockHandlers()
    middleware = ElicitationMiddleware(handlers=handlers)

    # Test existing handler
    from mcp.types import CallToolRequestParams
    request = CallToolRequestParams(name="simple_tool", arguments={})
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
    handlers = MockHandlers()
    middleware = ElicitationMiddleware(handlers=handlers)

    # Create mock FastMCP context
    mock_fastmcp_context = Mock(spec=Context)

    # Create a mock response that simulates the Pydantic model
    class MockElicitResponse:
        description = "short"
        priority = Priority.HIGH

    mock_fastmcp_context.elicit = AsyncMock(return_value=AcceptedElicitation(data=MockElicitResponse()))

    # Create middleware context
    message = CallToolRequestParams(
        name="simple_tool",
        arguments={"name": "test"},  # description and priority not provided
    )
    context = MiddlewareContext(message=message, fastmcp_context=mock_fastmcp_context, method="tools/call")

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
    handlers = MockHandlers()
    middleware = ElicitationMiddleware(handlers=handlers)

    # Create middleware context for unknown tool
    message = CallToolRequestParams(name="unknown_tool", arguments={"arg1": "value1", "arg2": "value2"})
    context = MiddlewareContext(message=message, method="tools/call")

    # Mock call_next to return the arguments
    async def call_next(ctx):
        return ctx.message.arguments

    result = await middleware.on_call_tool(context, call_next)

    assert result == message.arguments  # Should pass through unchanged


@pytest.mark.asyncio
async def test_handler_without_elicitation():
    """Test handler without any elicitation annotations."""
    handlers = MockHandlers()
    middleware = ElicitationMiddleware(handlers=handlers)

    # Create middleware context
    message = CallToolRequestParams(name="no_elicitation_tool", arguments={"value": "test_value"})
    context = MiddlewareContext(message=message, method="tools/call")

    # Mock call_next
    async def call_next(ctx):
        return ctx.message.arguments

    result = await middleware.on_call_tool(context, call_next)

    assert result["value"] == "test_value"


@pytest.mark.asyncio
async def test_passthrough_without_context():
    """Test that middleware passes through when no FastMCP context."""
    handlers = MockHandlers()
    middleware = ElicitationMiddleware(handlers=handlers)

    # Create middleware context without FastMCP context
    message = CallToolRequestParams(
        name="simple_tool",
        arguments={"name": "test", "description": "original", "priority": Priority.LOW},
    )
    context = MiddlewareContext(message=message, fastmcp_context=None, method="tools/call")

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
    handlers = MockHandlers()
    middleware = ElicitationMiddleware(handlers=handlers)

    # Create mock FastMCP context
    mock_fastmcp_context = Mock(spec=Context)

    class MockElicitResponse:
        notes = "These are my notes"

    mock_fastmcp_context.elicit = AsyncMock(return_value=AcceptedElicitation(data=MockElicitResponse()))

    # Create middleware context
    message = CallToolRequestParams(
        name="string_elicitation_tool",
        arguments={"value": "test"},  # notes not provided
    )
    context = MiddlewareContext(message=message, fastmcp_context=mock_fastmcp_context, method="tools/call")

    async def call_next(ctx):
        return ctx.message.arguments

    result = await middleware.on_call_tool(context, call_next)

    assert result["value"] == "test"
    assert result["notes"] == "These are my notes"
    mock_fastmcp_context.elicit.assert_called_once()


# Test for multiple passes removed - no longer using pass system


def test_requires_elicitation_type():
    """Test RequiresElicitation annotation type."""
    # Test valid creation
    re = RequiresElicitation(prompt="Choose format")
    assert re.prompt == "Choose format"

    # Test validation - empty prompt should raise error
    with pytest.raises(ValueError, match="Elicitation prompt is required"):
        RequiresElicitation(prompt="")


@pytest.mark.asyncio
async def test_no_elicitation_capability_skips_elicitation():
    """Test that clients without elicitation capability skip elicitation."""
    handlers = MockHandlers()
    middleware = ElicitationMiddleware(handlers=handlers)
    
    # Create context without elicitation capability
    message = CallToolRequestParams(
        name="string_elicitation_tool",
        arguments={"value": "test"}  # notes not provided, would normally trigger elicitation
    )
    
    # Mock a context with no elicitation capability
    mock_fastmcp_context = Mock()
    mock_session = Mock()
    mock_client_params = Mock()
    mock_capabilities = Mock()
    mock_capabilities.elicitation = None  # No elicitation capability
    
    mock_client_params.capabilities = mock_capabilities
    mock_session.client_params = mock_client_params
    mock_fastmcp_context.session = mock_session
    
    context = MiddlewareContext(message=message, fastmcp_context=mock_fastmcp_context)
    
    # Should pass through without elicitation
    handler = handlers.string_elicitation_tool
    result = await middleware.handle_on_tool_call(context, handler)
    assert result == context  # Passes through unchanged without elicitation