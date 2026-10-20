"""Middleware for parameter elicitation during tool execution.

Enables user intervention when parameters are marked with RequiresElicitation.
"""

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastmcp.exceptions import ToolError
from fastmcp.server.context import Context
from fastmcp.server.elicitation import (
    AcceptedElicitation,
    CancelledElicitation,
    DeclinedElicitation,
    handle_elicit_accept,
    parse_elicit_response_type,
)
from fastmcp.server.middleware.middleware import MiddlewareContext
from fastmcp.tools import InputRequiredToolResult
from mcp.server.session import ServerSession
from mcp.types import (
    CallToolRequestParams,
    ElicitRequest,
    ElicitRequestFormParams,
    ElicitResult,
    InputRequiredResult,
    InputResponse,
)
from mcp.types.version import MODERN_PROTOCOL_VERSIONS
from pydantic import BaseModel, Field, create_model

from .base import WagsMiddlewareBase

ElicitationOutcome = AcceptedElicitation[Any] | DeclinedElicitation | CancelledElicitation

ELICITATION_MESSAGE = "Please provide the required information"

# Key for the elicitation request in InputRequiredResult.input_requests
ELICITATION_INPUT_KEY = "wags/elicitation"


@dataclass
class RequiresElicitation:
    """Marks a parameter for user review before tool execution.

    Args:
        prompt: Message shown to the user describing the parameter
    """

    prompt: str

    def __post_init__(self) -> None:
        """Validate configuration."""
        if not self.prompt:
            raise ValueError("Elicitation prompt is required")


class ElicitationMiddleware(WagsMiddlewareBase):
    """Triggers elicitation dialogs for marked parameters.

    When tool handlers have parameters with RequiresElicitation annotations,
    this middleware presents those values to the user for review and
    potential modification. Aborts execution if the user declines.

    Handshake-era connections are elicited with a server-initiated request.
    2026-07-28 connections receive an InputRequiredResult and the answer is
    read from the client's retry (SEP-2322).
    """

    def _supports_elicitation(self, session: ServerSession) -> bool:
        """Check if client supports elicitation."""
        capabilities = session.client_capabilities
        if not capabilities:
            return False
        return capabilities.elicitation is not None

    def _is_modern_protocol(self, fastmcp_context: Context) -> bool:
        """Check if the connection negotiated a protocol era without server-initiated requests."""
        request_context = fastmcp_context.request_context
        return request_context is not None and request_context.protocol_version in MODERN_PROTOCOL_VERSIONS

    async def handle_on_tool_call(
        self,
        context: MiddlewareContext[CallToolRequestParams],
        handler: Callable[..., Any],
    ) -> MiddlewareContext[CallToolRequestParams] | InputRequiredToolResult:
        """Elicit values for parameters with RequiresElicitation.

        Args:
            context: The middleware context containing the tool call request
            handler: The handler method that will process this tool

        Returns:
            Context with any user-modified values, or an InputRequiredToolResult
            asking a 2026-07-28 client for them

        Raises:
            ToolError: If user declines or cancels
        """
        fastmcp_context = context.fastmcp_context
        if fastmcp_context is None:
            return context

        # Skip elicitation if client doesn't support it
        if not self._supports_elicitation(fastmcp_context.session):
            return context

        fields = self._collect_elicitation_fields(handler)
        if not fields:
            return context

        model = self._build_elicitation_model(fields, context.message.arguments or {})

        outcome: ElicitationOutcome
        if self._is_modern_protocol(fastmcp_context):
            responses = fastmcp_context.input_responses or {}
            response = responses.get(ELICITATION_INPUT_KEY)
            if response is None:
                return self._request_input(model)
            outcome = self._parse_input_response(response, model)
        else:
            outcome = await fastmcp_context.elicit(message=ELICITATION_MESSAGE, response_type=model)

        if isinstance(outcome, AcceptedElicitation):
            arguments = dict(context.message.arguments or {})
            for field_name in fields:
                if hasattr(outcome.data, field_name):
                    arguments[field_name] = getattr(outcome.data, field_name)
            updated_message = CallToolRequestParams(name=context.message.name, arguments=arguments)
            return context.copy(message=updated_message)

        action = outcome.__class__.__name__.replace("Elicitation", "").lower()
        raise ToolError(f"Elicitation was {action}: cannot proceed with tool call")

    def _request_input(self, model: type[BaseModel]) -> InputRequiredToolResult:
        """Build an InputRequiredResult asking the client to fill in the elicitation form."""
        config = parse_elicit_response_type(model)
        request = ElicitRequest(
            params=ElicitRequestFormParams(message=ELICITATION_MESSAGE, requested_schema=config.schema)
        )
        return InputRequiredToolResult(InputRequiredResult(input_requests={ELICITATION_INPUT_KEY: request}))

    def _parse_input_response(self, response: InputResponse, model: type[BaseModel]) -> ElicitationOutcome:
        """Convert a client's input response into an elicitation outcome."""
        if not isinstance(response, ElicitResult):
            raise ToolError(f"Expected an elicitation response, got {type(response).__name__}")
        if response.action == "accept":
            return handle_elicit_accept(parse_elicit_response_type(model), response.content)
        if response.action == "decline":
            return DeclinedElicitation()
        return CancelledElicitation()

    def _collect_elicitation_fields(self, handler: Callable[..., Any]) -> dict[str, tuple[Any, RequiresElicitation]]:
        """Collect parameters with RequiresElicitation annotations.

        Args:
            handler: The handler method to inspect

        Returns:
            Dictionary mapping parameter names to (type, metadata) tuples
        """
        fields = {}
        sig = inspect.signature(handler)

        for param_name, param in sig.parameters.items():
            if param_name == "self":
                continue

            metadata = self._get_annotation_metadata(param, RequiresElicitation)
            if metadata:
                base_type = self._extract_base_type(param.annotation)
                fields[param_name] = (base_type, metadata)

        return fields

    def _build_elicitation_model(
        self,
        fields: dict[str, tuple[Any, RequiresElicitation]],
        current_args: dict[str, Any],
    ) -> type[BaseModel]:
        """Build Pydantic model for elicitation dialog.

        Args:
            fields: Parameter names to (type, metadata) tuples
            current_args: Current values used as defaults

        Returns:
            Pydantic model class for elicitation
        """
        model_fields: dict[str, Any] = {}

        for param_name, (base_type, metadata) in fields.items():
            field_default = current_args.get(param_name, ...)
            model_fields[param_name] = (base_type, Field(default=field_default, description=metadata.prompt))

        return create_model("ToolElicitation", **model_fields)
