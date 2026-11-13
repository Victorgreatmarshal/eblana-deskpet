"""基础能力：档案、时间与系统状态、剪贴板、打开网页 / 应用 / 文件、待办。始终启用。"""
import datetime
import json
import os
import platform
import subprocess
import webbrowser
from typing import List

import psutil
import pyperclip

from config import ARCHIVE_FILE, TODOS_FILE
from .base import Skill, Tool, ToolContext, ToolError, schema

SYSTEM = platform.system()


def open_path(path, reveal: bool = False):
    """用系统默认程序打开文件；reveal=True 时在文件管理器中定位它"""
    path = str(path)
    if SYSTEM == "Darwin":
        subprocess.Popen(["open", "-R", path] if reveal else ["open", path])
    elif SYSTEM == "Windows":
        if reveal:
            subprocess.Popen(["explorer", f"/select,{path}"])
        else:
            os.startfile(path)  # noqa: 仅 Windows 存在
    else:
        subprocess.Popen(["xdg-open", os.path.dirname(path) if reveal else path])


# ── 档案 ──
def _read_archive(ctx: ToolContext, args: dict) -> str:
    if ARCHIVE_FILE.exists():
        return ARCHIVE_FILE.read_text(encoding="utf-8")
    return "未找到档案文件。"


# ── 系统状态 ──
def _system_status(ctx: ToolContext, args: dict) -> str:
    now = datetime.datetime.now()
    weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    battery = psutil.sensors_battery()
    bat_info = f"{battery.percent}% ({'充电中' if battery.power_plugged else '使用电池'})" if battery else "桌面电源"
    return json.dumps(
        {
            "current_time": now.strftime("%Y-%m-%d %H:%M:%S"),
            "weekday": weekdays[now.weekday()],
            "cpu_percent": f"{psutil.cpu_percent(interval=0.2)}%",
            "memory_percent": f"{psutil.virtual_memory().percent}%",
            "battery": bat_info,
        },
        ensure_ascii=False,
    )


# ── 剪贴板 ──
def _read_clipboard(ctx: ToolContext, args: dict) -> str:
    content = pyperclip.paste()
    if not content:
        return "剪贴板当前为空。"
    limit = 12000
    note = f"（过长，仅显示前 {limit} 字）" if len(content) > limit else ""
    return f"剪贴板内容（共 {len(content)} 字符）{note}：\n{content[:limit]}"


def _write_clipboard(ctx: ToolContext, args: dict) -> str:
    text = args.get("text", "")
    pyperclip.copy(text)
    return f"已将 {len(text)} 个字符写入剪贴板。"


# ── 打开网页 / 应用 / 文件 ──
SHORTCUTS = {
    "prts": "https://prts.wiki/w/%E6%AD%BB%E8%8A%92",
    "bilibili": "https://www.bilibili.com",
    "github": "https://github.com",
    "google": "https://www.google.com",
}


def _open_url_or_app(ctx: ToolContext, args: dict) -> str:
    t_type = args.get("target_type", "url")
    target = (args.get("target") or "").strip()
    if not target:
        raise ToolError("缺少要打开的目标")
    if t_type == "url":
        url = SHORTCUTS.get(target.lower(), target)
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        webbrowser.open(url)
        return f"已在默认浏览器中打开：{url}"
    if SYSTEM == "Darwin":
        subprocess.Popen(["open", "-a", target])
    elif SYSTEM == "Windows":
        os.startfile(target)  # 通过系统注册的应用名启动，不经过命令行解析
    else:
        subprocess.Popen([target])
    return f"已尝试启动应用：{target}"


def _open_file(ctx: ToolContext, args: dict) -> str:
    path = ctx.input_path(args.get("path", ""))
    reveal = bool(args.get("reveal", False))
    open_path(path, reveal=reveal)
    return f"已{'在文件夹中显示' if reveal else '打开'}：{ctx.display(path)}"


