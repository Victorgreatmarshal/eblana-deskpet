import html
import platform
import re
import webbrowser
from pathlib import Path
from typing import List, Tuple
from PyQt6.QtCore import QObject, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPalette, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

import llm
import providers
import skills
import theme
from agent import describe_api_error
from skills import humanize
from assets_manager import EXPRESSION_IDS
from config import EBLANA_SYSTEM_PROMPT, ConfigManager, OFFICIAL_ASSETS_DIR, set_windows_autostart

IS_WINDOWS = platform.system() == "Windows"

APPEARANCE_OPTIONS = [
    ("exp_calm", "剧情立绘（表情随对话变化）"),
    ("idle", "默认立绘"),
    ("special", "精英二立绘"),
    ("skin_summer", "时装 · 夏卉 FA161"),
    ("skin_ambience", "时装 · 晶化信念"),
    ("chibi", "Q 版小人"),
]

def tool_status_text(tool_name: str) -> str:
    return f"{skills.tool_status(tool_name)}…"


def _link(href: str, text: str) -> str:
    return f'<a href="{href}" style="color:{theme.ACCENT}; text-decoration:none;">{html.escape(text)}</a>'


def _elide(text: str, limit: int = 26) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


# 气泡只放得下短句：长回复截断，完整内容在「对话记录」里看
PREVIEW_CHARS = 150
_MD_FENCE = re.compile(r"```.*?(```|$)", re.S)
_MD_MARKS = re.compile(r"\*\*|__|`|^#{1,6}\s*", re.M)


def bubble_preview(text: str) -> Tuple[str, bool]:
    """返回 (气泡里显示的文字, 是否需要「查看全文」)"""
    plain = _MD_FENCE.sub("〔代码见对话记录〕", text)
    plain = re.sub(r"\n{3,}", "\n\n", _MD_MARKS.sub("", plain)).strip()
    needs_full = "```" in text
    if len(plain) > PREVIEW_CHARS:
        cut = plain[:PREVIEW_CHARS]
        idx = max(cut.rfind(ch) for ch in "。！？；\n")
        if idx > PREVIEW_CHARS * 0.6:
            cut = cut[: idx + 1]
        return cut.rstrip() + "……", True
    return plain, needs_full


def _apply_tool_window_flags(widget: QWidget):
    widget.setWindowFlags(
        Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool
    )
    widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    # macOS 默认会在应用失去焦点时隐藏 Tool 窗口
    widget.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow)


# ─────────────────────────────────────────────
# 小部件工厂
# ─────────────────────────────────────────────
class WrapLabel(QLabel):
    """自动换行且随文字增减调整高度的标签（表单里的普通换行标签换行后高度不会更新，会与下一行重叠）"""

    def __init__(self, text: str = "", role: str = ""):
        super().__init__(text)
        if role:
            self.setProperty("role", role)
        self.setWordWrap(True)

    def setText(self, text: str):
        super().setText(text)
        self._fit()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit()

    def _fit(self):
        width = self.width() if self.width() > 50 else 420
        self.setMinimumHeight(self.heightForWidth(width) if self.text() else 0)


def _label(text: str, role: str = "", wrap: bool = False) -> QLabel:
    lbl = QLabel(text)
    if role:
        lbl.setProperty("role", role)
    lbl.setWordWrap(wrap)
    return lbl


def _rule() -> QFrame:
    line = QFrame()
    line.setProperty("role", "rule")
    return line


def _section(title: str, tag: str) -> QHBoxLayout:
    row = QHBoxLayout()
    row.setSpacing(8)
    row.addWidget(_label(title, "section"))
    row.addWidget(_label(tag, "tag"))
    row.addWidget(_rule(), stretch=1)
    return row


def _header(title: str, tag: str, quote: str = "", avatar: QLabel = None) -> QHBoxLayout:
    row = QHBoxLayout()
    row.setSpacing(12)
    if avatar is not None:
        row.addWidget(avatar, alignment=Qt.AlignmentFlag.AlignTop)

    bar = QFrame()
    bar.setProperty("role", "accentBar")
    row.addWidget(bar)

    text_box = QVBoxLayout()
    text_box.setSpacing(2)
    text_box.addWidget(_label(title, "title"))
    text_box.addWidget(_label(tag, "tag"))
    if quote:
        text_box.addSpacing(6)
        text_box.addWidget(_label(quote, "quote", wrap=True))
    text_box.addStretch()
    row.addLayout(text_box, stretch=1)
    return row


def _button(text: str, role: str = "") -> QPushButton:
    btn = QPushButton(text)
    if role:
        btn.setProperty("role", role)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    return btn


