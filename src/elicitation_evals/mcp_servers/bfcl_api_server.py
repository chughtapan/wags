#!/usr/bin/env python3
"""
MCP Server wrapper for BFCL API classes.
Exposes API methods as MCP tools with proper documentation.
"""

import asyncio
import json
import sys
import os
import importlib
import inspect
from typing import Any, Dict, List

# Add path to BFCL submodule
bfcl_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'bfcl', 'berkeley-function-call-leaderboard')
sys.path.insert(0, bfcl_path)
from bfcl_eval.constants.executable_backend_config import (
    CLASS_FILE_PATH_MAPPING, 
    STATELESS_CLASSES, 
    MULTI_TURN_FUNC_DOC_FILE_MAPPING
)
from mcp.server.models import InitializationOptions
from mcp.server import NotificationOptions, Server
from mcp.types import TextContent, Tool

api_instance = None
class_name = None

def load_api_class(target_class_name: str):
    """Load the specified API class dynamically."""
    global api_instance, class_name
    
    if target_class_name not in CLASS_FILE_PATH_MAPPING:
        raise ValueError(f"Unknown class: {target_class_name}")
    
    module = importlib.import_module(CLASS_FILE_PATH_MAPPING[target_class_name])
    api_instance = getattr(module, target_class_name)()
    class_name = target_class_name

def load_function_docs(class_name: str) -> Dict[str, Dict]:
    """Load function documentation from JSON files."""
    if class_name not in MULTI_TURN_FUNC_DOC_FILE_MAPPING:
        return {}
    
    doc_file = MULTI_TURN_FUNC_DOC_FILE_MAPPING[class_name]
    doc_path = os.path.join(bfcl_path, 'bfcl_eval', 'data', 'multi_turn_func_doc', doc_file)
    
    func_docs = {}
    try:
        with open(doc_path, 'r') as f:
            for line in f:
                if line.strip():
                    func_doc = json.loads(line)
                    func_docs[func_doc['name']] = func_doc
    except Exception as e:
        print(f"Warning: Could not load function docs: {e}", file=sys.stderr)
    
    return func_docs

def convert_bfcl_param_to_mcp(bfcl_param: Dict) -> Dict:
    """Convert BFCL parameter format to MCP schema format."""
    mcp_param = {"type": "object", "properties": {}, "required": []}
    
    if "properties" in bfcl_param:
        for prop_name, prop_def in bfcl_param["properties"].items():
            mcp_param["properties"][prop_name] = {
                "type": prop_def["type"],
                "description": prop_def.get("description", "")
            }
            if prop_def["type"] == "array" and "items" in prop_def:
                mcp_param["properties"][prop_name]["items"] = prop_def["items"]
            if "default" in prop_def:
                mcp_param["properties"][prop_name]["default"] = prop_def["default"]
    
    if "required" in bfcl_param:
        mcp_param["required"] = bfcl_param["required"]
    
    return mcp_param

def get_api_tools() -> List[Tool]:
    """Get all available API methods as MCP tools using proper documentation."""
    if not api_instance or not class_name:
        return []
    
    func_docs = load_function_docs(class_name)
    tools = []
    
    for method_name, method in inspect.getmembers(api_instance, predicate=inspect.ismethod):
        if method_name.startswith('_'):
            continue
        
        if method_name in func_docs:
            func_doc = func_docs[method_name]
            description = func_doc.get("description", f"Call {method_name}")
            parameters = convert_bfcl_param_to_mcp(func_doc.get("parameters", {}))
        else:
            # Fallback to introspection
            sig = inspect.signature(method)
            description = inspect.getdoc(method) or f"Call {method_name}"
            parameters = {"type": "object", "properties": {}, "required": []}
            
            for param_name, param in sig.parameters.items():
                param_type = "string"
                if param.annotation != inspect.Parameter.empty:
                    if param.annotation == int:
                        param_type = "integer"
                    elif param.annotation == bool:
                        param_type = "boolean"
                    elif param.annotation in (list, List):
                        param_type = "array"
                    elif param.annotation in (dict, Dict):
                        param_type = "object"
                
                parameters["properties"][param_name] = {
                    "type": param_type,
                    "description": f"Parameter {param_name}"
                }
                if param.default == inspect.Parameter.empty:
                    parameters["required"].append(param_name)
        
        tools.append(Tool(name=method_name, description=description, inputSchema=parameters))
    
    return tools

async def call_api_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
    """Handle API tool calls by intercepting method calls."""
    try:
        if not api_instance:
            raise ValueError("No API class loaded")
        if not hasattr(api_instance, name):
            raise ValueError(f"Method {name} not found")
        
        result = getattr(api_instance, name)(**arguments)
        return [TextContent(type="text", text=json.dumps(result))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]

async def main():
    if len(sys.argv) < 2:
        print("Usage: python api_server.py <ClassName> [test_file.json test_id]", file=sys.stderr)
        print(f"Available classes: {', '.join(CLASS_FILE_PATH_MAPPING.keys())}", file=sys.stderr)
        sys.exit(1)
    
    target_class_name = sys.argv[1]
    test_file = sys.argv[2] if len(sys.argv) > 2 else None
    test_id = sys.argv[3] if len(sys.argv) > 3 else None
    
    try:
        load_api_class(target_class_name)
        
        if hasattr(api_instance, '_load_scenario') and target_class_name not in STATELESS_CLASSES:
            scenario = {}
            if test_file and test_id:
                try:
                    with open(test_file, 'r') as f:
                        for line in f:
                            if line.strip():
                                entry = json.loads(line)
                                if entry.get('id') == test_id:
                                    if 'initial_config' in entry and target_class_name in entry['initial_config']:
                                        scenario = entry['initial_config'][target_class_name]
                                    break
                except Exception as e:
                    print(f"Warning: Could not load scenario: {e}", file=sys.stderr)
            api_instance._load_scenario(scenario)
    except Exception as e:
        print(f"Error loading {target_class_name}: {e}", file=sys.stderr)
        sys.exit(1)
    
    server = Server(f"{target_class_name.lower()}-api")

    @server.list_tools()
    async def handle_list_tools() -> list[Tool]:
        return get_api_tools()

    @server.call_tool()
    async def handle_call_tool(name: str, arguments: dict) -> list[TextContent]:
        return await call_api_tool(name, arguments or {})

    # Run the server
    from mcp.server.stdio import stdio_server
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name=f"{target_class_name.lower()}-api",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )

if __name__ == "__main__":
    asyncio.run(main())