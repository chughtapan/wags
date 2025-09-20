"""Unit tests for handlers generator utilities."""

import json
from unittest.mock import AsyncMock, patch

import pytest
from mcp.types import Tool

from wags.utils.handlers_generator import (
    generate_handlers_stub,
    generate_method_stub,
    json_schema_to_python_type,
    sanitize_method_name,
)


# Fixtures - moved from conftest.py since only used here
@pytest.fixture
def basic_tool():
    """Create a basic Tool with minimal valid schema."""
    return Tool(
        name="test_tool",
        description="Test tool description",
        inputSchema={"type": "object", "properties": {}}
    )


@pytest.fixture
def tool_with_params():
    """Create a Tool with parameters."""
    return Tool(
        name="create_item",
        description="Create a new item",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "quantity": {"type": "integer"}
            },
            "required": ["name"]
        }
    )


@pytest.fixture
def tool_with_enum():
    """Create a Tool with enum parameter."""
    return Tool(
        name="status_tool",
        description="Tool with status enum",
        inputSchema={
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["active", "inactive"]}
            },
            "required": ["status"]
        }
    )


@pytest.fixture
def tool_with_boolean():
    """Create a Tool with boolean parameter."""
    return Tool(
        name="flag_tool",
        inputSchema={
            "type": "object",
            "properties": {
                "enabled": {"type": "boolean"}
            },
            "required": []
        }
    )


@pytest.fixture
def empty_tool():
    """Create a Tool without parameters."""
    return Tool(
        name="empty_tool",
        inputSchema={"type": "object", "properties": {}}
    )


@pytest.fixture
def tool_with_literal():
    """Create a Tool with Literal type enum."""
    return Tool(
        name="tool_with_literal",
        inputSchema={
            "type": "object",
            "properties": {
                "choice": {"type": "string", "enum": ["a", "b", "c"]}
            }
        }
    )


class TestJsonSchemaToPythonType:
    """Tests for json_schema_to_python_type function."""

    def test_all_type_conversions(self):
        """Test all JSON schema to Python type conversions."""
        assert json_schema_to_python_type({"type": "string"}) == "str"
        assert json_schema_to_python_type({"type": "integer"}) == "int"
        assert json_schema_to_python_type({"type": "number"}) == "float"
        assert json_schema_to_python_type({"type": "boolean"}) == "bool"
        assert json_schema_to_python_type({"type": "null"}) == "None"
        assert json_schema_to_python_type({"type": "array", "items": {"type": "string"}}) == "list[str]"
        nested_array = {"type": "array", "items": {"type": "array", "items": {"type": "integer"}}}
        assert json_schema_to_python_type(nested_array) == "list[list[int]]"
        obj_schema = {"type": "object", "properties": {"key": {"type": "string"}}}
        assert json_schema_to_python_type(obj_schema) == "dict[str, Any]"
        enum_schema = {"type": "string", "enum": ["option1", "option2", "option3"]}
        assert json_schema_to_python_type(enum_schema) == 'Literal["option1", "option2", "option3"]'
        assert json_schema_to_python_type({"type": "unknown"}) == "Any"
        assert json_schema_to_python_type("not a dict") == "Any"


class TestSanitizeMethodName:
    """Tests for sanitize_method_name function."""

    def test_all_name_sanitizations(self):
        """Test all method name sanitizations."""
        assert sanitize_method_name("create_issue") == "create_issue"
        assert sanitize_method_name("create-issue") == "create_issue"
        assert sanitize_method_name("api.create.issue") == "api_create_issue"
        assert sanitize_method_name("create issue now") == "create_issue_now"
        assert sanitize_method_name("create/issue") == "create_issue"
        assert sanitize_method_name("123create") == "tool_123create"
        assert sanitize_method_name("") == "tool"
        assert sanitize_method_name("create@#$issue!%^") == "createissue"
        assert sanitize_method_name("CreateIssue") == "createissue"


class TestGenerateMethodStub:
    """Tests for generate_method_stub function."""

    def test_all_tool_types(self, tool_with_params, tool_with_enum, tool_with_boolean, empty_tool):
        """Test generating method stubs for all tool types."""
        # Test simple tool with parameters
        result = generate_method_stub(tool_with_params)
        # No more @tool_handler decorator - just async def
        assert "async def create_item(" in result
        assert "name: str" in result
        assert "quantity: int | None = None" in result
        assert '"""Create a new item"""' in result

        # Test tool with enum
        result = generate_method_stub(tool_with_enum)
        assert 'status: Literal["active", "inactive"]' in result

        # Test tool with boolean default
        result = generate_method_stub(tool_with_boolean)
        assert "enabled: bool | None = False" in result

        # Test tool without parameters
        result = generate_method_stub(empty_tool)
        # No more @tool_handler decorator - just async def
        assert "async def" in result
        assert "async def empty_tool(" in result
        assert "self" in result


