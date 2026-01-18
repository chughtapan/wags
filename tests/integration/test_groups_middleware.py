"""Integration tests for GroupsMiddleware with FastMCP."""

from typing import Any

import pytest
from fastmcp import FastMCP
from fastmcp.client import Client
from fastmcp.exceptions import ToolError

from wags import create_proxy
from wags.middleware.groups import (
    GROUPS_META_KEY,
    GroupDefinition,
    GroupsMiddleware,
    in_group,
)


class IssuesHandlers:
    """Handler stubs for issues-only tests."""

    @in_group("issues")
    async def create_issue(self, owner: str, repo: str, title: str) -> None:
        pass


class GitHubHandlers:
    """Handler stubs that define group membership via decorators."""

    @in_group("issues")
    async def create_issue(self, owner: str, repo: str, title: str) -> None:
        pass  # Stub - actual execution by proxied server

    @in_group("issues")
    async def list_issues(self, owner: str, repo: str) -> None:
        pass

    @in_group("repo")
    async def create_repository(self, name: str) -> None:
        pass


@pytest.mark.asyncio
class TestGroupsMiddlewareIntegration:
    """Integration tests for GroupsMiddleware with proxy architecture."""

    async def test_middleware_filters_tools_by_group(self) -> None:
        """Test GroupsMiddleware filters tools by enabled groups."""
        # Create backend server with actual tools
        backend = FastMCP("github-backend")

        @backend.tool
        async def create_issue(owner: str, repo: str, title: str) -> dict[str, Any]:
            return {"owner": owner, "repo": repo, "title": title}

        @backend.tool
        async def list_issues(owner: str, repo: str) -> list[dict[str, Any]]:
            return [{"id": 1, "title": "Issue 1"}]

        @backend.tool
        async def create_repository(name: str) -> dict[str, Any]:
            return {"name": name}

        # Create proxy with middleware
        handlers = GitHubHandlers()
        proxy = create_proxy(backend, server_name="github-proxy")
        proxy.add_middleware(
            GroupsMiddleware(
                groups={
                    "issues": GroupDefinition(description="Issue tracking"),
                    "repo": GroupDefinition(description="Repository management"),
                },
                handlers=handlers,
                initial_groups=["issues"],
            )
        )

        async with Client(proxy) as client:
            tools = await client.list_tools()
            tool_names = {t.name for t in tools}

            # Meta-tools always present
            assert "enable_tools" in tool_names
            assert "disable_tools" in tool_names

            # Issues tools present (group enabled)
            assert "create_issue" in tool_names
            assert "list_issues" in tool_names

            # Repo tools not present (group not enabled)
            assert "create_repository" not in tool_names

    async def test_enabled_tool_call_passes_through(self) -> None:
        """Test calling an enabled tool passes through to backend."""
        backend = FastMCP("backend")

        @backend.tool
        async def create_issue(owner: str, repo: str, title: str) -> dict[str, Any]:
            return {"created": f"{owner}/{repo}: {title}"}

        handlers = IssuesHandlers()
        proxy = create_proxy(backend, server_name="proxy")
        proxy.add_middleware(
            GroupsMiddleware(
                groups={"issues": GroupDefinition(description="Issue tracking")},
                handlers=handlers,
                initial_groups=["issues"],
            )
        )

        async with Client(proxy) as client:
            result = await client.call_tool(
                "create_issue",
                {"owner": "myorg", "repo": "myrepo", "title": "Test Issue"},
            )
            assert result.data["created"] == "myorg/myrepo: Test Issue"

    async def test_disabled_tool_call_returns_error(self) -> None:
        """Test calling a disabled tool returns error message."""
        backend = FastMCP("backend")

        @backend.tool
        async def create_issue(owner: str, repo: str, title: str) -> dict[str, Any]:
            return {"created": f"{owner}/{repo}: {title}"}

        handlers = IssuesHandlers()
        proxy = create_proxy(backend, server_name="proxy")
        proxy.add_middleware(
            GroupsMiddleware(
                groups={"issues": GroupDefinition(description="Issue tracking")},
                handlers=handlers,
                # issues NOT enabled
            )
        )

        async with Client(proxy) as client:
            # Disabled tools raise ToolError with helpful message
            with pytest.raises(ToolError) as exc_info:
                await client.call_tool(
                    "create_issue",
                    {"owner": "myorg", "repo": "myrepo", "title": "Test"},
                )
            error_msg = str(exc_info.value)
            assert "not available" in error_msg
            assert "enable_tools" in error_msg

    async def test_enable_tools_makes_tools_visible(self) -> None:
        """Test enable_tools makes group's tools visible."""
        backend = FastMCP("backend")

        @backend.tool
        async def create_issue(owner: str, repo: str, title: str) -> dict[str, Any]:
            return {"created": f"{owner}/{repo}: {title}"}

        handlers = IssuesHandlers()
        proxy = create_proxy(backend, server_name="proxy")
        proxy.add_middleware(
            GroupsMiddleware(
                groups={"issues": GroupDefinition(description="Issue tracking")},
                handlers=handlers,
            )
        )

        async with Client(proxy) as client:
            # Initially not visible
            tools = await client.list_tools()
            assert "create_issue" not in {t.name for t in tools}

            # Enable group
            result = await client.call_tool("enable_tools", {"groups": ["issues"]})
            assert result.structured_content["enabled"] == ["issues"]

            # Now visible
            tools = await client.list_tools()
            assert "create_issue" in {t.name for t in tools}

    async def test_disable_tools_hides_tools(self) -> None:
        """Test disable_tools hides group's tools."""
        backend = FastMCP("backend")

        @backend.tool
        async def create_issue(owner: str, repo: str, title: str) -> dict[str, Any]:
            return {"created": f"{owner}/{repo}: {title}"}

        handlers = IssuesHandlers()
        proxy = create_proxy(backend, server_name="proxy")
        proxy.add_middleware(
            GroupsMiddleware(
                groups={"issues": GroupDefinition(description="Issue tracking")},
                handlers=handlers,
                initial_groups=["issues"],
            )
        )

        async with Client(proxy) as client:
            # Initially visible
            tools = await client.list_tools()
            assert "create_issue" in {t.name for t in tools}

            # Disable group
            result = await client.call_tool("disable_tools", {"groups": ["issues"]})
            assert result.structured_content["disabled"] == ["issues"]

            # Now hidden
            tools = await client.list_tools()
            assert "create_issue" not in {t.name for t in tools}

    async def test_handler_decorators_discovered(self) -> None:
        """Test @in_group decorated handlers are discovered."""

        class MultiGroupHandlers:
            @in_group("issues")
            async def create_issue(self, title: str) -> None:
                pass

            @in_group("issues")
            @in_group("communications")
            async def add_comment(self, target_id: int, body: str) -> None:
                pass

            @in_group("repo")
            async def create_repo(self, name: str) -> None:
                pass

        middleware = GroupsMiddleware(
            groups={
                "issues": GroupDefinition(description="Issue tracking"),
                "repo": GroupDefinition(description="Repository management"),
                "communications": GroupDefinition(description="Communications"),
            },
            handlers=MultiGroupHandlers(),
        )

        # Verify tool-to-group mapping was discovered
        assert "create_issue" in middleware._tool_to_groups
        assert middleware._tool_to_groups["create_issue"] == {"issues"}
        assert "create_repo" in middleware._tool_to_groups
        assert middleware._tool_to_groups["create_repo"] == {"repo"}
        # add_comment belongs to multiple groups
        assert "add_comment" in middleware._tool_to_groups
        assert middleware._tool_to_groups["add_comment"] == {"issues", "communications"}


