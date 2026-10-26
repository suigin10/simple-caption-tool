from pathlib import Path
import sys

from captioner.paths import app_directory, cache_directory
from captioner.preferences import Preferences
from captioner.runtime import LocalRuntime


def test_frozen_app_keeps_cache_beside_executable(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "simple-caption-tool.exe"))
    monkeypatch.delenv("LORA_CAPTIONER_CACHE", raising=False)
    monkeypatch.delenv("LORA_CAPTIONER_PREFERENCES", raising=False)
    assert app_directory() == tmp_path
    assert LocalRuntime().cache == tmp_path / ".local-cache"
    assert Preferences().path == tmp_path / ".local-cache" / "preferences.json"


def test_cache_override_is_shared_by_runtime_and_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("LORA_CAPTIONER_CACHE", str(tmp_path / "custom"))
    monkeypatch.delenv("LORA_CAPTIONER_PREFERENCES", raising=False)
    assert cache_directory() == tmp_path / "custom"
    assert LocalRuntime().cache == cache_directory()
    assert Preferences().path == cache_directory() / "preferences.json"
