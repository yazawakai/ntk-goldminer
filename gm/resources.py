# -*- coding: utf-8 -*-
"""资源管理：贴图 (PNG) 与音效 (WAV) 的加载、缩放与播放。

设计要点
--------
* 贴图放在 ``assets/images/<名字>.png``，找不到就用游戏内的矢量画法兜底，
  所以删掉资源目录游戏照样能跑。
* 音效放在 ``assets/sounds/<名字>.wav``，找不到就静音降级。
* 音效走 :mod:`gm.audio` 的**多路混音**：新音效不会打断正在播放的旧音效。
* 你只要往这两个目录里丢同名文件，就能换成自己的美术 / 音效，不用改代码。
"""
from __future__ import annotations

import math
import os
import tkinter as tk
from tkinter import font as tkfont

from . import config as C
from .audio import Audio


class Resources:
    """贴图 + 音效 + 字体，统一缓存。"""

    def __init__(self):
        self._images = {}       # (name, size) -> PhotoImage（同时持有引用防止被回收）
        self._missing = set()   # 已验证不存在的贴图
        self._sounds = {}       # name -> path or None
        self.audio = Audio(voices=C.AUDIO_VOICES, volume=C.AUDIO_VOLUME,
                           backend=C.AUDIO_BACKEND)
        self.family = self._pick_font()

    @property
    def muted(self):
        return self.audio.muted

    # -------------------------------------------------------------- 字体
    @staticmethod
    def _pick_font():
        try:
            families = set(tkfont.families())
        except Exception:       # pragma: no cover
            families = set()
        for name in C.FONT_CANDIDATES:
            if name in families:
                return name
        return "TkDefaultFont"

    def font(self, size, bold=False):
        """返回字体元组。

        字号用**负数**（Tk 里表示像素高度而不是磅值），这样在 150% / 200%
        缩放的屏幕上布局不会因为 DPI 换算而错位；真正的放大交给 Painter。
        """
        px = -int(round(abs(size)))
        return (self.family, px, "bold") if bold else (self.family, px)

    # -------------------------------------------------------------- 贴图
    def image(self, name, size=None):
        """取贴图；size=(w,h) 时做近似缩放；不存在返回 None。"""
        key = (name, size)
        if key in self._images:
            return self._images[key]
        if name in self._missing:
            return None
        path = os.path.join(C.IMAGE_DIR, name + ".png")
        if not os.path.isfile(path):
            self._missing.add(name)
            return None
        try:
            img = tk.PhotoImage(file=path)
            if size:
                img = self._resize(img, int(size[0]), int(size[1]))
        except Exception:
            self._missing.add(name)
            return None
        self._images[key] = img
        return img

    @staticmethod
    def _factors(cur, want):
        """返回 (zoom倍数, subsample倍数)，Tk 只支持整数缩放。"""
        ratio = cur / float(want)
        if ratio >= 1.0:                       # 需要缩小
            return 1, max(1, int(round(ratio)))
        return max(1, int(round(1.0 / ratio))), 1   # 需要放大

    @staticmethod
    def _resize(img, w, h):
        """按目标像素尺寸缩放贴图（x/y 轴分别取最接近的整数倍）。

        高 DPI 下目标尺寸正好是原始尺寸的整数倍（如 2 倍），
        所以这里能给出精确、清晰的缩放结果。
        """
        ow, oh = img.width(), img.height()
        if (ow, oh) == (w, h) or w <= 0 or h <= 0:
            return img
        zx, sx = Resources._factors(ow, w)
        zy, sy = Resources._factors(oh, h)
        out = img
        if zx > 1 or zy > 1:
            out = out.zoom(zx, zy)
        if sx > 1 or sy > 1:
            out = out.subsample(sx, sy)
        return out

    @staticmethod
    def _best_ratio(target, limit=4):
        """把浮点缩放系数近似成一对整数 (zoom, subsample)。

        Tk 只能整数倍缩放，所以 1.5 这种倍率用 zoom(3)+subsample(2) 拼出来。
        """
        best, best_err = (1, 1), abs(target - 1.0)
        for f in range(1, limit + 1):
            for z in range(1, limit + 1):
                err = abs(z / float(f) - target)
                if err < best_err - 1e-9:
                    best_err, best = err, (z, f)
        return best

    @staticmethod
    def _crop_center(img, w, h):
        """居中裁切出 w×h 的图片（用 Tk 的 image copy -from/-to）。"""
        w = max(1, min(int(w), img.width()))
        h = max(1, min(int(h), img.height()))
        x0 = (img.width() - w) // 2
        y0 = (img.height() - h) // 2
        out = tk.PhotoImage(width=w, height=h)
        out.tk.call(out, "copy", img, "-from", x0, y0, x0 + w, y0 + h, "-to", 0, 0)
        return out

    def image_fit(self, name, box_w, box_h, zoom=1.0):
        """把贴图缩放后塞进 box：先按比例缩放，再**居中裁切**到 box 大小。

        zoom=1.0 → 整张图完整放进框里（多余部分留框底色，不会变形）；
        zoom>1.0 → 图放大 zoom 倍再裁切，于是人物更大（特写），比如 2.0。
        结果按 (名字, 尺寸, 倍率) 缓存，商店每帧重绘不会重复缩放。
        """
        if not name:
            return None
        box_w, box_h = max(1, int(box_w)), max(1, int(box_h))
        key = ("fit", name, box_w, box_h, round(float(zoom), 2))
        if key in self._images:
            return self._images[key]
        base = self.image(name)
        if base is None:
            self._images[key] = None
            return None

        ow, oh = base.width(), base.height()
        fit = min(box_w / float(ow), box_h / float(oh))       # 完整放进去的倍率
        z, f = self._best_ratio(fit * max(0.05, float(zoom)))
        img = base
        if z > 1:
            img = img.zoom(z, z)
        if f > 1:
            img = img.subsample(f, f)
        if img.width() > box_w or img.height() > box_h:       # 放大的部分裁掉
            img = self._crop_center(img, box_w, box_h)
        self._images[key] = img
        return img

    # -------------------------------------------------------------- 音效
    def sound_path(self, name):
        if name not in self._sounds:
            path = os.path.join(C.SOUND_DIR, name + ".wav")
            self._sounds[name] = path if os.path.isfile(path) else None
        return self._sounds[name]

    def play(self, name):
        """播放一个音效。

        多个音效可以**同时响**（MCI 声道池），所以“抓到东西的叮”不会把
        “炸弹爆炸”掐断；静音 / 无文件 / 非 Windows 时安全忽略。
        """
        if self.audio.muted:
            return False
        path = self.sound_path(name)
        if not path:
            return False
        return self.audio.play(path)

    def toggle_mute(self):
        return self.audio.toggle_mute()

    def close(self):
        """退出时释放所有声道。"""
        self.audio.close()

    def audio_backend(self):
        return self.audio.describe()

    # -------------------------------------------------------------- 自检
    def report(self):
        """返回 (已有贴图, 缺失贴图, 已有音效, 缺失音效)，供调试输出。"""
        have_i, miss_i = [], []
        for name in C.SPRITES:
            (have_i if os.path.isfile(os.path.join(C.IMAGE_DIR, name + ".png")) else miss_i).append(name)
        have_s, miss_s = [], []
        for name in C.SOUNDS:
            (have_s if os.path.isfile(os.path.join(C.SOUND_DIR, name + ".wav")) else miss_s).append(name)
        return have_i, miss_i, have_s, miss_s
