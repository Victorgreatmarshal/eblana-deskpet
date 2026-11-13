"""演示文稿：按版式生成设计统一的 16:9 PPT（python-pptx），以及读取已有 PPT 的大纲。"""
import re
from typing import List

from .base import Skill, Tool, ToolContext, ToolError, schema

try:
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
    from pptx.oxml.ns import qn
    from pptx.oxml.xmlchemy import OxmlElement
    from pptx.util import Inches, Pt
except ImportError:  # 未安装时该技能不可用
    Presentation = None

FONT_LATIN = "Arial"
FONT_EA = "Microsoft YaHei"

THEMES = {
    # 深灰底 + 黄色强调，与桌宠界面一致
    "dark": {"bg": "17171A", "panel": "222226", "title": "FFFFFF", "body": "D4D4DA", "muted": "8A8A93", "line": "34343B", "accent": "FFC83D", "on_accent": "17171A"},
    # 浅色版，适合打印与正式汇报
    "light": {"bg": "F6F6F3", "panel": "FFFFFF", "title": "17171A", "body": "36363D", "muted": "7C7C85", "line": "DADAD4", "accent": "D9A21B", "on_accent": "17171A"},
}

W, H = 13.333, 7.5          # 16:9（英寸）
L = 0.75                    # 左右边距
CW = W - 2 * L              # 内容宽度
TOP = 1.75                  # 内容区顶部
BOTTOM = 6.75               # 内容区底部

LAYOUTS = ["section", "bullets", "two_column", "cards", "stats", "quote", "table", "closing"]


def _require():
    if Presentation is None:
        raise ToolError("未安装 python-pptx，无法生成演示文稿")


# ─────────────────────────────────────────────
# 绘制工具
# ─────────────────────────────────────────────
def _rgb(hex_color: str):
    return RGBColor.from_string(hex_color)


def _font(run, size: float, color: str, bold: bool = False):
    f = run.font
    f.size = Pt(size)
    f.bold = bold
    f.color.rgb = _rgb(color)
    f.name = FONT_LATIN
    r_pr = run._r.get_or_add_rPr()
    ea = r_pr.find(qn("a:ea"))
    if ea is None:
        ea = OxmlElement("a:ea")
        r_pr.find(qn("a:latin")).addnext(ea)
    ea.set("typeface", FONT_EA)


_BOLD = re.compile(r"(\*\*.+?\*\*)")


def _runs(paragraph, text: str, size: float, color: str, bold: bool = False, strong_color: str = None):
    """写入文字，支持 **加粗**（加粗部分用 strong_color）"""
    for part in _BOLD.split(text):
        if len(part) > 4 and part.startswith("**") and part.endswith("**"):
            _font_run(paragraph, part[2:-2], size, strong_color or color, True)
        elif part:
            _font_run(paragraph, part, size, color, bold)


def _font_run(paragraph, text, size, color, bold):
    run = paragraph.add_run()
    run.text = text
    _font(run, size, color, bold)


def _textbox(slide, x, y, w, h, anchor=MSO_ANCHOR.TOP):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = anchor
    return tf


def _para(tf, first: bool):
    return tf.paragraphs[0] if first else tf.add_paragraph()


def _text(slide, x, y, w, h, text, size, color, bold=False, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP,
          line_spacing=1.15, strong_color=None):
    tf = _textbox(slide, x, y, w, h, anchor)
    for i, line in enumerate(str(text).split("\n")):
        p = _para(tf, i == 0)
        p.alignment = align
        p.line_spacing = line_spacing
        _runs(p, line, size, color, bold, strong_color)
    return tf


def _rect(slide, x, y, w, h, fill: str):
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    shape.fill.solid()
    shape.fill.fore_color.rgb = _rgb(fill)
    shape.line.fill.background()
    shape.shadow.inherit = False
    return shape


def _set_bullet(paragraph, level: int, color: str, size: float):
    p_pr = paragraph._p.get_or_add_pPr()
    hang = Inches(0.3)
    p_pr.set("marL", str(int(hang + Inches(0.4) * (level - 1))))
    p_pr.set("indent", str(-int(hang)))
    bu_clr = OxmlElement("a:buClr")
    srgb = OxmlElement("a:srgbClr")
    srgb.set("val", color)
    bu_clr.append(srgb)
    bu_sz = OxmlElement("a:buSzPct")
    bu_sz.set("val", "70000" if level == 1 else "90000")
    bu_font = OxmlElement("a:buFont")
    bu_font.set("typeface", "Arial")
    bu_char = OxmlElement("a:buChar")
    bu_char.set("char", "■" if level == 1 else "–")
    for el in (bu_clr, bu_sz, bu_font, bu_char):
        p_pr.append(el)


