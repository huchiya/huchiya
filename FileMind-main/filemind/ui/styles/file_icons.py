"""Cached extension icons without opening files or invoking thumbnail handlers."""

import ctypes
import os
from functools import lru_cache
from pathlib import Path

from PySide6.QtGui import QIcon, QImage, QPixmap

from filemind.ui.styles.icons import file_type_icon


@lru_cache(maxsize=128)
def associated_file_icon(suffix: str) -> QIcon:
    """Use Windows associations by extension only, with an offline fallback."""
    if os.name == "nt":
        try:
            icon = _windows_icon(suffix)
            if not icon.isNull():
                return icon
        except (OSError, AttributeError, ValueError):
            pass
    return file_type_icon(Path("file" + suffix))


def _windows_icon(suffix: str) -> QIcon:
    from ctypes import wintypes

    class ShellFileInfo(ctypes.Structure):
        _fields_ = [("icon", wintypes.HANDLE), ("index", ctypes.c_int),
                    ("attributes", wintypes.DWORD), ("name", wintypes.WCHAR * 260),
                    ("type", wintypes.WCHAR * 80)]

    shell = ctypes.WinDLL("shell32", use_last_error=True)
    user = ctypes.WinDLL("user32", use_last_error=True)
    query = shell.SHGetFileInfoW
    query.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(ShellFileInfo),
                      ctypes.c_uint, ctypes.c_uint]
    query.restype = ctypes.c_size_t
    user.DestroyIcon.argtypes = [wintypes.HANDLE]
    info = ShellFileInfo()
    if not query("file" + suffix, 0x80, ctypes.byref(info), ctypes.sizeof(info), 0x100 | 0x10 | 0x1):
        return QIcon()
    try:
        return QIcon(QPixmap.fromImage(QImage.fromHICON(info.icon)))
    finally:
        if info.icon:
            user.DestroyIcon(info.icon)
