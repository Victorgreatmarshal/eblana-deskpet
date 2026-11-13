"""
去 AI 腔（humanize）：文风守则 + 套话检测 + 改写。

只靠提示词禁不住模型的口癖，所以分三层：
1. 守则写进系统提示词，从源头少说；
2. 流式输出时逐句检查，命中的句子不显示；
3. 回复结束后若仍有命中，让模型按原意改写（最多两次），还不行就删掉命中的分句。

规则针对的是「用法」而不是单字：稳、轻、重这些字在「稳定」「重要」「轻松」里照常使用，
只有拿来给学者的话、声音、状态打分（这句话稳、比刚才轻、很平）时才算套话。
"""
import re
from typing import Iterable, List, Tuple

from .base import Skill

# 分句内的「任意几个字」
_W = r"[^，。！？、；：,.!?;:\s“”\"]{1,8}"
# 后面紧跟标点或结尾（避免误伤「很重要」「很平静」）
_END = r"(?=[，。！？…、；：,.!?;:\s“”\"’）)~～]|$)"
# 允许再跟一个「了 / 些 / 点」
_END2 = r"(?=[了些点]|[，。！？…、；：,.!?;:\s“”\"’）)~～]|$)"
_ADJ = "稳重沉轻平直硬实响"

BUILTIN_RULES: List[Tuple[str, str]] = [
    # ── 给对方的话 / 声音 / 状态打分 ──
    ("评价话的分量", rf"(这|那|你这|你那|你刚才那)?(句)?话(说得|说的)?(很|更|挺|倒是|真|也|够)?[{_ADJ}]{_END2}"),
    ("评价话的分量", rf"(这|那)(句)?话(说得|说的|接得|接的)(很|真|挺)?(漂亮|好){_END}"),
    ("评价声音状态", r"(声音|嗓音|语气|口气|呼吸|手)(没抖|没颤|不抖了|稳了|平了|沉了|轻了|比刚才)"),
    ("和之前比较", rf"比(之前|刚才|以前|上次|往常|平时|方才|那时|那会儿|谁)(的)?(都|还|更|要)?[{_ADJ}强]{_END2}"),
    ("和之前比较", rf"比{_W}(还|更|都|要)?[稳沉轻重]{_END2}"),
    ("单字评价", rf"很[{_ADJ}]{_END}"),
    ("单字评价", r"(^|[。！？\n])\s*(稳|很稳|够稳|挺稳)[。！]?\s*(?=$|\n)"),
    ("说得响", r"比谁都响"),
    # ── 空洞的记下 / 收下 / 认下 ──
    ("空洞确认", r"我(都|已经|就)?(记下|记住|收下)(了|来了)"),
    ("空洞确认", r"我记得了"),
    ("空洞确认", r"(这话|这句话|这句|你这话|你这句话|这个账|这笔账|这份情|这事)(我)?(记|收|留|认)(下|住|着)(了)?"),
    ("空洞确认", r"(他|她|ta|TA|它)记得这(事|件事|句话)"),
    ("认下", r"(?<![确承否公体默辨指识])认(你|这个|下来|得实|得清)"),
    ("认下", r"就是认了"),
    ("认下", rf"我认{_END}"),
    ("认下", r"收不回去"),
    # ── 守护者 / 放行 / 不催 ──
    ("守护套话", r"我守着"),
    ("守护套话", r"回去睡"),
    ("守护套话", rf"(你去[，,]\s*)?我跟{_END}"),
    ("放行套话", rf"我?不拦(你)?{_END}"),
    ("放行套话", rf"我?不催(你)?{_END}"),
    ("放行套话", r"掂量"),
    # ── 接话 / 反问套路 ──
    ("接话套路", r"(没|不)接(你)?(的|那句|这句|这话)"),
    ("接话套路", r"这(句)?话我不接"),
    ("接话套路", r"接(的|得)(很|真|挺)?漂亮"),
    ("反问套路", r"问别人还是问自己"),
    ("反问套路", r"(告诉|教)你的[，,]?\s*还是你自己"),
    ("反问套路", r"还是你自己(想|悟|琢磨)(明白|出来|通)的"),
    # ── 其他 ──
    ("心思写脸上", r"(心思|心事|想法)都写(在|着)"),
    ("行开头", r"(^|[。！？\n])\s*行[，,]"),
    ("动作旁白", r"[（(][^（）()\n]{0,10}(笑|叹|挑眉|垂眸|抬眼|低头|顿了顿|靠近|轻声|眯眼|勾唇)[^（）()\n]{0,8}[）)]"),
    ("动作旁白", r"(?<!\*)\*(?!\*)[^*\n]{1,20}(?<!\*)\*(?!\*)"),  # *挑眉*，不含 Markdown 的 **加粗**
]

_COMPILED = [(label, re.compile(rx)) for label, rx in BUILTIN_RULES]
_WILDCARD = re.compile(r"(xx+|XX+|…+|\.{3,}|＊|\*)")


