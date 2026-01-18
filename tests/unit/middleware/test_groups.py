"""Unit tests for GroupsMiddleware."""

import json
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastmcp.exceptions import ToolError
from fastmcp.server.middleware.middleware import MiddlewareContext
from fastmcp.tools.tool import Tool
from mcp.types import CallToolRequestParams, ListToolsRequest

from wags.middleware.groups import (
    GROUPS_META_KEY,
    GroupDefinition,
    GroupsMiddleware,
    in_group,
)


async def call_meta_tool(middleware: GroupsMiddleware, tool_name: str, groups: list[str]) -> dict[str, Any]:
    """Helper to call enable_tools/disable_tools and return structured result."""
    message = CallToolRequestParams(name=tool_name, arguments={"groups": groups})
    context = MiddlewareContext(message=message)
    result = await middleware.on_call_tool(context, AsyncMock())
    mcp_result = result.to_mcp_result()
    if isinstance(mcp_result, tuple):
        return cast(dict[str, Any], mcp_result[1])
    return cast(dict[str, Any], json.loads(mcp_result[0].text))


class TestInGroupDecorator:
    def test_single_group(self) -> None:
        @in_group("issues")
        async def handler() -> None:
            pass

        assert getattr(handler, "__groups__") == {"issues"}

    def test_stacking_decorators(self) -> None:
        @in_group("issues")
        @in_group("communications")
        async def handler() -> None:
            pass

        assert getattr(handler, "__groups__") == {"issues", "communications"}

    def test_multiple_groups_single_call(self) -> None:
        @in_group("issues", "communications")
        async def handler() -> None:
            pass

        assert getattr(handler, "__groups__") == {"issues", "communications"}


class TestGroupDefinition:
    def test_basic(self) -> None:
        defn = GroupDefinition(description="Test group")
        assert defn.description == "Test group"
        assert defn.parent is None

    def test_with_parent(self) -> None:
        defn = GroupDefinition(description="Child group", parent="parent")
        assert defn.parent == "parent"


class TestGroupsMiddlewareInit:
    def test_unknown_parent_raises_error(self) -> None:
        with pytest.raises(ValueError, match="unknown parent 'unknown'"):
            GroupsMiddleware(groups={"child": GroupDefinition(description="Child", parent="unknown")})

    def test_handler_unknown_group_raises_error(self) -> None:
        class Handlers:
            @in_group("unknown_group")
            async def handler(self) -> None:
                pass

        with pytest.raises(ValueError, match="references unknown group"):
            GroupsMiddleware(
                groups={"issues": GroupDefinition(description="Issues")},
                handlers=Handlers(),
            )

    def test_initial_groups_unknown(self) -> None:
        with pytest.raises(ValueError, match="Unknown group: unknown"):
            GroupsMiddleware(
                groups={"issues": GroupDefinition(description="Issues")},
                initial_groups=["unknown"],
            )

    def test_initial_groups_child_before_parent(self) -> None:
        with pytest.raises(ValueError, match="parent 'comms' not enabled"):
            GroupsMiddleware(
                groups={
                    "comms": GroupDefinition(description="Communications"),
                    "email": GroupDefinition(description="Email", parent="comms"),
                },
                initial_groups=["email"],
            )


class TestGroupHierarchy:
    def test_build_hierarchy(self) -> None:
        middleware = GroupsMiddleware(
            groups={
                "comms": GroupDefinition(description="Communications"),
                "email": GroupDefinition(description="Email", parent="comms"),
                "calendar": GroupDefinition(description="Calendar", parent="comms"),
            }
        )
        assert middleware._children_map == {"comms": {"email", "calendar"}}

    def test_get_all_descendants(self) -> None:
        middleware = GroupsMiddleware(
            groups={
                "root": GroupDefinition(description="Root"),
                "level1": GroupDefinition(description="Level 1", parent="root"),
                "level2": GroupDefinition(description="Level 2", parent="level1"),
                "level2b": GroupDefinition(description="Level 2b", parent="level1"),
            }
        )
        assert middleware._get_all_descendants("root") == {
            "level1",
            "level2",
            "level2b",
        }

    def test_visibility(self) -> None:
        middleware = GroupsMiddleware(
            groups={
                "root": GroupDefinition(description="Root"),
                "child": GroupDefinition(description="Child", parent="root"),
            }
        )
        assert middleware._is_group_visible("root") is True
        assert middleware._is_group_visible("child") is False

        middleware._enable_group("root")
        assert middleware._is_group_visible("child") is True


