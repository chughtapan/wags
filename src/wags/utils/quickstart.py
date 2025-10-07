"""Quickstart command for creating WAGS proxy servers."""

from pathlib import Path
from typing import Any

from fastmcp import Client
from fastmcp.utilities.logging import get_logger
from mcp.types import Tool
from rich.console import Console
from rich.prompt import Confirm

from wags import load_config

logger = get_logger("wags.utils.quickstart")
console = Console()


def json_schema_to_python_type(schema: dict[str, Any]) -> str:
    """Convert JSON Schema to Python type annotation."""
    if not isinstance(schema, dict):
        return "Any"

    schema_type = schema.get("type")
    if schema_type is None:
        return "Any"

    if schema_type == "string":
        if "enum" in schema:
            values = ", ".join(f'"{v}"' for v in schema["enum"])
            return f"Literal[{values}]"
        return "str"

    # Handle array type
    if schema_type == "array":
        items = schema.get("items", {})
        item_type = json_schema_to_python_type(items)
        return f"list[{item_type}]"

    # Map simple types
    type_mapping = {
        "integer": "int",
        "number": "float",
        "boolean": "bool",
        "object": "dict[str, Any]",
        "null": "None",
    }

    return type_mapping.get(schema_type, "Any")


def sanitize_method_name(name: str) -> str:
    """Convert tool name to valid Python method name."""
    # Replace common separators with underscore
    for char in ["-", ".", "/", " "]:
        name = name.replace(char, "_")

    name = "".join(c if c.isalnum() or c == "_" else "" for c in name)

    # Ensure it doesn't start with a number
    if name and name[0].isdigit():
        name = f"tool_{name}"

    # Ensure it's not empty
    if not name:
        name = "tool"

    return name.lower()


def generate_method_stub(tool: Tool) -> str:
    """Generate a method stub for a tool."""
    method_name = sanitize_method_name(tool.name)

    # Parse parameters from inputSchema
    params = []
    params.append("self")

    if tool.inputSchema and isinstance(tool.inputSchema, dict):
        properties = tool.inputSchema.get("properties", {})
        required = tool.inputSchema.get("required", [])

        # Process required parameters first
        for param_name in required:
            if param_name in properties:
                param_schema = properties[param_name]
                param_type = json_schema_to_python_type(param_schema)
                params.append(f"{param_name}: {param_type}")

        # Process optional parameters
        for param_name, param_schema in properties.items():
            if param_name not in required:
                param_type = json_schema_to_python_type(param_schema)
                default = "None"
                if param_schema.get("type") == "boolean":
                    default = "False"
                elif param_schema.get("type") in ["integer", "number"]:
                    if "default" in param_schema:
                        default = str(param_schema["default"])
                params.append(f"{param_name}: {param_type} | None = {default}")

    # Build method signature
    params_str = ",\n        ".join(params)

    # Build docstring
    docstring = tool.description or f"Handler for {tool.name}"

    method = f"""    async def {method_name}(
        {params_str}
    ):
        \"\"\"{docstring}\"\"\"
        pass  # Stub - actual execution happens in MCP server"""

    return method


def generate_handlers_class(class_name: str, tools: list[Tool]) -> str:
    """Generate the complete handlers class code."""

    # Collect unique imports needed
    needs_literal = any(
        "enum" in prop
        for tool in tools
        if tool.inputSchema and isinstance(tool.inputSchema, dict)
        for prop in tool.inputSchema.get("properties", {}).values()
    )

    # Generate imports
    imports = []
    imports.append('"""Handler stubs for MCP server tools."""')
    imports.append("")
    imports.append("from typing import Any")
    if needs_literal:
        imports[-1] = "from typing import Any, Literal"
    imports.append("")
    imports.append("# Example middleware decorators - add as needed:")
    imports.append("# from wags.middleware import requires_root, RequiresElicitation")
    imports.append("")

    # Generate class definition
    class_def = f"""

class {class_name}:
    \"\"\"Handler stubs for MCP server tools.

    These are empty stubs used to attach middleware decorators.
    The actual tool implementation is in the MCP server.
    \"\"\"
"""

    # Generate method stubs
    methods = []
    for tool in tools:
        method = generate_method_stub(tool)
        methods.append(method)

    # Combine everything
    code = "\n".join(imports) + class_def
    if methods:
        code += "\n\n".join(methods)
    else:
        code += "\n    pass"

    return code


def generate_main_file(config_path: Path, handlers_module: str, class_name: str, server_name: str | None = None) -> str:
    """Generate the main.py file for the proxy server."""

    # Determine import statement for handlers
    if "/" in handlers_module or "\\" in handlers_module:
        # It's a path, extract just the module name
        handlers_module = Path(handlers_module).stem

    template = f'''"""WAGS proxy server with middleware."""

from pathlib import Path
from wags import create_proxy, load_config
from wags.middleware import RootsMiddleware, ElicitationMiddleware
from {handlers_module} import {class_name}

# Load configuration
config = load_config(Path(__file__).parent / "{config_path.name}")
mcp = create_proxy(config, server_name="{server_name or "wags-proxy"}")

# Initialize handler stubs
handlers = {class_name}()

# Add middleware - customize as needed
# Uncomment and configure the middleware you want to use:

# Access control - requires @requires_root decorators on handler methods
# mcp.add_middleware(RootsMiddleware(handlers=handlers))

# Parameter elicitation - requires RequiresElicitation annotations
# mcp.add_middleware(ElicitationMiddleware(handlers=handlers))

if __name__ == "__main__":
    import asyncio
    asyncio.run(mcp.run_stdio_async())
'''

    return template


