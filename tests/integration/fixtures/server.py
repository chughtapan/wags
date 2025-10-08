"""Simple MCP server for integration testing."""

from fastmcp import FastMCP

mcp = FastMCP("test-server")


@mcp.tool()
async def echo(message: str) -> str:
    """Echo a message back."""
    return message


@mcp.tool()
async def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


if __name__ == "__main__":
    mcp.run()