class TestGenerateMiddlewareClass:
    """Tests for generate_middleware_class function."""

    def test_all_class_generation_scenarios(self, basic_tool, tool_with_literal, empty_tool):
        """Test all middleware class generation scenarios."""
        # Test empty tools list
        from wags.utils.handlers_generator import generate_handlers_class
        result = generate_handlers_class("EmptyHandlers", [])
        assert "class EmptyHandlers" in result
        assert "pass" in result
        # Check for proper imports (no more tool_handler)
        assert "from" in result or "pass" in result

        # Test single tool
        result = generate_handlers_class("TestHandlers", [basic_tool])
        assert "class TestHandlers" in result
        assert "async def test_tool" in result
        assert "async def test_tool(" in result

        # Test multiple tools with literal
        tools = [tool_with_literal, empty_tool]
        result = generate_handlers_class("MultiHandlers", tools)
        assert "from typing import Any, Literal" in result
        assert "class MultiHandlers" in result
        assert "async def tool_with_literal(" in result
        assert "async def empty_tool(" in result


# TestConnectToServer class removed - connect_to_server function no longer exists
# Now using Client directly in generate_handlers_stub


class TestGenerateMiddlewareStub:
    """Tests for generate_handlers_stub function."""

    @pytest.mark.asyncio
    async def test_generate_stub_to_stdout(self, tmp_path, capsys, basic_tool):
        """Test generating stub to stdout."""
        # Create config
        config_file = tmp_path / "config.json"
        config_data = {"mcpServers": {"test": {}}}
        config_file.write_text(json.dumps(config_data))

        # Mock Client
        mock_mcp = AsyncMock()
        mock_mcp.list_tools = AsyncMock(return_value=[basic_tool])
        mock_mcp.__aenter__ = AsyncMock(return_value=mock_mcp)
        mock_mcp.__aexit__ = AsyncMock(return_value=None)

        with patch("wags.utils.handlers_generator.Client", return_value=mock_mcp):
            await generate_handlers_stub(config_file)

            # Check output
            captured = capsys.readouterr()
            assert "class TestHandlers" in captured.out  # Auto-generated from server name "test"
            assert "async def test_tool" in captured.out

    @pytest.mark.asyncio
    async def test_generate_stub_to_file(self, tmp_path, empty_tool):
        """Test generating stub to file."""
        config_file = tmp_path / "config.json"
        output_file = tmp_path / "output.py"
        config_data = {"mcpServers": {"my-server": {}}}
        config_file.write_text(json.dumps(config_data))

        # Rename the tool for this test
        test_tool = Tool(name="my_tool", inputSchema=empty_tool.inputSchema)

        # Mock Client
        mock_mcp = AsyncMock()
        mock_mcp.list_tools = AsyncMock(return_value=[test_tool])
        mock_mcp.__aenter__ = AsyncMock(return_value=mock_mcp)
        mock_mcp.__aexit__ = AsyncMock(return_value=None)

        with patch("wags.utils.handlers_generator.Client", return_value=mock_mcp):
            await generate_handlers_stub(
                config_file,
                server_name="my-server",
                output_path=output_file,
                class_name="CustomMiddleware"
            )

            # Check file was created
            assert output_file.exists()
            content = output_file.read_text()
            assert "class CustomMiddleware" in content
            assert "async def my_tool" in content

    @pytest.mark.asyncio
    async def test_generate_stub_auto_class_name(self, tmp_path):
        """Test auto-generating class name from server name."""
        config_file = tmp_path / "config.json"
        config_data = {"mcpServers": {"test-server": {}}}
        config_file.write_text(json.dumps(config_data))

        # Mock Client
        mock_mcp = AsyncMock()
        mock_mcp.list_tools = AsyncMock(return_value=[])
        mock_mcp.__aenter__ = AsyncMock(return_value=mock_mcp)
        mock_mcp.__aexit__ = AsyncMock(return_value=None)

        with patch("wags.utils.handlers_generator.Client", return_value=mock_mcp):
            with patch("wags.utils.handlers_generator.generate_handlers_class") as mock_gen:
                mock_gen.return_value = "generated code"

                await generate_handlers_stub(config_file, server_name="test-server")

                # Check class name was auto-generated correctly
                mock_gen.assert_called_once_with("TestServerHandlers", [])