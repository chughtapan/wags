from pathlib import Path

from handlers import GitHubHandlers

from wags import create_proxy, load_config
from wags.middleware import ElicitationMiddleware, RootsMiddleware

# Load configuration and create a proxy server
config = load_config(Path(__file__).parent / "config.json")
mcp = create_proxy(config, server_name="github-proxy")

# Handlers configure the middleware on what to do
handlers = GitHubHandlers()

# Add the configured middleware to your proxy server
mcp.add_middleware(RootsMiddleware(handlers=handlers))
mcp.add_middleware(ElicitationMiddleware(handlers=handlers))

if __name__ == "__main__":
    import asyncio
    asyncio.run(mcp.run_stdio_async())