@pytest.mark.asyncio
class TestProgressiveDisclosure:
    """Tests for progressive disclosure of groups."""

    async def test_child_groups_hidden_until_parent_enabled(self) -> None:
        """Test child groups not visible until parent enabled."""
        backend = FastMCP("backend")
        proxy = create_proxy(backend, server_name="proxy")
        proxy.add_middleware(
            GroupsMiddleware(
                groups={
                    "comms": GroupDefinition(description="Communications"),
                    "email": GroupDefinition(description="Email", parent="comms"),
                    "calendar": GroupDefinition(description="Calendar", parent="comms"),
                },
            )
        )

        async with Client(proxy) as client:
            # Check initial description - only root groups visible
            tools = await client.list_tools()
            enable_tool = next(t for t in tools if t.name == "enable_tools")
            assert "comms: Communications" in enable_tool.description
            assert "email" not in enable_tool.description

            # Enable parent group
            result = await client.call_tool("enable_tools", {"groups": ["comms"]})
            assert result.structured_content["enabled"] == ["comms"]
            assert "email" in result.structured_content["available_groups"]

            # Now children visible in description
            tools = await client.list_tools()
            enable_tool = next(t for t in tools if t.name == "enable_tools")
            assert "email" in enable_tool.description
            assert "calendar" in enable_tool.description

    async def test_cannot_enable_child_before_parent(self) -> None:
        """Test enabling child before parent returns error."""
        backend = FastMCP("backend")
        proxy = create_proxy(backend, server_name="proxy")
        proxy.add_middleware(
            GroupsMiddleware(
                groups={
                    "parent": GroupDefinition(description="Parent"),
                    "child": GroupDefinition(description="Child", parent="parent"),
                },
            )
        )

        async with Client(proxy) as client:
            result = await client.call_tool("enable_tools", {"groups": ["child"]})
            text = result.content[0].text
            assert "not visible" in text
            assert "Enable parent 'parent' first" in text

    async def test_disabling_parent_cascades_to_children(self) -> None:
        """Test disabling parent also disables all children."""

        class NestedHandlers:
            @in_group("email")
            async def send_email(self, to: str, body: str) -> None:
                pass

        backend = FastMCP("backend")

        @backend.tool
        async def send_email(to: str, body: str) -> dict[str, Any]:
            return {"sent_to": to}

        handlers = NestedHandlers()
        proxy = create_proxy(backend, server_name="proxy")
        proxy.add_middleware(
            GroupsMiddleware(
                groups={
                    "comms": GroupDefinition(description="Communications"),
                    "email": GroupDefinition(description="Email", parent="comms"),
                },
                handlers=handlers,
                initial_groups=["comms", "email"],
            )
        )

        async with Client(proxy) as client:
            # Verify email tool is available
            tools = await client.list_tools()
            assert "send_email" in {t.name for t in tools}

            # Disable parent
            result = await client.call_tool("disable_tools", {"groups": ["comms"]})
            text = result.content[0].text
            assert "comms" in text
            assert "email" in text  # Child also disabled

            # Email tool no longer available
            tools = await client.list_tools()
            assert "send_email" not in {t.name for t in tools}

    async def test_deeply_nested_groups(self) -> None:
        """Test deeply nested groups (3+ levels) progressively revealed."""
        backend = FastMCP("backend")
        proxy = create_proxy(backend, server_name="proxy")
        proxy.add_middleware(
            GroupsMiddleware(
                groups={
                    "root": GroupDefinition(description="Root"),
                    "level1": GroupDefinition(description="Level 1", parent="root"),
                    "level2": GroupDefinition(description="Level 2", parent="level1"),
                    "level3": GroupDefinition(description="Level 3", parent="level2"),
                },
            )
        )

        async with Client(proxy) as client:
            # Check initial description shows only root
            tools = await client.list_tools()
            enable_tool = next(t for t in tools if t.name == "enable_tools")
            assert "root: Root" in enable_tool.description
            assert "level1" not in enable_tool.description

            # Enable root -> level1 becomes visible
            await client.call_tool("enable_tools", {"groups": ["root"]})
            tools = await client.list_tools()
            enable_tool = next(t for t in tools if t.name == "enable_tools")
            assert "level1" in enable_tool.description
            assert "level2" not in enable_tool.description

            # Enable level1 -> level2 becomes visible
            await client.call_tool("enable_tools", {"groups": ["level1"]})
            tools = await client.list_tools()
            enable_tool = next(t for t in tools if t.name == "enable_tools")
            assert "level2" in enable_tool.description
            assert "level3" not in enable_tool.description


