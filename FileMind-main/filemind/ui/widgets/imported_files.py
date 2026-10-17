"""Metadata-only file list and compact, real business-state counters."""

from datetime import datetime

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from filemind.models import FileInfo
from filemind.ui.styles.file_icons import associated_file_icon


class ImportedFilesModel(QAbstractTableModel):
    """Show the snapshot of explicitly imported directory metadata."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.files: tuple[FileInfo, ...] = ()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.files)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else 4

    def headerData(self, section: int, orientation: Qt.Orientation,
                   role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return ("原文件名", "类型", "大小", "修改时间")[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if not index.isValid() or index.row() >= len(self.files):
            return None
        item = self.files[index.row()]
        if role == Qt.ItemDataRole.DecorationRole and index.column() == 0:
            return associated_file_icon(item.suffix)
        if role == Qt.ItemDataRole.ToolTipRole:
            return str(item.path)
        if role == Qt.ItemDataRole.DisplayRole:
            size = f"{item.size_bytes:,} B" if item.size_bytes < 1024 else f"{item.size_bytes / 1024:.1f} KB"
            return (item.name, item.suffix or "无扩展名", size,
                    datetime.fromtimestamp(item.modified_ns / 1e9).strftime("%Y-%m-%d %H:%M"))[index.column()]
        return None

    def set_files(self, files: list[FileInfo]) -> None:
        """Replace the metadata snapshot without opening any file."""
        self.beginResetModel()
        self.files = tuple(files)
        self.endResetModel()


class CompactMetric(QWidget):
    """Expose a small summary without a large statistic card."""

    def __init__(self, title: str) -> None:
        super().__init__()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 12, 0)
        row.setSpacing(5)
        self.value_label = QLabel("—")
        self.value_label.setObjectName("SummaryValue")
        label = QLabel(title)
        label.setObjectName("Muted")
        row.addWidget(self.value_label)
        row.addWidget(label)

    def set_value(self, value: int | str) -> None:
        """Display an actual scan or plan count."""
        self.value_label.setText(str(value))
