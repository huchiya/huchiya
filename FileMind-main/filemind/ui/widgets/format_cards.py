"""Responsive pastel format cards with explicit implementation states."""

from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from filemind.conversion.capabilities import FormatCapability, capabilities


class FormatCards(QWidget):
    """Show concrete local capabilities and limitations instead of format claims."""

    def __init__(self) -> None:
        super().__init__()
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(12)
        self.cards = [self._card(item) for item in capabilities()]
        self._columns = 0
        self._reflow()

    @staticmethod
    def _card(item: FormatCapability) -> QFrame:
        card = QFrame()
        card.setObjectName("CapabilityTile")
        card.setProperty("tint", item.tint)
        column = QVBoxLayout(card)
        column.setContentsMargins(16, 14, 16, 14)
        column.setSpacing(8)
        top = QHBoxLayout()
        title = QLabel(item.title)
        title.setObjectName("TileTitle")
        title.setWordWrap(True)
        top.addWidget(title, 1)
        state = QLabel(item.state)
        state.setObjectName("CapabilityState")
        top.addWidget(state)
        column.addLayout(top)
        for text in (f"输入：{item.inputs}", f"输出：{item.outputs}", item.detail):
            label = QLabel(text)
            label.setObjectName("CapabilityDetail")
            label.setWordWrap(True)
            column.addWidget(label)
        column.addStretch(1)
        return card

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._reflow()

    def _reflow(self) -> None:
        columns = 3 if self.width() >= 900 else 2 if self.width() >= 520 else 1
        if columns == self._columns:
            return
        while self.grid.count():
            self.grid.takeAt(0)
        for index, card in enumerate(self.cards):
            self.grid.addWidget(card, index // columns, index % columns)
        self._columns = columns
