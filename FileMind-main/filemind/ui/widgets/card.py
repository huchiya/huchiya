"""A lightweight content card with consistent spacing."""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QVBoxLayout, QWidget


class Card(QFrame):
    """A themed white card for grouping related controls."""

    def __init__(self, parent: QWidget | None = None, padding: int = 18):
        super().__init__(parent)
        self.setProperty("card", True)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(padding, padding, padding, padding)
        self.layout.setSpacing(12)
