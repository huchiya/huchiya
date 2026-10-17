"""Persistent provider settings with OS-backed API-key protection."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol, Sequence

from filemind.ai.model_config import ModelConfig
from filemind.ai.providers import ENVIRONMENT_KEY_NAMES, PROVIDER_BY_ID
from filemind.storage.paths import config_dir


class SecretStore(Protocol):
    """Small interface over the operating-system credential store."""

    def get(self, target: str) -> str | None: ...
    def set(self, target: str, value: str) -> None: ...
    def delete(self, target: str) -> None: ...


@dataclass(frozen=True)
class AISettings:
    """One provider profile loaded for an API operation."""

    provider_id: str
    base_url: str
    model: str
    timeout_seconds: int
    api_key: str = ""
    store_key_locally: bool = False
    api_key_source: str = "未配置"
    local: bool = False
    model_options: tuple[str, ...] = ()


class SettingsError(RuntimeError):
    """Safe configuration persistence error suitable for the settings page."""


class SettingsStore:
    """Store ordinary settings as JSON and secrets in Windows Credential Manager."""

    def __init__(self, settings_path: Path | None = None, project_root: Path | None = None,
                 secret_store: SecretStore | None = None):
        self.settings_path = settings_path or _default_settings_path()
        self.local_secrets_path = self.settings_path.with_name("local_api_keys.json")
        self.project_root = project_root or Path(__file__).resolve().parents[2]
        self.secret_store = secret_store if secret_store is not None else _default_secret_store()

    def load(self, provider_id: str | None = None) -> AISettings:
        """Load saved provider values with explicit secret-source precedence."""
        payload = self._read_settings()
        active_id = provider_id or str(payload.get("active_provider", "deepseek"))
        if active_id not in PROVIDER_BY_ID:
            active_id = "custom"
        preset = PROVIDER_BY_ID[active_id]
        profiles = payload.get("profiles", {})
        profile = profiles.get(active_id, {}) if isinstance(profiles, dict) else {}
        if not isinstance(profile, dict):
            profile = {}
        settings = AISettings(
            provider_id=active_id,
            base_url=str(profile.get("base_url", preset.base_url)),
            model=str(profile.get("model", preset.model)),
            timeout_seconds=_valid_timeout(profile.get("timeout_seconds", 45)),
            store_key_locally=bool(profile.get("store_key_locally", False)),
            local=preset.local,
            model_options=_string_tuple(profile.get("model_options")),
        )
        api_key, source = self._load_secret(settings)
        return AISettings(**{**asdict(settings), "api_key": api_key, "api_key_source": source})

    def save(self, settings: AISettings, online_ai_consent: bool | None = None) -> None:
        """Persist one provider profile and its API key using the selected backend."""
        if settings.provider_id not in PROVIDER_BY_ID:
            raise SettingsError("未知的 AI 服务商配置。")
        payload = self._read_settings()
        profiles = payload.setdefault("profiles", {})
        if not isinstance(profiles, dict):
            raise SettingsError("本地设置文件格式无效。")
        profiles[settings.provider_id] = {
            "base_url": settings.base_url.strip(), "model": settings.model.strip(),
            "timeout_seconds": _valid_timeout(settings.timeout_seconds),
            "store_key_locally": settings.store_key_locally,
        }
        if settings.model_options:
            profiles[settings.provider_id]["model_options"] = list(dict.fromkeys(settings.model_options))
        payload["active_provider"] = settings.provider_id
        if online_ai_consent is not None:
            payload["online_ai_consent"] = online_ai_consent
        if settings.local:
            # 本地模型不使用密钥，也无需清理占位密钥。
            self._atomic_write(self.settings_path, payload)
            return
        if settings.api_key.strip():
            self._save_secret(settings)
        else:
            self._delete_secret(settings.provider_id)
        self._atomic_write(self.settings_path, payload)

    def has_online_ai_consent(self) -> bool:
        """Return whether the user already accepted metadata disclosure."""
        return bool(self._read_settings().get("online_ai_consent", False))

    def set_online_ai_consent(self, accepted: bool) -> None:
        """Persist the user's explicit first-use metadata disclosure choice."""
        payload = self._read_settings()
        payload["online_ai_consent"] = accepted
        self._atomic_write(self.settings_path, payload)

    def has_chat_ai_consent(self, provider_id: str) -> bool:
        """Return whether the user accepted sending chat turns to this provider."""
        if provider_id not in PROVIDER_BY_ID:
            raise SettingsError("未知的 AI 服务商配置。")
        consents = self._read_settings().get("chat_ai_consents", {})
        return bool(isinstance(consents, dict) and consents.get(provider_id, False))

    def set_chat_ai_consent(self, provider_id: str, accepted: bool) -> None:
        """Persist provider-scoped Orbit consent separately from file AI."""
        if provider_id not in PROVIDER_BY_ID:
            raise SettingsError("未知的 AI 服务商配置。")
        payload = self._read_settings()
        consents = payload.setdefault("chat_ai_consents", {})
        if not isinstance(consents, dict):
            raise SettingsError("本地隐私设置格式无效。")
        consents[provider_id] = accepted
        self._atomic_write(self.settings_path, payload)

    def save_model_options(self, provider_id: str, models: Sequence[str]) -> None:
        """Persist only the detected model list for a provider without touching secrets."""
        if provider_id not in PROVIDER_BY_ID:
            raise SettingsError("未知的 AI 服务商配置。")
        payload = self._read_settings()
        profiles = payload.setdefault("profiles", {})
        if not isinstance(profiles, dict):
            raise SettingsError("本地设置文件格式无效。")
        profile = profiles.setdefault(provider_id, {})
        if not isinstance(profile, dict):
            raise SettingsError("本地设置文件格式无效。")
        cleaned = [str(model).strip() for model in models if str(model).strip()]
        if cleaned:
            profile["model_options"] = list(dict.fromkeys(cleaned))
        else:
            profile.pop("model_options", None)
        self._atomic_write(self.settings_path, payload)

    def set_active_model(self, provider_id: str, model_name: str) -> None:
        """Switch the active model for a provider without touching its secret source."""
        if provider_id not in PROVIDER_BY_ID:
            raise SettingsError("未知的 AI 服务商配置。")
        model_name = model_name.strip()
        if not model_name:
            raise SettingsError("模型名称不能为空。")
        payload = self._read_settings()
        profiles = payload.setdefault("profiles", {})
        if not isinstance(profiles, dict):
            raise SettingsError("本地设置文件格式无效。")
        profile = profiles.setdefault(provider_id, {})
        if not isinstance(profile, dict):
            raise SettingsError("本地设置文件格式无效。")
        profile["model"] = model_name
        payload["active_provider"] = provider_id
        self._atomic_write(self.settings_path, payload)

    def load_models(self) -> list[ModelConfig]:
        """Return the ordered multi-model selection with runtime keys resolved.

        Falls back to a single entry derived from the active provider profile so
        existing installations keep working after the multi-model upgrade.
        """
        payload = self._read_settings()
        raw_models = payload.get("models")
        if isinstance(raw_models, list):
            configs = [config for item in raw_models
                       if (config := ModelConfig.from_dict(item)) is not None]
            if configs:
                return [self._with_resolved_key(config) for config in configs]
        settings = self.load()
        return [self._with_resolved_key(ModelConfig(
            provider=settings.provider_id, model=settings.model, base_url=settings.base_url,
            api_key_env=ENVIRONMENT_KEY_NAMES.get(settings.provider_id, ""),
            timeout_seconds=settings.timeout_seconds, api_key=settings.api_key))]

    def save_models(self, models: Sequence[ModelConfig]) -> None:
        """Persist the ordered selection and enabled flags; keys are never written."""
        payload = self._read_settings()
        payload["models"] = [config.to_dict() for config in models]
        self._atomic_write(self.settings_path, payload)

    def is_parallel_mode_enabled(self) -> bool:
        """Return whether Orbit should fan a message out to every enabled model."""
        return bool(self._read_settings().get("parallel_models", False))

    def set_parallel_mode(self, enabled: bool) -> None:
        """Persist the opt-in parallel Orbit mode."""
        payload = self._read_settings()
        payload["parallel_models"] = bool(enabled)
        self._atomic_write(self.settings_path, payload)

    def get_appearance(self) -> str:
        """Return the stored appearance id (default keeps the original light theme)."""
        value = self._read_settings().get("appearance", "light")
        return value if isinstance(value, str) and value else "light"

    def set_appearance(self, appearance: str) -> None:
        """Persist the selected appearance (light/dark/system/green/orange)."""
        payload = self._read_settings()
        payload["appearance"] = str(appearance)
        self._atomic_write(self.settings_path, payload)

    def _with_resolved_key(self, config: ModelConfig) -> ModelConfig:
        """Resolve a key from an explicit env name, then the normal precedence."""
        if config.api_key:
            return config
        if config.api_key_env:
            value = os.environ.get(config.api_key_env, "").strip()
            if value:
                return config.with_api_key(value)
        try:
            return config.with_api_key(self.load(config.provider).api_key)
        except (SettingsError, OSError, ValueError):
            return config

    def _load_secret(self, settings: AISettings) -> tuple[str, str]:
        if settings.local:
            return "", "本机模型无需密钥"
        if self.secret_store:
            try:
                saved_value = self.secret_store.get(_credential_target(settings.provider_id))
            except OSError as error:
                raise SettingsError("无法读取系统凭据存储中的 API Key；请检查 Windows 凭据管理器或重新保存密钥。") from error
            if saved_value:
                return saved_value, "Windows 凭据管理器"
        local_secret = self._read_local_secret(settings.provider_id) if settings.store_key_locally else ""
        if local_secret:
            return local_secret, "本地明文配置文件"
        environment_value = os.environ.get(ENVIRONMENT_KEY_NAMES.get(settings.provider_id, ""), "").strip()
        if not environment_value and settings.provider_id == "deepseek":
            environment_value = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        if environment_value:
            return environment_value, "环境变量"
        legacy_value = self._legacy_env_key(settings.provider_id)
        return (legacy_value, "旧版 .env 文件") if legacy_value else ("", "未配置")

    def _save_secret(self, settings: AISettings) -> None:
        if settings.store_key_locally:
            payload = self._read_local_secrets()
            payload[settings.provider_id] = settings.api_key.strip()
            self._atomic_write(self.local_secrets_path, payload, restrict_permissions=True)
            if self.secret_store:
                self.secret_store.delete(_credential_target(settings.provider_id))
            return
        if not self.secret_store:
            raise SettingsError("此系统没有可用的安全凭据存储；如接受明文风险，请勾选本地保存选项。")
        try:
            self.secret_store.set(_credential_target(settings.provider_id), settings.api_key.strip())
            self._remove_local_secret(settings.provider_id)
        except OSError as error:
            raise SettingsError("无法写入系统凭据存储；可选择本机明文配置文件保存。") from error

    def _delete_secret(self, provider_id: str) -> None:
        if self.secret_store:
            self.secret_store.delete(_credential_target(provider_id))
        self._remove_local_secret(provider_id)

    def _legacy_env_key(self, provider_id: str) -> str:
        """Read only the historical DeepSeek variable as the final fallback."""
        if provider_id != "deepseek":
            return ""
        try:
            lines = (self.project_root / ".env").read_text(encoding="utf-8").splitlines()
        except OSError:
            return ""
        for line in lines:
            key, separator, value = line.partition("=")
            if separator and key.strip() == "DEEPSEEK_API_KEY":
                return value.strip().strip("\"'")
        return ""

    def _read_settings(self) -> dict[str, object]:
        try:
            payload = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {"active_provider": "deepseek", "profiles": {}}
        except (OSError, json.JSONDecodeError) as error:
            raise SettingsError("本地设置文件无法读取，请检查文件格式或权限。") from error
        if not isinstance(payload, dict) or not isinstance(payload.get("profiles", {}), dict):
            raise SettingsError("本地设置文件格式无效。")
        return payload

    def _read_local_secrets(self) -> dict[str, str]:
        try:
            payload = json.loads(self.local_secrets_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, json.JSONDecodeError) as error:
            raise SettingsError("本地密钥文件无法读取，请检查权限。") from error
        return payload if isinstance(payload, dict) else {}

    def _read_local_secret(self, provider_id: str) -> str:
        return str(self._read_local_secrets().get(provider_id, ""))

    def _remove_local_secret(self, provider_id: str) -> None:
        payload = self._read_local_secrets()
        if provider_id in payload:
            del payload[provider_id]
            self._atomic_write(self.local_secrets_path, payload, restrict_permissions=True)

    @staticmethod
    def _atomic_write(path: Path, payload: dict[str, object], restrict_permissions: bool = False) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary_name = tempfile.mkstemp(prefix=".filemind-", suffix=".tmp", dir=path.parent)
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as output:
                json.dump(payload, output, ensure_ascii=False, indent=2)
                output.flush()
                os.fsync(output.fileno())
            if restrict_permissions:
                _restrict_permissions(temporary_path)
            os.replace(temporary_path, path)
            if restrict_permissions:
                _restrict_permissions(path)
        finally:
            temporary_path.unlink(missing_ok=True)


