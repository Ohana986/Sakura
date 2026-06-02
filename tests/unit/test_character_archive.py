from __future__ import annotations

import json
import uuid
import zipfile
from pathlib import Path

import pytest

from app.config.character_archive import (
    ARCHIVE_FORMAT,
    ARCHIVE_VERSION,
    CharacterArchiveError,
    export_character_archive,
    import_character_archive,
)
from app.config.character_loader import CharacterRegistry


def test_character_archive_export_then_import_roundtrip() -> None:
    root = _runtime_root("roundtrip")
    source_root = root / "source"
    profile = _build_character_package(source_root)
    archive_path = root / "demo.char"

    export_character_archive(profile, archive_path)
    result = import_character_archive(archive_path, source_root)

    assert result.character_id == "demo_1"
    assert result.display_name == "Demo（1）"

    imported = CharacterRegistry(source_root).get(result.character_id)
    assert imported.display_name == "Demo（1）"
    assert imported.initial_message == "hello"
    assert imported.card_path.read_text(encoding="utf-8") == "system prompt"
    assert imported.default_portrait_path.name == "default.png"
    assert imported.expression_portraits["开心"].name == "happy.png"
    assert imported.reply_tones == ["中性", "开心"]
    assert imported.voice is not None
    assert imported.voice.gpt_model_path is not None
    assert imported.voice.sovits_model_path is not None
    assert imported.voice.gpt_model_path.is_file()
    assert imported.voice.sovits_model_path.is_file()
    assert imported.voice.tone_ref_path.read_text(encoding="utf-8").strip().endswith("|中性")
    assert (imported.package_dir / "voice" / "refs" / "tone_refs" / "neutral.wav").is_file()


def test_character_archive_manifest_uses_sakura_format() -> None:
    root = _runtime_root("manifest")
    profile = _build_character_package(root / "source")
    archive_path = root / "demo.char"

    export_character_archive(profile, archive_path)

    with zipfile.ZipFile(archive_path, "r") as zf:
        manifest = json.loads(zf.read("manifest.json"))
        names = set(zf.namelist())

    assert manifest["format"] == ARCHIVE_FORMAT
    assert manifest["version"] == ARCHIVE_VERSION
    assert manifest["character"]["card"] == "character/card.md"
    assert manifest["character"]["portrait"]["default"] == "character/portraits/default.png"
    assert "character/voice/models/gpt.ckpt" in names
    assert "character/voice/refs/tone_refs/neutral.wav" in names


def test_character_archive_rejects_non_sakura_format() -> None:
    root = _runtime_root("non_sakura")
    archive_path = root / "legacy.char"
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps({"format": "shinsekai.character"}))
        zf.writestr("character/card.md", "legacy")

    with pytest.raises(CharacterArchiveError, match="不支持"):
        import_character_archive(archive_path, root)

    assert not list((root / "characters").glob("*/character.json"))


def test_character_archive_rejects_zip_path_traversal() -> None:
    root = _runtime_root("zip_traversal")
    archive_path = root / "bad.char"
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("../evil.txt", "evil")
        zf.writestr(
            "manifest.json",
            json.dumps(
                {
                    "format": ARCHIVE_FORMAT,
                    "version": ARCHIVE_VERSION,
                    "character": {
                        "id": "bad",
                        "display_name": "Bad",
                        "card": "character/card.md",
                        "portrait": {"default": "character/portrait.png"},
                    },
                }
            ),
        )

    with pytest.raises(CharacterArchiveError):
        import_character_archive(archive_path, root)

    assert not (root / "evil.txt").exists()
    assert not list((root / "characters").glob("*/character.json"))


def test_character_archive_rejects_unsafe_manifest_resource_path() -> None:
    root = _runtime_root("bad_manifest")
    archive_path = root / "bad_manifest.char"
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "manifest.json",
            json.dumps(
                {
                    "format": ARCHIVE_FORMAT,
                    "version": ARCHIVE_VERSION,
                    "character": {
                        "id": "bad",
                        "display_name": "Bad",
                        "card": "character/card.md",
                        "portrait": {"default": "character/../portrait.png"},
                    },
                }
            ),
        )
        zf.writestr("character/card.md", "prompt")
        zf.writestr("character/portrait.png", b"png")

    with pytest.raises(CharacterArchiveError):
        import_character_archive(archive_path, root)

    assert not list((root / "characters").glob("*/character.json"))


def _runtime_root(name: str) -> Path:
    root = (
        Path(__file__).resolve().parents[2]
        / "temp"
        / "test_runtime"
        / "character_archive"
        / name
        / uuid.uuid4().hex
    )
    root.mkdir(parents=True, exist_ok=True)
    return root


def _build_character_package(root: Path):
    character_dir = root / "characters" / "demo"
    (character_dir / "portraits").mkdir(parents=True)
    (character_dir / "voice" / "models").mkdir(parents=True)
    (character_dir / "voice" / "refs" / "tone_refs").mkdir(parents=True)
    (character_dir / "card.md").write_text("system prompt", encoding="utf-8")
    (character_dir / "portraits" / "default.png").write_bytes(b"default")
    (character_dir / "portraits" / "happy.png").write_bytes(b"happy")
    (character_dir / "voice" / "models" / "gpt.ckpt").write_bytes(b"gpt")
    (character_dir / "voice" / "models" / "sovits.pth").write_bytes(b"sovits")
    (character_dir / "voice" / "refs" / "tone_refs" / "neutral.wav").write_bytes(b"wav")
    (character_dir / "voice" / "refs" / "ref.txt").write_text(
        "voice/refs/tone_refs/neutral.wav|JA|hello|中性\n",
        encoding="utf-8",
    )
    (character_dir / "character.json").write_text(
        json.dumps(
            {
                "id": "demo",
                "display_name": "Demo",
                "initial_message": "hello",
                "card": "card.md",
                "portrait": {
                    "default": "portraits/default.png",
                    "expressions": {
                        "站立待机": "portraits/default.png",
                        "开心": "portraits/happy.png",
                    },
                },
                "voice": {
                    "gpt_model": "voice/models/gpt.ckpt",
                    "sovits_model": "voice/models/sovits.pth",
                    "tone_refs": "voice/refs/ref.txt",
                    "ref_lang": "ja",
                    "text_lang": "ja",
                },
                "reply": {
                    "tones": ["中性", "开心"],
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return CharacterRegistry(root).get("demo")
