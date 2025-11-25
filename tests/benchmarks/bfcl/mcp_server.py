#!/usr/bin/env python3
"""
MCP Server wrapper for BFCL API classes.
Exposes API methods as MCP tools with automatic introspection.
"""

import argparse
import asyncio
import importlib
import inspect
import json
import sys
from typing import Any

from bfcl_eval.constants.eval_config import MULTI_TURN_FUNC_DOC_PATH
from bfcl_eval.constants.executable_backend_config import (
    CLASS_FILE_PATH_MAPPING,
    MULTI_TURN_FUNC_DOC_FILE_MAPPING,
    STATELESS_CLASSES,
)
from mcp.server.fastmcp import FastMCP


def load_api_class(class_name: str) -> Any:
    """Load and instantiate the specified API class."""
    module = importlib.import_module(CLASS_FILE_PATH_MAPPING[class_name])
    return getattr(module, class_name)()


def load_func_docs(class_name: str) -> dict[str, dict[str, Any]]:
    """Load BFCL's function documentation for a class.

    Returns a dict mapping function names to their full documentation,
    including rich descriptions and parameter schemas.
    """
    if class_name not in MULTI_TURN_FUNC_DOC_FILE_MAPPING:
        return {}

    doc_path = MULTI_TURN_FUNC_DOC_PATH / MULTI_TURN_FUNC_DOC_FILE_MAPPING[class_name]
    if not doc_path.exists():
        return {}

    docs = {}
    with open(doc_path) as f:
        for line in f:
            if line.strip():
                doc = json.loads(line)
                docs[doc["name"]] = doc
    return docs


def load_scenario_from_test(test_file: str, test_id: str, class_name: str) -> dict[str, Any]:
    """Load initial scenario configuration from a test file."""
    if not test_file or not test_id:
        return {}

    with open(test_file) as f:
        for line in f:
            if line.strip():
                entry = json.loads(line)
                if entry.get("id") == test_id:
                    config: dict[str, Any] = entry.get("initial_config", {}).get(class_name, {})
                    return config

    return {}


def patch_tool_with_func_doc(server: FastMCP, func_docs: dict[str, dict[str, Any]]) -> None:
    """Patch registered tools with BFCL's richer function documentation.

    FastMCP's introspection doesn't extract parameter descriptions from docstrings.
    BFCL provides pre-compiled JSON docs with proper descriptions, so we overlay them.
    """
    for tool_name, tool in server._tool_manager._tools.items():
        if tool_name not in func_docs:
            continue

        doc = func_docs[tool_name]

        # Patch tool description
        tool.description = doc.get("description", tool.description)

        # Patch parameter descriptions
        doc_params = doc.get("parameters", {}).get("properties", {})
        tool_params = tool.parameters.get("properties", {})

        for param_name, param_doc in doc_params.items():
            if param_name in tool_params and "description" in param_doc:
                tool_params[param_name]["description"] = param_doc["description"]


async def main() -> None:
    parser = argparse.ArgumentParser(description="MCP Server for BFCL API classes")
    parser.add_argument("class_name", help="API class name to load")
    parser.add_argument("test_file", nargs="?", help="Test file path (optional)")
    parser.add_argument("test_id", nargs="?", help="Test ID (optional)")
    args = parser.parse_args()

    class_name = args.class_name

    if class_name not in CLASS_FILE_PATH_MAPPING:
        print("Usage: python mcp_server.py <ClassName> [test_file.json test_id]", file=sys.stderr)
        print(f"Available classes: {', '.join(CLASS_FILE_PATH_MAPPING.keys())}", file=sys.stderr)
        sys.exit(1)

    # Load the API class
    api = load_api_class(class_name)
    print(f"Loaded {class_name}", file=sys.stderr)

    # Initialize scenario state if needed
    if hasattr(api, "_load_scenario") and class_name not in STATELESS_CLASSES:
        scenario = load_scenario_from_test(args.test_file, args.test_id, class_name)
        api._load_scenario(scenario)

    # Load BFCL's function documentation
    func_docs = load_func_docs(class_name)

    # Create server and register tools
    server = FastMCP(f"{class_name.lower()}-api")

    for method_name, method in inspect.getmembers(api, predicate=inspect.ismethod):
        if not method_name.startswith("_"):
            server.add_tool(method, name=method_name)

    # Patch tools with BFCL's richer descriptions
    patch_tool_with_func_doc(server, func_docs)

    await server.run_stdio_async()


if __name__ == "__main__":
    asyncio.run(main())