class TestHandlerScanning:
    def test_finds_decorated_methods(self) -> None:
        class Handlers:
            @in_group("issues")
            async def create_issue(self) -> None:
                pass

            @in_group("repo")
            async def create_repo(self) -> None:
                pass

        middleware = GroupsMiddleware(
            groups={
                "issues": GroupDefinition(description="Issues"),
                "repo": GroupDefinition(description="Repo"),
            },
            handlers=Handlers(),
        )
        assert middleware._tool_to_groups == {
            "create_issue": {"issues"},
            "create_repo": {"repo"},
        }

    def test_undecorated_methods_ignored(self) -> None:
        class Handlers:
            @in_group("issues")
            async def decorated(self) -> None:
                pass

            async def undecorated(self) -> None:
                pass

        middleware = GroupsMiddleware(
            groups={"issues": GroupDefinition(description="Issues")},
            handlers=Handlers(),
        )
        assert "undecorated" not in middleware._tool_to_groups


class TestToolFiltering:
    def test_get_enabled_tools(self) -> None:
        class Handlers:
            @in_group("issues")
            async def create_issue(self) -> None:
                pass

            @in_group("repo")
            async def create_repo(self) -> None:
                pass

        middleware = GroupsMiddleware(
            groups={
                "issues": GroupDefinition(description="Issues"),
                "repo": GroupDefinition(description="Repo"),
            },
            handlers=Handlers(),
            initial_groups=["issues"],
        )
        assert middleware._get_enabled_tools() == {"create_issue"}

    def test_tool_in_multiple_groups(self) -> None:
        class Handlers:
            @in_group("issues")
            @in_group("communications")
            async def add_comment(self) -> None:
                pass

        middleware = GroupsMiddleware(
            groups={
                "issues": GroupDefinition(description="Issues"),
                "communications": GroupDefinition(description="Communications"),
            },
            handlers=Handlers(),
        )

        middleware._enable_group("issues")
        assert middleware._get_enabled_tools() == {"add_comment"}

        middleware._enable_group("communications")
        assert middleware._get_enabled_tools() == {"add_comment"}

    def test_count_tools_if_enabled(self) -> None:
        class Handlers:
            @in_group("issues")
            async def create_issue(self) -> None:
                pass

            @in_group("issues")
            async def list_issues(self) -> None:
                pass

            @in_group("repo")
            async def create_repo(self) -> None:
                pass

        middleware = GroupsMiddleware(
            groups={
                "issues": GroupDefinition(description="Issues"),
                "repo": GroupDefinition(description="Repo"),
            },
            handlers=Handlers(),
        )
        assert middleware._count_tools_if_enabled("issues") == 2
        assert middleware._count_tools_if_enabled("repo") == 1