def _avatar_label(size: int, dpr: float) -> QLabel:
    lbl = QLabel()
    lbl.setFixedSize(size + 2, size + 2)
    lbl.setStyleSheet(f"border: 1px solid {theme.LINE}; background: {theme.FIELD};")
    for name, crop in (("avatar_e2.png", (0, 40, 180, 180)), ("avatar_e0.png", None)):
        path = OFFICIAL_ASSETS_DIR / name
        if not path.exists():
            continue
        pix = QPixmap(str(path))
        if crop and pix.width() >= crop[2] and pix.height() >= crop[1] + crop[3]:
            pix = pix.copy(*crop)
        pix = pix.scaled(
            round(size * dpr),
            round(size * dpr),
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        pix.setDevicePixelRatio(dpr)
        lbl.setPixmap(pix)
        break
    return lbl


def _fill_appearance_combo(combo: QComboBox, current: str):
    """表情差分统一归到「剧情立绘」一项；不在列表里的自定义形象单独列出，避免保存时被重置"""
    option_ids = [act_id for act_id, _ in APPEARANCE_OPTIONS]
    if current not in option_ids and current not in EXPRESSION_IDS:
        combo.addItem(f"当前形象（{current}）", userData=current)
    for act_id, label in APPEARANCE_OPTIONS:
        combo.addItem(label, userData=act_id)
    target = "exp_calm" if current in EXPRESSION_IDS else current
    idx = combo.findData(target)
    combo.setCurrentIndex(max(0, idx))


def _chosen_appearance(combo: QComboBox, current: str) -> str:
    chosen = combo.currentData()
    # 选的仍是「剧情立绘」时，保留当前正在使用的那张表情
    if chosen == "exp_calm" and current in EXPRESSION_IDS:
        return current
    return chosen


def _provider_combo(current: str) -> QComboBox:
    """按「国内 / 国际 / 聚合与本地」分组的服务商下拉框（分组标题不可选）"""
    combo = QComboBox()
    combo.setMaxVisibleItems(20)
    item_model = combo.model()
    for group in providers.GROUPS:
        combo.addItem(f"—— {group} ——", userData=None)
        item_model.item(combo.count() - 1).setEnabled(False)
        for p in providers.PROVIDER_LIST:
            if p.group == group:
                combo.addItem(p.name, userData=p.id)
    idx = combo.findData(current)
    combo.setCurrentIndex(idx if idx >= 0 else combo.findData("deepseek"))
    return combo


def _provider_key(config: ConfigManager, provider: str) -> str:
    keys = config.get("provider_keys") or {}
    if provider in keys:
        return keys[provider]
    return config.get("api_key", "") if provider == config.get("provider", "deepseek") else ""


# ─────────────────────────────────────────────
# 后台请求：测试连接、获取模型列表（不阻塞界面）
# ─────────────────────────────────────────────
class ApiTestWorker(QThread):
    done = pyqtSignal(bool, str)

    def __init__(self, provider_id: str, api_key: str, base_url: str, model: str, parent: QObject = None):
        super().__init__(parent)
        self.args = (provider_id, api_key, base_url, model)

    def run(self):
        provider_id, api_key, base_url, model = self.args
        try:
            client = llm.make_client(provider_id, api_key, base_url, timeout=25, max_retries=0)
            llm.complete_text(client, model=model, messages=[{"role": "user", "content": "ping"}], max_tokens=16)
            self.done.emit(True, "连接正常")
        except Exception as e:
            self.done.emit(False, f"连接失败：{describe_api_error(e)}")


class ModelListWorker(QThread):
    done = pyqtSignal(list, str)

    def __init__(self, provider_id: str, api_key: str, base_url: str, parent: QObject = None):
        super().__init__(parent)
        self.args = (provider_id, api_key, base_url)

    def run(self):
        try:
            client = llm.make_client(*self.args, timeout=25, max_retries=0)
            self.done.emit(llm.list_models(client), "")
        except Exception as e:
            self.done.emit([], describe_api_error(e))


def _start_worker(worker: QThread, on_done):
    # 父对象设为 QApplication：窗口提前关闭也不会销毁仍在运行的线程
    worker.setParent(QApplication.instance())
    worker.done.connect(on_done)
    worker.finished.connect(worker.deleteLater)
    worker.start()


class ApiKeyPanel(QWidget):
    """API Key 输入框 + 显示/隐藏 + 测试连接 + 状态提示"""

    def __init__(self, api_key: str, endpoint_getter, parent=None):
        super().__init__(parent)
        self._endpoint_getter = endpoint_getter  # () -> (provider_id, base_url, model)
        self.needs_key = True

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        row = QHBoxLayout()
        row.setSpacing(6)
        self.key_edit = QLineEdit(api_key)
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setPlaceholderText("粘贴 API Key")
        row.addWidget(self.key_edit, stretch=1)

        self.show_btn = _button("显示")
        self.show_btn.setCheckable(True)
        self.show_btn.toggled.connect(self._toggle_visible)
        row.addWidget(self.show_btn)

        self.test_btn = _button("测试连接")
        self.test_btn.clicked.connect(self._test)
        row.addWidget(self.test_btn)
        layout.addLayout(row)

        status_row = QHBoxLayout()
        self.status_lbl = WrapLabel("", "hint")
        status_row.addWidget(self.status_lbl, stretch=1)
        self.key_url = ""
        self.get_key_btn = _button("获取 API Key", "link")
        self.get_key_btn.clicked.connect(lambda: self.key_url and webbrowser.open(self.key_url))
        status_row.addWidget(self.get_key_btn)
        layout.addLayout(status_row)

    def set_provider(self, preset, api_key: str):
        self.key_url = preset.key_url
        self.needs_key = preset.needs_key
        self.get_key_btn.setText("获取 API Key" if preset.needs_key else "下载 Ollama")
        self.get_key_btn.setVisible(bool(preset.key_url))
        self.key_edit.setEnabled(preset.needs_key)
        self.show_btn.setEnabled(preset.needs_key)
        self.key_edit.setPlaceholderText("粘贴 API Key" if preset.needs_key else "本地服务无需 API Key")
        self.key_edit.setText(api_key if preset.needs_key else "")

    def key(self) -> str:
        return self.key_edit.text().strip()

    def set_hint(self, text: str):
        self._set_status(text, theme.TEXT_DIM)

    def _set_status(self, text: str, color: str):
        self.status_lbl.setText(text)
        self.status_lbl.setStyleSheet(f"color: {color};")

    def _toggle_visible(self, checked: bool):
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password)
        self.show_btn.setText("隐藏" if checked else "显示")

    def _test(self):
        provider_id, base_url, model = self._endpoint_getter()
        if self.needs_key and not self.key():
            self._set_status("请先填写 API Key", theme.ERROR)
            return
        if not base_url:
            self._set_status("请先填写 Base URL", theme.ERROR)
            return
        if not model:
            self._set_status("请先选择模型", theme.ERROR)
            return
        self.test_btn.setDisabled(True)
        self._set_status("正在测试…", theme.TEXT_DIM)
        _start_worker(ApiTestWorker(provider_id, self.key(), base_url, model), self._on_test_done)

    def _on_test_done(self, ok: bool, message: str):
        self.test_btn.setDisabled(False)
        self._set_status(message, theme.OK if ok else theme.ERROR)


