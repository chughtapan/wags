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
    Human-readable logger optimized for manual annotation.

    Design principles:
    - No infrastructure noise (no GitHub auth, FastAgent init logs)
    - Full text, no truncation (task descriptions, tool results, errors)
    - Clear step-by-step narrative
    - Easy to identify failure reasons
    """

    def __init__(self, log_path: Path):
        """Initialize the human-readable logger."""
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        if self.log_path.exists():
            self.log_path.unlink()

        self.start_time = time.time()
        self.turn_start_times: dict[int, float] = {}

    def _write_line(self, text: str = "") -> None:
        """Write a line to the log file."""
        with open(self.log_path, "a") as f:
            f.write(text + "\n")

    def _write_separator(self, char: str = "-", width: int = 80) -> None:
        """Write a separator line."""
        self._write_line(char * width)

    def log_test_start(self, task_id: str, model: str, task_description: str) -> None:
        """Log test initialization with FULL task details."""
        self._write_separator("=")
        self._write_line(f"TEST: {task_id}")
        self._write_line(f"MODEL: {model}")
        self._write_line(f"TIME: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self._write_separator("=")
        self._write_line("")
        self._write_line("TASK DESCRIPTION:")
        self._write_line(task_description)  # FULL description, no truncation
        self._write_line("")
        self._write_separator("=")
        self._write_line("MODEL EXECUTION")
        self._write_separator("=")
        self._write_line("")

    def log_turn_start(self, turn_id: int, user_message: str) -> None:
        """Log the start of a conversation turn."""
        self.turn_start_times[turn_id] = time.time()
        elapsed = time.time() - self.start_time
        self._write_separator("-")
        self._write_line(f"TURN {turn_id} (t={elapsed:.1f}s)")
        self._write_separator("-")
        self._write_line(user_message)  # FULL message, no truncation
        self._write_line("")

    def log_tool_call(self, turn_id: int, tool_name: str, arguments: dict[str, Any]) -> None:
        """Log a tool call with FULL arguments."""
        self._write_line(f"[TOOL] {tool_name}")

        # Show ALL arguments in readable format
        if arguments:
            for key, value in arguments.items():
                # Format multi-line strings nicely
                if isinstance(value, str) and ("\n" in value or len(value) > 80):
                    self._write_line(f"  {key}:")
                    for line in value.split("\n"):
                        self._write_line(f"    {line}")
                else:
                    # Single line values
                    self._write_line(f"  {key}: {value}")

    def log_tool_result(self, turn_id: int, tool_name: str, result: Any, is_error: bool) -> None:
        """Log tool result with truncation for readability."""
        MAX_RESULT_LENGTH = 250  # Truncate long results for readability

        if is_error:
            self._write_line(f"[ERROR] {tool_name}")
            # Show FULL error message
            error_msg = str(result)
            self._write_line(f"  {error_msg}")
        else:
            # Truncate long results
            result_str = str(result)
            if result_str and result_str != "None":
                if len(result_str) > MAX_RESULT_LENGTH:
                    truncated = result_str[:MAX_RESULT_LENGTH] + f"... (truncated, {len(result_str)} total chars)"
                    self._write_line(f"[RESULT] {truncated}")
                else:
                    self._write_line(f"[RESULT] {result_str}")
        self._write_line("")

    def log_assistant_response(self, turn_id: int, text: str) -> None:
        """Log assistant's FULL text response."""
        if text.strip():
            self._write_line("[ASSISTANT]")
            self._write_line(text)  # FULL response, no truncation
            self._write_line("")

    def log_turn_end(self, turn_id: int) -> None:
        """Log end of turn."""
        if turn_id in self.turn_start_times:
            turn_duration = time.time() - self.turn_start_times[turn_id]
            self._write_line(f"(Turn {turn_id} duration: {turn_duration:.1f}s)")
        self._write_line("")

    def log_execution_summary(
        self, status: str, reason: str, total_tool_calls: int, error_count: int, total_turns: int
    ) -> None:
        """Log execution summary."""
        self._write_separator("=")
        self._write_line("EXECUTION SUMMARY")
        self._write_separator("=")
        self._write_line(f"Status: {status.upper()}")
        self._write_line(f"Total Turns: {total_turns}")
        self._write_line(f"Total Tool Calls: {total_tool_calls}")
        self._write_line(f"Tool Errors: {error_count}")
        if reason:
            self._write_line(f"Completion Reason: {reason}")
        self._write_line("")

    def log_errors(self, errors: list[dict[str, Any]]) -> None:
        """Log detailed error summary."""
        if not errors:
            return

        self._write_separator("-")
        self._write_line(f"ERRORS ENCOUNTERED ({len(errors)} total)")
        self._write_separator("-")
        for i, error in enumerate(errors, 1):
            self._write_line(f"{i}. Turn {error['turn_id']}: {error['tool_name']}")
            # Show FULL error message
            self._write_line(f"   {error['error_message']}")
        self._write_line("")

    def log_evaluation_start(self) -> None:
        """Log start of evaluation."""
        self._write_separator("=")
        self._write_line("EVALUATION")
        self._write_separator("=")
        self._write_line("")

    def log_evaluation_check(
        self, check_num: int, operation: str, passed: bool, reason: str = "", expected: Any = None, actual: Any = None
    ) -> None:
        """Log a single evaluation check with FULL details."""
        status_symbol = "✓" if passed else "✗"
        status_text = "PASS" if passed else "FAIL"

        self._write_line(f"{check_num}. [{status_symbol}] {operation} - {status_text}")

        if not passed and reason:
            self._write_line(f"   WHY IT FAILED: {reason}")  # Key for annotation!

        if expected is not None:
            expected_str = self._format_value_full(expected)
            self._write_line(f"   EXPECTED: {expected_str}")

        if actual is not None:
            actual_str = self._format_value_full(actual)
            self._write_line(f"   ACTUAL: {actual_str}")

        if not passed and not reason:
            self._write_line("   (No failure reason provided)")

        self._write_line("")

    def _format_value_full(self, value: Any) -> str:
        """Format a value for display with NO truncation."""
        if isinstance(value, dict):
            return json.dumps(value, indent=2)
        elif isinstance(value, list):
            return json.dumps(value, indent=2)
        return str(value)  # FULL value, no truncation

    def log_evaluation_summary(self, passed: bool, total_checks: int, failed_checks: int) -> None:
        """Log evaluation summary."""
        self._write_separator("=")
        self._write_line("EVALUATION SUMMARY")
        self._write_separator("=")
        result = "PASSED" if passed else "FAILED"
        symbol = "✓" if passed else "✗"
        self._write_line(f"Overall Result: [{symbol}] {result}")
        self._write_line(f"Checks Passed: {total_checks - failed_checks}/{total_checks}")
        if failed_checks > 0:
            self._write_line(f"Checks Failed: {failed_checks}")
        self._write_line("")
        self._write_separator("=")

    def log_final_verdict(self, verdict: str) -> None:
        """Log final verdict."""
        self._write_line("")
        self._write_line(f"FINAL VERDICT: {verdict.upper()}")
        self._write_line("")
        self._write_separator("=")

    def log_infrastructure_event(
        self, event_type: str, component: str, status: str, details: str | None = None
    ) -> None:
        """
        Skip infrastructure events for annotation logs.

        These don't help understand model behavior, so we ignore them.
        """
        pass  # Don't log infrastructure noise

    def log_error_classification(
        self, error_message: str, classification: str, confidence: str, reasoning: str
    ) -> None:
        """Skip error classification for annotation logs."""
        pass  # Don't log this either


