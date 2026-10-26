import hashlib
import io
import threading
import zipfile

import pytest

from captioner.runtime import Cancelled, LocalRuntime, download, extract_zip


class Response(io.BytesIO):
    status = 200
    headers = {}


def test_resume_checks_range_and_hash(tmp_path, monkeypatch):
    data = b"verified model contents"
    asset = {"name": "m.gguf", "size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
             "url": "https://huggingface.co/test/model/resolve/pinned/m.gguf"}
    (tmp_path / "m.gguf.part").write_bytes(data[:4])
    def open_response(request, **kwargs):
        assert request.headers["Range"] == "bytes=4-"
        response = Response(data[4:])
        response.status = 206
        response.headers = {"Content-Range": f"bytes 4-{len(data)-1}/{len(data)}"}
        return response
    monkeypatch.setattr("urllib.request.urlopen", open_response)
    path = download(asset, tmp_path, threading.Event(), lambda _: None)
    assert path.read_bytes() == data
    assert not (tmp_path / "m.gguf.part").exists()


def test_download_rejects_hash_mismatch(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: Response(b"bad"))
    with pytest.raises(ValueError, match="検証"):
        download({"name": "m", "size": 3, "sha256": "0"*64, "url": "https://example.com/m"},
                 tmp_path, threading.Event(), lambda _: None)
    assert not (tmp_path / "m").exists()


def test_cancel_preserves_partial_download(tmp_path):
    partial = tmp_path / "m.part"
    partial.write_bytes(b"part")
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(Cancelled):
        download({"name": "m", "size": 8, "sha256": "x", "url": "https://example.com/m"},
                 tmp_path, cancel, lambda _: None)
    assert partial.read_bytes() == b"part"


def test_zip_cannot_escape_target(tmp_path):
    path = tmp_path / "bad.zip"
    with zipfile.ZipFile(path, "w") as out:
        out.writestr("../escape", "bad")
    with pytest.raises(ValueError):
        extract_zip(path, tmp_path / "runtime")
    assert not (tmp_path / "escape").exists()


def test_remote_inference_endpoint_is_rejected():
    runtime = LocalRuntime()
    runtime.base_url = "https://example.com"
    with pytest.raises(ValueError, match="ローカル"):
        runtime.request("/v1/chat/completions", {"private": "data"})


def test_relative_cache_is_resolved_before_subprocess_changes_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runtime = LocalRuntime(tmp_path / ".." / tmp_path.name / "cache")
    assert runtime.cache.is_absolute()
    assert runtime.cache == tmp_path / "cache"
