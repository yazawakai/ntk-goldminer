# -*- coding: utf-8 -*-
"""黄金矿工主程序：状态机 + 主循环 + 玩法逻辑 + 全部绘制。

状态机
------
menu  开始界面（背景是“待机演示”，钩子会自己慢慢摆）
playing / paused / level_clear / game_over / win

按键
----
空格 发射钩子  1 炸弹  2 沛国佳酿  P 暂停  M 静音/R 重开  Esc 退出
"""
from __future__ import annotations

import math
import random
import time
import tkinter as tk

from . import config as C
from . import scoreboard
from .entities import FloatingText, Hook, Item, burst
from .resources import Resources


class Painter:
    """把 960x640 的逻辑坐标映射到真实画布像素。

    用法和 ``tkinter.Canvas`` 基本一致，但所有坐标 / 线宽 / 字号都会被放大
    ``scale`` 倍。于是游戏逻辑始终按 960x640 设计，在 200% 缩放的屏幕上
    却能画出一个又大又清晰的窗口（而不是被系统拉伸得模模糊糊）。
    """

    def __init__(self, canvas, scale):
        self.c = canvas
        self.s = float(max(1, int(scale)))

    def _flat(self, coords):
        if len(coords) == 1 and isinstance(coords[0], (list, tuple)):
            coords = tuple(coords[0])
        s = self.s
        return tuple(v * s for v in coords)

    def _kw(self, kw):
        if kw.get("width") is not None:
            kw["width"] = max(1, int(round(float(kw["width"]) * self.s)))
        font = kw.get("font")
        if font and len(font) >= 2:
            kw["font"] = (font[0], int(round(font[1] * self.s))) + tuple(font[2:])
        return kw

    def create_rectangle(self, *c, **kw):
        return self.c.create_rectangle(*self._flat(c), **self._kw(kw))

    def create_oval(self, *c, **kw):
        return self.c.create_oval(*self._flat(c), **self._kw(kw))

    def create_line(self, *c, **kw):
        return self.c.create_line(*self._flat(c), **self._kw(kw))

    def create_polygon(self, *c, **kw):
        return self.c.create_polygon(*self._flat(c), **self._kw(kw))

    def create_arc(self, *c, **kw):
        return self.c.create_arc(*self._flat(c), **self._kw(kw))

    def create_text(self, x, y, **kw):
        return self.c.create_text(x * self.s, y * self.s, **self._kw(kw))

    def create_image(self, x, y, **kw):
        return self.c.create_image(x * self.s, y * self.s, **kw)

    def size(self, w, h):
        """把逻辑尺寸换算成贴图实际像素尺寸。"""
        return (max(1, int(round(w * self.s))), max(1, int(round(h * self.s))))


