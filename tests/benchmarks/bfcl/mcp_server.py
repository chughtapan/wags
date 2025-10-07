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

from bfcl_eval.constants.executable_backend_config import (
    CLASS_FILE_PATH_MAPPING,
    STATELESS_CLASSES,
)
from mcp.server.fastmcp import FastMCP


def load_api_class(target_class_name: str) -> Any:
    """Load the specified API class dynamically and return instance."""
    if target_class_name not in CLASS_FILE_PATH_MAPPING:
        raise ValueError(f"Unknown class: {target_class_name}")

    # Load the class
    module = importlib.import_module(CLASS_FILE_PATH_MAPPING[target_class_name])
    instance = getattr(module, target_class_name)()
    return instance


def load_scenario_from_test(test_file: str, test_id: str, target_class_name: str) -> dict[str, Any]:
    """Load scenario configuration from test file."""
    scenario = {}
    if test_file and test_id:
        try:
            with open(test_file) as f:
                for line in f:
                    if line.strip():
                        entry = json.loads(line)
                        if entry.get("id") == test_id:
                            if "initial_config" in entry and target_class_name in entry["initial_config"]:
                                scenario = entry["initial_config"][target_class_name]
                            break
        except Exception as e:
            print(f"Warning: Could not load scenario: {e}", file=sys.stderr)
    return scenario


async def main() -> None:
    parser = argparse.ArgumentParser(description="MCP Server for BFCL API classes")
    parser.add_argument("class_name", help="API class name to load")
    parser.add_argument("test_file", nargs="?", help="Test file path (optional)")
    parser.add_argument("test_id", nargs="?", help="Test ID (optional)")

    args = parser.parse_args()

    target_class_name = args.class_name

    if target_class_name not in CLASS_FILE_PATH_MAPPING:
        print("Usage: python api_server.py <ClassName> [test_file.json test_id]", file=sys.stderr)
        print(f"Available classes: {', '.join(CLASS_FILE_PATH_MAPPING.keys())}", file=sys.stderr)
        sys.exit(1)

    try:
        api_instance = load_api_class(target_class_name)
        print(f"Successfully loaded {target_class_name}", file=sys.stderr)

        # Load scenario if needed
        if hasattr(api_instance, "_load_scenario") and target_class_name not in STATELESS_CLASSES:
            scenario = load_scenario_from_test(args.test_file, args.test_id, target_class_name)
            api_instance._load_scenario(scenario)
    except Exception as e:
        print(f"Error loading {target_class_name}: {e}", file=sys.stderr)
        sys.exit(1)

    # Create FastMCP server
    server = FastMCP(f"{target_class_name.lower()}-api")

    # Register all API methods as tools
    for method_name, method in inspect.getmembers(api_instance, predicate=inspect.ismethod):
        if not method_name.startswith("_"):
            server.add_tool(method, name=method_name)

    # Run the server
    await server.run_stdio_async()


if __name__ == "__main__":
    asyncio.run(main())
