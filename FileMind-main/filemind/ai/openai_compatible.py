"""OpenAI SDK adapter for compatible Chat Completions providers."""

from __future__ import annotations

import json
import logging
from threading import Event
from typing import Iterator
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from openai import APIConnectionError, APIStatusError, APITimeoutError, AuthenticationError, BadRequestError
from openai import NotFoundError, OpenAI, RateLimitError

from filemind.ai.prompts import SYSTEM_PROMPT, build_organize_prompt
from filemind.ai.providers import PROVIDER_BY_ID
from filemind.ai.response import parse_file_suggestions
from filemind.ai.schemas import AIBatchFailure, AIFileMetadata, AIOrganizationResult
from filemind.ai.base import ProgressCallback
from filemind.models import FileInfo, FileSuggestion
from filemind.storage.settings import AISettings


MAX_BATCH_FILES = 16
MAX_BATCH_CHARS = 12_000
MAX_RULE_LENGTH = 2_000
LOGGER = logging.getLogger(__name__)


class AIServiceError(RuntimeError):
    """Safe-to-display provider error without request or credential contents."""


class OpenAICompatibleClient:
    """Use one synchronous OpenAI SDK client from a non-UI worker thread."""

    def __init__(self, settings: AISettings) -> None:
        validate_connection_settings(settings)
        self.settings = settings
        # 本地模型（如 Ollama）无需真实密钥；SDK 仍需要一个非空占位值。
        api_key = settings.api_key.strip() or ("ollama" if _is_local_provider(settings) else settings.api_key)
        self.client = OpenAI(api_key=api_key, base_url=settings.base_url,
                             timeout=settings.timeout_seconds, max_retries=0)

    def test_connection(self) -> str:
        """Send a real minimal chat request and return the provider model name."""
        try:
            response = self.client.chat.completions.create(
                model=self.settings.model,
                messages=[{"role": "user", "content": "Reply with the single word OK."}],
                max_tokens=16,
            )
        except Exception as error:
            _log_provider_failure(self.settings, error)
            raise _friendly_error(error, self.settings) from None
        return str(getattr(response, "model", "") or self.settings.model)

    def complete(
        self,
        messages: list[dict[str, object]],
        cancel_event: Event | None = None,
    ) -> str:
        """Send a fully-formed message list and return the assistant text."""
        try:
            response = self.client.chat.completions.create(
                model=self.settings.model,
                messages=messages,
            )
        except Exception as error:
            _log_provider_failure(self.settings, error)
            raise _friendly_error(error, self.settings) from None
        if cancel_event and cancel_event.is_set():
            raise InterruptedError("生成已停止")
        content = response.choices[0].message.content or ""
        if not content.strip():
            raise AIServiceError("服务返回了空回答，请重试。")
        return content

    def stream(
        self,
        messages: list[dict[str, object]],
        cancel_event: Event | None = None,
    ) -> Iterator[str]:
        """Yield response text chunks, discarding anything after cancellation."""
        try:
            stream = self.client.chat.completions.create(
                model=self.settings.model,
                messages=messages,
                stream=True,
            )
            for chunk in stream:
                if cancel_event and cancel_event.is_set():
                    raise InterruptedError("生成已停止")
                choices = getattr(chunk, "choices", None) or ()
                delta = choices[0].delta.content if choices else None
                if delta:
                    yield delta
        except InterruptedError:
            raise
        except Exception as error:
            _log_provider_failure(self.settings, error)
            raise _friendly_error(error, self.settings) from None

    def complete_chat(
        self,
        system_prompt: str,
        messages: list[dict[str, object]],
        cancel_event: Event | None = None,
    ) -> str:
        """Send one independent chat request and discard results after cancellation."""
        request_messages = [{"role": "system", "content": system_prompt}, *messages]
        return self.complete(request_messages, cancel_event)

    def organize_files(
        self,
        files: list[AIFileMetadata],
        user_rule: str,
        rename_enabled: bool,
        on_progress: ProgressCallback | None = None,
        cancel_event: Event | None = None,
    ) -> AIOrganizationResult:
        """Request suggestions in bounded batches and preserve explicit failures."""
        if not user_rule.strip():
            user_rule = "根据文件名和扩展名进行清晰、保守的分类；不确定时放入其他并保留原名。"
        if len(user_rule) > MAX_RULE_LENGTH:
            raise ValueError(f"整理规则不能超过 {MAX_RULE_LENGTH} 个字符")
        batches = _make_batches(files, user_rule, rename_enabled)
        suggestions: dict[str, FileSuggestion] = {}
        failures: list[AIBatchFailure] = []
        completed = 0
        for batch_index, batch in enumerate(batches):
            if cancel_event and cancel_event.is_set():
                raise InterruptedError("AI 整理已取消")
            batch_map = {item.file_id: _as_file_info(item) for item in batch}
            try:
                response = self.client.chat.completions.create(
                    model=self.settings.model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": build_organize_prompt(batch, user_rule, rename_enabled)},
                    ],
                )
                if cancel_event and cancel_event.is_set():
                    raise InterruptedError("AI 整理已取消")
                response_text = response.choices[0].message.content or ""
                parsed, item_failures = parse_file_suggestions(response_text, batch_map, rename_enabled)
                suggestions.update(parsed)
                for failed_id, failed_message in item_failures.items():
                    failures.append(AIBatchFailure((failed_id,), failed_message))
            except InterruptedError:
                raise
            except Exception as error:
                failures.append(AIBatchFailure(tuple(item.file_id for item in batch), _safe_batch_error(error)))
                if _is_fatal_provider_error(error):
                    remaining = [item for later in batches[batch_index + 1:] for item in later]
                    if remaining:
                        failures.append(AIBatchFailure(tuple(item.file_id for item in remaining), _safe_batch_error(error)))
                    break
            completed += len(batch)
            if on_progress:
                on_progress(completed, len(files))
        return AIOrganizationResult(suggestions, tuple(failures))


