"""Middleware for validating tool access against configured roots.

Uses simple prefix matching to check if resources are allowed based on
client-configured root URIs.
"""

import inspect
import re
from collections.abc import Callable
from typing import Any, TypeVar

from fastmcp.server.middleware.middleware import CallNext, MiddlewareContext
from mcp.server.session import ServerSession
from mcp.types import CallToolRequestParams, Notification

from .base import WagsMiddlewareBase

F = TypeVar("F", bound=Callable[..., Any])


def requires_root(template: str) -> Callable[[F], F]:
    """Mark a method as requiring root validation.

    Args:
        template: URI template with placeholders, e.g. "https://github.com/{owner}/{repo}"

    Raises:
        NameError: If template variables are not function parameters
        ValueError: If different template applied to already decorated function
    """

    def decorator(func: F) -> F:
        if hasattr(func, "__root_template__"):
            existing = getattr(func, "__root_template__")
            if existing != template:
                raise ValueError(
                    f"Method {func.__name__} already has root template: '{existing}'. "
                    f"Cannot apply different template: '{template}'"
                )
            return func

        template_vars = set(re.findall(r"{(\w+)}", template))
        if template_vars:
            sig = inspect.signature(func)
            func_params = set(sig.parameters.keys())

            missing_params = template_vars - func_params
            if missing_params:
                raise NameError(
                    f"Template variable(s) {missing_params} not found in function "
                    f"{func.__name__} parameters {func_params}"
                )

        setattr(func, "__root_template__", template)
        return func

    return decorator


class RootsMiddleware(WagsMiddlewareBase):
    """Validates tool calls against client-configured roots.

    Blocks decorated methods unless the resource URI starts with
    an allowed root prefix. Skips validation if client lacks roots capability.

    Examples:
    - "https://github.com/myorg/" allows all repos in myorg
    - "https://github.com/myorg/specific-repo" allows only that repo
    """

    def __init__(self, handlers: Any) -> None:
        """Initialize with handlers containing decorated methods."""
        super().__init__(handlers)
        self._roots: list[str] = []
        self._roots_loaded = False

    def _supports_roots(self, session: ServerSession) -> bool:
        """Check if client supports roots."""
        if not hasattr(session, "client_params") or not session.client_params:
            return False
        capabilities = session.client_params.capabilities
        if not capabilities:
            return False
        return capabilities.roots is not None

    async def _load_roots(self, context: MiddlewareContext) -> None:
        """Load roots from client context."""
        if context.fastmcp_context:
            try:
                roots = await context.fastmcp_context.list_roots()
                self._roots = [str(root.uri) for root in roots]
                self._roots_loaded = True
            except Exception:
                self._roots = []
                self._roots_loaded = True
        else:
            self._roots = []
            self._roots_loaded = True

    async def on_notification(
        self,
        context: MiddlewareContext[Notification[Any, Any]],
        call_next: CallNext[Notification[Any, Any], Any],
    ) -> Any:
        """Handle roots change notifications."""
        if context.method == "notifications/roots/list_changed":
            self._roots_loaded = False
        return await call_next(context)

    async def handle_on_tool_call(
        self,
        context: MiddlewareContext[CallToolRequestParams],
        handler: Callable[..., Any],
    ) -> MiddlewareContext[CallToolRequestParams]:
        """Validate tool call against configured roots.

        Returns:
            Context if validation passes

        Raises:
            ValueError: If required parameters missing
            PermissionError: If access denied
        """
        # Check once if we have a valid context
        if not context.fastmcp_context or not hasattr(context.fastmcp_context, "session"):
            return context

        # Skip roots checking if client doesn't support it
        if not self._supports_roots(context.fastmcp_context.session):
            return context

        template = getattr(handler, "__root_template__", None)
        if not template:
            return context

        if not self._roots_loaded:
            await self._load_roots(context)

        try:
            resource = template.format(**(context.message.arguments or {}))
        except KeyError as e:
            param = str(e).strip("'")
            raise ValueError(f"Missing required parameter '{param}' for root validation")

        if not self._roots:
            raise PermissionError("Access denied: No roots configured")

        if self._resource_matches_roots(resource):
            return context

        raise PermissionError(f"Access denied: {resource} not in allowed roots")

    def _resource_matches_roots(self, resource: str) -> bool:
        """Check if resource matches any root prefix."""
        return any(resource.startswith(root) for root in self._roots)