class ModelPicker(QWidget):
    """可手填的模型下拉框 + 「获取列表」"""

    def __init__(self, context_getter, parent=None):
        super().__init__(parent)
        self._context_getter = context_getter  # () -> (provider_id, api_key, base_url)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        row = QHBoxLayout()
        row.setSpacing(6)
        self.combo = QComboBox()
        self.combo.setEditable(True)
        self.combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.combo.setMaxVisibleItems(18)
        row.addWidget(self.combo, stretch=1)
        self.fetch_btn = _button("获取列表")
        self.fetch_btn.clicked.connect(self._fetch)
        row.addWidget(self.fetch_btn)
        layout.addLayout(row)
        self.hint = WrapLabel("", "hint")
        layout.addWidget(self.hint)

    def set_options(self, models, current: str, note: str = ""):
        self.combo.clear()
        self.combo.addItems(list(models))
        self.combo.setEditText(current)
        self.combo.lineEdit().setPlaceholderText("模型名称")
        self.hint.setText(note)
        self.hint.setStyleSheet("")

    def model(self) -> str:
        return self.combo.currentText().strip()

    def _fetch(self):
        provider_id, api_key, base_url = self._context_getter()
        if not base_url:
            self._set_hint("请先填写 Base URL", theme.ERROR)
            return
        if providers.get(provider_id).needs_key and not api_key:
            self._set_hint("请先填写 API Key，再获取模型列表", theme.ERROR)
            return
        self.fetch_btn.setDisabled(True)
        self._set_hint("正在获取模型列表…", theme.TEXT_DIM)
        _start_worker(ModelListWorker(provider_id, api_key, base_url), self._on_fetched)

    def _on_fetched(self, ids: list, error: str):
        self.fetch_btn.setDisabled(False)
        if error or not ids:
            self._set_hint(f"获取失败：{error or '列表为空'}。可以直接手动填写模型名称。", theme.ERROR)
            return
        current = self.model()
        self.combo.clear()
        self.combo.addItems(ids)
        self.combo.setEditText(current if current else ids[0])
        self._set_hint(f"共 {len(ids)} 个模型，可在下拉框中选择或直接输入。", theme.OK)

    def _set_hint(self, text: str, color: str):
        self.hint.setText(text)
        self.hint.setStyleSheet(f"color: {color};")


