"""Unit tests for fastagent_helpers module."""

import json

from fast_agent.types import PromptMessageExtended
from mcp.types import CallToolRequest, CallToolRequestParams, CallToolResult, TextContent

from tests.utils.fastagent_helpers import MessageSerializer


class TestMessageSerializer:
    """Test suite for MessageSerializer."""

    def test_serialize_simple_message(self):
        """Test serialization of a simple text message."""
        # Create a simple user message
        msg = PromptMessageExtended(
            role="user",
            content=[TextContent(type="text", text="Hello, world!")]
        )

        # Serialize to dictionary
        serialized = MessageSerializer.serialize_message(msg, 0)

        # Check basic structure
        assert serialized["index"] == 0
        assert serialized["role"] == "user"
        assert len(serialized["content"]) == 1
        assert serialized["content"][0]["text"] == "Hello, world!"

    def test_preserves_tool_calls(self):
        """Test that tool calls are preserved in serialization."""
        # Create a message with tool calls
        tool_call = CallToolRequest(
            method="tools/call",
            params=CallToolRequestParams(
                name="test_tool",
                arguments={"arg1": "value1", "arg2": 42}
            )
        )

        msg = PromptMessageExtended(
            role="assistant",
            content=[TextContent(type="text", text="I'll use a tool")],
            tool_calls={"tool_123": tool_call}
        )

        # Serialize to dictionary
        serialized = MessageSerializer.serialize_message(msg, 0)

        # Check tool calls are preserved
        assert serialized["tool_calls"] is not None
        assert "tool_123" in serialized["tool_calls"]
        assert serialized["tool_calls"]["tool_123"]["name"] == "test_tool"
        assert serialized["tool_calls"]["tool_123"]["arguments"]["arg1"] == "value1"

    def test_preserves_tool_results(self):
        """Test that tool results are preserved in serialization."""
        # Create a message with tool results
        tool_result = CallToolResult(
            content=[TextContent(type="text", text="Tool output")],
            isError=False
        )

        msg = PromptMessageExtended(
            role="user",
            content=[],
            tool_results={"tool_123": tool_result}
        )

        # Serialize to dictionary
        serialized = MessageSerializer.serialize_message(msg, 0)

        # Check tool results are preserved
        assert serialized["tool_results"] is not None
        assert "tool_123" in serialized["tool_results"]
        assert serialized["tool_results"]["tool_123"]["is_error"] is False
        assert serialized["tool_results"]["tool_123"]["content"][0]["text"] == "Tool output"

    def test_extract_tool_calls_by_turn(self):
        """Test extraction of tool calls grouped by turn."""
        # Create a complete conversation
        complete_data = {
            "messages": [
                {"role": "user", "tool_calls": None},
                {"role": "assistant", "tool_calls": {
                    "t1": {"name": "search", "arguments": {"query": "test"}}
                }},
                {"role": "user", "tool_calls": None},  # New turn
                {"role": "assistant", "tool_calls": {
                    "t2": {"name": "calculate", "arguments": {"x": 5}}
                }}
            ]
        }

        # Extract tool calls by turn
        turns = MessageSerializer.extract_tool_calls_by_turn(complete_data)

        # Check we have 2 turns
        assert len(turns) == 2
        
        # First turn has search tool
        assert len(turns[0]) == 1
        assert turns[0][0]["function"] == "search"
        assert turns[0][0]["arguments"]["query"] == "test"
        
        # Second turn has calculate tool
        assert len(turns[1]) == 1
        assert turns[1][0]["function"] == "calculate"
        assert turns[1][0]["arguments"]["x"] == 5

    def test_format_to_executable(self):
        """Test formatting tool calls to executable format."""
        # Tool calls in dictionary format
        tool_calls = [
            [
                {"function": "search", "arguments": {"query": "test", "limit": 10}},
                {"function": "filter", "arguments": {"field": "date"}}
            ],
            [
                {"function": "calculate", "arguments": {"x": 5, "y": 3}}
            ]
        ]

        # Format to executable
        executable = MessageSerializer.format_to_executable(tool_calls)

        # Check format
        assert len(executable) == 2
        assert len(executable[0]) == 2
        assert executable[0][0] == "search(query='test', limit=10)"
        assert executable[0][1] == "filter(field='date')"
        assert len(executable[1]) == 1
        assert executable[1][0] == "calculate(x=5, y=3)"

    def test_handles_mixed_content(self):
        """Test serialization of messages with multiple content types."""
        # Create a message with multiple content items
        msg = PromptMessageExtended(
            role="assistant",
            content=[
                TextContent(type="text", text="First part"),
                TextContent(type="text", text="Second part"),
            ]
        )

        # Serialize
        serialized = MessageSerializer.serialize_message(msg, 0)

        # Check all content is preserved
        assert len(serialized["content"]) == 2
        assert serialized["content"][0]["text"] == "First part"
        assert serialized["content"][1]["text"] == "Second part"

    def test_handles_empty_messages(self):
        """Test serialization of empty messages."""
        # Create an empty message
        msg = PromptMessageExtended(
            role="user",
            content=[]
        )

        # Serialize
        serialized = MessageSerializer.serialize_message(msg, 0)

        # Check structure is maintained
        assert serialized["role"] == "user"
        assert serialized["content"] == []
        assert serialized["tool_calls"] is None
        assert serialized["tool_results"] is None

    def test_preserves_message_order(self):
        """Test that serialize_complete preserves message order."""
        # Create a conversation
        messages = [
            PromptMessageExtended(
                role="user",
                content=[TextContent(type="text", text="First")]
            ),
            PromptMessageExtended(
                role="assistant",
                content=[TextContent(type="text", text="Second")]
            ),
            PromptMessageExtended(
                role="user",
                content=[TextContent(type="text", text="Third")]
            ),
        ]

        # Serialize complete conversation
        json_str = MessageSerializer.serialize_complete(messages)
        data = json.loads(json_str)

        # Check order is preserved
        assert len(data["messages"]) == 3
        assert data["messages"][0]["content"][0]["text"] == "First"
        assert data["messages"][1]["content"][0]["text"] == "Second"
        assert data["messages"][2]["content"][0]["text"] == "Third"