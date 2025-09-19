"""Base middleware for tool handling."""

from typing import get_args, get_origin

from fastmcp.server.middleware.middleware import Middleware
from mcp.types import CallToolRequestParams


def tool_handler(func):
    """Mark a method as a tool handler."""
    func._is_tool_handler = True
    return func


class BaseMiddleware(Middleware):
    """Base class for tool handling middleware."""

    def __init__(self):
        """Initialize and register tool handlers."""
        super().__init__()
        self.tool_handlers = {}
        self._register_handlers()

    def _register_handlers(self):
        """Register all methods marked with @tool_handler."""
        for name in dir(self):
            method = getattr(self, name)
            if callable(method) and getattr(method, '_is_tool_handler', False):
                self.tool_handlers[name] = method

    def get_tool_handler(self, request: CallToolRequestParams):
        """Get the handler for a tool request."""
        return self.tool_handlers.get(request.name)

    def _extract_base_type(self, annotation):
        """Extract the actual type from Annotated[type, ...]."""
        from typing import Annotated

        origin = get_origin(annotation)
        if origin is Annotated:
            args = get_args(annotation)
            return args[0] if args else annotation
        return annotation

    def _get_annotation_metadata(self, param, metadata_type):
        """Extract specific metadata type from parameter annotation."""
        if not hasattr(param.annotation, "__metadata__"):
            return None

        for metadata in param.annotation.__metadata__:
            if isinstance(metadata, metadata_type):
                return metadata

        return None

