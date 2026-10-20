"""MCP proxy server with middleware support."""

from typing import Any, overload

from fastmcp import FastMCP
from fastmcp.server import create_proxy as create_fastmcp_proxy

from wags.middleware.todo import TodoServer


@overload
def create_proxy(
    server_or_config: dict[str, Any], server_name: str = "wags-proxy", enable_todos: bool = False
) -> FastMCP:
    """Create a proxy from a server configuration dict."""
    ...


@overload
def create_proxy(server_or_config: FastMCP, server_name: str = "wags-proxy", enable_todos: bool = False) -> FastMCP:
    """Create a proxy from an existing FastMCP server instance."""
    ...


def create_proxy(
    server_or_config: dict[str, Any] | FastMCP, server_name: str = "wags-proxy", enable_todos: bool = False
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
        enable_todos: If True, mount TodoServer for task tracking (default: False)

    Returns:
        FastMCP proxy instance with middleware support

    Raises:
        NotImplementedError: If enable_todos=True and target server has instructions
    """
    # Inherit instructions from target server if available
    instructions = server_or_config.instructions if isinstance(server_or_config, FastMCP) else None
    proxy = create_fastmcp_proxy(server_or_config, name=server_name, instructions=instructions)

    if enable_todos:
        _enable_todos(proxy)

    return proxy


def _enable_todos(proxy: FastMCP) -> None:
    """Enable todo tracking on a proxy server."""
    # Check for instruction conflict
    if proxy.instructions:
        raise NotImplementedError(
            "Instruction merging not yet supported. Target server must not have instructions when enable_todos=True."
        )

    # Mount todo server and set instructions
    todo_server = TodoServer()
    proxy.mount(todo_server)
    proxy.instructions = todo_server.instructions
