"""MCP proxy server with middleware support."""

from typing import Any

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


def create_proxy(
    config: dict[str, Any],
    server_name: str = "wags-proxy"
) -> FastMCP:
    """Create a proxy server with middleware support.

    Args:
        config: Server configuration (command, args, env)
        server_name: Name for the proxy server

    Returns:
        FastMCP proxy instance
    """
    base_client: ProxyClient = ProxyClient(config, name=f"{server_name}-client")
    return _WagsProxy(
        client_factory=lambda: base_client.new(),
        name=server_name
    )