class ConnectionForm(QWidget):
    """服务商 / API Key / Base URL / 模型，初始设置和设置窗口共用"""

    def __init__(self, config: ConfigManager, hint: str = "", parent=None):
        super().__init__(parent)
        self.config = config
        self._typed = {}  # 切换服务商前填写的 Key 与模型，切回来时恢复

        form = _form()
        form.setContentsMargins(0, 0, 0, 0)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(form)

        self.provider_combo = _provider_combo(config.get("provider", "deepseek"))
        form.addRow(_label("服务商", "field"), self.provider_combo)

        self.key_panel = ApiKeyPanel(config.get("api_key", ""), self._endpoint)
        if hint:
            self.key_panel.set_hint(hint)
        form.addRow(_label("API Key", "field"), self.key_panel)

        self.base_url_edit = QLineEdit(config.get("base_url", ""))
        self.base_url_label = _label("Base URL", "field")
        form.addRow(self.base_url_label, self.base_url_edit)

        self.model_picker = ModelPicker(lambda: (self.provider_id(), self.key_panel.key(), self.base_url()))
        form.addRow(_label("模型", "field"), self.model_picker)

        self._current = self.provider_id()
        self._apply_provider(initial=True)
        self.provider_combo.currentIndexChanged.connect(lambda _i: self._apply_provider(initial=False))

    def provider_id(self) -> str:
        return self.provider_combo.currentData() or "custom"

    def base_url(self) -> str:
        return self.base_url_edit.text().strip() or providers.get(self.provider_id()).base_url

    def model(self) -> str:
        return self.model_picker.model() or providers.get(self.provider_id()).model

    def _endpoint(self):
        return self.provider_id(), self.base_url(), self.model()

    def _apply_provider(self, initial: bool):
        pid = self.provider_id()
        preset = providers.get(pid)
        if not initial:
            self._typed[self._current] = (self.key_panel.key(), self.model_picker.model(), self.base_url_edit.text())
        self._current = pid
        saved_here = pid == self.config.get("provider", "deepseek")

        key, model, base = self._typed.get(pid, (None, None, None))
        if key is None:
            key = self.config.get("api_key", "") if (initial or saved_here) else _provider_key(self.config, pid)
        if model is None:
            model = self.config.get("model", "") if saved_here else preset.model
        if base is None:
            base = self.config.get("base_url", "") if (pid == "custom" and saved_here) else preset.base_url

        self.key_panel.set_provider(preset, key)
        custom = pid == "custom"
        self.base_url_edit.setText(base)
        self.base_url_edit.setReadOnly(not custom)
        self.base_url_edit.setPlaceholderText("https://…/v1")
        self.model_picker.set_options(preset.models, model, preset.note)

    def values(self) -> dict:
        pid = self.provider_id()
        key = self.key_panel.key()
        keys = dict(self.config.get("provider_keys") or {})
        if providers.get(pid).needs_key:
            keys[pid] = key
        return {"provider": pid, "provider_keys": keys, "api_key": key, "base_url": self.base_url(), "model": self.model()}