_LIST_MARK = re.compile(r"^([-•*·■]|\d+[.、)])\s+")


def _bullets(slide, x, y, w, h, items: List[str], t: dict, size: float = None, lead: str = ""):
    items = [i for i in (items or []) if str(i).strip()]
    total = sum(len(str(i)) for i in items) + len(lead)
    if size is None:
        size = 22 if len(items) <= 4 and total < 160 else 19 if len(items) <= 6 and total < 280 else 16
    tf = _textbox(slide, x, y, w, h)
    first = True
    if lead:
        p = _para(tf, True)
        p.line_spacing = 1.2
        p.space_after = Pt(size * 0.8)
        _runs(p, lead, size, t["body"], strong_color=t["title"])
        first = False
    for item in items:
        raw = str(item)
        level = 2 if raw.startswith(("  ", "\t")) else 1
        p = _para(tf, first)
        first = False
        p.line_spacing = 1.15
        p.space_before = Pt(size * (0.3 if level == 2 else 0.75))
        _set_bullet(p, level, t["accent"] if level == 1 else t["muted"], size)
        _runs(p, _LIST_MARK.sub("", raw.strip()), size if level == 1 else size - 3,
              t["body"] if level == 1 else t["muted"], strong_color=t["title"])
    return tf


def _background(slide, t: dict):
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = _rgb(t["bg"])


def _chrome(slide, t: dict, title: str, page: int, deck_title: str):
    """内容页通用框架：左侧强调条 + 标题 + 细分割线 + 页脚"""
    _background(slide, t)
    _rect(slide, L, 0.58, 0.08, 0.56, t["accent"])
    _text(slide, L + 0.28, 0.45, CW - 0.28, 0.82, title, 28 if len(title) <= 22 else 24, t["title"], bold=True,
          anchor=MSO_ANCHOR.MIDDLE)
    _rect(slide, L, 1.38, CW, 0.014, t["line"])
    _text(slide, L, 6.98, 8, 0.3, deck_title, 10, t["muted"])
    _text(slide, W - L - 1.5, 6.98, 1.5, 0.3, f"{page:02d}", 10, t["muted"], bold=True, align=PP_ALIGN.RIGHT)


# ─────────────────────────────────────────────
# 版式
# ─────────────────────────────────────────────
def _cover(slide, t, title, subtitle, meta, closing=False):
    _background(slide, t)
    _rect(slide, 0, 0, 0.2, H, t["accent"])
    if meta:
        _text(slide, L + 0.25, 0.75, CW, 0.4, meta, 13, t["muted"])
    _text(slide, L + 0.25, 1.6, CW - 1.0, 2.6, title, 44 if len(title) <= 18 else 36, t["title"], bold=True,
          anchor=MSO_ANCHOR.BOTTOM, line_spacing=1.05)
    _rect(slide, L + 0.27, 4.42, 1.1, 0.07, t["accent"])
    if subtitle:
        _text(slide, L + 0.25, 4.75, CW - 1.5, 1.4, subtitle, 20, t["body"], line_spacing=1.25)
    if closing:
        _rect(slide, W - L - 3.2, H - 0.9, 3.2, 0.014, t["line"])


def _section(slide, t, spec, index):
    _background(slide, t)
    _text(slide, L, 1.9, 4, 1.4, f"{index:02d}", 80, t["accent"], bold=True, anchor=MSO_ANCHOR.BOTTOM)
    _rect(slide, L + 0.05, 3.5, CW, 0.014, t["line"])
    _text(slide, L, 3.75, CW, 1.1, spec.get("title", ""), 36, t["title"], bold=True)
    if spec.get("subtitle"):
        _text(slide, L, 4.85, CW * 0.8, 1.2, spec["subtitle"], 18, t["muted"], line_spacing=1.25)


