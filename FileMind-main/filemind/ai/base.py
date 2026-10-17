"""Provider-independent AI service contract."""

from threading import Event
from typing import Callable, Protocol

from filemind.ai.schemas import AIFileMetadata, AIOrganizationResult


ProgressCallback = Callable[[int, int], None]


class AIClient(Protocol):
    """Operations the UI may request from any supported model adapter."""

    def test_connection(self) -> str: ...

    def organize_files(
        self,
        files: list[AIFileMetadata],
        user_rule: str,
        rename_enabled: bool,
        on_progress: ProgressCallback | None = None,
        cancel_event: Event | None = None,
    ) -> AIOrganizationResult: ...