def validate_connection_settings(settings: AISettings) -> None:
    """Reject malformed or unsafe connection settings before SDK construction."""
    if not _is_local_provider(settings) and not settings.api_key.strip():
        raise ValueError("请先填写 API Key。")
    parsed = urlsplit(settings.base_url.strip())
    if parsed.scheme not in {"https", "http"} or not parsed.hostname:
        raise ValueError("API Base URL 必须是完整的 HTTP 或 HTTPS 地址。")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("API Base URL 不能包含账号、密码、查询参数或片段。")
    if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("远程 API 必须使用 HTTPS；HTTP 仅允许本机模型地址。")
    if not settings.model.strip():
        raise ValueError("请填写模型名称。")
    if not 5 <= settings.timeout_seconds <= 180:
        raise ValueError("请求超时时间必须在 5 到 180 秒之间。")


def _is_local_provider(settings: AISettings) -> bool:
    """A provider is local when its preset (or the loaded settings) is marked local."""
    preset = PROVIDER_BY_ID.get(settings.provider_id)
    return bool(settings.local or (preset is not None and preset.local))


def list_ollama_models(base_url: str, timeout_seconds: int = 10) -> list[str]:
    """Query a local Ollama server's installed models via its native /api/tags endpoint."""
    parsed = urlsplit(base_url.strip())
    if parsed.scheme not in {"https", "http"} or not parsed.hostname:
        raise AIServiceError("Ollama Base URL 必须是完整的 HTTP 或 HTTPS 地址。")
    if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise AIServiceError("Ollama 只接受本机地址；远程地址必须使用 HTTPS。")
    # OpenAI 兼容端点是 /v1/...，原生模型列表固定在服务器根路径 /api/tags。
    tags_url = f"{parsed.scheme}://{parsed.netloc}/api/tags"
    request = Request(tags_url, method="GET")
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - local scheme checked above
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        raise AIServiceError(f"Ollama 返回 HTTP {error.code}；请确认已启动本机 Ollama 服务。") from error
    except (URLError, OSError) as error:
        raise AIServiceError(_ollama_connection_error(error)) from error
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise AIServiceError("Ollama 返回了无法解析的响应；请检查服务地址。") from error
    models: list[str] = []
    seen: set[str] = set()
    for item in payload.get("models", []) if isinstance(payload, dict) else []:
        name = item.get("name") if isinstance(item, dict) else None
        if not isinstance(name, str) or not name.strip():
            continue
        base_name = name[:-7] if name.endswith(":latest") else name
        if base_name and base_name not in seen:
            seen.add(base_name)
            models.append(base_name)
    return models