def _two_column(slide, t, spec):
    col_w = (CW - 0.8) / 2
    for i, key in enumerate(("left", "right")):
        col = spec.get(key) or {}
        x = L + i * (col_w + 0.8)
        _rect(slide, x, TOP, 0.9, 0.06, t["accent"])
        _text(slide, x, TOP + 0.2, col_w, 0.6, col.get("heading", ""), 20, t["title"], bold=True)
        _bullets(slide, x, TOP + 0.9, col_w, BOTTOM - TOP - 0.9, col.get("items") or [], t,
                 size=17 if sum(len(s) for s in col.get("items") or []) < 200 else 15)
    _rect(slide, L + col_w + 0.39, TOP + 0.1, 0.014, BOTTOM - TOP - 0.3, t["line"])


def _cards(slide, t, spec):
    cards = (spec.get("cards") or [])[:4]
    if not cards:
        raise ToolError("cards 版式缺少 cards")
    gap = 0.35
    n = len(cards)
    card_w = (CW - gap * (n - 1)) / n
    card_h = BOTTOM - TOP - 0.2
    longest = max(len(c.get("text", "")) for c in cards)
    body_size = 16 if longest < 60 and n <= 3 else 14 if longest < 120 else 12
    for i, card in enumerate(cards):
        x = L + i * (card_w + gap)
        _rect(slide, x, TOP + 0.1, card_w, card_h, t["panel"])
        _rect(slide, x, TOP + 0.1, card_w, 0.06, t["accent"])
        _text(slide, x + 0.3, TOP + 0.45, card_w - 0.6, 0.4, f"{i + 1:02d}", 14, t["accent"], bold=True)
        _text(slide, x + 0.3, TOP + 0.9, card_w - 0.6, 0.9, card.get("heading", ""), 20 if n <= 3 else 18,
              t["title"], bold=True, line_spacing=1.1)
        _text(slide, x + 0.3, TOP + 1.9, card_w - 0.6, card_h - 2.1, card.get("text", ""), body_size, t["body"],
              line_spacing=1.3, strong_color=t["title"])


def _stats(slide, t, spec):
    stats = (spec.get("stats") or [])[:4]
    if not stats:
        raise ToolError("stats 版式缺少 stats")
    n = len(stats)
    gap = 0.4
    col_w = (CW - gap * (n - 1)) / n
    y = TOP + 0.6
    if spec.get("text"):
        _text(slide, L, TOP, CW, 0.6, spec["text"], 18, t["body"], strong_color=t["title"])
        y = TOP + 1.0
    for i, st in enumerate(stats):
        x = L + i * (col_w + gap)
        value = str(st.get("value", ""))
        _text(slide, x, y, col_w, 1.4, value, 54 if len(value) <= 6 else 40, t["accent"], bold=True,
              anchor=MSO_ANCHOR.BOTTOM)
        _rect(slide, x, y + 1.55, col_w, 0.014, t["line"])
        _text(slide, x, y + 1.75, col_w, 0.5, st.get("label", ""), 18, t["title"], bold=True)
        if st.get("note"):
            _text(slide, x, y + 2.35, col_w, 1.6, st["note"], 14, t["muted"], line_spacing=1.3)


def _quote(slide, t, spec, page, deck_title):
    _background(slide, t)
    _text(slide, L, 0.6, 2, 2.1, "“", 120, t["accent"], bold=True, line_spacing=1.0)
    quote = spec.get("text") or spec.get("title") or ""
    _text(slide, L + 0.9, 2.2, CW - 1.8, 3.0, quote, 30 if len(quote) <= 40 else 24, t["title"], bold=True,
          anchor=MSO_ANCHOR.MIDDLE, line_spacing=1.3)
    if spec.get("author"):
        _text(slide, L + 0.9, 5.4, CW - 1.8, 0.5, f"—— {spec['author']}", 16, t["muted"])
    _text(slide, W - L - 1.5, 6.98, 1.5, 0.3, f"{page:02d}", 10, t["muted"], bold=True, align=PP_ALIGN.RIGHT)


