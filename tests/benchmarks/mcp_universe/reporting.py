"""Human-readable logging for MCP-Universe benchmark results."""

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
        self,
        check_num: int,
        operation: str,
        passed: bool,
        reason: str = "",
        expected: Any = None,
        actual: Any = None,
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
