"""Local-only avatar rendering for the single-user account menu."""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPainter, QPainterPath, QPixmap

from filemind.ui.styles.icons import svg_icon


def avatar_icon(path: Path | None, size: int = 32) -> QIcon:
    """Render only the app-owned thumbnail inside a circular mask."""
    if path is None:
        return svg_icon("user", "#7C5CE7", size)
    source = QPixmap(str(path))
    if source.isNull():
        return svg_icon("user", size=size)
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    clip = QPainterPath()
    clip.addEllipse(0, 0, size * 2, size * 2)
    painter.setClipPath(clip)
    painter.drawPixmap(0, 0, source.scaled(size * 2, size * 2,
                                         Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                         Qt.TransformationMode.SmoothTransformation))
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return QIcon(pixmap)
