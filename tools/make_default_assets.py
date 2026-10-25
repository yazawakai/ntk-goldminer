# -*- coding: utf-8 -*-
"""生成黄金矿工的默认贴图 (PNG) 与音效 (WAV)。

纯标准库实现（zlib + struct + wave），**不需要 Pillow**，
所以任何 Python 3.8+ 环境都能一键重建素材。

用法：
    python tools/make_default_assets.py            # 只补缺失的文件
    python tools/make_default_assets.py --force    # 全部重新生成

生成后的文件可以直接用同名文件覆盖，游戏会自动加载：
    assets/images/<名字>.png      建议尺寸见 SPRITES 表
    assets/sounds/<名字>.wav      22050Hz / 16bit / 单声道
"""
from __future__ import annotations

import argparse
import math
import os
import random
import struct
import wave
import zlib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG_DIR = os.path.join(BASE, "assets", "images")
SND_DIR = os.path.join(BASE, "assets", "sounds")

# ====================================================================== 迷你绘图库
class Canvas:
    """极简 RGBA 画布：以 scale 倍超采样后降采样，得到抗锯齿效果。"""

    def __init__(self, w, h, scale=3):
        self.scale = scale
        self.lw, self.lh = w, h
        self.w, self.h = w * scale, h * scale
        self.buf = bytearray(self.w * self.h * 4)

    # ---------------------------------------------------------- 基础
    def blend(self, x, y, color):
        x, y = int(x), int(y)
        if not (0 <= x < self.w and 0 <= y < self.h):
            return
        r, g, b, a = color
        if a <= 0:
            return
        i = (y * self.w + x) * 4
        buf = self.buf
        if a >= 255:
            buf[i] = r; buf[i + 1] = g; buf[i + 2] = b; buf[i + 3] = 255
            return
        da = buf[i + 3]
        sa = a / 255.0
        out_a = sa + (da / 255.0) * (1 - sa)
        if out_a <= 0:
            return
        for k, sc in enumerate((r, g, b)):
            dc = buf[i + k]
            buf[i + k] = int(round((sc * sa + dc * (da / 255.0) * (1 - sa)) / out_a))
        buf[i + 3] = int(round(out_a * 255))

    def circle(self, cx, cy, r, color):
        s = self.scale
        cx, cy, r = cx * s, cy * s, r * s
        if r <= 0:
            return
        x0, x1 = max(0, int(cx - r) - 1), min(self.w - 1, int(cx + r) + 1)
        y0, y1 = max(0, int(cy - r) - 1), min(self.h - 1, int(cy + r) + 1)
        for y in range(y0, y1 + 1):
            dy = y + 0.5 - cy
            if abs(dy) > r:
                continue
            half = math.sqrt(max(0.0, r * r - dy * dy))
            for x in range(max(x0, int(cx - half)), min(x1, int(cx + half)) + 1):
                self.blend(x, y, color)

    def ellipse(self, cx, cy, rx, ry, color):
        s = self.scale
        cx, cy, rx, ry = cx * s, cy * s, rx * s, ry * s
        x0, x1 = max(0, int(cx - rx) - 1), min(self.w - 1, int(cx + rx) + 1)
        y0, y1 = max(0, int(cy - ry) - 1), min(self.h - 1, int(cy + ry) + 1)
        for y in range(y0, y1 + 1):
            dy = (y + 0.5 - cy) / ry if ry else 9e9
            if abs(dy) > 1:
                continue
            half = rx * math.sqrt(max(0.0, 1 - dy * dy))
            for x in range(max(x0, int(cx - half)), min(x1, int(cx + half)) + 1):
                self.blend(x, y, color)

    def rect(self, x0, y0, x1, y1, color):
        s = self.scale
        for y in range(max(0, int(y0 * s)), min(self.h, int(y1 * s))):
            for x in range(max(0, int(x0 * s)), min(self.w, int(x1 * s))):
                self.blend(x, y, color)

    def line(self, x0, y0, x1, y1, width, color):
        s = self.scale
        x0, y0, x1, y1 = x0 * s, y0 * s, x1 * s, y1 * s
        w = max(1.0, width * s)
        dist = math.hypot(x1 - x0, y1 - y0)
        steps = max(2, int(dist))
        for i in range(steps + 1):
            t = i / float(steps)
            self.circle(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, w / 2.0, color)

    def arc(self, cx, cy, r, a0, a1, width, color):
        steps = max(6, int(abs(a1 - a0) * r * self.scale / 2.0))
        for i in range(steps + 1):
            a = math.radians(a0 + (a1 - a0) * i / float(steps))
            self.circle(cx + math.cos(a) * r, cy + math.sin(a) * r,
                        width / 2.0, color)

    def poly(self, pts, color):
        s = self.scale
        p = [(x * s, y * s) for x, y in pts]
        ys = [q[1] for q in p]
        y0, y1 = max(0, int(min(ys))), min(self.h - 1, int(max(ys)) + 1)
        n = len(p)
        for y in range(y0, y1 + 1):
            yc = y + 0.5
            xs = []
            for i in range(n):
                ax, ay = p[i]
                bx, by = p[(i + 1) % n]
                if (ay <= yc < by) or (by <= yc < ay):
                    xs.append(ax + (yc - ay) * (bx - ax) / (by - ay))
            xs.sort()
            for i in range(0, len(xs) - 1, 2):
                for x in range(max(0, int(xs[i])), min(self.w - 1, int(xs[i + 1])) + 1):
                    self.blend(x, y, color)

    def poly_outline(self, pts, color, width):
        n = len(pts)
        for i in range(n):
            x0, y0 = pts[i]
            x1, y1 = pts[(i + 1) % n]
            self.line(x0, y0, x1, y1, width, color)

    # ---------------------------------------------------------- 输出
    def downsample(self):
        k = self.scale
        if k == 1:
            return self.buf, self.w, self.h
        w, h = self.lw, self.lh
        out = bytearray(w * h * 4)
        src = self.buf
        for y in range(h):
            for x in range(w):
                ar = ag = ab = aa = 0.0
                for dy in range(k):
                    base = ((y * k + dy) * self.w + x * k) * 4
                    for dx in range(k):
                        i = base + dx * 4
                        a = src[i + 3] / 255.0
                        ar += src[i] * a
                        ag += src[i + 1] * a
                        ab += src[i + 2] * a
                        aa += a
                o = (y * w + x) * 4
                if aa > 0:
                    out[o] = int(round(ar / aa))
                    out[o + 1] = int(round(ag / aa))
                    out[o + 2] = int(round(ab / aa))
                    out[o + 3] = int(round(min(1.0, aa / (k * k)) * 255))
        return out, w, h


