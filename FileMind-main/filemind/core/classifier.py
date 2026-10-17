"""Dependency-free extension-based classification for the first release."""

from filemind.models import ClassificationResult, FileInfo


CATEGORY_EXTENSIONS: dict[str, set[str]] = {
    "图片": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".heic"},
    "文档": {".doc", ".docx", ".pdf", ".txt", ".md", ".rtf", ".odt"},
    "表格": {".xls", ".xlsx", ".csv", ".tsv", ".ods"},
    "演示文稿": {".ppt", ".pptx", ".odp"},
    "视频": {".mp4", ".mov", ".mkv", ".avi", ".webm", ".wmv"},
    "音频": {".mp3", ".wav", ".flac", ".aac", ".m4a", ".ogg"},
    "压缩包": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2"},
    "安装包": {".exe", ".msi", ".dmg", ".apk", ".deb", ".rpm"},
    "代码": {".py", ".c", ".h", ".cpp", ".java", ".js", ".ts", ".html", ".css", ".sql"},
}


def classify_file(file_info: FileInfo) -> ClassificationResult:
    """Classify a file from its suffix without reading or uploading its contents."""
    for category, extensions in CATEGORY_EXTENSIONS.items():
        if file_info.suffix in extensions:
            return ClassificationResult(category, f"扩展名 {file_info.suffix} 属于{category}")
    suffix_hint = file_info.suffix or "无扩展名"
    return ClassificationResult("其他", f"{suffix_hint} 暂无匹配规则")
