#!/usr/bin/env python3
"""
MCP Server wrapper for AppWorld tasks.
Composes AppWorld's library components to support task-specific database state.
"""

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Import AppWorld's library components (from appworld.serve._mcp.serve pattern)
from appworld.apps.lib.models.db import get_db_home_path
from appworld.collections.api_docs import ApiDocCollection
from appworld.collections.apis import ApiCollection
from appworld.collections.models import ModelCollection
from appworld.task import Task
from mcp.server import ServerRequestContext
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolRequestParams, CallToolResult, ListToolsResult, PaginatedRequestParams, TextContent, Tool


@dataclass
class TaskConfig:
    """Configuration for an AppWorld task."""

    task: Task
    allowed_apps: tuple[str, ...]
    allowed_api_names: set[str] | None


@dataclass
class DatabasePaths:
    """Database paths for AppWorld task execution and persistence."""

    to_db_home_path: str
    from_db_home_path: str
    output_db_path: str


@dataclass
class AppWorldCollections:
    """AppWorld API and Model collections for task execution."""

    apis: ApiCollection
    model_collection: ModelCollection


def load_task_config(task_id: str) -> TaskConfig:
    """
    Load task and extract allowed apps/APIs configuration.

    Returns task configuration including allowed apps (excluding admin)
    and optional API name filtering from ALLOWED_APIS environment variable.
    """
    task = Task.load(task_id=task_id, load_ground_truth=False)
    allowed_apps = tuple([app for app in task.allowed_apps if app != "admin"])

    # Get API filtering from environment (set by APIPredictor)
    allowed_apis_env = os.getenv("ALLOWED_APIS", "")
    allowed_api_names = set(allowed_apis_env.split(",")) if allowed_apis_env else None

    return TaskConfig(
        task=task,
        allowed_apps=allowed_apps,
        allowed_api_names=allowed_api_names,
    )


def setup_database_paths(task_id: str, experiment_name: str) -> DatabasePaths:
    """
    Calculate database paths using AppWorld's architecture.

    Pattern: Load from task_input (disk) → Execute in task_output (memory) → Save to task_output (disk)

    - to_db_home_path: Memory path for task execution (:memory:task_output-{task_id})
    - from_db_home_path: Disk path for loading initial state (data/tasks/{task_id}/dbs/)
    - output_db_path: Disk path for saving results (experiments/outputs/{experiment_name}/tasks/{task_id}/dbs/)
    """
    return DatabasePaths(
        to_db_home_path=get_db_home_path(
            storage_type="memory",
            type="task_output",
            task_id=task_id,
        ),
        from_db_home_path=get_db_home_path(
            storage_type="disk",
            type="task_input",
            task_id=task_id,
        ),
        output_db_path=get_db_home_path(
            storage_type="disk",
            type="task_output",
            task_id=task_id,
            experiment_name=experiment_name,
        ),
    )


def load_collections(
    config: TaskConfig,
    db_paths: DatabasePaths,
) -> AppWorldCollections:
    """
    Load ApiCollection and ModelCollection with task-specific state.

    - ApiCollection: Provides callable APIs for task execution
    - ModelCollection: Manages database models for persistence
    """
    apis, _ = ApiCollection.load(
        to_db_home_path=db_paths.to_db_home_path,
        from_db_home_path=db_paths.from_db_home_path,
        date_and_time=config.task.datetime,
        random_seed=100,  # AppWorld's RANDOM_SEED constant
        show_api_response_schemas=True,
        load_apps=list(config.allowed_apps),
        remote_apis_url=None,  # Use local APIs
        raise_on_failure=False,
        wrap_response=True,
        unwrap_response=False,
        max_num_requests=None,
        skip_setup=False,  # Initialize task state from task_input
    )

    model_collection = ModelCollection.load(
        to_db_home_path=db_paths.to_db_home_path,
        from_db_home_path=db_paths.from_db_home_path,
        load_apps=[*config.allowed_apps, "admin", "supervisor"],
    )

    return AppWorldCollections(apis=apis, model_collection=model_collection)