class TestEnableTools:
    @pytest.mark.asyncio
    async def test_enable_root_group(self) -> None:
        middleware = GroupsMiddleware(groups={"issues": GroupDefinition(description="Issues")})
        result = await call_meta_tool(middleware, "enable_tools", ["issues"])
        assert result["enabled"] == ["issues"]
        assert "issues" in middleware._enabled_groups

    @pytest.mark.asyncio
    async def test_child_before_parent_fails(self) -> None:
        middleware = GroupsMiddleware(
            groups={
                "comms": GroupDefinition(description="Communications"),
                "email": GroupDefinition(description="Email", parent="comms"),
            }
        )
        result = await call_meta_tool(middleware, "enable_tools", ["email"])
        assert any("not visible" in e for e in result["errors"])
        assert "email" not in middleware._enabled_groups

    @pytest.mark.asyncio
    async def test_child_after_parent(self) -> None:
        middleware = GroupsMiddleware(
            groups={
                "comms": GroupDefinition(description="Communications"),
                "email": GroupDefinition(description="Email", parent="comms"),
            }
        )
        await call_meta_tool(middleware, "enable_tools", ["comms"])
        result = await call_meta_tool(middleware, "enable_tools", ["email"])
        assert result["enabled"] == ["email"]

    @pytest.mark.asyncio
    async def test_unknown_group(self) -> None:
        middleware = GroupsMiddleware(groups={"issues": GroupDefinition(description="Issues")})
        result = await call_meta_tool(middleware, "enable_tools", ["unknown"])
        assert "Unknown group: unknown" in result["errors"]

    @pytest.mark.asyncio
    async def test_already_enabled(self) -> None:
        middleware = GroupsMiddleware(
            groups={"issues": GroupDefinition(description="Issues")},
            initial_groups=["issues"],
        )
        result = await call_meta_tool(middleware, "enable_tools", ["issues"])
        assert "Group already enabled: issues" in result["errors"]

    @pytest.mark.asyncio
    async def test_max_tools_enforcement(self) -> None:
        class Handlers:
            @in_group("issues")
            async def issue1(self) -> None:
                pass

            @in_group("issues")
            async def issue2(self) -> None:
                pass

            @in_group("repo")
            async def repo1(self) -> None:
                pass

        middleware = GroupsMiddleware(
            groups={
                "issues": GroupDefinition(description="Issues"),
                "repo": GroupDefinition(description="Repo"),
            },
            handlers=Handlers(),
            initial_groups=["issues"],
            max_tools=2,
        )
        result = await call_meta_tool(middleware, "enable_tools", ["repo"])
        assert any("exceeding max_tools=2" in e for e in result["errors"])

    @pytest.mark.asyncio
    async def test_available_groups_in_response(self) -> None:
        middleware = GroupsMiddleware(
            groups={
                "comms": GroupDefinition(description="Communications"),
                "email": GroupDefinition(description="Email", parent="comms"),
                "calendar": GroupDefinition(description="Calendar", parent="comms"),
            }
        )
        result = await call_meta_tool(middleware, "enable_tools", ["comms"])
        assert set(result["available_groups"]) == {"email", "calendar"}


class TestDisableTools:
    @pytest.mark.asyncio
    async def test_disable_leaf_group(self) -> None:
        middleware = GroupsMiddleware(
            groups={
                "comms": GroupDefinition(description="Communications"),
                "email": GroupDefinition(description="Email", parent="comms"),
            },
            initial_groups=["comms", "email"],
        )
        result = await call_meta_tool(middleware, "disable_tools", ["email"])
        assert "email" in result["disabled"]
        assert "email" not in middleware._enabled_groups
        assert "comms" in middleware._enabled_groups

    @pytest.mark.asyncio
    async def test_parent_cascades_to_children(self) -> None:
        middleware = GroupsMiddleware(
            groups={
                "comms": GroupDefinition(description="Communications"),
                "email": GroupDefinition(description="Email", parent="comms"),
                "calendar": GroupDefinition(description="Calendar", parent="comms"),
            },
            initial_groups=["comms", "email", "calendar"],
        )
        result = await call_meta_tool(middleware, "disable_tools", ["comms"])
        assert set(result["disabled"]) == {"comms", "email", "calendar"}
        assert len(middleware._enabled_groups) == 0

    @pytest.mark.asyncio
    async def test_unknown_group(self) -> None:
        middleware = GroupsMiddleware(groups={"issues": GroupDefinition(description="Issues")})
        result = await call_meta_tool(middleware, "disable_tools", ["unknown"])
        assert "Unknown group: unknown" in result["errors"]

    @pytest.mark.asyncio
    async def test_not_enabled(self) -> None:
        middleware = GroupsMiddleware(groups={"issues": GroupDefinition(description="Issues")})
        result = await call_meta_tool(middleware, "disable_tools", ["issues"])
        assert "Group not enabled: issues" in result["errors"]


