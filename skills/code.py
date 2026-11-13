"""代码：在工作区读写代码与文本文件、精确修改、浏览目录。不执行代码。"""
from pathlib import Path

from .base import Skill, Tool, ToolContext, ToolError, schema

MAX_WRITE_CHARS = 400_000
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".idea", ".vscode", "dist", "build"}


def _write_file(ctx: ToolContext, args: dict) -> str:
    content = args.get("content")
    if content is None:
        raise ToolError("缺少 content")
    if len(content) > MAX_WRITE_CHARS:
        raise ToolError("内容过长，请拆分成多个文件")
    overwrite = args.get("overwrite", True)
    path = ctx.output_path(args.get("path", ""), unique=not overwrite)
    existed = path.exists()
    path.write_text(content, encoding="utf-8", newline="")
    ctx.record(path)
    return f"{'已覆盖' if existed else '已创建'}：{ctx.display(path)}（{content.count(chr(10)) + 1} 行）"


def _read_text(path: Path) -> str:
    if path.is_dir():
        raise ToolError("这是文件夹，请用 list_files 查看")
    data = path.read_bytes()
    if len(data) > 5_000_000:
        raise ToolError("文件超过 5 MB，无法读取")
    if b"\x00" in data[:8192]:
        raise ToolError("这是二进制文件；Word / PPT 请改用 word_read / ppt_read")
    return data.decode("utf-8", errors="replace")


def _read_file(ctx: ToolContext, args: dict) -> str:
    path = ctx.input_path(args.get("path", ""))
    lines = _read_text(path).splitlines()
    start = max(1, int(args.get("start_line") or 1))
    count = int(args.get("max_lines") or 400)
    chunk = lines[start - 1 : start - 1 + count]
    width = len(str(start + len(chunk)))
    body = "\n".join(f"{n:>{width}}| {line}" for n, line in enumerate(chunk, start=start))
    more = f"\n……（共 {len(lines)} 行，可用 start_line 继续读取）" if start - 1 + count < len(lines) else ""
    return f"文件：{ctx.display(path)}（第 {start}–{start + len(chunk) - 1} 行，共 {len(lines)} 行）\n{body}{more}"


def _edit_file(ctx: ToolContext, args: dict) -> str:
    path = ctx.input_path(args.get("path", ""))
    if not ctx.in_workspace(path):
        raise ToolError(f"只能修改工作区（{ctx.workspace}）内的文件；如需修改该项目，请学者在设置中把工作区指向它")
    find, repl = args.get("find") or "", args.get("replace", "")
    if not find:
        raise ToolError("缺少 find")
    text = _read_text(path)
    hits = text.count(find)
    if hits == 0:
        raise ToolError("没有找到 find 指定的原文，请先 read_file 确认（需逐字一致，包括缩进）")
    if hits > 1 and not args.get("replace_all"):
        raise ToolError(f"find 在文件中出现了 {hits} 次，请提供更长的上下文使其唯一，或设置 replace_all=true")
    path.write_text(text.replace(find, repl), encoding="utf-8", newline="")
    ctx.record(path)
    return f"已修改：{ctx.display(path)}（替换 {hits if args.get('replace_all') else 1} 处）"


def _list_files(ctx: ToolContext, args: dict) -> str:
    base = ctx.input_path(args.get("path") or ".")
    if not base.is_dir():
        raise ToolError("不是文件夹")
    depth = min(4, max(1, int(args.get("depth") or 2)))
    lines, limit = [], 300

    def walk(folder: Path, level: int):
        try:
            entries = sorted(folder.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        except PermissionError:
            return
        for entry in entries:
            if len(lines) >= limit:
                return
            if entry.name.startswith(".") or entry.name in SKIP_DIRS:
                continue
            indent = "  " * level
            if entry.is_dir():
                lines.append(f"{indent}{entry.name}/")
                if level + 1 < depth:
                    walk(entry, level + 1)
            else:
                size = entry.stat().st_size
                lines.append(f"{indent}{entry.name}  ({size / 1024:.1f} KB)" if size >= 1024 else f"{indent}{entry.name}  ({size} B)")

    walk(base, 0)
    tail = f"\n……（仅列出前 {limit} 项）" if len(lines) >= limit else ""
    return f"{ctx.display(base) if base != ctx.workspace else '工作区'}：\n" + ("\n".join(lines) or "（空）") + tail


SKILL = Skill(
    id="code",
    name="代码",
    summary="在工作区编写、阅读、修改代码与文本文件（不会运行代码）",
    instructions="""【代码】
- 写代码时把完整、可直接运行的代码用 write_file 写进工作区；多文件项目放在一个子文件夹里，并附 README.md 说明依赖与运行方式。
- 修改已有代码先 read_file，再用 edit_file 精确替换（find 需与原文逐字一致，包括缩进）；改动很大时可整体重写。
- 写入只限工作区。学者想让你改某个现有项目时，请学者在「设置 → 能力」把工作区指向那个项目文件夹。
- 你无法运行代码；交付时说明如何运行。不要在对话里贴大段代码（气泡放不下），10 行以内的片段可以直接给出。""",
    tools=[
        Tool(
            "write_file",
            "在工作区创建或覆盖一个文本文件（代码、Markdown、JSON、CSV 等）。路径相对于工作区，可包含子文件夹。",
            schema(
                {
                    "path": {"type": "string", "description": "相对工作区的路径，如 todo_app/main.py"},
                    "content": {"type": "string", "description": "完整文件内容"},
                    "overwrite": {"type": "boolean", "description": "已存在时是否覆盖，默认 true"},
                },
                ["path", "content"],
            ),
            _write_file,
            "编写代码",
        ),
        Tool(
            "read_file",
            "读取文本文件（带行号），可读取工作区内外的文件。",
            schema(
                {
                    "path": {"type": "string", "description": "文件路径；相对路径相对于工作区"},
                    "start_line": {"type": "integer", "description": "起始行，默认 1"},
                    "max_lines": {"type": "integer", "description": "最多读取的行数，默认 400"},
                },
                ["path"],
            ),
            _read_file,
            "阅读文件",
        ),
        Tool(
            "edit_file",
            "精确修改工作区内的文本文件：把 find 原文替换为 replace。",
            schema(
                {
                    "path": {"type": "string"},
                    "find": {"type": "string", "description": "要替换的原文，需逐字一致"},
                    "replace": {"type": "string", "description": "替换后的内容"},
                    "replace_all": {"type": "boolean", "description": "替换全部出现处，默认只允许唯一匹配"},
                },
                ["path", "find", "replace"],
            ),
            _edit_file,
            "修改代码",
        ),
        Tool(
            "list_files",
            "列出文件夹内容（默认工作区，深度 2）。",
            schema(
                {
                    "path": {"type": "string", "description": "文件夹路径，默认工作区"},
                    "depth": {"type": "integer", "description": "展开层数 1–4"},
                },
            ),
            _list_files,
            "查看文件夹",
        ),
    ],
)