def _table(slide, t, spec):
    rows = [list(map(str, r)) for r in (spec.get("rows") or []) if r]
    if not rows:
        raise ToolError("table 版式缺少 rows")
    cols = max(len(r) for r in rows)
    n_rows = len(rows)
    y = TOP
    if spec.get("text"):
        _text(slide, L, TOP, CW, 0.5, spec["text"], 16, t["body"])
        y = TOP + 0.65
    row_h = min(0.6, (BOTTOM - y) / n_rows)
    size = 14 if n_rows <= 7 and cols <= 5 else 12 if n_rows <= 11 else 10
    frame = slide.shapes.add_table(n_rows, cols, Inches(L), Inches(y), Inches(CW), Inches(row_h * n_rows))
    table = frame.table
    for r in range(n_rows):
        table.rows[r].height = Inches(row_h)
        for c in range(cols):
            cell = table.cell(r, c)
            cell.fill.solid()
            if r == 0:
                cell.fill.fore_color.rgb = _rgb(t["accent"])
            else:
                cell.fill.fore_color.rgb = _rgb(t["panel"] if r % 2 else t["bg"])
            cell.margin_left = cell.margin_right = Inches(0.12)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            tf = cell.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            text = rows[r][c] if c < len(rows[r]) else ""
            _runs(p, text, size, t["on_accent"] if r == 0 else t["body"], bold=(r == 0), strong_color=t["title"])


def _build_slide(prs, t, spec: dict, page: int, section_index: int, deck_title: str):
    layout = (spec.get("layout") or "bullets").lower()
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # 空白版式，全部元素自行绘制
    title = spec.get("title", "")
    if layout == "section":
        _section(slide, t, spec, section_index)
    elif layout == "closing":
        _cover(slide, t, title or "谢谢", spec.get("subtitle", ""), spec.get("text", ""), closing=True)
    elif layout == "quote":
        _quote(slide, t, spec, page, deck_title)
    else:
        _chrome(slide, t, title, page, deck_title)
        if layout == "bullets":
            _bullets(slide, L + 0.28, TOP, CW - 0.28, BOTTOM - TOP, spec.get("items") or [], t,
                     lead=spec.get("text", ""))
        elif layout == "two_column":
            _two_column(slide, t, spec)
        elif layout == "cards":
            _cards(slide, t, spec)
        elif layout == "stats":
            _stats(slide, t, spec)
        elif layout == "table":
            _table(slide, t, spec)
        else:
            raise ToolError(f"未知版式：{layout}（可用：{', '.join(LAYOUTS)}）")
    if spec.get("notes"):
        slide.notes_slide.notes_text_frame.text = spec["notes"]


# ─────────────────────────────────────────────
# 工具
# ─────────────────────────────────────────────
def _ppt_create(ctx: ToolContext, args: dict) -> str:
    _require()
    title = (args.get("title") or "").strip() or "未命名演示"
    slides = args.get("slides") or []
    if not slides:
        raise ToolError("slides 不能为空")
    theme = dict(THEMES.get((args.get("theme") or "dark").lower(), THEMES["dark"]))
    accent = (args.get("accent") or "").strip().lstrip("#")
    if re.fullmatch(r"[0-9a-fA-F]{6}", accent):
        theme["accent"] = accent.upper()

    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(W), Inches(H)
    prs.core_properties.title = title

    cover = prs.slides.add_slide(prs.slide_layouts[6])
    _cover(cover, theme, title, args.get("subtitle", ""), args.get("meta", ""))

    section_index = 0
    for page, spec in enumerate(slides, start=2):
        if (spec.get("layout") or "").lower() == "section":
            section_index += 1
        _build_slide(prs, theme, spec, page, section_index, title)

    path = ctx.output_path(args.get("filename") or title, ".pptx")
    prs.save(str(path))
    ctx.record(path)
    return f"已生成演示文稿：{ctx.display(path)}（共 {len(slides) + 1} 页，含封面）"


def _ppt_read(ctx: ToolContext, args: dict) -> str:
    _require()
    path = ctx.input_path(args.get("path", ""))
    if path.suffix.lower() != ".pptx":
        raise ToolError("只支持 .pptx 格式")
    prs = Presentation(str(path))
    out = [f"文件：{ctx.display(path)}，共 {len(prs.slides)} 页"]
    for i, slide in enumerate(prs.slides, start=1):
        texts = []
        for shape in slide.shapes:
            if shape.has_text_frame:
                text = shape.text_frame.text.strip()
                if text:
                    texts.append(text)
            elif getattr(shape, "has_table", False) and shape.has_table:
                for row in shape.table.rows:
                    texts.append("| " + " | ".join(c.text.strip() for c in row.cells) + " |")
        out.append(f"\n## 第 {i} 页\n" + "\n".join(texts))
        if slide.has_notes_slide:
            notes = slide.notes_slide.notes_text_frame.text.strip()
            if notes:
                out.append(f"（备注）{notes}")
    body = "\n".join(out)
    limit = int(args.get("max_chars") or 15000)
    return body[:limit] + (f"\n……（仅显示前 {limit} 字）" if len(body) > limit else "")


