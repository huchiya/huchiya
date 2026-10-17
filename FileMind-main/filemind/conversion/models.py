"""Stable conversion interfaces shared by UI and local adapters."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ConversionTarget:
    """An actually implemented target, with a truthful capability description."""

    key: str
    title: str
    extension: str
    note: str


@dataclass(frozen=True)
class ConversionInput:
    """An explicitly selected file and its inspected local capabilities."""

    path: Path
    kind: str
    description: str
    targets: tuple[ConversionTarget, ...]
    fingerprint: tuple[int, int, int, int]


@dataclass(frozen=True)
class ConversionResult:
    """A published output, only created after successful local conversion."""

    output: Path
    bytes_written: int
    target_title: str
