# Todo Integration

<em class="wags-brand">wags</em> provides automatic task tracking through to improve instruction adherence for complex tasks. When enabled, LLM agents get access to instructions and tools that help break down complex tasks and track progress using a todo list.

## Usage

### Basic Usage

```python
# Create proxy with todo support
proxy = create_proxy(server, enable_todos=True)
```

## How it works?

When todo integration is enabled, the target MCP server is provided TodoWrite tools which help track the detailed tasks to be done and the current progress. Additionally, detailed instructions are provided to break down task into actionable steps, update status before and after each task, maintain exactly one task as `in_progress`, mark completed immediately after finishing, etc.

For example, when an agent receives the task "Build project and fix errors":

1. Agent calls `TodoWrite` to create initial todos:
   - "Build project" (pending)
   - "Fix errors" (pending)

2. Agent starts first task by updating status to `in_progress`

3. Agent runs build tool, finds 3 errors

4. Agent updates todos to reflect discovered errors:
   - "Build project" (completed)
   - "Fix error in utils.py" (in_progress)
   - "Fix error in api.py" (pending)
   - "Fix error in models.py" (pending)

5. Agent fixes each error, updating status after each one until all completed

See `src/wags/middleware/todo.py` for the full instruction text.

**Note:** Instructions from proxy server must be included in the agent prompt. For `fast-agent` the `{{serverInstructions}}` macro enables this feature.

## Current Limitations

### No Persistence

Todo state is in-memory only. When the proxy instance is destroyed, todos are lost.

## See Also

- [Middleware Overview](overview.md)
- Source: `src/wags/middleware/todo.py`
