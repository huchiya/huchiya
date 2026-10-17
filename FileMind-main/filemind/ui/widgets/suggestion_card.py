"""Clickable task starter card used on the Orbit landing page."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout

from filemind.ui.styles.icons import svg_icon


class SuggestionCard(QPushButton):
    """A small prompt card that fills the chat composer with a real task."""

    selected = Signal(str, str)

    def __init__(self, title: str, description: str, prompt: str, icon: str) -> None:
        super().__init__()
        self.setObjectName("OrbitSuggestionCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 15, 16, 15)
        badge = QLabel()
        badge.setObjectName("OrbitSuggestionIcon")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setFixedSize(40, 40)
        badge.setPixmap(svg_icon(icon, "#7557DB", 24).pixmap(24, 24))
        name = QLabel(title)
        name.setObjectName("OrbitSuggestionTitle")
        detail = QLabel(description)
        detail.setObjectName("OrbitSuggestionDescription")
        detail.setWordWrap(True)
        layout.addWidget(badge, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(name)
        layout.addWidget(detail, 1)
        self.clicked.connect(lambda: self.selected.emit(title, prompt))
