"""Regression guards for the review-tool isolation fix and the shared suffix rule."""

import json
import sys
from pathlib import Path

import pytest

import tools.review_ui as review
from filemind.ai.response import parse_file_suggestions
from filemind.ai.schemas import file_metadata
from filemind.core.classifier import classify_file
from filemind.core.plan_editor import PlanEditor
from filemind.core.planner import build_plan, name_suffixes
from filemind.core.scanner import scan_files
from filemind.models import FileInfo


class _FakeWidget:
    def resize(self, *_args) -> None: ...
    def show(self) -> None: ...
    def close(self) -> None: ...
    def deleteLater(self) -> None: ...
    def grab(self):  # pragma: no cover - only used when --snapshot is passed
        return type("_Pixmap", (), {"save": lambda self, _path: True})()


class _FakeApp:
    def exec(self) -> int:
        return 0

    def sendPostedEvents(self, *_args, **_kwargs) -> None: ...


def _run_review_tool(monkeypatch, argv: list[str], live_calls: list[bool]) -> int:
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setattr("filemind.ui.startup.run_application",
                        lambda: live_calls.append(True) or 0)
    monkeypatch.setattr(review, "QApplication", lambda *_a, **_k: _FakeApp())
    monkeypatch.setattr(review, "apply_theme", lambda *_a, **_k: None)
    monkeypatch.setattr(review, "build_review", lambda *_a, **_k: (_FakeWidget(), None))
    return review.main()


def test_review_tool_defaults_to_isolated_data(monkeypatch) -> None:
    live_calls: list[bool] = []
    assert _run_review_tool(monkeypatch, ["review_ui.py", "--page", "setup"], live_calls) == 0
    assert live_calls == [], "默认不应启动真实应用"


def test_review_tool_live_flag_launches_the_real_app(monkeypatch) -> None:
    live_calls: list[bool] = []
    assert _run_review_tool(monkeypatch, ["review_ui.py", "--live"], live_calls) == 0
    assert live_calls == [True]


def test_name_suffixes_lowercases_the_full_extension_chain() -> None:
    assert name_suffixes("A.TAR.GZ") == (".tar", ".gz")
    assert name_suffixes("notes") == ()
    assert name_suffixes("归档.tar.gz") == (".tar", ".gz")


def test_manual_editor_requires_the_full_extension_chain(tmp_path: Path) -> None:
    (tmp_path / "archive.tar.gz").write_text("x", encoding="utf-8")
    editor = PlanEditor(build_plan(tmp_path, scan_files(tmp_path), classify_file))
    source = editor.rows[0].source

    with pytest.raises(ValueError):
        editor.set_new_name(source, "archive.gz")

    editor.set_new_name(source, "archive-backup.tar.gz")
    operation = next(item for item in editor.build().operations if item.source == source)
    assert operation.new_name == "archive-backup.tar.gz"


def test_ai_and_manual_paths_agree_on_multi_part_extensions() -> None:
    file_info = FileInfo(Path("archive.tar.gz"), 10, 1)
    file_id = file_metadata(file_info).file_id
    payload = json.dumps({"suggestions": [{
        "file_id": file_id, "category": "压缩包", "target_subdirectory": "",
        "new_name": "archive.gz", "reason": "分类",
    }]})

    suggestions, failures = parse_file_suggestions(payload, {file_id: file_info}, True)
    assert suggestions == {}
    assert file_id in failures
