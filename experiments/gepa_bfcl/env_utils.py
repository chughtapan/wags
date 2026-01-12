"""
env_utils.py

Environment validation util functions
"""

import sys
from typing import Any, List
import os

MODEL_PROVIDER_ENV_VARS = {
    # OpenAI
    "gpt-": ["OPENAI_API_KEY"],

    # Anthropic
    "claude-": ["ANTHROPIC_API_KEY"],
    
    # Qwen
    "qwen-": ["QWEN_API_KEY"],
    
    # Kimi
    "kimi-": ["KIMI_API_KEY"],
}

def validate_model_environment(models: List[str]) -> None:
    """
    Validate that required environment variables are set
    for the requested models. Exit early if misconfigured.
    """
    missing: dict[str, List[str]] = {}

    for model in models:
        for prefix, env_vars in MODEL_PROVIDER_ENV_VARS.items():
            if model.startswith(prefix):
                for env in env_vars:
                    val = os.getenv(env)
                    if not val or is_invalid_key(val):
                        missing.setdefault(model, []).append(env)

    if missing:
        print("\n[CONFIG ERROR] Missing required environment variables:\n")
        for model, envs in missing.items():
            print(f"  Model '{model}' requires:")
            for env in envs:
                print(f"    - {env}")
        print(
            "\nSet the missing variables and re-run. "
            "No artifacts were produced for this run.\n"
        )
        sys.exit(2)

def is_invalid_key(value: str) -> bool:
    return value.strip() == "" or value.lower().startswith("your_")