"""
Structured event logger for better JSONL logs.

This module provides structured, typed events instead of the current
approach of grepping for magic strings in mixed debug logs.
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any


class HumanReadableLogger:
    """
    Human-readable logger that writes detailed, formatted logs for debugging.

    This logger creates easy-to-read log files that help understand:
    - What the agent was asked to do
    - What actions it took
    - What went wrong and why
    - What the evaluation expected vs what was created
    """

    def __init__(self, log_path: Path):
        """
        Initialize the human-readable logger.

        Args:
            log_path: Path where the human-readable log will be written
        """
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        # Clear existing log for fresh start
        if self.log_path.exists():
            self.log_path.unlink()

        self.start_time = time.time()
        self.turn_start_times: dict[int, float] = {}

        self._write_separator("=")
        self._write_line("MCP-UNIVERSE TEST EXECUTION LOG")
        self._write_line(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self._write_separator("=")
        self._write_line("")

    def _write_line(self, text: str = "") -> None:
        """Write a line to the log file."""
        with open(self.log_path, "a") as f:
            f.write(text + "\n")

    def _write_separator(self, char: str = "-", width: int = 80) -> None:
        """Write a separator line."""
        self._write_line(char * width)

    def log_test_start(self, task_id: str, model: str, task_description: str) -> None:
        """Log test initialization with task details."""
        self._write_separator("=")
        self._write_line("TEST INITIALIZATION")
        self._write_separator("=")
        self._write_line(f"Task ID: {task_id}")
        self._write_line(f"Model: {model}")
        self._write_line("")
        self._write_line("TASK DESCRIPTION:")
        self._write_line(task_description[:500] + "..." if len(task_description) > 500 else task_description)
        self._write_line("")

    def log_turn_start(self, turn_id: int, user_message: str) -> None:
        """Log the start of a conversation turn."""
        self.turn_start_times[turn_id] = time.time()
        elapsed = time.time() - self.start_time
        self._write_separator("=")
        self._write_line(f"TURN {turn_id} (elapsed: {elapsed:.2f}s)")
        self._write_separator("=")
        self._write_line(f"User Request: {user_message[:200]}...")
        self._write_line("")

    def log_tool_call(self, turn_id: int, tool_name: str, arguments: dict[str, Any]) -> None:
        """Log a tool call with formatted arguments."""
        self._write_line(f"  [TOOL CALL] {tool_name}")
        # Format key arguments for readability
        if "owner" in arguments and "repo" in arguments:
            self._write_line(f"    → Repository: {arguments['owner']}/{arguments['repo']}")
        if "path" in arguments:
            self._write_line(f"    → Path: {arguments['path']}")
        if "branch" in arguments:
            self._write_line(f"    → Branch: {arguments['branch']}")
        if "query" in arguments:
            self._write_line(f"    → Query: {arguments['query']}")
        if "title" in arguments:
            self._write_line(f"    → Title: {arguments['title']}")
        if "base" in arguments and "head" in arguments:
            self._write_line(f"    → Merge: {arguments['head']} → {arguments['base']}")

    def log_tool_result(self, turn_id: int, tool_name: str, result: Any, is_error: bool) -> None:
        """Log a tool result."""
        if is_error:
            self._write_line(f"  [ERROR] {tool_name} failed:")
            error_msg = str(result)[:300]
            self._write_line(f"    ✗ {error_msg}")
        else:
            result_str = str(result)
            if len(result_str) > 200:
                result_str = result_str[:200] + "..."
            self._write_line(f"  [SUCCESS] {tool_name}")
            if result_str and result_str != "None":
                self._write_line(f"    ✓ {result_str}")

    def log_assistant_response(self, turn_id: int, text: str) -> None:
        """Log assistant's text response."""
        if text.strip():
            self._write_line(f"  [ASSISTANT] {text[:300]}...")

    def log_turn_end(self, turn_id: int) -> None:
        """Log end of turn."""
        if turn_id in self.turn_start_times:
            turn_duration = time.time() - self.turn_start_times[turn_id]
            self._write_line(f"  [Turn {turn_id} completed in {turn_duration:.2f}s]")
        self._write_line("")

    def log_execution_summary(
        self,
        status: str,
        reason: str,
        total_tool_calls: int,
        error_count: int,
        total_turns: int
    ) -> None:
        """Log execution summary."""
        self._write_separator("=")
        self._write_line("EXECUTION SUMMARY")
        self._write_separator("=")
        self._write_line(f"Status: {status.upper()}")
        self._write_line(f"Reason: {reason}")
        self._write_line(f"Total Turns: {total_turns}")
        self._write_line(f"Total Tool Calls: {total_tool_calls}")
        self._write_line(f"Errors: {error_count}")
        self._write_line("")

    def log_errors(self, errors: list[dict[str, Any]]) -> None:
        """Log detailed error summary."""
        if not errors:
            return

        self._write_separator("=")
        self._write_line("ERROR DETAILS")
        self._write_separator("=")
        for i, error in enumerate(errors, 1):
            self._write_line(f"{i}. Turn {error['turn_id']}: {error['tool_name']}")
            self._write_line(f"   Error: {error['error_message']}")
        self._write_line("")

    def log_evaluation_start(self) -> None:
        """Log start of evaluation."""
        self._write_separator("=")
        self._write_line("EVALUATION")
        self._write_separator("=")

    def log_evaluation_check(
        self,
        check_num: int,
        operation: str,
        passed: bool,
        reason: str = "",
        expected: Any = None,
        actual: Any = None
    ) -> None:
        """Log a single evaluation check."""
        status = "✓ PASS" if passed else "✗ FAIL"
        self._write_line(f"{check_num}. {operation}: {status}")

        if not passed and reason:
            self._write_line(f"   Reason: {reason}")

        if expected is not None:
            self._write_line(f"   Expected: {self._format_value(expected)}")

        if actual is not None:
            self._write_line(f"   Actual: {self._format_value(actual)}")

        if not passed and not reason:
            self._write_line(f"   No additional details available")

        self._write_line("")

    def _format_value(self, value: Any) -> str:
        """Format a value for display."""
        if isinstance(value, dict):
            if "owner" in value and "repo" in value:
                return f"File from {value['owner']}/{value['repo']}/{value.get('path', '')}"
            return str(value)[:200]
        return str(value)[:200]

    def log_evaluation_summary(self, passed: bool, total_checks: int, failed_checks: int) -> None:
        """Log evaluation summary."""
        self._write_separator("=")
        self._write_line("EVALUATION SUMMARY")
        self._write_separator("=")
        self._write_line(f"Overall: {'✓ PASSED' if passed else '✗ FAILED'}")
        self._write_line(f"Checks Passed: {total_checks - failed_checks}/{total_checks}")
        if failed_checks > 0:
            self._write_line(f"Checks Failed: {failed_checks}")
        self._write_line("")
        self._write_separator("=")

    def log_final_verdict(self, verdict: str) -> None:
        """Log final verdict."""
        self._write_line("")
        self._write_line(f"FINAL VERDICT: {verdict}")
        self._write_line("")
        self._write_separator("=")

    def log_infrastructure_event(
        self,
        event_type: str,
        component: str,
        status: str,
        details: str | None = None
    ) -> None:
        """Log infrastructure events."""
        self._write_separator("-")
        self._write_line(f"[INFRASTRUCTURE] {event_type.upper()}")
        self._write_line(f"Component: {component}")
        self._write_line(f"Status: {status}")
        if details:
            self._write_line(f"Details: {details}")
        self._write_line("")

    def log_error_classification(
        self,
        error_message: str,
        classification: str,
        confidence: str,
        reasoning: str
    ) -> None:
        """Log error classification."""
        self._write_separator("-")
        self._write_line(f"[ERROR CLASSIFICATION]")
        self._write_line(f"Type: {classification.upper()}")
        self._write_line(f"Confidence: {confidence}")
        self._write_line(f"Error: {error_message[:200]}")
        self._write_line(f"Reasoning: {reasoning}")
        self._write_line("")


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

    def log_completion_status(
        self,
        status: str,
        reason: str | None = None,
        total_tool_calls: int = 0,
        error_count: int = 0,
        final_message: str | None = None
    ) -> None:
        """
        Log the completion status of the agent run.

        Args:
            status: One of "completed", "max_iterations", "error"
            reason: Human-readable reason for stopping
            total_tool_calls: Total number of tool calls made
            error_count: Number of tool calls that resulted in errors
            final_message: The agent's final message (if any)
        """
        event: dict[str, Any] = {
            "type": "completion_status",
            "status": status,
            "total_tool_calls": total_tool_calls,
            "error_count": error_count,
        }
        if reason:
            event["reason"] = reason
        if final_message:
            event["final_message"] = final_message
        self._write_event(event)

    def log_error_summary(self, errors: list[dict[str, Any]]) -> None:
        """
        Log a summary of all errors encountered.

        Args:
            errors: List of error dictionaries with tool_name, error_message, turn_id
        """
        if errors:
            event = {
                "type": "error_summary",
                "error_count": len(errors),
                "errors": errors,
            }
            self._write_event(event)

    def log_infrastructure_event(
        self,
        event_type: str,
        component: str,
        status: str,
        details: dict[str, Any] | None = None
    ) -> None:
        """
        Log infrastructure-related events for debugging system issues.

        Args:
            event_type: Type of infrastructure event (e.g., "docker_start", "mcp_connection", "github_auth")
            component: Component involved (e.g., "github-mcp-server", "docker", "github-api")
            status: Status of the event (e.g., "started", "connected", "failed", "rate_limited")
            details: Additional details about the event
        """
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
        self,
        error_message: str,
        classification: str,
        confidence: str,
        reasoning: str
    ) -> None:
        """
        Log error classification to distinguish infrastructure vs model issues.

        Args:
            error_message: The error message
            classification: "infrastructure" or "model_failure"
            confidence: "high", "medium", or "low"
            reasoning: Explanation of why it was classified this way
        """
        event = {
            "type": "error_classification",
            "error_message": error_message[:500],
            "classification": classification,
            "confidence": confidence,
            "reasoning": reasoning,
        }
        self._write_event(event)
