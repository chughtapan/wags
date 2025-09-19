"""Elicitation middleware for automatic parameter collection."""

import inspect
from dataclasses import dataclass
from typing import Any

from fastmcp.server.elicitation import AcceptedElicitation, CancelledElicitation, DeclinedElicitation
from fastmcp.server.middleware.middleware import CallNext, MiddlewareContext
from mcp.types import CallToolRequestParams
from pydantic import Field, create_model

from .base import BaseMiddleware


@dataclass
class RequiresElicitation:
    """Marker for parameters needing elicitation."""

    prompt: str

    def __post_init__(self):
        """Validate configuration."""
        if not self.prompt:
            raise ValueError("Elicitation prompt is required")


class ElicitationMiddleware(BaseMiddleware):
    """Middleware for automatic parameter elicitation."""

    async def on_call_tool(
        self,
        context: MiddlewareContext[CallToolRequestParams],
        call_next: CallNext[CallToolRequestParams, Any],
    ) -> Any:
        """Handle tool calls with elicitation."""
        handler = self.get_tool_handler(context.message)

        # Pass through if no handler or no context
        if not handler or not context.fastmcp_context:
            return await call_next(context)

        arguments = dict(context.message.arguments or {})

        # Collect fields needing elicitation
        elicitation_fields = self._collect_elicitation_fields(handler)

        if elicitation_fields:
            # Build model with all fields
            elicit_model = self._build_elicitation_model(elicitation_fields, arguments)

            # Perform elicitation
            result = await context.fastmcp_context.elicit(
                message="Please provide the required information",
                response_type=elicit_model
            )

            # Handle elicitation response
            if isinstance(result, AcceptedElicitation):
                for field_name in elicitation_fields:
                    if hasattr(result.data, field_name):
                        arguments[field_name] = getattr(result.data, field_name)
            elif isinstance(result, (DeclinedElicitation, CancelledElicitation)):
                action = result.__class__.__name__.replace('Elicitation', '').lower()
                raise ValueError(f"Elicitation was {action}: cannot proceed with tool call")

        # Continue with updated arguments
        updated_message = CallToolRequestParams(
            name=context.message.name,
            arguments=arguments
        )
        updated_context = context.copy(message=updated_message)
        return await call_next(updated_context)

    def _collect_elicitation_fields(
        self, handler
    ) -> dict[str, tuple[Any, RequiresElicitation]]:
        """Collect all parameters with RequiresElicitation annotations."""
        fields = {}
        sig = inspect.signature(handler)

        for param_name, param in sig.parameters.items():
            # Use base class method to get metadata
            metadata = self._get_annotation_metadata(param, RequiresElicitation)
            if metadata:
                # Use base class method to extract type
                base_type = self._extract_base_type(param.annotation)
                fields[param_name] = (base_type, metadata)

        return fields

    def _build_elicitation_model(
        self,
        fields: dict[str, tuple[Any, RequiresElicitation]],
        current_args: dict
    ):
        """Build a Pydantic model with all elicitation fields."""
        model_fields: dict[str, Any] = {}

        for param_name, (base_type, metadata) in fields.items():
            field_default = current_args.get(param_name, ...)
            model_fields[param_name] = (
                base_type,
                Field(default=field_default, description=metadata.prompt)
            )

        return create_model("ToolElicitation", **model_fields)