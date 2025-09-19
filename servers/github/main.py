"""Main entry point for GitHub server with elicitation middleware."""

from pathlib import Path
from wags.utils.config import load_config, create_proxy
from .middleware import GithubElicitationMiddleware

# Load config and create proxy server
config = load_config(Path(__file__).parent / "config.json")
mcp = create_proxy(config, "github-proxy")

# Add middleware(s)
mcp.add_middleware(GithubElicitationMiddleware())

# Run the server when executed directly
if __name__ == "__main__":
    import asyncio
    asyncio.run(mcp.run_stdio_async())