"""Offline packaged-GUI smoke test, available only through an explicit CLI flag."""
import json
import os
from pathlib import Path
import sys
import traceback

_APPLICATION = None
_WINDOW = None


def run(output: Path) -> int:
    global _APPLICATION, _WINDOW
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["LORA_CAPTIONER_PREFERENCES"] = str(output / "preferences.json")
    from PIL import Image
    from PySide6.QtCore import QTimer
    from PySide6.QtSvg import QSvgRenderer
    from PySide6.QtWidgets import QApplication
    from captioner.core import Project
    from captioner.gui import MainWindow, configure_app
    from captioner.paths import cache_directory
    from captioner.preferences import Preferences
    from captioner.runtime import CATALOG, LocalRuntime
    report = {"frozen": bool(getattr(sys, "frozen", False)), "python_executable": Path(sys.executable).name,
              "model_inference_tested": False, "status": "failed"}
    _APPLICATION = QApplication([])
    _APPLICATION.setQuitOnLastWindowClosed(False)
    configure_app(_APPLICATION)
    fixture = output / "images"
    fixture.mkdir(exist_ok=True)
    Image.new("RGB", (200, 160), "#de725f").save(fixture / "akari_001.png")
    analysis = {"description": "A red rectangle.", "character_description": "A red rectangle.",
                "style_description": "A red rectangle.", "content_tags": ["red rectangle"],
                "appearance_tags": [], "style_tags": []}
    _WINDOW = MainWindow()
    _WINDOW.load_project(fixture)
    _WINDOW.list.setCurrentRow(0)
    _WINDOW.show()
    def finish():
        try:
            assert CATALOG["models"]["joy8b"]["assets"]
            assert _WINDOW.model.currentData() == "joy8b"
            icon = Path(__file__).parent / "icons" / "check.svg"
            assert QSvgRenderer(str(icon)).isValid(), "Bundled SVG not available"
            _WINDOW.trigger_source.setCurrentIndex(_WINDOW.trigger_source.findData("filename"))
            _WINDOW.trigger_length.setValue(1)
            _WINDOW.analysis_result("akari_001.png", {"event": "success", "analysis": analysis,
                                                      "raw": json.dumps(analysis), "model": "smoke-fixture"})
            assert _WINDOW.editor.toPlainText().startswith("akari, ")
            _WINDOW.editor.setPlainText("edited, red rectangle")
            _WINDOW.rebuild(True)
            assert _WINDOW.editor.toPlainText() == "edited, red rectangle"
            _WINDOW.export()
            assert (fixture / "akari_001.txt").read_text(encoding="utf8").strip() == "edited, red rectangle"
            assert _WINDOW.grab().save(str(output / "gui.png"))
            _WINDOW.close()
            assert Project(fixture).records["akari_001.png"].caption == "edited, red rectangle"
            assert Preferences().settings.trigger_source == "filename"
            assert LocalRuntime().cache == cache_directory()
            if report["frozen"] and "LORA_CAPTIONER_CACHE" not in os.environ:
                assert cache_directory() == Path(sys.executable).resolve().parent / ".local-cache"
            report.update({"status": "passed", "catalog_loaded": True, "svg_loaded": True,
                           "gui_rendered": True, "settings_persisted": True, "txt_exported": True,
                           "edit_protected": True, "project_reloaded": True,
                           "cache_next_to_executable": str(cache_directory())})
        except Exception:
            report["error"] = traceback.format_exc()
            _WINDOW.close()
        (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")
        _APPLICATION.quit()
    QTimer.singleShot(800, finish)
    _APPLICATION.exec()
    return 0 if report["status"] == "passed" else 1