class GoldMinerGame:
    # ================================================================== 初始化
    def __init__(self, root: tk.Tk, ui_scale=None):
        self.root = root
        self.scale = int(ui_scale or C.detect_ui_scale(root))
        self.canvas = tk.Canvas(root, width=C.WIDTH * self.scale, height=C.HEIGHT * self.scale,
                                highlightthickness=0, bd=0, bg=C.COLORS["sky_top"])
        self.canvas.pack()
        self.p = Painter(self.canvas, self.scale)
        self.res = Resources()

        # ---- 运行时状态
        self.state = "menu"
        self.running = True
        self.anim = 0.0
        self.last_time = time.perf_counter()

        self.score = 0
        self.level_index = 0
        self.items = []          # 当前场上的物品（菜单时是演示物品）
        self.particles = []
        self.texts = []
        self.hook = Hook()
        self.inventory = {"bomb": C.START_PROPS.get("bomb", 0),
                          "potion": C.START_PROPS.get("potion", 0)}
        self.pending_items = None    # 商店里预先摆好的下一关矿场
        self.shop_state = "browse"   # browse（逛店/买东西） → reaction（店长表情）
        self.shop_expr = "neutral"   # 店长表情：neutral / happy / sad
        self.shop_line = ""
        self.shop_spent = 0
        self.shop_bought = 0
        self.shop_hover = None
        self.shop_flash_timer = 0.0
        self.shop_reaction_timer = 0.0
        self.shop_msg = None
        self.shop_msg_timer = 0.0
        self.shop_ok = True
        self.potion_timer = 0.0
        self.time_left = 0.0
        self.time_total = 1.0
        self.last_tick_second = None
        self.hint_timer = 0.0
        self.level_bonus = 0
        self.target_done = False     # 本关是否已达标（达标后不结束，继续挖）
        self.clear_reason = ""       # "clear" = 挖空矿场， "timeup" = 时间耗尽
        self.overlay_timer = 0.0
        self.toast = None
        self.toast_timer = 0.0
        self.shake = 0.0
        self.flash = 0.0
        self.name_buffer = ""
        self.name_saved = False
        self.fixed_cleared = False   # 是否已通过 3 个手工简单关卡（之后是随机无尽）
        self.scores = scoreboard.load()
        self.best_score = int(self.scores[0]["score"]) if self.scores else 0

        self._dim_img = None
        self._dim_src = None
        self.menu_items = self._spawn_items(C.LEVELS[0])   # 待机演示用
        self.items = self.menu_items

        self._bind_keys()
        self._draw_static_background()
        self.root.after(C.FRAME_MS, self.tick)

    # ================================================================== 基础设施
    def _bind_keys(self):
        self.root.bind("<KeyPress>", self.on_key)
        self.canvas.bind("<Button-1>", self.on_click)     # 商店里用鼠标点着买
        self.canvas.bind("<Motion>", self.on_motion)
        self.canvas.focus_set()
        self.root.focus_force()

    # ================================================================== 鼠标
    def _mouse_xy(self, event):
        """画布像素 → 960x640 逻辑坐标（高 DPI 下画布被放大了 self.scale 倍）。"""
        return event.x / float(self.scale), event.y / float(self.scale)

    def on_motion(self, event):
        if self.state != "shop" or self.shop_state != "browse":
            self.shop_hover = None
            return
        x, y = self._mouse_xy(event)
        self.shop_hover = self._shop_hit(x, y)

    def on_click(self, event):
        if self.state != "shop" or self.shop_state != "browse":
            return
        x, y = self._mouse_xy(event)
        hit = self._shop_hit(x, y)
        if hit in C.PROPS:                    # 点商品 = 购买
            self.buy(hit)
            self.shop_hover = hit
        elif hit == "next":                   # 点按钮 = 出发
            self.leave_shop()
        elif hit == "keeper":                 # 点店长 = 闲聊
            self.shop_line = C.shop_talk("idle")
            self.shop_msg, self.shop_msg_timer, self.shop_ok = None, 0.0, True

    def quit(self):
        self.running = False
        try:
            self.res.close()          # 释放 MCI 音频声道
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass

    def target(self):
        return int(C.level(self.level_index)["target"])

    def bar_start(self):
        return int(C.level(self.level_index - 1)["target"]) if self.level_index > 0 else 0

    # ================================================================== 主循环
    def tick(self):
        if not self.running:
            return
        now = time.perf_counter()
        dt = min(now - self.last_time, C.MAX_DT)     # 掉帧保护
        self.last_time = now
        self.step(dt)
        self.render()
        self.root.after(C.FRAME_MS, self.tick)

    def step(self, dt):
        """推进一帧逻辑（与 tkinter 解耦，方便自动测试/回放）。"""
        self.anim += dt

        if self.state == "playing":
            self.update(dt)
        elif self.state == "level_clear":
            self.overlay_timer -= dt
            self._update_effects(dt)
            if self.overlay_timer <= 0:
                self.open_shop()                         # 过关后先逛商店，再进下一关
        elif self.state == "shop":
            self._update_effects(dt)
            if self.shop_state == "reaction":
                # 先让玩家看清店长的表情，再进下一关
                self.shop_reaction_timer -= dt
                if self.shop_reaction_timer <= 0:
                    self.enter_next_level()
            elif self.shop_flash_timer > 0:
                self.shop_flash_timer -= dt
                if self.shop_flash_timer <= 0:
                    self.shop_expr = "neutral"        # 高兴一下，然後回到平时的表情
        elif self.state == "menu":
            self.hook.update_swing(dt, 42.0)          # 待机演示
            self._update_effects(dt)
        else:
            self._update_effects(dt)

    # ================================================================== 流程控制
    def start_game(self):
        self.score = 0
        C.reset_random_levels()          # 新的一局：随机关卡重新洗牌
        self.fixed_cleared = False
        self.inventory = {"bomb": C.START_PROPS.get("bomb", 0),
                          "potion": C.START_PROPS.get("potion", 0)}
        self.pending_items = None
        self.shop_state, self.shop_expr = "browse", "neutral"
        self.shop_spent = self.shop_bought = 0
        self.shop_hover = None
        self.shop_msg, self.shop_msg_timer, self.shop_ok = None, 0.0, True
        self.shop_flash_timer = self.shop_reaction_timer = 0.0
        self.scores = scoreboard.load()
        self.best_score = int(self.scores[0]["score"]) if self.scores else 0
        self.particles.clear()
        self.texts.clear()
        self.start_level(0)

    def start_level(self, index, items=None):
        """开始第 index 关。items 由商店预先摆好时直接复用（商店预览 = 实际矿场）。"""
        cfg = C.level(index)
        self.level_index = index
        self.time_total = float(cfg["time"])
        self.time_left = float(cfg["time"])
        self.last_tick_second = None
        self.hook.reset()
        self.items = items if items is not None else self._spawn_items(cfg)
        self.pending_items = None
        self.particles.clear()
        self.texts.clear()
        self.potion_timer = 0.0
        self.hint_timer = 4.5
        self.overlay_timer = 0.0
        self.level_bonus = 0
        self.target_done = self.score >= self.target()
        self.clear_reason = ""
        self.toast = None
        self.toast_timer = 0.0
        self.res.play("level_begin")
        # 道具不再每关重置（买来的道具会留到后面的关卡）；
        # 如果某关配置里写了 start_props，则作为该关额外赠送
        for key, num in cfg.get("start_props", {}).items():
            self.inventory[key] = self.inventory.get(key, 0) + num
        self.state = "playing"
        self._toast("目标：累计 %d 分　剩余时间 %d 秒" % (self.target(), int(self.time_total)), 2.6)

    # ================================================================== 商店
    def open_shop(self):
        """过关后进入商店（同时把下一关的矿场先摆好，离开时直接用这份）。"""
        nxt = self.level_index + 1
        cfg = C.level(nxt)
        self.level_index = nxt                       # HUD 直接显示下一关信息
        self.time_total = float(cfg["time"])
        self.time_left = float(cfg["time"])
        self.potion_timer = 0.0
        self.hint_timer = 0.0
        self.hook.reset()
        self.pending_items = self._spawn_items(cfg)
        self.items = self.pending_items
        self.shop_state = "browse"                   # browse → reaction → 下一关
        self.shop_expr = "neutral"                   # 店长表情
        self.shop_spent = 0                          # 本次逛店花了多少
        self.shop_bought = 0                         # 本次逛店买了几件
        self.shop_hover = None
        self.shop_msg, self.shop_msg_timer, self.shop_ok = None, 0.0, True
        self.shop_line = C.shop_talk("greet")
        self.shop_reaction_timer = 0.0
        self.state = "shop"
        self.res.play("powerup")

    def shop_price(self, kind):
        return C.shop_price(kind, self.level_index + 1)

    def buy(self, kind):
        """商店购买：直接扣分。分数不够就买不了。"""
        if self.state != "shop" or self.shop_state != "browse":
            return False
        price = self.shop_price(kind)
        label = C.PROPS[kind]["label"]
        if self.score < price:
            self.shop_ok = False
            self.shop_msg = "分数不够：%s 要 %d 分，你只有 %d 分" % (label, price, self.score)
            self.shop_msg_timer = 2.4
            self.shop_line = C.shop_talk("poor")
            self.res.play("deny")
            return False
        self.score -= price
        self.inventory[kind] = self.inventory.get(kind, 0) + 1      # 跨关保留
        self.shop_spent += price
        self.shop_bought += 1
        self.shop_ok = True
        self.shop_msg = "买入 %s（-%d 分），现在共有 %d 个" % (label, price, self.inventory[kind])
        self.shop_msg_timer = 2.4
        self.shop_line = C.shop_talk("bought")
        self.shop_expr = "happy"                     # 买到东西 → 立刻高兴
        self.shop_flash_timer = 1.4
        self.res.play("collect")
        return True

    def leave_shop(self):
        """离开商店：按本次是否消费切换店长立绘，并播放对应语音。"""
        if self.state != "shop" or self.shop_state != "browse":
            return False
        self.shop_state = "reaction"
        self.shop_hover = None
        if self.shop_bought > 0:                       # 花过钱 → 平时那套立绘 + 夸奖语音
            self.shop_expr = "happy"
            self.shop_line = C.shop_talk("bye_spent")
            voice = C.SHOP_VOICE.get("bought")
        else:                                          # 空手走 → 不高兴立绘 + 抱怨语音
            self.shop_expr = "sad"
            self.shop_line = C.shop_talk("bye_free")
            voice = C.SHOP_VOICE.get("none")
        if voice:
            self.res.play(voice)                       # 店长语音（多路混音，不会打断别的音效）
        self.shop_reaction_timer = C.SHOP_REACTION_TIME
        return True

    def enter_next_level(self):
        """真正开始下一关（用商店里已经摆好的那份矿场）。"""
        items = self.pending_items
        self.shop_msg = None
        self.shop_msg_timer = 0.0
        self.start_level(self.level_index, items=items)

    def game_over(self):
        self.state = "game_over"
        self.name_buffer = ""
        self.name_saved = False
        self.res.play("guanyu_song")

    def save_score(self):
        if self.name_saved:
            return
        self.scores = scoreboard.add(self.name_buffer.strip() or "天意爷",
                                     self.score, self.level_index + 1,
                                     self.fixed_cleared)
        self.best_score = int(self.scores[0]["score"]) if self.scores else self.score
        self.name_saved = True
        self.res.play("collect")

    # ================================================================== 关卡生成
    def _spawn_items(self, cfg):
        """按关卡配置随机撒物品，互不重叠。

        道具默认不再出现在矿场里 —— 它们只在商店卖；
        想改回去把 config.PROPS_IN_FIELD 设成 True。
        """
        items = []
        for key, count in cfg["spawn"].items():
            if not C.PROPS_IN_FIELD and C.ITEMS[key].get("prop"):
                continue
            for _ in range(count):
                item = self._place_item(key, items)
                if item is not None:
                    items.append(item)
        return items

    @staticmethod
    def _reachable(x, y, r=0.0, margin_deg=2.5):
        """这点在钩爪的摆动扇形里吗（顺手把物品半径算成角度余量）。

        钩爪起点在矿工下面（PIVOT），只能左右摆 ±THETA_MAX，所以矿场上方两个角落
        其实够不到。生成物品时必须过滤掉这些点，否则会出现“永远挖不到的东西”，
        而“挖空矿场”又是提前过关的条件。
        """
        dx = x - C.PIVOT[0]
        dy = y - C.PIVOT[1]
        if dy <= 0:
            return False
        deg = abs(math.degrees(math.atan2(dx, dy)))
        slack = math.degrees(math.atan2(r + C.HOOK_R, max(1.0, math.hypot(dx, dy))))
        return deg - slack <= math.degrees(C.THETA_MAX) - margin_deg

    @staticmethod
    def _place_item(key, placed):
        r = C.ITEMS[key]["r"]
        for _ in range(240):                       # 拒绝采样，最多试 240 次
            x = random.uniform(C.FIELD_LEFT + r, C.FIELD_RIGHT - r)
            y = random.uniform(C.FIELD_TOP + r, C.FIELD_BOTTOM - r)
            if not GoldMinerGame._reachable(x, y, r):
                # 撒到钩子够不到的角落了 → 把 x 拉回扇形内再试一次
                span = math.tan(C.THETA_MAX - math.radians(3.0)) * max(1.0, y - C.PIVOT[1])
                lo = max(C.FIELD_LEFT + r, C.PIVOT[0] - span)
                hi = min(C.FIELD_RIGHT - r, C.PIVOT[0] + span)
                if hi <= lo:
                    continue
                x = random.uniform(lo, hi)
                if not GoldMinerGame._reachable(x, y, r):
                    continue
            ok = True
            for other in placed:
                dx, dy = x - other.x, y - other.y
                if dx * dx + dy * dy < (r + other.r + C.ITEM_GAP) ** 2:
                    ok = False
                    break
            if ok:
                return Item(key, x, y)
        return None                                # 放不下就少一个，保证不重叠

    # ================================================================== 输入
    def on_key(self, event):
        key = event.keysym

        # ---------- 全局
        if key == "Escape":
            self.quit()
            return

        # ---------- 结算界面：输入名字（这里的按键优先用于打字，M 不当静音用）
        if self.state == "game_over":
            if self.name_saved:
                if key in ("r", "R", "Return", "KP_Enter", "space"):
                    self.start_game()
                return
            if key == "BackSpace":
                self.name_buffer = self.name_buffer[:-1]
            elif key in ("Return", "KP_Enter"):
                self.save_score()
            elif key in ("r", "R") and not self.name_buffer:
                self.start_game()
            elif event.char and event.char.isprintable() and len(self.name_buffer) < 10:
                self.name_buffer += event.char
            return

        # ---------- 静音开关
        if key in ("m", "M"):
            muted = self.res.toggle_mute()
            self._toast("音效已%s" % ("静音" if muted else "开启"))
            return

        # ---------- 商店（M 仍然可以静音，所以放在静音开关之后）
        if self.state == "shop":
            if self.shop_state == "browse":
                if key == "1":
                    self.buy("bomb")
                elif key == "2":
                    self.buy("potion")
                elif key in ("Return", "KP_Enter", "space"):
                    self.leave_shop()
            return

        # ---------- 开始界面
        if self.state == "menu":
            if key in ("Return", "KP_Enter", "space"):
                self.start_game()
            return

        # ---------- 过关过场
        if self.state == "level_clear":
            if key == "space":
                self.overlay_timer = 0.0
            return

        # ---------- 暂停
        if self.state == "paused":
            if key in ("p", "P", "space", "Return"):
                self.state = "playing"
            return

        # ---------- 游戏中
        if key == "space":
            self.launch()
        elif key in ("p", "P"):
            self.state = "paused"
        elif key == "1":
            self.use_prop("bomb")
        elif key == "2":
            self.use_prop("potion")

    # ================================================================== 玩法
    def launch(self):
        if self.hook.state != Hook.SWING:
            return
        self.hook.state = Hook.SHOOT
        self.hook.claw = 1.0
        self.res.play("hook_shoot")

    def use_prop(self, kind):
        if self.inventory.get(kind, 0) <= 0:
            self._toast("没有%s了" % C.PROPS[kind]["label"])
            self.res.play("deny")
            return
        if kind == "bomb":
            if not (self.hook.state == Hook.RETRACT and self.hook.grabbed is not None):
                self._toast("炸弹要在钩子抓住东西以后用")
                self.res.play("deny")
                return
            self.inventory["bomb"] -= 1
            self._explode(self.hook.grabbed)
            self.hook.grabbed = None
            self.hook.bomb_boost = True
            self.shake = 0.4
            self.flash = 0.2
            self.res.play("nya")
            self._toast("爆破！空钩极速返回")
        else:
            self.inventory["potion"] -= 1
            self.potion_timer = C.POTION_TIME
            self.res.play("dangfuyidabai")
            self._toast("沛国佳酿生效：收绳 x%.1f，持续 %.0f 秒" % (C.POTION_MULT, C.POTION_TIME))

    def _explode(self, item):
        """炸掉手里的东西，并波及半径内的石头。"""
        cx, cy = item.x, item.y
        item.alive = False
        for other in self.items:
            if other.alive and other is not item and other.rock:
                if math.hypot(other.x - cx, other.y - cy) <= C.BOMB_RADIUS:
                    other.alive = False
                    self.particles += burst(other.x, other.y, "#9aa1ad", 9, speed=150)
        self.particles += burst(cx, cy, "#ffb347", 26, speed=260, life=0.75, size=5)

    def update(self, dt):
        # ---- 各种计时器
        if self.hint_timer > 0:
            self.hint_timer -= dt
        if self.potion_timer > 0:
            self.potion_timer = max(0.0, self.potion_timer - dt)
            if self.potion_timer == 0.0:
                self._toast("沛国佳酿效果结束")

        # ---- 倒计时
        self.time_left -= dt
        sec = int(math.ceil(max(0.0, self.time_left)))
        if sec != self.last_tick_second:
            self.last_tick_second = sec
            if 0 < sec <= 10:
                self.res.play("tick")
        if self.time_left <= 0:
            self.time_left = 0.0
            self._update_effects(dt)
            # 时间耗尽才结算：达标过关，没达标就结束
            if self.score >= self.target():
                self._level_clear(bonus=False)
            else:
                self.game_over()
            return

        # ---- 钩子 / 物品 / 特效
        self._update_hook(dt)
        self.items = [it for it in self.items if it.alive]
        self._update_effects(dt)

        # ---- 达标只是提示，不结束关卡（可以继续挖分）
        if not self.target_done and self.score >= self.target():
            self.target_done = True
            self.res.play("powerup")
            self._toast("目标已达成！继续挖，挖空矿场有剩余时间奖励", 3.0)

        # ---- 提前把矿场挖空 → 立刻过关，剩余时间折算奖励
        if not self.items:
            self._level_clear(bonus=True)

    def _update_hook(self, dt):
        h = self.hook
        cfg = C.level(self.level_index)

        if h.state == Hook.SWING:
            h.update_swing(dt, cfg["swing"])
            h.claw = min(1.0, h.claw + dt * 3.0)
            return

        if h.state == Hook.SHOOT:
            h.length += cfg["shoot"] * dt
            tip = h.tip()
            hit = None
            best = 1e9
            for it in self.items:
                if not it.alive:
                    continue
                d = math.hypot(tip[0] - it.x, tip[1] - it.y)
                if d <= it.r + C.HOOK_R and d < best:
                    hit, best = it, d
            if hit is not None:
                hit.grabbed = True
                hit.pop = 1.0
                h.grabbed = hit
                h.state = Hook.RETRACT
                h.claw = 0.0
                h.wobble = 0.0
                self.particles += burst(tip[0], tip[1], "#ffe9a8", 8, speed=140, life=0.4)
                self.res.play("hook_hit")
            elif h.out_of_bounds(tip) or h.length > h.max_reach():
                h.state = Hook.RETRACT
                h.claw = 1.0
            return

        # ---- 收线
        speed = h.retract_speed(self.potion_timer > 0)
        h.length -= speed * dt
        h.wobble += dt * 14.0
        if h.grabbed is not None:
            tip = h.tip(wobble=1.0)
            h.grabbed.x, h.grabbed.y = tip[0], tip[1] + h.grabbed.r * 0.35
        if h.length <= C.MIN_LEN:
            h.length = float(C.MIN_LEN)
            self._land()

    def _land(self):
        h = self.hook
        item = h.grabbed
        h.bomb_boost = False
        if item is not None and item.alive:
            item.alive = False
            if item.prop:
                self.inventory[item.prop] = self.inventory.get(item.prop, 0) + 1
                self.res.play("powerup")
                self._float(C.PIVOT[0], C.GROUND_Y - 4, item.burst_score_text(), C.COLORS["potion"])
                self.particles += burst(item.x, item.y, "#7fe8ff", 14, speed=170)
            else:
                self.score += item.value
                label = item.label
                match label:
                    case "帅案":
                        self.res.play("shuaian")
                    case "笑面虎":
                        self.res.play("xiaomianhu")
                    case "乌角鲨":
                        self.res.play("wujiaosha")
                    case "龙":
                        self.res.play("dragon")
                    case "仁之剑":
                        self.res.play("renzhijian")
                    case "义之剑":
                        self.res.play("yizhijian")
                    case "四轮车":
                        self.res.play("silunche")
                    case _:
                        self.res.play("collect")
                self._float(C.PIVOT[0], C.GROUND_Y - 4, item.burst_score_text(),
                            C.COLORS["gold"], size=22)
                self.particles += burst(item.x, item.y, C.COLORS["gold"], 12, speed=170)
        h.grabbed = None
        h.state = Hook.SWING
        h.claw = 1.0

    def _level_clear(self, bonus=True):
        """过关。bonus=True 表示“提前挖空矿场”，此时剩余时间折算奖励。"""
        self.clear_reason = "clear" if bonus else "timeup"
        self.level_bonus = 0
        if bonus:
            self.level_bonus = int(max(0.0, self.time_left)) * C.TIME_BONUS_PER_SEC
            self.score += self.level_bonus
        # 通过最后一个手工关卡 → 记录“已通关 3 个简单关卡”，接下来是随机无尽
        if not C.is_random_level(self.level_index) and self.level_index + 1 >= len(C.LEVELS):
            self.fixed_cleared = True
        self.overlay_timer = 2.6
        self.state = "level_clear"
        self.hook.reset()
        self.res.play("level_up")

    # ================================================================== 特效
    def _update_effects(self, dt):
        if self.particles:
            self.particles = [p for p in self.particles if p.update(dt)]
        if self.texts:
            self.texts = [t for t in self.texts if t.update(dt)]
        if self.toast_timer > 0:
            self.toast_timer -= dt
        if self.shake > 0:
            self.shake = max(0.0, self.shake - dt)
        if self.flash > 0:
            self.flash = max(0.0, self.flash - dt)
        if self.shop_msg_timer > 0:
            self.shop_msg_timer -= dt
        for it in self.items:
            if it.pop > 0:
                it.pop = max(0.0, it.pop - dt * 3.0)

    def _float(self, x, y, text, color, size=18):
        self.texts.append(FloatingText(x, y, text, color, size=size))

    def _toast(self, text, seconds=2.0):
        self.toast = text
        self.toast_timer = seconds

    # ================================================================== 渲染
    def _draw_static_background(self):
        """背景只画一次（贴图 background.png 存在就用贴图）。"""
        cv = self.p
        img = self.res.image("background", self.p.size(C.WIDTH, C.HEIGHT))
        if img is not None:
            cv.create_image(0, 0, image=img, anchor="nw", tags="bg")
            cv.create_line(0, C.GROUND_Y, C.WIDTH, C.GROUND_Y, fill=C.COLORS["grass"], width=3, tags="bg")
            return

        # ---- 矢量兜底：天空渐变 + 星星 + 泥土渐变 + 碎石
        bands = 26
        for i in range(bands):
            t = i / float(bands - 1)
            color = _mix(C.COLORS["sky_top"], C.COLORS["sky_bottom"], t)
            y0 = C.GROUND_Y * i / bands
            y1 = C.GROUND_Y * (i + 1) / bands
            cv.create_rectangle(0, y0, C.WIDTH, y1, fill=color, outline="", tags="bg")
        rnd = random.Random(20240607)
        for _ in range(90):
            x, y = rnd.uniform(0, C.WIDTH), rnd.uniform(0, C.GROUND_Y - 30)
            s = rnd.choice((1, 1, 2))
            cv.create_oval(x, y, x + s, y + s, fill="#cdd9ff", outline="", tags="bg")
        cv.create_rectangle(0, C.GROUND_Y, C.WIDTH, C.GROUND_Y + 6,
                            fill=C.COLORS["grass"], outline="", tags="bg")
        depth = C.HEIGHT - C.GROUND_Y
        for i in range(20):
            t = i / 19.0
            color = _mix(C.COLORS["dirt_top"], C.COLORS["dirt_bottom"], t)
            y0 = C.GROUND_Y + 6 + depth * i / 20.0
            y1 = C.GROUND_Y + 6 + depth * (i + 1) / 20.0
            cv.create_rectangle(0, y0, C.WIDTH, y1, fill=color, outline="", tags="bg")
        for _ in range(320):
            x, y = rnd.uniform(0, C.WIDTH), rnd.uniform(C.GROUND_Y + 20, C.HEIGHT)
            s = rnd.uniform(1.5, 4.0)
            cv.create_oval(x, y, x + s, y + s, fill=_mix(C.COLORS["dirt_top"], C.COLORS["dirt_bottom"],
                                                         rnd.random()), outline="", tags="bg")

    def render(self):
        self.canvas.delete("dyn")

        if self.state == "menu":
            self._render_world()
            self._render_menu()
        elif self.state == "shop":
            self._render_shop()           # 店内是独立的一整屏场景，不画矿场和 HUD
        else:
            self._render_world()
            self._render_hud()
            if self.state == "paused":
                self._render_pause()
            elif self.state == "level_clear":
                self._render_level_clear()
            elif self.state == "game_over":
                self._render_end()

        if self.toast_timer > 0 and self.toast and self.state != "shop":
            self._text(C.WIDTH / 2, C.HEIGHT - 104, self.toast, 15, C.COLORS["gold"], bold=True)
        if self.shake > 0:
            d = 4.0 * self.shake * self.scale
            self.canvas.move("dyn", random.uniform(-d, d), random.uniform(-d, d))
        if self.flash > 0:
            self.p.create_rectangle(0, 0, C.WIDTH, C.HEIGHT, fill="#ffe6b0",
                                    outline="", stipple="gray25", tags="dyn")

    # ------------------------------------------------------------ 世界
    def _render_world(self):
        for it in self.items:
            if it.alive:
                self._draw_item(it)
        self._draw_hook()
        self._draw_miner()
        for p in self.particles:
            r = p.radius
            self.p.create_oval(p.x - r, p.y - r, p.x + r, p.y + r,
                                    fill=p.color, outline="", tags="dyn")
        for t in self.texts:
            fading = t.life < 0.35
            self._text(t.x, t.y, t.text,
                       t.size if not fading else max(11, int(t.size * 0.75)),
                       t.color if not fading else C.COLORS["text_dim"], bold=True)

    def _draw_miner(self):
        # 矿工站在地表上，双手在身下握绳 —— 绳子的起点 (PIVOT) 就在他下面
        size = 84
        img = self.res.image("miner", self.p.size(size, size))
        if img is not None:
            self.p.create_image(C.PIVOT[0], C.GROUND_Y - 30, image=img, tags="dyn")
            return
        # ---- 没有贴图时的矢量兜底（同一个站位，约 0.68 倍比例）
        x, y = C.PIVOT[0], C.GROUND_Y - 30
        k = size / 124.0
        cv = self.p
        def o(dx, dy):
            return x + dx * k, y + dy * k
        cv.create_line(*o(-16, 96), *o(-10, 40), fill="#2f3b57", width=6, tags="dyn")       # 腿
        cv.create_line(*o(16, 96), *o(10, 40), fill="#2f3b57", width=6, tags="dyn")
        cv.create_rectangle(*o(-22, 6), *o(22, 48), fill="#3d6ea8", outline="#22375a", width=2, tags="dyn")
        cv.create_line(*o(-20, 12), *o(-13, 48), fill="#e0b183", width=7, tags="dyn")        # 双臂向下
        cv.create_line(*o(20, 12), *o(13, 48), fill="#e0b183", width=7, tags="dyn")
        cv.create_oval(*o(-18, -26), *o(18, 14), fill="#f0c39a", outline="#b98a5e", width=2, tags="dyn")
        cv.create_oval(*o(-18, 44), *o(-8, 54), fill="#f0c39a", outline="#b98a5e", width=2, tags="dyn")   # 手
        cv.create_oval(*o(8, 44), *o(18, 54), fill="#f0c39a", outline="#b98a5e", width=2, tags="dyn")
        cv.create_arc(*o(-26, -50), *o(26, -18), start=0, extent=180,
                      fill="#ffd964", outline="#b8860b", width=2, tags="dyn")               # 安全帽
        cv.create_rectangle(*o(-24, -30), *o(24, -20), fill="#ffcf49", outline="#b8860b",
                            width=2, tags="dyn")                                            # 帽檐
        cv.create_oval(*o(-12, -14), *o(-5, -7), fill="#2b2b2b", outline="", tags="dyn")    # 眼
        cv.create_oval(*o(5, -14), *o(12, -7), fill="#2b2b2b", outline="", tags="dyn")
        cv.create_line(*o(-10, 2), *o(10, 2), fill="#7a4a22", width=3, tags="dyn")          # 胡子

    def _draw_hook(self):
        h = self.hook
        cv = self.p
        tip = h.tip(wobble=1.0 if h.grabbed is not None else 0.0)
        color = C.COLORS["hook"]
        if h.bomb_boost:
            color = C.COLORS["danger"]
        elif self.potion_timer > 0:
            color = C.COLORS["potion"]

        cv.create_line(C.PIVOT[0], C.PIVOT[1], tip[0], tip[1],
                       fill=C.COLORS["rope"], width=2, tags="dyn")
        ux, uy = h.unit()
        prong = C.HOOK_R * 2.8
        for side in (-1, 1):
            spread = side * (0.12 + 0.42 * h.claw)
            ca, sa = math.cos(spread), math.sin(spread)
            px, py = ux * ca - uy * sa, ux * sa + uy * ca
            cv.create_line(tip[0], tip[1], tip[0] + px * prong, tip[1] + py * prong,
                           fill=color, width=4, capstyle="round", tags="dyn")
            # 爪尖再往内勾一点
            cv.create_line(tip[0] + px * prong * 0.62, tip[1] + py * prong * 0.62,
                           tip[0] + px * prong * 0.95 - ux * 5, tip[1] + py * prong * 0.95 - uy * 5,
                           fill=color, width=3, capstyle="round", tags="dyn")
        cv.create_oval(tip[0] - 4, tip[1] - 4, tip[0] + 4, tip[1] + 4,
                       fill=color, outline="", tags="dyn")

        it = h.grabbed
        if it is not None:      # 抓取动画：脉冲光环
            pulse = 5.0 + 3.0 * math.sin(self.anim * 14.0)
            self.p.create_oval(tip[0] - it.r - pulse, tip[1] - it.r - pulse,
                                    tip[0] + it.r + pulse, tip[1] + it.r + pulse,
                                    outline=C.COLORS["gold"], width=2, tags="dyn")

    # ------------------------------------------------------------ 物品绘制
    def _draw_item(self, it):
        img = self.res.image(it.key, self.p.size(it.sprite_size, it.sprite_size))
        if img is not None:
            self.p.create_image(it.x, it.y, image=img, tags="dyn")
            return
        self._draw_item_vector(it)

    def _draw_item_vector(self, it):
        cv = self.p
        x, y, r = it.x, it.y, it.r * (1.0 + 0.18 * it.pop)
        key = it.key

        if key.startswith("gold"):
            pts = []
            n = 9
            for i in range(n):
                ang = math.tau * i / n
                rad = r * (0.84 + 0.16 * math.sin(i * 2.3 + it.phase))
                pts += [x + math.cos(ang) * rad, y + math.sin(ang) * rad]
            cv.create_polygon(pts, smooth=True, fill="#f2c14e", outline="#9c6b12", width=2, tags="dyn")
            cv.create_oval(x - r * 0.5, y - r * 0.6, x - r * 0.05, y - r * 0.15,
                           fill="#ffeaa8", outline="", tags="dyn")
            cv.create_oval(x + r * 0.1, y + r * 0.2, x + r * 0.45, y + r * 0.5,
                           fill="#d9a02f", outline="", tags="dyn")

        elif key.startswith("rock"):
            pts = []
            n = 8
            for i in range(n):
                ang = math.tau * i / n
                rad = r * (0.86 + 0.14 * math.sin(i * 3.1 + it.phase))
                pts += [x + math.cos(ang) * rad, y + math.sin(ang) * rad]
            cv.create_polygon(pts, smooth=False, fill="#8a8f98", outline="#565c66", width=2, tags="dyn")
            cv.create_line(x - r * 0.4, y - r * 0.3, x + r * 0.1, y + r * 0.35,
                           fill="#6d737d", width=2, tags="dyn")
            cv.create_oval(x + r * 0.15, y - r * 0.5, x + r * 0.45, y - r * 0.2,
                           fill="#a4aab4", outline="", tags="dyn")

        elif key == "diamond":
            top = y - r
            pts = [x, top, x + r, y - r * 0.25, x + r * 0.6, y + r * 0.8,
                   x - r * 0.6, y + r * 0.8, x - r, y - r * 0.25]
            cv.create_polygon(pts, fill="#a9f0ff", outline="#2aa8c8", width=2, tags="dyn")
            cv.create_line(x - r, y - r * 0.25, x + r, y - r * 0.25, fill="#e8feff", width=1, tags="dyn")
            cv.create_line(x, top, x, y + r * 0.8, fill="#e8feff", width=1, tags="dyn")

        elif key in ("money_bag", "mystery_bag"):
            body = "#b98149" if key == "money_bag" else "#8b5cf6"
            edge = "#6f4423" if key == "money_bag" else "#5b21b6"
            cv.create_oval(x - r, y - r * 0.55, x + r, y + r, fill=body, outline=edge, width=2, tags="dyn")
            cv.create_rectangle(x - r * 0.35, y - r, x + r * 0.35, y - r * 0.35,
                                fill=body, outline=edge, width=2, tags="dyn")
            cv.create_line(x - r * 0.4, y - r * 0.6, x + r * 0.4, y - r * 0.6, fill=edge, width=2, tags="dyn")
            self._text(x, y + r * 0.15, "$" if key == "money_bag" else "?",
                       max(9, int(r * 1.1)), "#fff3d0", bold=True)

        elif key == "bomb_pickup":
            cv.create_oval(x - r, y - r, x + r, y + r, fill="#22262e", outline="#0d0f14", width=2, tags="dyn")
            cv.create_oval(x - r * 0.55, y - r * 0.6, x - r * 0.15, y - r * 0.2,
                           fill="#5b6270", outline="", tags="dyn")
            cv.create_line(x + r * 0.35, y - r * 0.75, x + r * 0.9, y - r * 1.4,
                           fill="#c98b3f", width=3, tags="dyn")
            cv.create_oval(x + r * 0.75, y - r * 1.6, x + r * 1.15, y - r * 1.2,
                           fill="#ffb347", outline="", tags="dyn")

        elif key == "potion_pickup":
            cv.create_rectangle(x - r * 0.34, y - r, x + r * 0.34, y - r * 0.6,
                                fill="#8a5a2b", outline="#5c3a1a", width=2, tags="dyn")
            cv.create_rectangle(x - r * 0.6, y - r * 0.65, x + r * 0.6, y + r,
                                fill="#dff0ff", outline="#7fb6d9", width=2, tags="dyn")
            cv.create_rectangle(x - r * 0.46, y - r * 0.1, x + r * 0.46, y + r * 0.85,
                                fill=C.COLORS["potion"], outline="", tags="dyn")
            cv.create_line(x - r * 0.45, y - r * 0.4, x - r * 0.45, y + r * 0.5,
                           fill="#ffffff", width=2, tags="dyn")

        else:
            # 通用兜底：config.ITEMS 里自己加的物品（没有专用画法 / 没有 PNG）也能看见。
            # 颜色由物品名算出来，所以同一个物品每次都是同一种颜色。
            seed = sum((i + 7) * ord(ch) for i, ch in enumerate(key))
            base = _hsv_hex((seed * 37) % 360, 0.60, 0.95)
            dark = _hsv_hex((seed * 37) % 360, 0.80, 0.58)
            pts = []
            for i in range(6):
                ang = math.tau * i / 6 + it.phase * 0.2
                rad = r * (0.95 if i % 2 == 0 else 0.70)
                pts += [x + math.cos(ang) * rad, y + math.sin(ang) * rad]
            cv.create_polygon(pts, fill=base, outline=dark, width=2, tags="dyn")
            cv.create_oval(x - r * 0.42, y - r * 0.58, x - r * 0.05, y - r * 0.18,
                           fill="#ffffff", outline="", tags="dyn")
            if r >= 14:                       # 写个首字，方便认出这是什么
                self._text(x, y + r * 0.34, it.label[:1], max(9, int(r * 0.9)),
                           "#2b2000", bold=True)

    # ------------------------------------------------------------ HUD
    def _render_hud(self):
        cv = self.p
        cfg = C.level(self.level_index)
        cv.create_rectangle(0, 0, C.WIDTH, 112, fill="#060c1a",
                            outline="", tags="dyn")
        cv.create_line(0, 112, C.WIDTH, 112, fill="#2b3d63", width=2, tags="dyn")


        head = "关卡 %d" % (self.level_index + 1)
        self._text(22, 26, head, 15, C.COLORS["text"], anchor="w", bold=True)

        # 分数 + 目标进度条
        self._text(22, 56, "分数 %d / 目标 %d" % (self.score, self.target()),
                   14, C.COLORS["gold"], anchor="w")
        bx0, bx1, by0, by1 = 22, 320, 74, 86
        cv.create_rectangle(bx0, by0, bx1, by1, fill="#17233d", outline="#2b3d63", tags="dyn")
        start, goal = self.bar_start(), max(1, self.target() - self.bar_start())
        frac = max(0.0, min(1.0, (self.score - start) / float(goal)))
        done = self.score >= self.target()
        if frac > 0:
            cv.create_rectangle(bx0 + 1, by0 + 1, bx0 + 1 + (bx1 - bx0 - 2) * frac, by1 - 1,
                                fill=C.COLORS["ok"] if done else C.COLORS["gold"],
                                outline="", tags="dyn")
        self._text((bx0 + bx1) / 2, (by0 + by1) / 2, "%d%%" % int(frac * 100),
                   11, C.COLORS["text"], bold=True)

        # 过关状态：达到目标分后不结束，要继续挖到时间结束（或清空矿场）
        left = sum(1 for it in self.items if it.alive)
        if done:
            self._text(22, 102, "✔ 目标已达成 · 挖空矿场可提前过关（剩 %d 件）" % left,
                       12, C.COLORS["ok"], anchor="w", bold=True)
        else:
            self._text(22, 102, "时间结束时达标即过关 · 矿场剩余 %d 件" % left,
                       12, C.COLORS["text_dim"], anchor="w")

        # 倒计时
        secs = int(math.ceil(max(0.0, self.time_left)))
        urgent = secs <= 10
        blink = urgent and secs <= 5 and int(self.anim * 4) % 2 == 0
        if not blink:
            self._text(C.WIDTH / 2, 42, "%02d" % secs, 34,
                       C.COLORS["danger"] if urgent else C.COLORS["text"], bold=True)
        self._text(C.WIDTH / 2, 82, "倒计时", 12, C.COLORS["text_dim"])
        frac_t = max(0.0, min(1.0, self.time_left / self.time_total))
        cv.create_rectangle(C.WIDTH / 2 - 90, 96, C.WIDTH / 2 + 90, 103,
                            fill="#17233d", outline="", tags="dyn")
        if frac_t > 0:
            cv.create_rectangle(C.WIDTH / 2 - 90, 96, C.WIDTH / 2 - 90 + 180 * frac_t, 103,
                                fill=C.COLORS["danger"] if urgent else C.COLORS["ok"],
                                outline="", tags="dyn")

        # 道具
        inv = "[1] %s x%d    [2] %s x%d" % (C.PROPS["bomb"]["label"], self.inventory.get("bomb", 0),
                                            C.PROPS["potion"]["label"], self.inventory.get("potion", 0))
        self._text(C.WIDTH - 22, 30, "道具：" + inv, 15, C.COLORS["text"], anchor="e")
        if self.potion_timer > 0:
            self._text(C.WIDTH - 22, 62, "沛国佳酿生效中 %.1fs（收绳 x%.1f）"
                       % (self.potion_timer, C.POTION_MULT), 14, C.COLORS["potion"], anchor="e", bold=True)
        else:
            tip = ("抓到矿场里的 %s / %s 可补充道具"
                   % (C.PROPS["bomb"]["label"], C.PROPS["potion"]["label"])) if C.PROPS_IN_FIELD \
                else "道具在过关后的商店里用分数购买"
            self._text(C.WIDTH - 22, 62, tip, 12, C.COLORS["text_dim"], anchor="e")

        # 关卡提示
        if self.hint_timer > 0:
            color = C.COLORS["text"] if self.hint_timer > 0.9 else C.COLORS["text_dim"]
            cv.create_rectangle(0, C.HEIGHT - 74, C.WIDTH, C.HEIGHT - 40,
                                fill="#0a1428", outline="#3d5a8f", tags="dyn")
            self._text(C.WIDTH / 2, C.HEIGHT - 57, "提示：" + cfg["hint"], 15, color, bold=True)

        # 底部操作条
        self._text(C.WIDTH / 2, C.HEIGHT - 14,
                   "空格 发射　·　1 炸弹　·　2 沛国佳酿　·　P 暂停　·　M 静音　·　Esc 退出",
                   12, "#e6d7b0")

    # ------------------------------------------------------------ 各界面
    def _render_menu(self):
        cv = self.p
        self._dim()
        self._panel(C.WIDTH / 2 - 330, 70, C.WIDTH / 2 + 330, C.HEIGHT - 60)

        self._text(C.WIDTH / 2, 118, "新 三 国 黄 金 矿 工", 52, C.COLORS["gold"], bold=True)
        #self._text(C.WIDTH / 2, 162, "", 14, C.COLORS["text_dim"])

        lines = [
            "空格：发射钩子（抓到越重的东西收线越慢）",
            "1：炸弹 —— 炸掉已抓住的东西，空钩极速返回",
            "2：沛国佳酿 —— 12 秒内收绳速度翻倍",
            "3 个简单关卡 + 之后随机生成的无尽矿脉",
            "道具只在每关结束后的商店里用分数购买，会一直留到后面的关卡",
            "达标不会立刻结束：挖到时间结束，或提前挖空矿场拿时间奖励",
        ]
        for i, line in enumerate(lines):
            self._text(C.WIDTH / 2, 208 + i * 27, line, 15, C.COLORS["text"])

        if int(self.anim * 2) % 2 == 0:
            self._text(C.WIDTH / 2, 384, "按 空格 / 回车 开始游戏", 20, C.COLORS["ok"], bold=True)
        else:
            self._text(C.WIDTH / 2, 384, "按 空格 / 回车 开始游戏", 20, "#2f6b48", bold=True)

        self._text(C.WIDTH / 2, 420, "历史最高分：%d" % self.best_score, 16, C.COLORS["gold"])

        # 排行榜
        self._text(C.WIDTH / 2, 456, "排 行 榜", 16, C.COLORS["text"], bold=True)
        if not self.scores:
            self._text(C.WIDTH / 2, 486, "还没有成绩，来创造第一条记录吧", 14, C.COLORS["text_dim"])
        else:
            for i, row in enumerate(self.scores[:5]):
                self._text(C.WIDTH / 2 - 260, 482 + i * 22,
                           "%d. %-10s %6d 分" % (i + 1, row.get("name", "?"),
                                                           int(row.get("score", 0))),
                           14, C.COLORS["text"] if i else C.COLORS["gold"], anchor="w")

    def _render_pause(self):
        self._dim()
        self._panel(C.WIDTH / 2 - 220, 250, C.WIDTH / 2 + 220, 390)
        self._text(C.WIDTH / 2, 300, "已 暂 停", 34, C.COLORS["text"], bold=True)
        self._text(C.WIDTH / 2, 348, "按 P 继续　·　Esc 退出", 16, C.COLORS["text_dim"])

    # ------------------------------------------------------------ 经典商店界面
    def _shop_geometry(self):
        """商店里所有矩形（逻辑坐标）。渲染、命中检测、立绘全都读这里。

        想让店长立绘更大：改 config.SHOP_KEEPER_FRAME（内画面会自动变大）；
        想让商品卡更多：往 config.SHOP_ORDER 里加名字，卡片会自动平分右侧宽度。
        """
        fx0, fy0, fx1, fy1 = C.SHOP_KEEPER_FRAME
        pad, cap = C.SHOP_KEEPER_PAD, C.SHOP_CAPTION_H
        g = {
            "sign":    (140, 16, 446, 82),
            "frame":   (fx0, fy0, fx1, fy1),
            # 立绘画面区域（相框内缩 + 底部留出台词条）
            "image":   (fx0 + pad, fy0 + pad, fx1 - pad, fy1 - pad - cap),
            "caption": (fx0 + pad, fy1 - pad - cap, fx1 - pad, fy1 - pad),
            "counter": (40, 464, 920, 508),
            "bottom":  (40, 512, 920, 600),
            "money":   (88, 556),
            "next":    (700, 520, 900, 590),
        }
        # 商品卡：右侧列自动平分
        kinds = list(C.SHOP_ORDER)
        n = max(1, len(kinds))
        x0, x1, gap = 570, 944, 14
        w = (x1 - x0 - gap * (n - 1)) / float(n)
        for i, kind in enumerate(kinds):
            cx0 = x0 + i * (w + gap)
            g["card_" + kind] = (cx0, 104, cx0 + w, 434)
        return g

    def _shop_layout(self):
        """商店里所有可点击区域（逻辑坐标），渲染和命中检测共用一份。"""
        g = self._shop_geometry()
        rects = {"keeper": g["frame"], "next": g["next"]}
        for kind in C.SHOP_ORDER:
            rects[kind] = g["card_" + kind]
        return rects

    def _shop_hit(self, x, y):
        for key, (x0, y0, x1, y1) in self._shop_layout().items():
            if x0 <= x <= x1 and y0 <= y <= y1:
                return key
        return None

    def _draw_keeper(self, cx, expr):
        """柜台后的店长立绘。返回 True 表示用的是贴图，False 表示用了矢量兜底。

        贴图优先（config.SHOP_KEEPER）：
            平时 / 买到东西 → gongxidiekeyichengdile.png
            没买东西就走   → jingranbuxu.png
        贴图先按 config.SHOP_KEEPER_ZOOM 放大（默认 2 倍特写），再**居中裁切**到
        相框内画面，所以人物会填满相框、不会拉变形；两张图都没有时才退回矢量店长。
        """
        cv = self.p
        g = self._shop_geometry()
        frame, inner = g["frame"], g["image"]
        caption = g["caption"]
        iw, ih = inner[2] - inner[0], inner[3] - inner[1]
        dw, dh = self.p.size(iw, ih)          # 换成画布真实像素（高 DPI 下会翻倍）
        icx, icy = (inner[0] + inner[2]) / 2, (inner[1] + inner[3]) / 2

        img = None
        for cand in (C.SHOP_KEEPER.get(expr), "shop_" + expr,
                     C.SHOP_KEEPER.get("neutral"), "shop_neutral"):
            img = self.res.image_fit(cand, dw, dh, C.SHOP_KEEPER_ZOOM)
            if img is not None:
                break
        if img is not None:
            glow = self.shop_state == "browse" and self.shop_flash_timer > 0
            cv.create_rectangle(*frame, fill="#3a2411",
                                outline=C.COLORS["gold"] if glow else "#8a5a2b",
                                width=8 if glow else 5, tags="dyn")
            cv.create_rectangle(*inner, fill="#120c05", outline="#5c3a1a", width=2, tags="dyn")
            self.p.create_image(icx, icy, image=img, tags="dyn")
            # 相框内的台词条（省地方，也让“店长在说话”更明显）
            cv.create_rectangle(*caption, fill="#2a1b0c", outline="#5c3a1a", width=2, tags="dyn")
            lines = self._wrap("店长：" + self.shop_line, 30)[:2]
            for i, line in enumerate(lines):
                self._text(icx, caption[1] + 12 + i * 18, line, 14, "#f4ecd8", bold=True)
            if glow:                              # 买到东西：相框发光 + 星星
                for dx, dy in ((-0.42, -0.36), (0.44, -0.26), (0.10, 0.30)):
                    sx = icx + dx * iw
                    sy = icy + dy * ih
                    cv.create_line(sx - 8, sy, sx + 8, sy, fill="#ffe58a", width=3, tags="dyn")
                    cv.create_line(sx, sy - 8, sx, sy + 8, fill="#ffe58a", width=3, tags="dyn")
            return True

        self._draw_keeper_vector(cx, expr)
        return False

    def _draw_keeper_vector(self, cx, expr):
        """没有立绘贴图时的矢量老店长（三种表情）。"""
        cv = self.p
        hy, r = 258, 50                      # 头部中心 / 半径
        skin, skin_dark = "#f0c39a", "#c08f63"
        hair, vest, shirt = "#ececec", "#6b3f2a", "#ded7c8"
        beard = "#f4f2ec"

        # 身体（马甲 + 衬衫领口）
        cv.create_polygon(cx - 80, 470, cx - 62, 344, cx + 62, 344, cx + 80, 470,
                          fill=vest, outline="#3d2416", width=3, tags="dyn")
        cv.create_polygon(cx - 26, 344, cx, 402, cx + 26, 344,
                          fill=shirt, outline="#b9b0a0", width=2, tags="dyn")
        # 双臂搭在柜台上，手露在柜台外沿
        for s in (-1, 1):
            cv.create_line(cx + s * 56, 380, cx + s * 116, 432,
                           fill=vest, width=26, capstyle="round", tags="dyn")
            cv.create_oval(cx + s * 116 - 17, 432 - 17, cx + s * 116 + 17, 432 + 17,
                           fill=skin, outline=skin_dark, width=2, tags="dyn")
        # 头 + 耳朵 + 两鬓白发
        cv.create_oval(cx - r, hy - r, cx + r, hy + r, fill=skin, outline=skin_dark, width=2, tags="dyn")
        for s in (-1, 1):
            cv.create_oval(cx + s * r - 9, hy - 9, cx + s * r + 9, hy + 9,
                           fill=skin, outline=skin_dark, width=2, tags="dyn")
            cv.create_oval(cx + s * 44 - 12, hy - 36, cx + s * 44 + 12, hy + 8,
                           fill=hair, outline="", tags="dyn")
        # 大白胡子
        cv.create_oval(cx - 48, hy + 8, cx + 48, hy + 100, fill=beard, outline="#c9c4b8", width=2, tags="dyn")
        cv.create_oval(cx - 30, hy + 4, cx + 30, hy + 30, fill=skin, outline="", tags="dyn")
        # 鼻子
        cv.create_oval(cx - 13, hy + 4, cx + 13, hy + 30, fill=skin_dark, outline="", tags="dyn")

        ex_l, ex_r, ey = cx - 21, cx + 21, hy - 10
        if expr == "happy":
            # 眉毛上扬 + 弯眼睛 + 大笑
            cv.create_arc(ex_l - 20, hy - 48, ex_l + 20, hy - 18, start=20, extent=140,
                          style="arc", outline="#5a3a22", width=5, tags="dyn")
            cv.create_arc(ex_r - 20, hy - 48, ex_r + 20, hy - 18, start=20, extent=140,
                          style="arc", outline="#5a3a22", width=5, tags="dyn")
            for ex in (ex_l, ex_r):
                cv.create_arc(ex - 17, ey - 12, ex + 17, ey + 14, start=0, extent=180,
                              style="arc", outline="#2b2b2b", width=5, tags="dyn")
            cv.create_arc(cx - 30, hy + 24, cx + 30, hy + 76, start=180, extent=180,
                          style="chord", fill="#5d1f1f", outline="#3a1010", width=2, tags="dyn")
            cv.create_oval(cx - 40, hy + 16, cx - 20, hy + 30, fill="#f0a0a0", outline="", tags="dyn")
            cv.create_oval(cx + 20, hy + 16, cx + 40, hy + 30, fill="#f0a0a0", outline="", tags="dyn")
            for dx, dy in ((-70, -70), (74, -60)):        # 小星星
                cv.create_line(cx + dx - 6, hy + dy, cx + dx + 6, hy + dy, fill="#ffe58a", width=3, tags="dyn")
                cv.create_line(cx + dx, hy + dy - 6, cx + dx, hy + dy + 6, fill="#ffe58a", width=3, tags="dyn")
        elif expr == "sad":
            # 眉毛内侧上挑（苦恼）+ 眼睛下垂 + 嘴角朝下 + 汗滴
            cv.create_line(ex_l - 18, hy - 32, ex_l + 16, hy - 46, fill="#5a3a22", width=5, tags="dyn")
            cv.create_line(ex_r - 16, hy - 46, ex_r + 18, hy - 32, fill="#5a3a22", width=5, tags="dyn")
            for ex in (ex_l, ex_r):
                cv.create_oval(ex - 8, ey - 5, ex + 8, ey + 11, fill="#2b2b2b", outline="", tags="dyn")
                cv.create_line(ex - 13, ey - 6, ex + 13, ey - 6, fill=skin_dark, width=4, tags="dyn")
            cv.create_arc(cx - 28, hy + 44, cx + 28, hy + 86, start=0, extent=180,
                          style="arc", outline="#4a2a12", width=5, tags="dyn")
            cv.create_polygon(cx - 82, hy - 30, cx - 74, hy - 8, cx - 90, hy - 8,
                              fill="#7fd4ff", outline="#3aa8d8", width=2, tags="dyn")
        else:
            # 平静：平眉 + 圆眼睛 + 一点点微笑
            cv.create_line(ex_l - 18, hy - 32, ex_l + 18, hy - 32, fill="#5a3a22", width=5, tags="dyn")
            cv.create_line(ex_r - 18, hy - 32, ex_r + 18, hy - 32, fill="#5a3a22", width=5, tags="dyn")
            for ex in (ex_l, ex_r):
                cv.create_oval(ex - 8, ey - 8, ex + 8, ey + 8, fill="#2b2b2b", outline="", tags="dyn")
                cv.create_oval(ex - 3, ey - 5, ex + 1, ey - 1, fill="#ffffff", outline="", tags="dyn")
            cv.create_arc(cx - 22, hy + 40, cx + 22, hy + 70, start=200, extent=140,
                          style="arc", outline="#4a2a12", width=4, tags="dyn")

    def _render_shop(self):
        """经典《黄金矿工》风格的商店：木板小店 + 柜台 + 店长立绘 + 货架商品 + 价格牌。"""
        cv = self.p
        g = self._shop_geometry()
        nxt = self.level_index + 1
        cfg = C.level(self.level_index)
        browse = self.shop_state == "browse"
        counter = g["counter"]
        bottom = g["bottom"]

        # ---- 店内背景（墙 + 地板）
        cv.create_rectangle(0, 0, C.WIDTH, counter[1], fill="#33220f", outline="", tags="dyn")
        for x in range(0, C.WIDTH + 1, 64):
            cv.create_line(x, 0, x, counter[1], fill="#2a1b0c", width=2, tags="dyn")
        cv.create_rectangle(0, counter[1], C.WIDTH, C.HEIGHT, fill="#241505", outline="", tags="dyn")
        for y in range(counter[1], C.HEIGHT, 34):
            cv.create_line(0, y, C.WIDTH, y, fill="#1c1004", width=2, tags="dyn")

        # ---- 招牌
        sx0, sy0, sx1, sy1 = g["sign"]
        cv.create_rectangle(sx0, sy0, sx1, sy1, fill="#4a2f16", outline="#8a5a2b", width=4, tags="dyn")
        self._text((sx0 + sx1) / 2, (sy0 + sy1) / 2, "矿 工 商 店", 30, C.COLORS["gold"], bold=True)

        # ---- 店长：有立绘就用相框（台词在相框内的台词条里）；
        #      没有立绘时退回矢量店长，台词改用头顶的对话气泡显示
        portrait = self._draw_keeper((g["frame"][0] + g["frame"][2]) / 2, self.shop_expr)
        if not portrait:
            bx0, by0, bx1, by1 = 150, 92, 470, 196
            cv.create_polygon(268, by1, 292, by1 + 24, 316, by1,
                              fill="#f4ecd8", outline="#8a5a2b", tags="dyn")
            cv.create_rectangle(bx0, by0, bx1, by1, fill="#f4ecd8",
                                outline="#8a5a2b", width=3, tags="dyn")
            lines = self._wrap(self.shop_line, 16)[:3]
            ty = (by0 + by1) / 2 - (len(lines) - 1) * 12      # 台词在气泡里居中
            for i, line in enumerate(lines):
                self._text((bx0 + bx1) / 2, ty + i * 24, line, 14, "#3a2411", bold=True)

        # ---- 柜台
        cv.create_rectangle(counter[0], counter[1], counter[2], counter[1] + 24,
                            fill="#7a4f26", outline="#3d2416", width=3, tags="dyn")
        cv.create_rectangle(counter[0], counter[1] + 24, counter[2], counter[3],
                            fill="#4a2f16", outline="#3d2416", width=3, tags="dyn")
        for x in range(counter[0] + 30, counter[2], 46):
            cv.create_line(x, counter[1] + 26, x, counter[3] - 2, fill="#3a2411", width=2, tags="dyn")
        cv.create_line(counter[0], counter[1], counter[2], counter[1], fill="#a9713a", width=3, tags="dyn")

        # ---- 货架上的商品（可点击，鼠标悬停高亮）
        for kind in C.SHOP_ORDER:
            x0, y0, x1, y1 = g["card_" + kind]
            cx = (x0 + x1) / 2
            price = self.shop_price(kind)
            afford = self.score >= price
            hover = browse and self.shop_hover == kind
            cv.create_rectangle(x0, y0, x1, y1, fill="#1d1207",
                                outline=C.COLORS["gold"] if hover else "#7a4f26",
                                width=5 if hover else 3, tags="dyn")
            cv.create_rectangle(x0 + 7, y0 + 7, x1 - 7, y1 - 7, fill="#150d05",
                                outline="#3d2a14", width=2, tags="dyn")
            # 快捷键角标
            cv.create_rectangle(x0 + 12, y0 + 12, x0 + 54, y0 + 46, fill="#3a2411",
                                outline="#7a4f26", width=2, tags="dyn")
            self._text(x0 + 33, y0 + 29, C.PROPS[kind]["hotkey"], 17, C.COLORS["gold"], bold=True)
            # 图标
            icon_y = y0 + 96
            img = self.res.image(C.prop_sprite(kind), self.p.size(64, 64))
            if img is not None:
                self.p.create_image(cx, icon_y, image=img, tags="dyn")
            else:
                self._draw_item_vector(Item(C.prop_sprite(kind), cx, icon_y + 6))
            self._text(cx, y0 + 152, C.PROPS[kind]["label"], 20, C.COLORS["text"], bold=True)
            # 价签
            tag_w = 62
            cv.create_polygon(cx - tag_w, y0 + 176, cx + tag_w - 14, y0 + 176,
                              cx + tag_w, y0 + 194, cx + tag_w - 14, y0 + 212,
                              cx - tag_w, y0 + 212,
                              fill="#f4ecd8", outline="#8a5a2b", width=2, tags="dyn")
            cv.create_oval(cx - tag_w + 11, y0 + 185, cx - tag_w + 21, y0 + 195,
                           fill="#c9c4b8", outline="", tags="dyn")
            self._text(cx + 5, y0 + 194, "%d 分" % price, 16,
                       "#7a2d12" if afford else "#a03030", bold=True)
            self._text(cx, y0 + 232, "已有 x%d" % self.inventory.get(kind, 0), 13,
                       C.COLORS["ok"] if self.inventory.get(kind, 0) else "#8a7a5a")
            for i, line in enumerate(self._wrap(C.PROPS[kind]["tip"], 11)[:3]):
                self._text(cx, y0 + 258 + i * 20, line, 12, "#b9a888")

        # ---- 底部：钱袋 + 下一关信息 + 按钮
        cv.create_rectangle(bottom[0], bottom[1], bottom[2], bottom[3],
                            fill="#1d1207", outline="#7a4f26", width=3, tags="dyn")
        mx, my = g["money"]
        img = self.res.image("money_bag", self.p.size(46, 46))
        if img is not None:
            self.p.create_image(mx, my, image=img, tags="dyn")
        else:
            self._draw_item_vector(Item("money_bag", mx, my))
        self._text(mx + 34, my - 10, "金币（分数）", 12, "#b9a888", anchor="w")
        self._text(mx + 34, my + 16, "%d" % self.score, 30, C.COLORS["gold"], anchor="w", bold=True)

        goal = self.target()
        if self.score >= goal:
            status, color = "已达标 ✔ 可以放心花钱", C.COLORS["ok"]
        else:
            status, color = "还差 %d 分才达标，留点本钱！" % (goal - self.score), C.COLORS["danger"]
        tx = bottom[0] + 320
        self._text(tx, bottom[1] + 24, "第 %d 关（%d 秒）　目标 %d 分"
                   % (nxt, int(cfg["time"]), goal), 14, "#e6d7b0", anchor="w")
        self._text(tx, bottom[1] + 50, status, 14, color, anchor="w", bold=True)
        # 这一行平时是操作提示；买东西时显示成交信息，离开时显示过场文字
        if self.shop_msg and self.shop_msg_timer > 0:
            self._text(tx, bottom[1] + 76, self.shop_msg, 14,
                       C.COLORS["gold"] if self.shop_ok else C.COLORS["danger"],
                       anchor="w", bold=True)
        elif self.shop_state == "reaction":
            self._text(tx, bottom[1] + 76, "店长%s，正在进入第 %d 关…"
                       % ("笑了" if self.shop_expr == "happy" else "有点不高兴", nxt),
                       14, "#e6d7b0", anchor="w")
        else:
            self._text(tx, bottom[1] + 76, "鼠标点击商品即可购买 · 1/2 快捷键 · 点店长会说话",
                       12, "#b9a888", anchor="w")

        btn = g["next"]
        hover_btn = browse and self.shop_hover == "next"
        cv.create_rectangle(btn[0], btn[1], btn[2], btn[3],
                            fill="#8a5a2b" if hover_btn else "#5c3a1a",
                            outline=C.COLORS["gold"] if hover_btn else "#8a5a2b",
                            width=4 if hover_btn else 3, tags="dyn")
        label = "进入第 %d 关 →" % nxt if browse else "出发！"
        self._text((btn[0] + btn[2]) / 2, (btn[1] + btn[3]) / 2, label, 20, "#fff3d0", bold=True)

    @staticmethod
    def _wrap(text, per_line):
        """按字符数折行（中文按字数折行就够用了），并避免标点跑到行首/单独成行。"""
        if per_line <= 0:
            return [text]
        lines = [text[i:i + per_line] for i in range(0, len(text), per_line)] or [""]
        if len(lines) > 1 and len(lines[-1]) <= 1:      # 别让标点单独占一行
            lines[-2] += lines[-1]
            lines.pop()
        out = []
        for line in lines:
            if out and line and line[0] in "，。！？；：、）】》」”,.!?;:)]}":
                out[-1] += line[0]                      # 行首标点挪回上一行
                line = line[1:]
            if line:
                out.append(line)
        return out or [""]


    def _render_level_clear(self):
        self._dim()
        self._panel(C.WIDTH / 2 - 300, 226, C.WIDTH / 2 + 300, 418)
        passed_fixed = (not C.is_random_level(self.level_index)
                        and self.level_index + 1 >= len(C.LEVELS))
        if self.clear_reason == "timeup":
            title = "时间到 · 第 %d 关达标！" % (self.level_index + 1)
        else:
            title = "矿场清空 · 第 %d 关完成！" % (self.level_index + 1)
        self._text(C.WIDTH / 2, 272, title, 30, C.COLORS["ok"], bold=True)

        y = 320
        if self.level_bonus > 0:
            self._text(C.WIDTH / 2, 320, "清场时间奖励 +%d（剩余 %d 秒 × %d）"
                       % (self.level_bonus, int(self.time_left), C.TIME_BONUS_PER_SEC),
                       16, C.COLORS["gold"])
            y = 352
        self._text(C.WIDTH / 2, y, "累计总分 %d" % self.score, 18, C.COLORS["text"])

        nxt = C.level(self.level_index + 1)["short"]
        if passed_fixed:
            self._text(C.WIDTH / 2, y + 32, "3 个简单关卡全部通关！进入随机无尽模式",
                       15, C.COLORS["gold"], bold=True)
            self._text(C.WIDTH / 2, y + 60, "先进商店补给，再挑战：%s（随机生成）" % nxt,
                       14, C.COLORS["text_dim"])
        else:
            self._text(C.WIDTH / 2, y + 32, "进商店补给后进入第 %d 关：%s"
                       % (self.level_index + 2, nxt), 14, C.COLORS["text_dim"])

    def _render_end(self):
        self._dim()
        self._panel(C.WIDTH / 2 - 340, 56, C.WIDTH / 2 + 340, C.HEIGHT - 46)

        self._text(C.WIDTH / 2, 104, "游 戏 结 束", 40, C.COLORS["danger"], bold=True)
        tail = "（已通关 3 个简单关卡）" if self.fixed_cleared else ""
        self._text(C.WIDTH / 2, 150, "本局得分 %d　·　历史最高 %d　·　到达第 %d 关%s"
                   % (self.score, max(self.best_score, self.score), self.level_index + 1, tail),
                   16, C.COLORS["text"])

        self._text(C.WIDTH / 2, 196, "排 行 榜", 16, C.COLORS["text"], bold=True)
        if not self.scores:
            self._text(C.WIDTH / 2, 226, "暂无记录", 14, C.COLORS["text_dim"])
        else:
            for i, row in enumerate(self.scores[:6]):
                self._text(C.WIDTH / 2 - 290, 224 + i * 24,
                           "%d. %-10s %6d 分" % (i + 1, row.get("name", "?"),
                                                           int(row.get("score", 0))),
                           14, C.COLORS["gold"] if i == 0 else C.COLORS["text"], anchor="w")

        if self.name_saved:
            self._text(C.WIDTH / 2, C.HEIGHT - 150, "成绩已保存，按 R 再挖一局", 18,
                       C.COLORS["ok"], bold=True)
            footer = "R 重新开始　·　Esc 退出"
        else:
            cursor = "▌" if int(self.anim * 2) % 2 == 0 else " "
            self._text(C.WIDTH / 2, C.HEIGHT - 152,
                       "输入你的名字后按回车保存：%s%s" % (self.name_buffer, cursor),
                       18, C.COLORS["text"], bold=True)
            self._text(C.WIDTH / 2, C.HEIGHT - 120,
                       "（直接回车 = 天意爷；名字留空时按 R 可不保存重开）",
                       13, C.COLORS["text_dim"])
            footer = "回车 保存成绩　·　Esc 退出"

        self._text(C.WIDTH / 2, C.HEIGHT - 80, footer, 15, C.COLORS["text_dim"])

    # ------------------------------------------------------------ 绘制小工具
    def _text(self, x, y, text, size=14, color=None, anchor="center", bold=False):
        return self.p.create_text(x, y, text=text, font=self.res.font(size, bold),
                                       fill=color or C.COLORS["text"], anchor=anchor, tags="dyn")

    def _panel(self, x0, y0, x1, y1):
        self.p.create_rectangle(x0, y0, x1, y1, fill="#0b1730",
                                outline="#3d5a8f", width=2, tags="dyn")

    def _dim(self):
        """整屏压暗：用一张 1x1 半透明 PNG 放大而成（canvas 矩形本身没有 alpha）。"""
        if self._dim_img is None:
            tiny = tk.PhotoImage(data=C.DIM_PNG_B64)
            self._dim_img = tiny.zoom(C.WIDTH * self.scale, C.HEIGHT * self.scale)
            self._dim_src = tiny          # 保持引用，防止被垃圾回收
        self.p.create_image(0, 0, image=self._dim_img, anchor="nw", tags="dyn")


# ------------------------------------------------------------------ 颜色工具
def _mix(c1, c2, t):
    """两个 #rrggbb 之间线性插值。"""
    t = max(0.0, min(1.0, t))
    a = tuple(int(c1[i:i + 2], 16) for i in (1, 3, 5))
    b = tuple(int(c2[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def _hsv_hex(h, s, v):
    """HSV → #rrggbb（给自定义物品自动配色用）。"""
    h = (h % 360) / 60.0
    i = int(h) % 6
    f = h - int(h)
    p, q, t = v * (1 - s), v * (1 - s * f), v * (1 - s * (1 - f))
    r, g, b = ((v, t, p), (q, v, p), (p, v, t), (p, q, v), (t, p, v), (v, p, q))[i]
    return "#%02x%02x%02x" % (int(r * 255), int(g * 255), int(b * 255))