class TestOnListTools:
    @pytest.mark.asyncio
    async def test_filters_to_enabled_groups(self) -> None:
        class Handlers:
            @in_group("issues")
            async def create_issue(self) -> None:
                pass

            @in_group("repo")
            async def create_repo(self) -> None:
                pass

        middleware = GroupsMiddleware(
            groups={
                "issues": GroupDefinition(description="Issues"),
                "repo": GroupDefinition(description="Repo"),
            },
            handlers=Handlers(),
            initial_groups=["issues"],
        )

        async def mock_call_next(context: MiddlewareContext[ListToolsRequest]) -> list[Tool]:
            return [
                Tool.from_function(lambda: None, name="create_issue", description=""),
                Tool.from_function(lambda: None, name="create_repo", description=""),
            ]

        context = MiddlewareContext(message=ListToolsRequest())
        result = await middleware.on_list_tools(context, mock_call_next)
        tool_names = {t.name for t in result}

        assert "enable_tools" in tool_names
        assert "disable_tools" in tool_names
        assert "create_issue" in tool_names
        assert "create_repo" not in tool_names

    @pytest.mark.asyncio
    async def test_discovers_groups_from_metadata(self) -> None:
        middleware = GroupsMiddleware(
            groups={"issues": GroupDefinition(description="Issues")},
            initial_groups=["issues"],
        )

        mock_tool = Tool.from_function(
            lambda: None,
            name="create_issue",
            description="",
            meta={GROUPS_META_KEY: ["issues"]},
        )

        async def mock_call_next(context: MiddlewareContext[ListToolsRequest]) -> list[Tool]:
            return [mock_tool]

        context = MiddlewareContext(message=ListToolsRequest())
        result = await middleware.on_list_tools(context, mock_call_next)
        assert "create_issue" in {t.name for t in result}


class TestOnCallTool:
    @pytest.mark.asyncio
    async def test_meta_tool_returns_structured_content(self) -> None:
        middleware = GroupsMiddleware(groups={"issues": GroupDefinition(description="Issues")})
        message = CallToolRequestParams(name="enable_tools", arguments={"groups": ["issues"]})
        context = MiddlewareContext(message=message)

        async def should_not_call(context: MiddlewareContext[CallToolRequestParams]) -> Any:
            raise AssertionError("Should not call next for meta-tool")

        result = await middleware.on_call_tool(context, should_not_call)
        mcp_result = result.to_mcp_result()
        assert isinstance(mcp_result, tuple)
        assert mcp_result[1]["enabled"] == ["issues"]

    @pytest.mark.asyncio
    async def test_enabled_tool_passes_through(self) -> None:
        class Handlers:
            @in_group("issues")
            async def create_issue(self) -> None:
                pass

        middleware = GroupsMiddleware(
            groups={"issues": GroupDefinition(description="Issues")},
            handlers=Handlers(),
            initial_groups=["issues"],
        )
        message = CallToolRequestParams(name="create_issue", arguments={})
        context = MiddlewareContext(message=message)

        mock_call_next = AsyncMock(return_value="success")
        result = await middleware.on_call_tool(context, mock_call_next)

        mock_call_next.assert_called_once()
        assert result == "success"

    @pytest.mark.asyncio
    async def test_disabled_tool_raises_error(self) -> None:
        class Handlers:
            @in_group("issues")
            async def create_issue(self) -> None:
                pass

        middleware = GroupsMiddleware(
            groups={"issues": GroupDefinition(description="Issues")},
            handlers=Handlers(),
        )
        message = CallToolRequestParams(name="create_issue", arguments={})
        context = MiddlewareContext(message=message)

        with pytest.raises(ToolError) as exc_info:
            await middleware.on_call_tool(context, AsyncMock())

        assert "not available" in str(exc_info.value)
        assert "enable_tools" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_error_includes_group_hint(self) -> None:
        class Handlers:
            @in_group("issues")
            async def create_issue(self) -> None:
                pass

        middleware = GroupsMiddleware(
            groups={"issues": GroupDefinition(description="Issues")},
            handlers=Handlers(),
        )
        message = CallToolRequestParams(name="create_issue", arguments={})
        context = MiddlewareContext(message=message)

        with pytest.raises(ToolError) as exc_info:
            await middleware.on_call_tool(context, AsyncMock())

        assert "enable_tools(groups=['issues'])" in str(exc_info.value)


