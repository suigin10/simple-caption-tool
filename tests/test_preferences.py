import json

from captioner.core import Project, Settings
from captioner.preferences import Preferences


def test_fresh_install_defaults_to_joycaption(tmp_path):
    prefs = Preferences(tmp_path / "prefs.json")
    assert Settings().model == "joy8b"
    assert prefs.settings.model == "joy8b"
    assert Project(tmp_path).settings.model == "joy8b"


def test_preferences_roundtrip_includes_models_and_ui_options(tmp_path):
    path = tmp_path / "prefs.json"
    prefs = Preferences(path)
    prefs.settings = Settings(model="qwen4b", format="mixed", trigger_source="filename",
                              trigger_length=5, trigger_unit="characters", gpu_layers=20)
    prefs.allow_edited, prefs.overwrite_txt, prefs.filter = True, True, "error"
    prefs.last_folder = str(tmp_path / "images")
    prefs.save()
    loaded = Preferences(path)
    assert loaded.settings == prefs.settings
    assert loaded.allow_edited and loaded.overwrite_txt
    assert loaded.filter == "error"
    assert loaded.last_folder == prefs.last_folder


def test_invalid_preferences_do_not_prevent_startup(tmp_path):
    path = tmp_path / "prefs.json"
    path.write_text("{broken", encoding="utf8")
    prefs = Preferences(path)
    assert prefs.load_error
    assert prefs.settings.model == "joy8b"


def test_new_project_inherits_last_settings_but_existing_keeps_its_own(tmp_path):
    project = Project(tmp_path, default_settings=Settings(model="qwen4b", trigger="saved"))
    project.save()
    reopened = Project(tmp_path, default_settings=Settings(model="joy8b", trigger="different"))
    assert reopened.settings.model == "qwen4b"
    assert reopened.settings.trigger == "saved"


def test_bad_individual_preferences_fall_back_to_valid_defaults(tmp_path):
    path = tmp_path / "prefs.json"
    path.write_text(json.dumps({"schema_version": 1, "settings": {
        "model": "removed-model", "gpu_layers": "bad", "trigger_length": 0,
        "format": "mixed", "unknown_future_option": True}}), encoding="utf8")
    prefs = Preferences(path)
    assert prefs.settings.model == "joy8b"
    assert prefs.settings.gpu_layers == 99
    assert prefs.settings.trigger_length == 1
    assert prefs.settings.format == "mixed"
