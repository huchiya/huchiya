"""Local conversion tests use only generated images, text and archives."""

import json
import zipfile
from pathlib import Path
from threading import Event
from unittest.mock import patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QImageReader

from filemind.conversion.service import ConversionError, convert_file, inspect_input


def convert(source: Path, target: str, output: Path):
    return convert_file(inspect_input(source), target, output, lambda *_: None, Event())


def test_image_encoding_and_pdf_are_real(tmp_path: Path) -> None:
    source = tmp_path / "透明图片.png"
    image = QImage(30, 20, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    assert image.save(str(source), "PNG")
    item = inspect_input(source)
    assert {"png", "jpeg", "pdf", "zip"} <= {target.key for target in item.targets}
    output = tmp_path / "输出.jpg"
    result = convert(source, "jpeg", output)
    assert bytes(QImageReader(str(output)).format()) == b"jpeg"
    assert QImage(str(output)).pixelColor(0, 0).red() > 245
    assert result.bytes_written == output.stat().st_size
    pdf = tmp_path / "输出.pdf"
    convert(source, "pdf", pdf)
    assert pdf.read_bytes().startswith(b"%PDF-")
    assert source.exists()


def test_csv_json_and_unicode_encoding_round_trip(tmp_path: Path) -> None:
    source = tmp_path / "中文.csv"
    source.write_text('课程,备注\n数据结构,"链表,树"\n', encoding="utf-8-sig")
    json_path = tmp_path / "记录.json"
    convert(source, "json", json_path)
    assert json.loads(json_path.read_text(encoding="utf-8")) == [{"课程": "数据结构", "备注": "链表,树"}]
    csv_path = tmp_path / "还原.csv"
    convert(json_path, "csv", csv_path)
    assert '"链表,树"' in csv_path.read_text(encoding="utf-8")
    utf16 = tmp_path / "utf16.txt"
    convert(source, "utf16", utf16)
    utf8 = tmp_path / "utf8.txt"
    convert(utf16, "utf8", utf8)
    assert utf8.read_text(encoding="utf-8") == source.read_text(encoding="utf-8-sig")


def test_unknown_format_only_offers_real_single_file_zip(tmp_path: Path) -> None:
    source = tmp_path / "课程.docx"
    source.write_bytes(b"generated opaque file")
    assert [target.key for target in inspect_input(source).targets] == ["zip"]
    output = tmp_path / "课程.zip"
    convert(source, "zip", output)
    with zipfile.ZipFile(output) as archive:
        assert archive.namelist() == [source.name]
        assert archive.read(source.name) == source.read_bytes()


@pytest.mark.parametrize("contents,target,message", [
    ('[{"课程":{"章节":1}}]', "csv", "嵌套"),
    ('{"课程":1}', "csv", "扁平对象"),
    ('invalid JSON', "json", "转换失败"),
])
def test_invalid_json_or_lossy_structure_rejected(tmp_path: Path, contents: str, target: str, message: str) -> None:
    source = tmp_path / "input.json"
    source.write_text(contents, encoding="utf-8")
    output = tmp_path / f"output.{target}"
    with pytest.raises(ConversionError, match=message):
        convert(source, target, output)
    assert not output.exists()
    assert not list(tmp_path.glob(".filemind-convert-*"))


@pytest.mark.parametrize("contents", ["字段,字段\n1,2", "字段,备注\n1", ",备注\n1,2"])
def test_ambiguous_csv_rejected(tmp_path: Path, contents: str) -> None:
    source = tmp_path / "input.csv"
    source.write_text(contents, encoding="utf-8")
    with pytest.raises(ConversionError, match="CSV"):
        convert(source, "json", tmp_path / "output.json")


def test_cancel_and_existing_output_never_modify_source_or_target(tmp_path: Path) -> None:
    source = tmp_path / "input.txt"
    source.write_text("中文虚拟文件", encoding="utf-8")
    item = inspect_input(source)
    output = tmp_path / "output.txt"
    output.write_text("preserve", encoding="utf-8")
    with pytest.raises(ConversionError, match="不会覆盖"):
        convert(source, "utf8", output)
    assert output.read_text() == "preserve"
    cancel = Event()
    cancel.set()
    with pytest.raises(InterruptedError):
        convert_file(item, "utf8", tmp_path / "cancel.txt", lambda *_: None, cancel)
    assert not (tmp_path / "cancel.txt").exists()
    assert source.read_text(encoding="utf-8") == "中文虚拟文件"


def test_cancel_after_encoding_cleans_staging_without_publishing(tmp_path: Path) -> None:
    source = tmp_path / "input.txt"
    source.write_text("sample", encoding="utf-8")
    cancel = Event()
    from filemind.conversion import service
    original = service._write_text

    def stop_after_write(item, key, staging):
        original(item, key, staging)
        cancel.set()

    with patch.object(service, "_write_text", side_effect=stop_after_write), pytest.raises(InterruptedError):
        convert_file(inspect_input(source), "utf8", tmp_path / "output.txt", lambda *_: None, cancel)
    assert not (tmp_path / "output.txt").exists()
    assert not list(tmp_path.glob(".filemind-convert-*"))


def test_source_change_and_invalid_destination_rejected(tmp_path: Path) -> None:
    source = tmp_path / "input.txt"
    source.write_text("first", encoding="utf-8")
    item = inspect_input(source)
    source.write_text("changed size", encoding="utf-8")
    with pytest.raises(ConversionError, match="变化"):
        convert_file(item, "utf8", tmp_path / "output.txt", lambda *_: None, Event())
    with pytest.raises(ConversionError, match="不存在"):
        convert(source, "utf8", tmp_path / "missing" / "output.txt")
    with pytest.raises(ConversionError, match="扩展名"):
        convert(source, "utf8", tmp_path / "wrong.pdf")
    with pytest.raises(ConversionError, match="不支持"):
        convert(source, "pdf", tmp_path / "output.pdf")


def test_permission_failure_is_reported_and_does_not_publish(tmp_path: Path) -> None:
    source = tmp_path / "input.txt"
    source.write_text("data", encoding="utf-8")
    with patch("filemind.conversion.service._write_text", side_effect=PermissionError("mock locked")):
        with pytest.raises(ConversionError, match="权限"):
            convert(source, "utf8", tmp_path / "output.txt")
    assert not (tmp_path / "output.txt").exists()
    assert not list(tmp_path.glob(".filemind-convert-*"))


def test_invalid_binary_text_and_image_rejected(tmp_path: Path) -> None:
    source = tmp_path / "input.txt"
    source.write_bytes(b"\x81\xff\x00")
    with pytest.raises(ConversionError, match="UTF"):
        convert(source, "utf8", tmp_path / "output.txt")
    fake_image = tmp_path / "input.png"
    fake_image.write_bytes(b"not an image")
    with pytest.raises(ConversionError, match="真实格式"):
        inspect_input(fake_image)


def test_racing_destination_is_not_overwritten(tmp_path: Path) -> None:
    source = tmp_path / "input.txt"
    source.write_text("data", encoding="utf-8")
    output = tmp_path / "output.txt"

    def destination_appears(completed, _total):
        if completed == 0:
            output.write_text("new user file", encoding="utf-8")

    with pytest.raises(ConversionError, match="不会覆盖"):
        convert_file(inspect_input(source), "utf8", output, destination_appears, Event())
    assert output.read_text() == "new user file"
