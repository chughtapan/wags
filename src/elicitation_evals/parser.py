"""JSONL log parsing and formatting utilities."""

import json
from typing import List, Dict, Any, Tuple


def parse_jsonl(log_path: str) -> List[List[Dict[str, Any]]]:
    """
    Parse JSONL log and extract tool calls by turn.
    
    Uses turn markers to properly group tool calls by which user message
    triggered them, then creates separate BFCL turns for each tool call.
    
    Args:
        log_path: Path to the JSONL log file
        
    Returns:
        List of turns, where each turn is a list of tool call dictionaries
    """
    all_turns = []
    current_turn_tools = []
    in_turn = False
    
    with open(log_path) as f:
        for line in f:
            if not line.strip():
                continue
            
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            
            # Check for turn markers
            message = entry.get("message", "")
            if "TURN_START:" in message:
                in_turn = True
                current_turn_tools = []
            elif "TURN_END:" in message:
                # Add all tool calls from this turn as a single turn
                # If no tool calls, add empty list for this turn
                all_turns.append(current_turn_tools)
                in_turn = False
                current_turn_tools = []
            
            # Look for OpenAI completion responses within a turn
            elif in_turn and (entry.get("namespace", "").endswith(".bfcl_test") and 
                             "OpenAI completion response" in message):
                
                data = entry.get("data", {}).get("data", {})
                choices = data.get("choices", [])
                
                for choice in choices:
                    msg = choice.get("message", {})
                    
                    # Extract tool calls
                    tool_calls = msg.get("tool_calls")
                    if tool_calls:
                        for tc in tool_calls:
                            func = tc.get("function", {})
                            # Remove server prefix from function name
                            name = func.get("name", "")
                            if "-" in name:
                                name = name.split("-", 1)[-1]
                            
                            # Parse arguments
                            try:
                                args = json.loads(func.get("arguments", "{}"))
                            except json.JSONDecodeError:
                                args = {}
                            
                            # Add to current turn's tool calls
                            current_turn_tools.append({
                                "function": name,
                                "arguments": args
                            })
    
    return all_turns


def format_to_executable(tool_calls: List[List[Dict[str, Any]]]) -> List[List[str]]:
    """
    Convert tool calls to BFCL executable format.
    
    Args:
        tool_calls: List of turns with tool call dictionaries
        
    Returns:
        List of turns with executable string format
    """
    result = []
    
    for turn in tool_calls:
        turn_calls = []
        for call in turn:
            # Format arguments as Python function call
            args_list = []
            for key, value in call["arguments"].items():
                args_list.append(f"{key}={repr(value)}")
            args_str = ", ".join(args_list)
            
            # Create executable format
            turn_calls.append(f"{call['function']}({args_str})")
        
        result.append(turn_calls)
    
    return result


def parse_and_format(log_path: str) -> Tuple[List[List[Dict[str, Any]]], List[List[str]]]:
    """
    Parse JSONL log and return both raw and executable formats.
    
    Args:
        log_path: Path to the JSONL log file
        
    Returns:
        Tuple of (raw_tool_calls, executable_format)
    """
    tool_calls = parse_jsonl(log_path)
    executable = format_to_executable(tool_calls)
    return tool_calls, executable