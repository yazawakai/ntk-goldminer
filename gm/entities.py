# -*- coding: utf-8 -*-
"""游戏实体：物品、钩子、粒子、飘字。

这一层只负责“是什么 / 怎么动”，不碰 tkinter 画布，
所以可以单独跑单元测试，也方便以后换渲染后端（pygame / web）。
"""
from __future__ import annotations

import math
import random

from . import config as C


# ====================================================================== 物品
class Item:
    """矿场里的一个可抓取物（金块 / 石头 / 钻石 / 袋子 / 道具）。"""

    def __init__(self, key, x, y):
        spec = C.ITEMS[key]
        self.key = key
        self.x = float(x)
        self.y = float(y)
        self.r = float(spec["r"])
        self.weight = float(spec["weight"])
        self.prop = spec.get("prop")            # "bomb" / "potion" / None
        self.rock = bool(spec.get("rock"))      # 石头（炸弹可波及）
        self.label = spec["label"]
        rng = spec.get("random")
        self.value = random.randint(*rng) if rng else int(spec.get("score", 0))
        self.alive = True
        self.grabbed = False
        self.phase = random.random() * math.tau  # 形状/微动相位
        self.pop = 0.0                           # 被抓瞬间的放大动画 1 -> 0

    @property
    def sprite_size(self):
        return int(self.r * 2 + 4)

    def burst_score_text(self):
        """飘字内容。"""
        if self.prop:
            return "%s +1" % C.PROPS[self.prop]["label"]
        return "+%d" % self.value

    def __repr__(self):  # pragma: no cover
        return "<Item %s (%.0f,%.0f) v=%d>" % (self.key, self.x, self.y, self.value)


# ====================================================================== 钩子
class Hook:
    """摆动 / 发射 / 收线的钩子。

    坐标约定：theta = 0 表示垂直向下，正值向右摆。
        tip = pivot + (sin(theta), cos(theta)) * length
    """

    SWING, SHOOT, RETRACT = "swing", "shoot", "retract"

    def __init__(self):
        self.reset()

    def reset(self):
        self.theta = 0.0
        self.direction = 1
        self.length = float(C.MIN_LEN)
        self.state = self.SWING
        self.grabbed = None     # Item 或 None
        self.claw = 1.0         # 1 = 张开, 0 = 夹紧（抓取动画）
        self.bomb_boost = False # 炸弹爆破后空钩极速返回
        self.wobble = 0.0       # 绳子晃动（重物拉扯）

    # ---------------------------------------------------------- 运动
    def update_swing(self, dt, speed_deg):
        """在 [-THETA_MAX, +THETA_MAX] 之间往返摆动。"""
        self.theta += self.direction * math.radians(speed_deg) * dt
        if self.theta >= C.THETA_MAX:
            self.theta = C.THETA_MAX
            self.direction = -1
        elif self.theta <= -C.THETA_MAX:
            self.theta = -C.THETA_MAX
            self.direction = 1
        self.length = float(C.MIN_LEN)
        self.wobble = 0.0

    def tip(self, wobble=0.0):
        """钩爪位置；wobble 为绳子张力晃动（夹着重物时抖一抖）。"""
        t = self.theta + (math.sin(self.wobble) * 0.012 * wobble)
        return (C.PIVOT[0] + math.sin(t) * self.length,
                C.PIVOT[1] + math.cos(t) * self.length)

    def unit(self):
        return (math.sin(self.theta), math.cos(self.theta))

    def max_reach(self):
        return C.HEIGHT * 1.05

    def out_of_bounds(self, tip):
        x, y = tip
        return x < 6 or x > C.WIDTH - 6 or y > C.HEIGHT - 10

    def retract_speed(self, potion_active=False):
        """按被抓物品重量算收绳速度（px/s）。"""
        item = self.grabbed
        weight = item.weight if item is not None else 0.0
        speed = C.BASE_RETRACT / (1.0 + weight)
        if potion_active:
            speed *= C.POTION_MULT
        if item is None and self.bomb_boost:
            speed *= C.BOMB_RETRACT_MULT
        return speed


# ====================================================================== 粒子
class Particle:
    """爆炸 / 抓到东西时的小碎屑。"""

    __slots__ = ("x", "y", "vx", "vy", "life", "max_life", "color", "size", "gravity")

    def __init__(self, x, y, vx, vy, life, color, size, gravity=520.0):
        self.x, self.y = float(x), float(y)
        self.vx, self.vy = float(vx), float(vy)
        self.life = self.max_life = float(life)
        self.color = color
        self.size = float(size)
        self.gravity = float(gravity)

    def update(self, dt):
        self.life -= dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.vy += self.gravity * dt
        return self.life > 0

    @property
    def radius(self):
        return max(0.6, self.size * (self.life / self.max_life))


def burst(x, y, color, count=10, speed=180.0, life=0.6, size=4.0, gravity=520.0):
    """在 (x, y) 炸开一圈粒子。"""
    out = []
    for i in range(count):
        ang = random.uniform(0, math.tau)
        spd = random.uniform(speed * 0.35, speed)
        out.append(Particle(x, y,
                            math.cos(ang) * spd,
                            math.sin(ang) * spd - speed * 0.25,
                            random.uniform(life * 0.6, life),
                            color, random.uniform(size * 0.5, size),
                            gravity))
    return out


# ====================================================================== 飘字
class FloatingText:
    """“+250”这种向上飘并淡出的分数提示。"""

    __slots__ = ("x", "y", "text", "color", "life", "max_life", "size", "rise")

    def __init__(self, x, y, text, color, size=18, life=1.1, rise=38.0):
        self.x, self.y = float(x), float(y)
        self.text = text
        self.color = color
        self.life = self.max_life = float(life)
        self.size = size
        self.rise = rise

    def update(self, dt):
        self.life -= dt
        self.y -= self.rise * dt
        return self.life > 0

    @property
    def alpha(self):
        return max(0.0, min(1.0, self.life / self.max_life))