def write_png(path, w, h, rgba):
    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))
    raw = bytearray()
    stride = w * 4
    for y in range(h):
        raw.append(0)                      # filter type 0
        raw += rgba[y * stride:(y + 1) * stride]
    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
           + chunk(b"IEND", b""))
    with open(path, "wb") as fp:
        fp.write(png)


def save(path, canvas):
    rgba, w, h = canvas.downsample()
    write_png(path, w, h, rgba)


def blob(cx, cy, r, n, jitter, seed):
    rnd = random.Random(seed)
    pts = []
    for i in range(n):
        a = math.tau * i / n
        rr = r * (1.0 - jitter / 2 + rnd.random() * jitter)
        pts.append((cx + math.cos(a) * rr, cy + math.sin(a) * rr))
    return pts


# ====================================================================== 贴图
GOLD_DARK = (150, 100, 20, 255)
GOLD_MID = (242, 193, 78, 255)
GOLD_LITE = (255, 240, 180, 235)


def make_gold(size):
    c = Canvas(size, size)
    cx = cy = size / 2.0
    r = size / 2.0 - 1.5
    pts = blob(cx, cy, r, 10, 0.22, size)
    c.poly(pts, GOLD_MID)
    c.poly_outline(pts, GOLD_DARK, max(1.0, size / 16.0))
    c.circle(cx - r * 0.34, cy - r * 0.36, r * 0.22, GOLD_LITE)
    c.circle(cx + r * 0.28, cy + r * 0.30, r * 0.16, (205, 148, 40, 170))
    c.circle(cx + r * 0.1, cy - r * 0.55, r * 0.09, (255, 255, 235, 200))
    return c


