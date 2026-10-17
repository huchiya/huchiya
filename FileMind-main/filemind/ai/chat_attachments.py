"""Validate explicitly selected Orbit attachments and build API content parts."""

from __future__ import annotations

import base64
from pathlib import Path

from filemind.storage.settings import AISettings


IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
               ".gif": "image/gif", ".webp": "image/webp"}
TEXT_TYPES = {".txt", ".md", ".csv", ".json", ".py", ".java", ".c", ".h", ".cpp",
              ".hpp", ".js", ".ts", ".html", ".css", ".sql", ".log", ".xml", ".yaml", ".yml"}
MAX_ATTACHMENTS = 5
MAX_FILE_BYTES = 4 * 1024 * 1024
MAX_REQUEST_BYTES = 12 * 1024 * 1024
MAX_ATTACHMENT_TEXT_CHARS = 30_000


def build_user_content(prompt: str, paths: tuple[Path, ...], settings: AISettings) -> str | list[dict[str, object]]:
    """Build OpenAI-compatible text/image content from user-selected files only."""
    if not paths:
        return prompt
    if len(paths) > MAX_ATTACHMENTS:
        raise ValueError(f"一次最多添加 {MAX_ATTACHMENTS} 个附件。")
    parts: list[dict[str, object]] = [{"type": "text", "text": prompt}]
    total_bytes = 0
    for path in paths:
        data = _read_selected_file(path)
        total_bytes += len(data)
        if total_bytes > MAX_REQUEST_BYTES:
            raise ValueError("附件总大小超过 12 MB，请减少或压缩附件。")
        parts.extend(_content_parts(path, data, settings))
    return parts


def _read_selected_file(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"附件不是普通文件或已失效：{path.name}")
    if path.suffix.lower() not in IMAGE_TYPES and path.suffix.lower() not in TEXT_TYPES:
        raise ValueError(f"暂不支持 {path.suffix or '无扩展名'} 文件；可选图片、文本或代码文件。")
    try:
        data = path.read_bytes()
    except OSError as error:
        raise ValueError(f"无法读取附件 {path.name}，请检查权限或文件占用。") from error
    if not data or len(data) > MAX_FILE_BYTES:
        raise ValueError(f"附件 {path.name} 为空或超过单文件 4 MB 限制。")
    return data


def _content_parts(path: Path, data: bytes, settings: AISettings) -> list[dict[str, object]]:
    suffix = path.suffix.lower()
    if suffix in IMAGE_TYPES:
        return [_image_part(path, data, settings)]
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError(f"附件 {path.name} 不是 UTF-8 文本，暂时无法分析。") from error
    if len(text) > MAX_ATTACHMENT_TEXT_CHARS:
        raise ValueError(f"附件 {path.name} 超过 {MAX_ATTACHMENT_TEXT_CHARS} 字符的文本分析限制。")
    return [{"type": "text", "text": f"[附件：{path.name}]\n{text}"}]


def _image_part(path: Path, data: bytes, settings: AISettings) -> dict[str, object]:
    if settings.provider_id != "deepseek" or settings.model != "deepseek-flash":
        raise ValueError("图片理解目前仅验证支持 DeepSeek V4.1 Flash；请在设置中切换到该模型。")
    mime_type = IMAGE_TYPES[path.suffix.lower()]
    encoded = base64.b64encode(data).decode("ascii")
    return {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{encoded}",
                                                  "detail": "auto"}}
