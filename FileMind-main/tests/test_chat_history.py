"""Persistence tests for Orbit's independent local conversation history."""

import json
import tempfile
import unittest
from pathlib import Path

from filemind.storage.chat_history import ChatHistoryStore


class ChatHistoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "chat_history.json"
        self.store = ChatHistoryStore(self.path)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_conversation_messages_reload_locally_and_title_from_first_user_turn(self) -> None:
        conversation = self.store.create_conversation()
        self.store.add_message(conversation.conversation_id, "user", "解释 C 语言指针")
        saved = self.store.add_message(conversation.conversation_id, "assistant", "指针保存地址。")

        reloaded = ChatHistoryStore(self.path).get_conversation(conversation.conversation_id)

        self.assertIsNotNone(reloaded)
        self.assertEqual(saved.title, "解释 C 语言指针")
        self.assertEqual([message.role for message in reloaded.messages], ["user", "assistant"])
        self.assertEqual(reloaded.messages[1].content, "指针保存地址。")

    def test_deleting_conversation_removes_it_without_affecting_another(self) -> None:
        first = self.store.create_conversation()
        second = self.store.create_conversation()

        self.store.delete_conversation(first.conversation_id)

        self.assertIsNone(self.store.get_conversation(first.conversation_id))
        self.assertEqual([item.conversation_id for item in self.store.list_conversations()],
                         [second.conversation_id])

    def test_rejects_empty_invalid_or_oversized_messages(self) -> None:
        conversation = self.store.create_conversation()
        for role, content in (("system", "not allowed"), ("user", "  "),
                              ("assistant", "x" * 20_001)):
            with self.subTest(role=role, content_length=len(content)):
                with self.assertRaises(ValueError):
                    self.store.add_message(conversation.conversation_id, role, content)

    def test_history_contains_chat_only_and_never_receives_api_key(self) -> None:
        conversation = self.store.create_conversation()
        self.store.add_message(conversation.conversation_id, "user", "请解释递归")
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertNotIn("api_key", payload[0])
        self.assertNotIn("api_key", payload[0]["messages"][0])
        self.assertNotIn("local-only-key", self.path.read_text(encoding="utf-8"))

    def test_history_persists_attachment_names_but_not_source_paths_or_content(self) -> None:
        conversation = self.store.create_conversation()
        saved = self.store.add_message(conversation.conversation_id, "user", "描述图片",
                                       (r"C:\Users\Student\secret\photo.png",))

        reloaded = ChatHistoryStore(self.path).get_conversation(conversation.conversation_id)
        raw_history = self.path.read_text(encoding="utf-8")

        self.assertEqual(saved.messages[0].attachments, ("photo.png",))
        self.assertEqual(reloaded.messages[0].attachments, ("photo.png",))
        self.assertNotIn("C:\\Users", raw_history)
        self.assertNotIn("base64", raw_history)


if __name__ == "__main__":
    unittest.main()
