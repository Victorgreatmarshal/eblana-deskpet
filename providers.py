"""
服务商预设。全部通过 OpenAI 兼容接口（/chat/completions、流式输出、工具调用）接入。

模型名称更新很快，预设里的只是默认值；设置里的「获取列表」会向服务商实时拉取可用模型。
新增服务商：在 PROVIDER_LIST 里加一项即可。
"""
from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class Provider:
    id: str
    name: str
    group: str                       # 设置里的分组：国内 / 国际 / 聚合与本地
    base_url: str
    model: str                       # 默认模型
    models: Tuple[str, ...] = ()     # 备选模型（获取列表失败时使用）
    key_url: str = ""                # 「获取 API Key」链接
    needs_key: bool = True
    headers: Dict[str, str] = field(default_factory=dict)  # 额外请求头，{key} 会替换为 API Key
    note: str = ""                   # 设置里模型下方的提示


PROVIDER_LIST: List[Provider] = [
    # ── 国内 ──
    Provider(
        "deepseek", "DeepSeek", "国内", "https://api.deepseek.com", "deepseek-chat",
        ("deepseek-chat", "deepseek-reasoner"),
        "https://platform.deepseek.com/api_keys",
        note="deepseek-chat 支持工具调用，推荐使用。",
    ),
    Provider(
        "qwen", "通义千问 Qwen（阿里云百炼）", "国内", "https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-plus",
        ("qwen-plus", "qwen-max", "qwen-flash", "qwen-turbo"),
        "https://bailian.console.aliyun.com/",
        note="qwen-plus、qwen-max 等别名会自动指向最新版本。",
    ),
    Provider(
        "kimi", "Kimi（月之暗面）", "国内", "https://api.moonshot.cn/v1", "kimi-latest",
        ("kimi-latest",),
        "https://platform.moonshot.cn/console/api-keys",
        note="可点「获取列表」选择 K3 等最新模型。",
    ),
    Provider(
        "glm", "智谱 GLM", "国内", "https://open.bigmodel.cn/api/paas/v4", "glm-5.3",
        ("glm-5.3", "glm-5.3-flash"),
        "https://open.bigmodel.cn/usercenter/apikeys",
    ),
    Provider(
        "siliconflow", "硅基流动 SiliconFlow", "国内", "https://api.siliconflow.cn/v1", "",
        (),
        "https://cloud.siliconflow.cn/account/ak",
        note="填好 Key 后点「获取列表」，选一个支持工具调用的模型。",
    ),
    # ── 国际 ──
    Provider(
        "gemini", "Google Gemini", "国际", "https://generativelanguage.googleapis.com/v1beta/openai", "gemini-flash-latest",
        ("gemini-flash-latest", "gemini-pro-latest", "gemini-flash-lite-latest"),
        "https://aistudio.google.com/apikey",
        note="*-latest 别名会自动指向最新的 Gemini 版本。",
    ),
    Provider(
        "anthropic", "Anthropic Claude", "国际", "https://api.anthropic.com/v1", "claude-sonnet-5-5",
        ("claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5"),
        "https://console.anthropic.com/settings/keys",
        headers={"x-api-key": "{key}", "anthropic-version": "2023-06-01"},
        note="Haiku 更快更省，Sonnet 均衡，Opus 能力最强。",
    ),
    Provider(
        "openai", "OpenAI", "国际", "https://api.openai.com/v1", "gpt-6.1-sol",
        ("gpt-6.1-sol", "gpt-6-luna"),
        "https://platform.openai.com/api-keys",
    ),
    Provider(
        "xai", "xAI Grok", "国际", "https://api.x.ai/v1", "grok-4.7",
        ("grok-4.7",),
        "https://console.x.ai/",
    ),
    Provider(
        "qwen_intl", "Qwen（阿里云国际版）", "国际", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1", "qwen-plus",
        ("qwen-plus", "qwen-max", "qwen-flash"),
        "https://modelstudio.console.alibabacloud.com/",
        note="国际版与国内版的 API Key 不通用。",
    ),
    Provider(
        "kimi_intl", "Kimi（国际版）", "国际", "https://api.moonshot.ai/v1", "kimi-latest",
        ("kimi-latest",),
        "https://platform.moonshot.ai/console/api-keys",
    ),
    Provider(
        "zai", "Z.ai GLM（国际版）", "国际", "https://api.z.ai/api/paas/v4", "glm-5.3",
        ("glm-5.3", "glm-5.3-flash"),
        "https://z.ai/manage-apikey/apikey-list",
    ),
    # ── 聚合与本地 ──
    Provider(
        "openrouter", "OpenRouter（一个 Key 用各家模型）", "聚合与本地", "https://openrouter.ai/api/v1", "deepseek/deepseek-chat",
        (
            "deepseek/deepseek-chat",
            "deepseek/deepseek-v4.1-flash",
            "google/gemini-3.8-flash",
            "qwen/qwen3.8-flash",
            "moonshotai/kimi-k3",
            "z-ai/glm-5.3",
            "anthropic/claude-sonnet-5.5",
        ),
        "https://openrouter.ai/keys",
        note="模型名格式为「厂商/模型」，需选择支持工具调用的模型。",
    ),
    Provider(
        "ollama", "本地模型 Ollama", "聚合与本地", "http://localhost:11434/v1", "qwen3:8b",
        ("qwen3:8b", "qwen3:14b", "llama3.1:8b"),
        "https://ollama.com/download",
        needs_key=False,
        note="需先安装 Ollama 并 pull 模型；技能需要支持工具调用的模型。",
    ),
    Provider(
        "custom", "自定义（OpenAI 兼容接口）", "聚合与本地", "", "",
        note="任何兼容 OpenAI 接口、支持工具调用的服务都可以使用。",
    ),
]

PROVIDERS: Dict[str, Provider] = {p.id: p for p in PROVIDER_LIST}
GROUPS = ["国内", "国际", "聚合与本地"]


def get(provider_id: str) -> Provider:
    return PROVIDERS.get(provider_id) or PROVIDERS["custom"]


def provider_for_url(base_url: str) -> str:
    url = (base_url or "").rstrip("/")
    for p in PROVIDER_LIST:
        if p.base_url and url == p.base_url.rstrip("/"):
            return p.id
    return "custom"


def request_headers(provider_id: str, api_key: str) -> Dict[str, str]:
    return {k: v.replace("{key}", api_key) for k, v in get(provider_id).headers.items()}
