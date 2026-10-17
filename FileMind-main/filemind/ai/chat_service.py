"""Stateless Orbit chat orchestration over the configured model client."""

from __future__ import annotations

from pathlib import Path
from threading import Event

from filemind.ai.chat_prompts import ORBIT_SYSTEM_PROMPT
from filemind.ai.chat_attachments import build_user_content
from filemind.ai.openai_compatible import OpenAICompatibleClient
from filemind.storage.settings import AISettings


class ChatService:
    """Send one bounded conversation context to the configured provider."""

    def __init__(self, settings: AISettings) -> None:
        self._settings = settings
        self._client = OpenAICompatibleClient(settings)

    def respond(self, messages: list[dict[str, object]], cancel_event: Event,
                attachments: tuple[Path, ...] = ()) -> str:
        """Return one complete answer without storing keys or conversation state."""
        if not messages or messages[-1].get("role") != "user":
            raise ValueError("对话中没有可发送的用户消息。")
        if cancel_event.is_set():
            raise InterruptedError("生成已停止")
        if sum(_message_text_length(message) for message in messages) > 60_000:
            raise ValueError("本次对话上下文过长，请新建对话后重试。")
        request_messages = [dict(message) for message in messages]
        request_messages[-1]["content"] = build_user_content(
            str(request_messages[-1].get("content", "")), attachments, self._settings
        )
        if sum(_message_text_length(message) for message in request_messages) > 60_000:
            raise ValueError("对话与附件文本总长度过长，请减少附件或新建对话。")
        if cancel_event.is_set():
            raise InterruptedError("生成已停止")
        return self._client.complete_chat(ORBIT_SYSTEM_PROMPT, request_messages, cancel_event)


def _message_text_length(message: dict[str, object]) -> int:
    """Count text blocks in either plain-string or multimodal user messages."""
    content = message.get("content", "")
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        return sum(len(str(part.get("text", ""))) for part in content if isinstance(part, dict))
    return 0
