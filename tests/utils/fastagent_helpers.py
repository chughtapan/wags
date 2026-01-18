"""Utilities for working with FastAgent message histories and tool interactions.

This module consolidates all FastAgent-related utilities for testing and evaluation,
providing properly typed functions for message extraction, turn management, and serialization.
"""

import json
from datetime import datetime
from typing import Any

from fast_agent.types import PromptMessageExtended
from mcp.types import CallToolRequest, CallToolResult

# ============= Core Extraction Functions =============


def get_tool_calls(messages: list[PromptMessageExtended]) -> list[tuple[str, CallToolRequest]]:
    """Extract all tool calls from message history.

    Args:
        messages: List of PromptMessageExtended objects from agent.message_history

    Returns:
        List of (tool_id, CallToolRequest) tuples in order of occurrence
    """
    tool_calls = []
    for msg in messages:
        if msg.tool_calls:
            for tool_id, request in msg.tool_calls.items():
                tool_calls.append((tool_id, request))
    return tool_calls


def get_tool_results(messages: list[PromptMessageExtended]) -> dict[str, CallToolResult]:
    """Extract all tool results from message history.

    Args:
        messages: List of PromptMessageExtended objects from agent.message_history

    Returns:
        Dict mapping tool_id to its CallToolResult
    """
    tool_results = {}
    for msg in messages:
        if msg.tool_results:
            tool_results.update(msg.tool_results)
    return tool_results


def get_result_text(result: CallToolResult) -> str:
    """Extract text content from a tool result.

    Args:
        result: CallToolResult containing response content blocks

    Returns:
        Concatenated text from all text content blocks in the result
    """
    texts = [content.text for content in result.content if hasattr(content, "text")]
    return " ".join(texts)


# ============= Turn Management =============


def split_into_turns(messages: list[PromptMessageExtended]) -> list[list[PromptMessageExtended]]:
    """Split message history into conversational turns.

    A turn starts with a user message (not a tool result) and includes
    all messages until the next user message or end of conversation.

    Args:
        messages: List of PromptMessageExtended objects

    Returns:
        List of turns, where each turn is a list of messages
    """
    turns = []
    current_turn: list[PromptMessageExtended] = []

    for msg in messages:
        # User message that's not a tool result starts a new turn
        if msg.role == "user" and not msg.tool_results:
            if current_turn:
                turns.append(current_turn)
            current_turn = [msg]
        else:
            current_turn.append(msg)

    # Don't forget the last turn
    if current_turn:
        turns.append(current_turn)

    return turns


# ============= MessageSerializer (from BFCL) =============


class MessageSerializer:
    """Serializer that preserves all FastAgent message data including tool calls.

    This class provides methods to serialize FastAgent messages to JSON while
    preserving tool calls and results that FastAgent's built-in serialization drops.
    """

    @staticmethod
    def strip_server_prefix(tool_name: str) -> str:
        """Strip server prefix from tool name.

        Args:
            tool_name: Tool name potentially with server prefix

        Returns:
            Tool name without prefix (e.g., 'github-list_issues' -> 'list_issues')
        """
        if "-" in tool_name:
            return tool_name.split("-", 1)[1]
        return tool_name

    @staticmethod
    def _serialize_content_item(content: Any) -> dict[str, Any]:
        """Serialize a single content item (text, tool use, etc.)."""
        if hasattr(content, "model_dump"):
            result: dict[str, Any] = content.model_dump(mode="json")
            return result
        elif hasattr(content, "__dict__"):
            content_dict: dict[str, Any] = {"type": getattr(content, "type", "text")}
            if hasattr(content, "text"):
                content_dict["text"] = content.text
            for attr in ["name", "input", "tool_use_id"]:
                if hasattr(content, attr):
                    content_dict[attr] = getattr(content, attr)
            return content_dict
        else:
            return {"type": "text", "text": str(content)}

    @staticmethod
    def _serialize_tool_calls(tool_calls: dict[str, CallToolRequest] | None) -> dict[str, Any] | None:
        """Serialize tool calls from a message."""
        if not tool_calls:
            return None

        serialized: dict[str, Any] = {}
        for tool_id, call in tool_calls.items():
            tool_name = MessageSerializer.strip_server_prefix(call.params.name)
            serialized[tool_id] = {"name": tool_name, "arguments": call.params.arguments}
        return serialized

    @staticmethod
    def _serialize_tool_results(tool_results: dict[str, CallToolResult] | None) -> dict[str, Any] | None:
        """Serialize tool results from a message."""
        if not tool_results:
            return None

        serialized = {}
        for tool_id, result in tool_results.items():
            result_content = [MessageSerializer._serialize_content_item(c) for c in result.content]
            serialized[tool_id] = {"content": result_content, "is_error": result.is_error}
        return serialized

    @staticmethod
    def serialize_message(msg: PromptMessageExtended, idx: int) -> dict[str, Any]:
        """Serialize a single message to dictionary.

        Args:
            msg: PromptMessageExtended to serialize
            idx: Message index in conversation

        Returns:
            Dictionary representation of the message
        """
        metadata: dict[str, str] = {}
        # Preserve stop reason if present
        if msg.stop_reason:
            metadata["stop_reason"] = str(msg.stop_reason)

        msg_dict: dict[str, Any] = {
            "index": idx,
            "role": msg.role,
            "content": [MessageSerializer._serialize_content_item(content) for content in msg.content],
            "tool_calls": MessageSerializer._serialize_tool_calls(msg.tool_calls),
            "tool_results": MessageSerializer._serialize_tool_results(msg.tool_results),
            "metadata": metadata,
        }

        return msg_dict

    @staticmethod
    def serialize_complete(messages: list[PromptMessageExtended]) -> str:
        """Serialize messages preserving all message data including tool calls and results.

        Args:
            messages: List of PromptMessageExtended objects from FastAgent

        Returns:
            JSON string with complete message preservation
        """
        serialized_messages = [MessageSerializer.serialize_message(msg, idx) for idx, msg in enumerate(messages)]

        return json.dumps(
            {
                "format": "complete_v1",
                "created_at": datetime.now().isoformat(),
                "message_count": len(serialized_messages),
                "messages": serialized_messages,
            },
            indent=2,
        )

    @staticmethod
    def extract_tool_calls_by_turn(complete_data: dict[str, Any]) -> list[list[dict[str, Any]]]:
        """Extract tool calls grouped by conversation turn from complete JSON data.

        Args:
            complete_data: Dictionary from complete.json file

        Returns:
            List of turns, where each turn is a list of tool call dicts
        """
        turns = []
        current_turn: list[dict[str, Any]] = []

        for msg in complete_data["messages"]:
            # Only split on user messages with actual content (not tool results)
            if msg["role"] == "user" and current_turn and not msg.get("tool_results"):
                turns.append(current_turn)
                current_turn = []
            elif msg["role"] == "assistant" and msg["tool_calls"]:
                for tool_id, call in msg["tool_calls"].items():
                    tool_info = {"function": call["name"], "arguments": call["arguments"], "tool_id": tool_id}
                    current_turn.append(tool_info)

        # Don't forget the last turn
        if current_turn:
            turns.append(current_turn)

        return turns

    @staticmethod
    def format_to_executable(tool_calls: list[list[dict[str, Any]]]) -> list[list[str]]:
        """Convert tool calls to BFCL executable format.

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
