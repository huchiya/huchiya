"""Public organization presets with explicit local versus AI capabilities."""

from dataclasses import dataclass
from datetime import datetime

from filemind.core.classifier import classify_file
from filemind.models import ClassificationResult, FileInfo


@dataclass(frozen=True)
class OrganizationPreset:
    """A selectable starting rule, never a model capability claim."""

    key: str
    title: str
    mode: str
    prompt: str = ""


PRESETS = (
    OrganizationPreset("extension", "按文件类型 · 本地", "rules"),
    OrganizationPreset("modified_month", "按修改年月 · 本地", "rules"),
    OrganizationPreset("courses", "按课程与章节 · AI", "ai", "按课程和章节整理学习资料；无法确定课程的文件保持原名，不要凭空猜测。"),
    OrganizationPreset("projects", "按项目与用途 · AI", "ai", "按照文件名所体现的项目和用途分类，代码、文档和素材分别归档；保留合理的原始名称。"),
    OrganizationPreset("custom", "自定义规则 · AI", "ai"),
    OrganizationPreset("purpose", "按用途或主题 · AI", "ai", "根据文件名所表达的用途和主题分类；无法确定时放入待确认，不猜测文件正文。"),
)


def classify_with_preset(item: FileInfo, preset_key: str) -> ClassificationResult:
    """Apply only deterministic local metadata rules without reading contents."""
    if preset_key == "modified_month":
        month = datetime.fromtimestamp(item.modified_ns / 1_000_000_000).strftime("%Y-%m")
        return ClassificationResult(month, "按本机时区的文件修改年月分类")
    return classify_file(item)
