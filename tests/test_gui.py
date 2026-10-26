import json
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtWidgets import QApplication

from captioner.gui import MainWindow, configure_app
from captioner.worker import AnalysisWorker
from captioner.core import Settings, fingerprint

APP = QApplication.instance() or QApplication([])
configure_app(APP)


ANALYSIS = {"description": "A red rectangle and a blue circle on white.",
            "character_description": "A red rectangle and a blue circle on white.",
            "style_description": "A red rectangle and a blue circle on white.",
            "content_tags": ["red rectangle", "blue circle", "white background"],
            "appearance_tags": [], "style_tags": ["flat illustration"]}


def test_gui_edit_replace_render_export_and_reopen(tmp_path):
    app = APP
    Image.new("RGB", (100, 150), "red").save(tmp_path / "日本語.png")
    window = MainWindow()
    window.load_project(tmp_path)
    window.list.setCurrentRow(0)
    window.analysis_result("日本語.png", {"event": "success", "analysis": ANALYSIS,
                                        "raw": json.dumps(ANALYSIS), "model": "fake"})
    window.editor.setPlainText("編集内容 red rectangle")
    window.find_text.setText("red rectangle")
    window.replace_text.setText("赤い四角")
    window.replace(True)
    assert window.project.records["日本語.png"].caption == "編集内容 赤い四角"
    window.output_format.setCurrentIndex(1)
    window.rebuild(True)
    assert window.project.records["日本語.png"].caption == "編集内容 赤い四角"
    window.allow_edited.setChecked(True)
    window.rebuild(True)
    assert "red rectangle, blue circle" in window.editor.toPlainText()
    window.export()
    assert (tmp_path / "日本語.txt").exists()
    window.close()
    reopened = MainWindow()
    reopened.load_project(tmp_path)
    assert reopened.project.records["日本語.png"].analysis == ANALYSIS
    assert reopened.project.settings.format == "tags"
    reopened.close()
    app.processEvents()


def test_worker_continues_after_bad_image_and_releases_runtime(tmp_path):
    app = APP
    for name in ("bad.png", "good.png"):
        Image.new("RGB", (20, 20), "red").save(tmp_path / name)
    class FakeRuntime:
        stopped = False
        def start(self, *args):
            pass
        def analyze(self, path, edge):
            if path.name == "bad.png":
                raise ValueError("bad image")
            return ANALYSIS, json.dumps(ANALYSIS)
        def stop(self):
            self.stopped = True
    runtime = FakeRuntime()
    jobs = [(name, fingerprint(tmp_path / name)) for name in ("bad.png", "good.png")]
    worker = AnalysisWorker(tmp_path, jobs, Settings(), runtime=runtime)
    results = []
    worker.result.connect(lambda key, event: results.append((key, event)))
    worker.start()
    deadline = time.monotonic() + 5
    while worker.isRunning() and time.monotonic() < deadline:
        app.processEvents()
        worker.wait(10)
    app.processEvents()
    assert not worker.isRunning()
    assert runtime.stopped
    assert [(key, e["event"]) for key, e in results] == [
        ("bad.png", "started"), ("bad.png", "error"), ("good.png", "started"), ("good.png", "success")]


def test_gui_filename_trigger_preview_and_settings_persist(tmp_path):
    Image.new("RGB", (30, 40), "red").save(tmp_path / "akari_school_001.png")
    window = MainWindow()
    window.load_project(tmp_path)
    window.list.setCurrentRow(0)
    window.trigger_source.setCurrentIndex(window.trigger_source.findData("filename"))
    window.trigger_length.setValue(2)
    assert not window.trigger.isEnabled()
    assert "akari_school" in window.trigger_preview.text()
    window.analysis_result("akari_school_001.png", {"event": "success", "analysis": ANALYSIS,
                                                  "raw": json.dumps(ANALYSIS), "model": "fake"})
    assert window.editor.toPlainText().startswith("akari_school, ")
    window.trigger_unit.setCurrentIndex(window.trigger_unit.findData("characters"))
    window.trigger_length.setValue(5)
    assert not window.trigger_separators.isEnabled()
    window.rebuild(True)
    assert window.editor.toPlainText().startswith("akari, ")
    window.close()
    reopened = MainWindow()
    reopened.load_project(tmp_path)
    assert reopened.trigger_source.currentData() == "filename"
    assert reopened.trigger_unit.currentData() == "characters"
    assert reopened.trigger_length.value() == 5
    reopened.trigger_source.setCurrentIndex(reopened.trigger_source.findData("manual"))
    assert reopened.trigger.isEnabled()
    reopened.close()
    APP.processEvents()


