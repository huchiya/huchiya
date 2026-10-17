"""Qt worker primitives for file scanning and operations."""

from __future__ import annotations

from threading import Event
from typing import Callable

from PySide6.QtCore import QObject, QRunnable, Signal, Slot


Task = Callable[[Callable[[int, int], None], Event], object]


class WorkerSignals(QObject):
    """Signals emitted by a worker and delivered to the GUI thread."""

    progress = Signal(int, int)
    completed = Signal(object)
    failed = Signal(str)
    cancelled = Signal(str)


class TaskWorker(QRunnable):
    """Run a synchronous service call in Qt's shared thread pool."""

    def __init__(self, task: Task):
        super().__init__()
        self.task = task
        self.signals = WorkerSignals()
        self.cancel_event = Event()

    def cancel(self) -> None:
        """Ask a cooperative task to stop at its next safe boundary."""
        self.cancel_event.set()

    @Slot()
    def run(self) -> None:
        try:
            result = self.task(self.signals.progress.emit, self.cancel_event)
            self.signals.completed.emit(result)
        except InterruptedError as error:
            self.signals.cancelled.emit(str(error))
        except Exception as error:
            self.signals.failed.emit(f"{type(error).__name__}: {error}")
