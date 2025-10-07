"""WAGS CLI using cyclopts."""

import asyncio
import sys
from pathlib import Path

import cyclopts
from fastmcp import __version__ as fastmcp_version
from fastmcp.utilities.logging import get_logger
from rich.console import Console

from wags import __version__

logger = get_logger("wags.cli")
console = Console()

app = cyclopts.App(
    name="wags",
    help="WAGS - Web Agent Gateway System for MCP servers with FastMCP.",
    version=__version__,
)


def cli() -> None:
    """Entry point for the CLI."""
    app()


@app.command
def version() -> None:
    """Show version information."""
    console.print(f"[bold]WAGS[/bold] version {__version__}")
    console.print(f"[dim]FastMCP version {fastmcp_version}[/dim]")


@app.command
def run(
    server_path: Path,
) -> None:
    """Run an MCP server with middleware.

    Args:
        server_path: Path to server directory containing main.py
    """
    from wags.utils.server import run_server

    try:
        asyncio.run(run_server(server_path))
    except KeyboardInterrupt:
        logger.info("Server stopped")
    except Exception as e:
        logger.error(f"Failed to run server: {e}")
        sys.exit(1)


@app.command
def quickstart(
    config: Path,
    *,
    server_name: str | None = None,
    handlers_file: str | None = None,
    main_file: str | None = None,
    class_name: str | None = None,
    only_handlers: bool = False,
    only_main: bool = False,
    force: bool = False,
) -> None:
    """Generate WAGS proxy server with middleware handlers.

    Args:
        config: Path to MCP config.json file
        server_name: Name of the server in config (defaults to first server)
        handlers_file: Output path for handlers file (defaults to handlers.py)
        main_file: Output path for main file (defaults to main.py)
        class_name: Name for the handlers class (defaults to auto-generated)
        only_handlers: Only generate handlers file
        only_main: Only generate main file
        force: Overwrite existing files without asking
    """
    from wags.utils.quickstart import run_quickstart

    try:
        asyncio.run(
            run_quickstart(
                config_path=config,
                server_name=server_name,
                handlers_file=handlers_file,
                main_file=main_file,
                class_name=class_name,
                only_handlers=only_handlers,
                only_main=only_main,
                force=force,
            )
        )
    except Exception as e:
        logger.error(f"Failed to run quickstart: {e}")
        sys.exit(1)


@app.command
def init(
    name: str,
    *,
    path: Path | None = None,
) -> None:
    """Initialize a new server with middleware scaffold.

    Args:
        name: Name for the new server
        path: Directory to create server in (defaults to servers/{name})
    """
    from wags.utils.server_template import create_server_scaffold

    try:
        create_server_scaffold(name, path)
        console.print(f"[green]✓[/green] Created server scaffold at {path or f'servers/{name}'}")
    except Exception as e:
        logger.error(f"Failed to initialize server: {e}")
        sys.exit(1)


if __name__ == "__main__":
    cli()
