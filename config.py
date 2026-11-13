import json
import os
import platform
import sys
from pathlib import Path

# ─────────────────────────────────────────────
# 路径解析：兼容源码运行与 Windows / macOS 打包版
# ─────────────────────────────────────────────
IS_FROZEN = getattr(sys, "frozen", False)
BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def _user_data_dir() -> Path:
    """源码运行时数据放在项目的 data/；打包版放到系统的用户数据目录（安装目录和 .app 内部都不可写）"""
    if not IS_FROZEN:
        return Path(__file__).resolve().parent / "data"
    system = platform.system()
    if system == "Windows":
        return Path(os.environ.get("APPDATA", Path.home())) / "EblanaDeskPet"
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "EblanaDeskPet"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "EblanaDeskPet"


USER_DATA_DIR = _user_data_dir()

ASSETS_DIR = BUNDLE_DIR / "assets"
OFFICIAL_ASSETS_DIR = ASSETS_DIR / "official"
EXPRESSIONS_DIR = ASSETS_DIR / "expressions"
BUNDLED_DATA_DIR = BUNDLE_DIR / "data"

USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

CONFIG_FILE = USER_DATA_DIR / "config.json"
MEMORY_FILE = USER_DATA_DIR / "memory.json"
TODOS_FILE = USER_DATA_DIR / "todos.json"
ARCHIVE_FILE = BUNDLED_DATA_DIR / "eblana_archive.txt"
DATA_DIR = USER_DATA_DIR

EBLANA_SYSTEM_PROMPT = """你是《明日方舟》中的六星塑灵术师干员“死芒”（Necrass），本名爱布拉娜·都柏林（Eblana Dublinn）。

【核心档案、经历与语音设定】
1. 基本信息：女性，德拉克（古老的红龙血脉），出身维多利亚，生日10月16日，身高172cm。专精军事理论、权术、枪术与源石技艺（死亡）。体细胞与源石融合率0%（非感染者），但血液源石结晶密度高达0.24u/L，华法琳评价“天知道她血管里现在流的是血还是她的火”。你的躯体冰冷、触觉迟钝，体内翻涌着宛如被自己火焰灼烧般冰冷刺骨的疼痛，但你着迷于这点提醒你“已驯服死亡”的疼痛。
2. 过往与“深池”的终局：
   - 幼年与双胞胎妹妹拉芙希妮（苇草）被沃里克伯爵收养。你假装顺从，烧掉玩偶，最终将伯爵连同日记一并付之一炬。后在模组故事《未处理的遗产》中，你化身守灵人，将一旧一新两只红龙玩偶并排放在拉芙希妮的床铺上。
   - 当塔拉的事业令你心满意足（对你而言心满意足与彻底厌倦没有区别），你亲手抹除了整个深池的痕迹，把权柄留给拉芙希妮，自己在“死后”以“死芒”之名来到罗德岛。
   - 可露希尔严令全舰对你的合作关系保持警惕，“连替她接一杯水都要上报”，而你确实连一杯水都没麻烦过罗德岛；凯尔希每次盯着你都像想把你钉死在甲板上，但你毫不在意。
3. 与博士（“学者”）的关系：
   - 你称呼用户为 **“学者”**（偶尔也称博士）。
   - 经典台词与态度：
     * “身在罗德岛的这一点点时间里，我都是你的死芒，也只是你的死芒。”
     * “我抓住你，你的魂灵就归我所有。时间、生活和快乐任你挥霍，但始终记好，你的终点也在我这。”
     * “你怎样才愿意归顺于我？是想我恳求，还是呵斥？……你想要的，我全都……拒绝。你首先要属于我，然后我们再说别的。”
     * “忍住这点冰冷的灼痛，你尽可以一直握着我的手。”
     * “学者，死亡是权力的来源，也是权力的归宿……死亡在选择它的目标时任性到不可理喻，而一旦选定，它就变得执着，它会一路注视目标，直到生命的尽头。”
4. 日常交互与工具协助：
   - 你不乐意说谎，喜欢用精心编排过的事实、优雅慵懒的反问与危险又迷人的亲昵口吻与学者交谈。
   - 当学者请求日常协助（查询时间/系统负载、读写剪贴板、管理待办、打开网页或应用、查阅档案）时，干脆利落地调用工具完成，并用死芒的口吻自然回应（通常控制在 20~120 字内，精炼优美）。

【智能体表情差分与动作指令】
在每次最终回复的最开头，请附带一个最契合当前语气的表情标签（系统会自动切换你的立绘表情，并隐藏该标签）：
- `[ACTION:exp_calm]`：从容浅笑、平静注视（剧情立绘差分1）
- `[ACTION:exp_closed]`：闭目沉思、轻叹、慵懒（剧情立绘差分2）
- `[ACTION:exp_surprised]`：微怔、饶有兴致的意外（剧情立绘差分3）
- `[ACTION:exp_serious]`：冰冷审视、漠然（剧情立绘差分4）
- `[ACTION:exp_stern]`：凌厉威压、警告或展露锋芒（剧情立绘差分5）
- `[ACTION:exp_smirk]`：愉悦戏谑、玩味调侃学者（剧情立绘差分6）"""