def _ollama_connection_error(error: Exception) -> str:
    causes = list(_exception_chain(error))
    if any("refused" in str(cause).lower() for cause in causes):
        return "无法连接本机 Ollama 服务，请确认已安装并启动 Ollama。"
    if any("timed out" in str(cause).lower() for cause in causes):
        return "连接本机 Ollama 超时；首次加载模型可能较慢，请稍后重试。"
    return f"无法连接本机 Ollama 服务：{error}"


def _make_batches(
    files: list[AIFileMetadata], user_rule: str, rename_enabled: bool
) -> list[list[AIFileMetadata]]:
    batches: list[list[AIFileMetadata]] = []
    current: list[AIFileMetadata] = []
    for item in files:
        candidate = current + [item]
        encoded = build_organize_prompt(candidate, user_rule, rename_enabled)
        if len(candidate) > MAX_BATCH_FILES or len(encoded) > MAX_BATCH_CHARS:
            if not current:
                raise ValueError(f"文件名过长，无法安全发送给模型：{item.file_name[:80]}")
            batches.append(current)
            current = [item]
        else:
            current = candidate
    if current:
        batches.append(current)
    return batches


def _as_file_info(item: AIFileMetadata) -> FileInfo:
    """Create the path-free adapter expected by the strict response validator."""
    from pathlib import Path

    return FileInfo(Path(item.file_name), item.size_bytes, item.modified_ns)


def _friendly_error(error: Exception, settings: AISettings | None = None) -> AIServiceError:
    if isinstance(error, AuthenticationError):
        return AIServiceError("API Key 无效或无权访问此服务。")
    if isinstance(error, APIStatusError) and error.status_code == 403:
        return AIServiceError("服务拒绝访问（403），请检查账号权限、模型授权或服务区域。")
    if isinstance(error, RateLimitError):
        return AIServiceError("请求受限（429），请检查调用频率、额度不足或账户余额。")
    if isinstance(error, APITimeoutError):
        return AIServiceError("请求超时，请检查网络或适当提高超时时间。")
    if isinstance(error, NotFoundError):
        return AIServiceError(_with_provider_detail(
            "接口地址或模型不存在，请检查 Base URL 与模型名称。", error, settings))
    if isinstance(error, BadRequestError):
        return AIServiceError(_with_provider_detail(
            "服务商拒绝了请求，请检查模型名称是否有效、是否支持 Chat Completions 及请求格式。", error, settings))
    if isinstance(error, APIConnectionError):
        return AIServiceError(_connection_error_message(error))
    if isinstance(error, APIStatusError):
        return AIServiceError(_with_provider_detail(_status_error_message(error.status_code), error, settings))
    return AIServiceError("模型请求失败，请检查配置后重试。")


def _with_provider_detail(message: str, error: APIStatusError,
                          settings: AISettings | None = None) -> str:
    """Append the provider's own error text so opaque 5xx/404 failures stay diagnosable."""
    detail = _provider_error_detail(error)
    if not detail:
        return message
    hint = _provider_detail_hint(detail, settings)
    return f"{message}{hint}（服务商返回：{detail}）"


