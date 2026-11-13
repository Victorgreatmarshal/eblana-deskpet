import re
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap

from config import EXPRESSIONS_DIR, OFFICIAL_ASSETS_DIR


def natural_sort_key(path: Path):
    """按自然数字顺序排列 PNG 序列帧，例如 frame_2.png 在 frame_10.png 前面"""
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r"(\d+)", path.name)]


ACTION_ALIASES = {
    "idle": ["idle", "relax", "stand", "default", "待机", "站立", "基建待机"],
    "touch": ["touch", "interact", "poke", "tap", "戳一下", "互动", "触摸"],
    "talk": ["talk", "speak", "attack", "说话", "交谈", "攻击"],
    "special": ["special", "skill", "victory", "start", "e2", "精二", "死芒", "技能", "特种", "战斗"],
    "sleep": ["sleep", "sit", "小憩", "睡眠", "坐"],
}

# 剧情立绘表情差分（对话时会随语气切换）
EXPRESSION_IDS = ("exp_calm", "exp_closed", "exp_surprised", "exp_serious", "exp_stern", "exp_smirk")
# 全身立绘 / 时装 / Q 版（由用户手动选择，对话中不会被自动替换）
SKIN_IDS = ("idle", "special", "skin_summer", "skin_ambience", "chibi")

# 内置立绘清单：(动作 ID, 菜单显示名, 文件路径, 目标尺寸)
OFFICIAL_CLIPS_SPEC = [
    ("exp_calm", "从容浅笑", EXPRESSIONS_DIR / "exp_1_calm.png", 310),
    ("exp_closed", "闭目沉思", EXPRESSIONS_DIR / "exp_2_closed_eyes.png", 310),
    ("exp_surprised", "微怔讶异", EXPRESSIONS_DIR / "exp_3_surprised.png", 310),
    ("exp_serious", "冰冷审视", EXPRESSIONS_DIR / "exp_4_serious.png", 310),
    ("exp_stern", "凌厉威压", EXPRESSIONS_DIR / "exp_5_stern.png", 310),
    ("exp_smirk", "愉悦戏谑", EXPRESSIONS_DIR / "exp_6_smirk.png", 310),
    ("idle", "默认立绘", OFFICIAL_ASSETS_DIR / "skin_e0.png", 310),
    ("special", "精英二立绘", OFFICIAL_ASSETS_DIR / "skin_e2.png", 340),
    ("skin_summer", "时装 · 夏卉 FA161", OFFICIAL_ASSETS_DIR / "skin_summer.png", 330),
    ("skin_ambience", "时装 · 晶化信念", OFFICIAL_ASSETS_DIR / "skin_ambience.png", 330),
    # Q 版小人：Spine 待机动画（由 tools/webm_to_webp.py 从录屏 WebM 抠图生成的 2 秒循环）
    ("chibi", "Q 版小人", OFFICIAL_ASSETS_DIR / "chibi_idle.webp", 280),
]

# 用 QMovie 逐帧播放的动画格式
MOVIE_SUFFIXES = (".gif", ".webp")


