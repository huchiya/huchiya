"""PDFium text extraction and page-image export, serialized across threads."""

import io
from pathlib import Path
from threading import Event, RLock
from zipfile import ZIP_DEFLATED, ZipFile

from filemind.conversion.base import ConversionError, Progress, check_cancel
from filemind.conversion.models import ConversionTarget


PDF_LOCK = RLock()
TARGETS = (
    ConversionTarget("pdf_text", "PDF → TXT（文本层）", ".txt", "按页提取文本层，不执行 OCR；扫描版 PDF 可能无文本。"),
    ConversionTarget("pdf_png", "PDF → PNG 页面 ZIP", ".zip", "逐页渲染为 144 DPI PNG，再打包；最多 100 页，不承诺保留交互表单。"),
    ConversionTarget("pdf_jpeg", "PDF → JPEG 页面 ZIP", ".zip", "逐页渲染并打包 JPEG；有损压缩，最多 100 页。"),
)


def inspect_pdf(source: Path) -> tuple[str, str, tuple[ConversionTarget, ...]]:
    """Inspect page count under the same mutex used by all PDFium calls."""
    import pypdfium2 as pdfium
    try:
        with PDF_LOCK, pdfium.PdfDocument(source) as document:
            count = len(document)
            if count < 1 or count > 100:
                raise ConversionError("PDF 页数必须为 1–100 页。")
            return "pdf", f"PDF · {count} 页 · 本地 PDFium", TARGETS
    except pdfium.PdfiumError as error:
        raise ConversionError("PDF 无法打开，可能已加密或损坏；请先在本机解密。") from error


def convert_pdf(source: Path, key: str, staging: Path, progress: Progress, cancel: Event) -> None:
    """Release each PDF page before continuing, keeping memory bounded."""
    import pypdfium2 as pdfium
    with PDF_LOCK, pdfium.PdfDocument(source) as document:
        if key == "pdf_text":
            _extract_text(document, staging, progress, cancel)
        else:
            _export_pages(document, key, staging, progress, cancel)


def _extract_text(document: object, output: Path, progress: Progress, cancel: Event) -> None:
    nonempty = False
    with output.open("w", encoding="utf-8") as stream:
        for index in range(len(document)):
            check_cancel(cancel)
            page = document[index]
            try:
                textpage = page.get_textpage()
                try:
                    text = textpage.get_text_bounded()
                finally:
                    textpage.close()
                nonempty = nonempty or bool(text.strip())
                stream.write(f"--- 第 {index + 1} 页 ---\n{text}\n\n")
            finally:
                page.close()
            progress(index + 1, len(document))
    if not nonempty:
        raise ConversionError("PDF 没有可提取的文本层；未执行 OCR，可改用页面图像导出。")


def _export_pages(document: object, key: str, output: Path, progress: Progress, cancel: Event) -> None:
    image_format, extension = ("PNG", "png") if key == "pdf_png" else ("JPEG", "jpg")
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for index in range(len(document)):
            check_cancel(cancel)
            page = document[index]
            try:
                width, height = page.get_size()
                if width * height * 4 > 20_000_000:
                    raise ConversionError("PDF 单页渲染超过 2000 万像素限制。")
                bitmap = page.render(scale=2)
                try:
                    with bitmap.to_pil() as image, io.BytesIO() as buffer:
                        image.convert("RGB").save(buffer, format=image_format)
                        archive.writestr(f"page-{index + 1:03}.{extension}", buffer.getvalue())
                finally:
                    bitmap.close()
            finally:
                page.close()
            progress(index + 1, len(document))
