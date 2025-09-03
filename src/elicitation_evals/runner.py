"""Test execution logic for evaluation framework."""

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional

from .config import generate_config, generate_script, prepare_test_data


def run_test(
    test_case: Dict[str, Any], 
    model: str = "gpt-4o", 
    temperature: float = 0.001,
    output_dir: Optional[Path] = None
) -> Dict[str, Any]:
    """
    Execute a test case with fast-agent.
    
    Args:
        test_case: Test case dictionary with function definitions and questions
        model: Model name to use
        temperature: Temperature setting
        output_dir: Directory for outputs (default: "outputs")
        
    Returns:
        Dictionary with execution results
    """
    test_id = test_case["id"]
    
    # Set default output directory
    if output_dir is None:
        output_dir = Path("outputs")
    
    print(f"Setting up test {test_id}...")
    
    # Generate configuration
    config_path = generate_config(test_case, model, temperature, output_dir)
    
    # Prepare test data for MCP servers
    test_data_path = prepare_test_data(test_case, output_dir)
    
    # Generate script
    script_content = generate_script(test_case, config_path, model, output_dir)
    
    # Save script to temporary file
    script_path = Path(tempfile.mktemp(suffix=".py"))
    script_path.write_text(script_content)
    
    print(f"Running test {test_id} with {model}...")
    
    # Clear any existing JSONL file from previous runs
    log_file = output_dir / "raw" / f"{test_id}_fastagent.jsonl"
    if log_file.exists():
        print(f"Clearing existing log file: {log_file}")
        log_file.unlink()
    
    try:
        # Execute the script
        result = subprocess.run(
            ["python", str(script_path)],
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        # Check if output file was created AND script succeeded
        success = log_file.exists() and result.returncode == 0
        
        if result.returncode != 0:
            print(f"Script exited with code {result.returncode}")
            if result.stderr:
                print(f"Error output: {result.stderr[:500]}...")
        
        return {
            "success": success,
            "test_id": test_id,
            "output_file": str(log_file) if success else None,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "return_code": result.returncode
        }
        
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "test_id": test_id,
            "error": "Test execution timed out after 5 minutes"
        }
        
    except Exception as e:
        return {
            "success": False,
            "test_id": test_id,
            "error": str(e)
        }
        
    finally:
        # Clean up temporary files
        script_path.unlink(missing_ok=True)
        test_data_path.unlink(missing_ok=True)