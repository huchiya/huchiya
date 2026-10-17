"""Local settings page: on-device workspace and data/privacy controls."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QMessageBox, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from filemind.ai.providers import PROVIDER_BY_ID
from filemind.storage.settings import SettingsError, SettingsStore
from filemind.ui.styles.theme import appearance_choices
from filemind.ui.widgets.card import Card
from filemind.ui.widgets.privacy_dialog import OrbitPrivacyDialog


class LocalSettingsPage(QWidget):
    """本机工作空间（锁屏）、外观与数据/隐私说明，独立于“模型配置”页。"""

    local_auth_requested = Signal(str)
    appearance_changed = Signal(str)

    def __init__(self, store: SettingsStore | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.store = store or SettingsStore()
        self._build_ui()

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        scroll_area = QScrollArea()
        scroll_area.setObjectName("SettingsScrollArea")
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        layout.addWidget(self._appearance_card())
        layout.addWidget(self._local_lock_card())
        layout.addWidget(self._privacy_card())
        layout.addStretch(1)
        scroll_area.setWidget(body)
        root_layout.addWidget(scroll_area)

    def _appearance_card(self) -> Card:
        card = Card()
        title = QLabel("外观")
        title.setStyleSheet("font-size:12pt;font-weight:650;")
        detail = QLabel("切换整个软件界面的主题色调。浅色为默认主题；跟随系统会随操作系统的深浅色自动切换。"
                        "绿色、橙色为可选强调主题。")
        detail.setObjectName("Muted")
        detail.setWordWrap(True)
        row = QHBoxLayout()
        caption = QLabel("主题色调")
        caption.setObjectName("Muted")
        self.appearance_combo = QComboBox()
        for value, label in appearance_choices():
            self.appearance_combo.addItem(label, value)
        getter = getattr(self.store, "get_appearance", None)
        try:
            current = getter() if callable(getter) else "light"
        except (SettingsError, OSError, ValueError):
            current = "light"
        index = self.appearance_combo.findData(current)
        self.appearance_combo.setCurrentIndex(index if index >= 0 else 0)
        self.appearance_combo.currentIndexChanged.connect(self._on_appearance_changed)
        row.addWidget(caption)
        row.addWidget(self.appearance_combo)
        row.addStretch(1)
        card.layout.addWidget(title)
        card.layout.addWidget(detail)
        card.layout.addLayout(row)
        return card

    def _on_appearance_changed(self, index: int) -> None:
        value = str(self.appearance_combo.itemData(index))
        setter = getattr(self.store, "set_appearance", None)
        if callable(setter):
            try:
                setter(value)
            except (SettingsError, OSError, ValueError):
                pass
        self.appearance_changed.emit(value)

    def _local_lock_card(self) -> Card:
        card = Card()
        title = QLabel("本机工作空间")
        title.setStyleSheet("font-size:12pt;font-weight:650;")
        detail = QLabel("密码只用于本机应用锁屏，不发送给模型服务。忘记密码可使用首次设置时保存的恢复码。"
                        "记住解锁最多保留 7 天；手动锁定或修改密码会撤销。此功能不提供磁盘加密。")
        detail.setWordWrap(True)
        detail.setObjectName("Muted")
        row = QHBoxLayout()
        self.lock_button = QPushButton("立即锁定")
        self.change_password_button = QPushButton("修改密码")
        self.lock_button.clicked.connect(lambda: self.local_auth_requested.emit("unlock"))
        self.change_password_button.clicked.connect(lambda: self.local_auth_requested.emit("change"))
        row.addWidget(self.lock_button)
        row.addWidget(self.change_password_button)
        row.addStretch(1)
        card.layout.addWidget(title)
        card.layout.addWidget(detail)
        card.layout.addLayout(row)
        return card

    def set_local_lock_available(self, available: bool) -> None:
        """Enable account actions only when the authenticated shell owns a lock."""
        for button in (self.lock_button, self.change_password_button):
            button.setEnabled(available)
            if not available:
                button.setToolTip("通过 main.py 正式入口启动后启用。")

    def _privacy_card(self) -> Card:
        card = Card()
        title = QLabel("数据与隐私")
        title.setStyleSheet("font-size:12pt;font-weight:650;")
        organize_detail = QLabel(
            "AI 整理会向所选服务发送文件名、扩展名、大小、修改时间和你填写的整理规则。在线服务由对应服务商处理这些数据。"
            "不会上传文件正文、整个文件夹或本地绝对路径。服务商会按其隐私政策处理请求。"
        )
        organize_detail.setObjectName("Muted")
        organize_detail.setWordWrap(True)
        orbit_detail = QLabel(
            "Orbit 会向当前服务商发送你输入的消息和最近最多 20 条对话上下文。会话在本机保存。"
        )
        orbit_detail.setObjectName("Muted")
        orbit_detail.setWordWrap(True)
        self.orbit_privacy_button = QPushButton("查看 Orbit 隐私说明")
        self.orbit_privacy_button.setObjectName("OrbitLinkButton")
        self.orbit_privacy_button.clicked.connect(self._show_orbit_privacy)
        card.layout.addWidget(title)
        card.layout.addWidget(organize_detail)
        card.layout.addWidget(orbit_detail)
        card.layout.addWidget(self.orbit_privacy_button, 0, Qt.AlignmentFlag.AlignLeft)
        return card

    def _show_orbit_privacy(self) -> None:
        """Let the user inspect the chat data scope at any time from settings."""
        try:
            settings = self.store.load()
        except (SettingsError, OSError, ValueError) as error:
            QMessageBox.warning(self, "无法读取当前模型", str(error))
            return
        provider = PROVIDER_BY_ID.get(settings.provider_id)
        provider_name = provider.name if provider else settings.provider_id
        OrbitPrivacyDialog(provider_name, settings.model, False, self).exec()
