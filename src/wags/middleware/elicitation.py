"""Middleware for parameter elicitation during tool execution.

Enables user intervention when parameters are marked with RequiresElicitation.
"""

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastmcp.server.elicitation import AcceptedElicitation, CancelledElicitation, DeclinedElicitation
from fastmcp.server.middleware.middleware import MiddlewareContext
from mcp.server.session import ServerSession
from mcp.types import CallToolRequestParams
from pydantic import Field, create_model

from .base import WagsMiddlewareBase


@dataclass
class RequiresElicitation:
    """Marks a parameter for user review before tool execution.

    Args:
        prompt: Message shown to the user describing the parameter
    """

    prompt: str

    def __post_init__(self):
        """Validate configuration."""
        if not self.prompt:
            raise ValueError("Elicitation prompt is required")


class ElicitationMiddleware(WagsMiddlewareBase):
    """Triggers elicitation dialogs for marked parameters.

    When tool handlers have parameters with RequiresElicitation annotations,
    this middleware presents those values to the user for review and
    potential modification. Aborts execution if the user declines.
    """

    def _supports_elicitation(self, session: ServerSession) -> bool:
        """Check if client supports elicitation."""
        if not hasattr(session, 'client_params') or not session.client_params:
            return False
        capabilities = session.client_params.capabilities
        if not capabilities:
            return False
        return capabilities.elicitation is not None

    async def handle_on_tool_call(
        self,
        context: MiddlewareContext[CallToolRequestParams],
        handler: Callable
    ) -> MiddlewareContext[CallToolRequestParams]:
        """Handle elicitation for parameters with RequiresElicitation.

        Args:
            context: The middleware context containing the tool call request
            handler: The handler method that will process this tool

        Returns:
            Context with any user-modified values

        Raises:
            ValueError: If user declines or cancels
        """
        # Check once if we have a valid context
        if not context.fastmcp_context or not hasattr(context.fastmcp_context, 'session'):
            return context
        
        # Skip elicitation if client doesn't support it
        if not self._supports_elicitation(context.fastmcp_context.session):
            return context

        fields = self._collect_elicitation_fields(handler)
        if not fields:
            return context
        
        model = self._build_elicitation_model(fields, context.message.arguments or {})
        result = await context.fastmcp_context.elicit(
            message="Please provide the required information",
            response_type=model
        )

        if isinstance(result, AcceptedElicitation):
            arguments = dict(context.message.arguments or {})
            for field_name in fields:
                if hasattr(result.data, field_name):
                    arguments[field_name] = getattr(result.data, field_name)
            updated_message = CallToolRequestParams(
                name=context.message.name,
                arguments=arguments
            )
            return context.copy(message=updated_message)
        elif isinstance(result, (DeclinedElicitation, CancelledElicitation)):
            action = result.__class__.__name__.replace('Elicitation', '').lower()
            raise ValueError(f"Elicitation was {action}: cannot proceed with tool call")

        return context

    def _collect_elicitation_fields(
        self, handler: Callable
    ) -> dict[str, tuple[Any, RequiresElicitation]]:
        """Collect parameters with RequiresElicitation annotations.

        Args:
            handler: The handler method to inspect

        Returns:
            Dictionary mapping parameter names to (type, metadata) tuples
        """
        fields = {}
        sig = inspect.signature(handler)

        for param_name, param in sig.parameters.items():
            if param_name == 'self':
                continue

            metadata = self._get_annotation_metadata(param, RequiresElicitation)
            if metadata:
                base_type = self._extract_base_type(param.annotation)
                fields[param_name] = (base_type, metadata)

        return fields

    def _build_elicitation_model(
        self,
        fields: dict[str, tuple[Any, RequiresElicitation]],
        current_args: dict
    ):
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
            model_fields[param_name] = (
                base_type,
                Field(default=field_default, description=metadata.prompt)
            )

        return create_model("ToolElicitation", **model_fields)