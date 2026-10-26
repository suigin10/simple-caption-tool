from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import threading

from PySide6.QtCore import QThread, Signal

from .core import Settings, fingerprint
from .runtime import AnalysisError, Cancelled, LocalRuntime, PROMPT_VERSION


class AnalysisWorker(QThread):
    progress = Signal(str)
    result = Signal(str, dict)
    failure = Signal(str)

    def __init__(self, root: Path, jobs: list[tuple[str, str]], settings: Settings,
                 runtime: LocalRuntime | None = None):
        super().__init__()
        self.root, self.jobs = root, jobs
        self.settings = Settings(**asdict(settings))
        self.cancel = threading.Event()
        self.runtime = runtime or LocalRuntime()

    def run(self):
        try:
            self.runtime.start(self.settings.model, self.settings.gpu_layers, self.cancel, self.progress.emit)
            for index, (key, expected_fingerprint) in enumerate(self.jobs):
                if self.cancel.is_set():
                    break
                self.progress.emit(f"解析 {index + 1}/{len(self.jobs)}: {key}")
                self.result.emit(key, {"event": "started"})
                self.runtime.last_attempts = []
                try:
                    path = self.root / key
                    if not path.resolve().is_relative_to(self.root.resolve()):
                        raise ValueError("画像パスがプロジェクト外です")
                    if fingerprint(path) != expected_fingerprint:
                        raise ValueError("画像が変更されています。フォルダーを開き直してください")
                    analysis, raw = self.runtime.analyze(path, self.settings.max_edge)
                    if fingerprint(path) != expected_fingerprint:
                        raise ValueError("解析中に画像が変更されました。再解析してください")
                    self.result.emit(key, {"event": "success", "analysis": analysis, "raw": raw,
                                           "model": self.settings.model, "prompt_version": PROMPT_VERSION,
                                           "fingerprint": expected_fingerprint,
                                           "max_edge": self.settings.max_edge,
                                           "attempts": list(getattr(self.runtime, "last_attempts", []))})
                except Exception as error:
                    self.result.emit(key, {"event": "error", "error": str(error),
                                           "raw": error.raw if isinstance(error, AnalysisError) else "",
                                           "model": self.settings.model, "prompt_version": PROMPT_VERSION,
                                           "attempts": list(getattr(self.runtime, "last_attempts", []))})
        except Cancelled:
            self.progress.emit("中止しました。取得・解析済みのデータは保存されています")
        except Exception as error:
            self.failure.emit(str(error))
        finally:
            self.runtime.stop()
