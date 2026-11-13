"""
技能注册表。

新增技能：在 skills/ 下写一个模块，定义 SKILL = Skill(...)，再加入 ALL_SKILLS 即可。
系统提示词由「人设」（可在设置中编辑）+ 运行时生成的「工作环境与技能守则」拼接而成，
所以技能更新后无需用户重置人设。
"""
import datetime
import json
import platform
from pathlib import Path
from typing import Dict, Iterable, List

from . import code, core, humanize, slides, word
from .base import Skill, Tool, ToolContext, ToolError

ALL_SKILLS: List[Skill] = [core.SKILL, humanize.SKILL, word.SKILL, slides.SKILL, code.SKILL]
OPTIONAL_SKILLS: List[Skill] = [s for s in ALL_SKILLS if s.optional]
LISTED_SKILLS: List[Skill] = [s for s in OPTIONAL_SKILLS if s.listed]
DEFAULT_ENABLED = [s.id for s in OPTIONAL_SKILLS]

_OS_NAMES = {"Darwin": "macOS", "Windows": "Windows", "Linux": "Linux"}

WORK_RULES = """【工作守则】
你不只陪学者闲谈，也替学者处理案头工作。接到工作时：
1. 弄清要交付什么。信息不足但能合理假设时直接动手，在回复里说明假设，不要反复追问。
2. 成果写进文件；回复仍用死芒的口吻、保持简短：做了什么、文件名、需要学者留意的一两点。不要在对话里复述文件全文。
3. 文件内容是交给学者使用的正式成果，用专业、中性的书面语，不带死芒的口吻（除非学者要求）。
4. 工具报错时调整参数或换个方法再试；仍然失败就如实说明原因。"""


def active_skills(enabled_ids: Iterable[str]) -> List[Skill]:
    enabled = set(enabled_ids or [])
    return [s for s in ALL_SKILLS if (not s.optional or s.id in enabled) and s.available()]


def tool_index(skills: Iterable[Skill]) -> Dict[str, Tool]:
    return {tool.name: tool for skill in skills for tool in skill.tools}


def build_prompt(skills: List[Skill], ctx: ToolContext) -> str:
    now = datetime.datetime.now()
    weekdays = "一二三四五六日"
    env = (
        "【工作环境】\n"
        f"- 当前时间：{now:%Y-%m-%d %H:%M}（星期{weekdays[now.weekday()]}）\n"
        f"- 操作系统：{_OS_NAMES.get(platform.system(), platform.system())}\n"
        f"- 工作区：{ctx.workspace}（你创建或修改的文件都保存在这里；相对路径均相对于工作区）"
    )
    sections = [env, WORK_RULES] + [s.instructions for s in skills]
    return "\n\n".join(sections)


def tool_status(tool_name: str) -> str:
    for skill in ALL_SKILLS:
        for tool in skill.tools:
            if tool.name == tool_name:
                return tool.status
    return tool_name


def execute(tools: Dict[str, Tool], name: str, raw_args: str, ctx: ToolContext) -> str:
    tool = tools.get(name)
    if tool is None:
        return f"未知工具：{name}"
    try:
        args = json.loads(raw_args or "{}")
        if not isinstance(args, dict):
            raise ValueError("参数必须是 JSON 对象")
    except Exception as e:
        return f"参数解析失败（{e}），请检查 JSON 格式后重试"
    try:
        return tool.handler(ctx, args)
    except ToolError as e:
        return f"失败：{e}"
    except Exception as e:
        return f"工具 {name} 出错：{type(e).__name__}: {e}"


def default_workspace() -> Path:
    return Path.home() / "Documents" / "死芒工作区"


def workspace_dir(configured: str) -> Path:
    path = Path(configured).expanduser() if (configured or "").strip() else default_workspace()
    path.mkdir(parents=True, exist_ok=True)
    return path
