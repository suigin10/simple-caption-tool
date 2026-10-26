"""Writable portable cache paths for source and frozen Windows builds."""
import os
from pathlib import Path
import sys


def app_directory() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def cache_directory() -> Path:
    return Path(os.environ.get("LORA_CAPTIONER_CACHE", str(app_directory() / ".local-cache"))).resolve()
