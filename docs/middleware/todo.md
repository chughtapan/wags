# Todo List Integration

<em class="wags-brand">wags</em> provides automatic task tracking through TodoServer integration. When enabled, LLM agents get access to TodoWrite and TodoRead tools that help break down complex tasks and track progress.

## Overview

The Todo integration:

- **Mounts TodoServer** on proxy servers without tool name prefixes
- **Provides instructions** that guide LLMs to use todo tools effectively
- **Tracks state in-memory** per proxy instance (no persistence)
- **Enforces single source** of instructions (no merging supported)

## How It Works

When you enable todos on a proxy:

1. A `TodoServer` instance is created with built-in instructions
2. The server is mounted on the proxy without a prefix (tools are `TodoWrite`, not `todo_TodoWrite`)
3. The proxy's instructions are set to the TodoServer's instructions
4. LLM agents can now use `TodoWrite(todos)` and `TodoRead()` tools

## Usage

### Basic Usage

```python
from fastmcp import FastMCP
from wags.proxy import create_proxy

# Create your target server
server = FastMCP("my-server")

@server.tool()
def some_tool() -> str:
    return "result"

# Create proxy with todo support
proxy = create_proxy(server, enable_todos=True)
```

### Without Todo Support

```python
#Default behavior - todos disabled
proxy = create_proxy(server)  # enable_todos=False by default
```

### Custom Server Name

```python
proxy = create_proxy(
    server,
    server_name="custom-proxy",
    enable_todos=True
)
```

## TodoServer Tools

### TodoWrite

Write or update the todo list for the current session.

**Parameters:**
- `todos: List[TodoItem]` - Complete list of todos with their current status

**TodoItem schema:**
```python
{
    "content": str,        # Imperative form: "Run tests"
    "status": "pending" | "in_progress" | "completed"
}
```

**Returns:**
```python
{
    "success": bool,
    "message": str  # e.g., "Updated 3 todos. In progress: Fix bug"
}
```

### TodoRead

Read the current todo list.

**Returns:**
```python
{
    "todos": [
        {
            "content": "Task description",
            "status": "completed"
        },
        ...
    ]
}
```

## Instructions

TodoServer provides comprehensive instructions that guide LLMs to:

1. **Break down tasks** into actionable steps
2. **Update status** before and after each task
3. **Maintain exactly one** task as `in_progress`
4. **Mark completed** immediately after finishing

See `src/wags/middleware/todo.py` for the full instruction text.

## Current Limitations

### No Instruction Merging

If your target server has instructions, you cannot use `enable_todos=True`:

```python
server = FastMCP("my-server", instructions="Do something")
proxy = create_proxy(server, enable_todos=True)  # ❌ Raises NotImplementedError
```

**Workaround:** Remove instructions from the target server.

### No Persistence

Todo state is in-memory only. When the proxy instance is destroyed, todos are lost.

### No Customization

You cannot modify the todo instructions or tool behavior without editing the source code.

## Implementation Details

### Instruction Inheritance

`_WagsProxy` automatically inherits instructions from target servers:

```python
server = FastMCP("test", instructions="Target instructions")
proxy = create_proxy(server)  # proxy.instructions == "Target instructions"
```

When `enable_todos=True`, the proxy uses TodoServer instructions instead.

### State Isolation

Each `TodoServer` instance maintains its own in-memory state:

```python
proxy1 = create_proxy(server1, enable_todos=True)
proxy2 = create_proxy(server2, enable_todos=True)
# proxy1 and proxy2 have separate todo lists
```

## Example Workflow

```python
# Agent receives task: "Build project and fix errors"

# 1. Agent calls TodoWrite
TodoWrite(todos=[
    {"content": "Build project", "status": "pending"},
    {"content": "Fix errors", "status": "pending"}
])

# 2. Agent starts first task
TodoWrite(todos=[
    {"content": "Build project", "status": "in_progress"},
    {"content": "Fix errors", "status": "pending"}
])

# 3. Agent runs build tool, finds 3 errors

# 4. Agent updates todos
TodoWrite(todos=[
    {"content": "Build project", "status": "completed"},
    {"content": "Fix error in utils.py", "status": "in_progress"},
    {"content": "Fix error in api.py", "status": "pending"},
    {"content": "Fix error in models.py", "status": "pending"}
])

# 5. Agent fixes each error, updating status after each one
# ... continues until all completed
```

## See Also

- [Middleware Overview](overview.md)
- Source: `src/wags/middleware/todo.py`
