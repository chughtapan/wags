"""API prediction for AppWorld tasks."""

from pathlib import Path

import appworld_experiments
from appworld.task import Task
from appworld_experiments.code.common.api_predictor import APIPredictor

EXPERIMENTS_PATH = Path(appworld_experiments.__file__).parent
SYSTEM_APP_NAME = "supervisor"


def _get_ground_truth_apis(task: Task) -> list[str]:
    """Get exact API list from ground truth using APIPredictor."""
    prompt_path = EXPERIMENTS_PATH / "prompts" / "api_predictor.txt"
    predictor = APIPredictor(
        prompt_file_path=str(prompt_path),
        demo_task_ids=[],
        app_api_separator="__",
        mode="ground_truth",
    )
    return predictor.non_predicted_apis(task)


def _predict_apis_using_model(task: Task, model_name: str) -> list[str]:
    raise NotImplementedError(
        "Predicted mode requires language model configuration. "
        "Use mode='ground_truth' (train/dev only) or mode='all' instead."
    )


def predict_apis(
    task_id: str,
    mode: str = "predicted",
    model_name: str = "gpt-4o-mini",
) -> list[str]:
    """
    Predict which APIs are needed for a task.

    Args:
        task_id: AppWorld task ID
        mode: predicted/ground_truth/app_oracle/all
        model_name: Model for prediction (only used if mode="predicted")

    Returns:
        List of API names in format "app__method"
        - ground_truth: ~6-10 specific APIs from oracle
        - app_oracle: ~50-100 APIs from oracle-identified apps
        - all: All available APIs (no limit)
    """
    needs_ground_truth = mode in ("ground_truth", "app_oracle")
    task = Task.load(
        task_id=task_id,
        storage_type="memory",
        load_ground_truth=needs_ground_truth,
        ground_truth_mode="full" if needs_ground_truth else "minimal",
    )

    if mode == "ground_truth":
        return _get_ground_truth_apis(task)

    elif mode == "predicted":
        return _predict_apis_using_model(task, model_name)

    elif mode == "app_oracle":
        ground_truth_apis_list = _get_ground_truth_apis(task)
        required_apps = {api.split("__", 1)[0] for api in ground_truth_apis_list}

        system_apis = [api for api in ground_truth_apis_list if api.startswith(f"{SYSTEM_APP_NAME}__")]
        domain_apis = [
            f"{app_name}__{api_name}"
            for app_name, api_docs in task.api_docs.items()
            if app_name in required_apps and app_name != SYSTEM_APP_NAME
            for api_name in api_docs.keys()
        ]

        return system_apis + domain_apis

    elif mode == "all":
        return [
            f"{app_name}__{api_name}" for app_name, api_docs in task.api_docs.items() for api_name in api_docs.keys()
        ]

    raise ValueError(f"Invalid mode: {mode}")