def _default_settings_path() -> Path:
    """Use the current user's configuration directory, never the repository."""
    return config_dir() / "settings.json"


def _default_secret_store() -> SecretStore | None:
    if os.name != "nt":
        return None
    from filemind.storage.windows_credentials import WindowsCredentialStore

    try:
        return WindowsCredentialStore()
    except OSError:
        return None


def _credential_target(provider_id: str) -> str:
    return f"FileMind/{provider_id}/api-key"


def _valid_timeout(value: object) -> int:
    try:
        timeout = int(value)
    except (TypeError, ValueError):
        return 45
    return min(max(timeout, 5), 180)


def _string_tuple(value: object) -> tuple[str, ...]:
    """Read a persisted list/sequence of strings as a de-duplicated tuple."""
    if not isinstance(value, (list, tuple)):
        return ()
    seen: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip() and item.strip() not in seen:
            seen.append(item.strip())
    return tuple(seen)


def _restrict_permissions(path: Path) -> None:
    """Restrict opt-in plaintext backup to the current user or POSIX mode 0600."""
    if os.name != "nt":
        path.chmod(0o600)
        return
    import getpass
    import shutil
    import subprocess

    icacls = shutil.which("icacls.exe")
    username = f"{os.environ.get('USERDOMAIN', '')}\\{getpass.getuser()}"
    if not icacls:
        raise SettingsError("找不到 Windows icacls，无法限制本地密钥文件权限。")
    result = subprocess.run([icacls, str(path), "/inheritance:r", "/grant:r", f"{username}:(F)"],
                            capture_output=True, check=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if result.returncode:
        raise SettingsError("无法将本地密钥文件权限限制为当前 Windows 用户。")
