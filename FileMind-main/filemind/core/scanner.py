"""Scan only the top-level files in a directory chosen by the user."""

from pathlib import Path
from threading import Event
from typing import Callable

from filemind.models import FileInfo


def scan_files(
    folder: Path,
    on_progress: Callable[[int, int], None] | None = None,
    cancel_event: Event | None = None,
) -> list[FileInfo]:
    """Return regular files directly inside ``folder``; never recurse."""
    root = folder.expanduser().resolve(strict=True)
    if not root.is_dir():
        raise NotADirectoryError(f"所选路径不是文件夹：{root}")

    files: list[FileInfo] = []
    entries = sorted(root.iterdir(), key=lambda item: item.name.casefold())
    total = len(entries)
    for index, entry in enumerate(entries, start=1):
        if cancel_event and cancel_event.is_set():
            raise InterruptedError("扫描已取消")
        if entry.name == ".filemind" or entry.is_symlink() or not entry.is_file():
            if on_progress:
                on_progress(index, total)
            continue
        stat = entry.stat(follow_symlinks=False)
        files.append(FileInfo(entry, stat.st_size, stat.st_mtime_ns))
        if on_progress:
            on_progress(index, total)
    return files
