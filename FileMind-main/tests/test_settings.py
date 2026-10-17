"""Persistence, precedence, and provider-switch tests with temporary files."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from filemind.storage.settings import AISettings, SettingsError, SettingsStore


class MemorySecretStore:
    def __init__(self):
        self.values: dict[str, str] = {}

    def get(self, target: str) -> str | None:
        return self.values.get(target)

    def set(self, target: str, value: str) -> None:
        self.values[target] = value

    def delete(self, target: str) -> None:
        self.values.pop(target, None)


class SettingsStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.secret_store = MemorySecretStore()
        self.store = SettingsStore(self.root / "settings.json", self.root, self.secret_store)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_configuration_and_secret_survive_reload_without_plaintext_json(self) -> None:
        settings = AISettings("deepseek", "https://api.deepseek.com", "deepseek-flash", 35, "secret-value")
        self.store.save(settings, online_ai_consent=True)
        loaded = SettingsStore(self.root / "settings.json", self.root, self.secret_store).load()

        self.assertEqual(loaded.provider_id, settings.provider_id)
        self.assertEqual(loaded.base_url, settings.base_url)
        self.assertEqual(loaded.model, settings.model)
        self.assertEqual(loaded.timeout_seconds, settings.timeout_seconds)
        self.assertEqual(loaded.api_key, settings.api_key)
        self.assertEqual(loaded.api_key_source, "Windows 凭据管理器")
        self.assertNotIn("secret-value", (self.root / "settings.json").read_text(encoding="utf-8"))
        self.assertTrue(self.store.has_online_ai_consent())

    def test_first_run_selects_official_deepseek_defaults_without_a_key(self) -> None:
        settings = self.store.load()

        self.assertEqual(settings.provider_id, "deepseek")
        self.assertEqual(settings.base_url, "https://api.deepseek.com")
        self.assertEqual(settings.model, "deepseek-flash")
        self.assertEqual(settings.api_key, "")
        self.assertEqual(settings.api_key_source, "未配置")

    def test_restart_keeps_user_selected_provider_and_model(self) -> None:
        selected = AISettings("openai", "https://example.test/v1", "account-model", 30, "user-key")
        self.store.save(selected)

        loaded = SettingsStore(self.root / "settings.json", self.root, self.secret_store).load()

        self.assertEqual((loaded.provider_id, loaded.base_url, loaded.model),
                         ("openai", "https://example.test/v1", "account-model"))
        self.assertEqual(loaded.api_key, "user-key")

    def test_orbit_privacy_consent_is_persisted_per_provider(self) -> None:
        self.store.set_chat_ai_consent("deepseek", True)
        reloaded = SettingsStore(self.root / "settings.json", self.root, self.secret_store)

        self.assertTrue(reloaded.has_chat_ai_consent("deepseek"))
        self.assertFalse(reloaded.has_chat_ai_consent("openai"))

    def test_orbit_privacy_consent_rejects_unknown_provider(self) -> None:
        with self.assertRaisesRegex(SettingsError, "未知的 AI 服务商"):
            self.store.set_chat_ai_consent("unknown", True)

    def test_provider_profiles_keep_independent_values(self) -> None:
        self.store.save(AISettings("deepseek", "https://custom.example/v1", "my-deepseek", 30, "key-one"))
        self.store.save(AISettings("openai", "https://api.openai.com/v1", "gpt-5-mini", 60, "key-two"))

        deepseek = self.store.load("deepseek")
        openai = self.store.load()

        self.assertEqual((deepseek.model, deepseek.api_key), ("my-deepseek", "key-one"))
        self.assertEqual((openai.provider_id, openai.model, openai.api_key), ("openai", "gpt-5-mini", "key-two"))

    def test_saved_credential_precedes_environment_and_legacy_env_keys(self) -> None:
        (self.root / ".env").write_text("DEEPSEEK_API_KEY=legacy-key\n", encoding="utf-8")
        self.store.save(AISettings("deepseek", "https://api.deepseek.com", "m", 45, "saved-key"))
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "environment-key"}):
            self.assertEqual(self.store.load().api_key, "saved-key")

    def test_legacy_env_is_deepseek_only_and_is_final_fallback(self) -> None:
        (self.root / ".env").write_text("DEEPSEEK_API_KEY=legacy-key\n", encoding="utf-8")
        self.assertEqual(self.store.load("deepseek").api_key, "legacy-key")
        self.assertEqual(self.store.load("openai").api_key, "")

    def test_user_opted_local_secret_storage_is_separate_from_settings(self) -> None:
        settings = AISettings("custom", "http://localhost:1234/v1", "local-model", 45,
                              "local-secret", store_key_locally=True)
        with patch("filemind.storage.settings._restrict_permissions") as restrict:
            self.store.save(settings)

        secret_file = self.root / "local_api_keys.json"
        self.assertTrue(secret_file.exists())
        self.assertEqual(json.loads(secret_file.read_text(encoding="utf-8"))["custom"], "local-secret")
        self.assertNotIn("local-secret", (self.root / "settings.json").read_text(encoding="utf-8"))
        restrict.assert_called()

    def test_credential_read_failure_is_not_misreported_as_missing_key(self) -> None:
        class BrokenSecretStore(MemorySecretStore):
            def get(self, target: str) -> str | None:
                raise OSError("credential store unavailable")

        store = SettingsStore(self.root / "settings.json", self.root, BrokenSecretStore())
        with self.assertRaisesRegex(SettingsError, "无法读取系统凭据存储"):
            store.load()


if __name__ == "__main__":
    unittest.main()
