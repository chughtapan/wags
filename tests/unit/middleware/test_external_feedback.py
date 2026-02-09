"""Unit tests for ExternalFeedbackMiddleware."""

from typing import Any

import pytest
from fastmcp.server.middleware.middleware import MiddlewareContext
from mcp.types import CallToolRequestParams

from wags.middleware.external_feedback import ExternalFeedbackMiddleware


@pytest.mark.asyncio
async def test_blocks_first_target_call_and_prints(capsys: pytest.CaptureFixture[str]) -> None:
    middleware = ExternalFeedbackMiddleware(
        target_tool_name="startEngine",
        warning_message="blocked",
        trigger_on_nth_call=1,
    )

    context = MiddlewareContext(message=CallToolRequestParams(name="startEngine", arguments={}), method="tools/call")

    async def call_next(_: MiddlewareContext[CallToolRequestParams]) -> Any:
        return "tool-executed"

    result = await middleware.on_call_tool(context, call_next)
    output = capsys.readouterr().out

    assert "EXTERNAL FEEDBACK TRIGGERED" in result
    assert "Tool call #1: startEngine" in output
    assert "TRIGGERED WARNING - BLOCKING TOOL CALL" in output


@pytest.mark.asyncio
async def test_allows_second_target_call() -> None:
    middleware = ExternalFeedbackMiddleware(
        target_tool_name="startEngine",
        warning_message="blocked",
        trigger_on_nth_call=1,
    )

    context = MiddlewareContext(message=CallToolRequestParams(name="startEngine", arguments={}), method="tools/call")

    async def call_next(_: MiddlewareContext[CallToolRequestParams]) -> Any:
        return "tool-executed"

    first_result = await middleware.on_call_tool(context, call_next)
    second_result = await middleware.on_call_tool(context, call_next)

    assert "EXTERNAL FEEDBACK TRIGGERED" in first_result
    assert second_result == "tool-executed"


@pytest.mark.asyncio
async def test_matches_namespaced_and_snake_case_variants() -> None:
    middleware = ExternalFeedbackMiddleware(
        target_tool_name="start_engine",
        warning_message="blocked",
        trigger_on_nth_call=1,
    )

    context = MiddlewareContext(
        message=CallToolRequestParams(name="vehiclecontrolapi__startEngine", arguments={}),
        method="tools/call",
    )

    async def call_next(_: MiddlewareContext[CallToolRequestParams]) -> Any:
        return "tool-executed"

    result = await middleware.on_call_tool(context, call_next)
    assert "EXTERNAL FEEDBACK TRIGGERED" in result
