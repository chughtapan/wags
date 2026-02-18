"""Unit tests for ExternalFeedbackMiddleware."""

import pytest
from fastmcp.server.middleware.middleware import MiddlewareContext
from fastmcp.tools.tool import ToolResult
from mcp.types import CallToolRequestParams

from wags.middleware.external_feedback import ExternalFeedbackMiddleware


def _tool_result_text(result: ToolResult) -> str:
    blocks = result.to_mcp_result()
    if isinstance(blocks, tuple):
        blocks = blocks[0]
    return " ".join(getattr(block, "text", str(block)) for block in blocks)


@pytest.mark.asyncio
async def test_blocks_first_target_call_and_prints(capsys: pytest.CaptureFixture[str]) -> None:
    middleware = ExternalFeedbackMiddleware(
        target_tool_name="startEngine",
        warning_message="blocked",
        trigger_on_nth_call=1,
    )

    context = MiddlewareContext(message=CallToolRequestParams(name="startEngine", arguments={}), method="tools/call")

    async def call_next(_: MiddlewareContext[CallToolRequestParams]) -> ToolResult:
        return ToolResult(content="tool-executed")

    result = await middleware.on_call_tool(context, call_next)
    output = capsys.readouterr().err

    assert "EXTERNAL FEEDBACK TRIGGERED" in _tool_result_text(result)
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

    async def call_next(_: MiddlewareContext[CallToolRequestParams]) -> ToolResult:
        return ToolResult(content="tool-executed")

    first_result = await middleware.on_call_tool(context, call_next)
    second_result = await middleware.on_call_tool(context, call_next)

    assert "EXTERNAL FEEDBACK TRIGGERED" in _tool_result_text(first_result)
    assert _tool_result_text(second_result) == "tool-executed"


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

    async def call_next(_: MiddlewareContext[CallToolRequestParams]) -> ToolResult:
        return ToolResult(content="tool-executed")

    result = await middleware.on_call_tool(context, call_next)
    assert "EXTERNAL FEEDBACK TRIGGERED" in _tool_result_text(result)