_ITEMS = {"type": "array", "items": {"type": "string"}}
SLIDE_SCHEMA = {
    "type": "object",
    "properties": {
        "layout": {"type": "string", "enum": LAYOUTS},
        "title": {"type": "string", "description": "页面标题，尽量写成结论句"},
        "subtitle": {"type": "string", "description": "section / closing 的副标题"},
        "text": {"type": "string", "description": "bullets / stats / table 顶部的导语；quote 的引文；closing 的补充信息"},
        "items": {**_ITEMS, "description": "bullets 的要点；两个空格开头为二级要点；可用 **加粗**"},
        "left": {"type": "object", "properties": {"heading": {"type": "string"}, "items": _ITEMS}},
        "right": {"type": "object", "properties": {"heading": {"type": "string"}, "items": _ITEMS}},
        "cards": {
            "type": "array",
            "description": "2–4 张并列卡片",
            "items": {"type": "object", "properties": {"heading": {"type": "string"}, "text": {"type": "string"}}},
        },
        "stats": {
            "type": "array",
            "description": "2–4 个关键数字",
            "items": {
                "type": "object",
                "properties": {
                    "value": {"type": "string", "description": "如 98%、3.2 亿、+15"},
                    "label": {"type": "string"},
                    "note": {"type": "string"},
                },
            },
        },
        "rows": {"type": "array", "items": _ITEMS, "description": "table 的行，第一行为表头"},
        "author": {"type": "string", "description": "quote 的出处"},
        "notes": {"type": "string", "description": "本页演讲备注"},
    },
    "required": ["layout"],
}

SKILL = Skill(
    id="slides",
    name="演示文稿",
    summary="按版式生成设计统一的 PPT：封面、分节、要点、对比、卡片、数据、表格",
    requires=("pptx",),
    instructions="""【演示文稿】
- 用 ppt_create 一次生成整份 PPT，封面会根据 title / subtitle / meta 自动生成。
- 版式：section 分节页、bullets 要点、two_column 对比、cards 2–4 张并列卡片、stats 2–4 个关键数字、quote 引言、table 表格、closing 结束页。
- 设计要求：每页只讲一个观点，标题写成结论句；要点 3–6 条，每条尽量不超过 30 字；相邻页面换用不同版式，不要整份都是 bullets；数字优先用 stats，并列概念用 cards，对比用 two_column。
- 结构一般 8–15 页：背景 / 目录 → 分节内容 → 总结 → closing；每页在 notes 写演讲备注。
- theme 默认 dark（深灰底、黄色强调色）；正式汇报或需要打印时用 light。
- 修改已有 PPT：先 ppt_read 读取内容，再用 ppt_create 生成新版本（文件名加「v2」）。""",
    tools=[
        Tool(
            "ppt_create",
            "生成一份 16:9 演示文稿（.pptx），保存到工作区。封面自动生成，slides 为封面之后的各页。",
            schema(
                {
                    "filename": {"type": "string", "description": "文件名，可不带扩展名"},
                    "title": {"type": "string", "description": "演示标题（封面大标题，也显示在页脚）"},
                    "subtitle": {"type": "string", "description": "封面副标题"},
                    "meta": {"type": "string", "description": "封面顶部的小字，如「2026.11 · 部门名」"},
                    "theme": {"type": "string", "enum": ["dark", "light"]},
                    "accent": {"type": "string", "description": "强调色十六进制（可选），如 FFC83D"},
                    "slides": {"type": "array", "items": SLIDE_SCHEMA},
                },
                ["filename", "title", "slides"],
            ),
            _ppt_create,
            "制作演示文稿",
        ),
        Tool(
            "ppt_read",
            "读取 .pptx 每一页的文字、表格与备注，用于总结或改版。",
            schema(
                {
                    "path": {"type": "string", "description": "文件路径；相对路径相对于工作区"},
                    "max_chars": {"type": "integer", "description": "最多返回的字数，默认 15000"},
                },
                ["path"],
            ),
            _ppt_read,
            "阅读演示文稿",
        ),
    ],
)
