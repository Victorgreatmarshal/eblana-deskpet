"""Word 文书：新建、读取、修订 .docx（python-docx）。"""
import re
from typing import Iterable, List

from .base import Skill, Tool, ToolContext, ToolError, schema

try:
    from docx import Document
    from docx.enum.text import WD_BREAK
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt, RGBColor
    from docx.table import Table
    from docx.text.paragraph import Paragraph
except ImportError:  # 未安装时该技能不可用
    Document = None

FONT_LATIN = "Calibri"
FONT_EA = "等线"
TEXT_RGB = "1F2329"
MUTED_RGB = "5C6370"
HEADER_FILL = "E9EBEF"

BLOCK_TYPES = ["heading", "paragraph", "bullets", "numbered", "table", "quote", "page_break"]
BLOCKS_SCHEMA = {
    "type": "array",
    "description": "按顺序排列的内容块",
    "items": {
        "type": "object",
        "properties": {
            "type": {"type": "string", "enum": BLOCK_TYPES},
            "text": {"type": "string", "description": "heading / paragraph / quote 的文字；可用 **加粗**；paragraph 中的换行会拆成多段"},
            "level": {"type": "integer", "description": "heading 级别 1-3"},
            "items": {"type": "array", "items": {"type": "string"}, "description": "bullets / numbered 的条目；以两个空格开头表示二级条目"},
            "rows": {
                "type": "array",
                "items": {"type": "array", "items": {"type": "string"}},
                "description": "table 的行，第一行是表头",
            },
        },
        "required": ["type"],
    },
}


def _require():
    if Document is None:
        raise ToolError("未安装 python-docx，无法处理 Word 文档")


# ─────────────────────────────────────────────
# 样式
# ─────────────────────────────────────────────
def _style_font(style, size: float, bold: bool = False, color: str = TEXT_RGB):
    style.font.name = FONT_LATIN
    style.font.size = Pt(size)
    style.font.bold = bold
    style.font.italic = False
    style.font.color.rgb = RGBColor.from_string(color)
    rfonts = style.element.get_or_add_rPr().find(qn("w:rFonts"))
    for attr in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
        rfonts.attrib.pop(qn(attr), None)
    rfonts.set(qn("w:eastAsia"), FONT_EA)


def _new_document():
    doc = Document()
    for section in doc.sections:
        section.left_margin = section.right_margin = Cm(2.5)
        section.top_margin = section.bottom_margin = Cm(2.3)

    styles = doc.styles
    normal = styles["Normal"]
    _style_font(normal, 11)
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.35

    for name, size, before in (("Heading 1", 16, 16), ("Heading 2", 14, 12), ("Heading 3", 12, 10)):
        st = styles[name]
        _style_font(st, size, bold=True)
        st.paragraph_format.space_before = Pt(before)
        st.paragraph_format.space_after = Pt(6)
        st.paragraph_format.keep_with_next = True

    _style_font(styles["Title"], 24, bold=True)
    styles["Title"].paragraph_format.space_after = Pt(4)
    _style_font(styles["Subtitle"], 13, color=MUTED_RGB)
    styles["Subtitle"].paragraph_format.space_after = Pt(18)
    _style_font(styles["Quote"], 11, color=MUTED_RGB)
    return doc


def _style_or(doc, name: str, fallback: str = "Normal"):
    try:
        return doc.styles[name]
    except KeyError:
        return doc.styles[fallback]


_BOLD = re.compile(r"(\*\*.+?\*\*)")
_LIST_MARK = re.compile(r"^([-•*·]|\d+[.、)])\s+")


def _add_rich_text(paragraph, text: str):
    for part in _BOLD.split(text):
        if len(part) > 4 and part.startswith("**") and part.endswith("**"):
            paragraph.add_run(part[2:-2]).bold = True
        elif part:
            paragraph.add_run(part)


def _shade(cell, fill: str):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    tc_pr.append(shd)


