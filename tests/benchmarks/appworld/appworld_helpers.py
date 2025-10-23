"""AppWorld integration helpers - instructions and API prediction."""

import json
from pathlib import Path
from typing import Any, Literal, cast

import appworld_experiments
from appworld.common.io import dump_yaml, read_file, read_json
from appworld.common.text import render_template
from appworld.task import Task
from appworld_experiments.code.common.api_predictor import APIPredictor

# Path to installed appworld_experiments package
EXPERIMENTS_PATH = Path(appworld_experiments.__file__).parent


def predict_apis(
    task_id: str,
    mode: str = "predicted",
    model_name: str = "gpt-4o-mini",
) -> list[str]:
    """
    Predict which APIs are needed for a task using AppWorld's APIPredictor.

    Args:
        task_id: AppWorld task ID
        mode: predicted/ground_truth/all
        model_name: Model for prediction (only used if mode="predicted")

    Returns:
        List of API names (typically 6-20 APIs instead of 400+)
    """
    task = Task.load(
        task_id=task_id,
        storage_type="memory",
        load_ground_truth=(mode == "ground_truth"),
        ground_truth_mode="full" if mode == "ground_truth" else "minimal",
    )

    prompt_path = EXPERIMENTS_PATH / "prompts/api_predictor.txt"

    predictor = APIPredictor(
        prompt_file_path=str(prompt_path),
        demo_task_ids=[],
        max_predicted_apis=20,
        app_api_separator="__",
        mode=cast(Literal["ground_truth", "predicted", "all"], mode),
    )

    if mode == "predicted":
        raise NotImplementedError(
            "Predicted mode requires language model configuration. "
            "Use mode='ground_truth' (train/dev only) or mode='all' instead."
        )

    return predictor.non_predicted_apis(task)


def load_system_instruction(task: Task, max_steps: int = 40) -> str:
    """
    Load and render system instruction from AppWorld's template with demo examples.

    Args:
        task: AppWorld Task object
        max_steps: Maximum number of turns allowed

    Returns:
        Rendered system instruction with supervisor info, rules, and demos
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
        max_steps=max_steps,
    )

    # Load demo messages and format them
    demos_path = EXPERIMENTS_PATH / "prompts/function_calling_agent/demos.json"
    demo_messages = read_json(str(demos_path))

    # Validate demo_messages is a list
    if not isinstance(demo_messages, list):
        raise TypeError(f"Expected list of demo messages, got {type(demo_messages)}")

    demo_text = _format_demo_messages(demo_messages)

    return base_instruction + demo_text


def _format_demo_messages(demo_messages: list[dict[str, Any]]) -> str:
    """Format demo messages as readable conversation."""
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
                    func_args = tc["function"]["arguments"]
                    args_dict = json.loads(func_args) if isinstance(func_args, str) else func_args
                    if args_dict:
                        args_str = ", ".join(f"{k}={repr(v)}" for k, v in args_dict.items())
                        calls.append(f"{func_name}({args_str})")
                    else:
                        calls.append(f"{func_name}()")
                demo_text_parts.append("\n" + "\n".join(calls))
            elif content:
                demo_text_parts.append(f"\n{content}")
        elif role == "tool" and content:
            demo_text_parts.append(f"\n{content}")

    return "\n".join(demo_text_parts)
