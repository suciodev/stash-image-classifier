import sys

_LEVEL_CHARS = {
    "trace": "t",
    "debug": "d",
    "info": "i",
    "warning": "w",
    "warn": "w",
    "error": "e",
}


def log(level: str, message: str):
    char = _LEVEL_CHARS.get(level.lower(), "i")
    print(f"\x01{char}\x02{message}", file=sys.stderr, flush=True)


def progress(value: float):
    print(f"\x01p\x02{round(value, 4)}", file=sys.stderr, flush=True)
