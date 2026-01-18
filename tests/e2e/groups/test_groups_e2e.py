"""E2E tests for GroupsMiddleware with LLM agents."""

import json
from typing import Any

import pytest
from fast_agent import FastAgent

from tests.utils.fastagent_helpers import MessageSerializer


def extract_tool_calls(agent: Any) -> list[dict[str, Any]]:
    """Extract all tool calls from agent message history."""
    messages = agent._agent(None).message_history
    complete_json = MessageSerializer.serialize_complete(messages)
    complete_data = json.loads(complete_json)
    tool_calls = MessageSerializer.extract_tool_calls_by_turn(complete_data)
    return [call for turn in tool_calls for call in turn]


def find_call(calls: list[dict[str, Any]], tool_suffix: str) -> dict[str, Any] | None:
    """Find first tool call ending with given suffix."""
    return next((c for c in calls if c["function"].endswith(tool_suffix)), None)


def find_all_calls(calls: list[dict[str, Any]], tool_suffix: str) -> list[dict[str, Any]]:
    """Find all tool calls ending with given suffix."""
    return [c for c in calls if c["function"].endswith(tool_suffix)]


def get_all_enabled_groups(calls: list[dict[str, Any]]) -> list[str]:
    """Collect all groups enabled across all enable_tools calls."""
    groups = []
    for call in find_all_calls(calls, "enable_tools"):
        groups.extend(call["arguments"]["groups"])
    return groups


