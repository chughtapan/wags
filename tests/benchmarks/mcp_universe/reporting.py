"""Human-readable logging for MCP-Universe benchmark results."""

import json
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


def _determine_completion_status(
    total_tool_calls: int, errors: list[dict[str, Any]], max_iterations: int = 500
) -> tuple[str, str]:
    """Determine completion status and reason based on execution results."""
    if total_tool_calls >= max_iterations:
        return "max_iterations", f"Agent reached maximum iteration limit ({total_tool_calls} tool calls)"
    if errors:
        return "completed", f"Agent completed with {len(errors)} recoverable error(s) during execution"
    return "completed", "Agent completed all requested tasks"


@dataclass
class EvaluationCheck:
    """Result of a single evaluation check."""

    check_num: int
    operation: str
    passed: bool
    reason: str = ""
    expected: Any = None
    actual: Any = None


class HumanReadableLogger:
    """
    Human-readable logger optimized for manual annotation.

    Design principles:
    - No infrastructure noise (no GitHub auth, FastAgent init logs)
    - Full text, no truncation (task descriptions, tool results, errors)
    - Clear step-by-step narrative
    - Easy to identify failure reasons
    """

    def __init__(self, log_path: Path, *, append: bool = False):
        """Initialize the human-readable logger."""
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        if not append and self.log_path.exists():
            self.log_path.unlink()

        self.start_time = time.time()
        self.turn_start_times: dict[int, float] = {}

    @classmethod
    def from_structured_log(
        cls,
        output_path: Path,
        structured_path: Path,
        test_id: str,
        model: str,
        task_description: str,
    ) -> "HumanReadableLogger":
        """Generate human-readable log by replaying structured events."""
        logger = cls(output_path)
        logger.log_test_start(test_id, model, task_description)

        stats = logger._replay_events(structured_path)

        if stats["errors"]:
            logger.log_errors(stats["errors"])

        status, reason = _determine_completion_status(stats["total_tool_calls"], stats["errors"])
        logger.log_execution_summary(
            status=status,
            reason=reason,
            total_tool_calls=stats["total_tool_calls"],
            error_count=len(stats["errors"]),
            total_turns=stats["total_turns"],
        )

        return logger

    def _replay_events(self, structured_path: Path) -> dict[str, Any]:
        """Replay structured events and return execution stats."""
        tool_names: dict[str, str] = {}
        errors: list[dict[str, Any]] = []
        turn_timestamps: dict[int, datetime] = {}
        first_timestamp: datetime | None = None
        total_tool_calls = 0
        total_turns = 0

        with open(structured_path, encoding="utf-8") as f:
            for line in f:
                event = json.loads(line)
                timestamp = datetime.fromisoformat(event["timestamp"])
                if first_timestamp is None:
                    first_timestamp = timestamp

                event_type = event["type"]
                if event_type == "turn":
                    total_turns += self._replay_turn_event(event, timestamp, first_timestamp, turn_timestamps)
                elif event_type == "tool_call":
                    total_tool_calls += 1
                    tool_names[event["tool_id"]] = event["tool_name"]
                    self.log_tool_call(event["turn_id"], event["tool_name"], event["arguments"])
                elif event_type == "tool_result":
                    self._replay_tool_result(event, tool_names, errors)
                elif event_type == "assistant_text":
                    self.log_assistant_response(event["turn_id"], event["text"])

        return {"errors": errors, "total_tool_calls": total_tool_calls, "total_turns": total_turns}

    def _replay_turn_event(
        self,
        event: dict[str, Any],
        timestamp: datetime,
        first_timestamp: datetime,
        turn_timestamps: dict[int, datetime],
    ) -> int:
        """Replay a turn event. Returns 1 if turn start, 0 otherwise."""
        turn_id = event["turn_id"]
        if event["phase"] == "start":
            turn_timestamps[turn_id] = timestamp
            elapsed = (timestamp - first_timestamp).total_seconds()
            self._log_turn_start_with_elapsed(turn_id, event.get("user_message", ""), elapsed)
            return 1
        else:
            start_ts = turn_timestamps.get(turn_id)
            duration = (timestamp - start_ts).total_seconds() if start_ts else 0
            self._log_turn_end_with_duration(turn_id, duration)
            return 0

    def _replay_tool_result(
        self, event: dict[str, Any], tool_names: dict[str, str], errors: list[dict[str, Any]]
    ) -> None:
        """Replay a tool result event, tracking errors."""
        tool_name = tool_names.get(event["tool_id"], "unknown")
        self.log_tool_result(event["turn_id"], tool_name, event["result"], event["is_error"])
        if event["is_error"]:
            errors.append(
                {
                    "turn_id": event["turn_id"],
                    "tool_id": event["tool_id"],
                    "tool_name": tool_name,
                    "error_message": str(event["result"]),
                }
            )

    def _log_turn_start_with_elapsed(self, turn_id: int, user_message: str, elapsed: float) -> None:
        """Log turn start with pre-calculated elapsed time (for replay)."""
        self._write_separator("-")
        self._write_line(f"TURN {turn_id} (t={elapsed:.1f}s)")
        self._write_separator("-")
        self._write_line(user_message)
        self._write_line("")

    def _log_turn_end_with_duration(self, turn_id: int, duration: float) -> None:
        """Log turn end with pre-calculated duration (for replay)."""
        self._write_line(f"(Turn {turn_id} duration: {duration:.1f}s)")
        self._write_line("")

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

    def log_evaluation_check(self, check: EvaluationCheck) -> None:
        """Log a single evaluation check with FULL details."""
        status_symbol = "✓" if check.passed else "✗"
        status_text = "PASS" if check.passed else "FAIL"

        self._write_line(f"{check.check_num}. [{status_symbol}] {check.operation} - {status_text}")

        if not check.passed and check.reason:
            self._write_line(f"   WHY IT FAILED: {check.reason}")  # Key for annotation!

        if check.expected is not None:
            expected_str = self._format_value_full(check.expected)
            self._write_line(f"   EXPECTED: {expected_str}")

        if check.actual is not None:
            actual_str = self._format_value_full(check.actual)
            self._write_line(f"   ACTUAL: {actual_str}")

        if not check.passed and not check.reason:
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
