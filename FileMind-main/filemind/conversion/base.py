"""Shared adapter contracts, bounded archive access and local cancellation."""

from pathlib import Path
from threading import Event
from typing import Callable
from zipfile import ZipFile


Progress = Callable[[int, int], None]


class ConversionError(RuntimeError):
    """Safe-to-display conversion failure without sensitive request contents."""


def check_cancel(cancel: Event) -> None:
    """Stop before publishing output; adapters also check between units of work."""
    if cancel.is_set():
        raise InterruptedError("转换已取消，未发布输出文件。")


def check_archive(path: Path) -> None:
    """Bound local Office/EPUB expansion without extracting to disk."""
    with ZipFile(path) as archive:
        entries = archive.infolist()
        if len(entries) > 3000 or sum(item.file_size for item in entries) > 64 * 1024 * 1024:
            raise ConversionError("压缩文档展开后过大，超过本机转换限制。")
        if any(item.file_size > 16 * 1024 * 1024 for item in entries):
            raise ConversionError("文档内部单项超过 16 MB，暂不读取。")
