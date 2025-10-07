"""Mock file server with TodoServer for e2e testing."""

from typing import Any

from fastmcp import FastMCP

from wags.proxy import create_proxy

# Create minimal file server
server = FastMCP("mock-files")


@server.tool()
async def mkdir(path: str) -> dict[str, Any]:
    """Create a directory."""
    return {"success": True, "created": path}


@server.tool()
async def mv(source: str, destination: str) -> dict[str, Any]:
    """Move a file or directory."""
    return {"success": True, "moved": f"{source} -> {destination}"}


@server.tool()
async def grep(pattern: str, file: str) -> dict[str, Any]:
    """Search for pattern in file."""
    return {"found": True, "matches": [f"Line containing {pattern}"]}


@server.tool()
async def sort(file: str) -> dict[str, Any]:
    """Sort file contents by line."""
    return {"success": True, "sorted": file}


@server.tool()
async def diff(file1: str, file2: str) -> dict[str, Any]:
    """Compare two files."""
    return {"differences": ["Files differ"]}


# Create proxy with TodoServer enabled - this will be run by `fastmcp run`
mcp = create_proxy(server, server_name="mock-files-todo", enable_todos=True)