# ─────────────────────────────────────────────
# 台词气泡
# ─────────────────────────────────────────────
class SpeechBubble(QWidget):
    """台词气泡。底部一行可放：提示文字、本轮生成的文件链接、「查看全文」"""

    link_activated = pyqtSignal(str)  # "open:<序号>" / "reveal:<序号>" / "log" / "workspace"

    def __init__(self, parent=None):
        super().__init__(parent)
        _apply_tool_window_flags(self)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setStyleSheet(theme.BUBBLE_QSS)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.container = QWidget(self)
        self.container.setObjectName("bubbleContainer")

        inner = QVBoxLayout(self.container)
        inner.setContentsMargins(14, 8, 10, 12)
        inner.setSpacing(6)

        header = QHBoxLayout()
        header.setSpacing(8)
        speaker = QLabel("死芒")
        speaker.setObjectName("speakerLabel")
        header.addWidget(speaker)
        tag = QLabel("NECRASS")
        tag.setObjectName("speakerTag")
        header.addWidget(tag, alignment=Qt.AlignmentFlag.AlignBottom)
        header.addStretch()

        self.close_btn = QPushButton("×")
        self.close_btn.setObjectName("closeBtn")
        self.close_btn.setFixedSize(18, 18)
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.clicked.connect(self.hide)
        header.addWidget(self.close_btn)
        inner.addLayout(header)

        rule = QFrame()
        rule.setObjectName("bubbleRule")
        inner.addWidget(rule)

        self.status_label = QLabel("")
        self.status_label.setObjectName("statusLabel")
        self.status_label.hide()
        inner.addWidget(self.status_label)

        self.content_label = QLabel("")
        self.content_label.setObjectName("contentLabel")
        self.content_label.setTextFormat(Qt.TextFormat.RichText)
        self.content_label.setWordWrap(True)
        self.content_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        inner.addWidget(self.content_label)

        self.footer_label = QLabel("")
        self.footer_label.setTextFormat(Qt.TextFormat.RichText)
        self.footer_label.setStyleSheet(f"color: {theme.TEXT_DIM}; font-size: 11px;")
        self.footer_label.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse)
        self.footer_label.linkActivated.connect(self.link_activated)
        self.footer_label.hide()
        inner.addWidget(self.footer_label)

        layout.addWidget(self.container)

        self.files: List[Path] = []
        self._footnote = ""
        self._show_full_link = False

        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide)

    @staticmethod
    def auto_duration(text: str) -> int:
        """按字数估算停留时间：6～30 秒"""
        return max(6000, min(30000, 2500 + len(text) * 120))

    def show_message(self, text: str, duration_ms: int = None, status: str = "", footnote: str = "",
                     allow_full: bool = True):
        self.status_label.setText(status)
        self.status_label.setVisible(bool(status))

        preview, needs_full = bubble_preview(text)
        self._footnote = footnote
        self._show_full_link = allow_full and needs_full
        body = html.escape(preview).replace("\n", "<br>")
        self.content_label.setText(f'<div style="line-height:140%;">{body}</div>')
        self._render_footer()
        self._fit_content(preview)
        self.show()

        if duration_ms is None:
            duration_ms = self.auto_duration(preview)
            if self.files or self._show_full_link:
                duration_ms = max(duration_ms, 20000)
        if duration_ms > 0:
            self.hide_timer.start(duration_ms)
        else:
            self.hide_timer.stop()

    def set_files(self, paths: List[str]):
        self.files = [Path(p) for p in paths]
        self._render_footer()
        self._relayout()

    def clear_files(self):
        self.files = []
        self._render_footer()

    def _render_footer(self):
        lines = []
        if self._footnote:
            lines.append(html.escape(self._footnote))
        for i, path in enumerate(self.files[:3]):
            lines.append(f"已生成　{_link(f'open:{i}', _elide(path.name))}　·　{_link(f'reveal:{i}', '所在位置')}")
        if len(self.files) > 3:
            lines.append(f"另有 {len(self.files) - 3} 个文件　·　{_link('workspace', '打开工作区')}")
        if self._show_full_link:
            lines.append(_link("log", "查看全文"))
        self.footer_label.setText(f'<div style="line-height:160%;">{"<br>".join(lines)}</div>')
        self.footer_label.setVisible(bool(lines))

    def _fit_content(self, text: str):
        """
        自动换行的 QLabel 在顶层窗口里 adjustSize() 算不准高度，长句会被截断；
        这里按文字宽度定出标签宽度（200～320），再按该宽度算出高度。
        """
        self.content_label.ensurePolished()
        fm = self.content_label.fontMetrics()
        natural = max((fm.horizontalAdvance(line) for line in text.split("\n")), default=0) + 6
        width = max(200, min(320, natural))
        # 先清掉上一条消息留下的固定高度，否则 heightForWidth 会被旧的最小高度撑大
        self.content_label.setMinimumHeight(0)
        self.content_label.setMaximumHeight(16777215)
        self.content_label.setFixedWidth(width)
        self.content_label.setFixedHeight(self.content_label.heightForWidth(width))
        self._relayout()

    def _relayout(self):
        self.container.layout().activate()
        self.layout().activate()
        self.adjustSize()

    def set_status(self, status: str):
        self.status_label.setText(status)
        self.status_label.setVisible(bool(status))
        self._relayout()
        self.show()


# ─────────────────────────────────────────────
# 对话记录（完整回复、代码等长内容在这里看）
# ─────────────────────────────────────────────
class ConversationWindow(QDialog):
    def __init__(self, memory, parent=None):
        super().__init__(parent)
        self.memory = memory
        self.setWindowTitle("死芒 · 对话记录")
        self.resize(620, 700)
        self.setStyleSheet(theme.DIALOG_QSS)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(14)
        layout.addLayout(_header("对话记录", "CONVERSATION LOG"))

        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        palette = self.browser.palette()
        palette.setColor(QPalette.ColorRole.Link, QColor(theme.ACCENT))
        self.browser.setPalette(palette)
        layout.addWidget(self.browser, stretch=1)

        row = QHBoxLayout()
        self.count_lbl = _label("", "hint")
        row.addWidget(self.count_lbl)
        row.addStretch()
        close_btn = _button("关闭")
        close_btn.clicked.connect(self.close)
        row.addWidget(close_btn)
        layout.addLayout(row)

    def refresh(self):
        parts = []
        for msg in self.memory.messages:
            who = "学者" if msg.get("role") == "user" else "死芒"
            parts.append(f"**{who}**\n\n{msg.get('content', '')}")
        self.browser.setMarkdown("\n\n---\n\n".join(parts) or "还没有对话记录。")
        bar = self.browser.verticalScrollBar()
        bar.setValue(bar.maximum())
        turns = len(self.memory.messages) // 2
        self.count_lbl.setText(f"共 {turns} 轮，最多保留最近 {self.memory.max_turns} 轮")

    def present(self):
        self.refresh()
        self.show()
        self.raise_()
        self.activateWindow()


