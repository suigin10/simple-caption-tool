"""Render the actual PySide6 window using a synthetic fixture, without downloading models."""
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageDraw
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from captioner.gui import MainWindow, configure_app

root = Path(sys.argv[1]).resolve()
destination = Path(sys.argv[2]).resolve()
root.mkdir(parents=True, exist_ok=True)
os.environ["LORA_CAPTIONER_PREFERENCES"] = str(root / ".captioner" / "preview-preferences.json")
for name, color in (("akari_school_001", "#db634f"), ("mio_casual_001", "#427ec1"), ("sora_uniform_001", "#7ca97d")):
    canvas = Image.new("RGB", (640, 480), "#f5f0e4")
    draw = ImageDraw.Draw(canvas)
    draw.ellipse((180, 60, 460, 340), fill=color)
    draw.rectangle((230, 350, 410, 370), fill="#324752")
    canvas.save(root / f"{name}.png")
app = QApplication([])
configure_app(app)
window = MainWindow()
window.load_project(root)
window.folder_label.setText("サンプル画像（プレビュー用）")
window.list.setCurrentRow(0)
analysis = {"description": "A red circle above a dark horizontal bar on a cream background.",
            "character_description": "A red circle above a dark horizontal bar on a cream background.",
            "style_description": "A red circle above a dark horizontal bar on a cream background.",
            "content_tags": ["red circle", "horizontal bar", "cream background"],
            "appearance_tags": [], "style_tags": ["flat illustration", "minimalism"]}
window.analysis_result("akari_school_001.png", {"event": "success", "analysis": analysis,
                                       "raw": json.dumps(analysis), "model": "preview-fixture"})
window.trigger_source.setCurrentIndex(window.trigger_source.findData("filename"))
window.trigger_length.setValue(1)
window.identity.setChecked(True)
window.rebuild(True)
window.show()
def capture():
    destination.parent.mkdir(parents=True, exist_ok=True)
    window.grab().save(str(destination))
    window.close()
    app.quit()
QTimer.singleShot(800, capture)
app.exec()
