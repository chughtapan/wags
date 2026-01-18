# Groups

When MCP servers expose many tools, agents can become overwhelmed with options, leading to poor tool selection and increased token usage. The `GroupsMiddleware` in <span class="wags-brand">wags</span> enables progressive tool disclosure by organizing tools into hierarchical groups that agents can enable or disable as needed.

## How It Works

Tools are assigned to groups using the `@in_group` decorator. The middleware:

1. Hides all grouped tools initially (or starts with configured `initial_groups`)
2. Exposes `enable_tools` and `disable_tools` meta-tools
3. Progressively reveals child groups as parents are enabled
4. Enforces optional `max_tools` limits

## Example

```python linenums="1" title="handlers.py"
from wags.middleware import GroupsMiddleware, GroupDefinition, in_group

class GithubHandlers:
    @in_group("issues")
    async def create_issue(self, owner: str, repo: str, title: str):
        pass

    @in_group("issues")
    async def list_issues(self, owner: str, repo: str):
        pass

    @in_group("repos")
    async def create_repository(self, name: str):
        pass
```

Configure the middleware with group definitions:

```python title="main.py"
from wags.middleware import GroupsMiddleware, GroupDefinition

handlers = GithubHandlers()
mcp.add_middleware(
    GroupsMiddleware(
        groups={
            "issues": GroupDefinition(description="Issue tracking"),
            "repos": GroupDefinition(description="Repository management"),
        },
        handlers=handlers,
        initial_groups=["issues"],  # Start with issues enabled
        max_tools=10,  # Optional limit
    )
)
```

## Hierarchical Groups

Groups can be nested using the `parent` parameter for progressive disclosure:

```python
groups = {
    "code": GroupDefinition(description="Code management"),
    "repos": GroupDefinition(description="Repositories", parent="code"),
    "branches": GroupDefinition(description="Branches", parent="repos"),
}
```

With this hierarchy:

- Only `code` is visible initially (root group)
- Enabling `code` reveals `repos` as an option
- Enabling `repos` reveals `branches` as an option
- Disabling `code` cascades to disable `repos` and `branches`

## Agent Interaction

When an agent calls `enable_tools(groups=["issues"])`, it receives a structured JSON response:

```json
{
  "enabled": ["issues"],
  "enabled_groups": ["issues"],
  "available_tools": ["create_issue", "list_issues"],
  "available_groups": [],
  "errors": []
}
```

The response includes:

- `enabled`: Groups that were newly enabled by this call
- `enabled_groups`: All currently enabled groups
- `available_tools`: Tools now available to the agent
- `available_groups`: Child groups that can now be enabled
- `errors`: Any validation errors (unknown groups, already enabled, etc.)

Similarly, `disable_tools` returns:

```json
{
  "disabled": ["issues"],
  "enabled_groups": [],
  "available_tools": [],
  "errors": []
}
```

A `tools/list_changed` notification is sent whenever groups are enabled or disabled, prompting the client to refresh its tool list.

When a tool from a disabled group is called, the agent receives an error message with a hint about which group to enable.

## API Documentation

::: wags.middleware.groups.in_group
    options:
      show_source: false
      members: []
      show_signature: false

::: wags.middleware.groups.GroupDefinition
    options:
      show_source: false
      members: []
      show_signature: false

::: wags.middleware.groups.GroupsMiddleware
    options:
      show_source: false
      show_bases: false
      members: []
      show_signature: false

::: wags.middleware.groups.EnableToolsResult
    options:
      show_source: false
      members: []
      show_signature: false

::: wags.middleware.groups.DisableToolsResult
    options:
      show_source: false
      members: []
      show_signature: false
