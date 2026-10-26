import pytest


@pytest.fixture(autouse=True)
def isolate_app_preferences(tmp_path, monkeypatch):
    monkeypatch.setenv("LORA_CAPTIONER_PREFERENCES", str(tmp_path / "app-preferences.json"))