class StructuredEventLogger:
    """
    Structured logger for typed, searchable events in JSONL format.

    This creates machine-readable logs for automated analysis.
    Separate from human-readable logs which are for manual annotation.
    """

    def __init__(self, log_path: Path):
        """Initialize the structured logger."""
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        if self.log_path.exists():
            self.log_path.unlink()

        self.start_time = time.time()
        self.turn_start_times: dict[int, float] = {}
        self.current_turn: int | None = None

    def _write_event(self, event: dict[str, Any]) -> None:
        """Write a structured event as JSONL."""
        event["timestamp"] = time.time()
        event["elapsed"] = time.time() - self.start_time
        with open(self.log_path, "a") as f:
            f.write(json.dumps(event) + "\n")

    def log_turn(self, turn_id: int, event_type: str, message: str | None = None) -> None:
        """Log a turn event."""
        if event_type == "start":
            self.current_turn = turn_id
            self.turn_start_times[turn_id] = time.time()

        event = {
            "event": "turn",
            "turn_id": turn_id,
            "type": event_type,
        }
        if message:
            event["message"] = message

        if event_type == "end" and turn_id in self.turn_start_times:
            event["duration"] = time.time() - self.turn_start_times[turn_id]

        self._write_event(event)

    def log_tool_call(self, turn_id: int, tool_name: str, arguments: dict[str, Any], tool_id: str) -> None:
        """Log a tool call."""
        self._write_event(
            {
                "event": "tool_call",
                "turn_id": turn_id,
                "tool_name": tool_name,
                "tool_id": tool_id,
                "arguments": arguments,
            }
        )

    def log_tool_result(self, turn_id: int, tool_id: str, result: Any, is_error: bool) -> None:
        """Log a tool result."""
        self._write_event(
            {
                "event": "tool_result",
                "turn_id": turn_id,
                "tool_id": tool_id,
                "result": result if not isinstance(result, (dict, list)) else json.dumps(result),
                "is_error": is_error,
            }
        )

    def log_assistant_response(self, turn_id: int, text: str) -> None:
        """Log assistant response."""
        self._write_event({"event": "assistant_response", "turn_id": turn_id, "text": text})

    def log_message_summary(self, messages: list[Any]) -> None:
        """Log message summary."""
        self._write_event({"event": "message_summary", "total_messages": len(messages)})

    def log_error_summary(self, errors: list[dict[str, Any]]) -> None:
        """Log error summary."""
        self._write_event({"event": "error_summary", "errors": errors})

    def log_execution_summary(
        self, status: str, reason: str, total_tool_calls: int, error_count: int, total_turns: int
    ) -> None:
        """Log execution summary."""
        self._write_event(
            {
                "event": "execution_summary",
                "status": status,
                "reason": reason,
                "total_tool_calls": total_tool_calls,
                "error_count": error_count,
                "total_turns": total_turns,
            }
        )

    def log_evaluation_start(self) -> None:
        """Log evaluation start."""
        self._write_event({"event": "evaluation_start"})

    def log_evaluation_check(
        self, check_num: int, operation: str, passed: bool, reason: str = "", expected: Any = None, actual: Any = None
    ) -> None:
        """Log evaluation check."""
        event: dict[str, Any] = {
            "event": "evaluation_check",
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
        self._write_event(
            {
                "event": "evaluation_summary",
                "passed": passed,
                "total_checks": total_checks,
                "failed_checks": failed_checks,
            }
        )

    def log_infrastructure_event(self, event_type: str, component: str, status: str, details: Any = None) -> None:
        """Log infrastructure event."""
        event: dict[str, Any] = {
            "event": "infrastructure",
            "type": event_type,
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
        self._write_event(
            {
                "event": "error_classification",
                "error_message": error_message,
                "classification": classification,
                "confidence": confidence,
                "reasoning": reasoning,
            }
        )

    def log_elicitation(self, func_name: str, action: str, params: dict[str, Any] | None) -> None:
        """Log parameter elicitation event."""
        event: dict[str, Any] = {"event": "elicitation", "func_name": func_name, "action": action}
        if params:
            event["params"] = params
        self._write_event(event)

    def log_completion_status(
        self, status: str, reason: str, total_tool_calls: int, error_count: int, final_message: str | None
    ) -> None:
        """Log execution completion status."""
        event: dict[str, Any] = {
            "event": "completion_status",
            "status": status,
            "reason": reason,
            "total_tool_calls": total_tool_calls,
            "error_count": error_count,
        }
        if final_message:
            event["final_message"] = final_message
        self._write_event(event)
