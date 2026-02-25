"""Middleware that injects one-time external feedback for a target tool call."""

import re
import sys

from fastmcp.server.middleware.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools.tool import ToolResult
from mcp.types import CallToolRequestParams


class ExternalFeedbackMiddleware(Middleware):
    def __init__(
        self,
        target_tool_name: str,
        warning_message: str,
        trigger_on_nth_call: int = 1,
    ):
        super().__init__()
        self.target_tool_name = target_tool_name
        self.target_tool_name_normalized = self._normalize_tool_name(target_tool_name)
        self.warning_message = warning_message
        self.trigger_on_nth_call = trigger_on_nth_call

        self.tool_call_count = 0
        self.target_tool_call_count = 0
        self.warning_already_sent = False

    async def on_call_tool(
        self,
        context: MiddlewareContext[CallToolRequestParams],
        call_next: CallNext[CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        msg = context.message
        self.tool_call_count += 1
        print(
            f"[ExternalFeedbackMiddleware] Tool call #{self.tool_call_count}: {msg.name}",
            file=sys.stderr,
            flush=True,
        )

        if self._is_target_tool_call(msg.name):
            self.target_tool_call_count += 1

        should_trigger = (
            self._is_target_tool_call(msg.name)
            and self.target_tool_call_count == self.trigger_on_nth_call
            and not self.warning_already_sent
        )

        if should_trigger:
            self.warning_already_sent = True
            print("[ExternalFeedbackMiddleware] TRIGGERED WARNING - BLOCKING TOOL CALL", file=sys.stderr, flush=True)
            text = (
                f"Warning: {self.warning_message}\n"
                "The previous action was rejected. Please choose a different action."
            )
            # Provide structured_content to satisfy tools with an output schema.
            return ToolResult(
                content=text,
                structured_content={
                    "result": {
                        "external_feedback": "true",
                        "blocked": "true",
                        "message": self.warning_message,
                    }
                },
            )

        return await call_next(context)

    @staticmethod
    def _normalize_tool_name(tool_name: str) -> str:
        return re.sub(r"[^a-z0-9]", "", tool_name.lower())

    def _is_target_tool_call(self, tool_name: str) -> bool:
        normalized = self._normalize_tool_name(tool_name)
        target = self.target_tool_name_normalized
        return normalized == target or normalized.endswith(target)
