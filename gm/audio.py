# -*- coding: utf-8 -*-
"""音频层：**多路混音**播放，新音效绝不打断正在响的旧音效。

为什么要换掉 winsound？
----------------------
``winsound.PlaySound(..., SND_ASYNC)`` 是**单通道**的：一个进程里同时只有一段声音，
后一段一响，前一段立刻被掐掉（抓到东西的“叮”会把爆炸声切断）。

怎么做到多路？
--------------
Windows 自带的 MCI（``winmm.dll``）可以给每个 ``alias`` 开一个**独立的 waveaudio
设备句柄**，由系统混音器叠加输出。这里维护一个小型**声道池**：

    close <alias> → open "<wav>" type waveaudio alias <alias> → play <alias> from 0

每次播放都挑一个当前没在响的空闲声道，所以**已经在响的那几路完全不受影响**。
如果池子全忙（同时 8 路声音，远超本游戏的实际需要），就**丢弃这一声新的**，
而不是抢断旧的 —— 宁可少响一下，也不切断已经在播的音频。

全部通过 ctypes 调用系统 API，**不需要任何第三方库**。

降级链：MCI 多路 → winsound 单路 → 静音（非 Windows / 没有可用音频设备）。
"""
from __future__ import annotations

import ctypes
import itertools
import os
import sys
import time
import wave

try:                        # Windows 自带；其他平台没有
    import winsound
except Exception:           # pragma: no cover
    winsound = None

_INSTANCE_SEQ = itertools.count(1)


