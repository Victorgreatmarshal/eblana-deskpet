"""
统一的界面配色与样式表。

风格参考明日方舟游戏内 UI：深灰底色、直角边框、1px 细分割线、白色正文，
只保留一个黄色强调色用于选中态、主按钮与标识条。改配色只需改本文件。
"""

# ── 配色 ────────────────────────────────────
ACCENT = "#FFC83D"        # 强调色（标识条 / 主按钮 / 选中态）
ACCENT_HOVER = "#FFD666"
ACCENT_TEXT = "#141414"   # 强调色底上的文字
BG = "#1A1A1D"            # 窗口底色
BG_RAISED = "#232327"     # 次级按钮 / 悬停
FIELD = "#111113"         # 输入框底色
LINE = "#35353B"          # 常规边框 / 分割线
LINE_STRONG = "#5A5A62"   # 悬停边框
TEXT = "#ECECEC"
TEXT_DIM = "#8C8C94"
TEXT_MUTED = "#5E5E66"
OK = "#6BCB8B"
ERROR = "#E5605A"

# 中文正文字体（按平台回退）与英文标签字体（窄体，接近游戏内的英文小标）
UI_FONT_FAMILIES = ["Microsoft YaHei UI", "PingFang SC", "Noto Sans CJK SC", "Source Han Sans SC"]
TAG_FONT = '"Bahnschrift", "DIN Alternate", "Arial Narrow", "Helvetica Neue"'


# ── 右键菜单 ────────────────────────────────
MENU_QSS = f"""
QMenu {{
    background-color: {BG};
    color: {TEXT};
    border: 1px solid {LINE};
    padding: 4px 0;
    font-size: 13px;
}}
QMenu::item {{
    padding: 6px 28px 6px 22px;
    border-left: 2px solid transparent;
    background: transparent;
}}
QMenu::item:selected {{
    background-color: {BG_RAISED};
    border-left: 2px solid {ACCENT};
    color: #FFFFFF;
}}
QMenu::item:disabled {{
    color: {TEXT_MUTED};
}}
QMenu::separator {{
    height: 1px;
    background: {LINE};
    margin: 4px 0;
}}
QMenu::indicator {{
    width: 6px;
    height: 6px;
    left: 9px;
}}
QMenu::indicator:checked {{
    background: {ACCENT};
}}
"""


