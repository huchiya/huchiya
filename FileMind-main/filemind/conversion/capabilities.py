"""Truthful capability cards, independent of any selected file."""

from dataclasses import dataclass
from importlib.util import find_spec

from filemind.conversion.office import office_binary


@dataclass(frozen=True)
class FormatCapability:
    """A UI summary, never a promise that every listed format converts losslessly."""

    title: str
    inputs: str
    outputs: str
    state: str
    detail: str
    tint: str


def capabilities() -> tuple[FormatCapability, ...]:
    """Describe installed adapters without probing codecs on the UI thread."""
    pdf = find_spec("pypdfium2") is not None
    media = find_spec("imageio_ffmpeg") is not None
    office = office_binary() is not None
    return (
        FormatCapability("图片", "PNG · JPEG · WebP · TIFF · BMP · GIF · AVIF 等",
                         "本机图片编码器 · 单页 PDF", "单帧支持",
                         "目标按已安装编码器显示；RAW、HEIC 尚未集成，动图/多页不转换。", "mint"),
        FormatCapability("文本与结构化数据", "TXT · Markdown · HTML · JSON · CSV · XML · YAML · EPUB",
                         "文本编码 · HTML · DOCX · JSON/YAML · CSV/XLSX", "已实现",
                         "仅 UTF-8 / 带 BOM 的 UTF-16；EPUB 仅章节文字，不处理 DRM。", "blue"),
        FormatCapability("Word / WPS 文档", "DOCX（WPS 保存的标准 DOCX 也可）",
                         "TXT · 静态 HTML", "内容提取",
                         "段落与表格文字导出，不保留版面和图片。DOC/ODT/RTF 另需 LibreOffice。", "amber"),
        FormatCapability("Excel / WPS 表格", "XLSX · CSV",
                         "全表 JSON · CSV ZIP · XLSX", "值导出",
                         "不计算公式、不读取外部数据；公式仅使用已有缓存值，不保留样式。", "mint"),
        FormatCapability("PPT / WPS 演示", "PPTX（标准 OOXML）",
                         "TXT · 静态 HTML", "文字提取",
                         "按页提取文本框文字，不导出动画、讲者备注或页面图像。", "blue"),
        FormatCapability("PDF", "未加密 PDF · 最多 100 页",
                         "文本层 TXT · PNG/JPEG 页面 ZIP", "已实现" if pdf else "不可用",
                         "本地 PDFium；扫描版无文本时明确提示，不包含 OCR。", "amber"),
        FormatCapability("音频", "MP3 · WAV · FLAC · Ogg · AAC · M4A 等",
                         "MP3 · WAV · FLAC · Ogg（按编码器）", "后端已安装" if media else "不可用",
                         "选择文件后检测真实音轨与编码器；重新编码可能有损，仅处理首个音轨。", "mint"),
        FormatCapability("视频", "MP4 · MOV · MKV · WebM · AVI · WMV",
                         "MP4 · WebM · MKV · 提取音轨", "后端已安装" if media else "不可用",
                         "本地 FFmpeg；不保留字幕/封面，不移除 DRM；限单文件 64 MB / 5 分钟处理时间。", "blue"),
        FormatCapability("Office 排版转换", "DOC/DOCX · XLS/XLSX · PPT/PPTX · ODT/ODS/ODP · RTF",
                         "PDF · 对应 Office/ODF 格式", "实验性" if office else "不可用",
                         "本机 LibreOffice 已检测到，复杂排版需核对。" if office else
                         "未检测到 LibreOffice；WPS/ET/DPS 专有格式尚未验证，不提供假转换。", "lavender"),
        FormatCapability("任意普通文件", "用户主动选择的一个普通文件",
                         "ZIP（保留源文件）", "已实现",
                         "不解压、不递归、不上传；所有转换均另存到新文件，不覆盖已有文件。", "amber"),
    )
