import json
import re
from typing import Dict, List
from urllib.parse import urlparse
from PyQt6.QtCore import QThread, pyqtSignal
import openai

import llm
import providers
import skills
from config import ConfigManager, MEMORY_FILE
from skills import humanize
from skills.base import ToolContext


# ─────────────────────────────────────────────
# 历史对话记忆管理
# ─────────────────────────────────────────────
class MemoryManager:
    def __init__(self, max_turns: int = 15):
        self.max_turns = max_turns
        self.messages: List[dict] = []
        self.load()

    def load(self):
        if MEMORY_FILE.exists():
            try:
                with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                    self.messages = json.load(f)
            except Exception:
                self.messages = []

    def save(self):
        # 仅持久化普通 user / assistant 消息，裁剪到最近 max_turns * 2 条
        clean = [m for m in self.messages if m.get("role") in ("user", "assistant") and m.get("content")]
        if len(clean) > self.max_turns * 2:
            clean = clean[-self.max_turns * 2 :]
        self.messages = clean
        try:
            with open(MEMORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self.messages, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Memory] 保存失败: {e}")

    def add_turn(self, user_text: str, assistant_text: str):
        self.messages.append({"role": "user", "content": user_text})
        self.messages.append({"role": "assistant", "content": assistant_text})
        self.save()

    def clear(self):
        self.messages.clear()
        if MEMORY_FILE.exists():
            MEMORY_FILE.unlink()


# ─────────────────────────────────────────────
# API 错误 → 可读提示
# ─────────────────────────────────────────────
def describe_api_error(e: Exception) -> str:
    if isinstance(e, openai.AuthenticationError):
        return "API Key 无效或已失效"
    if isinstance(e, openai.PermissionDeniedError):
        return "没有访问该模型的权限"
    if isinstance(e, openai.NotFoundError):
        return "模型名称或 Base URL 有误"
    if isinstance(e, openai.RateLimitError):
        return "请求过于频繁，请稍后再试"
    if isinstance(e, openai.APITimeoutError):
        return "请求超时，请检查网络"
    if isinstance(e, openai.APIConnectionError):
        if llm.is_local(e):
            return "连不上本地服务，请确认 Ollama 已经启动"
        return "无法连接服务器（当前网络可能屏蔽了该地址，可换个网络或改用其他服务商）"
    if isinstance(e, openai.APIStatusError):
        lowered = llm.error_text(e).lower()
        if "api key" in lowered or "api_key" in lowered or "apikey" in lowered:
            return "API Key 无效或已失效"  # Gemini、xAI 用 400 表示 Key 无效
        if e.status_code == 402:
            return "账户余额不足"
        return f"服务返回错误（HTTP {e.status_code}）"
    text = str(e).strip().splitlines()[0] if str(e).strip() else type(e).__name__
    return text[:80]


# ─────────────────────────────────────────────
# 异步智能体工作线程 (QThread)
# ─────────────────────────────────────────────
MAX_TOOL_ROUNDS = 10        # 一次请求内最多的工具调用轮数（写文档 / 做 PPT 往往需要读、写、改多步）
ACTION_TAG_PATTERN = re.compile(r"^\s*\[ACTION:([a-zA-Z0-9_]+)\]\s*")


