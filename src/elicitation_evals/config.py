"""Configuration utilities for BFCL evaluation."""

import json
import yaml
from pathlib import Path
from typing import Dict, Any, List
from jinja2 import Template


def generate_config(
    test_case: Dict[str, Any], 
    model: str, 
    temperature: float,
    output_dir: Path
) -> Path:
    """
    Generate YAML config for fast-agent.
    
    Args:
        test_case: BFCL test case dictionary
        model: Model name to use
        temperature: Temperature setting
        output_dir: Directory to save outputs
        
    Returns:
        Path to the generated config file
    """
    test_id = test_case["id"]
    
    # Get MCP server script path
    server_script_path = Path(__file__).parent / "bfcl" / "mcp_server.py"
    
    # Load config template
    template_path = Path(__file__).parent / "templates" / "config.yaml.j2"
    with open(template_path) as f:
        config_template = Template(f.read())
    
    # Generate config from template
    config_content = config_template.render(
        model=model,
        temperature=temperature,
        test_id=test_id,
        involved_classes=test_case.get("involved_classes", []),
        initial_configs=test_case.get("initial_config", {}),
        server_script_path=str(server_script_path.absolute()),
        test_data_path=str((output_dir / f"{test_id}_test.json").absolute()),
        log_path=str((output_dir / "raw" / f"{test_id}_fastagent.jsonl").absolute())
    )
    
    # Save config
    config_path = output_dir / "configs" / f"{test_id}.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(config_content)
    
    return config_path


def generate_script(
    test_case: Dict[str, Any],
    config_path: Path,
    model: str,
    output_dir: Path
) -> str:
    """
    Generate Python script for test execution.
    
    Args:
        test_case: BFCL test case dictionary
        config_path: Path to the config file
        model: Model name to use
        output_dir: Directory for outputs
        
    Returns:
        Generated script content as string
    """
    test_id = test_case["id"]
    
    # Prepare questions (flatten BFCL format)
    questions = []
    for turn_list in test_case.get("question", []):
        if isinstance(turn_list, list) and turn_list:
            msg = turn_list[0]
            if isinstance(msg, str):
                questions.append({"role": "user", "content": msg})
            elif isinstance(msg, dict):
                questions.append(msg)
    
    # Get server names
    servers = [
        class_name.lower().replace("api", "_api") 
        for class_name in test_case.get("involved_classes", [])
    ]
    
    # Load script template
    template_path = Path(__file__).parent / "templates" / "script.py.j2"
    with open(template_path) as f:
        script_template = Template(f.read())
    
    # Load system prompt template
    prompt_template_path = Path(__file__).parent / "templates" / "system_prompt.j2"
    with open(prompt_template_path) as f:
        prompt_template = Template(f.read())
    
    # Generate system prompt
    system_prompt = prompt_template.render()
    
    # Generate script from template
    script_content = script_template.render(
        test_id=test_id,
        config_path=str(config_path.absolute()),
        model=model,
        servers=servers,
        instruction=system_prompt,
        questions=questions,
        detailed_output=str((output_dir / "raw" / f"{test_id}_detailed.json").absolute()),
        standard_output=str((output_dir / "raw" / f"{test_id}_complete.json").absolute())
    )
    
    return script_content


def prepare_test_data(test_case: Dict[str, Any], output_dir: Path) -> Path:
    """
    Save test data for MCP servers to load.
    
    Args:
        test_case: BFCL test case dictionary
        output_dir: Directory to save outputs
        
    Returns:
        Path to the saved test data file
    """
    test_id = test_case["id"]
    test_data_path = output_dir / f"{test_id}_test.json"
    test_data_path.write_text(json.dumps(test_case))
    return test_data_path