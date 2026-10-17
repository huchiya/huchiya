"""Unified adapter tests: preset defaults, Ollama listing, and row-level errors."""

import unittest
from unittest.mock import Mock, patch

from filemind.ai.adapters import (OllamaProvider, OpenAIProvider, _ollama_root,
                                  build_provider, resolve_config, safe_error_message)
from filemind.ai.adapters import _fetch_ollama_tags
from filemind.ai.openai_compatible import AIServiceError
from filemind.ai.model_config import ModelConfig
from filemind.ai.providers import PROVIDER_BY_ID, ProviderPreset


class ResolveConfigTests(unittest.TestCase):
    def test_ollama_fills_default_base_url_and_placeholder_key(self) -> None:
        resolved = resolve_config(ModelConfig("ollama", "llama3.2"))
        self.assertEqual(resolved.base_url, "http://localhost:11434/v1")
        self.assertEqual(resolved.api_key, "ollama")

    def test_configured_values_are_kept(self) -> None:
        resolved = resolve_config(ModelConfig("deepseek", "deepseek-flash",
                                              base_url="https://proxy.example/v1", api_key="k"))
        self.assertEqual((resolved.base_url, resolved.api_key), ("https://proxy.example/v1", "k"))

    def test_ollama_root_strips_trailing_v1(self) -> None:
        for value, expected in (("http://localhost:11434/v1", "http://localhost:11434"),
                                ("http://localhost:11434/", "http://localhost:11434"),
                                ("", "http://localhost:11434")):
            with self.subTest(value=value):
                self.assertEqual(_ollama_root(value), expected)


class BuildProviderTests(unittest.TestCase):
    def test_kind_selects_the_matching_adapter(self) -> None:
        with patch("filemind.ai.adapters.OpenAICompatibleClient"):
            self.assertIsInstance(build_provider(ModelConfig("ollama", "m")), OllamaProvider)
            self.assertIsInstance(build_provider(ModelConfig("deepseek", "m", api_key="k")), OpenAIProvider)

    def test_unsupported_preset_raises_a_clear_error(self) -> None:
        preset = ProviderPreset("anthropic", "Anthropic", "https://api.anthropic.com/v1",
                                "claude", "预留插槽。", kind="unsupported")
        with self.assertRaisesRegex(AIServiceError, "暂未接入"):
            build_provider(ModelConfig("anthropic", "m", api_key="k"), preset)

    def test_retired_reserved_slots_are_no_longer_presets(self) -> None:
        self.assertTrue({"anthropic", "google"}.isdisjoint(PROVIDER_BY_ID))


class OpenAIProviderChatTests(unittest.TestCase):
    def _provider(self, client: Mock) -> OpenAIProvider:
        with patch("filemind.ai.adapters.OpenAICompatibleClient", return_value=client):
            return OpenAIProvider(ModelConfig("deepseek", "deepseek-flash", api_key="k"))

    def test_chat_wraps_content_and_latency(self) -> None:
        client = Mock()
        client.complete.return_value = "答案"
        result = self._provider(client).chat([{"role": "user", "content": "hi"}])

        self.assertEqual(result.content, "答案")
        self.assertIsNone(result.error)
        self.assertGreaterEqual(result.latency_ms, 0)
        self.assertEqual(result.to_dict()["provider"], "deepseek")
        client.complete.assert_called_once()

    def test_system_option_is_prepended(self) -> None:
        client = Mock()
        client.complete.return_value = "ok"
        self._provider(client).chat([{"role": "user", "content": "hi"}], {"system": "S"})
        self.assertEqual(client.complete.call_args.args[0][0], {"role": "system", "content": "S"})

    def test_provider_error_becomes_a_row_error_without_leaking_the_key(self) -> None:
        client = Mock()
        client.complete.side_effect = AIServiceError("API Key 无效或无权访问此服务。")
        result = self._provider(client).chat([{"role": "user", "content": "hi"}])

        self.assertFalse(result.ok)
        self.assertIn("API Key 无效", result.error)
        self.assertNotIn("k", result.error)

    def test_unexpected_error_is_replaced_with_a_generic_message(self) -> None:
        client = Mock()
        client.complete.side_effect = RuntimeError("internal boom with secret")
        result = self._provider(client).chat([{"role": "user", "content": "hi"}])

        self.assertIn("模型调用失败", result.error)
        self.assertNotIn("boom", result.error)

    def test_stream_delegates_to_the_client(self) -> None:
        client = Mock()
        client.stream.return_value = iter(["a", "b"])
        chunks = list(self._provider(client).chat_stream([{"role": "user", "content": "x"}]))
        self.assertEqual(chunks, ["a", "b"])


class OllamaListingTests(unittest.TestCase):
    def _provider(self) -> OllamaProvider:
        with patch("filemind.ai.adapters.OpenAICompatibleClient"):
            return OllamaProvider(ModelConfig("ollama", "qwen2.5:7b"))

    def test_list_models_parses_native_tags(self) -> None:
        provider = self._provider()
        payload = {"models": [{"name": "llama3.2:latest"}, {"name": "qwen2.5:7b"}, {"size": 1}]}
        with patch("filemind.ai.adapters._fetch_ollama_tags", return_value=payload) as fetch:
            self.assertEqual(provider.list_models(), ["llama3.2", "qwen2.5:7b"])
        self.assertIn("/api/tags", fetch.call_args.args[0])
        self.assertIn("localhost:11434", fetch.call_args.args[0])

    def test_list_models_returns_friendly_error_when_ollama_is_down(self) -> None:
        provider = self._provider()
        with patch("filemind.ai.adapters._fetch_ollama_tags", side_effect=OSError("connection refused")):
            with self.assertRaisesRegex(AIServiceError, "ollama serve"):
                provider.list_models()

    def test_tags_are_decoded_as_json(self) -> None:
        class _Response:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self) -> bytes:
                return b'{"models": [{"name": "tiny"}]}'

        with patch("filemind.ai.adapters.urllib.request.urlopen", return_value=_Response()):
            self.assertEqual(_fetch_ollama_tags("http://localhost:11434/api/tags", 5),
                             {"models": [{"name": "tiny"}]})


class SafeErrorMessageTests(unittest.TestCase):
    def test_known_errors_are_shown_verbatim_and_others_are_generic(self) -> None:
        self.assertEqual(safe_error_message(AIServiceError("明确错误")), "明确错误")
        self.assertEqual(safe_error_message(ValueError("校验失败")), "校验失败")
        self.assertEqual(safe_error_message(RuntimeError("secret")), "模型调用失败，请检查配置后重试。")


if __name__ == "__main__":
    unittest.main()