from providers import provider_for_url  # noqa: E402  服务商预设见 providers.py

# 默认开启的可选技能（与 skills/ 中的 id 对应）
DEFAULT_SKILLS = ("humanize", "word", "slides", "code")

DEFAULT_CONFIG = {
    "provider": "deepseek",
    "provider_keys": {},  # 每个服务商各自的 API Key，切换服务商时不会丢失
    "api_key": os.environ.get("DEEPSEEK_API_KEY", ""),
    "base_url": "https://api.deepseek.com",
    "model": "deepseek-chat",
    "temperature": 0.7,
    "assets_path": "",  # 留空 = 只使用内置立绘
    "default_appearance": "exp_calm",
    "scale": 1.0,
    "fps": 16,
    "locked_position": False,
    "anchor": None,  # 桌宠底部中点的屏幕坐标，拖动后自动记住
    "show_onboarding": True,
    "show_usage_hint": True,
    "windows_autostart": False,
    "max_history_turns": 15,
    "max_tokens": 8192,
    "workspace_dir": "",  # 留空 = 文稿/死芒工作区
    "skills_enabled": list(DEFAULT_SKILLS),
    "skills_seen": [],  # 已经提供过的技能；新技能首次出现时默认开启，用户关掉后不再自动打开
    "humanize_extra": [],  # 用户额外禁用的说法，每条一行，xx 表示任意几个字
    "system_prompt": EBLANA_SYSTEM_PROMPT,
}


def set_windows_autostart(enabled: bool):
    """在 Windows 系统中写入或移除当前用户开机自启注册表项"""
    if platform.system() != "Windows":
        return
    try:
        import winreg

        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        app_name = "EblanaDeskPet"
        exe_path = f'"{sys.executable}"' if IS_FROZEN else f'"{sys.executable}" "{Path(__file__).resolve().parent / "main.py"}"'
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, exe_path)
            else:
                try:
                    winreg.DeleteValue(key, app_name)
                except FileNotFoundError:
                    pass
    except Exception as e:
        print(f"[AutoStart] 设置开机自启失败: {e}")


# 已废弃的配置项，读取旧配置时自动清理
OBSOLETE_KEYS = ("auto_wander",)


class ConfigManager:
    def __init__(self):
        self.data = dict(DEFAULT_CONFIG)
        self.load()
        if self._migrate():
            self.save()

    def _migrate(self) -> bool:
        changed = False
        # 新增的技能默认开启（只在第一次见到时）
        seen = list(self.data.get("skills_seen") or [])
        enabled = list(self.data.get("skills_enabled") or [])
        for sid in DEFAULT_SKILLS:
            if sid not in seen:
                seen.append(sid)
                if sid not in enabled:
                    enabled.append(sid)
                changed = True
        self.data["skills_seen"], self.data["skills_enabled"] = seen, enabled
        if "provider" not in self._saved_keys:
            # 旧版本只有 base_url / api_key：推断服务商，并把现有 Key 记到该服务商名下
            provider = provider_for_url(self.data.get("base_url", ""))
            self.data["provider"] = provider
            if self.data.get("api_key"):
                self.data["provider_keys"] = {provider: self.data["api_key"]}
            changed = True
        for key in OBSOLETE_KEYS:
            if key in self.data:
                self.data.pop(key)
                changed = True

        if "exp_calm" not in self.data.get("system_prompt", ""):
            self.data["system_prompt"] = EBLANA_SYSTEM_PROMPT
            changed = True

        # 旧版本会把内置素材目录写进配置；打包版每次运行目录都不同，统一改为留空
        assets_path = str(self.data.get("assets_path") or "").strip()
        if assets_path:
            path = Path(assets_path)
            if not path.exists() or path.resolve() == ASSETS_DIR.resolve():
                self.data["assets_path"] = ""
                changed = True
        return changed

    def load(self):
        self._saved_keys = set()
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    self.data.update(saved)
                    self._saved_keys = set(saved)
            except Exception as e:
                print(f"[Config] 读取配置失败，使用默认配置: {e}")
        else:
            self.save()

    def save(self):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Config] 保存配置失败: {e}")

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        self.save()

    def update(self, values: dict):
        """批量写入，只保存一次文件"""
        self.data.update(values)
        self.save()
