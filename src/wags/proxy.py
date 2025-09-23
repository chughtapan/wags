"""MCP proxy server with middleware support."""

from typing import Any, overload

import mcp.types
from fastmcp import FastMCP
from fastmcp.server.middleware import MiddlewareContext
from fastmcp.server.proxy import FastMCPProxy, ProxyClient
from fastmcp.utilities.logging import get_logger

logger = get_logger("wags.proxy")


class _WagsProxy(FastMCPProxy):
    """FastMCP proxy with notification support. Private - use create_proxy()."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._register_notification_handlers()

    def _register_notification_handlers(self):
        async def handle_roots_list_changed(
            notify: mcp.types.RootsListChangedNotification,
        ) -> None:
            context = MiddlewareContext(
                message=notify,
                fastmcp_context=None,
                source="client",
                type="notification",
                method="notifications/roots/list_changed",
            )

            async def base_handler(ctx: MiddlewareContext) -> None:
                return None

            await self._apply_middleware(context, base_handler)

        self._mcp_server.notification_handlers[
            mcp.types.RootsListChangedNotification
        ] = handle_roots_list_changed


@overload
def create_proxy(
    server_or_config: dict[str, Any],
    server_name: str = "wags-proxy"
) -> FastMCP:
    """Create a proxy from a server configuration dict."""
    ...


@overload
def create_proxy(
    server_or_config: FastMCP,
    server_name: str = "wags-proxy"
) -> FastMCP:
    """Create a proxy from an existing FastMCP server instance."""
    ...


def create_proxy(
    server_or_config: dict[str, Any] | FastMCP,
    server_name: str = "wags-proxy"
) -> FastMCP:
    """Create a proxy server with middleware support.

    This function can be called in two ways:
    
    1. With a configuration dict (for subprocess-based servers):
       ```python
       config = {"command": "python", "args": ["server.py"]}
       proxy = create_proxy(config)
       ```
    
    2. With a FastMCP server instance (for in-memory servers):
       ```python
       server = FastMCP("my-server")
       proxy = create_proxy(server)
       ```

    Args:
        server_or_config: Either a server configuration dict (command, args, env) or
                          a FastMCP server instance to wrap
        server_name: Name for the proxy server

    Returns:
        FastMCP proxy instance with middleware support
    """
    base_client: ProxyClient = ProxyClient(server_or_config, name=f"{server_name}-client")
    return _WagsProxy(
        client_factory=lambda: base_client.new(),
        name=server_name
    )