@pytest.mark.asyncio
class TestMetadataDiscovery:
    """Tests for tool metadata discovery."""

    async def test_tools_with_groups_meta_discovered(self) -> None:
        """Test tools with GROUPS_META_KEY are auto-discovered."""
        backend = FastMCP("backend")

        # Tool with groups metadata (no handler needed)
        @backend.tool(meta={GROUPS_META_KEY: ["issues"]})
        async def create_issue(title: str) -> dict[str, Any]:
            return {"title": title}

        proxy = create_proxy(backend, server_name="proxy")
        middleware = GroupsMiddleware(
            groups={"issues": GroupDefinition(description="Issue tracking")},
            initial_groups=["issues"],
        )
        proxy.add_middleware(middleware)

        async with Client(proxy) as client:
            tools = await client.list_tools()
            tool_names = {t.name for t in tools}
            assert "create_issue" in tool_names

    async def test_handler_decorators_take_precedence(self) -> None:
        """Test handler decorators take precedence over metadata."""

        class Handlers:
            @in_group("issues")  # Handler says "issues"
            async def my_tool(self) -> None:
                pass

        backend = FastMCP("backend")

        # Tool metadata says "repo", but handler decorator says "issues"
        @backend.tool(meta={GROUPS_META_KEY: ["repo"]})
        async def my_tool() -> dict[str, Any]:
            return {}

        handlers = Handlers()
        middleware = GroupsMiddleware(
            groups={
                "issues": GroupDefinition(description="Issue tracking"),
                "repo": GroupDefinition(description="Repository"),
            },
            handlers=handlers,
        )

        # Handler decoration takes precedence
        assert middleware._tool_to_groups.get("my_tool") == {"issues"}