def test_retry_diagnostics_reach_saved_project_and_failures_continue(tmp_path):
    from captioner.runtime import AnalysisError
    for name in ("bad.png", "good.png"):
        Image.new("RGB", (20, 20), "white").save(tmp_path / name)
    window = MainWindow()
    window.load_project(tmp_path)
    class FakeRuntime:
        def start(self, *args):
            pass
        def analyze(self, path, edge):
            self.last_attempts = [{"raw": "partial", "valid": False}, {"raw": "second", "valid": False}]
            if path.name == "bad.png":
                raise AnalysisError("still incomplete", "second")
            self.last_attempts = [{"raw": "partial", "valid": False}, {"raw": json.dumps(ANALYSIS), "valid": True}]
            return ANALYSIS, json.dumps(ANALYSIS)
        def stop(self):
            pass
    jobs = [(name, fingerprint(tmp_path / name)) for name in ("bad.png", "good.png")]
    worker = AnalysisWorker(tmp_path, jobs, Settings(), runtime=FakeRuntime())
    worker.result.connect(window.analysis_result)
    worker.run()
    payload = json.loads(window.project.file.read_text(encoding="utf8"))
    records = {r["path"]: r for r in payload["images"]}
    assert records["bad.png"]["status"] == "error"
    assert records["good.png"]["status"] == "done"
    assert len(records["bad.png"]["history"][-1]["attempts"]) == 2
    assert records["bad.png"]["history"][-1]["raw"] == "second"
    assert records["good.png"]["history"][-1]["attempts"][0]["raw"] == "partial"
    window.close()
    APP.processEvents()


def test_last_settings_restore_without_opening_an_image_folder(tmp_path):
    window = MainWindow()
    assert window.model.currentData() == "joy8b"
    window.model.setCurrentIndex(window.model.findData("qwen4b"))
    window.output_format.setCurrentIndex(window.output_format.findData("mixed"))
    window.trigger_source.setCurrentIndex(window.trigger_source.findData("filename"))
    window.trigger_unit.setCurrentIndex(window.trigger_unit.findData("characters"))
    window.trigger_length.setValue(6)
    window.layers.setValue(23)
    window.allow_edited.setChecked(True)
    window.overwrite_txt.setChecked(True)
    window.filter.setCurrentIndex(window.filter.findData("error"))
    # The debounce saves even before a project is opened.
    window.save_timer.timeout.emit()
    restored = MainWindow()
    assert restored.project is None
    assert restored.model.currentData() == "qwen4b"
    assert restored.output_format.currentData() == "mixed"
    assert restored.trigger_source.currentData() == "filename"
    assert restored.trigger_unit.currentData() == "characters"
    assert restored.trigger_length.value() == 6
    assert restored.layers.value() == 23
    assert restored.allow_edited.isChecked() and restored.overwrite_txt.isChecked()
    assert restored.filter.currentData() == "error"
    new_folder = tmp_path / "new-images"
    new_folder.mkdir()
    restored.load_project(new_folder)
    assert restored.project.settings.model == "qwen4b"
    assert restored.project.settings.trigger_length == 6
    restored.close()
    window.close()
    APP.processEvents()


def test_all_reanalysis_includes_done_and_hidden_images_and_protects_edits(tmp_path, monkeypatch):
    import captioner.gui as gui
    for name in ("a.png", "b.png", "missing.png"):
        Image.new("RGB", (20, 20), "white").save(tmp_path / name)
    window = MainWindow()
    window.load_project(tmp_path)
    records = window.project.records
    records["a.png"].analysis = ANALYSIS
    records["a.png"].status = "done"
    records["a.png"].caption = "hand edited"
    records["a.png"].edited = True
    records["b.png"].status = "error"
    (tmp_path / "missing.png").unlink()
    records["missing.png"].status = "missing"
    window.filter.setCurrentIndex(window.filter.findData("pending"))
    assert window.items["a.png"].isHidden()
    captured = []
    class RecordingWorker(AnalysisWorker):
        def start(self):
            captured.append(self)
    monkeypatch.setattr(gui, "AnalysisWorker", RecordingWorker)
    window.all_button.click()
    assert len(captured) == 1
    assert {key for key, _ in captured[0].jobs} == {"a.png", "b.png"}
    assert not window.all_button.isEnabled()
    assert not window.force_button.isEnabled()
    window.analysis_result("a.png", {"event": "success", "analysis": ANALYSIS,
                                     "raw": json.dumps(ANALYSIS), "model": "fake"})
    assert records["a.png"].caption == "hand edited"
    window.analysis_finished()
    assert window.all_button.isEnabled()
    window.close()
    APP.processEvents()


def test_hair_detail_option_is_saved_and_restored(tmp_path):
    window = MainWindow()
    assert window.detailed_hair.isChecked()
    window.detailed_hair.setChecked(False)
    window.close()
    restored = MainWindow()
    assert not restored.detailed_hair.isChecked()
    restored.close()
    APP.processEvents()