def make_rock(size):
    c = Canvas(size, size)
    cx = cy = size / 2.0
    r = size / 2.0 - 1.5
    pts = blob(cx, cy, r, 7, 0.18, size * 7)
    c.poly(pts, (138, 143, 152, 255))
    c.poly_outline(pts, (86, 92, 102, 255), max(1.0, size / 18.0))
    c.line(cx - r * 0.45, cy - r * 0.35, cx + r * 0.05, cy + r * 0.4, size / 18.0, (109, 115, 125, 255))
    c.line(cx + r * 0.05, cy + r * 0.4, cx + r * 0.45, cy + r * 0.1, size / 22.0, (109, 115, 125, 255))
    c.circle(cx + r * 0.3, cy - r * 0.45, r * 0.2, (164, 170, 180, 200))
    return c


def make_diamond(size):
    c = Canvas(size, size)
    cx = cy = size / 2.0
    r = size / 2.0 - 1.5
    pts = [(cx, cy - r), (cx + r, cy - r * 0.25), (cx + r * 0.55, cy + r * 0.85),
           (cx - r * 0.55, cy + r * 0.85), (cx - r, cy - r * 0.25)]
    c.poly(pts, (169, 240, 255, 255))
    c.poly_outline(pts, (42, 168, 200, 255), max(1.0, size / 14.0))
    c.line(cx - r, cy - r * 0.25, cx + r, cy - r * 0.25, max(1.0, size / 20.0), (232, 254, 255, 255))
    c.line(cx, cy - r, cx, cy + r * 0.85, max(1.0, size / 20.0), (232, 254, 255, 220))
    c.line(cx - r * 0.55, cy - r * 0.25, cx, cy + r * 0.85, 1.0, (232, 254, 255, 200))
    c.line(cx + r * 0.55, cy - r * 0.25, cx, cy + r * 0.85, 1.0, (232, 254, 255, 200))
    return c


def make_bag(size, kind="money"):
    c = Canvas(size, size)
    cx = size / 2.0
    body = (185, 129, 73, 255) if kind == "money" else (139, 92, 246, 255)
    edge = (111, 68, 35, 255) if kind == "money" else (91, 33, 182, 255)
    r = size / 2.0 - 1.5
    cy = size * 0.62
    c.ellipse(cx, cy, r, r * 0.82, body)
    c.rect(cx - r * 0.34, cy - r * 1.5, cx + r * 0.34, cy - r * 0.6, body)
    c.ellipse(cx, cy, r, r * 0.82, (0, 0, 0, 0))
    # 袋口与绳子
    c.line(cx - r * 0.36, cy - r * 1.1, cx + r * 0.36, cy - r * 1.1, size / 14.0, edge)
    c.line(cx - r * 0.5, cy - r * 0.62, cx + r * 0.5, cy - r * 0.62, size / 16.0, edge)
    c.ellipse(cx, cy + r * 0.1, r * 0.98, r * 0.7, (0, 0, 0, 0))
    # 符号
    glyph = "#f7e7bd" if kind == "money" else "#f4e9ff"
    col = tuple(int(glyph[i:i + 2], 16) for i in (1, 3, 5)) + (255,)
    w = max(1.4, size / 13.0)
    if kind == "money":
        c.arc(cx, cy - r * 0.05, r * 0.3, -60, 180, w, col)
        c.arc(cx, cy + r * 0.3, r * 0.3, 120, 360, w, col)
        c.line(cx, cy - r * 0.45, cx, cy + r * 0.7, w * 0.8, col)
    else:
        c.arc(cx, cy - r * 0.1, r * 0.34, 190, 420, w, col)
        c.line(cx + r * 0.16, cy + r * 0.12, cx, cy + r * 0.34, w, col)
        c.circle(cx, cy + r * 0.6, w * 0.65, col)
    return c


