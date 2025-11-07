"""WAGS CLI using cyclopts."""

import asyncio
import sys
from pathlib import Path

import cyclopts
from fastmcp import __version__ as fastmcp_version
from fastmcp.utilities.logging import get_logger
from mcp.types import Tool
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
    servers: str | None = None,
    config_path: Path | None = None,
    instruction_file: Path | None = None,
    model: str = "gpt-4o",
) -> None:
    """Run an interactive agent connected to wags servers.

    Args:
        servers: Comma-separated list of servers to connect to (defaults to all)
        config_path: Path to fastagent.config.yaml (defaults to servers/fastagent.config.yaml)
        instruction_file: Path to instruction file (defaults to src/wags/utils/agent_instructions.txt)
        model: Model to use (defaults to gpt-4o)
    """
    from fast_agent.cli.commands.go import run_async_agent

    if config_path is None:
        config_path = Path("servers/fastagent.config.yaml")

    if not config_path.exists():
        console.print(f"[red]Error:[/red] Config file not found: {config_path}")
        console.print("\nCreate a fastagent.config.yaml file or specify --config-path")
        sys.exit(1)

    if instruction_file is None:
        instruction_file = Path(__file__).parent.parent / "utils" / "agent_instructions.txt"

    if not instruction_file.exists():
        console.print(f"[red]Error:[/red] Instruction file not found: {instruction_file}")
        sys.exit(1)

    try:
        run_async_agent(
            name="wags",
            instruction=instruction_file.read_text(encoding="utf-8"),
            config_path=str(config_path),
            servers=servers,
            urls=None,
            auth=None,
            model=model,
            message=None,
            prompt_file=None,
            stdio_commands=None,
            agent_name="agent",
        )
    except KeyboardInterrupt:
        console.print("\n[dim]Agent stopped[/dim]")


@app.command
def start_server(
    server_path: Path,
) -> None:
    """Start an MCP server with middleware.

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


def _check_overwrite(file_path: Path, force: bool) -> bool:
    """Check if file can be overwritten."""
    if not file_path.exists():
        return True
    if force:
        console.print(f"[yellow]Overwriting existing file:[/yellow] {file_path}")
        return True
    from rich.prompt import Confirm

    return Confirm.ask(f"File {file_path} already exists. Overwrite?", default=False)


def _generate_handlers_file(handlers_path: Path, class_name: str, tools: list[Tool], force: bool) -> None:
    """Generate and write handlers file."""
    from wags.utils.handlers_generator import generate_handlers_class

    if _check_overwrite(handlers_path, force):
        console.print("[cyan]Generating handlers file...[/cyan]")
        handlers_code = generate_handlers_class(class_name, tools)
        handlers_path.write_text(handlers_code)
        console.print(f"[green]Created:[/green] {handlers_path}")
    else:
        console.print("[yellow]Skipped handlers file[/yellow]")


def _generate_main_file(main_path: Path, handlers_file: str, class_name: str, config_name: str, force: bool) -> None:
    """Generate and write main file."""
    from jinja2 import Template

    if _check_overwrite(main_path, force):
        console.print("[cyan]Generating main file...[/cyan]")
        templates_dir = Path(__file__).parent.parent / "templates"
        with open(templates_dir / "main.py.j2") as f:
            template = Template(f.read())
        handlers_module = Path(handlers_file).stem
        main_code = template.render(
            handlers_module=handlers_module,
            class_name=class_name,
            config_filename=config_name,
            server_name="wags-proxy",
        )
        main_path.write_text(main_code)
        console.print(f"[green]Created:[/green] {main_path}")
    else:
        console.print("[yellow]Skipped main file[/yellow]")


@app.command
def quickstart(
    config: Path,
    *,
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
        handlers_file: Output path for handlers file (defaults to handlers.py)
        main_file: Output path for main file (defaults to main.py)
        class_name: Name for the handlers class (defaults to auto-generated)
        only_handlers: Only generate handlers file
        only_main: Only generate main file
        force: Overwrite existing files without asking
    """
    from wags.utils.config import load_config
    from wags.utils.handlers_generator import introspect_server

    try:
        config_dir = config.parent
        handlers_file = handlers_file or "handlers.py"
        main_file = main_file or "main.py"
        handlers_path = config_dir / handlers_file
        main_path = config_dir / main_file

        if only_main and only_handlers:
            console.print("[red]Error: Cannot specify both --only-handlers and --only-main[/red]")
            sys.exit(1)

        if only_main and not handlers_path.exists():
            console.print(
                f"[red]Error: Handlers file {handlers_path} does not exist. "
                "Generate it first or specify --handlers-file[/red]"
            )
            sys.exit(1)

        load_config(config)

        tools = []
        if not only_main:
            console.print("[cyan]Connecting to MCP server to discover tools...[/cyan]")
            # Handle both sync and async contexts
            try:
                asyncio.get_running_loop()
                # We're in an async context, run in a thread to avoid event loop conflict
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, introspect_server(config))
                    tools = future.result()
            except RuntimeError:
                # No event loop running, use asyncio.run
                tools = asyncio.run(introspect_server(config))
            console.print(f"[green]Found {len(tools)} tools[/green]")

        class_name = class_name or "Handlers"

        if not only_main:
            _generate_handlers_file(handlers_path, class_name, tools, force)

        if not only_handlers:
            _generate_main_file(main_path, handlers_file, class_name, config.name, force)

        console.print("\n[bold green]✅ Quickstart complete![/bold green]")

    except Exception as e:
        logger.error(f"Failed to run quickstart: {e}")
        sys.exit(1)


if __name__ == "__main__":
    cli()