class EblanaAgentWorker(QThread):
    """在后台线程运行流式对话与工具调用，避免阻塞界面"""

    chunk_received = pyqtSignal(str)       # 当前累积的回复文本
    tool_invoked = pyqtSignal(str)         # 开始调用某个工具（名称）
    action_triggered = pyqtSignal(str)     # 解析到 [ACTION:xxx]
    files_produced = pyqtSignal(list)      # 本轮生成或修改的文件（路径字符串列表）
    status_changed = pyqtSignal(str)       # 气泡状态栏文字（如「斟酌措辞…」）
    finished_reply = pyqtSignal(str)       # 完整回复
    error_occurred = pyqtSignal(str)       # 错误提示

    def __init__(self, user_prompt: str, config: ConfigManager, memory: MemoryManager):
        super().__init__()
        self.user_prompt = user_prompt
        self.config = config
        self.memory = memory

    def run(self):
        preset = providers.get(self.config.get("provider", "deepseek"))
        if preset.needs_key and not self.config.get("api_key", "").strip():
            self.error_occurred.emit("还没有配置 API Key。\n右键点我，在「设置」里填好再来找我，学者。")
            return
        model = (self.config.get("model") or preset.model or "").strip()
        if not model:
            self.error_occurred.emit("还没有选择模型。\n右键点我，在「设置 → 连接」里选一个模型吧，学者。")
            return

        try:
            ctx = ToolContext(skills.workspace_dir(self.config.get("workspace_dir", "")))
        except Exception as e:
            self.error_occurred.emit(f"工作区不可用：{e}\n请在「设置 → 能力」里换一个文件夹。")
            return

        active = skills.active_skills(self.config.get("skills_enabled", skills.DEFAULT_ENABLED))
        tools = skills.tool_index(active)
        tool_schemas = [t.schema() for t in tools.values()]
        persona = self.config.get("system_prompt", "")
        system_prompt = persona + "\n\n" + skills.build_prompt(active, ctx)
        humanize_on = any(s.id == "humanize" for s in active)
        extra_rules = self.config.get("humanize_extra", []) or []

        try:
            client = llm.client_from_config(self.config)
            messages = [{"role": "system", "content": system_prompt}]
            history = self.memory.messages[-self.config.get("max_history_turns", 15) * 2 :]
            if humanize_on:
                # 历史里的套话会被模型当成范例模仿，发送前先清掉
                history = [
                    {**m, "content": humanize.scrub(m["content"], extra_rules) or "……"} if m.get("role") == "assistant" else m
                    for m in history
                ]
            messages.extend(history)
            messages.append({"role": "user", "content": self.user_prompt})

            for step in range(MAX_TOOL_ROUNDS + 1):
                if step == MAX_TOOL_ROUNDS:
                    # 不用 tool_choice="none"（并非各家都支持），改为明确要求直接作答
                    messages.append({"role": "user", "content": "（系统提示：工具调用次数已达上限。请不要再调用工具，直接根据已有结果回复。）"})
                request = dict(
                    model=model,
                    messages=messages,
                    temperature=float(self.config.get("temperature", 0.7)),
                    max_tokens=int(self.config.get("max_tokens", 8192)),
                    stream=True,
                )
                if tool_schemas:
                    request["tools"] = tool_schemas
                response = llm.chat(client, **request)

                collected_content = ""
                action_emitted = False
                tool_calls_buffer: Dict[tuple, dict] = {}  # 按出现顺序保存
                announced = set()
                last_slot = None
                shown, flagged = "", False

                for chunk in response:
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta

                    # 1. 收集工具调用增量；名称一出现就通知界面（参数可能还要流式生成很久）
                    if delta.tool_calls:
                        for tc in delta.tool_calls:
                            # 各家流式格式略有差异：有的不给 index，只在首段给 id，或一次给全
                            if getattr(tc, "index", None) is not None:
                                slot = ("index", tc.index)
                            elif tc.id:
                                slot = ("id", tc.id)
                            else:
                                slot = last_slot or ("index", 0)
                            last_slot = slot
                            buf = tool_calls_buffer.setdefault(
                                slot, {"id": "", "type": "function", "function": {"name": "", "arguments": ""}}
                            )
                            if tc.id:
                                buf["id"] = tc.id
                            fn = tc.function
                            if fn:
                                if fn.name and fn.name != buf["function"]["name"]:
                                    buf["function"]["name"] += fn.name
                                if fn.arguments:
                                    buf["function"]["arguments"] += fn.arguments
                            name = buf["function"]["name"]
                            if name and slot not in announced and name in tools:
                                announced.add(slot)
                                self.tool_invoked.emit(name)

                    # 2. 收集文本流
                    if delta.content:
                        collected_content += delta.content
                        match = ACTION_TAG_PATTERN.match(collected_content)
                        if match:
                            if not action_emitted:
                                self.action_triggered.emit(match.group(1).lower())
                                action_emitted = True
                            display_text = ACTION_TAG_PATTERN.sub("", collected_content)
                        elif collected_content.lstrip().startswith("[ACTION") and "]" not in collected_content:
                            display_text = ""  # 标签还没收完整，先不显示残片
                        else:
                            display_text = collected_content
                        if display_text and humanize_on:
                            # 只放出检查过的完整句子；出现套话就停在它前面，等改写后再整体显示
                            prefix, hit = humanize.safe_prefix(display_text, extra_rules)
                            if hit and not flagged:
                                flagged = True
                                self.status_changed.emit("斟酌措辞…")
                            if len(prefix) > len(shown):
                                shown = prefix
                                self.chunk_received.emit(shown)
                        elif display_text:
                            self.chunk_received.emit(display_text)

                # 本轮有工具调用：执行后继续下一轮（最后一轮不再执行，有文字就当作最终回复）
                if tool_calls_buffer and step == MAX_TOOL_ROUNDS and not collected_content.strip():
                    break
                if tool_calls_buffer and step < MAX_TOOL_ROUNDS:
                    calls = list(tool_calls_buffer.values())
                    for n, call in enumerate(calls):
                        call["id"] = call["id"] or f"call_{step}_{n}"
                    messages.append({"role": "assistant", "content": collected_content or None, "tool_calls": calls})
                    produced_before = len(ctx.produced)
                    for call in calls:
                        name = call["function"]["name"]
                        result = skills.execute(tools, name, call["function"]["arguments"], ctx)
                        messages.append({"role": "tool", "tool_call_id": call["id"], "content": result})
                    if len(ctx.produced) != produced_before:
                        self.files_produced.emit([str(p) for p in ctx.produced])
                    continue

                # 没有工具调用：最终回复
                final_clean = ACTION_TAG_PATTERN.sub("", collected_content).strip() or "……"
                if not action_emitted:
                    self.action_triggered.emit("talk")
                if humanize_on:
                    final_clean = self._humanize(client, model, persona, final_clean, extra_rules)
                remembered = final_clean
                if ctx.produced:
                    remembered += "\n\n（本次处理的文件：" + "、".join(ctx.display(p) for p in ctx.produced) + "）"
                self.memory.add_turn(self.user_prompt, remembered)
                self.finished_reply.emit(final_clean)
                return

            self.error_occurred.emit("这件事步骤太多，我没能在限定的轮数内收尾。把任务拆小一点再交给我吧，学者。")
        except openai.APIConnectionError as e:
            if isinstance(e, openai.APITimeoutError):
                self.error_occurred.emit("请求超时了。网络不太稳定，稍后再试吧，学者。")
                return
            if llm.is_local(e):
                self.error_occurred.emit("连不上本地的模型服务。先确认 Ollama 已经启动，并且拉取了设置里的模型，学者。")
                return
            host = urlparse(self.config.get("base_url", "")).hostname or "服务器"
            self.error_occurred.emit(
                f"连不上 {host}，当前网络可能屏蔽了它。\n"
                "换个网络，或在「设置 → 连接」里换一个服务商。"
            )
        except Exception as e:
            self.error_occurred.emit(f"请求失败：{describe_api_error(e)}")

    def _humanize(self, client, model: str, persona: str, text: str, extra_rules) -> str:
        """检测到套话时请模型改写（最多两次），仍不干净就删掉命中的分句"""
        hits = humanize.find_hits(text, extra_rules)
        for _attempt in range(2):
            if not hits:
                return text
            self.status_changed.emit("斟酌措辞…")
            try:
                reply = llm.complete_text(
                    client,
                    model=model,
                    messages=humanize.rewrite_messages(persona, text, hits),
                    temperature=0.8,
                    max_tokens=1024,
                )
                candidate = ACTION_TAG_PATTERN.sub("", reply).strip()
                candidate = candidate.strip("「」“”\"")
            except Exception:
                break
            if candidate:
                text = candidate
            hits = humanize.find_hits(text, extra_rules)
        if hits:
            return humanize.scrub(text, extra_rules) or "……"
        return text
