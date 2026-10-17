"""Persist operation records in the selected directory without external services."""

import json
import os
from pathlib import Path
from typing import Any

from filemind.models import OperationRecord


class OperationHistory:
    """Read and write JSON operation records under the selected directory."""

    def __init__(self, root: Path):
        self.root = root.expanduser().resolve(strict=True)
        self.history_dir = self.root / ".filemind" / "history"
        if (self.root / ".filemind").is_symlink() or self.history_dir.is_symlink():
            raise ValueError("FileMind 历史记录目录不能是符号链接")

    def _ensure_safe_directory(self) -> None:
        metadata_dir = self.root / ".filemind"
        if metadata_dir.is_symlink() or self.history_dir.is_symlink():
            raise ValueError("FileMind 历史记录目录不能是符号链接")
        metadata_dir.mkdir(exist_ok=True)
        self.history_dir.mkdir(exist_ok=True)
        if not self.history_dir.resolve().is_relative_to(self.root):
            raise ValueError("历史记录目录必须位于所选目录内")

    def save(self, record: OperationRecord) -> None:
        """Atomically save one operation record."""
        self._ensure_safe_directory()
        destination = self.history_dir / f"{record.operation_id}.json"
        temporary = destination.with_suffix(".tmp")
        payload = {
            "operation_id": record.operation_id,
            "created_at": record.created_at,
            "root": record.root,
            "operations": record.operations,
            "undone": record.undone,
        }
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, destination)

    def load(self, operation_id: str) -> OperationRecord:
        """Load one known operation record and reject malformed data."""
        if not operation_id.isalnum() or len(operation_id) != 32:
            raise ValueError("操作记录编号无效")
        path = self.history_dir / f"{operation_id}.json"
        payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("root") != str(self.root) or not isinstance(payload.get("operations"), list):
            raise ValueError("操作记录与当前目录不匹配或格式无效")
        return OperationRecord(
            operation_id,
            str(payload["created_at"]),
            str(payload["root"]),
            payload["operations"],
            bool(payload.get("undone", False)),
        )

    def list_records(self) -> list[OperationRecord]:
        """Return valid operation records newest first."""
        if not self.history_dir.exists():
            return []
        records: list[OperationRecord] = []
        for path in self.history_dir.glob("*.json"):
            try:
                records.append(self.load(path.stem))
            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
                continue
        return sorted(records, key=lambda record: record.created_at, reverse=True)
