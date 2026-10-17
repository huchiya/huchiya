"""Local authentication state and lifecycle tests with isolated storage."""

import os
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication, QDialog

from filemind.storage.local_lock import LocalLockStore
from filemind.ui.dialogs.local_lock import LocalLockDialog
from filemind.ui.startup import authenticate
from filemind.ui.startup import run_application


@pytest.fixture(scope="session")
def application() -> QApplication:
    return QApplication.instance() or QApplication([])


def wait_for_dialog(dialog: LocalLockDialog) -> None:
    loop = QEventLoop()
    dialog._worker.signals.completed.connect(loop.quit)
    dialog._worker.signals.failed.connect(loop.quit)
    QTimer.singleShot(8000, loop.quit)
    loop.exec()
    QApplication.processEvents()
    assert dialog._worker is None


def test_first_run_recovery_acknowledgement_and_background_work(application, tmp_path: Path) -> None:
    dialog = LocalLockDialog(LocalLockStore(tmp_path / "auth.json"))
    dialog.show()
    dialog.password_edit.setText("first password")
    dialog.confirm_edit.setText("first password")
    timer_events: list[bool] = []
    QTimer.singleShot(5, lambda: timer_events.append(True))
    dialog._submit()
    assert not dialog.primary_button.isEnabled()
    wait_for_dialog(dialog)
    assert timer_events
    assert dialog.recovery_panel.isVisible()
    assert len(dialog.recovery_display.text()) == 32
    assert not dialog.primary_button.isEnabled()
    dialog.saved_checkbox.setChecked(True)
    dialog._submit()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert not dialog.recovery_display.text()
    dialog.close()


def test_bad_password_retry_and_no_duplicate_request(application, tmp_path: Path) -> None:
    store = LocalLockStore(tmp_path / "auth.json")
    store.initialize("real password")
    dialog = LocalLockDialog(store)
    dialog.password_edit.setText("wrong password")
    dialog._submit()
    worker = dialog._worker
    dialog._submit()
    assert dialog._worker is worker
    wait_for_dialog(dialog)
    assert "密码不正确" in dialog.status_label.text()
    assert dialog.result() != QDialog.DialogCode.Accepted
    dialog.password_edit.setText("real password")
    dialog._submit()
    wait_for_dialog(dialog)
    assert dialog.result() == QDialog.DialogCode.Accepted
    dialog.close()


def test_password_mismatch_does_not_write_and_cancel_does_not_launch_main(application, tmp_path: Path) -> None:
    store = LocalLockStore(tmp_path / "auth.json")
    dialog = LocalLockDialog(store)
    dialog.password_edit.setText("first password")
    dialog.confirm_edit.setText("another password")
    dialog._submit()
    assert dialog._worker is None
    assert not store.path.exists()
    dialog.reject()
    with patch("filemind.ui.startup.LocalLockDialog") as mocked:
        mocked.return_value.exec.return_value = QDialog.DialogCode.Rejected
        assert not authenticate(store)


def test_window_close_waits_for_password_write(application, tmp_path: Path) -> None:
    dialog = LocalLockDialog(LocalLockStore(tmp_path / "auth.json"))
    dialog.password_edit.setText("first password")
    dialog.confirm_edit.setText("first password")
    dialog._submit()
    dialog.reject()
    assert dialog._close_pending
    wait_for_dialog(dialog)
    assert dialog.result() == QDialog.DialogCode.Rejected
    assert dialog.store.is_configured()


def test_cancelled_startup_does_not_construct_pages_or_load_settings(application) -> None:
    with patch("filemind.ui.startup.QApplication"), patch("filemind.ui.startup.apply_theme"), \
            patch("filemind.ui.startup.LocalLockStore"), \
            patch("filemind.ui.startup.authenticate", return_value=False), \
            patch("filemind.ui.startup.MainWindow") as main_window:
        assert run_application() == 0
        main_window.assert_not_called()