def make_bomb(size):
    c = Canvas(size, size)
    cx, cy = size / 2.0, size * 0.56
    r = size * 0.38
    c.line(cx + r * 0.4, cy - r * 0.8, cx + r * 1.1, cy - r * 2.0, size / 12.0, (201, 139, 63, 255))
    c.circle(cx + r * 1.15, cy - r * 2.1, size * 0.07, (255, 179, 71, 255))
    c.circle(cx + r * 1.15, cy - r * 2.1, size * 0.035, (255, 245, 210, 255))
    c.circle(cx, cy, r, (34, 38, 46, 255))
    c.circle(cx - r * 0.35, cy - r * 0.38, r * 0.22, (110, 118, 132, 220))
    c.rect(cx - r * 0.3, cy - r * 1.2, cx + r * 0.3, cy - r * 0.85, (58, 63, 74, 255))
    return c


def make_potion(size):
    c = Canvas(size, size)
    cx = size / 2.0
    bottle = (223, 240, 255, 255)
    liquid = (73, 200, 255, 255)
    c.rect(cx - size * 0.10, size * 0.10, cx + size * 0.10, size * 0.26, (138, 90, 43, 255))
    c.rect(cx - size * 0.14, size * 0.24, cx + size * 0.14, size * 0.36, bottle)
    c.rect(cx - size * 0.26, size * 0.34, cx + size * 0.26, size * 0.90, bottle)
    c.circle(cx - size * 0.13, size * 0.88, size * 0.13, bottle)
    c.circle(cx + size * 0.13, size * 0.88, size * 0.13, bottle)
    c.rect(cx - size * 0.20, size * 0.46, cx + size * 0.20, size * 0.80, liquid)
    c.circle(cx - size * 0.07, size * 0.78, size * 0.07, liquid)
    c.circle(cx + size * 0.07, size * 0.78, size * 0.07, liquid)
    c.line(cx - size * 0.17, size * 0.40, cx - size * 0.17, size * 0.62, size / 16.0, (255, 255, 255, 200))
    c.line(cx - size * 0.30, size * 0.86, cx + size * 0.30, size * 0.86, 1.0, (127, 182, 217, 255))
    return c


def make_miner(size):
    """矿工：帽子在上、脸露出来、右手握着绳子起点（精灵高度的 30% 处）。"""
    c = Canvas(size, size)
    cx = size / 2.0
    skin = (240, 195, 154, 255)
    skin_dark = (185, 138, 94, 255)
    shirt = (61, 110, 168, 255)
    shirt_dark = (34, 55, 90, 255)
    hat = (255, 207, 73, 255)
    hat_dark = (184, 134, 11, 255)
    # 腿
    c.line(cx - size * 0.13, size * 0.99, cx - size * 0.08, size * 0.80, size * 0.085, shirt_dark)
    c.line(cx + size * 0.13, size * 0.99, cx + size * 0.08, size * 0.80, size * 0.085, shirt_dark)
    # 身体
    c.rect(cx - size * 0.19, size * 0.60, cx + size * 0.19, size * 0.82, shirt)
    c.rect(cx - size * 0.04, size * 0.60, cx + size * 0.04, size * 0.82, shirt_dark)
    # 双臂向下、双手握在身体下方 —— 钩爪的起点就在矿工下面
    c.line(cx - size * 0.20, size * 0.64, cx - size * 0.13, size * 0.90, size * 0.075, skin)
    c.line(cx + size * 0.20, size * 0.64, cx + size * 0.13, size * 0.90, size * 0.075, skin)
    c.circle(cx - size * 0.13, size * 0.91, size * 0.052, skin)
    c.circle(cx + size * 0.13, size * 0.91, size * 0.052, skin)
    # 头
    c.circle(cx, size * 0.45, size * 0.165, skin)
    c.arc(cx, size * 0.47, size * 0.165, 20, 160, size * 0.02, skin_dark)
    c.circle(cx - size * 0.06, size * 0.43, size * 0.024, (43, 43, 43, 255))
    c.circle(cx + size * 0.06, size * 0.43, size * 0.024, (43, 43, 43, 255))
    c.line(cx - size * 0.07, size * 0.52, cx + size * 0.07, size * 0.52, size * 0.03, (122, 74, 34, 255))
    # 安全帽（帽子在头顶，不遮住脸）
    c.arc(cx, size * 0.38, size * 0.17, 180, 360, size * 0.095, hat)
    c.rect(cx - size * 0.22, size * 0.345, cx + size * 0.22, size * 0.385, hat)
    c.rect(cx - size * 0.22, size * 0.375, cx + size * 0.22, size * 0.392, hat_dark)
    c.circle(cx, size * 0.23, size * 0.032, (255, 245, 200, 255))
    return c


