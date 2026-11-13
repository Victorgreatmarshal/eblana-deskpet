"""
对各家 OpenAI 兼容接口的统一封装：建客户端、发请求时自动适配参数差异、拉取模型列表。

各家实现细节不完全一致，这里集中处理：
- 部分模型不接受 max_tokens（要求 max_completion_tokens）或不允许自定义 temperature：
  首次被拒后自动调整参数重试，并记住该模型的调整；
- 不需要 Key 的本地服务（Ollama）传入占位 Key；
- 个别服务商需要额外请求头（如 Anthropic 的 x-api-key）。
"""
from typing import Dict, List, Tuple

import openai
from openai import OpenAI

import providers

# (base_url, model) -> 该模型需要的参数调整
_PARAM_FIXES: Dict[Tuple[str, str], dict] = {}

# 模型列表里这些显然不是对话模型
_NON_CHAT = ("embed", "embedding", "tts", "whisper", "dall-e", "rerank", "moderation", "transcribe", "speech", "image-gen", "imagen")


def make_client(provider_id: str, api_key: str, base_url: str, timeout: float = 90, max_retries: int = 1) -> OpenAI:
    preset = providers.get(provider_id)
    key = api_key.strip() or ("not-needed" if not preset.needs_key else "")
    return OpenAI(
        api_key=key,
        base_url=(base_url or preset.base_url).strip(),
        timeout=timeout,
        max_retries=max_retries,
        default_headers=providers.request_headers(provider_id, key) or None,
    )


def client_from_config(config, timeout: float = 90) -> OpenAI:
    return make_client(
        config.get("provider", "deepseek"), config.get("api_key", ""), config.get("base_url", ""), timeout=timeout
    )


def _apply_fixes(kwargs: dict, fix: dict) -> dict:
    req = dict(kwargs)
    if fix.get("max_completion_tokens") and "max_tokens" in req:
        req["max_completion_tokens"] = req.pop("max_tokens")
    for name in fix.get("drop", ()):
        req.pop(name, None)
    return req


def chat(client: OpenAI, **kwargs):
    """chat.completions.create，遇到参数不被支持时自动调整重试"""
    key = (str(client.base_url), kwargs.get("model", ""))
    fix = _PARAM_FIXES.setdefault(key, {"drop": set()})
    for _ in range(4):
        try:
            return client.chat.completions.create(**_apply_fixes(kwargs, fix))
        except openai.BadRequestError as e:
            msg = error_text(e).lower()
            if "max_tokens" in msg and "max_completion_tokens" in msg and not fix.get("max_completion_tokens"):
                fix["max_completion_tokens"] = True
            elif "temperature" in msg and "temperature" not in fix["drop"]:
                fix["drop"].add("temperature")
            elif "tool_choice" in msg and "tool_choice" not in fix["drop"]:
                fix["drop"].add("tool_choice")
            elif "stream_options" in msg and "stream_options" not in fix["drop"]:
                fix["drop"].add("stream_options")
            else:
                raise
    return client.chat.completions.create(**_apply_fixes(kwargs, fix))


def error_text(e: Exception) -> str:
    """错误详情：流式请求时 str(e) 只有状态码，具体原因在 body 里"""
    return f"{e} {getattr(e, 'body', '') or ''}"


def is_local(e: Exception) -> bool:
    url = str(getattr(getattr(e, "request", None), "url", "") or "")
    return "://localhost" in url or "://127.0.0.1" in url or "://[::1]" in url


def complete_text(client: OpenAI, **kwargs) -> str:
    """以流式方式拿完整文本（有些模型只支持流式调用），忽略思考过程"""
    parts = []
    for chunk in chat(client, stream=True, **kwargs):
        if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
            parts.append(chunk.choices[0].delta.content)
    return "".join(parts)


def list_models(client: OpenAI) -> List[str]:
    ids = []
    for m in client.models.list():
        mid = getattr(m, "id", "") or ""
        if mid.startswith("models/"):  # Gemini 的列表带 models/ 前缀
            mid = mid[len("models/"):]
        if mid and not any(tag in mid.lower() for tag in _NON_CHAT):
            ids.append(mid)
    return sorted(set(ids), key=str.lower)
