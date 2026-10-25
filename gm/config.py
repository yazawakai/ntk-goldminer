# -*- coding: utf-8 -*-
"""黄金矿工 (Gold Miner) —— 全局配置。

窗口 / 颜色 / 物理 / 物品 / 关卡 / 道具 的所有数值都集中在这里，
只改这一个文件就能调整手感、难度与平衡性。
"""
from __future__ import annotations

import math
import os
import random

# ------------------------------------------------------------------ 路径
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSET_DIR = os.path.join(BASE_DIR, "assets")
IMAGE_DIR = os.path.join(ASSET_DIR, "images")   # 自定义贴图: <名字>.png
SOUND_DIR = os.path.join(ASSET_DIR, "sounds")   # 自定义音效: <名字>.wav
DATA_DIR = os.path.join(BASE_DIR, "data")
SCORE_FILE = os.path.join(DATA_DIR, "scoreboard.json")

# ------------------------------------------------------------------ 窗口
TITLE = "新三国黄金矿工"
WIDTH, HEIGHT = 960, 640
FPS = 60
FRAME_MS = max(1, int(1000 / FPS))
MAX_DT = 0.05                      # 掉帧保护：单帧最多推进 50ms

# ------------------------------------------------------------------ 版面
GROUND_Y = 168                     # 地表线
# 钩爪起点（绳子出来的地方）：放在**矿工下面**，也就是他脚下稍微入土的位置。
# 想让绳子更低/更高改这里的第二个数：GROUND_Y + 0 就是正好贴地表，+30 更深。
PIVOT = (WIDTH // 2, GROUND_Y + 18)
MIN_LEN = 46                       # 最短绳长
HOOK_R = 7                         # 钩爪碰撞半径
THETA_MAX = math.radians(78)       # 摆动最大角度（0 = 垂直向下）
FIELD_TOP = GROUND_Y + 62          # 物品可生成区域（留出钩爪静止时的位置）
FIELD_BOTTOM = HEIGHT - 24
FIELD_LEFT, FIELD_RIGHT = 30, WIDTH - 30
ITEM_GAP = 6                       # 物品之间的最小间隙

# ------------------------------------------------------------------ 物理
BASE_RETRACT = 300.0               # 空钩收绳基准速度 px/s
WEIGHT_K = 0.85                    # 重量对收绳速度的影响（越重越慢）
BOMB_RETRACT_MULT = 6.0            # 用炸弹后空钩返回倍率
POTION_TIME = 12.0                 # 沛国佳酿持续秒数
POTION_MULT = 2.0                  # 沛国佳酿收绳倍率
BOMB_RADIUS = 118                  # 炸弹爆炸波及半径（只波及石头）
TIME_BONUS_PER_SEC = 10            # 提前挖空矿场时，剩余时间折算分数

# ------------------------------------------------------------------ 颜色
COLORS = {
    "sky_top": "#0b1226",
    "sky_bottom": "#1d3055",
    "grass": "#4f7a2b",
    "dirt_top": "#7a4f26",
    "dirt_bottom": "#33200f",
    "panel": "#050a16",
    "text": "#f4f7ff",
    "text_dim": "#9fb0d0",
    "gold": "#ffcf49",
    "danger": "#ff5d5d",
    "ok": "#6ef0a0",
    "hook": "#dfe6f2",
    "rope": "#e8d9b5",
    "potion": "#49c8ff",
}

# 中文字体候选（按顺序取第一个系统里存在的）
FONT_CANDIDATES = (
    "Microsoft YaHei UI", "Microsoft YaHei", "SimHei", "SimSun",
    "PingFang SC", "Hiragino Sans GB", "Noto Sans CJK SC",
    "WenQuanYi Micro Hei", "Arial Unicode MS",
)

# 1x1 的深色半透明 PNG（base64），游戏里放大成整屏遮罩用
# —— tkinter 的 canvas 矩形没有 alpha，只有图片有，所以用它来做“变暗”效果
DIM_PNG_B64 = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNg5RJbDwABEgDVw0YDnQAAAABJRU5ErkJggg==")

# ------------------------------------------------------------------ 物品
# score       基础分值（0 表示用 random 区间随机）
# weight      重量系数，越重收绳越慢
# r           碰撞/绘制半径（像素）
# random      (min, max) 随机分值
# prop        抓到后变成道具
# rock        True 表示是石头（炸弹可以炸掉周围石头）
ITEMS = {
    "gold_small":    dict(label="小金块",   score=50,  weight=1.0, r=13),
    "gold_medium":   dict(label="中金块",   score=100, weight=1.5, r=18),
    "gold_large":    dict(label="大金块",   score=250, weight=2.2, r=25),
    "gold_huge":     dict(label="巨型金块", score=500, weight=3.0, r=32),
    "rock_small":    dict(label="小石头",   score=11,  weight=2.0, r=16, rock=True),
    "rock_large":    dict(label="大石头",   score=20,  weight=3.4, r=26, rock=True),
    "diamond":       dict(label="钻石",     score=600, weight=0.5, r=12),
    "money_bag":     dict(label="钱袋",     score=0,   weight=1.2, r=17, random=(120, 480)),
    "bomb_pickup":   dict(label="炸弹",     score=0,   weight=1.0, r=15, prop="bomb"),
    "potion_pickup": dict(label="强力水",   score=0,   weight=1.0, r=15, prop="potion"),
    "shuaian":       dict(label="帅案",     score=166,   weight=1.2, r=25),
    "xiaomianhu":    dict(label="笑面虎",   score=300, weight=2.0, r=30),
    "wujiaosha":     dict(label="乌角鲨",   score=450, weight=2.5, r=50),
    "dragon":        dict(label="龙", score=868, weight=4.0, r=50),
    "renzhijian":    dict(label="仁之剑", score=120, weight=1.0, r=20),
    "yizhijian":     dict(label="义之剑", score=120, weight=1.0, r=20),
    "silunche":      dict(label="四轮车", score=100, weight=1.5, r=25)
}

# ------------------------------------------------------------------ 道具 / 商店
# 道具**只能从商店购买**：每关结束后进入商店，用分数换道具，价格随关数上涨。
# 购买会直接从分数里扣（和经典黄金矿工一样，所以别把钱花光）。
# 想把“矿场里也能捡到道具”打开，把 PROPS_IN_FIELD 改成 True 即可。
PROPS = {
    "bomb":   dict(label="炸弹",   hotkey="1", tip="炸掉钩子上已抓住的东西，空钩极速返回"),
    "potion": dict(label="沛国佳酿", hotkey="2", tip="12 秒内收绳速度翻倍，配合大石头抢时间"),
}

START_PROPS = dict(bomb=0, potion=0)   # 开局自带道具（默认 0，都要自己买）
PROPS_IN_FIELD = False                 # 矿场里是否还会随机刷出道具

SHOP_ORDER = ("bomb", "potion")        # 商店里的排列顺序
SHOP = {                               # 售价 = min(cap, base + step × (关数-1))
    "bomb":   dict(base=180, step=35, cap=900),
    "potion": dict(base=260, step=45, cap=1100),
}


SHOP_REACTION_TIME = 1.2               # 退出商店时店长表情停留的秒数

# 店长立绘（放在 assets/images/<名字>.png，按整数倍缩放塞进相框、保持宽高比）
#   neutral / happy → 平时（也是买到东西闪一下时用的）
#   sad            → 一分钱没买就走
SHOP_KEEPER = {
    "neutral": "gongxidiekeyichengdile",
    "happy":   "gongxidiekeyichengdile",
    "sad":     "jingranbuxu",
}

# 离开商店时播放的语音（assets/sounds/<名字>.wav）：
#   bought → 这次买过东西（配 neutral/happy 那张立绘）
#   none   → 一分钱没花（配 sad 那张立绘）
SHOP_VOICE = {
    "bought": "gongxidiekeyichengdile",
    "none":   "jingranbuxu",
}

# 店长相框（逻辑坐标，画布是 960x640）。立绘会按**整数倍**缩放塞进「内画面」
# 并保持宽高比，所以想让立绘更大，就调大 SHOP_KEEPER_FRAME，内画面会自动跟着变大。
# 参考：490x280 的图放进 502x302 的内画面 = 原分辨率 1:1 显示。
SHOP_KEEPER_FRAME = (30, 92, 556, 458)  # 相框外框 x0, y0, x1, y1
SHOP_KEEPER_PAD = 12                    # 相框边厚：内画面 = 外框内缩这么多
SHOP_CAPTION_H = 40                     # 相框内底部台词条高度
# 立绘**本身**的放大倍率（相对“整张图刚好填满相框”的基准）：
#   1.0 → 整张图放大填满相框（人物比原图大，几乎不裁切）
#   1.5 → 再放大 1.5 倍并居中裁切，人物更大（默认，接近特写）
#   2.0 → 再放大 2 倍，只留画面中心，最“怼脸”但原图小的话会发虚
# 小数倍率也能用（内部用 zoom + subsample 拼出来）
SHOP_KEEPER_ZOOM = 1.5

# 店长的台词（每种随机取一条）。bye_spent 用于“本次逛店花过钱”（高兴脸），
# bye_free 用于“一分没花就走”（不高兴脸）。
SHOP_TALK = {
    "greet": ("欢迎光临！看看要点啥？", "家伙什儿都摆好了，随便挑。",
              "金子挖得多，我这儿什么都好说。"),
    "bought": ("好眼力！拿好，接着发财！", "爽快！这才像要下矿的人。",
               "多谢惠顾，祝你挖到大金块！"),
    "poor": ("钱不够啊，先去挖点金子吧。", "这个价，你现在还买不起。",
             "攒够了再来，我给你留着。"),
    "bye_spent": ("恭喜爹可以称帝了！",),
    "bye_free": ("竟然不许！",),
    "idle": ("石头别硬拉，白费时间。", "钻石最轻最值钱，看准了再出手。",
             "时间到之前把分数攒够，不然就收摊咯。"),
}


def shop_price(kind, level_no):
    """商店售价（按即将进入的第 level_no 关计算，level_no 从 1 开始）。"""
    cfg = SHOP[kind]
    steps = max(0, int(level_no) - 1)
    return int(min(cfg["cap"], cfg["base"] + cfg["step"] * steps))


def shop_talk(key):
    """随机取一条店长台词。

    容错：下面三种写法都能取到一整句话，不会只取到一个字 ——
        "bye_free": ("竟然不许！")           ← 这是字符串（少了逗号），整句返回
        "bye_free": ("竟然不许！",)          ← 单元组，整句返回
        "bye_free": ("A 台词", "B 台词")     ← 多句随机
    """
    entry = SHOP_TALK.get(key)
    if not entry:
        return "……"
    if isinstance(entry, str):
        return entry
    lines = [str(x) for x in entry]
    if len(lines) > 1 and all(len(x) == 1 for x in lines):
        return "".join(lines)              # 被逐字写开的句子，拼回去
    return random.choice(lines)


def prop_sprite(kind):
    """道具对应的贴图名（也是矿场物品名）。"""
    return kind + "_pickup"

# ------------------------------------------------------------------ 关卡
# 过关规则：
#   * 时间耗尽时结算：累计分数 >= target 则过关，否则游戏结束；
#   * 提前把矿场挖空 → 立刻过关，剩余时间按 TIME_BONUS_PER_SEC 折算奖励。
# 所以达到 target 之后可以继续挖，分数越多越好。
#
# LEVELS 里是 3 个手工设计的**简单关卡**（目标低、石头少、节奏慢）。
# 第 4 关开始不再写死，交给下面的 make_random_level() 随机生成无尽关卡。
LEVELS = [
    dict(
        short="第 1 关",
        name="第 1 关",
        hint="你的兵器不是双股剑吗，在我看来，一把叫仁之剑，一把叫义之剑。",
        time=60, target=600, swing=95.0, shoot=700.0,
        spawn=dict(gold_small=5, gold_medium=4, gold_large=3, diamond=2,
                   rock_small=4, rock_large=2, money_bag=1,
                   shuaian=3, renzhijian=1, yizhijian=1),
    ),
    dict(
        short="第 2 关",
        name="第 2 关",
        hint="这对堂兄弟，可谓是一对笑面虎，两头乌角鲨。",
        time=55, target=1500, swing=110.0, shoot=700.0,
        spawn=dict(gold_small=4, gold_medium=3, gold_large=2, gold_huge=1, diamond=2,
                   rock_small=3, rock_large=2, money_bag=2,
                   xiaomianhu=2, wujiaosha=2, silunche=2),
    ),
    dict(
        short="第 3 关",
        name="第 3 关",
        hint="他在投效大哥之前，已有卧龙之称。龙，可是帝王之征啊。",
        time=52, target=2700, swing=125.0, shoot=700.0,
        spawn=dict(gold_small=3, gold_medium=3, gold_large=2, gold_huge=1, diamond=2,
                   rock_small=3, rock_large=1, money_bag=2,
                   dragon=2, shuaian=2, silunche=2),
    ),
]

# ------------------------------------------------------------------ 随机无尽关卡
# 第 4 关起：目标分、时间、钩子速度、物品表全部随机，难度随关数递增。
RANDOM_BASE_TARGET = LEVELS[-1]["target"]   # 从最后一关的目标分往上加
RANDOM_TARGET_STEP = 1000                    # 每关目标分增量
RANDOM_TARGET_JITTER = 300                  # 增量的随机浮动
RANDOM_BASE_TIME = LEVELS[-1]["time"]
RANDOM_MIN_TIME = 34                        # 时间下限（秒）
RANDOM_TIME_DECAY = 2                       # 每关减少的秒数
RANDOM_BASE_SWING = LEVELS[-1]["swing"]
RANDOM_BASE_SHOOT = LEVELS[-1]["shoot"]
RANDOM_MAX_SWING = 180.0                    # 摆动速度上限 °/s
RANDOM_MAX_SHOOT = 980.0                    # 发射速度上限 px/s
RANDOM_HINTS = (
    "酒是老英雄，越喝越奋勇。",
    "战至最后一刻，自刎归天。",
    "我看你是舍不得这张帅案吧！",
    "全军冲杀蜀军阵营，直奔诸葛亮四轮车！",
    "你的兵器不是双股剑吗，在我看来，一把叫仁之剑，一把叫义之剑。",
    "这对堂兄弟，可谓是一对笑面虎，两头乌角鲨。",
    "他在投效大哥之前，已有卧龙之称。龙，可是帝王之征啊。",
    "那好啊，他过江我也过江。",
    "风从虎，云从龙，龙虎英雄傲苍穹。",
    "好火啊，比夷陵之火还好啊。",
    "只要曹孟德一息尚存，他就战无不胜。",
    "不是阿瞒害了你，是这个乱世害了你。",
    "徐州城不愧为中原第一雄关。",
    "是啊，吃什么",
    "你拾它作甚，你今天捡起来，他明天还要来撒野的。",
    "从这一刻起，历史发生了剧变。",
    "接着奏乐，接着舞。",
    "曹贼！奸贼！恶贼！逆贼！",
    "生死不明，那就是死了。",
    "胜兵必骄，骄兵必败，败兵必哀，哀兵必胜",
    "那就是夷陵山脉最后一道山梁",
    "我在想我的那些个蛐蛐，它们个个有情有义",
)
_RANDOM_CACHE = {}

def is_random_level(index):
    """index 是否属于随机关卡（第 4 关开始）。"""
    return index >= len(LEVELS)


def reset_random_levels():
    """重开一局时清空随机关卡缓存，让每次游玩都拿到新的随机矿脉。"""
    _RANDOM_CACHE.clear()


def make_random_level(index):
    """随机生成第 index 关（index >= 3）。同一 index 在一次游戏内保持一致。"""
    i = index - len(LEVELS)                 # 第几个随机关：0,1,2,...
    h = i // 2                              # 难度档位，每两关提一档
    target = RANDOM_BASE_TARGET + RANDOM_TARGET_JITTER * (sum(range(4, min(index + 2, 11))))
    if index >= 10:
        target += RANDOM_TARGET_JITTER * 10 * (index - 10)
    time_s = max(RANDOM_MIN_TIME,
                 RANDOM_BASE_TIME - RANDOM_TIME_DECAY * (i + 1))
    swing = min(RANDOM_MAX_SWING, RANDOM_BASE_SWING + 4.0 * i)
    shoot = 700.0

    # 难度只升不降：时间不比上一关多，目标 / 速度不比上一关低
    prev = _RANDOM_CACHE.get(index - 1) or LEVELS[-1]
    time_s = min(time_s, prev["time"])
    target = max(target, prev["target"] + 200)
    swing = max(swing, prev["swing"])
    shoot = max(shoot, prev["shoot"])

    def cnt(lo, hi, extra=0, cap=8):
        return max(1, min(cap, random.randint(lo, hi) + extra))

    def mincnt(lo, hi, extra=0):
        t = random.randint(lo, hi)
        if t - extra <= 0:
            return random.randint(0, 1)
        return max(1, t - extra)

    return dict(
        short="第 %d 关" % (index + 1),
        name="第 %d 关" % (index + 1),
        hint=random.choice(RANDOM_HINTS) + "（目标 %d 分 / %d 秒）" % (target, time_s),
        time=time_s, target=target, swing=swing, shoot=shoot,
        spawn=dict(
            gold_small=mincnt(2, 4, h),
            gold_medium=mincnt(2, 4, h),
            gold_large=mincnt(1, 3, h),
            gold_huge=mincnt(1, 2, h // 2),
            diamond=mincnt(1, 3, h // 2),
            rock_small=mincnt(2, 4, h),
            rock_large=mincnt(1, 3, h),
            money_bag=mincnt(0, 2, h),
            bomb_pickup=cnt(1, 2),
            potion_pickup=cnt(1, 2),
            shuaian=cnt(1, 3, h),
            xiaomianhu=cnt(2, 2),
            wujiaosha=cnt(2, 2),
            dragon=cnt(1, 2, h // 2, 4),
            renzhijian=cnt(1, 2, h),
            yizhijian=cnt(1, 2, h),
            silunche=cnt(1, 2, h),
        ),
        random=True,
    )


def level(i):
    """安全取关卡配置。

    前 3 关取 LEVELS；之后按 index 随机生成并缓存（钩子每帧都会取配置，
    必须保证同一关返回同一个 dict，否则速度会每帧抖动）。
    """
    if i < 0:
        i = 0
    if i < len(LEVELS):
        return LEVELS[i]
    if i not in _RANDOM_CACHE:
        _RANDOM_CACHE[i] = make_random_level(i)
    return _RANDOM_CACHE[i]

# ------------------------------------------------------------------ 音效名
# 对应 assets/sounds/<名字>.wav，缺文件自动静音
SOUNDS = ("hook_shoot", "hook_hit", "collect", "explosion",
          "powerup", "level_up", "game_over", "tick", "deny",
          "gongxidiekeyichengdile", "jingranbuxu","level_begin","guanyu_song",
          "shuaian", "xiaomianhu", "wujiaosha", "dragon", "renzhijian", "yizhijian",
          "silunche")

# ------------------------------------------------------------------ 音频
# 音效走 MCI 多路混音：新音效**不会打断**正在播放的旧音效（池满时丢弃新音效）。
#   AUDIO_VOICES  声道池大小（同时最多几段声音）。如果加了十几秒的长语音
#                 （比如每关开场的 level_begin.wav、结束时的 guanyu_song.wav），
#                 把它调大一点，免得长语音占满池子让音效播不出来。
#   AUDIO_VOLUME  0.0 ~ 1.0（部分声卡驱动不支持单独音量时会自动忽略）
#   AUDIO_BACKEND "auto" 自动；"mci" 只用多路；"winsound" 强制单通道（对比用）
AUDIO_VOICES = 12
AUDIO_VOLUME = 1.0
AUDIO_BACKEND = "auto"

# 贴图名（对应 assets/images/<名字>.png）
SPRITES = tuple(ITEMS) + ("miner", "background")


# ------------------------------------------------------------------ 高 DPI
# 游戏逻辑永远按 960x640 设计；在 200% 缩放的屏幕上用一个整数倍率放大画布，
# 这样界面又大又清晰（而不是被系统拉伸得模糊）。
UI_SCALE_MAX = 3


def detect_ui_scale(root=None):
    """按屏幕 DPI 选整数倍率 1/2/3，并保证窗口不超出屏幕。"""
    dpi = 96
    try:
        import ctypes
        dpi = int(ctypes.windll.user32.GetDpiForSystem())
    except Exception:
        dpi = 96
    if dpi >= 264:
        scale = 3
    elif dpi >= 168:
        scale = 2
    else:
        scale = 1
    scale = max(1, min(UI_SCALE_MAX, scale))

    screen_w = screen_h = None
    if root is not None:
        try:
            screen_w, screen_h = root.winfo_screenwidth(), root.winfo_screenheight()
        except Exception:
            pass
    while scale > 1 and screen_w and screen_h and (
            WIDTH * scale > screen_w - 40 or HEIGHT * scale > screen_h - 90):
        scale -= 1
    return scale

