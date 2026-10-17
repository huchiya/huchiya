"""Orbit's branded, provider-scoped online chat disclosure."""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from filemind.ui.styles.theme import resolve_qss


class OrbitPrivacyDialog(QDialog):
    """Explain the exact Orbit chat data flow before its first online request."""

    def __init__(self, provider_label: str, model_name: str, require_consent: bool,
                 parent=None) -> None:
        super().__init__(parent)
        self.require_consent = require_consent
        self.setWindowTitle("Orbit 对话与隐私")
        self.setObjectName("OrbitPrivacyDialog")
        self.setMinimumWidth(470)
        self.setModal(True)
        self._build_content(provider_label, model_name)
        self._apply_style()

    def _build_content(self, provider_label: str, model_name: str) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 22)
        layout.setSpacing(13)
        eyebrow = QLabel("ORBIT · 数据使用说明")
        eyebrow.setObjectName("PrivacyEyebrow")
        title = QLabel("你的消息将发送给 AI 服务商")
        title.setObjectName("PrivacyTitle")
        title.setWordWrap(True)
        service = QLabel(f"本次使用：{provider_label} · {model_name}")
        service.setObjectName("PrivacyService")
        service.setWordWrap(True)
        details = QLabel(
            "每次请求会发送你提交的消息、当前会话最近最多 20 条对话消息，以及 Orbit 的系统提示词。"
            "内容将由上述服务商处理。"
        )
        details.setObjectName("PrivacyDetails")
        details.setWordWrap(True)
        local = QLabel(
            "Orbit 不会自动读取文件或文件整理记录。只有你手动选择附件并确认发送时，才会读取所选内容。"
            "会话历史仅保存附件名称，不保存文件内容或本地路径。"
        )
        local.setObjectName("PrivacyDetails")
        local.setWordWrap(True)
        future = QLabel("图片理解目前仅验证支持 DeepSeek V4.1 Flash；其他文件按文本内容发送。")
        future.setObjectName("PrivacyNote")
        future.setWordWrap(True)
        for widget in (eyebrow, title, service, details, local, future):
            layout.addWidget(widget)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.cancel_button = QPushButton("取消")
        self.cancel_button.setObjectName("PrivacyCancel")
        self.cancel_button.clicked.connect(self.reject)
        self.continue_button = QPushButton("同意并继续" if self.require_consent else "关闭")
        self.continue_button.setObjectName("PrivacyContinue")
        self.continue_button.clicked.connect(self.accept)
        if not self.require_consent:
            self.cancel_button.setVisible(False)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.continue_button)
        layout.addLayout(buttons)

    def _apply_style(self) -> None:
        self.setStyleSheet(resolve_qss("""
            QDialog#OrbitPrivacyDialog { background:@card@; }
            QLabel#PrivacyEyebrow { color:@purple@; font-size:9pt; font-weight:650; }
            QLabel#PrivacyTitle { color:@text_strong@; font-size:17pt; font-weight:700; }
            QLabel#PrivacyService { background:@purple_soft@; color:@purple_text@; border-radius:10px; padding:10px 12px; }
            QLabel#PrivacyDetails { color:@text@; }
            QLabel#PrivacyNote { color:@muted@; background:@purple_soft@; border-radius:10px; padding:10px 12px; }
            QPushButton { min-height:36px; border-radius:10px; padding:7px 15px; }
            QPushButton#PrivacyCancel { color:@muted@; background:@card@; border:1px solid @purple_border@; }
            QPushButton#PrivacyContinue { color:@text_on_primary@; background:@purple@; border:1px solid @purple@; font-weight:650; }
            QPushButton#PrivacyContinue:hover { background:@send_hover@; border-color:@send_hover@; }
        """))

    def reapply_theme(self) -> None:
        """Allow a live theme change to restyle an open privacy dialog."""
        self._apply_style()
