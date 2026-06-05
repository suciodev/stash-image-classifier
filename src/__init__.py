import sys
import json


def log(level: str, message: str):
    """Emit a log line to stdout in the Stash plugin protocol format."""
    print(json.dumps({"type": level.capitalize(), "message": message}), flush=True)


def progress(value: float):
    """Emit a progress update (0.0–1.0) to stdout."""
    print(json.dumps({"progress": round(value, 4)}), flush=True)
