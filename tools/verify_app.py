"""Exercise real GUI -> worker -> local VLM -> JSON -> TXT -> reopen, with synthetic input."""
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageDraw
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from captioner.gui import MainWindow, configure_app

root = Path(sys.argv[1]).resolve()
root.mkdir(parents=True, exist_ok=True)
os.environ["LORA_CAPTIONER_PREFERENCES"] = str(root / ".captioner" / "preview-preferences.json")
image = Image.new("RGB", (640, 480), "white")
draw = ImageDraw.Draw(image)
draw.rectangle((55, 100, 230, 300), fill="red")
draw.ellipse((340, 110, 530, 300), fill="blue")
image.save(root / "日本語-動作確認.png")
app = QApplication([])
app.setQuitOnLastWindowClosed(False)
configure_app(app)
window = MainWindow()
window.load_project(root)
window.model.setCurrentIndex(window.model.findData("qwen4b"))
window.list.setCurrentRow(0)
window.show()
errors = []
reopened = None
deadline = time.monotonic() + 350

def complete():
    global reopened
    if window.worker is not None:
        if time.monotonic() > deadline:
            errors.append("GUI integration test timed out")
            window.cancel_analysis()
        return
    try:
        record = window.project.records["日本語-動作確認.png"]
        assert record.status == "done", record.error
        assert record.analysis
        window.editor.setPlainText("integration_test, " + record.caption)
        window.rebuild(True)
        assert record.caption.startswith("integration_test, "), "Manual edit was overwritten"
        window.export()
        text = (root / "日本語-動作確認.txt").read_text(encoding="utf8")
        assert text.startswith("integration_test, ")
        window.close()
        reopened = MainWindow()
        reopened.load_project(root)
        assert reopened.project.records["日本語-動作確認.png"].caption == text.rstrip()
        reopened.close()
    except Exception as error:
        errors.append(str(error))
    poll.stop()
    window.close()
    app.quit()

poll = QTimer()
poll.timeout.connect(complete)
QTimer.singleShot(0, lambda: window.start_analysis(False))
poll.start(100)
app.exec()
if errors:
    raise SystemExit("FAILED: " + "; ".join(errors))
print("PASSED: real GUI / Qwen / Japanese image path / autosave / edit protection / UTF-8 TXT / reopen", flush=True)