# ─────────────────────────────────────────────
# 对话输入栏
# ─────────────────────────────────────────────
class ChatInputBar(QWidget):
    message_submitted = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        _apply_tool_window_flags(self)
        self.setStyleSheet(theme.INPUT_BAR_QSS)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.panel = QWidget(self)
        self.panel.setObjectName("inputPanel")

        inner = QHBoxLayout(self.panel)
        inner.setContentsMargins(8, 4, 4, 4)
        inner.setSpacing(6)

        self.input_edit = QLineEdit(self)
        self.input_edit.setPlaceholderText("输入消息，回车发送")
        self.input_edit.setMinimumWidth(240)
        palette = self.input_edit.palette()
        palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(theme.TEXT_MUTED))
        self.input_edit.setPalette(palette)
        self.input_edit.returnPressed.connect(self._on_submit)
        inner.addWidget(self.input_edit)

        self.send_btn = QPushButton("发送")
        self.send_btn.setObjectName("sendBtn")
        self.send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_btn.clicked.connect(self._on_submit)
        inner.addWidget(self.send_btn)

        layout.addWidget(self.panel)
        self.adjustSize()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            return
        super().keyPressEvent(event)

    def _on_submit(self):
        text = self.input_edit.text().strip()
        if not text:
            return
        self.input_edit.clear()
        self.message_submitted.emit(text)

    def set_busy(self, busy: bool):
        self.input_edit.setDisabled(busy)
        self.send_btn.setDisabled(busy)
        self.send_btn.setText("回复中" if busy else "发送")
        if not busy and self.isVisible():
            self.input_edit.setFocus()


# ─────────────────────────────────────────────
# 初始设置（首次启动 / 未填写 API Key 时弹出）
# ─────────────────────────────────────────────
class OnboardingDialog(QDialog):
    def __init__(self, config: ConfigManager, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("死芒 · 初始设置")
        self.setMinimumWidth(520)
        self.setStyleSheet(theme.DIALOG_QSS)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 22, 24, 20)
        main_layout.setSpacing(14)

        main_layout.addLayout(
            _header(
                "初始设置",
                "INITIAL SETUP",
                "“你终于愿意让步了？那么，把登记表给我吧。”",
                avatar=_avatar_label(64, self.devicePixelRatioF()),
            )
        )

        # 连接
        main_layout.addLayout(_section("连接", "CONNECTION"))
        self.connection = ConnectionForm(self.config, hint="用于对话功能，可稍后在「设置」中填写。")
        main_layout.addWidget(self.connection)

        # 外观
        main_layout.addLayout(_section("外观", "APPEARANCE"))
        form = QFormLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)

        self.appearance_combo = QComboBox()
        _fill_appearance_combo(self.appearance_combo, self.config.get("default_appearance", "exp_calm"))
        form.addRow(_label("形象", "field"), self.appearance_combo)

        self.scale_spin = _scale_spin(self.config.get("scale", 1.0))
        form.addRow(_label("缩放", "field"), self.scale_spin)
        main_layout.addLayout(form)

        # 启动
        main_layout.addLayout(_section("启动", "STARTUP"))
        self.autostart_cb = _autostart_checkbox(self.config)
        main_layout.addWidget(self.autostart_cb)
        self.skip_next_cb = QCheckBox("下次启动时跳过此窗口")
        self.skip_next_cb.setChecked(not bool(self.config.get("show_onboarding", True)))
        main_layout.addWidget(self.skip_next_cb)

        main_layout.addSpacing(4)
        main_layout.addWidget(_rule())

        btn_row = QHBoxLayout()
        quit_btn = _button("退出")
        quit_btn.clicked.connect(self.reject)
        btn_row.addWidget(quit_btn)
        btn_row.addStretch()
        launch_btn = _button("开始使用", "primary")
        launch_btn.setDefault(True)
        launch_btn.clicked.connect(self._on_launch)
        btn_row.addWidget(launch_btn)
        main_layout.addLayout(btn_row)

    def _on_launch(self):
        current = self.config.get("default_appearance", "exp_calm")
        autostart = self.autostart_cb.isChecked()
        self.config.update(
            {
                **self.connection.values(),
                "default_appearance": _chosen_appearance(self.appearance_combo, current),
                "scale": self.scale_spin.value() / 100,
                "windows_autostart": autostart,
                "show_onboarding": not self.skip_next_cb.isChecked(),
            }
        )
        set_windows_autostart(autostart)
        self.accept()


def _scale_spin(value) -> QSpinBox:
    spin = QSpinBox()
    spin.setRange(30, 300)
    spin.setSingleStep(10)
    spin.setSuffix(" %")
    spin.setValue(round(float(value) * 100))
    return spin


