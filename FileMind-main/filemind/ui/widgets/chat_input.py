"""Reusable Orbit composer with explicit model and request state."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import (QEvent, QEasingCurve, Property, QPoint, QPropertyAnimation,
                            QRect, QSize, Qt, Signal)
from PySide6.QtGui import (QColor, QEnterEvent, QFocusEvent, QFont, QPaintEvent, QPainter,
                           QPainterPath, QPen, QRegion, QTextCursor)
from PySide6.QtWidgets import (QApplication, QComboBox, QFrame, QHBoxLayout, QLabel,
                               QPlainTextEdit, QPushButton, QFileDialog, QSizePolicy,
                               QVBoxLayout, QWidget)

from filemind.ai.providers import PROVIDER_MODEL_SUGGESTIONS
from filemind.ui.widgets.card import Card
from filemind.ui.styles.icons import provider_icon
from filemind.ui.styles.theme import COLORS


class ChatTextEdit(QPlainTextEdit):
    """Send on Enter while preserving Shift+Enter for multiline messages."""

    submit = Signal()

    def keyPressEvent(self, event) -> None:
        if event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter} and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.submit.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class OrbitModelCombo(QComboBox):
    """Draw a compact chevron so the provider selector matches Orbit styling."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrame(False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setMouseTracking(True)
        self._provider_name = ""
        self._panel: OrbitModelPanel | None = None
        self._attached_window: QWidget | None = None
        self._arrow_angle = 0.0
        self._arrow_anim = QPropertyAnimation(self, b"arrow_angle", self)
        self._arrow_anim.setDuration(180)
        self._arrow_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _get_arrow_angle(self) -> float:
        return self._arrow_angle

    def _set_arrow_angle(self, value: float) -> None:
        self._arrow_angle = float(value)
        self.update()

    arrow_angle = Property(float, _get_arrow_angle, _set_arrow_angle)

    def _animate_arrow(self, pointing_up: bool) -> None:
        """Flip the chevron: 0deg points down (v), 180deg points up (^)."""
        self._arrow_anim.stop()
        self._arrow_anim.setStartValue(self._arrow_angle)
        self._arrow_anim.setEndValue(180.0 if pointing_up else 0.0)
        self._arrow_anim.start()

    def set_provider_name(self, name: str) -> None:
        """Remember the provider label for the custom picker's header."""
        self._provider_name = name

    def showPopup(self) -> None:
        """Open the branded picker above the capsule; clicking the capsule again
        (or anywhere outside) closes it."""
        if self.count() == 0 or not self.isEnabled():
            return
        if self._panel is not None:
            self._dismiss_panel()
            return
        items = [(self.itemIcon(i), self.itemText(i), self.itemData(i), i == self.currentIndex())
                 for i in range(self.count())]
        panel = OrbitModelPanel(self, self._provider_name, items)
        panel.selected.connect(self._on_panel_selected)
        panel.closed.connect(self._on_panel_closed)
        panel.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        # NB: the destroyed callback must identity-check the panel being torn
        # down. close() only schedules deleteLater(), so when the user clicks
        # the capsule fast, a new panel can be created before the old one's
        # destroyed signal fires. An unconditional `self._panel = None` would
        # then wipe the reference to the *new* panel, leaving it orphaned on
        # the desktop with no event filter to dismiss it.
        panel.destroyed.connect(
            lambda *_args, p=panel: setattr(self, "_panel", None) if self._panel is p else None
        )
        self._panel = panel
        panel.adjustSize()
        panel.move(self._compute_panel_origin(panel))
        panel.show()
        QApplication.instance().installEventFilter(self)
        # Track the top-level window so the panel follows the app on move/resize
        # and dismisses when the window loses focus — otherwise the frameless
        # tool window is left stranded on the desktop after the user drags the
        # main window.
        self._attached_window = self.window()
        self._animate_arrow(True)
        self.update()

    def _compute_panel_origin(self, panel: QWidget) -> QPoint:
        """Where the panel should sit, relative to the capsule, clamped to screen."""
        top_left = self.mapToGlobal(self.rect().topLeft())
        bottom_left = self.mapToGlobal(self.rect().bottomLeft())
        # Default: open upward, aligned with the capsule.
        origin = QPoint(top_left.x(), top_left.y() - panel.height() - 6)
        from PySide6.QtGui import QGuiApplication
        screen = QGuiApplication.screenAt(self.mapToGlobal(self.rect().center()))
        if screen is not None:
            available = screen.availableGeometry()
            if origin.y() < available.top():
                # Not enough room above; fall back to opening downward.
                origin.setY(bottom_left.y() + 6)
            if origin.x() + panel.width() > available.right():
                origin.setX(available.right() - panel.width() - 8)
            origin.setX(max(origin.x(), available.left() + 8))
        return origin

    def _reposition_panel(self) -> None:
        """Move the panel to track the capsule after the window moved/resized."""
        panel = self._panel
        if panel is None:
            return
        panel.move(self._compute_panel_origin(panel))

    @staticmethod
    def _global_rect(widget: QWidget) -> QRect:
        return QRect(widget.mapToGlobal(QPoint(0, 0)), widget.size())

    def eventFilter(self, obj, event) -> bool:
        """Dismiss the panel on outside clicks; a click on the capsule closes it
        without immediately reopening; a click on an item is left to the button.

        Also handles:
          * Escape key press  -> close the panel
          * top-level window move/resize -> reposition the panel so it tracks
            the capsule instead of being stranded on the desktop
          * top-level window deactivate  -> close the panel (user switched away)
        """
        etype = event.type()
        if etype == QEvent.Type.MouseButtonPress and self._panel is not None:
            position = event.globalPosition().toPoint()
            if self._global_rect(self._panel).contains(position):
                return False
            if self._global_rect(self).contains(position):
                self._dismiss_panel()
                return True
            self._dismiss_panel()
            return False
        if self._panel is not None and etype == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Escape:
                self._dismiss_panel()
                return True
        # Window-level tracking events arrive with obj == the top-level window
        # we captured in showPopup(); only act while the panel is alive.
        if self._panel is not None and obj is self._attached_window:
            if etype in (QEvent.Type.Move, QEvent.Type.Resize):
                self._reposition_panel()
                return False
            if etype == QEvent.Type.WindowDeactivate:
                # Ignore the deactivation caused by the panel (a Tool window)
                # itself grabbing focus; only close when the user truly leaves
                # the app.
                if QApplication.activeWindow() is not self._panel:
                    self._dismiss_panel()
                    return True
        return super().eventFilter(obj, event)

    def _dismiss_panel(self) -> None:
        QApplication.instance().removeEventFilter(self)
        self._attached_window = None
        panel = self._panel
        self._panel = None
        if panel is not None:
            panel.close()

    def _on_panel_closed(self) -> None:
        QApplication.instance().removeEventFilter(self)
        self._attached_window = None
        self._panel = None
        self._animate_arrow(False)
        self.update()

    def _on_panel_selected(self, index: int) -> None:
        """Apply a picked model; changing the index emits the existing signal."""
        if 0 <= index < self.count() and index != self.currentIndex():
            self.setCurrentIndex(index)
        if self._panel is not None:
            self._panel.close()

    def hidePopup(self) -> None:
        """Close our custom panel when the combo wants to dismiss the popup."""
        self._dismiss_panel()
        super().hidePopup()

    def enterEvent(self, event: QEnterEvent) -> None:
        super().enterEvent(event)
        self.update()

    def leaveEvent(self, event: QEvent) -> None:
        super().leaveEvent(event)
        self.update()

    def focusInEvent(self, event: QFocusEvent) -> None:
        super().focusInEvent(event)
        self.update()

    def focusOutEvent(self, event: QFocusEvent) -> None:
        super().focusOutEvent(event)
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        disabled = not self.isEnabled()
        stroke = COLORS["purple_border"]
        if self.underMouse():
            stroke = "#CFC3FB"
        if self.hasFocus():
            stroke = COLORS["purple"]
        fill = QColor(COLORS["purple_soft"] if not disabled else "#F2F3F6")
        painter.setBrush(fill)
        painter.setPen(QPen(QColor(stroke), 1.2))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 13, 13)
        icon_rect = self.rect()
        icon_rect.setX(10)
        icon_rect.setY((self.height() - 24) // 2)
        icon_rect.setWidth(24)
        icon_rect.setHeight(24)
        if self.currentIndex() >= 0:
            icon = self.itemIcon(self.currentIndex())
            if not icon.isNull():
                # 图标已为透明背景的品牌图形，直接绘制即可融入胶囊，
                # 不做方形底框、也不做圆形裁剪，保证与参考图一致。
                icon.paint(painter, icon_rect)
        text_left = icon_rect.right() + 10
        text_right = self.width() - 35
        text = self.fontMetrics().elidedText(
            self.currentText(), Qt.TextElideMode.ElideRight, max(0, text_right - text_left)
        )
        painter.setPen(QColor(COLORS["muted"] if disabled else COLORS["text"]))
        metrics = self.fontMetrics()
        baseline = (self.height() - metrics.height()) // 2 + metrics.ascent()
        painter.drawText(text_left, baseline, text)
        center_x = self.width() - 17
        center_y = self.height() / 2
        # The chevron is drawn pointing down (v) then rotated by _arrow_angle;
        # opening the panel flips it to (^) with a QPropertyAnimation.
        painter.save()
        painter.translate(center_x, center_y)
        painter.rotate(self._arrow_angle)
        chevron = QPainterPath()
        chevron.moveTo(-4, -2)
        chevron.lineTo(0, 2)
        chevron.lineTo(4, -2)
        arrow_color = COLORS["purple"] if self._arrow_angle > 0.5 else COLORS["muted"]
        painter.setPen(QPen(QColor(arrow_color), 1.6))
        painter.drawPath(chevron)
        painter.restore()


class OrbitModelItemButton(QPushButton):
    """A rounded, hoverable model row: brand icon, name, and a right-side check."""

    def __init__(self, icon, name: str, selected: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._item_icon = icon
        self._item_name = name
        self._item_selected = selected
        self.setFixedHeight(38)
        self.setMinimumWidth(214)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def enterEvent(self, event: QEnterEvent) -> None:
        super().enterEvent(event)
        self.update()

    def leaveEvent(self, event: QEvent) -> None:
        super().leaveEvent(event)
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        row = self.rect().adjusted(1, 1, -1, -1)
        if self._item_selected:
            background, foreground = COLORS["popup_sel_bg"], COLORS["popup_sel_text"]
        elif self.underMouse():
            background, foreground = COLORS["primary_soft"], COLORS["text"]
        else:
            background, foreground = None, COLORS["text"]
        painter.setPen(Qt.PenStyle.NoPen)
        if background is not None:
            painter.setBrush(QColor(background))
            painter.drawRoundedRect(row, 9, 9)
        icon_rect = QRect(12, (self.height() - 22) // 2, 22, 22)
        if self._item_icon is not None and not self._item_icon.isNull():
            self._item_icon.paint(painter, icon_rect)
        font = QFont(self.font())
        font.setPixelSize(13)
        if self._item_selected:
            font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.setPen(QColor(foreground))
        text_x = icon_rect.right() + 10
        text_width = self.width() - text_x - 34
        name = painter.fontMetrics().elidedText(
            self._item_name, Qt.TextElideMode.ElideRight, max(0, text_width)
        )
        painter.drawText(QRect(text_x, 0, text_width, self.height()),
                         Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, name)
        if self._item_selected:
            check_x = self.width() - 20
            check_y = self.height() / 2
            check = QPainterPath()
            check.moveTo(check_x - 5, check_y)
            check.lineTo(check_x - 1.5, check_y + 3.5)
            check.lineTo(check_x + 5, check_y - 4)
            painter.setPen(QPen(QColor(COLORS["purple"]), 1.8))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(check)


class OrbitModelPanel(QFrame):
    """A branded, borderless model picker rendered above the composer.

    The window is translucent and the rounded card (14px, matching app cards) is
    painted manually so there is no native rectangular frame or drop shadow.
    """

    selected = Signal(int)
    closed = Signal()

    def __init__(self, parent: QWidget | None, provider_name: str, items) -> None:
        flags = (Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                 | Qt.WindowType.NoDropShadowWindowHint)
        super().__init__(parent, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setObjectName("OrbitModelPanel")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 9, 10, 10)
        outer.setSpacing(5)
        title = QLabel(provider_name or "选择模型")
        title.setObjectName("OrbitModelPanelHeader")
        title.setContentsMargins(6, 1, 6, 1)
        outer.addWidget(title)
        separator = QFrame()
        separator.setObjectName("OrbitModelPanelSep")
        separator.setFixedHeight(1)
        outer.addWidget(separator)
        outer.addSpacing(1)
        for index, (icon, text, _data, selected) in enumerate(items):
            button = OrbitModelItemButton(icon, text, selected)
            button.clicked.connect(lambda checked=False, idx=index: self.selected.emit(idx))
            outer.addWidget(button)
        self.setMinimumWidth(236)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_round_mask()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._apply_round_mask()

    def _apply_round_mask(self) -> None:
        """Clip the rounded corners so no native (black) corner is ever drawn."""
        radius = 14.0
        path = QPainterPath()
        path.addRoundedRect(self.rect().adjusted(1, 1, -1, -1), radius, radius)
        region = QRegion(path.toFillPolygon().toPolygon())
        self.setMask(region)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        card = self.rect().adjusted(1, 1, -1, -1)
        painter.setBrush(QColor(COLORS["card"]))
        painter.setPen(QPen(QColor(COLORS["purple_border"]), 1.0))
        painter.drawRoundedRect(card, 14, 14)

    def closeEvent(self, event) -> None:
        self.closed.emit()
        super().closeEvent(event)


def _model_display_name(model_id: str) -> str:
    """User-facing label; the combo's item data keeps the API model id."""
    if model_id == "deepseek-flash":
        return "V4.1 Flash"
    return model_id


class ChatInput(QWidget):
    """Message editor, selected configured model, and send/stop controls."""

    send_requested = Signal(str, object)
    stop_requested = Signal()
    configure_requested = Signal()
    model_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._busy = False
        self._configured = False
        self._syncing = False
        self._provider_id: str | None = None
        self._last_model_args: tuple | None = None
        self._attachments: tuple[Path, ...] = ()
        card = Card(padding=15)
        card.setObjectName("OrbitComposerCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(card)
        # 输入引导提示放在输入框上方作为独立标签，避免中文输入法输入拼音时
        # 与输入框内文字重叠（QPlainTextEdit 的 placeholder 在 document 为空时
        # 不会因 IME 拼音自动隐藏）。
        self.editor_hint = QLabel("今天有什么可以帮你？（Enter 发送，Shift+Enter 换行）")
        self.editor_hint.setObjectName("OrbitEditorHint")
        self.editor_hint.setWordWrap(False)
        card.layout.addWidget(self.editor_hint)
        self.editor = ChatTextEdit()
        self.editor.setObjectName("OrbitEditor")
        self.editor.setMinimumHeight(64)
        self.editor.setMaximumHeight(132)
        self.editor.submit.connect(self._submit)
        self.editor.textChanged.connect(self._update_send_state)
        card.layout.addWidget(self.editor)

        attachment_row = QHBoxLayout()
        attachment_row.setContentsMargins(4, 0, 4, 0)
        self.attachment_label = QLabel()
        self.attachment_label.setObjectName("OrbitAttachmentSummary")
        self.attachment_label.setVisible(False)
        attachment_row.addWidget(self.attachment_label, 1)
        self.clear_attachments_button = QPushButton("清除")
        self.clear_attachments_button.setObjectName("OrbitAttachmentClear")
        self.clear_attachments_button.setVisible(False)
        self.clear_attachments_button.clicked.connect(self.clear_attachments)
        attachment_row.addWidget(self.clear_attachments_button)
        card.layout.addLayout(attachment_row)

        footer = QHBoxLayout()
        self.attach_button = QPushButton("＋ 添加文件")
        self.attach_button.setObjectName("OrbitAttachButton")
        self.attach_button.setToolTip(
            "选择图片或 UTF-8 文本/代码文件。图片目前需 DeepSeek V4.1 Flash；单文件最大 4 MB。"
        )
        self.attach_button.clicked.connect(self._pick_attachments)
        footer.addWidget(self.attach_button)
        self.privacy_label = QLabel("消息与近期上下文发送至当前服务商；附件仅按本次选择发送。")
        self.privacy_label.setObjectName("Muted")
        self.privacy_label.setWordWrap(True)
        self.privacy_label.setStyleSheet("font-size:9pt;")
        footer.addStretch(1)
        self.model_combo = OrbitModelCombo()
        self.model_combo.setObjectName("OrbitModelSelector")
        self.model_combo.setMinimumWidth(156)
        self.model_combo.setMaximumWidth(196)
        self.model_combo.setMinimumHeight(40)
        self.model_combo.setIconSize(QSize(24, 24))
        self.model_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.model_combo.setMinimumContentsLength(9)
        self.model_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        footer.addWidget(self.model_combo)
        self.configure_button = QPushButton("配置模型")
        self.configure_button.setObjectName("OrbitLinkButton")
        self.configure_button.clicked.connect(self.configure_requested.emit)
        footer.addWidget(self.configure_button)
        self.send_button = QPushButton("发送")
        self.send_button.setObjectName("OrbitSendButton")
        self.send_button.setFixedHeight(40)
        self.send_button.clicked.connect(self._submit)
        footer.addWidget(self.send_button)
        self.stop_button = QPushButton("停止")
        self.stop_button.setObjectName("OrbitStopButton")
        self.stop_button.setFixedHeight(40)
        self.stop_button.setVisible(False)
        self.stop_button.clicked.connect(self.stop_requested.emit)
        footer.addWidget(self.stop_button)
        card.layout.addLayout(footer)
        card.layout.addWidget(self.privacy_label)
        self.model_combo.currentIndexChanged.connect(self._model_changed)
        self.set_model(None, None, None)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self.setMaximumHeight(236)
        self._update_send_state()

    def set_model(self, provider_id: str | None, provider_name: str | None, model_name: str | None,
                  has_api_key: bool = False) -> None:
        """List the provider's default model options plus the active model, and select the active one."""
        self._last_model_args = (provider_id, provider_name, model_name, has_api_key)
        self._provider_id = provider_id or "custom"
        self._configured = bool(provider_name and model_name)
        self.model_combo.set_provider_name(provider_name or provider_id or "custom")
        self._syncing = True
        self.model_combo.clear()
        try:
            if not self._configured:
                self.model_combo.addItem(provider_icon(self._provider_id), "尚未配置模型")
                self.model_combo.setToolTip("尚未配置模型")
                self.model_combo.setEnabled(False)
                return
            suggestions = list(PROVIDER_MODEL_SUGGESTIONS.get(provider_id or "", ()))
            options = list(dict.fromkeys([model_name, *suggestions]))
            for option in options:
                self.model_combo.addItem(provider_icon(provider_id or "custom"), _model_display_name(option), option)
            active_index = self.model_combo.findData(model_name)
            if active_index >= 0:
                self.model_combo.setCurrentIndex(active_index)
            self.model_combo.setToolTip(f"{provider_name} · {model_name}")
            self.model_combo.setEnabled(True)
        finally:
            self._syncing = False
        self.configure_button.setVisible(not has_api_key)

    def refresh_model_icons(self) -> None:
        """Re-load provider brand icons after a light/dark theme switch."""
        if self._configured and self._last_model_args is not None:
            self.set_model(*self._last_model_args)

    def sync_model(self, model_id: str) -> None:
        """Reflect a model chosen in the sibling composer without re-emitting a change."""
        index = self.model_combo.findData(model_id)
        if index >= 0 and index != self.model_combo.currentIndex():
            self._syncing = True
            try:
                self.model_combo.setCurrentIndex(index)
            finally:
                self._syncing = False

    def _model_changed(self, index: int) -> None:
        if self._syncing or not self._configured:
            return
        model_id = self.model_combo.itemData(index)
        if isinstance(model_id, str) and model_id:
            self.model_selected.emit(model_id)

    def set_text(self, text: str) -> None:
        """Fill a suggested prompt without submitting it."""
        self.editor.setPlainText(text)
        self.editor.setFocus()
        self.editor.moveCursor(QTextCursor.MoveOperation.End)

    def clear_text(self) -> None:
        """Clear the composer after a message has been accepted."""
        self.editor.clear()

    @property
    def selected_attachments(self) -> tuple[Path, ...]:
        """Return explicitly selected files without reading their contents."""
        return self._attachments

    def clear_attachments(self) -> None:
        """Forget selected files and refresh the compact attachment summary."""
        self._attachments = ()
        self._update_attachment_display()

    def _pick_attachments(self) -> None:
        paths, _selected_filter = QFileDialog.getOpenFileNames(
            self, "添加图片或文本文件", "",
            "支持的附件 (*.png *.jpg *.jpeg *.gif *.webp *.txt *.md *.csv *.json *.py *.java *.c *.h *.cpp *.hpp *.js *.ts *.html *.css *.sql *.log *.xml *.yaml *.yml)",
        )
        if not paths:
            return
        try:
            self.set_attachments((*self._attachments, *(Path(path) for path in paths)))
        except ValueError as error:
            self.attachment_label.setText(str(error))
            self.attachment_label.setToolTip(str(error))
            self.attachment_label.setVisible(True)
            self.clear_attachments_button.setVisible(bool(self._attachments))
            return

    def set_attachments(self, paths: tuple[Path, ...]) -> None:
        """Set selected attachments after checking types, count, and current files."""
        self._attachments = _validate_selection(paths)
        self._update_attachment_display()

    def _update_attachment_display(self) -> None:
        names = "、".join(path.name for path in self._attachments)
        self.attachment_label.setText(f"已添加 {len(self._attachments)} 个文件：{names}" if names else "")
        self.attachment_label.setToolTip(names)
        self.attachment_label.setVisible(bool(names))
        self.clear_attachments_button.setVisible(bool(names))
        self._update_send_state()

    def set_busy(self, busy: bool) -> None:
        """Prevent duplicate sends while leaving stop available."""
        self._busy = busy
        self.editor.setEnabled(not busy)
        self.attach_button.setEnabled(not busy)
        self.clear_attachments_button.setEnabled(not busy)
        self.model_combo.setEnabled(self._configured and not busy)
        self.send_button.setVisible(not busy)
        self.send_button.setEnabled(not busy and bool(self.editor.toPlainText().strip()))
        self.stop_button.setVisible(busy)
        self.stop_button.setEnabled(busy)
        self._update_send_state()

    def _update_send_state(self) -> None:
        self.send_button.setEnabled(not self._busy and bool(self.editor.toPlainText().strip()))

    def _submit(self) -> None:
        if not self._busy and self.editor.toPlainText().strip():
            self.send_requested.emit(self.editor.toPlainText().strip(), self._attachments)


def _validate_selection(paths: tuple[Path, ...]) -> tuple[Path, ...]:
    allowed = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".txt", ".md", ".csv", ".json",
               ".py", ".java", ".c", ".h", ".cpp", ".hpp", ".js", ".ts", ".html", ".css",
               ".sql", ".log", ".xml", ".yaml", ".yml"}
    unique = tuple(dict.fromkeys(paths))
    if len(unique) > 5:
        raise ValueError("一次最多添加 5 个附件。")
    for path in unique:
        if path.suffix.lower() not in allowed:
            raise ValueError(f"暂不支持 {path.suffix or '无扩展名'} 文件类型。")
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"无法添加非普通文件：{path.name}")
        try:
            file_size = path.stat().st_size
        except OSError as error:
            raise ValueError(f"无法访问附件：{path.name}") from error
        if file_size > 4 * 1024 * 1024:
            raise ValueError(f"{path.name} 超过单文件 4 MB 限制。")
    return unique
