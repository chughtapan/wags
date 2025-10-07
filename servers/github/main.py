"""Main entry point for GitHub server with middleware."""

from pathlib import Path

from wags import create_proxy, load_config
from wags.middleware import ElicitationMiddleware, RootsMiddleware

from .handlers import GithubHandlers

# Load config and create proxy server
config = load_config(Path(__file__).parent / "config.json")
mcp = create_proxy(config, "github-proxy")

# Initialize handlers
handlers = GithubHandlers()

# Add middleware stack
mcp.add_middleware(RootsMiddleware(handlers=handlers))
mcp.add_middleware(ElicitationMiddleware(handlers=handlers))

# Run the server when executed directly
if __name__ == "__main__":
    import asyncio

    asyncio.run(mcp.run_stdio_async())