def _write_blocks(doc, blocks: Iterable[dict]) -> int:
    count = 0
    for block in blocks or []:
        kind = (block.get("type") or "paragraph").lower()
        text = (block.get("text") or "").strip()
        if kind == "heading":
            level = min(3, max(1, int(block.get("level") or 1)))
            doc.add_heading(text, level=level)
        elif kind == "paragraph":
            for line in [l for l in text.split("\n") if l.strip()] or [""]:
                _add_rich_text(doc.add_paragraph(), line.strip())
        elif kind in ("bullets", "numbered"):
            base = "List Bullet" if kind == "bullets" else "List Number"
            for item in block.get("items") or []:
                level2 = item.startswith(("  ", "\t"))
                style = _style_or(doc, f"{base} 2" if level2 else base, base)
                _add_rich_text(doc.add_paragraph(style=style), _LIST_MARK.sub("", item.strip()))
        elif kind == "table":
            rows = [list(map(str, r)) for r in (block.get("rows") or []) if r]
            if not rows:
                raise ToolError("table 缺少 rows")
            cols = max(len(r) for r in rows)
            table = doc.add_table(rows=len(rows), cols=cols)
            table.style = _style_or(doc, "Table Grid")
            for r_idx, row in enumerate(rows):
                for c_idx in range(cols):
                    cell = table.cell(r_idx, c_idx)
                    cell.text = ""
                    _add_rich_text(cell.paragraphs[0], row[c_idx] if c_idx < len(row) else "")
                    if r_idx == 0:
                        for run in cell.paragraphs[0].runs:
                            run.bold = True
                        _shade(cell, HEADER_FILL)
            doc.add_paragraph()  # 表格后留一行间距
        elif kind == "quote":
            _add_rich_text(doc.add_paragraph(style=_style_or(doc, "Quote")), text)
        elif kind == "page_break":
            doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
        else:
            raise ToolError(f"未知内容块类型：{kind}（可用：{', '.join(BLOCK_TYPES)}）")
        count += 1
    return count


def _iter_paragraphs(doc) -> Iterable:
    yield from doc.paragraphs
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                yield from cell.paragraphs
    for section in doc.sections:
        yield from section.header.paragraphs
        yield from section.footer.paragraphs


def _replace_in_paragraph(paragraph, find: str, repl: str) -> int:
    if find not in paragraph.text:
        return 0
    count = 0
    for run in paragraph.runs:
        if find in run.text:
            count += run.text.count(find)
            run.text = run.text.replace(find, repl)
    if count:
        return count
    # 目标文字跨越多个 run：合并到第一个 run（保留其格式）
    full = paragraph.text
    runs = paragraph.runs
    runs[0].text = full.replace(find, repl)
    for run in runs[1:]:
        run.text = ""
    return full.count(find)


# ─────────────────────────────────────────────
# 工具
# ─────────────────────────────────────────────
def _word_create(ctx: ToolContext, args: dict) -> str:
    _require()
    title = (args.get("title") or "").strip()
    doc = _new_document()
    if title:
        doc.add_paragraph(title, style="Title")
        doc.core_properties.title = title
    if args.get("subtitle"):
        doc.add_paragraph(args["subtitle"].strip(), style="Subtitle")
    doc.core_properties.author = (args.get("author") or "").strip()
    n = _write_blocks(doc, args.get("blocks"))
    path = ctx.output_path(args.get("filename") or title or "未命名文档", ".docx")
    doc.save(str(path))
    ctx.record(path)
    return f"已创建 Word 文档：{ctx.display(path)}（{n} 个内容块）"


def _word_read(ctx: ToolContext, args: dict) -> str:
    _require()
    path = ctx.input_path(args.get("path", ""))
    if path.suffix.lower() != ".docx":
        raise ToolError("只支持 .docx 格式（旧版 .doc 请先在 Word 中另存为 .docx）")
    doc = Document(str(path))
    lines: List[str] = []
    for el in doc.element.body.iterchildren():
        if el.tag == qn("w:p"):
            p = Paragraph(el, doc)
            text = p.text.strip()
            if not text:
                continue
            style = p.style.name if p.style is not None else ""
            if style == "Title":
                lines.append(f"# {text}")
            elif style.startswith("Heading"):
                level = int(style.split()[-1]) if style.split()[-1].isdigit() else 1
                lines.append(f"{'#' * (level + 1)} {text}")
            elif style.startswith("List"):
                lines.append(f"- {text}")
            else:
                lines.append(text)
        elif el.tag == qn("w:tbl"):
            table = Table(el, doc)
            for row in table.rows:
                lines.append("| " + " | ".join(c.text.strip().replace("\n", " ") for c in row.cells) + " |")
    body = "\n".join(lines)
    limit = int(args.get("max_chars") or 15000)
    note = f"\n……（共 {len(body)} 字，仅显示前 {limit} 字）" if len(body) > limit else ""
    return f"文件：{ctx.display(path)}\n\n{body[:limit]}{note}"


