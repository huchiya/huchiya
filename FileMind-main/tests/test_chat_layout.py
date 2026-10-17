"""Ensure long Markdown remains readable when the chat viewport changes."""

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QUrl
from PySide6.QtGui import QTextDocument
from PySide6.QtWidgets import QApplication

from filemind.chat_models import ChatMessage
from filemind.ui.widgets.chat_message import ChatMessageBubble, LocalMarkdownView


def process_layout() -> None:
    for _ in range(4):
        QApplication.processEvents()


def test_long_reply_reflows_and_is_not_clipped_at_400_pixels() -> None:
    message = ChatMessage("assistant", "## 测试回答\n\n" + "- 这是需要完整保留的较长回答。\n" * 60)
    widget = ChatMessageBubble(message)
    widget.resize(760, 700)
    widget.show()
    process_layout()
    wide_height = widget.content.height()
    assert wide_height > 400
    assert widget.content.height() >= widget.content.document().size().height()
    widget.resize(420, widget.height())
    process_layout()
    assert widget.content.height() >= wide_height
    assert widget.content.height() >= widget.content.document().size().height()
    widget.close()


def test_markdown_image_cannot_load_a_local_file(tmp_path: Path) -> None:
    image_path = tmp_path / "private.png"
    image_path.write_bytes(b"not a real image")
    widget = LocalMarkdownView()
    widget.setMarkdown(f"![untrusted image]({image_path.as_uri()})")
    result = widget.document().resource(QTextDocument.ResourceType.ImageResource, QUrl.fromLocalFile(str(image_path)))
    assert result is None or result.isNull()
    widget.close()
