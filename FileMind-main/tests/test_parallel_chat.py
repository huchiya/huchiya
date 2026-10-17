"""End-to-end parallel Orbit send: one message fans out, answers are grouped."""

import os
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from filemind.ai.chat_result import ChatResult, MultiModelResult
from filemind.ai.model_config import ModelConfig
from filemind.storage.chat_history import ChatHistoryStore
from filemind.storage.settings import AISettings
from filemind.ui.main_window import MainWindow


class _ParallelSettingsStore:
    """Settings double that has two usable models and parallel mode enabled."""

    def load(self, provider_id=None):
        provider = provider_id or "openai"
        return AISettings(provider, "https://api.openai.com/v1", "gpt-4o", 10, f"key-{provider}")

    def load_models(self):
        return [ModelConfig("openai", "gpt-4o", api_key="key-openai"),
                ModelConfig("ollama", "qwen2.5:7b", api_key="ollama")]

    def save_models(self, models):
        return None

    def is_parallel_mode_enabled(self):
        return True

    def set_parallel_mode(self, enabled):
        return None

    def has_chat_ai_consent(self, provider_id):
        return True

    def set_chat_ai_consent(self, provider_id, accepted):
        return None

    def has_online_ai_consent(self):
        return True

    def set_online_ai_consent(self, accepted):
        return None


def _wait_for_chat(window: MainWindow) -> None:
    deadline = time.monotonic() + 5
    while window._chat_worker is not None and time.monotonic() < deadline:
        QTest.qWait(10)
    assert window._chat_worker is None, "并行请求未在等待时间内结束"
    QApplication.processEvents()


def test_parallel_send_fans_out_and_groups_the_answer(monkeypatch, tmp_path: Path) -> None:
    window = MainWindow(_ParallelSettingsStore(), ChatHistoryStore(tmp_path / "chats.json"))
    captured: dict[str, object] = {}

    def fake_run_models(configs, messages, options=None, cancel_event=None, **kwargs):
        captured["configs"] = list(configs)
        captured["messages"] = list(messages)
        return MultiModelResult((
            ChatResult("openai", "gpt-4o", "答案 A", 11, None, "OpenAI"),
            ChatResult("ollama", "qwen2.5:7b", "答案 B", 22, None, "Ollama"),
        ))

    monkeypatch.setattr("filemind.ui.main_window.run_models", fake_run_models)

    window._send_chat_message("你好")
    _wait_for_chat(window)

    assert [config.identity for config in captured["configs"]] == ["openai/gpt-4o", "ollama/qwen2.5:7b"]
    assert captured["messages"] == [{"role": "user", "content": "你好"}]
    conversation = window.chat_history.get_conversation(window._chat_conversation_id)
    assert conversation is not None
    answer = conversation.messages[-1]
    assert answer.role == "assistant"
    assert "### OpenAI" in answer.content and "### Ollama" in answer.content
    assert "答案 A" in answer.content and "答案 B" in answer.content
    window.close()


def test_parallel_send_surfaces_a_total_failure(monkeypatch, tmp_path: Path) -> None:
    window = MainWindow(_ParallelSettingsStore(), ChatHistoryStore(tmp_path / "chats.json"))

    def failing_run_models(configs, messages, options=None, cancel_event=None, **kwargs):
        return MultiModelResult((
            ChatResult("openai", "gpt-4o", "", 5, "无法连接服务商。", "OpenAI"),
            ChatResult("ollama", "qwen2.5:7b", "", 5, "无法连接本机 Ollama。", "Ollama"),
        ))

    monkeypatch.setattr("filemind.ui.main_window.run_models", failing_run_models)

    window._send_chat_message("你好")
    _wait_for_chat(window)

    conversation = window.chat_history.get_conversation(window._chat_conversation_id)
    assert conversation is not None
    assert conversation.messages[-1].role == "user", "全部失败时不应写入助手回答"
    window.close()
