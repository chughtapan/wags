"""Base middleware for MCP tool request interception.

This module provides the foundation for creating middleware that can
intercept tool requests and perform custom processing before they
reach their handlers.
"""

import inspect
from collections.abc import Callable
from typing import Any, get_args, get_origin

from fastmcp.server.middleware.middleware import CallNext, Middleware, MiddlewareContext
from mcp.types import CallToolRequestParams


class WagsMiddlewareBase(Middleware):
    """Base class for tool-aware middleware.

    This class provides the basic infrastructure for middleware that needs
    to intercept and process tool calls. It looks up handlers for incoming
    tool requests and delegates to handle_on_tool_call for custom processing.
    Subclasses may override handle_on_tool_call to implement their specific logic.
    """

    def __init__(self, handlers):
        """Initialize with handlers object.

        Args:
            handlers: Object containing tool handler methods
        """
        super().__init__()
        self.handlers = handlers

    def get_tool_handler(self, request: CallToolRequestParams) -> Callable | None:
        """Get handler for this request if it exists.

        Args:
            request: The tool call request

        Returns:
            Handler method if found, None otherwise
        """
        name = request.name
        if hasattr(self.handlers, name):
            handler = getattr(self.handlers, name)
            if callable(handler) and inspect.iscoroutinefunction(handler):
                return handler
        return None

    async def on_call_tool(
        self,
        context: MiddlewareContext[CallToolRequestParams],
        call_next: CallNext[CallToolRequestParams, Any],
    ) -> Any:
        """Intercept tool calls and process them through the middleware chain."""
        handler = self.get_tool_handler(context.message)
        if handler:
            context = await self.handle_on_tool_call(context, handler)
        return await call_next(context)

    async def handle_on_tool_call(
        self,
        context: MiddlewareContext[CallToolRequestParams],
        handler: Callable
    ) -> MiddlewareContext[CallToolRequestParams]:
        """Process a tool call with custom logic.

        Subclasses may override this method to implement their specific
        middleware behavior. The method receives the context and handler,
        allowing inspection and modification of the request.

        Args:
            context: The middleware context containing the tool request
            handler: The handler method that will process this tool

        Returns:
            The context, either unchanged or modified using context.copy()
        """
        return context

    def _extract_base_type(self, annotation):
        """Extract the actual type from Annotated[type, ...].

        Helper method for subclasses to use.

        Returns:
            The base type without annotations
        """
        from typing import Annotated

        origin = get_origin(annotation)
        if origin is Annotated:
            args = get_args(annotation)
            return args[0] if args else annotation
        return annotation

    def _get_annotation_metadata(self, param, metadata_type):
        """Extract specific metadata type from parameter annotation.

        Helper method for subclasses to use.

        Args:
            param: The parameter to inspect
            metadata_type: The metadata class to look for

        Returns:
            The metadata instance if found, None otherwise
        """
        if not hasattr(param.annotation, "__metadata__"):
            return None

        for metadata in param.annotation.__metadata__:
            if isinstance(metadata, metadata_type):
                return metadata

        return None