# Middleware

Middleware in <span class="wags-brand">wags</span> are built using the amazing `FastMCP` sdk, which already provides many powerful features, such as hooks to intercept protocol messages e.g., `on_call_tool`, `on_list_tools`, `on_read_resource`, `on_get_prompt`, `on_notification`, and the `MiddlewareContext` provides:

- `context.message` - Request/response data
- `context.fastmcp_context` - Access to roots, elicitation, sampling
- `context.source` - Origin ("client" or "server")
- `context.type` - Message type ("request", "notification")

The <span class="wags-brand">wags</span> middleware toolkit further provides *fine-grained interception* hooks and helpers for *easy configuration* of middleware capabilities. Majority of the features can be configured only by adding decorators and type annotations instead of having to write complex code.

```python title="WAGS WagsMiddlewareBase"
--8<-- "snippets/middleware/base_middleware.py"
```

## Next Steps

Understand what features different middlewares provide and how to configure them:

- [Groups](groups.md) for progressive tool disclosure via hierarchical groups.
- [TodoList](todo.md) to ensure agents perform complex tasks correctly.
- [Roots](roots.md) to enable client-configured fine-grained access control for MCP servers.
- [Elicitation](elicitation.md) add human-in-the-loop features to improve UX.
