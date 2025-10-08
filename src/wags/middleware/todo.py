"""Todo management server for task tracking in LLM workflows."""

from typing import Literal

from fastmcp import FastMCP
from pydantic import BaseModel, Field

# ruff: noqa: E501
TODO_INSTRUCTIONS = """
# Task Management (MANDATORY)
You have access to the TodoWrite tools to help you manage and plan tasks. Use these tools VERY frequently to ensure that you are tracking your tasks and giving the user visibility into your progress.
These tools are also MANDATORY for planning tasks, and for breaking down larger complex tasks into smaller steps. If you do not use this tool when planning, you may forget to do important tasks - and that is unacceptable.
It is critical that you mark todos as completed as soon as you are done with a task. Do not batch up multiple tasks before marking them as completed.

**MANDATORY WORKFLOW**: For EVERY task you perform:
1. Call TodoWrite to mark the task as "in_progress" BEFORE starting it
2. Execute the task (mkdir, mv, grep, etc.)
3. Call TodoWrite to mark the task as "completed" AFTER finishing it

You MUST call TodoWrite at least 2 times per task (before and after). This is NOT optional.

Examples:

<example>
user: Run the build and fix any type errors

assistant: I'll run the build and fix any type errors. Let me use the TodoWrite tool to track this task.

[Calls TodoWrite with todos=[
  {"content": "Run the build", "status": "pending"},
  {"content": "Fix any type errors", "status": "pending"}
]]

Now let me mark the first task as in_progress and run the build.

[Calls TodoWrite with todos=[
  {"content": "Run the build", "status": "in_progress"},
  {"content": "Fix any type errors", "status": "pending"}
]]

[Runs build using Bash]

I found 10 type errors. Let me update the todos to track fixing each error.

[Calls TodoWrite with todos=[
  {"content": "Run the build", "status": "completed"},
  {"content": "Fix type error in src/utils.ts line 45", "status": "in_progress"},
  {"content": "Fix type error in src/api.ts line 23", "status": "pending"},
  {"content": "Fix type error in src/models.ts line 67", "status": "pending"},
  {"content": "Fix type error in src/handlers.ts line 89", "status": "pending"},
  {"content": "Fix remaining 6 type errors", "status": "pending"}
]]

[Fixes first error]

The first error has been fixed. Let me mark it as completed and move to the next one.

[Calls TodoWrite with todos=[
  {"content": "Run the build", "status": "completed"},
  {"content": "Fix type error in src/utils.ts line 45", "status": "completed"},
  {"content": "Fix type error in src/api.ts line 23", "status": "in_progress"},
  {"content": "Fix type error in src/models.ts line 67", "status": "pending"},
  {"content": "Fix type error in src/handlers.ts line 89", "status": "pending"},
  {"content": "Fix remaining 6 type errors", "status": "pending"}
]]

[Continues this pattern for each error, always passing the complete todo list with updated statuses]
</example>

## When to Use This Tool
Use this tool ALWAYS, especially in these scenarios:

1. Complex multi-step tasks - When a task requires 2 or more distinct steps or actions
2. Non-trivial and complex tasks - Tasks that require careful planning or multiple operations
3. User explicitly requests todo list - When the user directly asks you to use the todo list
4. User provides multiple tasks - When users provide a list of things to be done (numbered or comma-separated)
5. After receiving new instructions - Immediately capture user requirements as todos
6. When you start working on a task - Mark it as in_progress BEFORE beginning work
7. After completing a task - Mark it as completed and add any new follow-up tasks discovered during implementation

## Task States and Management

1. **Task States**: Use these states to track progress:
   - pending: Task not yet started
   - in_progress: Currently working on (limit to ONE task at a time)
   - completed: Task finished successfully

   **IMPORTANT**: Task descriptions should use imperative form:
   - content: Describe what needs to be done (e.g., "Run the build", "Fix type errors")

2. **Task Management**:
   - **CRITICAL**: Call TodoWrite BEFORE starting each task (to mark it as in_progress)
   - **CRITICAL**: Call TodoWrite AFTER completing each task (to mark it as completed)
   - **ALWAYS** pass the COMPLETE todo list with all tasks, just changing status fields
   - Update task status in real-time as you work
   - Mark tasks complete IMMEDIATELY after finishing (don't batch completions)
   - Exactly ONE task must be in_progress at any time (not less, not more)
   - Complete current tasks before starting new ones

3. **Common Mistake to Avoid**:
   - **WRONG**: Calling TodoWrite only once at the beginning and never updating
   - **RIGHT**: Calling TodoWrite multiple times - before and after each task execution

When in doubt, use this tool. Being proactive with task management demonstrates attentiveness and ensures you complete all requirements successfully.
"""


class TodoItem(BaseModel):
    """A single todo item matching Claude Code's schema."""

    content: str = Field(
        ...,
        min_length=1,
        description="The Imperative form describing what needs to be done (e.g., 'Run tests', 'Build the project')",
    )
    status: Literal["pending", "in_progress", "completed"] = Field(..., description="Current status of the task")


class TodoServer(FastMCP):
    """Todo management server with built-in instructions.

    Provides TodoWrite tool for task tracking.
    State is in-memory per instance.

    Usage:
        from wags.proxy import create_proxy

        server = FastMCP("my-server")
        proxy = create_proxy(server, enable_todos=True)
    """

    def __init__(self) -> None:
        """Initialize todo server with instructions and tools."""
        super().__init__("todo-server", instructions=TODO_INSTRUCTIONS)

        # State for todo tracking (in-memory per instance)
        self._todo_list: list[TodoItem] = []

        # Register tools
        self._register_tools()

    def _register_tools(self) -> None:
        """Register TodoWrite tool."""

        @self.tool(
            description=(
                "Use this tool to create and manage a structured task list for your current coding session. "
                "This helps you track progress, organize complex tasks, and demonstrate thoroughness to the user. "
                "It also helps the user understand the progress of the task and overall progress of their requests."
            )
        )
        async def TodoWrite(todos: list[TodoItem]) -> dict[str, bool | str]:
            """Write/update the todo list."""
            # Update todos
            self._todo_list = todos

            # Build message with in_progress task if present
            message = f"Updated {len(todos)} todos"
            in_progress_tasks = [t for t in todos if t.status == "in_progress"]
            if in_progress_tasks:
                message += f". In progress: {in_progress_tasks[0].content}"

            return {"success": True, "message": message}
