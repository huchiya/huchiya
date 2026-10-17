"""Mocked request tests for Orbit's stateless chat service."""

import unittest
import base64
import tempfile
from pathlib import Path
from threading import Event
from unittest.mock import Mock, patch

from filemind.ai.chat_service import ChatService
from filemind.ai.openai_compatible import AIServiceError
from filemind.storage.settings import AISettings


class ChatServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = AISettings("deepseek", "https://api.deepseek.com", "deepseek-flash", 45,
                                   "mock-secret")

    def test_respond_reuses_configured_client_with_independent_chat_prompt(self) -> None:
        client = Mock()
        client.complete_chat.return_value = "二分查找每轮缩小一半搜索区间。"
        messages = [{"role": "user", "content": "解释二分查找"}]
        with patch("filemind.ai.chat_service.OpenAICompatibleClient", return_value=client):
            answer = ChatService(self.settings).respond(messages, Event())

        self.assertIn("二分查找", answer)
        args = client.complete_chat.call_args.args
        self.assertIn("Orbit AI 助手", args[0])
        self.assertEqual(args[1], messages)
        self.assertNotIn("mock-secret", repr(args))

    def test_cancel_event_is_passed_to_client(self) -> None:
        client = Mock()
        client.complete_chat.return_value = "已完成"
        cancel_event = Event()
        with patch("filemind.ai.chat_service.OpenAICompatibleClient", return_value=client):
            ChatService(self.settings).respond([{"role": "user", "content": "你好"}], cancel_event)

        self.assertIs(client.complete_chat.call_args.args[2], cancel_event)

    def test_cancelled_request_does_not_read_or_send_attachments(self) -> None:
        client = Mock()
        cancel_event = Event()
        cancel_event.set()
        with patch("filemind.ai.chat_service.OpenAICompatibleClient", return_value=client):
            service = ChatService(self.settings)
        with self.assertRaises(InterruptedError):
            service.respond([{"role": "user", "content": "说明图片"}], cancel_event)
        client.complete_chat.assert_not_called()

    def test_rejects_missing_final_user_turn_and_oversized_context(self) -> None:
        with patch("filemind.ai.chat_service.OpenAICompatibleClient"):
            service = ChatService(self.settings)
        with self.assertRaisesRegex(ValueError, "用户消息"):
            service.respond([{"role": "assistant", "content": "hello"}], Event())
        with self.assertRaisesRegex(ValueError, "上下文过长"):
            service.respond([{"role": "user", "content": "x" * 60_001}], Event())

    def test_provider_errors_remain_user_safe(self) -> None:
        client = Mock()
        client.complete_chat.side_effect = AIServiceError("API Key 无效或无权访问此服务。")
        with patch("filemind.ai.chat_service.OpenAICompatibleClient", return_value=client):
            with self.assertRaisesRegex(AIServiceError, "API Key 无效"):
                ChatService(self.settings).respond([{"role": "user", "content": "你好"}], Event())

    def test_image_attachment_becomes_a_deepseek_vision_part(self) -> None:
        client = Mock()
        client.complete_chat.return_value = "图片内容已收到。"
        with tempfile.TemporaryDirectory() as directory:
            image_path = Path(directory) / "课程截图.png"
            image_path.write_bytes(b"sample-image")
            with patch("filemind.ai.chat_service.OpenAICompatibleClient", return_value=client):
                ChatService(self.settings).respond(
                    [{"role": "user", "content": "请描述图片"}], Event(), (image_path,)
                )

        sent_content = client.complete_chat.call_args.args[1][-1]["content"]
        self.assertEqual(sent_content[0], {"type": "text", "text": "请描述图片"})
        self.assertEqual(sent_content[1]["type"], "image_url")
        self.assertIn(base64.b64encode(b"sample-image").decode("ascii"),
                      sent_content[1]["image_url"]["url"])

    def test_text_attachment_is_read_only_for_the_request_and_images_require_verified_model(self) -> None:
        client = Mock()
        client.complete_chat.return_value = "已分析代码。"
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "算法.py"
            source.write_text("print('hello')", encoding="utf-8")
            with patch("filemind.ai.chat_service.OpenAICompatibleClient", return_value=client):
                ChatService(self.settings).respond(
                    [{"role": "user", "content": "解释代码"}], Event(), (source,)
                )
            content = client.complete_chat.call_args.args[1][-1]["content"]
            self.assertIn("print('hello')", content[1]["text"])

            image = Path(directory) / "图.png"
            image.write_bytes(b"pixels")
            incompatible = AISettings("openai", "https://api.openai.com/v1", "gpt-5-mini", 45,
                                      "mock-secret")
            with patch("filemind.ai.chat_service.OpenAICompatibleClient", return_value=client):
                with self.assertRaisesRegex(ValueError, "仅验证支持 DeepSeek"):
                    ChatService(incompatible).respond(
                        [{"role": "user", "content": "看图"}], Event(), (image,)
                    )


if __name__ == "__main__":
    unittest.main()