def build_tool_schemas(
    allowed_apps: tuple[str, ...],
    allowed_api_names: set[str] | None,
) -> list[dict[str, Any]]:
    """
    Build and filter MCP tool schemas from AppWorld API documentation.

    Returns list of MCP tool schemas, optionally filtered by allowed_api_names.
    """
    api_docs_raw = ApiDocCollection.build(load_apps=allowed_apps).mcp()

    # Validate that we got a list from AppWorld's API
    if not isinstance(api_docs_raw, list):
        raise TypeError(f"Expected list from ApiDocCollection.mcp(), got {type(api_docs_raw)}")

    api_docs: list[dict[str, Any]] = api_docs_raw

    if allowed_api_names:
        api_docs = [doc for doc in api_docs if doc["name"] in allowed_api_names]

    return api_docs


def format_tool_response(response: dict[str, Any]) -> CallToolResult:
    """
    Format tool response in MCP 'both' format.

    Returns text content and structured data following AppWorld's pattern.
    This allows MCP clients to use either human-readable text or structured data.

    See: https://github.com/modelcontextprotocol/python-sdk#structured-output-support
    """
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(response, indent=2))],
        structured_content=response,
    )


def format_error_response(tool_name: str, error: Exception) -> CallToolResult:
    """
    Format error response in MCP 'both' format.

    Returns error message as both text and structured data with is_error flag.
    """
    error_msg = f"Error executing tool {tool_name}: {error}"
    print(error_msg, file=sys.stderr)
    return CallToolResult(
        content=[TextContent(type="text", text=error_msg)],
        structured_content={"error": str(error), "is_error": True},
        is_error=True,
    )


async def serve_task_mcp(task_id: str, experiment_name: str = "wags-benchmark") -> None:
    """Serve MCP for a specific AppWorld task with task-specific database state."""
    # Load configuration
    config = load_task_config(task_id)
    db_paths = setup_database_paths(task_id, experiment_name)

    # Load AppWorld components
    collections = load_collections(config, db_paths)
    api_docs = build_tool_schemas(config.allowed_apps, config.allowed_api_names)

    tools = [
        Tool(
            name=api_doc["name"],
            description=api_doc["description"],
            input_schema=api_doc["input_schema"],
            output_schema=api_doc["output_schema"],
        )
        for api_doc in api_docs
    ]

    async def list_tools(ctx: ServerRequestContext[Any], params: PaginatedRequestParams | None) -> ListToolsResult:
        """List available tools with AppWorld's MCP schemas."""
        return ListToolsResult(tools=tools)

    async def call_tool(ctx: ServerRequestContext[Any], params: CallToolRequestParams) -> CallToolResult:
        """Call AppWorld API and save databases on task completion."""
        name = params.name
        arguments = params.arguments or {}
        app_name = api_name = name
        if name.count("__") >= 1:
            app_name, api_name = name.split("__", 1)

        try:
            # Call API using AppWorld's convention
            response = collections.apis[app_name][api_name](**arguments)

            # Save databases on task completion
            if api_name == "complete_task" or name == "supervisor__complete_task":
                Path(db_paths.output_db_path).mkdir(parents=True, exist_ok=True)
                collections.model_collection.save(db_home_path=db_paths.output_db_path, save_model_hashes=True)

            return format_tool_response(response)
        except Exception as e:
            return format_error_response(name, e)

    # Create MCP server
    server_name = "AppWorld" if len(config.allowed_apps) > 1 else f"AppWorld: {config.allowed_apps[0].title()}"
    server = Server(server_name, version="1.0.0", on_list_tools=list_tools, on_call_tool=call_tool)

    # Run MCP server in stdio mode
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(notification_options=NotificationOptions()),
        )

    # Clean up database connections before exiting
    # This ensures SQLite connections are closed and the process can exit cleanly
    collections.model_collection.close()
    collections.apis.close()


async def main() -> None:
    parser = argparse.ArgumentParser(description="AppWorld MCP Server with task-specific state")
    parser.add_argument("task_id", help="AppWorld task ID (e.g., '82e2fac_1')")
    parser.add_argument(
        "--experiment-name",
        default="wags-benchmark",
        help=(
            "Experiment name for outputs "
            "(databases saved to experiments/outputs/{experiment_name}/tasks/{task_id}/dbs/)"
        ),
    )
    args = parser.parse_args()

    await serve_task_mcp(args.task_id, args.experiment_name)


if __name__ == "__main__":
    asyncio.run(main())
