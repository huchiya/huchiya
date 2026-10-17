"""Markdown-aware conversation message bubble for Orbit."""

from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl, QRect, QRectF
from PySide6.QtGui import (QColor, QPainter, QPainterPath, QPen, QPixmap, QResizeEvent,
                           QTextDocument)
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QSizePolicy, QTextBrowser,
                               QVBoxLayout, QWidget)

from filemind.chat_models import ChatMessage
from filemind.ui.styles.icons import svg_icon
from filemind.ui.styles.theme import COLORS

_AI_AVATAR_PATH = Path(__file__).resolve().parent.parent / "assets" / "ai_avatar.png"


class LocalMarkdownView(QTextBrowser):
    """Render text without automatically loading model-supplied local images."""

    def loadResource(self, resource_type: int, name: QUrl) -> object:
        if resource_type == QTextDocument.ResourceType.ImageResource:
            return QPixmap()
        return None


class AvatarLabel(QWidget):
    """Circular avatar: the Orbit planet image for the assistant, and a purple
    person glyph on a soft purple tile for the user."""

    SIZE = 38

    def __init__(self, is_user: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._is_user = is_user
        self.setFixedSize(self.SIZE, self.SIZE)
        self._avatar_pix = QPixmap() if is_user else QPixmap(str(_AI_AVATAR_PATH))

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        target = self.rect()
        if self._is_user:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(COLORS["purple_soft"]))
            painter.drawEllipse(target.adjusted(1, 1, -1, -1))
            icon = svg_icon("user", COLORS["purple"], 22)
            icon.paint(painter, QRect(0, 0, self.SIZE, self.SIZE).adjusted(8, 8, -8, -8))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(COLORS["purple_border"]), 1.2))
            painter.drawEllipse(QRectF(target).adjusted(0.7, 0.7, -0.7, -0.7))
        elif not self._avatar_pix.isNull():
            clip = QPainterPath()
            clip.addEllipse(QRectF(target))
            painter.setClipPath(clip)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(COLORS["purple"]))
            painter.drawEllipse(target.adjusted(0, 0, -1, -1))
            painter.drawPixmap(target, self._avatar_pix, self._avatar_pix.rect())
            painter.setClipping(False)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(COLORS["purple_border"]), 1.4))
            painter.drawEllipse(QRectF(target).adjusted(0.7, 0.7, -0.7, -0.7))
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(COLORS["purple"]))
            painter.drawEllipse(target.adjusted(1, 1, -1, -1))


class ChatMessageBubble(QWidget):
    """Render a user or assistant message with safe, local Markdown display."""

    def __init__(self, message: ChatMessage, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        is_user = message.role == "user"
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 8, 14, 8)
        row.setSpacing(10)
        self.bubble = QFrame()
        self.bubble.setObjectName("OrbitUserBubble" if is_user else "OrbitAssistantBubble")
        self.bubble.setMaximumWidth(720)
        column = QVBoxLayout(self.bubble)
        column.setContentsMargins(15, 12, 15, 12)
        caption = QLabel("你" if is_user else "Orbit")
        caption.setObjectName("OrbitMessageCaption")
        column.addWidget(caption)
        self.attachment_label = QLabel("  ·  ".join(message.attachments))
        self.attachment_label.setObjectName("OrbitMessageAttachments")
        self.attachment_label.setWordWrap(True)
        self.attachment_label.setVisible(bool(message.attachments))
        column.addWidget(self.attachment_label)
        self.content = LocalMarkdownView()
        self.content.setFrameShape(QFrame.Shape.NoFrame)
        self.content.setObjectName("OrbitMessageContent")
        self.content.setReadOnly(True)
        self.content.setOpenExternalLinks(False)
        self.content.setOpenLinks(False)
        self.content.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.content.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.content.setMinimumHeight(34)
        self.content.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.content.document().setDefaultStyleSheet(
            "pre, code { font-family: Consolas, 'Cascadia Code', monospace; "
            "background: #F1EFFA; color: #32235B; }"
            "blockquote { color: #64748B; border-left: 3px solid #B8A6F3; }"
        )
        if is_user:
            self.content.setPlainText(message.content)
        else:
            self.content.setMarkdown(message.content)
        column.addWidget(self.content)
        # Symmetric avatar columns so the assistant/user avatars line up on the
        # two edges and the bubble always sits in the same central content area.
        self.avatar = AvatarLabel(is_user)
        left_slot = self._avatar_slot(self.avatar if not is_user else None)
        right_slot = self._avatar_slot(self.avatar if is_user else None)
        row.addWidget(left_slot, 0, Qt.AlignmentFlag.AlignTop)
        if is_user:
            row.addStretch(1)
            row.addWidget(self.bubble, 0, Qt.AlignmentFlag.AlignTop)
        else:
            row.addWidget(self.bubble, 1, Qt.AlignmentFlag.AlignTop)
        row.addWidget(right_slot, 0, Qt.AlignmentFlag.AlignTop)
        self._resize_to_document()

    @staticmethod
    def _avatar_slot(avatar: QWidget | None) -> QWidget:
        slot = QWidget()
        slot.setFixedWidth(AvatarLabel.SIZE)
        slot.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        slot_layout = QHBoxLayout(slot)
        slot_layout.setContentsMargins(0, 0, 0, 0)
        slot_layout.setSpacing(0)
        if avatar is not None:
            slot_layout.addWidget(avatar, 0, Qt.AlignmentFlag.AlignTop)
        return slot

    def _resize_to_document(self) -> None:
        document = self.content.document()
        document.setTextWidth(max(120, self.content.viewport().width()))
        height = max(34, math.ceil(document.size().height()) + 8)
        if self.content.height() != height:
            self.content.setFixedHeight(height)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        QTimer.singleShot(0, self._resize_to_document)
