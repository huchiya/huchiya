"""Supported OpenAI-compatible provider defaults.

``kind`` selects the chat adapter: ``openai`` reuses the OpenAI SDK (which also
covers Ollama's ``/v1`` compatibility endpoint), ``ollama`` adds the native model
listing, and ``unsupported`` marks a provider that is only a reserved slot until
a native adapter exists. ``requires_key`` documents whether an API key is needed,
and ``local`` marks a provider that runs on this machine and never sends data out.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderPreset:
    """Public default connection values for one chat provider."""

    provider_id: str
    name: str
    base_url: str
    model: str
    note: str
    kind: str = "openai"
    requires_key: bool = True
    api_key_env: str = ""
    local: bool = False


PROVIDERS: tuple[ProviderPreset, ...] = (
    ProviderPreset("deepseek", "DeepSeek", "https://api.deepseek.com", "deepseek-flash",
                   "官方当前通用模型 DeepSeek-V4.1-Flash；模型 ID 为 deepseek-flash，兼容 Chat Completions。",
                   api_key_env="DEEPSEEK_API_KEY"),
    ProviderPreset("openai", "OpenAI", "https://api.openai.com/v1", "gpt-5-mini",
                   "使用 OpenAI Chat Completions；需单独开通 API 计费与权限。",
                   api_key_env="OPENAI_API_KEY"),
    ProviderPreset("siliconflow", "硅基流动 SiliconFlow", "https://api.siliconflow.cn/v1",
                   "deepseek-ai/DeepSeek-V4-Flash", "模型可用性和名称以 SiliconFlow 模型广场为准。",
                   api_key_env="SILICONFLOW_API_KEY"),
    ProviderPreset("dashscope", "阿里云百炼 DashScope", "https://dashscope.aliyuncs.com/compatible-mode/v1",
                   "qwen-plus", "预设北京公共兼容端点；地域、业务空间和模型授权可能影响可用性。",
                   api_key_env="DASHSCOPE_API_KEY"),
    ProviderPreset("zhipu", "智谱清言 ZhipuAI", "https://open.bigmodel.cn/api/paas/v4", "glm-4-flash",
                   "智谱 AI 的 OpenAI 兼容接口；模型 ID 以 glm- 开头，可用性以官方文档为准。",
                   api_key_env="ZHIPU_API_KEY"),
    ProviderPreset("wenxin", "文心一言 ERNIE", "https://qianfan.baidubce.com/v2", "ernie-4.5-turbo-128k",
                   "百度千帆的 OpenAI 兼容接口；模型 ID 以 ernie- 开头。",
                   api_key_env="WENXIN_API_KEY"),
    ProviderPreset("kimi", "Kimi 月之暗面", "https://api.moonshot.cn/v1", "kimi-k2-0711-preview",
                   "Moonshot AI 的 OpenAI 兼容接口；模型 ID 以 kimi-/moonshot- 开头。",
                   api_key_env="MOONSHOT_API_KEY"),
    ProviderPreset("doubao", "豆包 Doubao", "https://ark.cn-beijing.volces.com/api/v3", "doubao-seed-1-6-250615",
                   "火山方舟上的豆包模型，OpenAI 兼容接口；模型 ID 以 doubao- 开头。",
                   api_key_env="DOUBAO_API_KEY"),
    ProviderPreset("volcengine", "火山引擎 Volcano Engine", "https://ark.cn-beijing.volces.com/api/v3",
                   "doubao-1-5-pro-32k-250115", "火山方舟 OpenAI 兼容接口；模型 ID 以 doubao-/deepseek-/qwen- 开头。",
                   api_key_env="VOLCENGINE_API_KEY"),
    ProviderPreset("qwen", "千问 Qwen", "https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-max",
                   "阿里云百炼上的通义千问，OpenAI 兼容接口；模型 ID 以 qwen- 开头。",
                   api_key_env="QWEN_API_KEY"),
    ProviderPreset("hunyuan", "腾讯混元 Hunyuan", "https://api.hunyuan.cloud.tencent.com/v1", "hunyuan-turbos-latest",
                   "腾讯云混元 OpenAI 兼容接口；模型 ID 以 hunyuan- 开头，需在腾讯云开通并配置 API Key。",
                   api_key_env="HUNYUAN_API_KEY"),
    ProviderPreset("ollama", "本地 Ollama", "http://localhost:11434/v1", "llama3.2",
                   "调用本机 Ollama 的 OpenAI 兼容端点。无需 API Key，数据不离开本机；请先安装并启动 Ollama 服务。",
                   kind="ollama", requires_key=False, api_key_env="OLLAMA_API_KEY", local=True),
    ProviderPreset("custom", "自定义 OpenAI 兼容接口", "", "", "仅支持兼容的 Chat Completions 接口。",
                   api_key_env="FILEMIND_API_KEY"),
)

PROVIDER_BY_ID = {provider.provider_id: provider for provider in PROVIDERS}

# 本地 provider 不需要 API Key；发送数据也不会离开本机。
LOCAL_PROVIDER_IDS: frozenset[str] = frozenset(
    provider.provider_id for provider in PROVIDERS if provider.local
)
REMOTE_PROVIDER_IDS: frozenset[str] = frozenset(
    provider.provider_id for provider in PROVIDERS if not provider.local
)

ENVIRONMENT_KEY_NAMES = {provider.provider_id: provider.api_key_env for provider in PROVIDERS if provider.api_key_env}

# 每个服务商可下拉选择的建议模型 ID；仅供参考，实际可用模型以服务商目录为准。
# Ollama 的列表还会被本机 /api/tags 探测结果扩充。
PROVIDER_MODEL_SUGGESTIONS: dict[str, tuple[str, ...]] = {
    "deepseek": ("deepseek-flash", "deepseek-chat", "deepseek-reasoner"),
    "openai": ("gpt-5-mini", "gpt-4o", "gpt-4o-mini", "o3-mini"),
    "siliconflow": ("deepseek-ai/DeepSeek-V4-Flash", "deepseek-ai/DeepSeek-V3.2",
                    "Qwen/Qwen2.5-72B-Instruct", "Qwen/QwQ-32B"),
    "dashscope": ("qwen-plus", "qwen-max", "qwen-turbo", "qwen3"),
    "zhipu": ("glm-4-flash", "glm-4-air", "glm-4-plus", "glm-4.5", "glm-4.5-air"),
    "wenxin": ("ernie-4.5-turbo-128k", "ernie-4.5-8k-preview", "ernie-4.0-turbo-8k", "ernie-3.5-8k"),
    "kimi": ("kimi-k2-0711-preview", "moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"),
    "doubao": ("doubao-seed-1-6-250615", "doubao-1-5-pro-32k-250115", "doubao-1-5-lite-32k-250115"),
    "volcengine": ("doubao-seed-1-6-250615", "doubao-1-5-pro-32k-250115", "deepseek-v3-241226", "qwen3-32b"),
    "qwen": ("qwen-max", "qwen-plus", "qwen-turbo", "qwen3-max", "qwen3-235b-a22b"),
    "hunyuan": ("hunyuan-turbos-latest", "hunyuan-turbo", "hunyuan-standard"),
    "ollama": (),
    "custom": (),
}
