"""
Generate middleware stubs from MCP servers.

This tool connects to an MCP server, introspects its tools,
and generates a middleware class with type annotations.
"""

from pathlib import Path
from typing import Any

from fastmcp import Client
from mcp.types import Tool

from wags.utils.config import load_config


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

    method = f"""    @tool_handler
    async def {method_name}(
        {params_str}
    ):
        \"\"\"{docstring}\"\"\"
        pass"""

    return method


def generate_middleware_class(class_name: str, tools: list[Tool]) -> str:
    """Generate the complete middleware class code."""

    # Collect unique imports needed
    needs_literal = any(
        "enum" in prop
        for tool in tools
        if tool.inputSchema and isinstance(tool.inputSchema, dict)
        for prop in tool.inputSchema.get("properties", {}).values()
    )

    # Generate imports
    imports = ["from typing import Any"]
    if needs_literal:
        imports[0] = "from typing import Any, Literal"
    imports.extend([
        "",
        "from wags.middleware.base import tool_handler",
        "from wags.middleware.elicitation import ElicitationMiddleware",
    ])

    # Generate class definition
    class_def = f"""


class {class_name}(ElicitationMiddleware):
    \"\"\"Auto-generated middleware for MCP server.\"\"\"
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


async def generate_middleware_stub(
    config_path: Path,
    server_name: str | None = None,
    output_path: Path | None = None,
    class_name: str | None = None
):
    """Generate middleware stub from MCP server (for CLI usage)."""
    config = load_config(config_path)

    if "mcpServers" not in config:
        raise ValueError("Config file must have 'mcpServers' section")

    servers = config["mcpServers"]
    if not servers:
        raise ValueError("No servers found in config")

    if server_name is None:
        if len(servers) > 1:
            raise ValueError(f"Multiple servers found, please specify one: {', '.join(servers.keys())}")
        server_name = next(iter(servers))
    elif server_name not in servers:
        raise ValueError(f"Server '{server_name}' not found. Available: {', '.join(servers.keys())}")

    client = Client(config)
    async with client:
        tools = await client.list_tools()

    if class_name is None:
        parts = server_name.replace("-", "_").replace(".", "_").split("_")
        class_name = "".join(p.capitalize() for p in parts) + "Middleware"

    code = generate_middleware_class(class_name, tools)

    if output_path:
        output_path.write_text(code)
    else:
        print(code)