# ── 对话框（初始设置 / 设置）────────────────
DIALOG_QSS = f"""
QDialog {{
    background-color: {BG};
}}
QLabel {{
    color: {TEXT};
    font-size: 13px;
}}
QLabel[role="title"] {{
    font-size: 18px;
    font-weight: bold;
    color: #FFFFFF;
}}
QLabel[role="tag"] {{
    font-family: {TAG_FONT};
    font-size: 11px;
    letter-spacing: 2px;
    color: {TEXT_DIM};
}}
QLabel[role="section"] {{
    font-size: 13px;
    font-weight: bold;
    color: #FFFFFF;
}}
QLabel[role="field"] {{
    color: {TEXT_DIM};
    font-size: 12px;
}}
QLabel[role="hint"] {{
    color: {TEXT_DIM};
    font-size: 12px;
}}
QLabel[role="quote"] {{
    color: {TEXT_DIM};
    font-size: 12px;
}}
QFrame[role="rule"] {{
    background: {LINE};
    border: none;
    min-height: 1px;
    max-height: 1px;
}}
QFrame[role="accentBar"] {{
    background: {ACCENT};
    border: none;
    min-width: 4px;
    max-width: 4px;
}}
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    background-color: {FIELD};
    border: 1px solid {LINE};
    border-radius: 0;
    color: {TEXT};
    padding: 5px 8px;
    font-size: 13px;
    selection-background-color: {ACCENT};
    selection-color: {ACCENT_TEXT};
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 1px solid {ACCENT};
}}
QComboBox QAbstractItemView {{
    background-color: {FIELD};
    color: {TEXT};
    border: 1px solid {LINE};
    selection-background-color: {BG_RAISED};
    selection-color: #FFFFFF;
    outline: 0;
}}
QCheckBox {{
    color: {TEXT};
    font-size: 13px;
    spacing: 8px;
}}
QCheckBox:disabled {{
    color: {TEXT_MUTED};
}}
QCheckBox::indicator {{
    width: 12px;
    height: 12px;
    border: 1px solid {LINE_STRONG};
    background: {FIELD};
}}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border: 1px solid {ACCENT};
}}
QCheckBox::indicator:disabled {{
    border: 1px solid {LINE};
}}
QPushButton {{
    background-color: {BG_RAISED};
    color: {TEXT};
    border: 1px solid {LINE};
    border-radius: 0;
    padding: 6px 14px;
    font-size: 13px;
}}
QPushButton:hover {{
    border: 1px solid {LINE_STRONG};
}}
QPushButton:pressed {{
    background-color: {FIELD};
}}
QPushButton:disabled {{
    color: {TEXT_MUTED};
    border: 1px solid {LINE};
}}
QPushButton:checked {{
    border: 1px solid {LINE_STRONG};
    background-color: {FIELD};
}}
QPushButton[role="primary"] {{
    background-color: {ACCENT};
    color: {ACCENT_TEXT};
    border: 1px solid {ACCENT};
    font-weight: bold;
    padding: 7px 22px;
}}
QPushButton[role="primary"]:hover {{
    background-color: {ACCENT_HOVER};
    border: 1px solid {ACCENT_HOVER};
}}
QPushButton[role="link"] {{
    background: transparent;
    border: none;
    color: {TEXT_DIM};
    text-decoration: underline;
    padding: 0;
    font-size: 12px;
}}
QPushButton[role="link"]:hover {{
    color: {TEXT};
}}
QScrollArea {{
    border: none;
    background: transparent;
}}
QWidget#dialogBody, QWidget#scrollViewport {{
    background: transparent;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {LINE_STRONG};
    min-height: 24px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QToolTip {{
    background-color: {BG};
    color: {TEXT};
    border: 1px solid {LINE};
    padding: 4px 6px;
}}
"""


# ── 台词气泡 ────────────────────────────────
BUBBLE_QSS = f"""
QWidget#bubbleContainer {{
    background-color: rgba(20, 20, 22, 236);
    border: 1px solid rgba(255, 255, 255, 34);
    border-left: 3px solid {ACCENT};
}}
QLabel#speakerLabel {{
    color: #FFFFFF;
    font-size: 14px;
    font-weight: bold;
}}
QLabel#speakerTag {{
    font-family: {TAG_FONT};
    color: {TEXT_DIM};
    font-size: 10px;
    letter-spacing: 2px;
}}
QLabel#statusLabel {{
    color: {ACCENT};
    font-size: 11px;
}}
QLabel#contentLabel {{
    color: #E6E6E6;
    font-size: 13px;
}}
QFrame#bubbleRule {{
    background: rgba(255, 255, 255, 30);
    border: none;
    min-height: 1px;
    max-height: 1px;
}}
QPushButton#closeBtn {{
    background: transparent;
    color: {TEXT_DIM};
    border: none;
    font-size: 15px;
    padding: 0;
}}
QPushButton#closeBtn:hover {{
    color: #FFFFFF;
}}
"""


# ── 对话输入栏 ──────────────────────────────
INPUT_BAR_QSS = f"""
QWidget#inputPanel {{
    background-color: rgba(20, 20, 22, 242);
    border: 1px solid {LINE};
}}
QLineEdit {{
    background: transparent;
    border: none;
    color: {TEXT};
    font-size: 13px;
    padding: 4px 6px;
    selection-background-color: {ACCENT};
    selection-color: {ACCENT_TEXT};
}}
QPushButton#sendBtn {{
    background-color: {ACCENT};
    color: {ACCENT_TEXT};
    border: none;
    border-radius: 0;
    padding: 5px 14px;
    font-weight: bold;
    font-size: 12px;
}}
QPushButton#sendBtn:hover {{
    background-color: {ACCENT_HOVER};
}}
QPushButton#sendBtn:disabled {{
    background-color: {BG_RAISED};
    color: {TEXT_MUTED};
}}
"""
