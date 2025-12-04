"""
Structured event logger for better JSONL logs.

This module provides structured, typed events instead of the current
approach of grepping for magic strings in mixed debug logs.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any


class StructuredEventLogger:
    """
    Structured logger for typed, searchable events.

    Each event is properly typed and searchable, making it much easier
    to extract and analyze specific events.
    """

    def __init__(self, log_path: Path):
        """
        Initialize the structured event logger.

        Args:
            log_path: Path where the structured JSONL log will be written
        """
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        # Clear existing log for fresh start
        if self.log_path.exists():
            self.log_path.unlink()

    def _write_event(self, event: dict[str, Any]) -> None:
        """
        Write a single structured event to JSONL.

        Args:
            event: Event dictionary to write
        """
        event["timestamp"] = datetime.now().isoformat()
        with open(self.log_path, "a") as f:
            f.write(json.dumps(event) + "\n")

    def log_turn(self, turn_id: int, phase: str, user_message: str | None = None) -> None:
        """
        Log turn start/end with proper structure.

        Args:
            turn_id: The turn number
            phase: Either "start" or "end"
            user_message: The user's message (only for start phase)
        """
        event = {"type": "turn", "turn_id": turn_id, "phase": phase}
        if user_message and phase == "start":
            event["user_message"] = user_message
        self._write_event(event)

    def log_tool_call(self, turn_id: int, tool_name: str, arguments: dict[str, Any], tool_id: str) -> None:
        """
        Log a tool call with full details.

        Args:
            turn_id: The turn number
            tool_name: Name of the tool being called
            arguments: Arguments passed to the tool
            tool_id: Unique identifier for this tool call
        """
        event = {
            "type": "tool_call",
            "turn_id": turn_id,
            "tool_name": tool_name,
            "arguments": arguments,
            "tool_id": tool_id,
        }
        self._write_event(event)

    def log_tool_result(self, turn_id: int, tool_id: str, result: Any, is_error: bool = False) -> None:
        """
        Log a tool result.

        Args:
            turn_id: The turn number
            tool_id: Identifier matching the tool call
            result: The result from the tool
            is_error: Whether the result is an error
        """
        event = {
            "type": "tool_result",
            "turn_id": turn_id,
            "tool_id": tool_id,
            "result": str(result) if not isinstance(result, (dict, list)) else result,
            "is_error": is_error,
        }
        self._write_event(event)

    def log_assistant_response(self, turn_id: int, text: str) -> None:
        """
        Log assistant text response.

        Args:
            turn_id: The turn number
            text: The assistant's text response
        """
        event = {"type": "assistant_text", "turn_id": turn_id, "text": text}
        self._write_event(event)

    def log_elicitation(self, function_name: str, decision: str, params: dict[str, Any] | None = None) -> None:
        """
        Log elicitation decision with structure.

        Args:
            function_name: Name of the function being elicited
            decision: Either "accepted" or "declined"
            params: Parameters if accepted, None if declined
        """
        event: dict[str, Any] = {"type": "elicitation", "function": function_name, "decision": decision}
        if params and decision == "accepted":
            event["params"] = params
        self._write_event(event)

    def log_message_summary(self, messages: list[Any]) -> None:
        """
        Log a summary of all messages for debugging.

        Args:
            messages: List of messages to summarize
        """
        role_counts: dict[str, int] = {}
        tool_call_count = 0
        tool_result_count = 0

        for msg in messages:
            role = str(msg.role)
            role_counts[role] = role_counts.get(role, 0) + 1
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                tool_call_count += len(msg.tool_calls)
            if hasattr(msg, "tool_results") and msg.tool_results:
                tool_result_count += len(msg.tool_results)

        summary: dict[str, Any] = {
            "type": "summary",
            "total_messages": len(messages),
            "role_counts": role_counts,
            "tool_call_count": tool_call_count,
            "tool_result_count": tool_result_count,
        }

        self._write_event(summary)

    # Additional methods for MCP-Universe benchmark support

    def log_execution_summary(
        self, status: str, reason: str, total_tool_calls: int, error_count: int, total_turns: int
    ) -> None:
        """Log execution summary."""
        self._write_event({
            "type": "execution_summary",
            "status": status,
            "reason": reason,
            "total_tool_calls": total_tool_calls,
            "error_count": error_count,
            "total_turns": total_turns,
        })

    def log_evaluation_start(self) -> None:
        """Log evaluation start."""
        self._write_event({"type": "evaluation_start"})

    def log_evaluation_check(
        self,
        check_num: int,
        operation: str,
        passed: bool,
        reason: str = "",
        expected: Any = None,
        actual: Any = None,
    ) -> None:
        """Log evaluation check."""
        event: dict[str, Any] = {
            "type": "evaluation_check",
            "check_num": check_num,
            "operation": operation,
            "passed": passed,
        }
        if reason:
            event["reason"] = reason
        if expected is not None:
            event["expected"] = expected if not isinstance(expected, (dict, list)) else json.dumps(expected)
        if actual is not None:
            event["actual"] = actual if not isinstance(actual, (dict, list)) else json.dumps(actual)
        self._write_event(event)

    def log_evaluation_summary(self, passed: bool, total_checks: int, failed_checks: int) -> None:
        """Log evaluation summary."""
        self._write_event({
            "type": "evaluation_summary",
            "passed": passed,
            "total_checks": total_checks,
            "failed_checks": failed_checks,
        })

    def log_infrastructure_event(
        self, event_type: str, component: str, status: str, details: Any = None
    ) -> None:
        """Log infrastructure event."""
        event: dict[str, Any] = {
            "type": "infrastructure",
            "event_type": event_type,
            "component": component,
            "status": status,
        }
        if details:
            event["details"] = details
        self._write_event(event)

    def log_error_classification(
        self, error_message: str, classification: str, confidence: str, reasoning: str
    ) -> None:
        """Log error classification."""
        self._write_event({
            "type": "error_classification",
            "error_message": error_message,
            "classification": classification,
            "confidence": confidence,
            "reasoning": reasoning,
        })

    def log_error_summary(self, errors: list[dict[str, Any]]) -> None:
        """Log error summary."""
        self._write_event({"type": "error_summary", "errors": errors})

    def log_completion_status(
        self, status: str, reason: str, total_tool_calls: int, error_count: int, final_message: str | None
    ) -> None:
        """Log execution completion status."""
        event: dict[str, Any] = {
            "type": "completion_status",
            "status": status,
            "reason": reason,
            "total_tool_calls": total_tool_calls,
            "error_count": error_count,
        }
        if final_message:
            event["final_message"] = final_message
        self._write_event(event)
