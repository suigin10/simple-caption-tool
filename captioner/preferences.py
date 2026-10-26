"""App-wide last-used settings, independent of the image project."""
from dataclasses import asdict
import json
import os
from pathlib import Path

from .core import Settings, atomic_write
from .paths import cache_directory


class Preferences:
    def __init__(self, path: Path | None = None):
        cache = cache_directory()
        self.path = path or Path(os.environ.get("LORA_CAPTIONER_PREFERENCES", str(cache / "preferences.json")))
        self.settings = Settings()
        self.allow_edited = False
        self.overwrite_txt = False
        self.filter = "all"
        self.last_folder = ""
        self.load_error = ""
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if data.get("schema_version") != 1:
                raise ValueError("未対応の設定形式です")
            values = data.get("settings", {})
            if not isinstance(values, dict):
                raise ValueError("設定の形式が不正です")
            defaults = asdict(Settings())
            allowed = {"target": {"character", "style"}, "format": {"natural", "tags", "mixed"},
                       "model": {"joy8b", "qwen4b"}, "trigger_source": {"manual", "filename"},
                       "trigger_unit": {"characters", "words"}, "max_edge": {768, 1024, 1536}}
            for key, default in defaults.items():
                value = values.get(key, default)
                if type(value) is not type(default):
                    continue
                if key in allowed and value not in allowed[key]:
                    continue
                if key == "gpu_layers" and not 0 <= value <= 99:
                    continue
                if key == "trigger_length" and not 1 <= value <= 999:
                    continue
                setattr(self.settings, key, value)
            ui = data.get("ui", {})
            if not isinstance(ui, dict):
                ui = {}
            self.allow_edited = ui.get("allow_edited") is True
            self.overwrite_txt = ui.get("overwrite_txt") is True
            if ui.get("filter") in {"all", "pending", "done", "error", "edited"}:
                self.filter = ui["filter"]
            if isinstance(data.get("last_folder"), str):
                self.last_folder = data["last_folder"]
        except (OSError, UnicodeError, ValueError, TypeError, AttributeError) as error:
            self.load_error = str(error)

    def save(self):
        payload = {"schema_version": 1, "settings": asdict(self.settings),
                   "ui": {"allow_edited": self.allow_edited, "overwrite_txt": self.overwrite_txt,
                          "filter": self.filter}, "last_folder": self.last_folder}
        atomic_write(self.path, json.dumps(payload, ensure_ascii=False, indent=2))