def compile_extra(lines: Iterable[str]) -> List[Tuple[str, "re.Pattern"]]:
    """用户在设置里写的说法：每行一条，xx 表示任意几个字"""
    rules = []
    for raw in lines or []:
        line = raw.strip().strip("“”\"「」")
        if not line:
            continue
        parts = _WILDCARD.split(line)
        rx = "".join(_W if _WILDCARD.fullmatch(p) else re.escape(p) for p in parts if p)
        if rx:
            rules.append(("自定义", re.compile(rx)))
    return rules


def find_hits(text: str, extra: Iterable[str] = ()) -> List[str]:
    hits = []
    for _label, rx in _COMPILED + compile_extra(extra):
        for m in rx.finditer(text or ""):
            frag = m.group(0).strip("，。！？\n ")
            if frag and frag not in hits:
                hits.append(frag)
    # 去掉被更长片段包含的重复命中
    return [h for h in hits if not any(h != other and h in other for other in hits)]


_SENTENCE = re.compile(r"[^。！？\n]*[。！？\n]+|[^。！？\n]+$")
_CLAUSE = re.compile(r"[^，；…]*[，；…]+|[^，；…]+$")
_PUNCT = re.compile(r"[，。！？；…、\s]")


def scrub(text: str, extra: Iterable[str] = ()) -> str:
    """删掉含套话的分句（兜底手段，也用于清理历史记录）；删完只剩几个字的句子整句去掉"""
    rules = _COMPILED + compile_extra(extra)
    out = []
    for sentence in _SENTENCE.findall(text or ""):
        if not any(rx.search(sentence) for _l, rx in rules):
            out.append(sentence)
            continue
        kept = "".join(c for c in _CLAUSE.findall(sentence) if not any(rx.search(c) for _l, rx in rules))
        if len(_PUNCT.sub("", kept)) <= 4:
            continue
        out.append(re.sub(r"[，、；]+$", "。", kept.rstrip()))
    return re.sub(r"^[，、；：,]+", "", "".join(out).strip())


def safe_prefix(text: str, extra: Iterable[str] = ()) -> Tuple[str, bool]:
    """
    流式显示用：返回 (可以显示的完整句子前缀, 是否已出现套话)。
    只放出已经说完的句子，句子里有套话就停在它前面。
    """
    rules = _COMPILED + compile_extra(extra)
    shown = ""
    for sentence in re.findall(r"[^。！？\n]*[。！？\n]+", text or ""):
        if any(rx.search(shown + sentence) for _l, rx in rules):
            return shown, True
        shown += sentence
    return shown, False


def rewrite_messages(persona: str, text: str, hits: List[str]) -> List[dict]:
    listed = "、".join(f"「{h}」" for h in hits)
    return [
        {"role": "system", "content": persona + "\n\n" + GUIDE},
        {
            "role": "user",
            "content": (
                "下面是你准备说给学者的话，其中出现了套话：" + listed + "。\n"
                "请改写这段话：意思和死芒的口吻不变，长度相近；没有信息量的套话直接删掉，"
                "需要表达的意思换成具体、自然的说法；不要用守则里列出的任何说法；"
                "只输出改写后的台词本身，不要解释。\n\n原话：\n" + text
            ),
        },
    ]


GUIDE = """【说话方式（去 AI 腔）】
你的台词要像一个活生生的人在说话。
- 回应学者说的内容本身，不点评学者「说话的方式」：不说某句话稳、重、轻、沉、平、直、响、漂亮，不拿它和「之前」「刚才」比较，也不评价对方的声音、语气、手有没有抖。
- 不做空洞的确认：不说「我记下了 / 记住了 / 收下了」「这话我留着」「这个账我记着」「认你 / 我认 / 认下来」。真要记住什么，就说出记住了哪一点、会怎么用。
- 不用守护者式与放行式套话：「睡吧，我守着」「你去，我跟」「我不拦」「我不催你」「你自己掂量」「回去睡」。
- 不用接话、反问套路：「没接你那句」「这句话我不接」「这话是谁告诉你的，还是你自己想明白的」「问别人还是问自己」。
- 不以「行，……」开头表示接受；不写括号或星号里的动作旁白，如「（轻笑）」「*挑眉*」。
- 不要每句都只有几个字、故作深沉；不要用三段排比或「不是……而是……」制造金句。
- 死芒的味道来自具体的事实、细节和慵懒的反问：提具体的东西（档案里的经历、学者此刻在做的事、手边的物件），而不是抽象的「分量」。宁可多说一句有内容的话，也不说一句空的漂亮话。"""


SKILL = Skill(
    id="humanize",
    name="去 AI 腔",
    summary="避免套话与 AI 腔句式；检测到时自动改写",
    instructions=GUIDE,
    tools=[],
    listed=False,  # 在设置的「文风」分区单独显示
)