@pytest.mark.asyncio
class TestMaxToolsLimit:
    """Tests for max_tools enforcement."""

    async def test_max_tools_blocks_over_limit(self) -> None:
        """Test max_tools enforcement blocks over-limit."""

        class Handlers:
            @in_group("group1")
            async def tool1(self) -> None:
                pass

            @in_group("group1")
            async def tool2(self) -> None:
                pass

            @in_group("group2")
            async def tool3(self) -> None:
                pass

        backend = FastMCP("backend")

        @backend.tool
        async def tool1() -> dict[str, Any]:
            return {}

        @backend.tool
        async def tool2() -> dict[str, Any]:
            return {}

        @backend.tool
        async def tool3() -> dict[str, Any]:
            return {}

        handlers = Handlers()
        proxy = create_proxy(backend, server_name="proxy")
        proxy.add_middleware(
            GroupsMiddleware(
                groups={
                    "group1": GroupDefinition(description="Group 1"),
                    "group2": GroupDefinition(description="Group 2"),
                },
                handlers=handlers,
                initial_groups=["group1"],
                max_tools=2,  # Already at limit with group1
            )
        )

        async with Client(proxy) as client:
            result = await client.call_tool("enable_tools", {"groups": ["group2"]})
            text = result.content[0].text
            assert "exceeding max_tools=2" in text
            assert "Disable some groups first" in text


@pytest.mark.asyncio
class TestProxyIntegration:
    """Tests for full proxy integration."""

    async def test_groups_middleware_with_proxy(self) -> None:
        """Test GroupsMiddleware integrates with create_proxy."""
        # Create backend server
        backend = FastMCP("backend")

        @backend.tool
        async def create_issue(title: str) -> dict[str, Any]:
            return {"title": title, "source": "backend"}

        @backend.tool
        async def create_repo(name: str) -> dict[str, Any]:
            return {"name": name, "source": "backend"}

        # Create handlers with group metadata
        class Handlers:
            @in_group("issues")
            async def create_issue(self, title: str) -> None:
                pass

            @in_group("repo")
            async def create_repo(self, name: str) -> None:
                pass

        handlers = Handlers()
        proxy = create_proxy(backend, server_name="test-proxy")
        proxy.add_middleware(
            GroupsMiddleware(
                groups={
                    "issues": GroupDefinition(description="Issue tracking"),
                    "repo": GroupDefinition(description="Repository"),
                },
                handlers=handlers,
                initial_groups=["issues"],
            )
        )

        async with Client(proxy) as client:
            # Issues enabled, repo not
            tools = await client.list_tools()
            tool_names = {t.name for t in tools}
            assert "create_issue" in tool_names
            assert "create_repo" not in tool_names

            # Call enabled tool
            result = await client.call_tool("create_issue", {"title": "Test"})
            assert result.data["source"] == "backend"

            # Call disabled tool - raises ToolError
            with pytest.raises(ToolError) as exc_info:
                await client.call_tool("create_repo", {"name": "test"})
            assert "not available" in str(exc_info.value)