def _word_edit(ctx: ToolContext, args: dict) -> str:
    _require()
    src = ctx.input_path(args.get("path", ""))
    if src.suffix.lower() != ".docx":
        raise ToolError("只支持 .docx 格式")
    doc = Document(str(src))
    results = []
    for op in args.get("operations") or []:
        kind = op.get("op")
        if kind == "replace":
            find, repl = op.get("find") or "", op.get("replace") or ""
            if not find:
                raise ToolError("replace 缺少 find")
            n = sum(_replace_in_paragraph(p, find, repl) for p in _iter_paragraphs(doc))
            results.append(f"替换「{find[:20]}」{n} 处")
        elif kind == "append":
            results.append(f"末尾追加 {_write_blocks(doc, op.get('blocks'))} 个内容块")
        elif kind == "insert_after":
            anchor = op.get("anchor") or ""
            target = next((p for p in doc.paragraphs if anchor and anchor in p.text), None)
            if target is None:
                raise ToolError(f"找不到包含「{anchor}」的段落")
            body = doc.element.body
            before = set(body.iterchildren())
            n = _write_blocks(doc, op.get("blocks"))
            new_elements = [el for el in body.iterchildren() if el not in before and el.tag != qn("w:sectPr")]
            ref = target._p
            for el in new_elements:
                ref.addnext(el)
                ref = el
            results.append(f"在「{anchor[:20]}」后插入 {n} 个内容块")
        elif kind == "delete":
            needle = op.get("contains") or ""
            if not needle:
                raise ToolError("delete 缺少 contains")
            doomed = [p for p in doc.paragraphs if needle in p.text]
            for p in doomed:
                p._p.getparent().remove(p._p)
            results.append(f"删除包含「{needle[:20]}」的段落 {len(doomed)} 段")
        else:
            raise ToolError(f"未知操作：{kind}（可用：replace / insert_after / append / delete）")

    if args.get("save_as"):
        target_path = ctx.output_path(args["save_as"], ".docx")
    elif ctx.in_workspace(src):
        target_path = src
    else:
        target_path = ctx.output_path(f"{src.stem}（修订）.docx")
    doc.save(str(target_path))
    ctx.record(target_path)
    kept = "（原文件未改动）" if target_path != src else ""
    return "；".join(results or ["没有执行任何操作"]) + f"\n已保存：{ctx.display(target_path)}{kept}"


SKILL = Skill(
    id="word",
    name="Word 文书",
    summary="新建、读取、修订 .docx 文档：周报、方案、公文、会议纪要等",
    requires=("docx",),
    instructions="""【Word 文书】
- 新建用 word_create：先拟好结构（标题 → 摘要或导语 → 分级小标题 → 正文、要点、表格 → 结语），一次写完整，不要只交提纲。
- 修改已有文档：先 word_read 了解内容，再用 word_edit（replace 改字句、insert_after 在某段后插入、append 追加、delete 删除段落）。工作区外的原文件不会被覆盖，会在工作区另存一份「（修订）」副本。
- 周报、方案、公文、会议纪要、合同草稿等按各自体例书写；不确定的数据用「【待补充】」标出，不要编造。
- 文件名用简洁的中文主题，例如「2026年11月工作周报」。""",
    tools=[
        Tool(
            "word_create",
            "新建一份排版规范的 Word 文档（.docx），保存到工作区。",
            schema(
                {
                    "filename": {"type": "string", "description": "文件名，可不带扩展名"},
                    "title": {"type": "string", "description": "文档大标题"},
                    "subtitle": {"type": "string", "description": "副标题，如日期、部门（可选）"},
                    "author": {"type": "string", "description": "作者（可选）"},
                    "blocks": BLOCKS_SCHEMA,
                },
                ["filename", "title", "blocks"],
            ),
            _word_create,
            "撰写 Word 文档",
        ),
        Tool(
            "word_read",
            "读取 .docx 文档的全部文字（标题层级、列表、表格），用于总结、审阅或修改前了解内容。",
            schema(
                {
                    "path": {"type": "string", "description": "文件路径；相对路径相对于工作区"},
                    "max_chars": {"type": "integer", "description": "最多返回的字数，默认 15000"},
                },
                ["path"],
            ),
            _word_read,
            "阅读 Word 文档",
        ),
        Tool(
            "word_edit",
            "修订 .docx 文档：替换文字、在指定段落后插入内容、末尾追加、删除段落。工作区内的文件就地保存；工作区外的文件另存为修订副本。",
            schema(
                {
                    "path": {"type": "string", "description": "要修改的文件路径"},
                    "operations": {
                        "type": "array",
                        "description": "按顺序执行的修改操作",
                        "items": {
                            "type": "object",
                            "properties": {
                                "op": {"type": "string", "enum": ["replace", "insert_after", "append", "delete"]},
                                "find": {"type": "string", "description": "replace：要查找的原文"},
                                "replace": {"type": "string", "description": "replace：替换成的文字"},
                                "anchor": {"type": "string", "description": "insert_after：定位段落中的一段原文"},
                                "contains": {"type": "string", "description": "delete：删除包含这段文字的段落"},
                                "blocks": BLOCKS_SCHEMA,
                            },
                            "required": ["op"],
                        },
                    },
                    "save_as": {"type": "string", "description": "另存为的文件名（可选）"},
                },
                ["path", "operations"],
            ),
            _word_edit,
            "修订 Word 文档",
        ),
    ],
)
