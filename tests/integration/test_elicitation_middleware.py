"""Integration tests for ElicitationMiddleware with FastMCP."""

from enum import Enum
from typing import Annotated, Any

import pytest
from fastmcp import FastMCP
from fastmcp.client import Client
from fastmcp.client.elicitation import ElicitResult
from mcp.client.session import ClientSession
from mcp.shared.context import RequestContext
from mcp.types import ElicitRequestParams

from wags.middleware.elicitation import ElicitationMiddleware, RequiresElicitation


class Priority(Enum):
    """Test enum for priority levels."""

    LOW = 1
    MEDIUM = 2
    HIGH = 3


class TestHandlers:
    """Test handlers for elicitation tests."""

    async def elicitation_tool(
        self,
        name: str,
        description: Annotated[str, RequiresElicitation("Enter a description")],
        priority: Annotated[Priority, RequiresElicitation("Select priority level")],
    ) -> dict[str, Any]:
        """Tool with elicitation parameters."""
        return {
            "name": name,
            "description": description,
            "priority": priority.value if isinstance(priority, Priority) else priority,
        }

    async def multi_elicitation_tool(
        self,
        base_value: int,
        multiplier: Annotated[int, RequiresElicitation("Enter multiplier (1-10)")],
        notes: Annotated[str, RequiresElicitation("Add any notes")],
    ) -> dict[str, Any]:
        """Tool with multiple elicitation fields."""
        return {"result": base_value * multiplier, "notes": notes}

    async def simple_tool(self, name: str, value: int) -> dict[str, Any]:
        """Simple tool without elicitation."""
        return {"name": name, "value": value * 2}


@pytest.mark.asyncio
class TestElicitationMiddleware:
    """Integration tests for ElicitationMiddleware."""

    async def test_elicitation_with_accepted_response(self) -> None:
        """Test ElicitationMiddleware with accepted elicitation using real client flow."""
        mcp = FastMCP("test-server")
        handlers = TestHandlers()

        # Add elicitation middleware
        elicitation_mw = ElicitationMiddleware(handlers=handlers)
        mcp.add_middleware(elicitation_mw)

        # Track elicitation requests
        elicitation_requests = []

        # Create elicitation handler that accepts and provides values
        async def test_elicitation_handler(
            message: str,
            response_type: type[Any],
            params: ElicitRequestParams,
            context: RequestContext[ClientSession, Any],
        ) -> dict[str, Any]:
            """Auto-accept elicitation with test values."""
            elicitation_requests.append(
                {"message": message, "response_type": response_type.__name__ if response_type else None}
            )

            # Return accepted values based on the response type
            if response_type:
                # The response_type will have fields like description and priority
                return {"description": "Test description", "priority": Priority.HIGH}
            return {}

        # Register tool with all required parameters
        @mcp.tool
        async def elicitation_tool(name: str, description: str, priority: Priority) -> dict[str, Any]:
            return await handlers.elicitation_tool(name, description, priority)

        # Test with client using elicitation handler
        async with Client(mcp, elicitation_handler=test_elicitation_handler) as client:
            result = await client.call_tool(
                "elicitation_tool",
                {
                    "name": "test",
                    "description": "original description",  # Provided but will be edited
                    "priority": Priority.LOW,  # Provided but will be edited
                },
            )

            # Verify elicitation happened and values were EDITED
            assert len(elicitation_requests) > 0
            assert result.data["name"] == "test"  # Not elicited, stays same
            assert result.data["description"] == "Test description"  # EDITED via elicitation
            assert result.data["priority"] == Priority.HIGH.value  # EDITED via elicitation

    async def test_elicitation_with_declined_response(self) -> None:
        """Test ElicitationMiddleware with declined elicitation using real client flow."""
        mcp = FastMCP("test-server")
        handlers = TestHandlers()

        # Add elicitation middleware
        elicitation_mw = ElicitationMiddleware(handlers=handlers)
        mcp.add_middleware(elicitation_mw)

        # Create elicitation handler that declines
        async def declining_elicitation_handler(
            message: str,
            response_type: type[Any],
            params: ElicitRequestParams,
            context: RequestContext[ClientSession, Any],
        ) -> ElicitResult[Any]:
            """Decline all elicitation requests."""
            # Return ElicitResult with action="decline"
            return ElicitResult(action="decline")

        # Register tool with all required parameters
        @mcp.tool
        async def elicitation_tool(name: str, description: str, priority: Priority) -> dict[str, Any]:
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
                        "priority": Priority.LOW,  # But user declines to edit
                    },
                )

            # Verify the error is about declined elicitation
            assert "declined" in str(exc_info.value).lower() or "elicitation" in str(exc_info.value).lower()

    async def test_elicitation_multiple_fields(self) -> None:
        """Test ElicitationMiddleware collecting multiple fields in one elicitation."""
        mcp = FastMCP("test-server")
        handlers = TestHandlers()

        # Add elicitation middleware
        elicitation_mw = ElicitationMiddleware(handlers=handlers)
        mcp.add_middleware(elicitation_mw)

        # Track elicitation details
        elicitation_count = []

        # Create elicitation handler
        async def multi_field_handler(
            message: str,
            response_type: type[Any],
            params: ElicitRequestParams,
            context: RequestContext[ClientSession, Any],
        ) -> dict[str, Any]:
            """Provide multiple field values."""
            elicitation_count.append(1)

            # Return all required fields at once
            return {"multiplier": 5, "notes": "Test notes from elicitation"}

        # Register tool with all required parameters
        @mcp.tool
        async def multi_elicitation_tool(base_value: int, multiplier: int, notes: str) -> dict[str, Any]:
            return await handlers.multi_elicitation_tool(base_value, multiplier, notes)

        # Test with client
        async with Client(mcp, elicitation_handler=multi_field_handler) as client:
            result = await client.call_tool(
                "multi_elicitation_tool",
                {
                    "base_value": 10,
                    "multiplier": 2,  # Provided but will be edited to 5
                    "notes": "original notes",  # Provided but will be edited
                },
            )

            # Should have elicited both fields in ONE call
            assert len(elicitation_count) == 1
            assert result.data["result"] == 50  # 10 * 5 (edited multiplier)
            assert result.data["notes"] == "Test notes from elicitation"  # Edited notes

    async def test_no_elicitation_passthrough(self) -> None:
        """Test that tools without elicitation annotations work normally."""
        mcp = FastMCP("test-server")
        handlers = TestHandlers()

        # Add elicitation middleware
        elicitation_mw = ElicitationMiddleware(handlers=handlers)
        mcp.add_middleware(elicitation_mw)

        # Track if elicitation was called
        elicitation_called = []

        async def tracking_handler(
            message: str,
            response_type: type[Any],
            params: ElicitRequestParams,
            context: RequestContext[ClientSession, Any],
        ) -> dict[str, Any]:
            elicitation_called.append(1)
            return {}

        # Register simple tool (no elicitation annotations)
        @mcp.tool
        async def simple_tool(name: str, value: int) -> dict[str, Any]:
            return await handlers.simple_tool(name, value)

        # Test with client
        async with Client(mcp, elicitation_handler=tracking_handler) as client:
            result = await client.call_tool("simple_tool", {"name": "test", "value": 10})

            # No elicitation should have been triggered
            assert len(elicitation_called) == 0
            assert result.data == {"name": "test", "value": 20}
