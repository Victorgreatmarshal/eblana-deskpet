import math
import random
import sys
from PyQt6.QtCore import QElapsedTimer, QLockFile, QPoint, QPointF, QSize, Qt, QTimer
from PyQt6.QtGui import QAction, QActionGroup, QFont, QFontDatabase, QGuiApplication, QIcon, QMovie, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon, QWidget

import skills
import theme
from agent import EblanaAgentWorker, MemoryManager
from assets_manager import EXPRESSION_IDS, SKIN_IDS, AssetsManager
from config import ConfigManager, OFFICIAL_ASSETS_DIR, USER_DATA_DIR
from skills.core import open_path
from ui_components import (
    ChatInputBar,
    ConversationWindow,
    OnboardingDialog,
    SettingsDialog,
    SpeechBubble,
    tool_status_text,
)


# 精选自 PRTS 死芒官方语音记录与晋升档案，配对对应的表情差分
TOUCH_VOICE_POOL = [
    ("exp_smirk", "“忍住这点冰冷的灼痛，你尽可以一直握着我的手。”"),
    ("exp_calm", "“想吃些甜食吗？我可以为你准备一些。佐餐的酒？也有。”"),
    ("exp_calm", "“那位凯尔希医生的眼神很是凶锐，每当她盯着我，我都觉得她是想把我钉死在甲板上。不过不用担心，身在罗德岛的这一点点时间里，我都是你的死芒，也只是你的死芒。”"),
    ("exp_closed", "“我的躯体冰冷，我的触觉迟钝，我体内翻涌着永不停歇、宛如被自己的火焰灼烧般冰冷刺骨的疼痛……偏偏就是这点疼痛令人着迷，不然，我甚至会忘记自己已经驯服了死亡。”"),
    ("exp_smirk", "“你怎样才愿意归顺于我？是想我恳求，还是呵斥？……你想要的，我全都……拒绝。你首先要属于我，然后我们再说别的。”"),
    ("exp_serious", "“你对我的邀约保持沉默，或是顾左右而言他，我都允许，可这不意味着你能从我这抽身。我抓住你，你的魂灵就归我所有。时间、生活和快乐任你挥霍，但始终记好，你的终点也在我这。”"),
    ("exp_surprised", "“见到我高兴吗，学者？每次我来时你都在，这并不能用‘恰好’一笔带过。因为你的确是个有趣的谜。”"),
    ("exp_stern", "“为什么要压抑自己呢？我在你身上看见了毁灭的欲望，你理应将其倾泻出去，毫无保留。”"),
    ("exp_closed", "“……深沉的睡眠与死无异。希望你能像往常一样悠悠醒来，学者。”"),
]

GREETING = "你终于愿意让步了？那么，把登记表给我吧。“死芒”这个代号怎么样，学者？"
USAGE_HINT = "单击对话 · 右键打开菜单 · 拖动移动位置"

# 右键菜单「快捷指令」：(菜单文字, 发送给死芒的内容)
QUICK_PROMPTS = [
    ("询问她为何来到罗德岛", "爱布拉娜，我刚看了你的高权限档案和苇草的信。跟我聊聊你为什么抹去深池、又为什么留在罗德岛注视着我？"),
    ("总结 / 翻译剪贴板内容", "请读取我当前的剪贴板内容，帮我总结或翻译，并给出你的见解。"),
    ("查看时间与系统状态", "现在几点了？顺便看看我的电脑状态如何。"),
    ("查看待办事项", "帮我看看目前有哪些待办事项？"),
    ("打开 PRTS 档案页", "帮我在浏览器打开 prts 看看你的档案。"),
    None,  # 分隔线：以下为工作类指令
    ("剪贴板内容 → Word 文档", "读取我的剪贴板，把内容整理成一份结构清晰、排版规范的 Word 文档，保存到工作区。"),
    ("剪贴板内容 → 演示文稿", "读取我的剪贴板，提炼要点做成一份演示文稿（PPT），保存到工作区。"),
    ("查看工作区里的文件", "看看我的工作区里现在有哪些文件。"),
]

BOB_AMPLITUDE = 3          # 待机呼吸浮动幅度（逻辑像素）
BOB_PERIOD_MS = 2800       # 浮动周期
TOUCH_REACTION_MS = 5500   # 点击后表情保持时长
REPLY_REACTION_MS = 8000   # 回复后表情保持时长


