"""Middleware that injects one-time external feedback for a target tool call."""

from typing import Any
import re

from fastmcp.server.middleware.middleware import CallNext, Middleware, MiddlewareContext
from mcp.types import CallToolRequestParams


class ExternalFeedbackMiddleware(Middleware):
    """
    Experimental middleware for injecting external feedback (warnings)
    when a known-bad tool call is attempted.

    Behavior:
    - Intercepts a specific tool call
    - Blocks execution ONCE
    - Returns a warning message as tool output
    - Allows the next attempt to pass through
    """

    def __init__(
        self,
        target_tool_name: str,
        warning_message: str,
        trigger_on_nth_call: int = 1,
    ):
        """
        Args:
            target_tool_name: tool to intercept (e.g. "start_engine")
            warning_message: text returned to the agent
            trigger_on_nth_call: which tool call index to trigger on (1 = first)
        """
        super().__init__()
        self.target_tool_name = target_tool_name
        self.target_tool_name_normalized = self._normalize_tool_name(target_tool_name)
        self.warning_message = warning_message
        self.trigger_on_nth_call = trigger_on_nth_call

        # Episode-local state
        self.tool_call_count = 0
        self.target_tool_call_count = 0
        self.warning_already_sent = False
        
        print("[ExternalFeedbackMiddleware] CONSTRUCTOR CALLED")

    async def on_call_tool(
        self,
        context: MiddlewareContext[CallToolRequestParams],
        call_next: CallNext[CallToolRequestParams, Any],
    ) -> Any:
        """
        Intercept tool calls before execution.
        """
        message = context.message
        self.tool_call_count += 1

        # Print every tool call to make middleware behavior visible during eval runs.
        print(
            f"[ExternalFeedbackMiddleware] Tool call #{self.tool_call_count}: {message.name}"
        )

        if self._is_target_tool_call(message.name):
            self.target_tool_call_count += 1

        should_trigger = (
            self._is_target_tool_call(message.name)
            and self.target_tool_call_count == self.trigger_on_nth_call
            and not self.warning_already_sent
        )

        if should_trigger:
            self.warning_already_sent = True

            print(
                "[ExternalFeedbackMiddleware] TRIGGERED WARNING - BLOCKING TOOL CALL"
            )

            # Block execution by not calling call_next; return synthetic tool output.
            return (
                "EXTERNAL FEEDBACK TRIGGERED\n\n"
                f"{self.warning_message}\n\n"
                "You MUST choose a different action. "
                "This tool call was intentionally blocked for this experiment."
            )

        # Otherwise, allow normal execution
        return await call_next(context)

    @staticmethod
    def _normalize_tool_name(tool_name: str) -> str:
        """Normalize tool names to match across naming conventions."""
        return re.sub(r"[^a-z0-9]", "", tool_name.lower())

    def _is_target_tool_call(self, tool_name: str) -> bool:
        """Match direct, namespaced, and case/underscore variants."""
        normalized = self._normalize_tool_name(tool_name)
        target = self.target_tool_name_normalized
        return normalized == target or normalized.endswith(target)