def _autostart_checkbox(config: ConfigManager) -> QCheckBox:
    cb = QCheckBox("开机自动启动" if IS_WINDOWS else "开机自动启动（仅支持 Windows）")
    cb.setChecked(IS_WINDOWS and bool(config.get("windows_autostart", False)))
    cb.setEnabled(IS_WINDOWS)
    return cb


# ─────────────────────────────────────────────
# 设置（右键菜单打开）
# ─────────────────────────────────────────────
class SettingsDialog(QDialog):
    settings_saved = pyqtSignal()

    def __init__(self, config: ConfigManager, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("死芒 · 设置")
        self.setMinimumWidth(580)
        self.setStyleSheet(theme.DIALOG_QSS)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # 内容较多，放进滚动区域；底部按钮固定
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        body.setObjectName("dialogBody")
        scroll.setWidget(body)
        # 用对象名限定选择器：不带选择器的样式会传给所有子控件，把分割线和强调条也变透明
        scroll.viewport().setObjectName("scrollViewport")
        outer.addWidget(scroll, stretch=1)

        main_layout = QVBoxLayout(body)
        main_layout.setContentsMargins(24, 22, 24, 12)
        main_layout.setSpacing(12)
        main_layout.addLayout(_header("设置", "SETTINGS"))

        # 连接
        main_layout.addLayout(_section("连接", "CONNECTION"))
        self.connection = ConnectionForm(self.config, hint="修改后可先测试连接再保存。")
        main_layout.addWidget(self.connection)

        # 能力
        main_layout.addLayout(_section("能力", "SKILLS"))
        ability = _form()
        ws_row = QHBoxLayout()
        ws_row.setSpacing(6)
        self.workspace_edit = QLineEdit(self.config.get("workspace_dir", ""))
        self.workspace_edit.setPlaceholderText(str(skills.default_workspace()))
        ws_row.addWidget(self.workspace_edit, stretch=1)
        ws_btn = _button("选择文件夹")
        ws_btn.clicked.connect(self._choose_workspace)
        ws_row.addWidget(ws_btn)
        ws_box = QVBoxLayout()
        ws_box.setSpacing(6)
        ws_box.addLayout(ws_row)
        ws_box.addWidget(_label("生成和修改的文件都保存在这里；工作区以外的文件只读不写。", "hint", wrap=True))
        ability.addRow(_label("工作区", "field"), ws_box)

        skill_box = QVBoxLayout()
        skill_box.setSpacing(4)
        enabled = set(self.config.get("skills_enabled", skills.DEFAULT_ENABLED))
        self.skill_checks = {}
        for skill in skills.LISTED_SKILLS:
            available = skill.available()
            cb = QCheckBox(skill.name)
            cb.setChecked(available and skill.id in enabled)
            cb.setEnabled(available)
            self.skill_checks[skill.id] = cb
            skill_box.addWidget(cb)
            hint = skill.summary if available else f"缺少依赖（{', '.join(skill.requires)}），暂不可用"
            note = _label(hint, "hint", wrap=True)
            note.setContentsMargins(21, 0, 0, 6)
            skill_box.addWidget(note)
        ability.addRow(_label("技能", "field"), skill_box)
        main_layout.addLayout(ability)

        # 文风
        main_layout.addLayout(_section("文风", "STYLE"))
        self.humanize_cb = QCheckBox("去 AI 腔：检测到套话时自动改写")
        self.humanize_cb.setChecked("humanize" in enabled)
        main_layout.addWidget(self.humanize_cb)
        builtin_hint = _label(
            "已内置常见套话规则：给你的话打分（这句话稳、比刚才轻、很平）、空洞确认（我记下了、认你）、"
            "守护与放行（睡吧我守着、我不拦、你掂量）、接话与反问套路、动作旁白等。"
            "稳、轻、重这些字在「稳定」「重要」「轻松」里不受影响。",
            "hint",
            wrap=True,
        )
        builtin_hint.setToolTip(humanize.GUIDE)
        main_layout.addWidget(builtin_hint)
        main_layout.addWidget(_label("额外禁用的说法（每行一条，xx 表示任意几个字，例如：xx比xx沉）", "field"))
        self.humanize_edit = QPlainTextEdit()
        self.humanize_edit.setPlaceholderText("这话我记着\nxx比xx沉\n你自己掂量")
        self.humanize_edit.setPlainText("\n".join(self.config.get("humanize_extra", []) or []))
        self.humanize_edit.setFixedHeight(96)
        main_layout.addWidget(self.humanize_edit)

        # 外观
        main_layout.addLayout(_section("外观", "APPEARANCE"))
        look = _form()
        self.appearance_combo = QComboBox()
        _fill_appearance_combo(self.appearance_combo, self.config.get("default_appearance", "exp_calm"))
        look.addRow(_label("默认形象", "field"), self.appearance_combo)

        self.scale_spin = _scale_spin(self.config.get("scale", 1.0))
        look.addRow(_label("缩放", "field"), self.scale_spin)

        asset_box = QVBoxLayout()
        asset_box.setSpacing(6)
        asset_row = QHBoxLayout()
        asset_row.setSpacing(6)
        self.assets_path_edit = QLineEdit(self.config.get("assets_path", ""))
        self.assets_path_edit.setPlaceholderText("留空则使用内置立绘")
        asset_row.addWidget(self.assets_path_edit, stretch=1)
        btn_dir = _button("选择文件夹")
        btn_dir.clicked.connect(self._choose_folder)
        asset_row.addWidget(btn_dir)
        btn_file = _button("选择文件")
        btn_file.clicked.connect(self._choose_file)
        asset_row.addWidget(btn_file)
        asset_box.addLayout(asset_row)
        asset_box.addWidget(_label("支持单个 GIF / PNG，或按动作分子文件夹的 PNG 序列帧。", "hint", wrap=True))
        look.addRow(_label("自定义素材", "field"), asset_box)
        main_layout.addLayout(look)

        # 启动
        main_layout.addLayout(_section("启动", "STARTUP"))
        self.autostart_cb = _autostart_checkbox(self.config)
        main_layout.addWidget(self.autostart_cb)
        self.onboarding_cb = QCheckBox("每次启动时显示初始设置")
        self.onboarding_cb.setChecked(bool(self.config.get("show_onboarding", True)))
        main_layout.addWidget(self.onboarding_cb)

        # 人设
        persona_head = _section("人设", "PERSONA")
        reset_btn = _button("恢复默认", "link")
        reset_btn.clicked.connect(lambda: self.prompt_edit.setPlainText(EBLANA_SYSTEM_PROMPT))
        persona_head.addWidget(reset_btn)
        main_layout.addLayout(persona_head)
        main_layout.addWidget(_label("技能守则与工作区信息会在运行时自动附加，这里只需写角色设定。", "hint", wrap=True))
        self.prompt_edit = QPlainTextEdit()
        self.prompt_edit.setPlainText(self.config.get("system_prompt", ""))
        self.prompt_edit.setMinimumHeight(140)
        main_layout.addWidget(self.prompt_edit)
        main_layout.addStretch(1)

        # 底部按钮（不随内容滚动）
        footer = QWidget()
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(24, 0, 24, 18)
        footer_layout.setSpacing(12)
        footer_layout.addWidget(_rule())
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        cancel_btn = _button("取消")
        cancel_btn.clicked.connect(self.reject)
        save_btn = _button("保存", "primary")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._save)
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(save_btn)
        footer_layout.addLayout(btn_layout)
        outer.addWidget(footer)

        screen = QApplication.primaryScreen().availableGeometry()
        self.resize(600, min(880, screen.height() - 80))

    def _choose_workspace(self):
        start = self.workspace_edit.text() or str(skills.default_workspace())
        folder = QFileDialog.getExistingDirectory(self, "选择工作区文件夹", start)
        if folder:
            self.workspace_edit.setText(folder)

    def _choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择素材文件夹", self.assets_path_edit.text())
        if folder:
            self.assets_path_edit.setText(folder)

    def _choose_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择素材文件",
            self.assets_path_edit.text(),
            "图片 (*.gif *.png *.webp *.jpg *.jpeg)",
        )
        if file_path:
            self.assets_path_edit.setText(file_path)

    def _save(self):
        workspace = self.workspace_edit.text().strip()
        try:
            skills.workspace_dir(workspace)
        except Exception as e:
            QMessageBox.warning(self, "工作区不可用", f"无法使用这个文件夹作为工作区：\n{e}")
            return

        current = self.config.get("default_appearance", "exp_calm")
        autostart = self.autostart_cb.isChecked()
        self.config.update(
            {
                **self.connection.values(),
                "workspace_dir": workspace,
                "skills_enabled": [sid for sid, cb in self.skill_checks.items() if cb.isChecked()]
                + (["humanize"] if self.humanize_cb.isChecked() else []),
                "humanize_extra": [l.strip() for l in self.humanize_edit.toPlainText().splitlines() if l.strip()],
                "default_appearance": _chosen_appearance(self.appearance_combo, current),
                "assets_path": self.assets_path_edit.text().strip(),
                "scale": self.scale_spin.value() / 100,
                "windows_autostart": autostart,
                "show_onboarding": self.onboarding_cb.isChecked(),
                "system_prompt": self.prompt_edit.toPlainText().strip() or EBLANA_SYSTEM_PROMPT,
            }
        )
        set_windows_autostart(autostart)
        self.settings_saved.emit()
        self.accept()


def _form() -> QFormLayout:
    form = QFormLayout()
    form.setHorizontalSpacing(14)
    form.setVerticalSpacing(10)
    form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    return form
