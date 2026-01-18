"""Middleware for progressive tool disclosure via groups.

Tools can be assigned to groups via handler decorators (@in_group) or
tool metadata (GROUPS_META_KEY). Agents use enable_tools/disable_tools
meta-tools to control which groups are active.
"""

import inspect
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, TypeVar

import mcp.types as mt
from fastmcp.exceptions import ToolError
from fastmcp.server.middleware.middleware import CallNext, MiddlewareContext
from fastmcp.tools.tool import Tool, ToolResult
from pydantic import BaseModel

from wags.middleware.base import WagsMiddlewareBase


class EnableToolsResult(BaseModel):
    """Structured result from enable_tools meta-tool."""

    enabled: list[str]
    enabled_groups: list[str]
    available_tools: list[str]
    available_groups: list[str]
    errors: list[str]


class DisableToolsResult(BaseModel):
    """Structured result from disable_tools meta-tool."""

    disabled: list[str]
    enabled_groups: list[str]
    available_tools: list[str]
    errors: list[str]


F = TypeVar("F", bound=Callable[..., Any])

# Metadata key for groups in tool meta
GROUPS_META_KEY = "io.modelcontextprotocol/groups"


def in_group(*group_names: str) -> Callable[[F], F]:
    """Mark a handler method as belonging to one or more groups.

    Can be stacked to add tool to multiple groups:

        @in_group("issues")
        @in_group("communications")
        async def create_issue(self, ...):
            pass

    Args:
        group_names: Names of groups this tool belongs to
    """

    def decorator(func: F) -> F:
        existing: set[str] = getattr(func, "__groups__", set())
        updated = existing | set(group_names)
        setattr(func, "__groups__", updated)
        return func

    return decorator


@dataclass
class GroupDefinition:
    """Definition of a tool group."""

    description: str
    parent: str | None = None


