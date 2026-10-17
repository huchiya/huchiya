"""Validate structured AI suggestions without accepting model-supplied paths."""

import json
from typing import Any

from filemind.core.planner import (name_suffixes, validate_category, validate_file_name,
                                   validate_relative_subdirectory)
from filemind.models import FileInfo, FileSuggestion


MAX_RESPONSE_BYTES = 1_000_000
SUGGESTION_FIELDS = {"file_name", "category", "new_name", "reason"}
AI_SUGGESTION_FIELDS = {"file_id", "category", "target_subdirectory", "new_name", "reason"}
# The full field set above is documented for the prompt; the per-item parser
# tolerates omitted optional fields (target_subdirectory, new_name, reason) so
# one loosely-typed field no longer discards the whole batch.


def parse_suggestions(response_text: str, expected_names: set[str]) -> dict[str, FileSuggestion]:
    """Parse exact per-file suggestions; model output cannot choose filesystem paths."""
    if len(response_text.encode("utf-8")) > MAX_RESPONSE_BYTES:
        raise ValueError("模型返回内容超过大小限制")
    try:
        payload: Any = json.loads(response_text)
    except json.JSONDecodeError as error:
        raise ValueError("模型返回的内容不是合法 JSON") from error
    if not isinstance(payload, dict) or set(payload) != {"suggestions"}:
        raise ValueError("模型返回格式必须包含 suggestions 数组")
    items = payload["suggestions"]
    if not isinstance(items, list) or len(items) != len(expected_names):
        raise ValueError("模型必须为每个文件返回且只返回一条建议")

    suggestions: dict[str, FileSuggestion] = {}
    for item in items:
        suggestion = _parse_item(item, expected_names)
        if suggestion.file_name in suggestions:
            raise ValueError(f"模型重复返回文件：{suggestion.file_name}")
        suggestions[suggestion.file_name] = suggestion
    if set(suggestions) != expected_names:
        raise ValueError("模型返回的文件名与待整理文件不一致")
    return suggestions


def parse_file_suggestions(
    response_text: str,
    expected_files: dict[str, FileInfo],
    rename_enabled: bool,
) -> tuple[dict[str, FileSuggestion], dict[str, str]]:
    """Validate stable-ID suggestions while tolerating per-item problems.

    Returns ``(suggestions, item_failures)``. A single malformed item no longer
    discards the whole batch: only the offending file is reported and the caller
    falls back to local rules for that row. Unsafe categories, subdirectories and
    rename suffixes still fail their row (never silently execute); top-level
    structural errors (bad JSON, missing ``suggestions`` array) still raise.
    """
    if len(response_text.encode("utf-8")) > MAX_RESPONSE_BYTES:
        raise ValueError("模型返回内容超过大小限制")
    try:
        payload: Any = json.loads(response_text)
    except json.JSONDecodeError as error:
        raise ValueError("模型返回的内容不是合法 JSON") from error
    if not isinstance(payload, dict) or set(payload) != {"suggestions"}:
        raise ValueError("模型返回格式必须包含 suggestions 数组")
    items = payload["suggestions"]
    if not isinstance(items, list):
        raise ValueError("模型返回格式必须包含 suggestions 数组")

    suggestions: dict[str, FileSuggestion] = {}
    item_failures: dict[str, str] = {}
    for item in items:
        file_id = item.get("file_id") if isinstance(item, dict) else None
        if not isinstance(file_id, str) or file_id not in expected_files:
            # Cannot map this item to one requested file; ignore it. Files that
            # never receive a usable item are collected as failures below.
            continue
        if file_id in suggestions or file_id in item_failures:
            continue
        try:
            suggestions[file_id] = _parse_file_item(
                item, file_id, expected_files[file_id], rename_enabled
            )
        except ValueError as error:
            item_failures[file_id] = str(error)

    # Files the model never answered (or whose item was unusable) fail their row
    # so the caller falls back to local rules instead of the whole batch.
    for file_id in expected_files:
        if file_id not in suggestions and file_id not in item_failures:
            item_failures[file_id] = "模型未返回该文件的有效建议"
    return suggestions, item_failures


def _parse_file_item(
    item: Any,
    file_id: str,
    file_info: FileInfo,
    rename_enabled: bool,
) -> FileSuggestion:
    """Parse one suggestion, normalizing optional fields while keeping safety."""
    if not isinstance(item, dict):
        raise ValueError("AI 建议字段无效")
    category_raw = item.get("category")
    if not isinstance(category_raw, str) or not category_raw.strip():
        raise ValueError("AI 建议字段 category 必须是文本")
    category = validate_category(category_raw)

    # Subdirectory is optional. null / missing / non-text safely mean "no
    # subdirectory" (the file goes directly under the category folder); an
    # actual text value must still pass the path-escape validator.
    sub_raw = item.get("target_subdirectory", "")
    if sub_raw is None:
        subdirectory = ""
    elif isinstance(sub_raw, str):
        subdirectory = validate_relative_subdirectory(sub_raw)
    else:
        subdirectory = ""

    reason_raw = item.get("reason")
    reason = reason_raw.strip() if isinstance(reason_raw, str) else ""
    if not reason:
        reason = "AI 分类建议"
    if len(reason) > 500:
        reason = reason[:500]

    suggested_name = ""
    if rename_enabled:
        name_raw = item.get("new_name")
        if isinstance(name_raw, str):
            name_raw = name_raw.strip()
            if name_raw:
                validate_file_name(name_raw)
                if name_suffixes(name_raw) != name_suffixes(file_info.name):
                    raise ValueError(f"新文件名必须保留原扩展名：{file_info.name}")
                suggested_name = name_raw
        # null / non-text / empty all keep the original name.
    return FileSuggestion(file_info.name, category, suggested_name, reason, file_id, subdirectory)


def _parse_item(item: Any, expected_names: set[str]) -> FileSuggestion:
    if not isinstance(item, dict) or set(item) != SUGGESTION_FIELDS:
        raise ValueError("单条建议字段无效，模型不得返回目标路径或操作命令")
    if not all(isinstance(item[field], str) for field in SUGGESTION_FIELDS):
        raise ValueError("建议字段必须全部为文本")
    file_name = item["file_name"]
    if file_name not in expected_names:
        raise ValueError(f"模型返回了未扫描的文件：{file_name}")
    category = validate_category(item["category"])
    new_name = validate_file_name(item["new_name"])
    reason = item["reason"].strip()
    if not reason:
        raise ValueError("整理理由不能为空")
    original_suffix = "".join(name_suffixes(file_name))
    suggested_suffix = "".join(name_suffixes(new_name))
    if suggested_suffix != original_suffix:
        raise ValueError(f"新文件名必须保留原扩展名：{file_name}")
    return FileSuggestion(file_name, category, new_name, reason)
