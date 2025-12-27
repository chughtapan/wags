""""
logging_utils.py

Utility functions for logging and saving outputs
"""

from __future__ import annotations
import json
import hashlib
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    """
    Returns current UTC time
    """
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    
    
def sha256_text(text: str) -> str:
    """
    Computes a SHA 256 hash of string

    Used to identify instruction prompts across runs instead of storing large strings everywhere
    """
    hexdigest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"sha256:{hexdigest}"


def safe_json(obj: Any) -> Any:
    """
    Convert a given object into a JSON-serializable structure
    """
    try:
        json.dumps(obj)
        return obj
    
    except Exception:
        if isinstance(obj, dict):
            return {str(k): safe_json(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [safe_json(x) for x in obj]
        if hasattr(obj, "__dict__"):
            return safe_json(obj.__dict__)
        return repr(obj)
    

def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    """
    Append a record to a .jsonl file
    
    If the file at path doesn't exist, it will be created 
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # Open the file
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
        

class TeeIO:
    """
    Similar to a file, this object processes writes to both a 
    stream (stdout, stderr) and a log file
    """
    
    def __init__(self, real_stream, log_file):
        self.real_stream = real_stream
        self.log_file = log_file
        
    def write(self, s: str) -> None:
        self.real_stream.write(s)
        self.log_file.write(s)
        
    def flush(self) -> None:
        self.real_stream.flush()
        self.log_file.flush()

    def isatty(self) -> bool:
        return False
    
