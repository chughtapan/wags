"""Tests for elicitation types."""
import pytest

from src.wags.middleware.elicitation import RequiresElicitation


def test_requires_elicitation_creation():
    """Test creating RequiresElicitation annotation."""
    re = RequiresElicitation(prompt="Choose format")
    assert re.prompt == "Choose format"


def test_requires_elicitation_validation():
    """Test validation of RequiresElicitation."""
    with pytest.raises(ValueError, match="Elicitation prompt is required"):
        RequiresElicitation(prompt="")  # Empty prompt


def test_requires_elicitation_with_prompt():
    """Test RequiresElicitation with prompt."""
    re = RequiresElicitation(prompt="Enter value")
    assert re.prompt == "Enter value"