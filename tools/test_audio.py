# -*- coding: utf-8 -*-
"""音效叠加自测：验证“新音效不会打断正在播放的旧音效”。

用法：
    python tools/test_audio.py            # 依次叠放多个音效并打印声道状态
    python tools/test_audio.py --compare  # 先演示旧的 winsound 单通道行为做对比

它会检查同时处于 playing 状态的声道数量：
    MCI 多路   → 能同时 ≥ 3 路（PASS）
    winsound   → 永远只有 1 路（这是它掐断旧声音的原因）
"""
from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gm import config as C              # noqa: E402
from gm.audio import Audio              # noqa: E402

SEQUENCE = ("hook_shoot", "hook_hit", "collect", "powerup", "explosion", "level_up")


def path_of(name):
    p = os.path.join(C.SOUND_DIR, name + ".wav")
    return p if os.path.isfile(p) else None


def show(audio, title):
    active = audio.active()
    print("%-26s 正在播放 %d 路：%s" % (title, len(active), active or "—"))
    return len(active)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--compare", action="store_true", help="顺便演示 winsound 单通道的对比")
    ap.add_argument("--gap", type=float, default=0.06, help="每个音效之间的间隔秒数")
    args = ap.parse_args()

    missing = [n for n in SEQUENCE if not path_of(n)]
    if missing:
        print("缺少音效文件：%s（先跑 python tools/make_default_assets.py）" % ", ".join(missing))
        return 1

    print("=" * 66)
    audio = Audio(voices=C.AUDIO_VOICES, volume=C.AUDIO_VOLUME, backend="auto")
    print("音频后端：%s" % audio.describe())
    if audio.backend != "mci":
        print("注意：这台机器用不了 MCI 多路播放，下面的并发数会是 1（已降级）。")
    print("-" * 66)

    peak = 0
    for i, name in enumerate(SEQUENCE):
        audio.play(path_of(name))
        time.sleep(args.gap)
        peak = max(peak, show(audio, "播放 %d：%s" % (i + 1, name)))
    peak = max(peak, show(audio, "全部叠放后"))
    print("-" * 66)
    print("播放成功 %d 次，因声道满丢弃 %d 次，峰值并发 %d 路"
          % (audio.played, audio.dropped, peak))
    print("结论：%s" % ("PASS —— 多个音效可以同时响，新音效不会打断旧音效 ✅"
                        if peak >= 2 else "FAIL —— 同时只有 1 路，请检查音频设备 / 后端设置"))

    if args.compare:
        print("-" * 66)
        try:
            import winsound
        except Exception:
            print("非 Windows，跳过 winsound 对比")
        else:
            print("对比：winsound 单通道连播同样 3 个音效（听感上后一个会掐掉前一个）")
            for name in SEQUENCE[:3]:
                winsound.PlaySound(path_of(name),
                                   winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
                time.sleep(args.gap)
            time.sleep(0.6)
    audio.close()
    print("=" * 66)
    return 0


if __name__ == "__main__":
    sys.exit(main())
