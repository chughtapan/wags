#!/usr/bin/env python3
"""
MCP Server wrapper for BFCL API classes.
Exposes API methods as MCP tools with automatic introspection.

Experimental WAGS integration:
- If BFCL_EXTERNAL_FEEDBACK_ENABLED is set, we wrap the FastMCP server with a WAGS proxy
  and attach ExternalFeedbackMiddleware.
- Otherwise, behavior is identical to the original BFCL server.
"""

import argparse
import asyncio
import functools
import importlib
import inspect
import json
import os
import sys
from typing import Any

from bfcl_eval.constants.eval_config import MULTI_TURN_FUNC_DOC_PATH
from bfcl_eval.constants.executable_backend_config import (
    CLASS_FILE_PATH_MAPPING,
    MULTI_TURN_FUNC_DOC_FILE_MAPPING,
    STATELESS_CLASSES,
)
from mcp.server.fastmcp import FastMCP


def _env_flag_enabled(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


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


def _strip_return_annotation(method: Any) -> Any:
    """Remove the return annotation so FastMCP skips Pydantic output validation.

    Several BFCL API methods have return annotations like Dict[str, Union[str, bool]]
    that don't match their actual return values (e.g. booking_history is a nested dict,
    not str|bool). FastMCP builds a Pydantic output model from the annotation; when
    validation fails the tool response is dropped entirely, leaving an unanswered
    tool_call_id that causes OpenAI to reject the next request with a 400 error.

    IMPORTANT: we must set __signature__ explicitly rather than just overriding
    __annotations__. functools.wraps sets __wrapped__, and inspect.signature follows
    __wrapped__ back to the original function — bypassing __annotations__ entirely.
    Setting __signature__ directly takes precedence over __wrapped__ in inspect.signature.
    """
    @functools.wraps(method)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return method(*args, **kwargs)
    orig_sig = inspect.signature(method)
    wrapper.__signature__ = orig_sig.replace(return_annotation=inspect.Parameter.empty)
    return wrapper


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
    
    # Normalize class name to handle lowercase inputs like "vehiclecontrolapi"
    if class_name.lower() in {k.lower(): k for k in CLASS_FILE_PATH_MAPPING}.keys():
        for k in CLASS_FILE_PATH_MAPPING:
            if k.lower() == class_name.lower():
                class_name = k
                break


    if class_name not in CLASS_FILE_PATH_MAPPING:
        print("Usage: python mcp_server.py <ClassName> [test_file.json test_id]", file=sys.stderr)
        print(f"Available classes: {', '.join(CLASS_FILE_PATH_MAPPING.keys())}", file=sys.stderr)
        sys.exit(1)

    # Load the API class
    api = load_api_class(class_name)
    print(f"[mcp_server] Loaded {class_name}", file=sys.stderr, flush=True)

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
            server.add_tool(_strip_return_annotation(method), name=method_name)

    # Patch tools with BFCL's richer descriptions
    patch_tool_with_func_doc(server, func_docs)

    # --- Seed initial cwd for precondition_check triggers ---
    if hasattr(api, "_current_dir") and hasattr(api._current_dir, "name"):
        os.environ["BFCL_INITIAL_CWD"] = "/" + api._current_dir.name
        print(
            f"[mcp_server] BFCL_INITIAL_CWD=/{api._current_dir.name}",
            file=sys.stderr, flush=True,
        )

    # --- WAGS / external feedback experiment wiring ---
    feedback_enabled = _env_flag_enabled("BFCL_EXTERNAL_FEEDBACK_ENABLED", default=False)
    if feedback_enabled:
        print("[mcp_server] BFCL_EXTERNAL_FEEDBACK_ENABLED=ON -> starting WAGS proxy mode", file=sys.stderr, flush=True)

        # Import here so baseline BFCL runs don't depend on WAGS.
        from wags import create_proxy
        from wags.middleware.external_feedback import ExternalFeedbackMiddleware

        proxy = create_proxy(server, server_name=f"wags-{class_name.lower()}-proxy")

        # Config-file mode: BFCL_EXTERNAL_FEEDBACK_CONFIG points to a JSON rules
        # file.  Legacy mode: individual _TOOL / _MESSAGE / _N env vars are used.
        config_path = os.getenv("BFCL_EXTERNAL_FEEDBACK_CONFIG")
        if config_path:
            print(
                f"[mcp_server] Config-file mode: loading triggers from {config_path}",
                file=sys.stderr,
                flush=True,
            )
            middleware = ExternalFeedbackMiddleware(config_path=config_path)
        else:
            print(
                "[mcp_server] Legacy env-var mode: "
                f"tool={os.getenv('BFCL_EXTERNAL_FEEDBACK_TOOL', 'startEngine')} "
                f"n={os.getenv('BFCL_EXTERNAL_FEEDBACK_N', '1')}",
                file=sys.stderr,
                flush=True,
            )
            middleware = ExternalFeedbackMiddleware(
                target_tool_name=os.getenv("BFCL_EXTERNAL_FEEDBACK_TOOL", "startEngine"),
                warning_message=os.getenv(
                    "BFCL_EXTERNAL_FEEDBACK_MESSAGE",
                    "🚨 TEST WARNING: This tool call is intentionally blocked. Choose a different action and continue. 🚨",
                ),
                trigger_on_nth_call=int(os.getenv("BFCL_EXTERNAL_FEEDBACK_N", "1")),
            )

        # Attach middleware to the PROXY (not the underlying server).
        proxy.add_middleware(middleware)

        # Loud startup logging so we know wiring is correct.
        try:
            tool_count = len(server._tool_manager._tools)
            tool_names_preview = list(server._tool_manager._tools.keys())[:10]
        except Exception:
            tool_count = -1
            tool_names_preview = []

        print(f"[mcp_server] Base server tool count: {tool_count}", file=sys.stderr, flush=True)
        if tool_names_preview:
            print(f"[mcp_server] Base server tools (preview): {tool_names_preview}", file=sys.stderr, flush=True)

        print(f"[mcp_server] Proxy middleware count: {len(proxy.middleware)}", file=sys.stderr, flush=True)
        print(f"[mcp_server] Proxy middleware: {[type(m).__name__ for m in proxy.middleware]}", file=sys.stderr, flush=True)

        await proxy.run_stdio_async()
        return

    # --- Baseline behavior ---
    print("[mcp_server] BFCL_EXTERNAL_FEEDBACK_ENABLED=OFF -> starting baseline server mode", file=sys.stderr, flush=True)
    await server.run_stdio_async()


if __name__ == "__main__":
    asyncio.run(main())
