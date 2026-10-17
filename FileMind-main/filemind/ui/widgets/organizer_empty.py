"""Compact, actionable organizer guidance that disappears after import."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QPushButton, QStyle, QVBoxLayout, QWidget


class OrganizerEmpty(QWidget):
    """Guide first import with real local directory selection."""

    choose_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("OrganizerEmpty")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 18, 24, 18)
        layout.setSpacing(10)
        layout.addStretch(1)
        self.title = QLabel("让文件各归其位")
        self.title.setObjectName("EmptyTitle")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title)
        self.description = QLabel("选择一个本机文件夹，先核对文件清单，再生成整理建议。")
        self.description.setObjectName("Muted")
        self.description.setWordWrap(True)
        self.description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.description)
        choose = QPushButton("选择文件夹")
        choose.setObjectName("PrimaryButton")
        choose.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon))
        choose.clicked.connect(self.choose_requested.emit)
        layout.addWidget(choose, 0, Qt.AlignmentFlag.AlignCenter)
        self.tiles = QGridLayout()
        self.tiles.setSpacing(10)
        for index, (title, detail, tint) in enumerate((
                ("文档与笔记", "PDF · Word · TXT", "blue"),
                ("图片与素材", "PNG · JPEG · WebP", "mint"),
                ("代码与项目", "Python · Java · C", "lavender"),
                ("音频与视频", "MP3 · WAV · MP4", "amber"))):
            self.tiles.addWidget(self._tile(title, detail, tint), index // 2, index % 2)
        layout.addLayout(self.tiles)
        layout.addStretch(1)

    @staticmethod
    def _tile(title: str, description: str, tint: str) -> QFrame:
        tile = QFrame()
        tile.setObjectName("CapabilityTile")
        tile.setProperty("tint", tint)
        column = QVBoxLayout(tile)
        column.setContentsMargins(12, 9, 12, 9)
        column.setSpacing(3)
        label = QLabel(title)
        label.setObjectName("TileTitle")
        column.addWidget(label)
        subtitle = QLabel(description)
        subtitle.setObjectName("Muted")
        column.addWidget(subtitle)
        return tile

    def set_selected(self, selected: bool) -> None:
        """Distinguish a first-use screen from a genuinely empty scan."""
        self.title.setText("这个目录暂无待整理文件" if selected else "让文件各归其位")
        self.description.setText("仅扫描所选目录第一层普通文件；可以选择其他文件夹。" if selected else
                                 "选择一个本机文件夹，先核对文件清单，再生成整理建议。")
