from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
TEXT_FIELDS = ("description", "character_description", "style_description")
TAG_FIELDS = ("content_tags", "appearance_tags", "style_tags")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as out:
            out.write(text)
            out.flush()
            os.fsync(out.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_analysis(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("解析結果がJSONオブジェクトではありません")
    for key in TEXT_FIELDS:
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise ValueError(f"解析結果の {key} がありません")
    for key in TAG_FIELDS:
        if not isinstance(data.get(key), list) or not all(isinstance(v, str) for v in data[key]):
            raise ValueError(f"解析結果の {key} は文字列の配列が必要です")
    result = {key: data[key] for key in (*TEXT_FIELDS, *TAG_FIELDS)}
    if "hair_details" in data:
        details = data["hair_details"]
        if not isinstance(details, list) or not all(isinstance(d, dict) and isinstance(d.get("description"), str)
                and isinstance(d.get("tags"), list) and all(isinstance(t, str) for t in d["tags"]) for d in details):
            raise ValueError("髪型詳細の形式が不正です")
        result["hair_details"] = details
    return result


@dataclass
class Settings:
    target: str = "character"
    format: str = "natural"
    trigger: str = ""
    trigger_source: str = "manual"
    trigger_length: int = 1
    trigger_unit: str = "words"
    trigger_separators: str = "_-"
    include_identity: bool = True  # Legacy field retained for old project JSON compatibility.
    detailed_hair: bool = True
    model: str = "joy8b"
    gpu_layers: int = 99
    max_edge: int = 1024


def resolve_trigger(settings: Settings, image_path: str | None = None) -> str:
    if settings.trigger_source == "manual":
        return settings.trigger.strip()
    if not image_path:
        raise ValueError("ファイル名トリガーには画像のファイル名が必要です")
    if settings.trigger_length < 1:
        raise ValueError("トリガーの長さは1以上にしてください")
    stem = Path(image_path.replace(chr(92), "/")).stem.strip()
    if settings.trigger_unit == "characters":
        trigger = stem[:settings.trigger_length].strip()
    else:
        words = list(re.finditer(r"[^\s" + re.escape(settings.trigger_separators) + r"]+", stem))
        count = min(settings.trigger_length, len(words))
        trigger = stem[words[0].start():words[count - 1].end()] if count else ""
    if not trigger:
        raise ValueError(f"ファイル名からトリガーを抽出できません: {image_path}")
    return trigger


def render(analysis: dict, settings: Settings, image_path: str | None = None) -> str:
    if settings.target == "character":
        prose = analysis["description"]
        tags = list(analysis["content_tags"]) + list(analysis["appearance_tags"]) + list(analysis["style_tags"])
    else:
        prose = analysis["style_description"]
        tags = list(analysis["content_tags"]) + list(analysis["appearance_tags"])
    hair_details = analysis.get("hair_details", [])
    supplements = [d["description"].strip() for d in hair_details if d.get("description", "").strip()]
    if supplements:
        prose = prose.rstrip() + " " + " ".join(supplements)
    for detail in hair_details:
        person = detail.get("person", "person")
        tags += [(person + ": " + tag) if len(hair_details) > 1 else tag for tag in detail.get("tags", [])]
    tags = list(dict.fromkeys(t.strip() for t in tags if t.strip()))
    if settings.format == "natural":
        body = prose.strip()
    elif settings.format == "tags":
        body = ", ".join(tags)
    else:
        body = prose.strip() + "\n" + ", ".join(tags)
    trigger = resolve_trigger(settings, image_path)
    return (trigger + ", " if trigger else "") + body


@dataclass
class Record:
    path: str
    fingerprint: str = ""
    analysis: dict | None = None
    caption: str = ""
    edited: bool = False
    status: str = "pending"
    error: str = ""
    history: list = field(default_factory=list)


class Project:
    def __init__(self, root: Path, default_settings: Settings | None = None):
        self.root = root.resolve()
        self.file = self.root / ".captioner" / "project.json"
        self.settings = Settings(**asdict(default_settings)) if default_settings else Settings()
        self.records: dict[str, Record] = {}
        self.scan_errors: list[str] = []
        if self.file.exists():
            data = json.loads(self.file.read_text(encoding="utf-8"))
            if data.get("schema_version") != 1:
                raise ValueError("未対応のプロジェクト形式です")
            self.settings = Settings(**data["settings"])
            for item in data["images"]:
                candidate = self.root / item["path"]
                if not candidate.resolve().is_relative_to(self.root):
                    raise ValueError("プロジェクト外を参照する画像パスがあります")
                record = Record(**item)
                if record.status == "running":
                    record.status = "pending"
                self.records[record.path] = record
        # Earlier versions allowed suppressing hair/eye color. The current policy
        # always preserves visible appearance in natural-language and tag output.
        self.settings.include_identity = True
        self.scan()

    def scan(self) -> None:
        for path in sorted(self.root.rglob("*")):
            if path.suffix.lower() not in EXTENSIONS or not path.is_file():
                continue
            if not path.resolve().is_relative_to(self.root) or ".captioner" in path.relative_to(self.root).parts:
                continue
            relative = path.relative_to(self.root).as_posix()
            try:
                signature = fingerprint(path)
            except OSError as error:
                self.scan_errors.append(f"{relative}: {error}")
                continue
            if relative not in self.records:
                self.records[relative] = Record(path=relative)
                sidecar = path.with_suffix(".txt")
                if sidecar.is_file() and sidecar.resolve().is_relative_to(self.root):
                    try:
                        self.records[relative].caption = sidecar.read_text(encoding="utf-8-sig").rstrip("\r\n")
                        self.records[relative].edited = True
                    except (OSError, UnicodeError) as error:
                        self.scan_errors.append(f"{sidecar.name}: {error}")
            record = self.records[relative]
            if record.status == "missing":
                record.status = "done" if record.analysis else "pending"
            if record.fingerprint and record.fingerprint != signature:
                record.history.append({"at": now(), "event": "image_changed", "analysis": record.analysis,
                                       "caption": record.caption})
                record.analysis = None
                record.status = "pending"
                record.error = "画像が変更されました。再解析が必要です"
            record.fingerprint = signature
        for record in self.records.values():
            if not (self.root / record.path).is_file():
                record.status = "missing"

    def save(self) -> None:
        payload = {"schema_version": 1, "saved_at": now(), "settings": asdict(self.settings),
                   "images": [asdict(r) for r in self.records.values()]}
        atomic_write(self.file, json.dumps(payload, ensure_ascii=False, indent=2))

    def edit(self, key: str, text: str) -> None:
        record = self.records[key]
        if record.caption != text:
            record.history.append({"at": now(), "event": "edit", "caption": record.caption})
            record.caption, record.edited = text, True

    def regenerate(self, keys: list[str], overwrite_edited: bool = False) -> int:
        captions = {}
        for key in keys:
            record = self.records[key]
            if record.analysis and (overwrite_edited or not record.edited):
                captions[key] = render(record.analysis, self.settings, record.path)
        for key, caption in captions.items():
            record = self.records[key]
            record.history.append({"at": now(), "event": "render", "caption": record.caption})
            record.caption = caption
            record.edited = False
        self.save()
        return len(captions)

    def export(self, overwrite: bool = False) -> tuple[int, int]:
        targets = {}
        for record in self.records.values():
            if not record.caption.strip() or record.status == "missing":
                continue
            source = self.root / record.path
            if not source.resolve().is_relative_to(self.root):
                raise ValueError("出力先がプロジェクト外です")
            if record.fingerprint != fingerprint(source):
                raise ValueError(f"画像が変更されています。フォルダーを開き直してください: {record.path}")
            target = source.with_suffix(".txt")
            if not target.resolve().is_relative_to(self.root):
                raise ValueError("TXT出力先がプロジェクト外です")
            normalized = str(target).casefold()
            if normalized in targets:
                raise ValueError(f"TXT名が重複します: {targets[normalized][0].name} / {source.name}")
            targets[normalized] = (target, record.caption)
        written = skipped = 0
        for target, text in targets.values():
            if target.exists():
                if not overwrite:
                    skipped += 1
                    continue
                # Preserve the previous sidecar before every replacement.
                backup = self.root / ".captioner" / "txt-backups" / target.relative_to(self.root)
                backup = backup.with_name(backup.name + "." + datetime.now().strftime("%Y%m%d%H%M%S%f") + ".bak")
                backup.parent.mkdir(parents=True, exist_ok=True)
                backup.write_bytes(target.read_bytes())
            atomic_write(target, text.rstrip() + "\n")
            written += 1
        return written, skipped
