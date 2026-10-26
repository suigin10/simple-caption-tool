import pytest


@pytest.fixture(autouse=True)
def isolate_app_preferences(tmp_path, monkeypatch):
    monkeypatch.setenv("LORA_CAPTIONER_PREFERENCES", str(tmp_path / "app-preferences.json"))


@pytest.fixture(scope="session", autouse=True)
def cleanup_qt_application():
    yield
    # Dispose GUI test objects while Qt is still alive, before interpreter teardown.
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QApplication
    import gc
    import shiboken6
    app = QApplication.instance()
    if app is not None:
        for widget in app.topLevelWidgets():
            widget.close()
            widget.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
        gc.collect()
        shiboken6.delete(app)
