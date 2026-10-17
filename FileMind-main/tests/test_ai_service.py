"""Mocked tests for OpenAI-compatible providers and strict AI suggestions."""

import json
import socket
import ssl
import tempfile
import unittest
from pathlib import Path
from threading import Event
from unittest.mock import patch

import httpx
from openai import (APIConnectionError, APIStatusError, APITimeoutError, AuthenticationError,
                    BadRequestError, NotFoundError, OpenAI, RateLimitError)

from filemind.ai.openai_compatible import (AIServiceError, OpenAICompatibleClient,
                                          _friendly_error, validate_connection_settings)
from filemind.ai.providers import PROVIDERS, PROVIDER_BY_ID
from filemind.ai.response import parse_file_suggestions
from filemind.ai.schemas import file_metadata
from filemind.core.classifier import classify_file
from filemind.core.planner import build_plan
from filemind.core.scanner import scan_files
from filemind.models import FileInfo, FileSuggestion
from filemind.storage.settings import AISettings


class AIFakeTransport:
    def __init__(self, response_text: str = "OK", error: Exception | None = None):
        self.response_text = response_text
        self.error = error
        self.calls: list[dict[str, object]] = []
        self.chat = self
        self.completions = self

    def create(self, **request: object):
        self.calls.append(request)
        if self.error:
            raise self.error
        content = self.response_text
        messages = request.get("messages", [])
        if content == "auto" and isinstance(messages, list):
            body = json.loads(messages[-1]["content"])
            content = json.dumps({"suggestions": [
                {"file_id": item["file_id"], "category": "学习资料", "target_subdirectory": "数据结构/第1章",
                 "new_name": "链表复习.txt", "reason": "文件名与课程规则匹配"}
                for item in body["files"]
            ]}, ensure_ascii=False)
        return type("Response", (), {
            "model": "fake-model",
            "choices": [type("Choice", (), {"message": type("Message", (), {"content": content})()})()],
        })()


class AIServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = AISettings("custom", "https://api.example.com/v1", "test-model", 10, "test-secret")

    def test_provider_presets_are_explicit_and_custom_is_manual(self) -> None:
        self.assertEqual({item.provider_id for item in PROVIDERS}, set(PROVIDER_BY_ID))
        self.assertEqual(PROVIDER_BY_ID["custom"].base_url, "")
        self.assertEqual(PROVIDER_BY_ID["dashscope"].model, "qwen-plus")

    def test_empty_key_and_invalid_base_url_fail_before_request(self) -> None:
        with self.assertRaisesRegex(ValueError, "API Key"):
            validate_connection_settings(AISettings("custom", "https://api.example.com", "m", 20))
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            validate_connection_settings(AISettings("custom", "http://example.com/v1", "m", 20, "secret"))

    def test_successful_connection_test_performs_real_client_call(self) -> None:
        transport = AIFakeTransport()
        with patch("filemind.ai.openai_compatible.OpenAI", return_value=transport) as openai_factory:
            client = OpenAICompatibleClient(self.settings)
            actual_model = client.test_connection()

        self.assertEqual(actual_model, "fake-model")
        openai_factory.assert_called_once()
        self.assertEqual(len(transport.calls), 1)

    def test_deepseek_connection_uses_exact_chat_endpoint_and_timeout(self) -> None:
        settings = AISettings("deepseek", "https://api.deepseek.com", "deepseek-flash", 37, "mock-key")
        requests: list[httpx.Request] = []

        def respond(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, json={
                "id": "test", "object": "chat.completion", "created": 1,
                "model": "deepseek-flash", "choices": [{"index": 0,
                    "message": {"role": "assistant", "content": "OK"}, "finish_reason": "stop"}],
            })

        transport = httpx.Client(transport=httpx.MockTransport(respond))
        captured: dict[str, object] = {}

        def client_factory(**options):
            captured.update(options)
            return OpenAI(**options, http_client=transport)

        with patch("filemind.ai.openai_compatible.OpenAI", side_effect=client_factory):
            self.assertEqual(OpenAICompatibleClient(settings).test_connection(), "deepseek-flash")

        self.assertEqual(str(requests[0].url), "https://api.deepseek.com/chat/completions")
        self.assertEqual(captured["base_url"], "https://api.deepseek.com")
        self.assertEqual(captured["timeout"], 37)
        self.assertEqual(captured["max_retries"], 0)
        self.assertEqual(requests[0].headers["authorization"], "Bearer mock-key")
        transport.close()

    def test_invalid_json_is_reported_for_each_batch(self) -> None:
        with patch("filemind.ai.openai_compatible.OpenAI", return_value=AIFakeTransport("{bad")):
            client = OpenAICompatibleClient(self.settings)
            result = client.organize_files([file_metadata(_file("资料.txt"))], "按课程分类", True)

        self.assertEqual(result.suggestions, {})
        self.assertIn("合法 JSON", result.failures[0].message)

    def test_files_are_batched_and_failed_files_remain_explicit(self) -> None:
        request = httpx.Request("POST", self.settings.base_url)
        rate_error = RateLimitError("rate limited", response=httpx.Response(429, request=request), body=None)

        class PartialTransport(AIFakeTransport):
            def create(inner_self, **request_body):
                if not inner_self.calls:
                    return super(PartialTransport, inner_self).create(**request_body)
                inner_self.calls.append(request_body)
                raise rate_error

        files = [_file(f"课程资料-{index}.txt") for index in range(18)]
        transport = PartialTransport("auto")
        with patch("filemind.ai.openai_compatible.OpenAI", return_value=transport):
            client = OpenAICompatibleClient(self.settings)
            result = client.organize_files([file_metadata(item) for item in files], "分课程整理", True)

        self.assertEqual(len(transport.calls), 2)
        self.assertEqual(len(result.suggestions), 16)
        self.assertEqual(sum(len(failure.file_ids) for failure in result.failures), 2)
        self.assertIn("额度不足", result.failures[0].message)

    def test_cancel_after_remote_response_discards_ai_result(self) -> None:
        cancel_event = Event()

        class CancellingTransport(AIFakeTransport):
            def create(inner_self, **request_body):
                response = super(CancellingTransport, inner_self).create(**request_body)
                cancel_event.set()
                return response

        with patch("filemind.ai.openai_compatible.OpenAI", return_value=CancellingTransport("auto")):
            client = OpenAICompatibleClient(self.settings)
            with self.assertRaises(InterruptedError):
                client.organize_files([file_metadata(_file("notes.txt"))], "整理", True,
                                      cancel_event=cancel_event)

    def test_api_errors_are_sanitized_without_returning_key(self) -> None:
        request = httpx.Request("POST", self.settings.base_url)
        response_401 = httpx.Response(401, request=request)
        response_404 = httpx.Response(404, request=request)
        response_429 = httpx.Response(429, request=request)
        errors = (
            (AuthenticationError("secret must not leak", response=response_401, body=None), "API Key 无效"),
            (NotFoundError("secret must not leak", response=response_404, body=None), "模型不存在"),
            (RateLimitError("secret must not leak", response=response_429, body=None), "额度不足"),
            (APITimeoutError(request=request), "请求超时"),
            (APIConnectionError(request=request), "无法连接服务商"),
        )
        for error, expected in errors:
            with self.subTest(error=type(error).__name__):
                with patch("filemind.ai.openai_compatible.OpenAI", return_value=AIFakeTransport(error=error)):
                    client = OpenAICompatibleClient(self.settings)
                    with self.assertRaises(AIServiceError) as raised:
                        client.test_connection()
                self.assertIn(expected, str(raised.exception))
                self.assertNotIn("secret must not leak", str(raised.exception))

    def test_http_status_errors_have_distinct_user_guidance(self) -> None:
        request = httpx.Request("POST", self.settings.base_url)
        expected_by_status = {
            403: "账号权限",
            500: "服务器异常",
        }
        for status, expected in expected_by_status.items():
            response = httpx.Response(status, request=request)
            error = APIStatusError("private detail", response=response, body=None)
            with self.subTest(status=status):
                self.assertIn(expected, str(_friendly_error(error)))

    def test_provider_error_body_is_surfaced_for_opaque_server_errors(self) -> None:
        # Ollama 等本机服务对未安装模型等故障有时返回 500，body 里才是真正原因。
        request = httpx.Request("POST", self.settings.base_url)
        response = httpx.Response(500, request=request)
        error = APIStatusError(
            "opaque internal error", response=response,
            body={"error": {"message": 'model "qwen2.5" not found, try pulling it first'}},
        )
        message = str(_friendly_error(error))
        self.assertIn("服务器异常", message)
        self.assertIn("not found", message)
        self.assertIn("ollama pull", message)

    def test_bad_request_body_is_surfaced_for_invalid_model_names(self) -> None:
        # 聚合平台（如 SiliconFlow）在模型名无效时返回 400，body 里才有确切原因。
        request = httpx.Request("POST", self.settings.base_url)
        response = httpx.Response(400, request=request)
        error = BadRequestError("opaque", response=response, body={
            "error": {"message": "Model does not exist. Please check the model name."},
        })
        message = str(_friendly_error(error))
        self.assertIn("拒绝了请求", message)
        self.assertIn("Model does not exist", message)

    def test_out_of_memory_server_error_gets_an_actionable_hint(self) -> None:
        # Ollama 真实 500 响应体把 message 放在顶层（不是 error.message），两种措辞都要覆盖。
        request = httpx.Request("POST", self.settings.base_url)
        response = httpx.Response(500, request=request)
        bodies = (
            "llama-server reported out-of-memory during startup: "
            "unable to allocate CPU_REPACK buffer of size 3121348608",
            "llama-server process has terminated: exit status 1: "
            "failed to allocate buffer of size 3121348608",
        )
        for text in bodies:
            error = APIStatusError("opaque", response=response, body={"message": text, "type": "api_error"})
            with self.subTest(text=text[:40]):
                message = str(_friendly_error(error))
                self.assertIn("内存不足", message)
                self.assertIn("llama3.2:1b", message)

    def test_not_found_body_is_surfaced_without_the_sdk_message(self) -> None:
        request = httpx.Request("POST", self.settings.base_url)
        response = httpx.Response(404, request=request)
        with_body = NotFoundError(
            "secret SDK text", response=response,
            body={"error": "model 'qwen2.5' not found, try pulling it first"},
        )
        message = str(_friendly_error(with_body))
        self.assertIn("模型不存在", message)
        self.assertIn("try pulling", message)
        self.assertNotIn("secret SDK text", message)

        without_body = NotFoundError("secret SDK text", response=response, body=None)
        self.assertNotIn("secret SDK text", str(_friendly_error(without_body)))

    def test_connection_errors_distinguish_dns_tls_and_proxy(self) -> None:
        request = httpx.Request("POST", self.settings.base_url)
        dns_error = APIConnectionError(request=request)
        dns_error.__cause__ = socket.gaierror("private dns detail")
        tls_error = APIConnectionError(request=request)

        class TlsError(ssl.SSLError):
            pass

        tls_error.__cause__ = TlsError("private tls detail")
        proxy_error = APIConnectionError(request=request)

        class ProxyError(RuntimeError):
            pass

        proxy_error.__cause__ = ProxyError("private proxy detail")

        self.assertIn("DNS 解析", str(_friendly_error(dns_error)))
        self.assertIn("TLS", str(_friendly_error(tls_error)))
        self.assertIn("代理连接失败", str(_friendly_error(proxy_error)))

    def test_model_suggestions_use_stable_ids_and_enter_safe_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "课程资料.txt").write_text("local-only body", encoding="utf-8")
            source = scan_files(root)[0]
            transport = AIFakeTransport("auto")
            with patch("filemind.ai.openai_compatible.OpenAI", return_value=transport):
                client = OpenAICompatibleClient(self.settings)
                ai_result = client.organize_files([file_metadata(source)], "按课程章节整理", True)
            plan = build_plan(root, [source], classify_file, ai_result.suggestions, True)
            operation = plan.operations[0]

            self.assertEqual(operation.classification.source, "AI")
            self.assertEqual(operation.target, root / "学习资料" / "数据结构" / "第1章" / "链表复习.txt")
            self.assertEqual(operation.new_name, "链表复习.txt")
            self.assertNotIn(str(root), str(transport.calls[0]))
            self.assertNotIn("local-only body", str(transport.calls[0]))

    def test_ai_plan_reports_destination_collision_without_overwriting(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "notes.txt"
            source.write_text("source", encoding="utf-8")
            target = root / "文档" / "notes.txt"
            target.parent.mkdir()
            target.write_text("keep", encoding="utf-8")
            file_info = scan_files(root)[0]
            suggestion = {file_metadata(file_info).file_id: _suggestion(file_info, "文档", "")}

            plan = build_plan(root, [file_info], classify_file, suggestion, True)

            self.assertIn("已存在同名文件", plan.operations[0].warning or "")
            self.assertEqual(target.read_text(encoding="utf-8"), "keep")

    def test_bad_subdirectory_and_renamed_suffix_are_rejected(self) -> None:
        source = _file("课件.pdf")
        file_id = file_metadata(source).file_id
        base = {"file_id": file_id, "category": "学习", "target_subdirectory": "", "new_name": "课件.pdf",
                "reason": "课程资料"}
        bad_path = dict(base, target_subdirectory="../外部")
        bad_suffix = dict(base, new_name="课件.txt")
        for item in (bad_path, bad_suffix):
            with self.subTest(item=item):
                suggestions, failures = parse_file_suggestions(
                    json.dumps({"suggestions": [item]}, ensure_ascii=False), {file_id: source}, True)
                # Unsafe rows are isolated to local rules instead of being adopted.
                self.assertEqual(suggestions, {})
                self.assertIn(file_id, failures)

    def test_null_name_keeps_original_when_rename_is_not_requested(self) -> None:
        source = _file("原始名称.tar.gz")
        file_id = file_metadata(source).file_id
        item = {"file_id": file_id, "category": "压缩包", "target_subdirectory": "", "new_name": None,
                "reason": "不确定文件主题"}
        suggestions, failures = parse_file_suggestions(
            json.dumps({"suggestions": [item]}, ensure_ascii=False), {file_id: source}, False)
        self.assertEqual(suggestions[file_id].new_name, "")
        self.assertEqual(failures, {})

    def test_missing_duplicate_and_unknown_file_ids_keep_other_rows(self) -> None:
        first = _file("a.txt")
        second = _file("b.txt")
        first_id = file_metadata(first).file_id
        second_id = file_metadata(second).file_id
        good = {"file_id": first_id, "category": "文档", "target_subdirectory": "", "new_name": None,
                "reason": "文本资料"}
        cases = (
            [good],
            [good, good],
            [good, dict(good, file_id="f_unknown")],
        )
        expected = {first_id: first, second_id: second}
        for items in cases:
            with self.subTest(items=items):
                suggestions, failures = parse_file_suggestions(
                    json.dumps({"suggestions": items}, ensure_ascii=False), expected, False)
                # The valid first row is kept; only the missing/duplicate/unknown
                # file falls back to local rules instead of failing the batch.
                self.assertIn(first_id, suggestions)
                self.assertIn(second_id, failures)


def _file(name: str) -> FileInfo:
    return FileInfo(Path(name), 12, 123456)


def _suggestion(file_info: FileInfo, category: str, subdirectory: str) -> FileSuggestion:
    return FileSuggestion(file_info.name, category, file_info.name, "本地测试建议",
                          file_metadata(file_info).file_id, subdirectory)


if __name__ == "__main__":
    unittest.main()
