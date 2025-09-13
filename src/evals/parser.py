"""JSONL log parsing and formatting utilities."""

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ParserState:
    """State tracking for parsing JSONL logs."""

    all_turns: list[list[dict[str, Any]]] = field(default_factory=list)
    current_turn_tools: list[dict[str, Any]] = field(default_factory=list)
    in_turn: bool = False


class JsonlParser:
    """Parser for JSONL log files containing tool calls."""

    def parse_file(self, log_path: str) -> list[list[dict[str, Any]]]:
        """
        Parse JSONL log and extract tool calls by turn.

        Uses turn markers to properly group tool calls by which user message
        triggered them, then creates separate BFCL turns for each tool call.

        Args:
            log_path: Path to the JSONL log file

        Returns:
            List of turns, where each turn is a list of tool call dictionaries
        """
        state = ParserState()

        with open(log_path) as f:
            for line in f:
                if not line.strip():
                    continue

                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                self._process_line(entry, state)

        return state.all_turns

    def _process_line(self, entry: dict, state: ParserState) -> None:
        """Process a single JSONL entry."""
        is_marker, marker_type = self._is_turn_marker(entry)

        if is_marker:
            self._handle_turn_marker(marker_type, state)
            return

        if not state.in_turn:
            return

        # Extract tool calls if this is an OpenAI completion response
        if self._is_completion_response(entry):
            tool_calls = self._extract_tool_calls(entry)
            state.current_turn_tools.extend(tool_calls)

    def _is_turn_marker(self, entry: dict) -> tuple[bool, str | None]:
        """Check if entry is a turn start/end marker."""
        message = entry.get("message", "")

        if "TURN_START:" in message:
            return True, "start"
        elif "TURN_END:" in message:
            return True, "end"

        return False, None

    def _handle_turn_marker(self, marker_type: str, state: ParserState) -> None:
        """Handle turn start/end markers."""
        if marker_type == "start":
            state.in_turn = True
            state.current_turn_tools = []
        elif marker_type == "end":
            state.all_turns.append(state.current_turn_tools)
            state.in_turn = False
            state.current_turn_tools = []

    def _is_completion_response(self, entry: dict) -> bool:
        """Check if entry is an OpenAI completion response."""
        message = entry.get("message", "")
        return "OpenAI completion response" in message

    def _extract_tool_calls(self, entry: dict) -> list[dict[str, Any]]:
        """Extract tool calls from OpenAI completion response."""
        tool_calls_list = []

        data = entry.get("data", {}).get("data", {})
        choices = data.get("choices", [])

        for choice in choices:
            msg = choice.get("message", {})
            tool_calls = msg.get("tool_calls")

            if not tool_calls:
                continue

            for tc in tool_calls:
                func = tc.get("function", {})
                name = self._clean_function_name(func.get("name", ""))
                args = self._parse_arguments(func.get("arguments", "{}"))

                tool_calls_list.append({"function": name, "arguments": args})

        return tool_calls_list

    def _clean_function_name(self, name: str) -> str:
        """Remove server prefix from function name."""
        if "-" in name:
            return name.split("-", 1)[-1]
        return name

    def _parse_arguments(self, args_str: str) -> dict:
        """Parse JSON arguments string."""
        try:
            return json.loads(args_str)
        except json.JSONDecodeError:
            return {}


def parse_jsonl(log_path: str) -> list[list[dict[str, Any]]]:
    """
    Parse JSONL log and extract tool calls by turn.

    Backward compatibility wrapper for JsonlParser.

    Args:
        log_path: Path to the JSONL log file

    Returns:
        List of turns, where each turn is a list of tool call dictionaries
    """
    parser = JsonlParser()
    return parser.parse_file(log_path)


def format_to_executable(tool_calls: list[list[dict[str, Any]]]) -> list[list[str]]:
    """
    Convert tool calls to BFCL executable format.

    Args:
        tool_calls: List of turns with tool call dictionaries

    Returns:
        List of turns with executable string format
    """
    result = []

    for turn in tool_calls:
        turn_calls = []
        for call in turn:
            # Format arguments as Python function call
            args_list = []
            for key, value in call["arguments"].items():
                args_list.append(f"{key}={repr(value)}")
            args_str = ", ".join(args_list)

            # Create executable format
            turn_calls.append(f"{call['function']}({args_str})")

        result.append(turn_calls)

    return result


def parse_and_format(log_path: str) -> tuple[list[list[dict[str, Any]]], list[list[str]]]:
    """
    Parse JSONL log and return both raw and executable formats.

    Args:
        log_path: Path to the JSONL log file

    Returns:
        Tuple of (raw_tool_calls, executable_format)
    """
    tool_calls = parse_jsonl(log_path)
    executable = format_to_executable(tool_calls)
    return tool_calls, executable