class TestGroupsMiddleware:
    @pytest.mark.asyncio
    @pytest.mark.verified_models(["gpt-5", "claude-sonnet-4-5"])
    async def test_progressive_disclosure(self, fast_agent: FastAgent, model: str) -> None:
        """Agent enables groups before using tools."""
        fast = fast_agent

        @fast.agent(
            name="groups_test",
            model=model,
            servers=["mock-github-groups"],
            instruction=(
                "You are a helpful assistant. When you need to use a tool that is not available, "
                "first call enable_tools to make it available."
            ),
        )
        async def test_workflow() -> None:
            async with fast.run() as agent:
                await agent.send("Create an issue titled 'Bug report' with body 'Found a bug in the API'")
                calls = extract_tool_calls(agent)

                enable_call = find_call(calls, "enable_tools")
                assert enable_call, "Agent should call enable_tools"
                assert "issues" in enable_call["arguments"]["groups"]

                create_call = find_call(calls, "create_issue")
                assert create_call, "Agent should call create_issue"
                assert create_call["arguments"]["title"] == "Bug report"

        await test_workflow()

    @pytest.mark.asyncio
    @pytest.mark.verified_models(["gpt-5", "claude-sonnet-4-5"])
    async def test_group_hierarchy(self, fast_agent: FastAgent, model: str) -> None:
        """Agent navigates parent-child group hierarchy."""
        fast = fast_agent

        @fast.agent(
            name="hierarchy_test",
            model=model,
            servers=["mock-github-groups"],
            instruction=(
                "You are a helpful assistant. Use enable_tools to discover and enable tool groups. "
                "Some groups have parent-child relationships - enable parents first to reveal children."
            ),
        )
        async def test_hierarchy() -> None:
            async with fast.run() as agent:
                await agent.send("Create a repository named 'test-repo'.")
                calls = extract_tool_calls(agent)

                assert find_all_calls(calls, "enable_tools"), "Agent should call enable_tools"

                enabled = get_all_enabled_groups(calls)
                assert "code_management" in enabled, "Agent should enable code_management parent"
                assert "repo_management" in enabled, "Agent should enable repo_management"
                assert find_call(calls, "create_repository"), "Agent should call create_repository"

        await test_hierarchy()

    @pytest.mark.asyncio
    @pytest.mark.verified_models(["gpt-5", "claude-sonnet-4-5"])
    async def test_disable_groups(self, fast_agent: FastAgent, model: str) -> None:
        """Agent disables groups after use to reduce context."""
        fast = fast_agent

        @fast.agent(
            name="disable_test",
            model=model,
            servers=["mock-github-groups"],
            instruction=("You are a helpful assistant. After completing a task, disable groups you no longer need."),
        )
        async def test_disable() -> None:
            async with fast.run() as agent:
                await agent.send(
                    "First enable the issues group, then create an issue titled 'Test'. "
                    "After creating the issue, disable the issues group since we're done with it."
                )
                calls = extract_tool_calls(agent)

                assert find_call(calls, "enable_tools"), "Agent should call enable_tools"
                assert find_call(calls, "create_issue"), "Agent should call create_issue"
                assert find_call(calls, "disable_tools"), "Agent should call disable_tools"

        await test_disable()

    @pytest.mark.asyncio
    @pytest.mark.verified_models(["gpt-5", "claude-sonnet-4-5"])
    async def test_deep_hierarchy(self, fast_agent: FastAgent, model: str) -> None:
        """Agent navigates 3+ level group hierarchy."""
        fast = fast_agent

        @fast.agent(
            name="deep_hierarchy_test",
            model=model,
            servers=["mock-github-groups"],
            instruction=(
                "You are a helpful assistant. Use enable_tools to discover and enable tool groups. "
                "Groups may have parent-child relationships - enable parents first to reveal children."
            ),
        )
        async def test_deep_hierarchy() -> None:
            async with fast.run() as agent:
                await agent.send("Create a branch named 'feature-x' in repo 'my-repo'.")
                calls = extract_tool_calls(agent)

                assert find_all_calls(calls, "enable_tools"), "Agent should call enable_tools"

                enabled = get_all_enabled_groups(calls)
                assert "code_management" in enabled, "Agent should enable code_management (level 1)"
                assert "repo_management" in enabled, "Agent should enable repo_management (level 2)"
                assert "branches" in enabled, "Agent should enable branches (level 3)"

                branch_calls = find_all_calls(calls, "create_branch")
                assert branch_calls, "Agent should call create_branch"
                correct = next(
                    (c for c in branch_calls if c["arguments"].get("branch_name") == "feature-x"),
                    None,
                )
                assert correct, f"Expected branch_name='feature-x', got: {[c['arguments'] for c in branch_calls]}"

        await test_deep_hierarchy()

    @pytest.mark.asyncio
    @pytest.mark.verified_models(["gpt-5", "claude-sonnet-4-5"])
    async def test_error_recovery(self, fast_agent: FastAgent, model: str) -> None:
        """Agent recovers from disabled tool error by enabling the right group."""
        fast = fast_agent

        @fast.agent(
            name="recovery_test",
            model=model,
            servers=["mock-github-groups"],
            instruction=(
                "You are a helpful assistant. If a tool is not available, the error will tell you "
                "which group to enable. Use enable_tools to make the tool available, then retry."
            ),
        )
        async def test_recovery() -> None:
            async with fast.run() as agent:
                await agent.send("Please create an issue titled 'Login broken' with body 'Cannot log in to the app'.")
                calls = extract_tool_calls(agent)

                assert find_call(calls, "enable_tools"), "Agent should call enable_tools"

                create_call = find_call(calls, "create_issue")
                assert create_call, "Agent should call create_issue"
                assert create_call["arguments"]["title"] == "Login broken"

        await test_recovery()

    @pytest.mark.asyncio
    @pytest.mark.verified_models(["gpt-5", "claude-sonnet-4-5"])
    async def test_max_tools_limit(self, fast_agent: FastAgent, model: str) -> None:
        """Agent handles max_tools limit by disabling groups to make room."""
        fast = fast_agent

        @fast.agent(
            name="max_tools_test",
            model=model,
            servers=["mock-github-groups"],
            instruction=(
                "You are a helpful assistant. The server has a max_tools limit. "
                "If enabling a group would exceed the limit, disable unneeded groups first."
            ),
        )
        async def test_max_tools() -> None:
            async with fast.run() as agent:
                await agent.send(
                    "First, enable the issues group. Then enable the pull_requests group. "
                    "If you hit a max_tools limit, disable issues first before enabling pull_requests."
                )
                calls = extract_tool_calls(agent)

                assert find_all_calls(calls, "enable_tools"), "Agent should call enable_tools"

                enabled = get_all_enabled_groups(calls)
                assert "pull_requests" in enabled, "Agent should enable pull_requests group"

        await test_max_tools()