def render_fit(src: QPixmap, box_w: float, box_h: float, dpr: float) -> QPixmap:
    """把图片等比缩放进 box（逻辑像素），并按屏幕缩放比渲染，高分屏下保持清晰"""
    if src.isNull():
        return src
    out = src.scaled(
        max(1, round(box_w * dpr)),
        max(1, round(box_h * dpr)),
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    out.setDevicePixelRatio(dpr)
    return out


class AnimationClip:
    """
    单个动作 / 表情差分。

    frames(scale, dpr) 返回按当前缩放与屏幕像素比渲染好的帧并缓存，
    动画计时器每帧只需切换缓存好的图片，不再逐帧重新缩放。
    movie_path 指向 GIF / 动画 WebP 时改由 QMovie 播放；movie_box 为显示时等比缩放进的方框（逻辑像素），
    为空则按原始尺寸显示。
    """

    def __init__(
        self,
        name: str,
        display_name: str = "",
        frames: Optional[List[QPixmap]] = None,
        movie_path: Optional[Path] = None,
        builder: Optional[Callable[[float, float], List[QPixmap]]] = None,
        custom: bool = False,
        movie_box: Optional[float] = None,
    ):
        self.name = name
        self.display_name = display_name or name
        self.movie_path: Optional[Path] = movie_path
        self.movie_box = movie_box
        self.custom = custom  # 来自用户自定义素材
        self._source: List[QPixmap] = frames or []
        self._builder = builder
        self._cache_key: Optional[Tuple[float, float]] = None
        self._cache: List[QPixmap] = []

    @property
    def is_movie(self) -> bool:
        return self.movie_path is not None

    def frames(self, scale: float = 1.0, dpr: float = 1.0) -> List[QPixmap]:
        key = (round(scale, 3), round(dpr, 3))
        if key != self._cache_key:
            if self._builder is not None:
                self._cache = self._builder(*key)
            else:
                self._cache = [
                    render_fit(p, p.width() * key[0], p.height() * key[0], key[1]) for p in self._source
                ]
            self._cache_key = key
        return self._cache


class AssetsManager:
    """管理内置立绘、表情差分以及用户自定义 GIF / PNG 序列帧。"""

    def __init__(self, assets_path: str):
        self.assets_path: Optional[Path] = None
        self.clips: Dict[str, AnimationClip] = {}
        self.reload(assets_path)

    def reload(self, assets_path: Optional[str] = None) -> List[str]:
        if assets_path is not None:
            self.assets_path = Path(assets_path) if assets_path.strip() else None
        self.clips.clear()

        if self.assets_path is not None and self.assets_path.exists():
            if self.assets_path.is_file():
                self._load_single_file(self.assets_path)
            elif self.assets_path.is_dir():
                self._load_directory(self.assets_path)

        self._register_official_clips()

        if not self.clips:
            self._generate_fallback_clips()

        return list(self.clips.keys())

    def _match_canonical_action(self, raw_name: str) -> str:
        lower = raw_name.lower()
        for canonical, aliases in ACTION_ALIASES.items():
            for alias in aliases:
                if alias in lower:
                    return canonical
        return raw_name

    def _load_single_file(self, file_path: Path):
        suffix = file_path.suffix.lower()
        if suffix == ".gif":
            self.clips["idle"] = AnimationClip("idle", file_path.stem, movie_path=file_path, custom=True)
        elif suffix in (".png", ".webp", ".jpg", ".jpeg"):
            pix = QPixmap(str(file_path))
            if not pix.isNull():
                self.clips["idle"] = AnimationClip("idle", file_path.stem, frames=[pix], custom=True)

    def _load_directory(self, folder: Path):
        subdirs = [
            d for d in folder.iterdir()
            if d.is_dir() and not d.name.startswith(".") and d.name not in ("official", "expressions")
        ]
        for subdir in sorted(subdirs, key=natural_sort_key):
            action_name = self._match_canonical_action(subdir.name)
            png_files = sorted(
                [p for p in subdir.iterdir() if p.suffix.lower() in (".png", ".webp")],
                key=natural_sort_key,
            )
            gif_files = sorted(
                [p for p in subdir.iterdir() if p.suffix.lower() == ".gif"],
                key=natural_sort_key,
            )
            if png_files:
                frames = [QPixmap(str(p)) for p in png_files]
                frames = [f for f in frames if not f.isNull()]
                if frames:
                    self.clips[action_name] = AnimationClip(action_name, subdir.name, frames=frames, custom=True)
            elif gif_files:
                self.clips[action_name] = AnimationClip(
                    action_name, subdir.name, movie_path=gif_files[0], custom=True
                )

        direct_gifs = sorted(
            [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".gif"],
            key=natural_sort_key,
        )
        for gif_file in direct_gifs:
            action_name = self._match_canonical_action(gif_file.stem)
            if action_name not in self.clips:
                self.clips[action_name] = AnimationClip(action_name, gif_file.stem, movie_path=gif_file, custom=True)
            if "idle" not in self.clips:
                self.clips["idle"] = AnimationClip("idle", gif_file.stem, movie_path=gif_file, custom=True)

        direct_pngs = sorted(
            [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in (".png", ".webp")],
            key=natural_sort_key,
        )
        if direct_pngs and not self.clips:
            frames = [QPixmap(str(p)) for p in direct_pngs]
            frames = [f for f in frames if not f.isNull()]
            if frames:
                self.clips["idle"] = AnimationClip("idle", folder.name, frames=frames, custom=True)

    def _register_official_clips(self):
        for act_id, disp_name, path, size in OFFICIAL_CLIPS_SPEC:
            if not path.exists() or act_id in self.clips:
                continue
            if path.suffix.lower() in MOVIE_SUFFIXES:
                self.clips[act_id] = AnimationClip(act_id, disp_name, movie_path=path, movie_box=size)
            else:
                self.clips[act_id] = AnimationClip(
                    act_id,
                    display_name=disp_name,
                    builder=lambda scale, dpr, p=path, s=size: [render_fit(QPixmap(str(p)), s * scale, s * scale, dpr)],
                )

        # 没有自定义 talk / touch 素材时，借用表情差分
        if "talk" not in self.clips and "exp_calm" in self.clips:
            self.clips["talk"] = self.clips["exp_calm"]
        if "touch" not in self.clips and "exp_smirk" in self.clips:
            self.clips["touch"] = self.clips["exp_smirk"]

    def get_clip(self, action: str) -> AnimationClip:
        if action in self.clips:
            return self.clips[action]
        if "exp_calm" in self.clips:
            return self.clips["exp_calm"]
        if "idle" in self.clips:
            return self.clips["idle"]
        return next(iter(self.clips.values()))

    def available_actions(self) -> List[str]:
        return list(self.clips.keys())

    def _generate_fallback_clips(self):
        pix = QPixmap(240, 260)
        pix.fill(Qt.GlobalColor.transparent)
        self.clips["idle"] = AnimationClip("idle", "默认", frames=[pix])
