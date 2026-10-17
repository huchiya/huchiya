"""Offscreen tests for the reference model-configuration UI and navigation."""

import os
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

from filemind.ai.providers import PROVIDER_BY_ID
from filemind.storage.settings import SettingsStore
from filemind.ui.main_window import NAVIGATION_ITEMS
from filemind.ui.pages.settings_page import SettingsPage


class _MemorySecretStore:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def get(self, target: str) -> str | None:
        return self.values.get(target)

    def set(self, target: str, value: str) -> None:
        self.values[target] = value

    def delete(self, target: str) -> None:
        self.values.pop(target, None)


def _page() -> SettingsPage:
    temporary = tempfile.TemporaryDirectory()
    root = Path(temporary.name)
    page = SettingsPage(SettingsStore(root / "settings.json", root, _MemorySecretStore()))
    page._temporary = temporary  # keep the directory alive for the whole test
    return page


def test_provider_combo_lists_all_supported_providers() -> None:
    page = _page()
    ids = [page.provider_combo.itemData(index) for index in range(page.provider_combo.count())]
    assert ids == ["deepseek", "openai", "siliconflow", "dashscope", "zhipu", "wenxin",
                   "kimi", "doubao", "volcengine", "qwen", "hunyuan", "ollama", "custom"]
    assert {"anthropic", "google"}.isdisjoint(ids)
    page.deleteLater()


def test_model_combo_is_populated_with_suggestions() -> None:
    page = _page()
    texts = [page.model_combo.itemText(index) for index in range(page.model_combo.count())]
    assert "deepseek-flash" in texts and "deepseek-reasoner" in texts
    assert page.model_combo.currentText() == PROVIDER_BY_ID["deepseek"].model
    page.deleteLater()


def test_ollama_hides_key_fields_and_enables_test_without_a_key() -> None:
    page = _page()
    assert not page.secret_container.isHidden()
    assert page.detect_ollama_button.isHidden()

    page.provider_combo.setCurrentIndex(page.provider_combo.findData("ollama"))

    assert page.secret_container.isHidden()
    assert page.local_key_checkbox.isHidden()
    assert not page.detect_ollama_button.isHidden()
    assert page.test_button.isEnabled()
    page.deleteLater()


def test_ollama_models_fill_the_combo_and_mark_dirty() -> None:
    page = _page()
    page.provider_combo.setCurrentIndex(page.provider_combo.findData("ollama"))

    page.set_ollama_models(["llama3.2", "qwen2.5:7b"], None)

    texts = [page.model_combo.itemText(index) for index in range(page.model_combo.count())]
    assert "llama3.2" in texts and "qwen2.5:7b" in texts
    assert page.has_unsaved_changes
    page.set_ollama_models([], "无法连接本机 Ollama 服务")
    assert "无法连接" in page.status_label.text()
    assert page.detect_ollama_button.isEnabled()
    page.deleteLater()


def test_saving_ollama_profile_persists_without_a_key() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        store = SettingsStore(root / "settings.json", root, _MemorySecretStore())
        page = SettingsPage(store)
        page.provider_combo.setCurrentIndex(page.provider_combo.findData("ollama"))

        assert page.save_current() is True

        reloaded = SettingsStore(root / "settings.json", root, _MemorySecretStore()).load("ollama")
        assert reloaded.local is True
        assert reloaded.api_key == ""
        assert reloaded.api_key_source == "本机模型无需密钥"
        assert reloaded.model == "llama3.2"
        page.deleteLater()


def test_sidebar_renames_settings_entry_to_model_configuration() -> None:
    labels = {key: title for key, title, _icon, _title, _subtitle in NAVIGATION_ITEMS}
    assert labels["settings"] == "模型配置"