def make_background(w, h, ground_y=168):
    c = Canvas(w, h, scale=1)
    sky_top = (11, 18, 38)
    sky_bot = (29, 48, 85)
    for y in range(ground_y):
        t = y / float(ground_y)
        col = tuple(int(sky_top[i] + (sky_bot[i] - sky_top[i]) * t) for i in range(3)) + (255,)
        c.rect(0, y, w, y + 1, col)
    rnd = random.Random(20240607)
    for _ in range(120):
        x, y = rnd.uniform(0, w), rnd.uniform(0, ground_y - 24)
        c.circle(x, y, rnd.choice((0.7, 0.7, 1.2)), (205, 217, 255, rnd.randint(120, 255)))
    c.circle(w - 148, 66, 44, (200, 214, 255, 40))          # 月亮光晕
    c.circle(w - 148, 66, 26, (238, 243, 255, 190))         # 月亮
    c.circle(w - 158, 58, 7, (214, 222, 245, 160))
    c.rect(0, ground_y, w, ground_y + 6, (79, 122, 43, 255))
    c.rect(0, ground_y + 6, w, ground_y + 10, (58, 92, 30, 255))
    dirt_top, dirt_bot = (122, 79, 38), (51, 32, 15)
    depth = h - ground_y - 10
    for y in range(ground_y + 10, h):
        t = (y - ground_y - 10) / float(max(1, depth))
        col = tuple(int(dirt_top[i] + (dirt_bot[i] - dirt_top[i]) * t) for i in range(3)) + (255,)
        c.rect(0, y, w, y + 1, col)
    for _ in range(2200):
        x, y = rnd.uniform(0, w), rnd.uniform(ground_y + 14, h)
        t = (y - ground_y - 10) / float(max(1, depth))
        base = [int(dirt_top[i] + (dirt_bot[i] - dirt_top[i]) * t) for i in range(3)]
        shade = rnd.choice((-26, -12, 12, 26))
        col = tuple(max(0, min(255, v + shade)) for v in base) + (255,)
        c.circle(x, y, rnd.uniform(0.8, 2.4), col)
    return c


SPRITES = {
    "gold_small": lambda: make_gold(30),
    "gold_medium": lambda: make_gold(40),
    "gold_large": lambda: make_gold(54),
    "gold_huge": lambda: make_gold(68),
    "rock_small": lambda: make_rock(36),
    "rock_large": lambda: make_rock(56),
    "diamond": lambda: make_diamond(28),
    "money_bag": lambda: make_bag(38, "money"),
    "mystery_bag": lambda: make_bag(38, "mystery"),
    "bomb_pickup": lambda: make_bomb(34),
    "potion_pickup": lambda: make_potion(34),
    "miner": lambda: make_miner(84),
    "background": lambda: make_background(960, 640),
}


# ====================================================================== 音效
SR = 22050


def env(i, n, attack=0.02, release=0.35):
    """简易 ADSR（这里只用 A + 指数衰减）。"""
    a = max(1, int(n * attack))
    r = max(1, int(n * release))
    if i < a:
        return i / float(a)
    if i > n - r:
        return max(0.0, (n - i) / float(r)) ** 1.5
    return math.exp(-2.2 * (i - a) / float(max(1, n - a)))


def render(dur, gen, volume=0.55, attack=0.02, release=0.35):
    n = int(SR * dur)
    return [max(-1.0, min(1.0, gen(i / SR, i, n) * env(i, n, attack, release) * volume))
            for i in range(n)]