class TestToolsListChangedNotification:
    @pytest.mark.asyncio
    async def test_sent_on_enable(self) -> None:
        middleware = GroupsMiddleware(groups={"issues": GroupDefinition(description="Issues")})
        mock_session = MagicMock()
        mock_session.send_tool_list_changed = AsyncMock()
        mock_fastmcp_context = MagicMock()
        mock_fastmcp_context.session = mock_session

        message = CallToolRequestParams(name="enable_tools", arguments={"groups": ["issues"]})
        context = MiddlewareContext(message=message, fastmcp_context=mock_fastmcp_context)

        await middleware.on_call_tool(context, AsyncMock())
        mock_session.send_tool_list_changed.assert_called_once()

    @pytest.mark.asyncio
    async def test_sent_on_disable(self) -> None:
        middleware = GroupsMiddleware(
            groups={"issues": GroupDefinition(description="Issues")},
            initial_groups=["issues"],
        )
        mock_session = MagicMock()
        mock_session.send_tool_list_changed = AsyncMock()
        mock_fastmcp_context = MagicMock()
        mock_fastmcp_context.session = mock_session

        message = CallToolRequestParams(name="disable_tools", arguments={"groups": ["issues"]})
        context = MiddlewareContext(message=message, fastmcp_context=mock_fastmcp_context)

        await middleware.on_call_tool(context, AsyncMock())
        mock_session.send_tool_list_changed.assert_called_once()

    @pytest.mark.asyncio
    async def test_not_sent_when_no_change(self) -> None:
        middleware = GroupsMiddleware(
            groups={"issues": GroupDefinition(description="Issues")},
            initial_groups=["issues"],
        )
        mock_session = MagicMock()
        mock_session.send_tool_list_changed = AsyncMock()
        mock_fastmcp_context = MagicMock()
        mock_fastmcp_context.session = mock_session

        message = CallToolRequestParams(name="enable_tools", arguments={"groups": ["issues"]})
        context = MiddlewareContext(message=message, fastmcp_context=mock_fastmcp_context)

        await middleware.on_call_tool(context, AsyncMock())
        mock_session.send_tool_list_changed.assert_not_called()


class TestDynamicDescriptions:
    def test_enable_tools_shows_root_groups(self) -> None:
        middleware = GroupsMiddleware(
            groups={
                "issues": GroupDefinition(description="Issue tracking"),
                "repo": GroupDefinition(description="Repository management"),
            }
        )
        desc = middleware._build_enable_tools_description()
        assert "issues: Issue tracking" in desc
        assert "repo: Repository management" in desc

    def test_enable_tools_shows_enabled_status(self) -> None:
        middleware = GroupsMiddleware(
            groups={"issues": GroupDefinition(description="Issue tracking")},
            initial_groups=["issues"],
        )
        desc = middleware._build_enable_tools_description()
        assert "(enabled)" in desc

    def test_enable_tools_shows_max_tools(self) -> None:
        middleware = GroupsMiddleware(
            groups={"issues": GroupDefinition(description="Issue tracking")},
            max_tools=10,
        )
        desc = middleware._build_enable_tools_description()
        assert "Max tools limit: 10" in desc

    def test_enable_tools_shows_children_after_parent_enabled(self) -> None:
        middleware = GroupsMiddleware(
            groups={
                "comms": GroupDefinition(description="Communications"),
                "email": GroupDefinition(description="Email", parent="comms"),
            }
        )
        assert "email" not in middleware._build_enable_tools_description()

        middleware._enable_group("comms")
        assert "email: Email" in middleware._build_enable_tools_description()

    def test_disable_tools_shows_enabled(self) -> None:
        middleware = GroupsMiddleware(
            groups={
                "issues": GroupDefinition(description="Issue tracking"),
                "repo": GroupDefinition(description="Repository"),
            },
            initial_groups=["issues"],
        )
        desc = middleware._build_disable_tools_description()
        assert "issues: Issue tracking" in desc
        assert "repo" not in desc

    def test_disable_tools_empty_when_none_enabled(self) -> None:
        middleware = GroupsMiddleware(groups={"issues": GroupDefinition(description="Issue tracking")})
        desc = middleware._build_disable_tools_description()
        assert "No groups currently enabled" in desc
