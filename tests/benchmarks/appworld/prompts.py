"""AppWorld prompt and instruction management."""

import json
from pathlib import Path
from typing import Any

import appworld_experiments
from appworld.common.io import dump_yaml, read_file, read_json
from appworld.common.text import render_template
from appworld.task import Task
from fast_agent.mcp.common import create_namespaced_name

# Path to installed appworld_experiments package
EXPERIMENTS_PATH = Path(appworld_experiments.__file__).parent


def load_system_instruction(task: Task, use_few_shot: bool = False) -> str:
    """
    Load and render system instruction from AppWorld's template.

    Args:
        task: AppWorld Task object
        use_few_shot: If True, include demo examples in prompt. Default is False (zero-shot).

    Returns:
        Rendered system instruction with supervisor info and rules.
        If use_few_shot=True, also includes worked-out demo examples.
    """
    # Load and render base system instruction template
    template_path = Path(__file__).parent / "system_instruction.txt"
    template_content = read_file(str(template_path))

    # Ensure template is string (read_file can return bytes)
    if isinstance(template_content, bytes):
        template_content = template_content.decode("utf-8")

    # Format app descriptions as YAML
    app_descriptions_yaml = dump_yaml(task.app_descriptions).rstrip()

    # Render template with variables
    base_instruction = render_template(
        template_content,
        main_user=task.supervisor,
        app_descriptions=app_descriptions_yaml,
    )

    # Zero-shot mode: return base instruction as-is
    if not use_few_shot:
        return base_instruction

    # Few-shot mode: Add intro line and demo examples
    examples_intro = (
        "\n\nNext, I will show you some worked-out examples "
        "as a tutorial before we proceed with the real task instruction."
    )
    base_instruction += examples_intro

    # Load demo messages and format them
    demos_path = EXPERIMENTS_PATH / "prompts/function_calling_agent/demos.json"
    demo_messages = read_json(str(demos_path))

    # Validate demo_messages is a list
    if not isinstance(demo_messages, list):
        raise TypeError(f"Expected list of demo messages, got {type(demo_messages)}")

    demo_text = _format_demo_messages(demo_messages)

    return base_instruction + demo_text


def _format_demo_messages(demo_messages: list[dict[str, Any]], server_name: str = "appworld") -> str:
    """
    Format demo messages as readable conversation.

    Args:
        demo_messages: List of demo message dictionaries
        server_name: MCP server name (default: "appworld")
    """
    demo_text_parts = ["\n"]

    for msg in demo_messages:
        role = msg["role"]
        content = msg.get("content")

        if role == "user" and content:
            demo_text_parts.append(
                f"----------------------------------------------------------------------------\n{content}"
            )
        elif role == "assistant":
            tool_calls = msg.get("tool_calls", [])
            if tool_calls:
                calls = []
                for tc in tool_calls:
                    func_name = tc["function"]["name"]
                    prefixed_name = create_namespaced_name(server_name, func_name)
                    func_args = tc["function"]["arguments"]
                    args_dict = json.loads(func_args) if isinstance(func_args, str) else func_args
                    if args_dict:
                        args_str = ", ".join(f"{k}={repr(v)}" for k, v in args_dict.items())
                        calls.append(f"{prefixed_name}({args_str})")
                    else:
                        calls.append(f"{prefixed_name}()")
                demo_text_parts.append("\n" + "\n".join(calls))
            elif content:
                demo_text_parts.append(f"\n{content}")
        elif role == "tool" and content:
            demo_text_parts.append(f"\n{content}")

    return "\n".join(demo_text_parts)
