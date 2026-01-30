import json
import sys
from typing import Dict, List, Any


def format_code_block(content: str, language: str = "") -> str:
    """Format content as a markdown code block."""
    return f"```{language}\n{content}\n```"


def format_tool_call(tool_name: str, arguments: Dict[str, Any]) -> str:
    """Format a tool call as Python code."""
    args_str = ", ".join(f"{k}={repr(v)}" for k, v in arguments.items())
    return f"{tool_name}({args_str})"


def format_tool_result(result_content: List[Dict]) -> str:
    """Format tool result content."""
    if not result_content:
        return ""
    
    # Extract text from result
    text_parts = []
    for item in result_content:
        if item.get("type") == "text":
            text_parts.append(item.get("text", ""))
    
    combined_text = "\n".join(text_parts)
    
    # Try to parse as JSON for pretty formatting
    try:
        parsed = json.loads(combined_text)
        return format_code_block(json.dumps(parsed, indent=2), "json")
    except (json.JSONDecodeError, ValueError):
        return combined_text


def format_assistant_message(message: Dict) -> str:
    """Format an assistant message with tool calls and content."""
    output = []
    
    # Add tool calls if present
    if message.get("tool_calls"):
        output.append("**Model Output:**")
        for call_id, call_data in message["tool_calls"].items():
            tool_name = call_data.get("name", "")
            arguments = call_data.get("arguments", {})
            output.append(format_code_block(format_tool_call(tool_name, arguments), "python"))
    
    # Add text content if present
    if message.get("content"):
        for item in message["content"]:
            if item.get("type") == "text":
                text = item.get("text", "")
                if text.strip():
                    if not message.get("tool_calls"):
                        output.append("**Model Output:**")
                        output.append("")
                        output.append(f"_{text}_" if "No tool calls" in text else text)
                    else:
                        # Format as blockquote for responses after tool calls
                        lines = text.strip().split("\n")
                        output.append("")
                        for line in lines:
                            output.append(f"> {line}" if line else ">")
    
    return "\n".join(output)


def convert_json_to_markdown(data: Dict) -> str:
    """Convert JSON conversation data to Markdown format."""
    lines = []
    messages = data.get("messages", [])
    
    # Group messages into turns (user -> assistant -> tool_results -> assistant)
    turn_number = 0
    i = 0
    
    while i < len(messages):
        msg = messages[i]
        
        if msg["role"] == "user" and msg.get("content"):
            # Start of a new turn with user content
            lines.append(f"## Turn {turn_number}")
            lines.append("")
            
            # User message
            user_text = ""
            for item in msg["content"]:
                if item.get("type") == "text":
                    user_text = item.get("text", "")
                    break
            
            lines.append(f"**User:** {user_text}")
            lines.append("")
            
            # Look ahead for expected tool calls (if this is a validation document)
            # This would need to be added from external validation data
            
            # Get assistant response
            if i + 1 < len(messages) and messages[i + 1]["role"] == "assistant":
                assistant_msg = messages[i + 1]
                
                # Add tool calls
                if assistant_msg.get("tool_calls"):
                    lines.append(format_assistant_message(assistant_msg))
                    
                    # Get tool results
                    if i + 2 < len(messages) and messages[i + 2].get("tool_results"):
                        tool_results_msg = messages[i + 2]
                        for call_id, result in tool_results_msg["tool_results"].items():
                            if result.get("content"):
                                lines.append(format_tool_result(result["content"]))
                        
                        # Get final assistant response with text
                        if i + 3 < len(messages) and messages[i + 3]["role"] == "assistant":
                            final_msg = messages[i + 3]
                            if final_msg.get("content"):
                                for item in final_msg["content"]:
                                    if item.get("type") == "text":
                                        text = item.get("text", "").strip()
                                        if text:
                                            lines.append("")
                                            for line in text.split("\n"):
                                                lines.append(f"> {line}" if line else ">")
                            i += 3
                        else:
                            i += 2
                    else:
                        i += 1
                else:
                    # No tool calls, just text response
                    lines.append(format_assistant_message(assistant_msg))
                    i += 1
            
            lines.append("")
            turn_number += 1
        
        i += 1
    
    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        print("Usage: python script.py <input_json_file> [output_md_file]")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else input_file.replace(".json", ".md")
    
    # Read JSON file
    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # Convert to Markdown
    markdown = convert_json_to_markdown(data)
    
    # Write to output file
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(markdown)
    
    print(f"Conversion complete! Output written to: {output_file}")


if __name__ == "__main__":
    main()