# ── 待办 ──
def _load_todos() -> List[dict]:
    if TODOS_FILE.exists():
        try:
            return json.loads(TODOS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save_todos(todos: List[dict]):
    TODOS_FILE.write_text(json.dumps(todos, ensure_ascii=False, indent=2), encoding="utf-8")


def _manage_todos(ctx: ToolContext, args: dict) -> str:
    action = args.get("action", "list")
    todos = _load_todos()
    if action == "list":
        return json.dumps(todos, ensure_ascii=False) if todos else "当前没有任何待办事项。"
    if action == "add":
        content = (args.get("content") or "").strip()
        if not content:
            raise ToolError("待办内容不能为空")
        next_id = max([t.get("id", 0) for t in todos], default=0) + 1
        todos.append(
            {"id": next_id, "content": content, "done": False, "created_at": datetime.datetime.now().strftime("%m-%d %H:%M")}
        )
        _save_todos(todos)
        return f"已添加待办 #{next_id}：{content}"
    tid = args.get("todo_id")
    if action == "complete":
        for t in todos:
            if t.get("id") == tid:
                t["done"] = True
                _save_todos(todos)
                return f"已将待办 #{tid}（{t['content']}）标记为完成。"
        return f"未找到编号为 #{tid} 的待办。"
    if action == "delete":
        remaining = [t for t in todos if t.get("id") != tid]
        _save_todos(remaining)
        return f"已删除待办 #{tid}。" if len(remaining) < len(todos) else f"未找到编号为 #{tid} 的待办。"
    raise ToolError(f"未知操作：{action}")


SKILL = Skill(
    id="core",
    name="基础",
    summary="档案、时间与系统状态、剪贴板、打开网页 / 应用 / 文件、待办",
    optional=False,
    instructions="""【基础】
- 学者问起你的档案细节时调用 read_eblana_archive，依据原文作答。
- 「看看我复制的内容」之类的请求用 read_clipboard；需要学者直接粘贴的结果用 write_clipboard。
- 文件交付后，学者要求查看时用 open_file 打开（reveal=true 则在文件夹中定位）。""",
    tools=[
        Tool(
            "read_eblana_archive",
            "查阅罗德岛高权限资料库中关于死芒（爱布拉娜）的完整官方档案原文（体检报告、沃里克伯爵日记、深池访谈、维娜录音、苇草书信、精二晋升记录、模组故事等）。学者问起你的档案细节、过往经历或人事评价时调用。",
            schema({}),
            _read_archive,
            "调阅干员档案",
        ),
        Tool(
            "get_system_status",
            "获取当前日期、时间、星期，以及学者电脑的 CPU、内存占用和电池电量。",
            schema({}),
            _system_status,
            "读取时间与系统状态",
        ),
        Tool(
            "read_clipboard",
            "读取学者当前剪贴板中的文本。",
            schema({}),
            _read_clipboard,
            "读取剪贴板",
        ),
        Tool(
            "write_clipboard",
            "把文本写入学者的剪贴板，方便直接粘贴。",
            schema({"text": {"type": "string", "description": "要写入的文本"}}, ["text"]),
            _write_clipboard,
            "写入剪贴板",
        ),
        Tool(
            "open_url_or_app",
            "在浏览器中打开网页（可用简写 prts / bilibili / github / google），或启动本地应用程序。",
            schema(
                {
                    "target_type": {"type": "string", "enum": ["url", "app"], "description": "网页填 url，本地应用填 app"},
                    "target": {"type": "string", "description": "网页 URL 或应用名称（如 Safari、Notes、Visual Studio Code）"},
                },
                ["target_type", "target"],
            ),
            _open_url_or_app,
            "打开网页或应用",
        ),
        Tool(
            "open_file",
            "用系统默认程序打开一个文件（如刚生成的 Word / PPT），或在文件夹中定位它。相对路径相对于工作区。",
            schema(
                {
                    "path": {"type": "string", "description": "文件路径"},
                    "reveal": {"type": "boolean", "description": "true 表示在文件夹中显示而不是打开"},
                },
                ["path"],
            ),
            _open_file,
            "打开文件",
        ),
        Tool(
            "manage_todos",
            "管理学者的待办事项：查看、添加、标记完成或删除。",
            schema(
                {
                    "action": {"type": "string", "enum": ["list", "add", "complete", "delete"]},
                    "content": {"type": "string", "description": "action 为 add 时的待办内容"},
                    "todo_id": {"type": "integer", "description": "action 为 complete / delete 时的待办编号"},
                },
                ["action"],
            ),
            _manage_todos,
            "整理待办事项",
        ),
    ],
)
