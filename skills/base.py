"""
技能（Skill）= 一组工具 + 一段注入系统提示词的工作守则。

工具的 handler 签名为 handler(ctx: ToolContext, args: dict) -> str，返回给模型看的结果文本。
可预期的失败抛 ToolError，消息会原样告诉模型，方便它换个方法重试。
"""
import importlib.util
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Tuple


class ToolError(Exception):
    """可预期的工具错误（参数不对、文件不存在、越过工作区等）"""


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    handler: Callable[["ToolContext", dict], str]
    status: str  # 调用时气泡里显示的状态，例如「撰写 Word 文档」

    def schema(self) -> dict:
        return {
            "type": "function",
            "function": {"name": self.name, "description": self.description, "parameters": self.parameters},
        }


@dataclass
class Skill:
    id: str
    name: str            # 设置里显示的名称
    summary: str         # 设置里的一句话说明
    instructions: str    # 注入系统提示词的工作守则
    tools: List[Tool]
    optional: bool = True              # False = 基础能力，始终启用
    requires: Tuple[str, ...] = ()     # 依赖的第三方模块
    listed: bool = True                # 是否出现在设置的「技能」列表里

    def available(self) -> bool:
        return all(importlib.util.find_spec(mod) is not None for mod in self.requires)


_INVALID_CHARS = re.compile(r'[<>:"|?*\x00-\x1f]')


@dataclass
class ToolContext:
    workspace: Path
    produced: List[Path] = field(default_factory=list)  # 本轮生成或修改的文件

    def __post_init__(self):
        self.workspace = Path(self.workspace).expanduser().resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)

    # ── 路径规则：读取不限位置；写入只允许在工作区内 ──
    def in_workspace(self, path: Path) -> bool:
        path = path.resolve()
        return path == self.workspace or self.workspace in path.parents

    def output_path(self, name: str, suffix: str = "", unique: bool = True) -> Path:
        name = (name or "").strip().replace("\\", "/")
        if not name:
            raise ToolError("缺少文件名")
        raw = Path(name).expanduser()
        if raw.is_absolute():
            target = raw.resolve()
        else:
            parts = [_INVALID_CHARS.sub("_", p) for p in raw.parts if p not in ("", ".")]
            if not parts:
                raise ToolError("文件名无效")
            target = (self.workspace / Path(*parts)).resolve()
        if not self.in_workspace(target) or target == self.workspace:
            raise ToolError(f"只能写入工作区（{self.workspace}）内的文件，请改用相对路径")
        if suffix and not target.name.lower().endswith(suffix):
            target = target.with_name(target.name + suffix)
        if unique and target.exists():
            stem, ext = target.name[: -len(target.suffix)] if target.suffix else target.name, target.suffix
            n = 2
            while (candidate := target.with_name(f"{stem} ({n}){ext}")).exists():
                n += 1
            target = candidate
        target.parent.mkdir(parents=True, exist_ok=True)
        return target

    def input_path(self, path: str) -> Path:
        cleaned = (path or "").strip().strip('"').strip("'")
        if not cleaned:
            raise ToolError("缺少文件路径")
        p = Path(cleaned).expanduser()
        if not p.is_absolute():
            p = self.workspace / p
        p = p.resolve()
        if not p.exists():
            raise ToolError(f"找不到文件：{p}")
        return p

    def display(self, path: Path) -> str:
        """工作区内的文件用相对路径展示，其余用完整路径"""
        path = path.resolve()
        return str(path.relative_to(self.workspace)) if self.in_workspace(path) else str(path)

    def record(self, path: Path):
        path = path.resolve()
        if path not in self.produced:
            self.produced.append(path)


def schema(properties: Dict[str, dict], required: List[str] = ()) -> dict:
    return {"type": "object", "properties": properties, "required": list(required)}
