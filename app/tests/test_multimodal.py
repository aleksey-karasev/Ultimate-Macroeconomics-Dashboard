"""Tests for the chat multimodal-upload dispatcher.

Audio (Whisper) and document (docling) conversion are monkeypatched so the
dispatch logic is exercised without any network / OpenAI / docling call.
"""

from __future__ import annotations

import base64
from unittest.mock import MagicMock

from core import multimodal
from core.multimodal import (
    ProcessedUploads,
    api_message_content,
    augment_message,
    convert_document,
    process_uploads,
    transcribe_audio,
)
import pytest


def test_text_file_decoded_into_block() -> None:
    result = process_uploads([("notes.txt", "text/plain", b"hello world")])
    assert result.images == []
    assert any("hello world" in block for block in result.text_blocks)
    assert any("notes.txt" in block for block in result.text_blocks)


def test_image_becomes_data_uri() -> None:
    raw = b"\x89PNG\r\n\x1a\n fake"
    result = process_uploads([("chart.png", "image/png", raw)])
    assert len(result.images) == 1
    assert result.images[0].startswith("data:image/png;base64,")
    encoded = result.images[0].split(",", 1)[1]
    assert base64.b64decode(encoded) == raw
    assert any("chart.png" in block for block in result.text_blocks)


def test_empty_upload_skipped() -> None:
    result = process_uploads([("empty.pdf", "application/pdf", b"")])
    assert result.images == []
    assert any("empty" in block.lower() for block in result.text_blocks)


def test_unsupported_extension_noted() -> None:
    result = process_uploads([("archive.zip", "application/zip", b"PK\x03\x04")])
    assert any("Unsupported" in block for block in result.text_blocks)


def test_audio_transcribed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(multimodal, "transcribe_audio", lambda *_: "spoken text")
    result = process_uploads([("voice.wav", "audio/wav", b"RIFFfake")])
    assert result.images == []
    assert any("spoken text" in block for block in result.text_blocks)


def test_audio_failure_degrades_to_note(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*_: object) -> str:
        raise RuntimeError("no whisper")

    monkeypatch.setattr(multimodal, "transcribe_audio", _boom)
    result = process_uploads([("voice.mp3", "audio/mpeg", b"ID3fake")])
    assert any("Could not transcribe" in block for block in result.text_blocks)


def test_document_converted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(multimodal, "convert_document", lambda *_: "# Title\n\nbody")
    result = process_uploads([("report.pdf", "application/pdf", b"%PDF-1.4")])
    assert any("# Title" in block for block in result.text_blocks)
    assert any("report.pdf" in block for block in result.text_blocks)


def test_document_failure_degrades_to_note(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*_: object) -> str:
        raise RuntimeError("docling down")

    monkeypatch.setattr(multimodal, "convert_document", _boom)
    result = process_uploads([("report.docx", None, b"PK\x03\x04")])
    assert any("Could not read document" in block for block in result.text_blocks)


def test_augment_message_appends_blocks() -> None:
    merged = augment_message("summarize this", ["--- Attached file: a.txt ---\nbody"])
    assert merged.startswith("summarize this")
    assert "body" in merged


def test_augment_message_without_text() -> None:
    merged = augment_message("", ["block one", "block two"])
    assert merged == "block one\n\nblock two"


def test_augment_message_no_blocks_is_identity() -> None:
    assert augment_message("hello", []) == "hello"


def test_supported_extensions_cover_each_kind() -> None:
    exts = multimodal.supported_upload_extensions()
    for expected in ("pdf", "png", "mp3", "txt", "docx"):
        assert expected in exts


def test_processed_uploads_defaults() -> None:
    empty = ProcessedUploads()
    assert empty.text_blocks == []
    assert empty.images == []


def test_api_message_content_preserves_ocr_for_follow_up_turns() -> None:
    message = {
        "role": "user",
        "content": "Summarize the report",
        "api_content": "Summarize the report\n\n--- Attached file ---\nfull OCR text",
    }
    assert api_message_content(message).endswith("full OCR text")


def test_api_message_content_uses_display_text_for_regular_messages() -> None:
    assert api_message_content({"role": "user", "content": "Hello"}) == "Hello"


def _mock_http_client(monkeypatch: pytest.MonkeyPatch, payload: dict) -> MagicMock:
    client = MagicMock()
    client.__enter__.return_value = client
    response = MagicMock()
    response.json.return_value = payload
    client.post.return_value = response
    factory = MagicMock(return_value=client)
    monkeypatch.setattr(multimodal.httpx, "Client", factory)
    return factory


def test_document_conversion_allows_multi_minute_ocr(monkeypatch: pytest.MonkeyPatch) -> None:
    factory = _mock_http_client(monkeypatch, {"markdown": "full OCR text"})
    monkeypatch.setattr(multimodal, "resolve_docling_base_url", lambda: "http://docling")

    assert convert_document("report.pdf", "application/pdf", b"pdf") == "full OCR text"
    timeout = factory.call_args.kwargs["timeout"]
    assert timeout >= 600


def test_voice_transcription_allows_long_recordings(monkeypatch: pytest.MonkeyPatch) -> None:
    factory = _mock_http_client(monkeypatch, {"text": "full transcript"})
    monkeypatch.setattr(multimodal.SETTINGS, "openai_api_key", "test-key")

    assert transcribe_audio("voice.wav", b"audio") == "full transcript"
    timeout = factory.call_args.kwargs["timeout"]
    assert timeout >= 300
