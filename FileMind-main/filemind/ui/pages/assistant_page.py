"""Independent Orbit landing page, conversation view, and local chat controls."""

from __future__ import annotations

from PySide6.QtCore import QByteArray, Qt, QTimer, Signal
from PySide6.QtGui import QPainter, QPixmap, QResizeEvent
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QStackedWidget,
    QVBoxLayout, QWidget,
)

from filemind.ai.chat_prompts import SUGGESTED_PROMPTS
from filemind.chat_models import ChatConversation, ChatMessage
from filemind.ui.widgets.chat_input import ChatInput
from filemind.ui.widgets.chat_message import AvatarLabel, ChatMessageBubble
from filemind.ui.widgets.suggestion_card import SuggestionCard
from filemind.ui.styles.theme import resolve_qss


SHORTCUT_DETAILS = (
    ("学习规划", "拆解知识点，安排阶段练习", "learning"),
    ("代码解释", "理解代码流程与报错原因", "code"),
    ("项目计划", "拆分模块、任务和里程碑", "project"),
    ("分析文档", "粘贴文本后提炼重点和待办", "document"),
)


class AssistantPage(QWidget):
    """Keep Orbit messages, request feedback, and prompts out of file organization."""

    message_submitted = Signal(str, object)
    retry_requested = Signal()
    stop_requested = Signal()
    configure_requested = Signal()
    shortcut_selected = Signal(str, str)
    model_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("OrbitRoot")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._conversation_id: str | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 12, 26, 18)
        layout.setSpacing(12)
        self.stack = QStackedWidget()
        self.home_page = self._build_home_page()
        self.chat_page = self._build_chat_page()
        self.stack.addWidget(self.home_page)
        self.stack.addWidget(self.chat_page)
        layout.addWidget(self.stack, 1)
        self._apply_style()

    def _build_home_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 6)
        layout.addStretch(1)
        orb = QLabel()
        orb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        orb.setPixmap(_orbit_pixmap())
        layout.addWidget(orb)
        title = QLabel("Orbit AI 助手")
        title.setObjectName("OrbitHeroTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        subtitle = QLabel("你的智能工作伙伴")
        subtitle.setObjectName("OrbitHeroSubtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)
        self.setup_notice = QLabel()
        self.setup_notice.setObjectName("OrbitSetupNotice")
        self.setup_notice.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setup_notice.setWordWrap(True)
        self.setup_notice.setVisible(False)
        layout.addWidget(self.setup_notice)
        layout.addSpacing(16)
        self.home_composer = ChatInput()
        self._connect_composer(self.home_composer)
        layout.addWidget(self.home_composer)
        shortcuts = QGridLayout()
        self.shortcuts_grid = shortcuts
        self._shortcut_columns = 4
        shortcuts.setSpacing(12)
        self.suggestion_cards: list[SuggestionCard] = []
        for index, (title, description, icon) in enumerate(SHORTCUT_DETAILS):
            card = SuggestionCard(title, description, SUGGESTED_PROMPTS[title], icon)
            card.selected.connect(self._shortcut_clicked)
            self.suggestion_cards.append(card)
            shortcuts.addWidget(card, 0, index)
        layout.addSpacing(8)
        layout.addLayout(shortcuts)
        layout.addStretch(1)
        footnote = QLabel("Orbit 不会读取本地文件。发送消息前会提示你哪些内容将发送给所选模型服务。")
        footnote.setObjectName("OrbitFootnote")
        footnote.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footnote.setWordWrap(True)
        layout.addWidget(footnote)
        scroll = QScrollArea()
        scroll.setObjectName("OrbitHomeScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(page)
        return scroll

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if not hasattr(self, "shortcuts_grid"):
            return
        columns = 2 if self.width() < 620 else 4
        if columns != self._shortcut_columns:
            while self.shortcuts_grid.count():
                self.shortcuts_grid.takeAt(0)
            for index, card in enumerate(self.suggestion_cards):
                self.shortcuts_grid.addWidget(card, index // columns, index % columns)
            self._shortcut_columns = columns

    def _build_chat_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        self.chat_title = QLabel("新对话")
        self.chat_title.setObjectName("OrbitChatTitle")
        layout.addWidget(self.chat_title)
        self.message_scroll = QScrollArea()
        self.message_scroll.setObjectName("OrbitMessageScroll")
        self.message_scroll.setWidgetResizable(True)
        self.message_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.messages_container = QWidget()
        self.messages_container.setObjectName("OrbitMessagesContainer")
        self.messages_container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.messages_layout = QVBoxLayout(self.messages_container)
        self.messages_layout.setContentsMargins(4, 8, 4, 8)
        self.messages_layout.setSpacing(6)
        self.messages_layout.addStretch(1)
        self.message_scroll.setWidget(self.messages_container)
        self.message_scroll.setStyleSheet("QScrollArea, QWidget#OrbitMessagesContainer {background:transparent;}")
        self.message_scroll.viewport().setStyleSheet("background:transparent;")
        layout.addWidget(self.message_scroll, 1)
        status_row = QHBoxLayout()
        self.status_label = QLabel()
        self.status_label.setObjectName("OrbitStatus")
        self.status_label.setWordWrap(True)
        status_row.addWidget(self.status_label, 1)
        self.retry_button = QPushButton("重试")
        self.retry_button.setObjectName("OrbitRetryButton")
        self.retry_button.setVisible(False)
        self.retry_button.clicked.connect(self.retry_requested.emit)
        status_row.addWidget(self.retry_button)
        self.configure_error_button = QPushButton("检查模型设置")
        self.configure_error_button.setObjectName("OrbitRetryButton")
        self.configure_error_button.setVisible(False)
        self.configure_error_button.clicked.connect(self.configure_requested.emit)
        status_row.addWidget(self.configure_error_button)
        layout.addLayout(status_row)
        self.chat_composer = ChatInput()
        self._connect_composer(self.chat_composer)
        layout.addWidget(self.chat_composer)
        return page

    def _connect_composer(self, composer: ChatInput) -> None:
        composer.send_requested.connect(self.message_submitted.emit)
        composer.stop_requested.connect(self.stop_requested.emit)
        composer.configure_requested.connect(self.configure_requested.emit)
        composer.model_selected.connect(self._composer_model_selected)

    def _composer_model_selected(self, model_id: str) -> None:
        """Keep the sibling composer in sync and forward the new active model."""
        self.home_composer.sync_model(model_id)
        self.chat_composer.sync_model(model_id)
        self.model_selected.emit(model_id)

    def _shortcut_clicked(self, title: str, prompt: str) -> None:
        self.home_composer.set_text(prompt)
        self.shortcut_selected.emit(title, prompt)

    def set_model(self, provider_id: str | None, provider_name: str | None, model_name: str | None,
                  has_api_key: bool = False) -> None:
        """Update both composers with the one actual active model profile."""
        self.home_composer.set_model(provider_id, provider_name, model_name, has_api_key)
        self.chat_composer.set_model(provider_id, provider_name, model_name, has_api_key)
        self.setup_notice.setVisible(not has_api_key)
        self.setup_notice.setText("默认使用设置页中的模型。尚未配置 API Key；附件只会在你选择并确认发送后读取。")

    def set_conversation(self, conversation: ChatConversation | None) -> None:
        """Switch views and render a persisted conversation without sharing state."""
        self._conversation_id = conversation.conversation_id if conversation else None
        self.home_composer.clear_attachments()
        self.chat_composer.clear_attachments()
        self.clear_error()
        if conversation is None or not conversation.messages:
            self.stack.setCurrentWidget(self.home_page)
            return
        self.chat_title.setText(conversation.title)
        self._clear_messages()
        for message in conversation.messages:
            self._append_bubble(message)
        self.stack.setCurrentWidget(self.chat_page)
        self._scroll_to_bottom()

    def accept_submission(self) -> None:
        """Clear both editors only after storage and provider checks succeed."""
        self.home_composer.clear_text()
        self.chat_composer.clear_text()
        self.home_composer.clear_attachments()
        self.chat_composer.clear_attachments()

    def show_conversation(self, conversation: ChatConversation) -> None:
        """Display a conversation after appending its user turn."""
        self.set_conversation(conversation)
        self.stack.setCurrentWidget(self.chat_page)

    def set_busy(self, busy: bool, conversation_id: str | None = None) -> None:
        """Reflect only the request belonging to the currently displayed chat."""
        for composer in (self.home_composer, self.chat_composer):
            composer.set_busy(busy)
        if busy and conversation_id == self._conversation_id:
            self.status_label.setText("Orbit 正在思考…")
            self.retry_button.setVisible(False)
            self.configure_error_button.setVisible(False)
        elif busy:
            self.status_label.setText("另一段对话仍在生成；完成后可以继续提问。")
            self.retry_button.setVisible(False)
        elif not busy:
            self.status_label.clear()
            self.retry_button.setVisible(False)
            self.configure_error_button.setVisible(False)

    def show_error(self, message: str, conversation_id: str) -> None:
        """Show a safe retry state only if this request's conversation is open."""
        self.set_busy(False)
        if conversation_id == self._conversation_id:
            self.status_label.setText(message)
            self.retry_button.setVisible(True)
            self.configure_error_button.setVisible(True)

    def show_stopped(self, conversation_id: str) -> None:
        """Confirm cancellation without appending a stale model response."""
        self.set_busy(False)
        if conversation_id == self._conversation_id:
            self.status_label.setText("已停止生成。可以编辑消息后重新发送。")
            self.retry_button.setVisible(True)

    def clear_error(self) -> None:
        self.status_label.clear()
        self.retry_button.setVisible(False)

    def current_conversation_id(self) -> str | None:
        """Return the ID currently rendered in the message view."""
        return self._conversation_id

    def _clear_messages(self) -> None:
        while self.messages_layout.count():
            item = self.messages_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.messages_layout.addStretch(1)

    def _append_bubble(self, message: ChatMessage) -> None:
        stretch = self.messages_layout.takeAt(self.messages_layout.count() - 1)
        if stretch.widget():
            stretch.widget().deleteLater()
        self.messages_layout.addWidget(ChatMessageBubble(message))
        self.messages_layout.addStretch(1)

    def _scroll_to_bottom(self) -> None:
        QTimer.singleShot(0, lambda: self.message_scroll.verticalScrollBar().setValue(
            self.message_scroll.verticalScrollBar().maximum()
        ))

    def reapply_theme(self) -> None:
        """Refresh page-level styles after a global theme change."""
        self._apply_style()
        self.home_composer.refresh_model_icons()
        self.chat_composer.refresh_model_icons()
        for avatar in self.messages_container.findChildren(AvatarLabel):
            avatar.update()

    def _apply_style(self) -> None:
        self.setStyleSheet(resolve_qss("""
            QWidget#OrbitRoot { background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 @orb_grad_a@,stop:0.55 @orb_grad_b@,stop:1 @orb_grad_c@); }
            QScrollArea#OrbitHomeScroll, QScrollArea#OrbitHomeScroll > QWidget > QWidget { background:transparent; border:0; }
            QWidget#OrbitMessagesContainer { background:transparent; }
            QScrollArea#OrbitMessageScroll { background:transparent; border:0; }
            QLabel#OrbitHeroTitle { color:@hero_title@; font-size:26pt; font-weight:700; }
            QLabel#OrbitHeroSubtitle { color:@hero_subtitle@; font-size:14pt; padding-bottom:5px; }
            QLabel#OrbitEditorHint { color:@hint@; font-size:10pt; padding:2px 6px 4px 6px; }
            QLabel#OrbitFootnote, QLabel#OrbitStatus { color:@footnote@; }
            QLabel#OrbitSetupNotice { color:@setup_text@; background:@setup_bg@; border:1px solid @setup_border@;
                border-radius:10px; padding:8px 12px; }
            QLabel#OrbitChatTitle { color:@hero_title@; font-size:15pt; font-weight:650; padding:8px 4px; }
            QFrame#OrbitComposerCard { background:@card@; border:1px solid @composer_border@;
                border-radius:18px; }
            QPlainTextEdit#OrbitEditor { border:0; background:transparent; padding:7px 6px;
                font-size:11pt; color:@text@; }
            QComboBox#OrbitModelSelector { min-height:40px; max-height:40px; border:0;
                background:transparent; padding:0; outline:0; }
            QComboBox#OrbitModelSelector::drop-down { width:27px; border:0; }
            QComboBox#OrbitModelSelector::down-arrow { image:none; }
            QComboBox#OrbitModelSelector QAbstractItemView { background:@card@;
                border:1px solid @purple_border@; border-radius:10px; padding:5px;
                selection-background-color:@popup_sel_bg@; selection-color:@popup_sel_text@; }
            QPushButton#OrbitSendButton { background:@purple@; color:@text_on_primary@; border:0; border-radius:16px;
                padding:9px 18px; font-weight:600; }
            QPushButton#OrbitSendButton:hover { background:@send_hover@; }
            QPushButton#OrbitSendButton:disabled { background:@send_disabled@; color:@send_disabled_text@; }
            QPushButton#OrbitStopButton, QPushButton#OrbitRetryButton { background:@primary_soft@;
                color:@link@; border:1px solid @info_border@; border-radius:10px; padding:8px 14px; }
            QPushButton#OrbitLinkButton { color:@link@; border:0; background:transparent; }
            QFrame#OrbitAssistantBubble { background:@chat_bubble_a@; border:1px solid @chat_bubble_a_b@; border-radius:16px; }
            QFrame#OrbitUserBubble { background:@chat_bubble_u@; border:1px solid @chat_bubble_u_b@; border-radius:16px; }
            QLabel#OrbitMessageCaption { color:@msg_caption@; font-weight:600; }
            QLabel#OrbitMessageAttachments { color:@msg_att_text@; background:@msg_att_bg@;
                border-radius:8px; padding:5px 8px; }
            QTextBrowser#OrbitMessageContent { border:0; background:transparent; color:@msg_content@;
                padding:0; selection-background-color:@msg_selection@; }
            QPushButton#OrbitSuggestionCard { text-align:left; background:@card@;
                border:1px solid @border@; border-radius:15px; min-height:112px; }
            QPushButton#OrbitSuggestionCard:hover { background:@sug_hover@; border-color:@sug_hover_b@; }
            QPushButton#OrbitSuggestionCard:pressed { background:@sug_pressed@; }
            QLabel#OrbitSuggestionIcon { color:@sug_icon_color@; background:@sug_icon_bg@; border-radius:11px;
                padding:0; }
            QLabel#OrbitSuggestionTitle { color:@sug_title@; font-size:11pt; font-weight:650; }
            QLabel#OrbitSuggestionDescription { color:@sug_desc@; font-size:9pt; }
            QLabel#OrbitAttachmentSummary { color:@attach_btn@; background:@attach_bg@;
                border:1px solid @attach_border@; border-radius:9px; padding:6px 10px; }
            QPushButton#OrbitAttachmentClear { color:@muted@; background:transparent;
                border:0; padding:5px 8px; }
            QPushButton#OrbitAttachButton { color:@attach_btn@; background:@attach_btn_bg@;
                border:1px solid @attach_btn_border@; border-radius:11px; padding:8px 12px; }
            QPushButton#OrbitAttachButton:hover { background:@sug_pressed@; border-color:@attach_btn_hover_b@; }
            QScrollArea#OrbitMessageScroll { background:transparent; border:0; }
        """))


def _orbit_pixmap() -> QPixmap:
    """Draw a self-contained lavender orbit emblem without network assets."""
    svg = b'''<svg xmlns="http://www.w3.org/2000/svg" width="140" height="140" viewBox="0 0 140 140">
      <defs><radialGradient id="orb" cx="35%" cy="25%" r="75%">
        <stop offset="0" stop-color="#F8E9FF"/><stop offset=".42" stop-color="#C58CFF"/>
        <stop offset=".78" stop-color="#895CEB"/><stop offset="1" stop-color="#5C8CF5"/></radialGradient>
        <filter id="glow"><feGaussianBlur stdDeviation="7" result="blur"/>
          <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>
      <circle cx="70" cy="70" r="48" fill="#C5A7FF" opacity=".18" filter="url(#glow)"/>
      <ellipse cx="70" cy="70" rx="62" ry="24" transform="rotate(-18 70 70)" fill="none" stroke="#FFFFFF" stroke-width="2.5" opacity=".92"/>
      <circle cx="70" cy="70" r="37" fill="url(#orb)" stroke="#FFFFFF" stroke-opacity=".8" stroke-width="2"/>
      <path d="M51 81c4-17 13-25 29-29M54 92c14 6 32 2 43-10" fill="none" stroke="#F8F3FF" stroke-width="3" stroke-linecap="round" opacity=".82"/>
      <circle cx="45" cy="77" r="3" fill="#FFF"/><circle cx="105" cy="51" r="3" fill="#FFF"/>
    </svg>'''
    pixmap = QPixmap(140, 140)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    QSvgRenderer(QByteArray(svg)).render(painter)
    painter.end()
    return pixmap
