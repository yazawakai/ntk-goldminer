# -*- coding: utf-8 -*-
"""黄金矿工 (Gold Miner) —— 启动入口。

运行：
    python main.py
"""
from __future__ import annotations

import os
import sys
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gm import config as C            # noqa: E402
from gm.game import GoldMinerGame     # noqa: E402


def enable_dpi_awareness():
    """Windows 高分屏下避免窗口模糊。"""
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass


def main():
    enable_dpi_awareness()
    root = tk.Tk()
    root.title(C.TITLE)
    root.resizable(False, False)

    game = GoldMinerGame(root)

    # 居中显示
    root.update_idletasks()
    w, h = root.winfo_width(), root.winfo_height()
    x = max(0, (root.winfo_screenwidth() - w) // 2)
    y = max(0, (root.winfo_screenheight() - h) // 3)
    root.geometry("+%d+%d" % (x, y))

    # 启动时打印一次自检，方便确认自定义贴图 / 音效是否被识别
    have_i, miss_i, have_s, miss_s = game.res.report()
    print("[窗口] 画布 %dx%d（UI 倍率 x%d，高 DPI 下自动放大）"
          % (w, h, game.scale))
    print("[资源] 贴图 %d/%d 已加载；音效 %d/%d 已加载"
          % (len(have_i), len(have_i) + len(miss_i), len(have_s), len(have_s) + len(miss_s)))
    print("[音频] %s" % game.res.audio_backend())
    if miss_i:
        print("       缺少贴图（将使用矢量兜底）:", ", ".join(miss_i))
    if miss_s:
        print("       缺少音效（将静音）:", ", ".join(miss_s))

    root.protocol("WM_DELETE_WINDOW", game.quit)
    root.mainloop()


if __name__ == "__main__":
    main()
