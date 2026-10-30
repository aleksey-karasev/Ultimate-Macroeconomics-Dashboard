"""Regression tests for document/voice delivery to the agent."""

from contextlib import nullcontext
import importlib
from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock

from core.multimodal import ProcessedUploads
import pytest

chat = importlib.import_module("pages.11_ai_agent_chat")


def _messages(state: dict) -> list[dict]:
    return cast(list[dict], state[chat.CHAT_STATE_KEY])


def _mock_ui(monkeypatch: pytest.MonkeyPatch, state: dict, submission: object) -> None:
    monkeypatch.setattr(chat.st, "session_state", state)
    monkeypatch.setattr(chat.st, "chat_input", lambda *args, **kwargs: submission)
    monkeypatch.setattr(chat.st, "spinner", lambda *args, **kwargs: nullcontext())
    monkeypatch.setattr(chat.st, "chat_message", lambda *args, **kwargs: nullcontext())
    monkeypatch.setattr(chat.st, "markdown", lambda *args, **kwargs: None)
    monkeypatch.setattr(chat.st, "caption", lambda *args, **kwargs: None)
    monkeypatch.setattr(chat.st, "empty", lambda *args, **kwargs: MagicMock())


def _capture_agent_call(monkeypatch: pytest.MonkeyPatch, captured: dict) -> None:
    def stream(**kwargs):
        captured.update(kwargs)
        yield {"type": "final", "answer": "Answer", "artifacts": {}}

    monkeypatch.setattr(chat, "agent_chat_stream", stream)


def test_document_ocr_is_sent_in_current_turn_and_stored_for_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    upload = SimpleNamespace(name="report.pdf", type="application/pdf", getvalue=lambda: b"pdf")
    submission = SimpleNamespace(text="Summarize this", files=[upload])
    state = {chat.CHAT_STATE_KEY: [], chat.SESSION_ID_KEY: "session"}
    _mock_ui(monkeypatch, state, submission)
    monkeypatch.setattr(
        chat,
        "process_uploads",
        lambda attachments: ProcessedUploads(
            text_blocks=["--- Attached file: report.pdf ---\nfull OCR text"]
        ),
    )
    captured: dict = {}
    _capture_agent_call(monkeypatch, captured)

    chat._handle_chat()

    assert "full OCR text" in captured["user_message"]
    assert captured["chat_history"] == []
    assert _messages(state)[0]["api_content"] == captured["user_message"]
    assert _messages(state)[0]["content"] == "Summarize this"


def test_voice_only_recording_is_transcribed_and_sent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audio = SimpleNamespace(name="voice.wav", type="audio/wav", getvalue=lambda: b"recorded-audio")
    state = {
        chat.CHAT_STATE_KEY: [],
        chat.SESSION_ID_KEY: "session",
        chat.VOICE_INPUT_KEY: audio,
    }
    _mock_ui(monkeypatch, state, submission=None)

    def process(attachments: list) -> ProcessedUploads:
        assert [item[0] for item in attachments] == ["voice.wav"]
        return ProcessedUploads(text_blocks=["--- Transcribed audio ---\nfull transcript"])

    monkeypatch.setattr(chat, "process_uploads", process)
    captured: dict = {}
    _capture_agent_call(monkeypatch, captured)

    chat._handle_chat()

    assert "full transcript" in captured["user_message"]
    assert _messages(state)[0]["api_content"] == captured["user_message"]


def test_follow_up_turn_includes_previous_document_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    previous_api_content = "Summarize\n\n--- Attached file ---\nfull OCR text"
    state = {
        chat.CHAT_STATE_KEY: [
            {
                "role": "user",
                "content": "Summarize",
                "api_content": previous_api_content,
            },
            {"role": "assistant", "content": "Earlier answer"},
        ],
        chat.SESSION_ID_KEY: "session",
    }
    submission = SimpleNamespace(text="What does it say about growth?", files=[])
    _mock_ui(monkeypatch, state, submission)
    captured: dict = {}
    _capture_agent_call(monkeypatch, captured)

    chat._handle_chat()

    assert captured["user_message"] == "What does it say about growth?"
    assert captured["chat_history"] == [
        {"role": "user", "content": previous_api_content},
        {"role": "assistant", "content": "Earlier answer"},
    ]
