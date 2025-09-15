#!/usr/bin/env python3
"""
Elicitation handler for BFCL test execution.
Provides ground truth-based elicitation for complex fields.
"""

import ast
from typing import TYPE_CHECKING, Any

from mcp.shared.context import RequestContext
from mcp.types import ElicitRequestParams, ElicitResult

if TYPE_CHECKING:
    from mcp.client.session import ClientSession


class GroundTruthElicitationHandler:
    """Handler for elicitation based on ground truth data."""

    def __init__(self, ground_truth_data: list[list[str]], structured_logger=None):
        """
        Initialize the elicitation handler.

        Args:
            ground_truth_data: List of turns with function calls
            structured_logger: Optional structured logger for event tracking
        """
        self.ground_truth_data = ground_truth_data
        self.structured_logger = structured_logger
        self.function_counters = {}

    def parse_function_call(self, call_str: str) -> dict[str, Any] | None:
        """
        Parse function call string using AST.

        Args:
            call_str: Function call string to parse

        Returns:
            Dict with 'function' and 'params' keys, or None if parsing fails
        """
        try:
            # Parse the function call as a Python expression
            tree = ast.parse(call_str, mode="eval")
            call_node = tree.body

            if not isinstance(call_node, ast.Call):
                return None

            if isinstance(call_node.func, ast.Name):
                func_name = call_node.func.id
            elif isinstance(call_node.func, ast.Attribute):
                func_name = call_node.func.attr
            else:
                return None

            params = {}
            for keyword in call_node.keywords:
                key = keyword.arg
                value = ast.literal_eval(keyword.value)
                params[key] = value

            return {"function": func_name, "params": params}

        except (SyntaxError, ValueError):
            return None

    def extract_function_name(self, message: str) -> str:
        """
        Extract function name from elicitation message.

        Args:
            message: Format "ClassName:function_name"

        Returns:
            Function name
        """
        if ":" in message:
            _, func_name = message.rsplit(":", 1)
            return func_name
        return message

    def find_matching_call(self, func_name: str, occurrence: int) -> dict[str, Any] | None:
        """
        Find the Nth occurrence of a function in ground truth data.

        Args:
            func_name: Name of the function to find
            occurrence: Which occurrence to find (0-indexed)

        Returns:
            Parsed function call or None
        """
        matches_found = 0

        for turn in self.ground_truth_data:
            for call_str in turn:
                parsed = self.parse_function_call(call_str)
                if not parsed:
                    continue

                if parsed["function"] == func_name:
                    if matches_found == occurrence:
                        return parsed
                    matches_found += 1

        return None

    def filter_text_params(self, params: dict[str, Any]) -> dict[str, str]:
        """
        Filter parameters to only include text/string values.

        Args:
            params: Function parameters

        Returns:
            Dict containing only string parameters
        """
        return {k: v for k, v in params.items() if isinstance(v, str)}

    def find_ground_truth_params(self, message: str) -> dict[str, str] | None:
        """
        Find matching parameters from ground truth data.

        Args:
            message: Format "ClassName:function_name"

        Returns:
            Dict of text parameters from ground truth, or None
        """
        if not self.ground_truth_data:
            return None

        func_name = self.extract_function_name(message)

        # Get current count for this function (0-indexed)
        current_count = self.function_counters.get(func_name, 0)

        # Find the matching function call
        parsed = self.find_matching_call(func_name, current_count)

        if parsed:
            # Increment counter for next time
            self.function_counters[func_name] = current_count + 1

            # Filter to only text parameters
            text_params = self.filter_text_params(parsed["params"])

            if text_params:
                return text_params

        return None

    async def handle(
        self,
        context: RequestContext["ClientSession", Any],
        params: ElicitRequestParams,
    ) -> ElicitResult:
        """
        Handle elicitation request by matching against ground truth.

        Args:
            context: Request context
            params: Elicitation parameters

        Returns:
            ElicitResult with action and content
        """
        message = params.message

        # Find matching parameters from ground truth
        ground_truth_params = self.find_ground_truth_params(message)

        if ground_truth_params:
            func_name = self.extract_function_name(message)
            if self.structured_logger:
                self.structured_logger.log_elicitation(
                    func_name, "accepted", ground_truth_params
                )
            return ElicitResult(action="accept", content=ground_truth_params)

        # No matching function found or no text params
        func_name = self.extract_function_name(message)
        if self.structured_logger:
            self.structured_logger.log_elicitation(
                func_name, "declined", None
            )
        return ElicitResult(action="decline")


def create_elicitation_handler(ground_truth_data: list[list[str]], structured_logger=None):
    """
    Factory function to create an elicitation handler.

    Args:
        ground_truth_data: Ground truth data from BFCL
        structured_logger: Optional structured logger for event tracking

    Returns:
        Async handler function for elicitation
    """
    handler = GroundTruthElicitationHandler(ground_truth_data, structured_logger)
    return handler.handle
