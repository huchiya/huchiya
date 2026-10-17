"""Compact, accessible row used by Orbit's recent conversation list."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFontMetrics, QMouseEvent, QResizeEvent
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMenu, QSizePolicy, QToolButton, QWidget


class ConversationRow(QFrame):
    """Show an ellipsized title and contextual delete action for one chat."""

    activated = Signal(str)
    delete_requested = Signal(str)

    def __init__(self, conversation_id: str, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.conversation_id = conversation_id
        self.full_title = title
        self.setObjectName("OrbitConversationRow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 3, 4, 3)
        layout.setSpacing(4)
        self.title_label = QLabel()
        self.title_label.setObjectName("OrbitConversationTitle")
        self.title_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.title_label.setMinimumWidth(0)
        self.title_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.title_label.setToolTip(title)
        layout.addWidget(self.title_label, 1)
        self.more_button = QToolButton()
        self.more_button.setObjectName("OrbitConversationMore")
        self.more_button.setText("⋯")
        self.more_button.setToolTip("对话选项")
        self.more_button.setAccessibleName(f"删除对话：{title}")
        self.more_button.clicked.connect(self._show_menu)
        layout.addWidget(self.more_button)
        self.set_selected(False)
        self._elide_title()

    def set_selected(self, selected: bool) -> None:
        """Refresh the selected style using the parent list's current row."""
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._elide_title()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.activated.emit(self.conversation_id)
        super().mouseReleaseEvent(event)

    def _elide_title(self) -> None:
        available = max(20, self.title_label.width())
        metrics = QFontMetrics(self.title_label.font())
        self.title_label.setText(metrics.elidedText(
            self.full_title, Qt.TextElideMode.ElideRight, available
        ))

    def _show_menu(self) -> None:
        menu = QMenu(self)
        delete_action = menu.addAction("删除对话")
        delete_action.triggered.connect(lambda: self.delete_requested.emit(self.conversation_id))
        menu.exec(self.more_button.mapToGlobal(self.more_button.rect().bottomLeft()))