class EblanaDeskPet(QWidget):
    def __init__(self, config: ConfigManager):
        super().__init__()
        self.config = config
        self.memory = MemoryManager(max_turns=self.config.get("max_history_turns", 15))
        self.assets = AssetsManager(self.config.get("assets_path", ""))

        initial = self.config.get("default_appearance", "exp_calm")
        self.base_appearance = initial
        self.current_action = initial

        # 渲染状态：静态立绘只有 1 帧，靠绘制偏移实现呼吸浮动；序列帧 / GIF 按帧播放
        self._frames = []
        self._frame_index = 0
        self._pixmap: QPixmap = None
        self._bob_enabled = False
        self._clock = QElapsedTimer()
        self._clock.start()
        self.movie: QMovie = None
        self._movie_dpr = 1.0

        # 位置以「底部中点」为锚：切换不同尺寸的立绘时，人物脚下位置不跳动
        self._anchor = self._initial_anchor()

        # 拖拽 / 点击判定
        self._dragging = False
        self._drag_moved = False
        self._press_global = QPoint()
        self._drag_offset = QPoint()

        self._last_voice = -1
        self._choice_groups = {}
        self.active_worker: EblanaAgentWorker = None

        self._init_window()
        self._init_timers()
        self.menu = self._build_menu()
        self._init_tray()
        self.play_action(initial)
        self._clamp_anchor_to_screen()
        self._place_at_anchor()

        QTimer.singleShot(500, self._greet)

    # ─────────────────────────────────────────
    # 初始化
    # ─────────────────────────────────────────
    def _init_window(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow)

        self.setAcceptDrops(True)  # 把文件拖到桌宠身上即可交给她处理

        self.bubble = SpeechBubble()
        self.bubble.link_activated.connect(self._on_bubble_link)
        self.input_bar = ChatInputBar()
        self.input_bar.message_submitted.connect(self.handle_user_message)
        self.log_window: ConversationWindow = None

    def _init_timers(self):
        fps = max(1, int(self.config.get("fps", 16)))
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self._tick)
        self.anim_timer.start(int(1000 / fps))

        # 表情回到默认的计时器：只保留一个，新的反应会覆盖旧的，避免互相提前打断
        self.revert_timer = QTimer(self)
        self.revert_timer.setSingleShot(True)
        self.revert_timer.timeout.connect(lambda: self.play_action(self.base_appearance))

    def _init_tray(self):
        self.tray = QSystemTrayIcon(self)
        for name in ("avatar_e0.png", "avatar_e2.png"):
            path = OFFICIAL_ASSETS_DIR / name
            if path.exists():
                self.tray.setIcon(QIcon(str(path)))
                break
        self.tray.setToolTip("死芒 · 桌宠")
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _initial_anchor(self) -> QPoint:
        saved = self.config.get("anchor")
        if isinstance(saved, (list, tuple)) and len(saved) == 2:
            return QPoint(int(saved[0]), int(saved[1]))
        area = QGuiApplication.primaryScreen().availableGeometry()
        return QPoint(area.right() - 200, area.bottom() + 1)

    def _greet(self):
        footnote = USAGE_HINT if self.config.get("show_usage_hint", True) else ""
        self.bubble.show_message(GREETING, duration_ms=9000, footnote=footnote)
        self._sync_floating_widgets()
        if footnote:
            self.config.set("show_usage_hint", False)

    def showEvent(self, event):
        super().showEvent(event)
        handle = self.windowHandle()
        if handle is not None and not getattr(self, "_screen_hooked", False):
            # 拖到缩放比例不同的显示器时，按新屏幕重新渲染，保持清晰
            handle.screenChanged.connect(lambda _s: self._render_clip(self.current_action))
            self._screen_hooked = True

    # ─────────────────────────────────────────
    # 渲染
    # ─────────────────────────────────────────
    def play_action(self, action_name: str, revert_ms: int = 0, update_base: bool = False):
        """切换到指定动作 / 表情。revert_ms > 0 时到点后回到默认形象。"""
        clip = self._render_clip(action_name)
        if update_base:
            self.base_appearance = clip.name
            self.config.set("default_appearance", clip.name)
        if revert_ms > 0:
            self.revert_timer.start(revert_ms)
        else:
            self.revert_timer.stop()

    def _render_clip(self, action_name: str):
        clip = self.assets.get_clip(action_name)
        self.current_action = clip.name
        scale = float(self.config.get("scale", 1.0))

        if self.movie:
            self.movie.stop()
            self.movie.deleteLater()
            self.movie = None

        if clip.is_movie:
            self.movie = QMovie(str(clip.movie_path), parent=self)
            self.movie.jumpToFrame(0)
            rect = self.movie.frameRect()
            native_w, native_h = (rect.width() or 220), (rect.height() or 240)
            if clip.movie_box:
                fit = clip.movie_box * scale / max(native_w, native_h)
                size = QSize(round(native_w * fit), round(native_h * fit))
            else:
                size = QSize(round(native_w * scale), round(native_h * scale))
            # 按屏幕像素比解码，高分屏下不发虚
            self._movie_dpr = self.devicePixelRatioF()
            self.movie.setScaledSize(QSize(round(size.width() * self._movie_dpr), round(size.height() * self._movie_dpr)))
            self.movie.frameChanged.connect(self._on_movie_frame)
            self._frames = []
            self._bob_enabled = False
            self._pixmap = None
            self._set_sprite_size(size)
            self.movie.start()
        else:
            self._frames = clip.frames(scale, self.devicePixelRatioF())
            self._frame_index = 0
            self._pixmap = self._frames[0] if self._frames else None
            self._bob_enabled = len(self._frames) == 1
            size = self._pixmap.deviceIndependentSize().toSize() if self._pixmap else QSize(64, 64)
            self._set_sprite_size(size)

        self.update()
        return clip

    def _on_movie_frame(self, _index: int):
        if self.movie:
            pixmap = self.movie.currentPixmap()
            pixmap.setDevicePixelRatio(self._movie_dpr)
            self._pixmap = pixmap
            self.update()

    def _tick(self):
        if len(self._frames) > 1:
            self._frame_index = (self._frame_index + 1) % len(self._frames)
            self._pixmap = self._frames[self._frame_index]
            self.update()
        elif self._bob_enabled and self.isVisible():
            self.update()

    def _bob_offset(self) -> float:
        if not self._bob_enabled:
            return 0.0
        phase = (self._clock.elapsed() % BOB_PERIOD_MS) / BOB_PERIOD_MS * 2 * math.pi
        return math.sin(phase) * BOB_AMPLITUDE

    def paintEvent(self, event):
        if self._pixmap is None or self._pixmap.isNull():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        size = self._pixmap.deviceIndependentSize()
        x = (self.width() - size.width()) / 2
        y = BOB_AMPLITUDE + self._bob_offset()
        painter.drawPixmap(QPointF(x, y), self._pixmap)
        painter.end()

    def _set_sprite_size(self, sprite: QSize):
        self.setFixedSize(max(1, sprite.width()), sprite.height() + BOB_AMPLITUDE * 2)
        self._place_at_anchor()

    # ─────────────────────────────────────────
    # 位置
    # ─────────────────────────────────────────
    def _place_at_anchor(self):
        self.move(self._anchor.x() - self.width() // 2, self._anchor.y() - self.height())
        self._sync_floating_widgets()

    def _screen_area(self):
        screen = (
            QGuiApplication.screenAt(self.frameGeometry().center())
            or QGuiApplication.screenAt(self._anchor)
            or QGuiApplication.primaryScreen()
        )
        return screen.availableGeometry()

    def _clamp_anchor_to_screen(self):
        """保证人物中心留在屏幕内（例如上次所在的副屏已断开时）"""
        area = self._screen_area()
        x = min(max(self._anchor.x(), area.left()), area.right())
        y = min(max(self._anchor.y(), area.top() + self.height() // 2), area.bottom() + 1)
        self._anchor = QPoint(x, y)

    def _sync_floating_widgets(self):
        if not hasattr(self, "bubble"):
            return
        geo = self.frameGeometry()
        area = self._screen_area()

        def clamp(v, lo, hi):
            return max(lo, min(v, hi))

        bw, bh = self.bubble.width(), self.bubble.height()
        bx = clamp(geo.center().x() - bw // 2, area.left(), area.right() + 1 - bw)
        by = clamp(geo.top() + 12 - bh, area.top(), area.bottom() + 1 - bh)
        self.bubble.move(bx, by)

        iw, ih = self.input_bar.width(), self.input_bar.height()
        ix = clamp(geo.center().x() - iw // 2, area.left(), area.right() + 1 - iw)
        iy = clamp(geo.bottom() + 4, area.top(), area.bottom() + 1 - ih)
        self.input_bar.move(ix, iy)

    # ─────────────────────────────────────────
    # 鼠标交互
    # ─────────────────────────────────────────
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_moved = False
            self._press_global = event.globalPosition().toPoint()
            self._drag_offset = self._press_global - self.pos()
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton:
            self.menu.popup(event.globalPosition().toPoint())
            event.accept()

    def mouseMoveEvent(self, event):
        if not (self._dragging and event.buttons() & Qt.MouseButton.LeftButton):
            return
        pos = event.globalPosition().toPoint()
        if not self._drag_moved:
            if (pos - self._press_global).manhattanLength() < QApplication.startDragDistance():
                return
            self._drag_moved = True
        if self.config.get("locked_position", False):
            return
        top_left = pos - self._drag_offset
        self._anchor = QPoint(top_left.x() + self.width() // 2, top_left.y() + self.height())
        self.move(top_left)
        self._sync_floating_widgets()
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._dragging = False
        if self._drag_moved:
            if not self.config.get("locked_position", False):
                self._clamp_anchor_to_screen()
                self._place_at_anchor()
                self.config.set("anchor", [self._anchor.x(), self._anchor.y()])
        else:
            self._on_click()
        event.accept()

    def _on_click(self):
        self._show_input_bar()
        if self._is_busy():
            return  # 正在回复时不打断气泡内容
        choices = [i for i in range(len(TOUCH_VOICE_POOL)) if i != self._last_voice]
        self._last_voice = random.choice(choices)
        expression, quote = TOUCH_VOICE_POOL[self._last_voice]
        self._react(expression, "touch", TOUCH_REACTION_MS)
        self.bubble.show_message(quote)
        self._sync_floating_widgets()

    def _react(self, expression: str, custom_action: str, revert_ms: int):
        """
        临时反应：剧情立绘模式下切换表情；自定义素材模式下播放对应动作；
        选了全身立绘 / 时装时保持不变，不会被对话自动换装。
        """
        if self.base_appearance in EXPRESSION_IDS:
            target = expression if expression in EXPRESSION_IDS else None
        else:
            clip = self.assets.clips.get(custom_action)
            target = custom_action if clip is not None and clip.custom else None
        if target:
            self.play_action(target, revert_ms=revert_ms)

    def _revert_soon(self, delay_ms: int):
        if self.current_action != self.base_appearance:
            self.revert_timer.start(delay_ms)

    # ─────────────────────────────────────────
    # 对话
    # ─────────────────────────────────────────
    def _is_busy(self) -> bool:
        return self.active_worker is not None and self.active_worker.isRunning()

    def handle_user_message(self, text: str):
        if self._is_busy():
            return

        self.input_bar.set_busy(True)
        self.bubble.clear_files()
        self.bubble.show_message("……", duration_ms=0, status="思考中…")
        self._sync_floating_widgets()

        self.active_worker = EblanaAgentWorker(text, self.config, self.memory)
        self.active_worker.chunk_received.connect(self._on_agent_chunk)
        self.active_worker.tool_invoked.connect(self._on_agent_tool)
        self.active_worker.action_triggered.connect(self._on_agent_action)
        self.active_worker.files_produced.connect(self._on_agent_files)
        self.active_worker.status_changed.connect(self._on_agent_status)
        self.active_worker.finished_reply.connect(self._on_agent_finished)
        self.active_worker.error_occurred.connect(self._on_agent_error)
        self.active_worker.start()

    def _on_agent_chunk(self, current_text: str):
        self.bubble.show_message(current_text, duration_ms=0, allow_full=False)
        self._sync_floating_widgets()

    def _on_agent_status(self, status: str):
        self.bubble.set_status(status)
        self._sync_floating_widgets()

    def _on_agent_files(self, paths: list):
        self.bubble.set_files(paths)
        self._sync_floating_widgets()

    def _on_agent_tool(self, tool_name: str):
        self._react("exp_serious", "special", 0)
        self.bubble.set_status(tool_status_text(tool_name))
        self._sync_floating_widgets()

    def _on_agent_action(self, action_name: str):
        # 回复过程中保持该表情，回复结束后再计时恢复
        expression = "exp_calm" if action_name == "talk" else action_name
        self._react(expression, "talk", 0)

    def _on_agent_finished(self, final_text: str):
        self.input_bar.set_busy(False)
        self.bubble.show_message(final_text)
        self._sync_floating_widgets()
        self._revert_soon(REPLY_REACTION_MS)
        if self.log_window is not None and self.log_window.isVisible():
            self.log_window.refresh()

    def _on_agent_error(self, err_msg: str):
        self.input_bar.set_busy(False)
        self.bubble.show_message(err_msg, duration_ms=12000)
        self._sync_floating_widgets()
        self._revert_soon(1500)

    # ─────────────────────────────────────────
    # 菜单与托盘
    # ─────────────────────────────────────────
    def _menu_action(self, menu: QMenu, text: str, slot, checkable: bool = False) -> QAction:
        act = QAction(text, menu)
        if checkable:
            act.setCheckable(True)
            act.triggered.connect(slot)
        else:
            act.triggered.connect(lambda _checked=False: slot())
        menu.addAction(act)
        return act

    def _build_menu(self) -> QMenu:
        menu = QMenu(self)
        menu.setStyleSheet(theme.MENU_QSS)

        self.act_chat = self._menu_action(menu, "打开对话栏", self._toggle_input_bar)

        quick = QMenu("快捷指令", menu)
        for entry in QUICK_PROMPTS:
            if entry is None:
                quick.addSeparator()
                continue
            label, prompt = entry
            self._menu_action(quick, label, lambda p=prompt: self.handle_user_message(p))
        menu.addMenu(quick)
        menu.addSeparator()

        self.exp_menu = QMenu("表情", menu)
        menu.addMenu(self.exp_menu)
        self.skin_menu = QMenu("立绘", menu)
        menu.addMenu(self.skin_menu)
        self.act_lock = self._menu_action(menu, "锁定位置", self._set_locked, checkable=True)
        menu.addSeparator()

        self._menu_action(menu, "对话记录", self._open_log)
        self._menu_action(menu, "打开工作区", self._open_workspace)
        self._menu_action(menu, "清空对话记录…", self._clear_memory)
        self._menu_action(menu, "设置…", self._open_settings)
        menu.addSeparator()

        self.act_visible = self._menu_action(menu, "隐藏桌宠", self._toggle_visible)
        self._menu_action(menu, "退出", QApplication.quit)

        menu.aboutToShow.connect(self._refresh_menu)
        return menu

    def _refresh_menu(self):
        self.act_chat.setText("收起对话栏" if self.input_bar.isVisible() else "打开对话栏")
        self.act_lock.setChecked(bool(self.config.get("locked_position", False)))
        self.act_visible.setText("隐藏桌宠" if self.isVisible() else "显示桌宠")
        self._fill_choice_menu(self.exp_menu, EXPRESSION_IDS)
        self._fill_choice_menu(self.skin_menu, SKIN_IDS)

    def _fill_choice_menu(self, menu: QMenu, ids):
        menu.clear()
        old_group = self._choice_groups.pop(id(menu), None)
        if old_group is not None:
            old_group.deleteLater()  # 连同上一次生成的选项一起释放
        group = QActionGroup(menu)
        group.setExclusive(True)
        self._choice_groups[id(menu)] = group
        for clip_id in ids:
            clip = self.assets.clips.get(clip_id)
            if clip is None:
                continue
            act = QAction(clip.display_name, group)
            act.setCheckable(True)
            act.setChecked(self.base_appearance == clip_id)
            act.triggered.connect(lambda _checked=False, a=clip_id: self.play_action(a, update_base=True))
            menu.addAction(act)
        menu.menuAction().setVisible(not menu.isEmpty())

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._toggle_visible()

    def _toggle_visible(self):
        if self.isVisible():
            self.hide()
            self.bubble.hide()
            self.input_bar.hide()
        else:
            self.show()
            self._place_at_anchor()

    def _toggle_input_bar(self):
        if self.input_bar.isVisible():
            self.input_bar.hide()
        else:
            self._show_input_bar()

    def _show_input_bar(self):
        if not self.input_bar.isVisible():
            self.input_bar.show()
            self._sync_floating_widgets()
        self.input_bar.activateWindow()
        self.input_bar.input_edit.setFocus()

    def _set_locked(self, locked: bool):
        self.config.set("locked_position", bool(locked))

    def _open_settings(self):
        dlg = SettingsDialog(self.config, self)
        dlg.settings_saved.connect(self._on_settings_updated)
        dlg.exec()
        dlg.deleteLater()

    def _on_settings_updated(self):
        self.assets.reload(self.config.get("assets_path", ""))
        self.play_action(self.config.get("default_appearance", self.current_action), update_base=True)
        self.bubble.show_message("设置已生效，学者。", duration_ms=4000)
        self._sync_floating_widgets()

    def _clear_memory(self):
        box = QMessageBox(self)
        box.setWindowTitle("清空对话记录")
        box.setText("清空后，死芒将不再记得之前的对话。确定继续吗？")
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
        box.button(QMessageBox.StandardButton.Yes).setText("清空")
        box.button(QMessageBox.StandardButton.Cancel).setText("取消")
        box.setStyleSheet(theme.DIALOG_QSS.replace("QDialog", "QMessageBox"))
        if box.exec() != QMessageBox.StandardButton.Yes:
            return
        self.memory.clear()
        if self.log_window is not None and self.log_window.isVisible():
            self.log_window.refresh()
        self.bubble.show_message("之前的谈话，我已经烧掉了。重新开始吧，学者。", duration_ms=5000)
        self._sync_floating_widgets()

    # ─────────────────────────────────────────
    # 文件、工作区与对话记录
    # ─────────────────────────────────────────
    def _workspace(self):
        return skills.workspace_dir(self.config.get("workspace_dir", ""))

    def _open_workspace(self):
        try:
            open_path(self._workspace())
        except Exception as e:
            self.bubble.show_message(f"打不开工作区：{e}")
            self._sync_floating_widgets()

    def _open_log(self):
        if self.log_window is None:
            self.log_window = ConversationWindow(self.memory)
        self.log_window.present()

    def _on_bubble_link(self, href: str):
        kind, _, arg = href.partition(":")
        if kind in ("open", "reveal"):
            idx = int(arg) if arg.isdigit() else -1
            if 0 <= idx < len(self.bubble.files):
                path = self.bubble.files[idx]
                if path.exists():
                    open_path(path, reveal=(kind == "reveal"))
                else:
                    self.bubble.show_message("那份文件已经不在原处了，学者。")
                    self._sync_floating_widgets()
        elif kind == "log":
            self._open_log()
        elif kind == "workspace":
            self._open_workspace()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and any(u.isLocalFile() for u in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if not paths:
            return
        event.acceptProposedAction()
        listing = "；".join(paths)
        self._show_input_bar()
        self.input_bar.input_edit.setText(f"处理这个文件：{listing}　")
        self.input_bar.input_edit.setCursorPosition(len(self.input_bar.input_edit.text()))
        names = "、".join(p.replace("\\", "/").rsplit("/", 1)[-1] for p in paths[:3])
        self.bubble.show_message(f"{names}……要我怎么处理它，学者？", duration_ms=8000)
        self._sync_floating_widgets()

    def shutdown(self):
        self.tray.hide()
        if self._is_busy():
            self.active_worker.wait(1500)


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    installed = set(QFontDatabase.families())
    families = [f for f in theme.UI_FONT_FAMILIES if f in installed]
    if families:
        font = QFont(app.font())
        font.setFamilies(families + [app.font().family()])
        app.setFont(font)

    icon_path = OFFICIAL_ASSETS_DIR / "avatar_e0.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    # 只允许运行一个实例（开机自启 + 手动双击时不会出现两个死芒）
    lock = QLockFile(str(USER_DATA_DIR / "eblana-deskpet.lock"))
    if not lock.tryLock(100):
        QMessageBox.information(None, "死芒", "桌宠已经在运行了，请在任务栏托盘中找到它。")
        sys.exit(0)

    config = ConfigManager()

    if config.get("show_onboarding", True):
        onboarding = OnboardingDialog(config)
        if onboarding.exec() != OnboardingDialog.DialogCode.Accepted:
            sys.exit(0)

    pet = EblanaDeskPet(config)
    app.aboutToQuit.connect(pet.shutdown)
    pet.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
