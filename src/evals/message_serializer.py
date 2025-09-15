"""
Message serializer that properly preserves all FastAgent message data.

This module provides serialization that actually preserves tool calls,
unlike FastAgent's built-in serialization which drops them.
"""

import json
from datetime import datetime
from typing import Any

from fast_agent.types import PromptMessageExtended


class MessageSerializer:
    """
    Practical serializer that preserves everything we need from FastAgent messages.
    """

    @staticmethod
    def _strip_server_prefix(tool_name: str) -> str:
        """Strip server prefix from tool name (e.g., 'ticketapi-create_ticket' -> 'create_ticket')."""
        if "-" in tool_name:
            return tool_name.split("-", 1)[1]
        return tool_name

    @staticmethod
    def _serialize_content_item(content: Any) -> dict[str, Any]:
        """Serialize a single content item (text, tool use, etc.)."""
        if hasattr(content, 'model_dump'):
            return content.model_dump()
        elif hasattr(content, '__dict__'):
            content_dict = {"type": getattr(content, 'type', 'text')}
            if hasattr(content, 'text'):
                content_dict["text"] = content.text
            for attr in ['name', 'input', 'tool_use_id']:
                if hasattr(content, attr):
                    content_dict[attr] = getattr(content, attr)
            return content_dict
        else:
            return {"type": "text", "text": str(content)}

    @staticmethod
    def _serialize_tool_calls(tool_calls: dict) -> dict[str, Any] | None:
        """Serialize tool calls from a message."""
        if not tool_calls:
            return None

        serialized = {}
        for tool_id, call in tool_calls.items():
            tool_name = MessageSerializer._strip_server_prefix(call.params.name)
            serialized[tool_id] = {
                "name": tool_name,
                "arguments": call.params.arguments
            }
        return serialized

    @staticmethod
    def _serialize_tool_results(tool_results: dict) -> dict[str, Any] | None:
        """Serialize tool results from a message."""
        if not tool_results:
            return None

        serialized = {}
        for tool_id, result in tool_results.items():
            result_content = [
                MessageSerializer._serialize_content_item(c)
                for c in result.content
            ]
            serialized[tool_id] = {
                "content": result_content,
                "is_error": result.isError
            }
        return serialized

    @staticmethod
    def _serialize_message(msg: PromptMessageExtended, idx: int) -> dict[str, Any]:
        """Serialize a single message."""
        msg_dict = {
            "index": idx,
            "role": msg.role,
            "content": [
                MessageSerializer._serialize_content_item(content)
                for content in msg.content
            ],
            "tool_calls": MessageSerializer._serialize_tool_calls(msg.tool_calls),
            "tool_results": MessageSerializer._serialize_tool_results(msg.tool_results),
            "metadata": {}
        }

        # Preserve stop reason if present
        if msg.stop_reason:
            msg_dict["metadata"]["stop_reason"] = str(msg.stop_reason)

        return msg_dict

    @staticmethod
    def serialize_complete(messages: list[PromptMessageExtended]) -> str:
        """
        Serialize messages preserving all message data including tool calls and results.

        Args:
            messages: List of PromptMessageExtended objects from FastAgent

        Returns:
            JSON string with complete message preservation
        """
        serialized_messages = [
            MessageSerializer._serialize_message(msg, idx)
            for idx, msg in enumerate(messages)
        ]

        return json.dumps({
            "format": "complete_v1",
            "created_at": datetime.now().isoformat(),
            "message_count": len(serialized_messages),
            "messages": serialized_messages
        }, indent=2)

    @staticmethod
    def extract_tool_calls_by_turn(complete_data: dict) -> list[list[dict[str, Any]]]:
        """
        Extract tool calls grouped by conversation turn from complete JSON data.

        Args:
            complete_data: Dictionary from complete.json file

        Returns:
            List of turns, where each turn is a list of tool call dicts
        """
        turns = []
        current_turn = []

        for msg in complete_data["messages"]:
            if msg["role"] == "user" and current_turn:
                turns.append(current_turn)
                current_turn = []
            elif msg["role"] == "assistant" and msg["tool_calls"]:
                for tool_id, call in msg["tool_calls"].items():
                    tool_info = {
                        "function": call["name"],
                        "arguments": call["arguments"],
                        "tool_id": tool_id
                    }
                    current_turn.append(tool_info)

        # Don't forget the last turn
        if current_turn:
            turns.append(current_turn)

        return turns

    @staticmethod
    def format_to_executable(tool_calls: list[list[dict[str, Any]]]) -> list[list[str]]:
        """
        Convert tool calls to BFCL executable format.

        This matches the format expected by BFCL evaluator.

        Args:
            tool_calls: List of turns with tool call dictionaries

        Returns:
            List of turns with executable string format
        """
        result = []

        for turn in tool_calls:
            turn_calls = []
            for call in turn:
                args_list = []
                for key, value in call["arguments"].items():
                    args_list.append(f"{key}={repr(value)}")
                args_str = ", ".join(args_list)
                turn_calls.append(f"{call['function']}({args_str})")

            result.append(turn_calls)

        return result