def resolve_server_name(config: dict[str, Any], server_name: str | None = None) -> str:
    """Resolve the server name from config."""
    if "mcpServers" not in config:
        raise ValueError("Config file must have 'mcpServers' section")

    servers = config["mcpServers"]
    if not servers:
        raise ValueError("No servers found in config")

    if server_name is None:
        if len(servers) > 1:
            raise ValueError(f"Multiple servers found, please specify one: {', '.join(servers.keys())}")
        result: str = next(iter(servers))
        return result
    elif server_name not in servers:
        raise ValueError(f"Server '{server_name}' not found. Available: {', '.join(servers.keys())}")

    return server_name


async def introspect_server(config_path: Path) -> list[Tool]:
    """Connect to MCP server and get its tools."""
    config = load_config(config_path)

    client = Client(config)
    async with client:
        tools = await client.list_tools()

    return tools


def check_file_exists(file_path: Path, force: bool = False) -> bool:
    """Check if file exists and ask for confirmation if needed."""
    if file_path.exists():
        if force:
            console.print(f"[yellow]Overwriting existing file:[/yellow] {file_path}")
            return True
        else:
            return Confirm.ask(f"File {file_path} already exists. Overwrite?", default=False)
    return True


async def run_quickstart(
    config_path: Path,
    server_name: str | None = None,
    handlers_file: str | None = None,
    main_file: str | None = None,
    class_name: str | None = None,
    only_handlers: bool = False,
    only_main: bool = False,
    force: bool = False,
) -> None:
    """Run the quickstart command to generate WAGS proxy files.

    Args:
        config_path: Path to MCP server config.json
        server_name: Name of server in config (defaults to first)
        handlers_file: Output path for handlers file (defaults to handlers.py)
        main_file: Output path for main file (defaults to main.py)
        class_name: Name for handlers class (defaults to auto-generated)
        only_handlers: Only generate handlers file
        only_main: Only generate main file (requires existing handlers)
        force: Overwrite existing files without asking
    """
    config_dir = config_path.parent

    # Default file names
    if handlers_file is None:
        handlers_file = "handlers.py"
    if main_file is None:
        main_file = "main.py"

    handlers_path = config_dir / handlers_file
    main_path = config_dir / main_file

    # Determine what to generate
    generate_handlers = not only_main
    generate_main = not only_handlers

    if only_main and only_handlers:
        raise ValueError("Cannot specify both --only-handlers and --only-main")

    # For main-only, we need the handlers to exist or be specified
    if only_main:
        if not handlers_path.exists():
            raise FileNotFoundError(
                f"Handlers file {handlers_path} does not exist. Generate it first or specify --handlers-file"
            )

    # Load config and resolve server name
    config = load_config(config_path)
    server_name = resolve_server_name(config, server_name)

    # Introspect server if we need to generate handlers
    tools: list[Tool] = []
    if generate_handlers:
        console.print(f"[cyan]Connecting to MCP server '{server_name}' to discover tools...[/cyan]")
        tools = await introspect_server(config_path)
        console.print(f"[green]Found {len(tools)} tools in server '{server_name}'[/green]")

    # Generate class name if not provided
    if class_name is None:
        if server_name:
            parts = server_name.replace("-", "_").replace(".", "_").split("_")
            class_name = "".join(p.capitalize() for p in parts) + "Handlers"
        else:
            class_name = "Handlers"

    # Generate and write handlers file
    if generate_handlers:
        if check_file_exists(handlers_path, force):
            console.print("[cyan]Generating handlers file...[/cyan]")
            handlers_code = generate_handlers_class(class_name, tools)
            handlers_path.write_text(handlers_code)
            console.print(f"[green]Created:[/green] {handlers_path}")
        else:
            console.print("[yellow]Skipped handlers file[/yellow]")

    # Generate and write main file
    if generate_main:
        if check_file_exists(main_path, force):
            console.print("[cyan]Generating main file...[/cyan]")
            main_code = generate_main_file(config_path, handlers_file, class_name, server_name or "wags-proxy")
            main_path.write_text(main_code)
            console.print(f"[green]Created:[/green] {main_path}")
        else:
            console.print("[yellow]Skipped main file[/yellow]")

    # Show next steps
    console.print("\n[bold green]✅ Quickstart complete![/bold green]")
    console.print("\n[bold]Next steps:[/bold]")
    console.print(f"1. Review and add middleware decorators to {handlers_file}")
    console.print("   - Add @requires_root for access control")
    console.print("   - Add RequiresElicitation for parameter review")
    console.print(f"2. Uncomment desired middleware in {main_file}")
    console.print(f"3. Run your proxy server: [cyan]python {main_file}[/cyan]")
    console.print("4. Configure your MCP client to use the proxy instead of the direct server")