class GroupsMiddleware(WagsMiddlewareBase):
    """Middleware for progressive tool disclosure via groups."""

    def __init__(
        self,
        groups: dict[str, GroupDefinition],
        handlers: Any | None = None,
        initial_groups: list[str] | None = None,
        max_tools: int | None = None,
    ):
        super().__init__(handlers=handlers)
        self.group_definitions = groups
        self.max_tools = max_tools
        self._enabled_groups: set[str] = set()
        self._tool_to_groups: dict[str, set[str]] = {}
        self._all_tools: Sequence[Tool] | None = None
        self._children_map: dict[str, set[str]] = {}

        self._build_hierarchy()
        if handlers:
            self._scan_handlers(handlers)

        for g in initial_groups or []:
            if g not in self.group_definitions:
                raise ValueError(f"Unknown group: {g}")
            if not self._is_group_visible(g):
                parent = self.group_definitions[g].parent
                raise ValueError(f"Cannot initially enable '{g}': parent '{parent}' not enabled")
            self._enable_group(g)

    def _build_hierarchy(self) -> None:
        """Build parent-child relationships from group definitions."""
        for name, defn in self.group_definitions.items():
            if defn.parent:
                if defn.parent not in self.group_definitions:
                    raise ValueError(f"Group '{name}' has unknown parent '{defn.parent}'")
                self._children_map.setdefault(defn.parent, set()).add(name)

    def _get_all_descendants(self, group_name: str) -> set[str]:
        """Get all descendant groups (children, grandchildren, etc.)."""
        descendants: set[str] = set()
        to_process = [group_name]
        while to_process:
            current = to_process.pop()
            for child in self._children_map.get(current, []):
                if child not in descendants:
                    descendants.add(child)
                    to_process.append(child)
        return descendants

    def _enable_group(self, group_name: str) -> bool:
        """Enable a group. Returns True if newly enabled."""
        if group_name in self._enabled_groups:
            return False
        self._enabled_groups.add(group_name)
        return True

    def _disable_group_with_descendants(self, group_name: str) -> set[str]:
        """Disable a group and all its enabled descendants."""
        newly_disabled: set[str] = set()
        if group_name in self._enabled_groups:
            self._enabled_groups.discard(group_name)
            newly_disabled.add(group_name)
        for descendant in self._get_all_descendants(group_name):
            if descendant in self._enabled_groups:
                self._enabled_groups.discard(descendant)
                newly_disabled.add(descendant)
        return newly_disabled

    def _is_group_visible(self, group_name: str) -> bool:
        """A group is visible if it's a root or its parent is enabled."""
        defn = self.group_definitions[group_name]
        return defn.parent is None or defn.parent in self._enabled_groups

    def _scan_handlers(self, handlers: Any) -> None:
        """Scan handler methods for @in_group decorators."""
        for name in dir(handlers):
            if name.startswith("_"):
                continue
            method = getattr(handlers, name)
            if callable(method) and inspect.iscoroutinefunction(method):
                groups: set[str] = getattr(method, "__groups__", set())
                if groups:
                    for g in groups:
                        if g not in self.group_definitions:
                            raise ValueError(
                                f"Handler '{name}' references unknown group '{g}'. Define it in group_definitions."
                            )
                    self._tool_to_groups[name] = groups

    def _discover_groups_from_metadata(self, tools: Sequence[Tool]) -> None:
        """Discover group memberships from tool metadata."""
        for tool in tools:
            if tool.name in self._tool_to_groups:
                continue
            if hasattr(tool, "meta") and tool.meta:
                groups = tool.meta.get(GROUPS_META_KEY, [])
                if groups:
                    valid_groups = {g for g in groups if g in self.group_definitions}
                    if valid_groups:
                        self._tool_to_groups[tool.name] = valid_groups

    def _get_enabled_tools(self) -> set[str]:
        """Get tool names from enabled groups."""
        return {tool_name for tool_name, groups in self._tool_to_groups.items() if groups & self._enabled_groups}

    def _count_tools_if_enabled(self, group_name: str) -> int:
        """Count total tools if group were enabled."""
        simulated_enabled = self._enabled_groups | {group_name}
        return sum(1 for groups in self._tool_to_groups.values() if groups & simulated_enabled)

    def _build_enable_tools_description(self) -> str:
        """Build description showing available groups with progressive disclosure."""
        lines = ["Enable tool groups for use.", "", "Available groups:"]

        def format_group(name: str, indent: int = 0) -> list[str]:
            prefix = "  " * indent + "- " if indent else "- "
            defn = self.group_definitions[name]
            status = " (enabled)" if name in self._enabled_groups else ""
            result = [f"{prefix}{name}: {defn.description}{status}"]
            if name in self._enabled_groups:
                for child in sorted(self._children_map.get(name, [])):
                    result.extend(format_group(child, indent + 1))
            return result

        root_groups = [n for n, d in self.group_definitions.items() if d.parent is None]
        for name in sorted(root_groups):
            lines.extend(format_group(name))

        if self.max_tools:
            current_count = len(self._get_enabled_tools())
            lines.append(f"\nMax tools limit: {self.max_tools} (current: {current_count})")
        return "\n".join(lines)

    def _build_disable_tools_description(self) -> str:
        """Build description showing currently enabled groups."""
        lines = ["Disable tool groups to reduce context.", ""]
        if self._enabled_groups:
            lines.append("Currently enabled:")
            lines.extend(
                f"- {name}: {self.group_definitions[name].description}" for name in sorted(self._enabled_groups)
            )
        else:
            lines.append("No groups currently enabled.")
        return "\n".join(lines)

    def _create_meta_tools(self) -> list[Tool]:
        """Create enable_tools and disable_tools meta-tools."""

        async def enable_tools_fn(groups: list[str]) -> EnableToolsResult:
            raise NotImplementedError

        async def disable_tools_fn(groups: list[str]) -> DisableToolsResult:
            raise NotImplementedError

        return [
            Tool.from_function(
                fn=enable_tools_fn,
                name="enable_tools",
                description=self._build_enable_tools_description(),
                output_schema=None,
            ),
            Tool.from_function(
                fn=disable_tools_fn,
                name="disable_tools",
                description=self._build_disable_tools_description(),
                output_schema=None,
            ),
        ]

    def _validate_enable_group(self, group_name: str) -> str | None:
        """Return error message if group can't be enabled, None if valid."""
        if group_name not in self.group_definitions:
            return f"Unknown group: {group_name}"
        if not self._is_group_visible(group_name):
            parent = self.group_definitions[group_name].parent
            return f"Group '{group_name}' not visible. Enable parent '{parent}' first."
        if group_name in self._enabled_groups:
            return f"Group already enabled: {group_name}"
        if self.max_tools:
            projected = self._count_tools_if_enabled(group_name)
            if projected > self.max_tools:
                return (
                    f"Cannot enable '{group_name}': would result in {projected} tools, "
                    f"exceeding max_tools={self.max_tools}. Disable some groups first."
                )
        return None

    def _get_available_children(self) -> set[str]:
        """Get child groups that are visible but not yet enabled."""
        available: set[str] = set()
        for g in self._enabled_groups:
            for child in self._children_map.get(g, set()):
                if child not in self._enabled_groups:
                    available.add(child)
        return available

    async def _enable_tools(self, groups: list[str]) -> EnableToolsResult:
        """Process enable_tools request."""
        enabled: list[str] = []
        errors: list[str] = []
        for group_name in groups:
            if error := self._validate_enable_group(group_name):
                errors.append(error)
            elif self._enable_group(group_name):
                enabled.append(group_name)
        return EnableToolsResult(
            enabled=enabled,
            enabled_groups=sorted(self._enabled_groups),
            available_tools=sorted(self._get_enabled_tools()),
            available_groups=sorted(self._get_available_children()),
            errors=errors,
        )

    async def _disable_tools(self, groups: list[str]) -> DisableToolsResult:
        """Process disable_tools request."""
        all_disabled: list[str] = []
        errors: list[str] = []
        for group_name in groups:
            if group_name not in self.group_definitions:
                errors.append(f"Unknown group: {group_name}")
            elif group_name not in self._enabled_groups:
                errors.append(f"Group not enabled: {group_name}")
            else:
                newly_disabled = self._disable_group_with_descendants(group_name)
                all_disabled.extend(sorted(newly_disabled))
        return DisableToolsResult(
            disabled=all_disabled,
            enabled_groups=sorted(self._enabled_groups),
            available_tools=sorted(self._get_enabled_tools()),
            errors=errors,
        )

    async def on_list_tools(
        self,
        context: MiddlewareContext[mt.ListToolsRequest],
        call_next: CallNext[mt.ListToolsRequest, Sequence[Tool]],
    ) -> Sequence[Tool]:
        """Filter tools to only enabled groups + meta-tools."""
        all_tools = await call_next(context)
        self._all_tools = all_tools
        self._discover_groups_from_metadata(all_tools)

        enabled_tool_names = self._get_enabled_tools()
        filtered = [t for t in all_tools if t.name in enabled_tool_names]
        return self._create_meta_tools() + filtered

    async def _send_tools_list_changed(self, context: MiddlewareContext) -> None:
        """Send tools/list_changed notification to client."""
        if context.fastmcp_context and hasattr(context.fastmcp_context, "session"):
            session = context.fastmcp_context.session
            if hasattr(session, "send_tool_list_changed"):
                await session.send_tool_list_changed()

    async def on_call_tool(
        self,
        context: MiddlewareContext[mt.CallToolRequestParams],
        call_next: CallNext[mt.CallToolRequestParams, Any],
    ) -> Any:
        """Handle meta-tool calls and block disabled tool calls."""
        tool_name = context.message.name
        args = context.message.arguments or {}

        if tool_name == "enable_tools":
            enable_result = await self._enable_tools(args.get("groups", []))
            if enable_result.enabled:
                await self._send_tools_list_changed(context)
            return ToolResult(structured_content=enable_result)

        if tool_name == "disable_tools":
            disable_result = await self._disable_tools(args.get("groups", []))
            if disable_result.disabled:
                await self._send_tools_list_changed(context)
            return ToolResult(structured_content=disable_result)

        if tool_name not in self._get_enabled_tools():
            containing_groups = self._tool_to_groups.get(tool_name, set())
            hint = f" Try: enable_tools(groups={sorted(containing_groups)})" if containing_groups else ""
            raise ToolError(
                f"Tool '{tool_name}' is not available. Enable its group first.{hint} "
                f"Currently enabled: {sorted(self._enabled_groups) or 'none'}"
            )

        return await call_next(context)
