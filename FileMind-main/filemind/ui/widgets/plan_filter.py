"""Shared plan filtering for inline workspaces and confirmation dialogs."""

from pathlib import Path

from PySide6.QtCore import QModelIndex, QObject, QSortFilterProxyModel


class PlanFilterModel(QSortFilterProxyModel):
    """Filter by path components, never by ambiguous path substrings."""

    def __init__(self, parent: QObject) -> None:
        super().__init__(parent)
        self.target: Path | None = None
        self.is_file = False
        self.query = ""

    def filterAcceptsRow(self, source_row: int, parent: QModelIndex) -> bool:
        model = self.sourceModel()
        operation = model.operations[source_row]
        if self.target is not None:
            if self.is_file and operation.target != self.target:
                return False
            if not self.is_file and not operation.target.is_relative_to(self.target):
                return False
        searchable = f"{operation.original_name} {operation.target} {operation.classification.reason}"
        return self.query.casefold() in searchable.casefold()

    def set_target(self, target: Path | None, is_file: bool) -> None:
        """Select exactly one destination file or a whole destination folder."""
        self.beginFilterChange()
        self.target, self.is_file = target, is_file
        self.endFilterChange(QSortFilterProxyModel.Direction.Rows)

    def set_query(self, query: str) -> None:
        """Search names and reasons inside the selected subtree."""
        self.beginFilterChange()
        self.query = query.strip()
        self.endFilterChange(QSortFilterProxyModel.Direction.Rows)
