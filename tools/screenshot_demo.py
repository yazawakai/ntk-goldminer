# -*- coding: utf-8 -*-
"""自动演示 + 截图：无需人工操作，直接把各个界面存成 PNG。

用法：
    python tools/screenshot_demo.py           # 输出到 shots/
它会启动真实游戏（真实主循环），按时间轴自动开局、发射钩子、喝强力水、
触发过关与结算界面，并在每个关键时刻用 GDI 抓取窗口画面存成图片。
"""
from __future__ import annotations

import ctypes
import os
import random
import sys
import ctypes.wintypes as wt

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, "tools"))

import tkinter as tk                                   # noqa: E402
from make_default_assets import write_png             # noqa: E402
from main import enable_dpi_awareness                 # noqa: E402
from gm.entities import Hook                          # noqa: E402
from gm.game import GoldMinerGame                     # noqa: E402

OUT_DIR = os.path.join(BASE, "shots")
user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG),
                ("biPlanes", wt.WORD), ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
                ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", wt.LONG),
                ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD), ("biClrImportant", wt.DWORD)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wt.DWORD * 3)]


def grab_window(hwnd):
    """抓取窗口像素，返回 (w, h, rgba)。"""
    rect = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w, h = rect.right - rect.left, rect.bottom - rect.top
    screen_dc = user32.GetDC(0)
    hdc = user32.GetWindowDC(hwnd)
    mem = gdi32.CreateCompatibleDC(screen_dc)
    bmp = gdi32.CreateCompatibleBitmap(screen_dc, w, h)
    old = gdi32.SelectObject(mem, bmp)
    painted = user32.PrintWindow(hwnd, mem, 2)          # PW_RENDERFULLCONTENT
    if not painted:
        gdi32.BitBlt(mem, 0, 0, w, h, hdc, 0, 0, 0x00CC0020)   # SRCCOPY
    bi = BITMAPINFO()
    bi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bi.bmiHeader.biWidth = w
    bi.bmiHeader.biHeight = -h                         # 负数 = 自上而下
    bi.bmiHeader.biPlanes = 1
    bi.bmiHeader.biBitCount = 32
    bi.bmiHeader.biCompression = 0
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bi), 0)
    gdi32.SelectObject(mem, old)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem)
    user32.ReleaseDC(hwnd, hdc)
    user32.ReleaseDC(0, screen_dc)

    data = bytearray(buf.raw)
    if not any(data[0::4]) and not any(data[1::4]) and not any(data[2::4]):
        return None                                    # 全黑 = 抓取失败
    data[0::4], data[2::4] = data[2::4], data[0::4]    # BGRA -> RGBA
    data[3::4] = b"\xff" * (w * h)
    return w, h, data


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    enable_dpi_awareness()          # 与 main.py 一致：按物理像素取窗口坐标
    root = tk.Tk()
    root.title("黄金矿工 Gold Miner")
    root.resizable(False, False)
    game = GoldMinerGame(root)
    root.update_idletasks()
    root.geometry("+%d+%d" % (max(0, (root.winfo_screenwidth() - root.winfo_width()) // 2),
                              max(0, (root.winfo_screenheight() - root.winfo_height()) // 3)))
    root.focus_force()
    saved = []

    def snap(name):
        root.update_idletasks()
        hwnd = int(root.frame(), 16) if root.frame() else root.winfo_id()
        got = grab_window(hwnd) or grab_window(root.winfo_id())
        if not got:
            print("  截图失败:", name)
            return
        w, h, rgba = got
        path = os.path.join(OUT_DIR, name + ".png")
        write_png(path, w, h, rgba)
        saved.append((name, w, h))
        print("  截图 -> %s (%dx%d)" % (os.path.relpath(path, BASE), w, h))

    def auto_launch():
        if not game.running:
            return
        if game.state == "playing" and game.hook.state == Hook.SWING:
            game.launch()
        root.after(140, auto_launch)

    def force_grab():
        """摆一个“钩子正夹着金块往回拉”的画面，展示抓取动画。"""
        items = [i for i in game.items if i.alive and not i.prop]
        if not items:
            return
        it = random.choice(items)
        it.grabbed, it.pop = True, 1.0
        it.x, it.y = 420, 330
        game.hook.grabbed = it
        game.hook.state = Hook.RETRACT
        game.hook.theta, game.hook.length, game.hook.claw = -0.28, 300.0, 0.0
        game._float(480, 200, it.burst_score_text(), "#ffcf49", size=22)

    root.after(900, lambda: snap("1_menu"))
    root.after(1400, game.start_game)
    root.after(1500, auto_launch)
    root.after(3200, lambda: game.use_prop("potion"))
    root.after(4600, force_grab)
    # 故意把分数拉到目标之上：演示“达标也不结束关卡”的新 HUD（绿条 + ✔）
    root.after(4700, lambda: setattr(game, "score", int(game.target() * 1.25)))
    root.after(4900, lambda: snap("2_playing"))
    root.after(5400, lambda: setattr(game, "state", "paused"))
    root.after(5700, lambda: snap("3_paused"))
    root.after(6100, lambda: game._level_clear(bonus=True))      # 挖空矿场 → 提前过关
    root.after(6500, lambda: snap("4_level_clear"))
    root.after(6900, lambda: game._level_clear(bonus=False))     # 时间到达标 → 过关
    root.after(7300, lambda: snap("5_timeup_clear"))
    # 商店：默认平静脸 → 买完高兴脸 → 花钱离开时道谢
    root.after(7700, lambda: (setattr(game, "score", 2600), game.open_shop()))
    root.after(8200, lambda: snap("6_shop_neutral"))
    root.after(8500, lambda: (game.buy("bomb"), game.buy("potion")))
    root.after(8950, lambda: snap("7_shop_happy"))
    root.after(9200, game.leave_shop)
    root.after(9600, lambda: snap("8_shop_bye_happy"))
    # 再进一次店，一分钱不花就走 → 店长不高兴
    root.after(10200, game.open_shop)
    root.after(10600, game.leave_shop)
    root.after(10900, lambda: snap("9_shop_bye_sad"))
    root.after(11500, lambda: game.start_level(4))               # 第 5 关：随机无尽矿脉
    root.after(12000, lambda: snap("10_random_level"))
    root.after(12500, game.game_over)
    root.after(12900, lambda: snap("11_game_over"))
    root.after(13400, lambda: (setattr(game, "running", False), root.destroy()))
    root.mainloop()

    a = game.res.audio
    print("完成：共 %d 张截图，输出目录 shots/" % len(saved))
    print("      真实节奏下的音频：成功 %d 次、丢弃 %d 次、后端 %s"
          % (a.played, a.dropped, a.describe()))


if __name__ == "__main__":
    main()