def _provider_detail_hint(detail: str, settings: AISettings | None = None) -> str:
    """Turn a known local-model failure into one actionable sentence."""
    lowered = detail.lower()
    memory_markers = ("out-of-memory", "out of memory", "outofmemory", "unable to allocate",
                      "failed to allocate", "allocate buffer", "alloc_buffer")
    if any(marker in lowered for marker in memory_markers):
        return " 本机内存不足，无法加载该模型；请改用更小的模型（例如 `llama3.2:1b`、`phi3:mini`），或降低上下文长度后重试。"
    if "try pulling" in lowered:
        # 错误体本身就提示需要拉取模型（典型的本机 Ollama 场景），直接给出操作指引。
        return (" 本机未安装该模型，请先运行 `ollama pull <模型>` 安装，"
                "或在“模型配置”里点“检测本机 Ollama 模型”选择已安装的模型。")
    if "not found" in lowered and "model" in lowered:
        if settings is not None and _is_local_provider(settings):
            return (" 本机未安装该模型，请先运行 `ollama pull <模型>` 安装，"
                    "或在“模型配置”里点“检测本机 Ollama 模型”选择已安装的模型。")
        return " 请确认该模型名称在所选服务商可用（可在“模型配置”里核对模型名称）。"
    return ""


def _provider_error_detail(error: Exception) -> str:
    """Read a short message only from the provider's JSON error body, never the SDK text.

    The SDK's own message string is intentionally ignored: it can echo request internals
    or credential fragments. Provider error bodies describe the failure, so they are safe
    to surface after whitespace collapsing and truncation.
    """
    body = getattr(error, "body", None) if isinstance(error, APIStatusError) else None
    raw = body.get("error", body.get("message")) if isinstance(body, dict) else None
    if isinstance(raw, dict):
        raw = raw.get("message")
    if not isinstance(raw, str) or not raw.strip():
        return ""
    collapsed = " ".join(raw.split())
    return collapsed if len(collapsed) <= 140 else f"{collapsed[:140].rstrip()}…"


def _connection_error_message(error: APIConnectionError) -> str:
    causes = list(_exception_chain(error))
    names = {type(cause).__name__.lower() for cause in causes}
    modules = {type(cause).__module__.lower() for cause in causes}
    if any("proxy" in name for name in names):
        return "代理连接失败，请检查代理地址和代理服务状态。"
    if any("ssl" in name or "tls" in name for name in names) or any(
        module == "ssl" for module in modules
    ):
        return "TLS 安全连接失败，请检查系统时间、证书和 HTTPS 代理设置。"
    if any(name == "gaierror" for name in names):
        return "DNS 解析失败，请检查网络连接和域名解析。"
    return "无法连接服务商，网络连接失败；请检查网络、DNS、Base URL 和代理设置。"


def _exception_chain(error: BaseException) -> tuple[BaseException, ...]:
    chain: list[BaseException] = []
    current: BaseException | None = error
    while current is not None and current not in chain:
        chain.append(current)
        current = current.__cause__ or current.__context__
    return tuple(chain)


def _status_error_message(status_code: int) -> str:
    if status_code >= 500:
        return f"服务商服务器异常（HTTP {status_code}），请稍后重试。"
    if status_code == 402:
        return "服务商账户余额或付款状态异常（HTTP 402），请检查账户。"
    return f"服务商返回 HTTP {status_code}，请检查配置和账户权限。"


def _log_provider_failure(settings: AISettings, error: Exception) -> None:
    status = error.status_code if isinstance(error, APIStatusError) else "-"
    LOGGER.warning("AI request failed provider=%s error_type=%s http_status=%s",
                   settings.provider_id, type(error).__name__, status)


def _safe_batch_error(error: Exception) -> str:
    if isinstance(error, ValueError):
        return str(error)
    return str(_friendly_error(error))


def _is_fatal_provider_error(error: Exception) -> bool:
    return isinstance(error, (AuthenticationError, NotFoundError, BadRequestError, APIConnectionError,
                              APITimeoutError, APIStatusError))