def sweep(f0, f1, shape="sine", dur=0.12, vibrato=0.0):
    def gen(t, i, n):
        k = i / float(max(1, n - 1))
        f = f0 + (f1 - f0) * k
        ph = math.tau * (f0 * t + (f1 - f0) * t * k / 2.0)
        v = math.sin(ph)
        if vibrato:
            v *= 1.0 + vibrato * math.sin(math.tau * 18 * t)
        if shape == "square":
            v = 1.0 if v >= 0 else -1.0
        elif shape == "tri":
            v = 2.0 / math.pi * math.asin(math.sin(ph))
        return v
    return gen


def notes(seq, dur_each=0.08, shape="sine", volume=0.5):
    """seq = [(freq, dur), ...]，拼成一段旋律。"""
    out = []
    for freq, dur in seq:
        n = int(SR * dur)
        for i in range(n):
            t = i / SR
            v = math.sin(math.tau * freq * t)
            if shape == "square":
                v = 1.0 if v >= 0 else -1.0
            out.append(v * env(i, n, 0.02, 0.45) * volume)
    return out


def make_sounds():
    rnd = random.Random(7)
    noise = [rnd.uniform(-1, 1) for _ in range(SR)]

    def noise_at(t):
        return noise[int(t * SR) % len(noise)]

    sounds = {}
    sounds["hook_shoot"] = render(0.14, sweep(900, 260, "square"), volume=0.3, release=0.6)
    sounds["hook_hit"] = ([noise_at(t) * 0.6 * math.exp(-30 * t) for t in
                           (i / SR for i in range(int(SR * 0.05)))]
                          + render(0.10, sweep(190, 120), volume=0.45))
    sounds["collect"] = (notes([(659, 0.07)], volume=0.45)
                         + notes([(988, 0.13)], volume=0.5))
    sounds["explosion"] = [max(-1.0, min(1.0,
                             (noise_at(t) * 0.9 + math.sin(math.tau * 58 * t) * 0.6)
                             * math.exp(-6.5 * t) * 0.8))
                           for t in (i / SR for i in range(int(SR * 0.5)))]
    sounds["powerup"] = notes([(523, 0.06), (659, 0.06), (784, 0.06), (1047, 0.12)], volume=0.45)
    sounds["level_up"] = notes([(523, 0.11), (659, 0.11), (784, 0.11), (1047, 0.22)], volume=0.5)
    sounds["game_over"] = notes([(440, 0.16), (349, 0.16), (262, 0.16), (196, 0.30)], volume=0.5)
    sounds["tick"] = render(0.05, sweep(1300, 1300, "square"), volume=0.18, release=0.7)
    sounds["deny"] = render(0.13, sweep(240, 160, "square", vibrato=0.15), volume=0.28)
    return sounds


def write_wav(path, samples):
    with wave.open(path, "wb") as fp:
        fp.setnchannels(1)
        fp.setsampwidth(2)
        fp.setframerate(SR)
        fp.writeframes(b"".join(struct.pack("<h", int(max(-1.0, min(1.0, s)) * 32000))
                                for s in samples))


# ====================================================================== 入口
def main():
    ap = argparse.ArgumentParser(description="生成默认贴图与音效")
    ap.add_argument("--force", action="store_true", help="覆盖已存在的文件")
    args = ap.parse_args()

    os.makedirs(IMG_DIR, exist_ok=True)
    os.makedirs(SND_DIR, exist_ok=True)

    made = skipped = 0
    for name, factory in SPRITES.items():
        path = os.path.join(IMG_DIR, name + ".png")
        if os.path.exists(path) and not args.force:
            skipped += 1
            continue
        save(path, factory())
        made += 1
        print("  贴图 -> %s" % os.path.relpath(path, BASE))

    for name, samples in make_sounds().items():
        path = os.path.join(SND_DIR, name + ".wav")
        if os.path.exists(path) and not args.force:
            skipped += 1
            continue
        write_wav(path, samples)
        made += 1
        print("  音效 -> %s" % os.path.relpath(path, BASE))

    print("完成：生成 %d 个文件，跳过 %d 个已存在文件。" % (made, skipped))


if __name__ == "__main__":
    main()
