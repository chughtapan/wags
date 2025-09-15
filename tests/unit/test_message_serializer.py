"""Unit tests for MessageSerializer."""

import json

from fast_agent.types import PromptMessageExtended
from mcp.types import CallToolRequest, CallToolRequestParams, CallToolResult, TextContent

from src.evals.message_serializer import MessageSerializer


class TestMessageSerializer:
    """Test suite for MessageSerializer."""

    def test_serialize_simple_message(self):
        """Test serialization of a simple text message."""
        # Create a simple user message
        msg = PromptMessageExtended(
            role="user",
            content=[TextContent(type="text", text="Hello, world!")]
        )

        # Serialize
        json_str = MessageSerializer.serialize_complete([msg])
        data = json.loads(json_str)

        # Verify structure
        assert data["format"] == "complete_v1"
        assert data["message_count"] == 1
        assert len(data["messages"]) == 1

        # Verify message content
        msg_data = data["messages"][0]
        assert msg_data["role"] == "user"
        assert len(msg_data["content"]) == 1
        assert msg_data["content"][0]["text"] == "Hello, world!"

    def test_preserves_tool_calls(self):
        """Test that tool calls are preserved during serialization."""
        # Create message with tool calls
        msg = PromptMessageExtended(
            role="assistant",
            content=[TextContent(type="text", text="I'll check the weather for you.")],
            tool_calls={
                "call_123": CallToolRequest(
                    params=CallToolRequestParams(
                        name="get_weather",
                        arguments={"city": "Paris", "units": "celsius"}
                    )
                )
            }
        )

        # Serialize
        json_str = MessageSerializer.serialize_complete([msg])
        data = json.loads(json_str)

        # Verify tool calls preserved
        msg_data = data["messages"][0]
        assert msg_data["tool_calls"] is not None
        assert "call_123" in msg_data["tool_calls"]
        assert msg_data["tool_calls"]["call_123"]["name"] == "get_weather"
        assert msg_data["tool_calls"]["call_123"]["arguments"]["city"] == "Paris"

    def test_preserves_tool_results(self):
        """Test that tool results are preserved."""
        # Create message with tool results
        msg = PromptMessageExtended(
            role="user",  # Tool results come back as user messages
            content=[],
            tool_results={
                "call_123": CallToolResult(
                    content=[TextContent(type="text", text="Weather: Sunny, 22°C")],
                    isError=False
                )
            }
        )

        # Serialize
        json_str = MessageSerializer.serialize_complete([msg])
        data = json.loads(json_str)

        # Verify tool results preserved
        msg_data = data["messages"][0]
        assert msg_data["tool_results"] is not None
        assert "call_123" in msg_data["tool_results"]
        assert msg_data["tool_results"]["call_123"]["is_error"] is False
        assert msg_data["tool_results"]["call_123"]["content"][0]["text"] == "Weather: Sunny, 22°C"

    def test_extract_tool_calls_by_turn(self):
        """Test extraction of tool calls grouped by turn."""
        # Create a conversation with multiple turns
        messages = [
            # Turn 1
            PromptMessageExtended(role="user", content=[TextContent(type="text", text="Get weather")]),
            PromptMessageExtended(
                role="assistant",
                content=[],
                tool_calls={
                    "call_1": CallToolRequest(
                        params=CallToolRequestParams(
                            name="get_weather",
                            arguments={"city": "Paris"}
                        )
                    )
                }
            ),
            # Turn 2
            PromptMessageExtended(role="user", content=[TextContent(type="text", text="Book flight")]),
            PromptMessageExtended(
                role="assistant",
                content=[],
                tool_calls={
                    "call_2": CallToolRequest(
                        params=CallToolRequestParams(
                            name="book_flight",
                            arguments={"from": "NYC", "to": "LAX"}
                        )
                    ),
                    "call_3": CallToolRequest(
                        params=CallToolRequestParams(
                            name="send_confirmation",
                            arguments={"email": "user@example.com"}
                        )
                    )
                }
            ),
        ]

        # First serialize to complete format, then extract
        complete_json = MessageSerializer.serialize_complete(messages)
        complete_data = json.loads(complete_json)

        # Extract tool calls from the JSON data
        turns = MessageSerializer.extract_tool_calls_by_turn(complete_data)

        # Verify structure
        assert len(turns) == 2

        # Turn 1 should have 1 tool call
        assert len(turns[0]) == 1
        assert turns[0][0]["function"] == "get_weather"
        assert turns[0][0]["arguments"]["city"] == "Paris"

        # Turn 2 should have 2 tool calls
        assert len(turns[1]) == 2
        assert turns[1][0]["function"] == "book_flight"
        assert turns[1][1]["function"] == "send_confirmation"

    def test_format_to_executable(self):
        """Test conversion to BFCL executable format."""
        tool_calls = [
            [
                {"function": "get_weather", "arguments": {"city": "Paris"}},
                {"function": "get_temperature", "arguments": {"location": "Paris", "units": "celsius"}}
            ],
            [
                {"function": "book_flight", "arguments": {"from": "NYC", "to": "LAX", "date": "2024-01-15"}}
            ]
        ]

        # Convert to executable format
        executable = MessageSerializer.format_to_executable(tool_calls)

        # Verify format
        assert len(executable) == 2
        assert len(executable[0]) == 2
        assert executable[0][0] == "get_weather(city='Paris')"
        assert executable[0][1] == "get_temperature(location='Paris', units='celsius')"
        assert executable[1][0] == "book_flight(from='NYC', to='LAX', date='2024-01-15')"

    def test_handles_mixed_content(self):
        """Test handling of messages with both text and tool calls."""
        msg = PromptMessageExtended(
            role="assistant",
            content=[
                TextContent(type="text", text="Let me help you with that."),
                TextContent(type="text", text="I'll check the weather now.")
            ],
            tool_calls={
                "call_456": CallToolRequest(
                    params=CallToolRequestParams(
                        name="get_weather",
                        arguments={"city": "London"}
                    )
                )
            }
        )

        # Serialize
        json_str = MessageSerializer.serialize_complete([msg])
        data = json.loads(json_str)

        # Verify both content and tool calls are preserved
        msg_data = data["messages"][0]
        assert len(msg_data["content"]) == 2
        assert msg_data["content"][0]["text"] == "Let me help you with that."
        assert msg_data["content"][1]["text"] == "I'll check the weather now."
        assert msg_data["tool_calls"]["call_456"]["name"] == "get_weather"

    def test_handles_empty_messages(self):
        """Test handling of empty messages."""
        messages = []
        json_str = MessageSerializer.serialize_complete(messages)
        data = json.loads(json_str)

        assert data["message_count"] == 0
        assert len(data["messages"]) == 0

    def test_preserves_message_order(self):
        """Test that message order is preserved."""
        messages = [
            PromptMessageExtended(role="user", content=[TextContent(type="text", text="First")]),
            PromptMessageExtended(role="assistant", content=[TextContent(type="text", text="Second")]),
            PromptMessageExtended(role="user", content=[TextContent(type="text", text="Third")]),
        ]

        json_str = MessageSerializer.serialize_complete(messages)
        data = json.loads(json_str)

        assert len(data["messages"]) == 3
        assert data["messages"][0]["content"][0]["text"] == "First"
        assert data["messages"][1]["content"][0]["text"] == "Second"
        assert data["messages"][2]["content"][0]["text"] == "Third"