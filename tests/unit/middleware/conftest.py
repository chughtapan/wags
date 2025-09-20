"""Shared test fixtures for middleware tests."""

from enum import Enum
from typing import Annotated, Literal

import pytest

from src.wags.middleware.elicitation import RequiresElicitation


class Priority(Enum):
    """Test enum for priority levels."""

    LOW = 1
    MEDIUM = 2
    HIGH = 3


class MockHandlers:
    """Mock handlers for elicitation tests."""

    async def simple_tool(
        self,
        name: str,
        description: Annotated[Literal["short", "detailed"], RequiresElicitation("Choose description format")],
        priority: Annotated[Priority, RequiresElicitation("Select priority level")],
    ):
        """Simple tool for testing with multiple elicitation fields."""
        return {
            "name": name,
            "description": description,
            "priority": priority.value if isinstance(priority, Priority) else priority,
        }

    async def string_elicitation_tool(self, value: str, notes: Annotated[str, RequiresElicitation("Add notes")]):
        """Tool with open-ended string elicitation."""
        return {"value": value, "notes": notes}

    async def no_elicitation_tool(self, value: str):
        """Tool without elicitation annotations."""
        return {"value": value}


@pytest.fixture
def mock_handlers():
    """Provide mock handlers instance."""
    return MockHandlers()