class Audio:
    """多路音效播放器（MCI 声道池 + winsound 兜底）。"""

    def __init__(self, voices=8, volume=1.0, backend="auto"):
        self.muted = False
        self.volume = max(0.0, min(1.0, float(volume)))
        self.backend = "silent"        # mci / winsound / silent
        self.played = 0                # 统计：成功播放次数
        self.dropped = 0               # 统计：声道全忙而丢弃新音效的次数
        self._closed = False
        self._mm = None
        self._pool = []                # [alias, ...]
        self._busy = {}                # alias -> 忙到哪个时间点（time.monotonic）
        self._duration = {}            # 音频文件 -> 秒数
        self._turn = 0

        if backend in ("auto", "mci"):
            self._init_mci(max(1, int(voices)))
        if self._mm is None and backend in ("auto", "winsound") and winsound is not None:
            self.backend = "winsound"

    # ------------------------------------------------------------ MCI 初始化
    def _init_mci(self, count):
        if sys.platform != "win32":
            return
        try:
            mm = ctypes.WinDLL("winmm")
            mm.mciSendStringW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p,
                                          ctypes.c_uint, ctypes.c_void_p]
            mm.mciSendStringW.restype = ctypes.c_uint
        except Exception:                     # pragma: no cover
            return
        self._mm = mm
        tag = "gmsnd%d" % next(_INSTANCE_SEQ)     # 同进程多个实例也不冲突
        self._pool = ["%s_%d" % (tag, i) for i in range(count)]
        self.backend = "mci"

    # ------------------------------------------------------------ MCI 底层
    def _cmd(self, cmd, reply=False):
        """执行一条 MCI 命令，返回 (错误码, 回复文本)。"""
        if self._mm is None:
            return (1, "")
        buf = ctypes.create_unicode_buffer(300) if reply else None
        rc = self._mm.mciSendStringW(cmd, buf, 300 if reply else 0, None)
        return (rc, buf.value.strip() if reply else "")

    def _mode(self, alias):
        rc, val = self._cmd("status %s mode" % alias, reply=True)
        return val if rc == 0 else ""

    def _length(self, path, alias):
        """音频时长（秒）。

        先用 wave 读文件头（最准最快）；不是标准 wav 时再问 MCI 要长度，
        最后兜底按文件大小估一个。结果按文件缓存。
        """
        if path in self._duration:
            return self._duration[path]
        secs = None
        try:
            with wave.open(path, "rb") as fp:
                rate = fp.getframerate() or 1
                secs = fp.getnframes() / float(rate)
        except Exception:
            rc, val = self._cmd("status %s length" % alias, reply=True)
            if rc == 0:
                try:
                    secs = int(val) / 1000.0        # waveaudio 的 length 单位是毫秒
                except Exception:
                    secs = None
            if secs is None:
                try:
                    secs = max(1.0, os.path.getsize(path) / 16000.0)   # 粗暴估算
                except Exception:
                    secs = 3.0
        self._duration[path] = secs
        return secs

    def _free_voice(self):
        """找一个空闲声道；全在响就返回 None（绝不抢断）。

        这里用**播放时长记账**判断声道是否忙，而不是每帧去问 MCI 的状态：
        在“关掉又立刻复用同一个 alias”的高频场景里，驱动有时会一直回报
        playing，那样声道池会被假占用耗尽（真实的坑，已实测）。
        """
        now = time.monotonic()
        n = len(self._pool)
        for i in range(n):
            alias = self._pool[(self._turn + i) % n]
            if self._busy.get(alias, (0.0, ""))[0] <= now:
                self._turn = (self._turn + i + 1) % n
                return alias
        return None

    def _play_on(self, alias, path):
        """在指定声道上播放；返回 False 表示设备打不开（需要降级）。"""
        self._cmd("close %s" % alias)          # 复用这个声道：先关掉它的上一段
        rc, _ = self._cmd('open "%s" type waveaudio alias %s' % (path, alias), reply=True)
        if rc != 0:
            return False
        secs = self._length(path, alias)
        if self.volume < 0.999:
            # 部分驱动不支持 setaudio，失败也无所谓
            self._cmd("setaudio %s volume to %d" % (alias, int(self.volume * 1000)))
        rc, _ = self._cmd("play %s from 0" % alias, reply=True)
        if rc != 0:
            self._cmd("close %s" % alias)
            return False
        self._busy[alias] = (time.monotonic() + secs + 0.08, os.path.basename(path))
        return True

    # ------------------------------------------------------------ 对外接口
    def play(self, path):
        """播放一个 wav；**不会影响任何正在播放的音效**。"""
        if self.muted or self._closed or not path:
            return False

        if self._mm is not None:
            alias = self._free_voice()
            if alias is None:                  # 声道池满：丢掉这一声新的
                self.dropped += 1
                return False
            if self._play_on(alias, path):
                self.played += 1
                return True
            # 这台机器用不了 MCI（比如没有 waveaudio 设备）→ 永久降级
            self._mm = None
            self.backend = "winsound" if winsound is not None else "silent"

        if winsound is None:
            return False
        try:
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC
                               | winsound.SND_NODEFAULT)
            self.played += 1
            return True
        except Exception:                      # pragma: no cover
            return False

    def active(self):
        """当前正在响的声道列表 —— 调试 / 自测用。"""
        if self._mm is None:
            return []
        now = time.monotonic()
        return [a for a in self._pool if self._busy.get(a, (0.0, ""))[0] > now]

    def busy_detail(self):
        """每个占用中的声道 (别名, 剩余秒数, 文件名)，调试用。"""
        now = time.monotonic()
        out = []
        for alias in self._pool:
            until, name = self._busy.get(alias, (0.0, ""))
            if until > now:
                out.append((alias, round(until - now, 2), name))
        return out

    def stop_all(self):
        """立刻停掉所有正在播放的音效（静音 / 退出时用）。"""
        self._busy.clear()
        if self._mm is None:
            if winsound is not None:
                try:
                    winsound.PlaySound(None, winsound.SND_PURGE)
                except Exception:              # pragma: no cover
                    pass
            return
        for alias in self._pool:
            self._cmd("close %s" % alias)

    def close(self):
        self.stop_all()
        self._mm = None
        self._closed = True

    def set_muted(self, muted):
        self.muted = bool(muted)
        if self.muted:
            self.stop_all()
        return self.muted

    def toggle_mute(self):
        return self.set_muted(not self.muted)

    def describe(self):
        """给启动自检用的一行说明。"""
        if self._closed:
            return "已关闭"
        if self.muted:
            return "已静音"
        if self.backend == "mci":
            return "MCI 多路混音（%d 声道，新音效不会打断旧音效）" % len(self._pool)
        if self.backend == "winsound":
            return "winsound 单通道（后一段会打断前一段）"
        return "无可用音频输出（静音）"
