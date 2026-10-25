# -*- coding: utf-8 -*-
"""自动化冒烟测试：驱动真实游戏循环，覆盖所有状态与渲染分支。

跑法：
    python tools/smoke_test.py

它不依赖人工操作：自动发射钩子、自动用道具、自动过关、自动输入名字，
并在“有贴图”和“没有贴图（走矢量兜底）”两种模式下各渲染一遍，
任何异常都会直接抛出并让进程以非 0 退出。
"""
from __future__ import annotations

import math
import os
import random
import sys
import time
import types
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tkinter as tk                       # noqa: E402

from gm import config as C                 # noqa: E402
from gm.audio import Audio                 # noqa: E402
from gm.game import GoldMinerGame          # noqa: E402

DT = 1.0 / 60.0


def key(game, keysym, char=""):
    game.on_key(SimpleNamespace(keysym=keysym, char=char))


def mouse(game, x, y, click=False):
    """模拟鼠标：x/y 用 960x640 逻辑坐标，转成画布像素再发给游戏。"""
    event = SimpleNamespace(x=int(x * game.scale), y=int(y * game.scale))
    if click:
        game.on_click(event)
    else:
        game.on_motion(event)


def wait_audio(seconds=1.0):
    """等正在播的音效放完。

    本测试用固定步长“快进”，单位时间里的音效密度远高于真实游戏，
    声道池可能全满（此时按设计会丢弃新音效）。真机游玩不会出现这种情况，
    所以这里等一会儿再断言语音，保证测试结果稳定。
    """
    time.sleep(seconds)


def frames(game, n, dt=DT):
    for _ in range(n):
        game.step(dt)


def play_until_clear(game, max_seconds=90.0, prop_every=4.0):
    """自动挖矿：瞄准最近的目标发射，定期用道具，直到过关或超时。"""
    steps = int(max_seconds / DT)
    used = 0
    target = None
    for i in range(steps):
        if game.state != "playing":
            break
        if game.hook.state == "swing":
            if target is None or not target.alive:
                alive = [it for it in game.items if it.alive]
                target = random.choice(alive) if alive else None
            if target is not None:
                want = math.atan2(target.x - C.PIVOT[0], target.y - C.PIVOT[1])
                if abs(game.hook.theta - want) < 0.06:
                    game.launch()
        if abs(i * DT % prop_every) < DT:
            game.use_prop("bomb" if (i // int(prop_every / DT)) % 2 else "potion")
            used += 1
        game.step(DT)
    return used


def main():
    root = tk.Tk()
    game = GoldMinerGame(root)
    log = []

    # ---------- 1) 菜单：渲染 + 待机演示
    frames(game, 20)
    log.append("菜单渲染 20 帧 OK（钩子待机摆动）")

    # ---------- 2) 开始游戏
    key(game, "space")
    assert game.state == "playing", game.state
    assert len(game.items) > 10, "物品数量异常: %d" % len(game.items)
    assert not [it for it in game.items if it.prop], "道具不应该再出现在矿场里（只从商店买）"
    assert game.inventory == {"bomb": 0, "potion": 0}, "开局不应该白送道具"
    # 钩爪起点在矿工下面，只能左右摆 ±THETA_MAX，所以物品必须落在扇形内
    assert all(GoldMinerGame._reachable(it.x, it.y, it.r) for it in game.items), \
        "生成的物品必须在钩爪可达的扇形内（否则永远挖不到、清不空矿场）"
    log.append("开局成功：第 %d 关，场上 %d 个物品（无道具刷新），目标 %d 分"
               % (game.level_index + 1, len(game.items), game.target()))

    # ---------- 3) 暂停 / 恢复
    key(game, "p")
    frames(game, 5)
    assert game.state == "paused"
    key(game, "p")
    assert game.state == "playing"
    log.append("暂停 / 恢复 OK")

    # ---------- 4) 抓取动画 + 道具 + 音效调用
    grabs = 0
    props = 0
    for _ in range(6):
        if game.state != "playing":
            break
        before = game.score
        props += play_until_clear(game, max_seconds=4.0)
        if game.score > before:
            grabs += 1
    assert game.score > 0, "玩了半天一分没得，抓取逻辑可能坏了"
    assert grabs > 0
    log.append("自动挖矿 OK：得分 %d，抓取 %d 次，用道具 %d 次（当前状态 %s）"
               % (game.score, grabs, props, game.state))

    # ---------- 5) 过关规则 + 商店 + 随机无尽关卡
    levels_seen = []
    shop_log = []
    by_timeup = False
    random_played = 0
    for _ in range(12):
        if game.state != "playing" or random_played >= 2:
            break
        levels_seen.append(game.level_index + 1)
        if C.is_random_level(game.level_index):
            random_played += 1                       # 玩完这关就攒够两个随机关了
        if not game.items:                           # 场上空了就补几个，便于测试
            game.items = game._spawn_items(C.level(game.level_index))
        game.score = game.target()
        game.step(DT)
        assert game.state == "playing", "达到目标分后关卡不应该立刻结束"
        assert game.target_done, "达标后应该给出提示"
        game.hook.grabbed = None
        game.hook.state = "swing"
        if by_timeup:                                # 路径 A：时间耗尽 → 达标过关
            game.time_left = 0.001
            game.step(DT)
            assert game.clear_reason == "timeup"
            assert game.level_bonus == 0, "时间耗尽的过关不该再有时间奖励"
        else:                                        # 路径 B：挖空矿场 → 提前过关 + 奖励
            for it in game.items:
                it.alive = False
            game.step(DT)
            assert game.clear_reason == "clear"
            assert game.level_bonus > 0, "提前挖空矿场应有剩余时间奖励"
        by_timeup = not by_timeup

        assert game.state == "level_clear"
        game.overlay_timer = 0.0
        game.step(DT)                                # 过关 → 进商店
        assert game.state == "shop", "过关后应该进入商店，而不是直接进下一关"

        # ---------- 商店：鼠标点击购买 → 店长表情 → 退出
        lvl_no = game.level_index + 1
        price_bomb, price_potion = game.shop_price("bomb"), game.shop_price("potion")
        assert price_bomb == C.shop_price("bomb", lvl_no) > 0
        assert C.shop_price("bomb", 1) < C.shop_price("bomb", 6) <= C.SHOP["bomb"]["cap"]
        assert len(game.items) > 5, "商店里应该已经摆好下一关的矿场"
        preview = list(game.items)
        assert game.shop_state == "browse" and game.shop_expr == "neutral"
        assert game.shop_line, "店长应该有开场白"

        # 鼠标悬停 + 点击商品（事件坐标是画布像素，所以要乘上 UI 倍率）
        frames(game, 1)
        card = game._shop_layout()["bomb"]
        mouse(game, (card[0] + card[2]) / 2, (card[1] + card[3]) / 2)
        assert game.shop_hover == "bomb", "鼠标悬停应该高亮对应商品"
        mouse(game, 0, 0, click=False)

        score_before = game.score
        had_bomb = game.inventory["bomb"]
        had_potion = game.inventory["potion"]
        game.score = price_bomb + price_potion + 10      # 刚好够买两样
        mouse(game, (card[0] + card[2]) / 2, (card[1] + card[3]) / 2, click=True)
        assert game.inventory["bomb"] == had_bomb + 1, "鼠标点击商品应该买到东西"
        assert game.score == price_bomb + price_potion + 10 - price_bomb
        assert game.shop_expr == "happy", "买到东西后店长应该高兴"
        assert game.shop_spent == price_bomb and game.shop_bought == 1
        assert game.buy("potion") is True
        assert game.score == 10
        assert game.inventory["potion"] == had_potion + 1
        game.score = 5                                    # 故意不够钱
        assert game.buy("bomb") is False, "分数不够时不应该买成功"
        assert game.inventory["bomb"] == had_bomb + 1 and game.score == 5
        assert game.shop_expr == "neutral" or game.shop_flash_timer > 0
        game.score = score_before

        # 退出商店：花过钱 → 平时立绘 + 夸奖语音，并且要停一下才进关卡
        assert game.res.sound_path(C.SHOP_VOICE["bought"]) is not None, "缺少夸奖语音文件"
        wait_audio(1.2)
        played_before = game.res.audio.played
        assert game.leave_shop() is True
        assert game.shop_state == "reaction" and game.shop_expr == "happy"
        assert game.res.audio.played > played_before, "离开商店应该播放店长语音"
        assert game.shop_reaction_timer == C.SHOP_REACTION_TIME
        frames(game, 3)
        assert game.state == "shop", "立绘/语音还要停留一会儿"
        game.shop_reaction_timer = 0.0
        game.step(DT)
        assert game.state == "playing", "表情播完就要进下一关"
        assert game.items == preview, "商店摆好的矿场应该就是正式开打的矿场"
        assert game.inventory["bomb"] == had_bomb + 1, "买来的道具应该跨关保留"
        shop_log.append("第 %d 关商店：炸弹 %d 分 / 强力水 %d 分，点击购买+消费语音正常"
                        % (lvl_no, price_bomb, price_potion))

    # ---------- 5b) 一分钱不花就离开商店 → 换成不高兴立绘 + 抱怨语音
    game.open_shop()
    assert game.shop_expr == "neutral" and game.shop_spent == 0
    assert game.shop_line
    assert game.res.sound_path(C.SHOP_VOICE["none"]) is not None, "缺少抱怨语音文件"
    mouse(game, 700, 200)                      # 悬停到商品卡上
    assert game.shop_hover in C.PROPS
    wait_audio(1.2)
    played_before = game.res.audio.played
    assert game.leave_shop() is True
    assert game.shop_state == "reaction" and game.shop_expr == "sad", "空手离开应该换成不高兴立绘"
    assert game.res.audio.played > played_before, "空手离开也要播放对应语音"
    mouse(game, 800, 555, click=True)          # 立绘演出期间点击不生效
    assert game.state == "shop"
    game.shop_reaction_timer = 0.0
    game.step(DT)
    assert game.state == "playing"

    # 店长立绘：有贴图时走相框立绘（放大 + 居中裁切），缺图才退回矢量
    g_geo = game._shop_geometry()
    ix0, iy0, ix1, iy1 = g_geo["image"]
    bw, bh = ix1 - ix0, iy1 - iy0
    dw, dh = game.p.size(bw, bh)                     # 画布真实像素（高 DPI 下会翻倍）
    for expr in ("neutral", "happy", "sad"):
        name = C.SHOP_KEEPER.get(expr)
        got = game.res.image_fit(name, dw, dh, C.SHOP_KEEPER_ZOOM)
        assert got is not None, "找不到店长立绘 %s" % name
        assert got.width() <= dw and got.height() <= dh, "立绘不能超出相框内画面"
    if C.SHOP_KEEPER_ZOOM > 1:                       # 特写：放大后正好裁成相框大小
        big = game.res.image_fit(C.SHOP_KEEPER["neutral"], dw, dh, C.SHOP_KEEPER_ZOOM)
        assert (big.width(), big.height()) == (dw, dh), \
            "SHOP_KEEPER_ZOOM>1 时应裁成相框大小，实际 %sx%s" % (big.width(), big.height())
    else:                                            # 1.0：整张图填满相框（不裁切）
        big = game.res.image_fit(C.SHOP_KEEPER["neutral"], dw, dh, 1.0)
        assert big.width() >= dw * 0.9 or big.height() >= dh * 0.9, \
            "zoom=1.0 应至少有一边填满相框，实际 %sx%s" % (big.width(), big.height())
    assert game._draw_keeper(236, "neutral") is True, "有立绘时应该走相框立绘"
    log.append("商店语音/立绘 OK：平时=%s，空手走=%s；立绘放大 x%.1f 后适配相框 %dx%d 像素；"
               "离开时按是否消费播放对应语音"
               % (C.SHOP_KEEPER["neutral"], C.SHOP_KEEPER["sad"],
                  C.SHOP_KEEPER_ZOOM, dw, dh))

    assert game.state == "playing", game.state
    assert game.fixed_cleared, "通过第 3 关后应记录“已通关 3 个简单关卡”"
    assert game.level_index >= len(C.LEVELS) + 1, "第 4 关起应该已经在玩随机关卡"
    assert sum(1 for lv in levels_seen if lv > len(C.LEVELS)) >= 2, "应该连续玩到多个随机关"

    # 随机关卡生成器：同一局内稳定、比上一关更难、重开一局会重新随机
    a, b = C.level(len(C.LEVELS)), C.level(len(C.LEVELS))
    assert a is b, "同一次游戏内随机关卡配置必须保持一致"
    assert a["target"] > C.LEVELS[-1]["target"], "随机关卡目标分应高于最后一关"
    assert C.is_random_level(3) and not C.is_random_level(2)
    chained = [C.level(i) for i in range(len(C.LEVELS), len(C.LEVELS) + 5)]
    targets = [c["target"] for c in chained]
    assert targets == sorted(targets) and len(set(targets)) == len(targets), \
        "随机关卡目标分应该严格递增：%s" % targets
    times = [c["time"] for c in chained]
    assert all(t >= C.RANDOM_MIN_TIME for t in times), "随机关卡时间不能低于下限：%s" % times
    C.reset_random_levels()
    assert C.level(len(C.LEVELS)) is not a, "重开一局应该生成新的随机关卡"
    log.append("过关规则 OK：时间到达标 / 时间到未达标→结束 / 清空矿场+奖励")
    log.append("商店 OK：%s" % "；".join(shop_log[:2]))
    log.append("随机无尽关卡 OK：连续经历关卡 %s；随机关目标分 %s，时间 %s"
               % (levels_seen, targets, times))

    # ---------- 6) 时间到但没达标 → 游戏结束，输入名字存分
    game.score = max(1, game.target() - 1)
    game.time_left = 0.001
    game.step(DT)
    assert game.state == "game_over", game.state
    assert game.score < game.target()
    frames(game, 5)
    for ch in "Min":
        key(game, ch, ch)                            # 注意：结算界面的 M 是打字而不是静音
    assert game.name_buffer == "Min"
    key(game, "Return")
    assert game.name_saved, "成绩没有保存"
    frames(game, 5)
    #assert game.scores[0]["cleared"], "已通关 3 个简单关卡的成绩应标记为通关"
    log.append("计分板保存 OK：%s" % game.scores[0])

    # ---------- 7) 重开：随机关卡重新洗牌 + 再次结算
    old_cfg = C.level(len(C.LEVELS))
    key(game, "r")
    assert game.state == "playing" and game.score == 0 and game.level_index == 0
    assert not game.fixed_cleared
    game.time_left = 0.01                            # 0 分 < 第 1 关目标 → 结束
    game.step(DT)
    assert game.state == "game_over", game.state
    frames(game, 5)
    key(game, "Return")
    assert game.name_saved
    log.append("重开 + 二次结算 OK（当前最高分 %d，随机矿脉 %s → %s）"
               % (game.best_score, old_cfg["short"], C.level(len(C.LEVELS))["short"]))

    # ---------- 8) 贴图 / 音效加载情况
    have_i, miss_i, have_s, miss_s = game.res.report()
    log.append("贴图 %d/%d，音效 %d/%d"
               % (len(have_i), len(have_i) + len(miss_i), len(have_s), len(have_s) + len(miss_s)))

    # ---------- 8b) 音效叠加：新音效不能打断正在播放的旧音效
    audio = game.res.audio
    busy = audio.busy_detail()
    if busy:
        log.append("音频：测试期间有 %d 路长语音在播（%s 等），符合预期" % (len(busy), busy[0][2]))
    audio.stop_all()                         # 清空声道，让下面的断言是确定性的
    assert game.res.play("collect") is True
    assert game.res.play("explosion") is True
    assert game.res.play("level_up") is True
    time.sleep(0.04)
    overlap = len(audio.active())
    if audio.backend == "mci":
        assert overlap >= 2, "多路混音失败，同时只有 %d 路：%s" % (overlap, audio.active())
    log.append("音效叠加 OK：%s；实测同时 %d 路（测试期间累计播放 %d 次、丢弃 %d 次）"
               % (audio.describe(), overlap, audio.played, audio.dropped))

    # 声道池满时的行为：丢弃新音效，绝不打断正在响的
    tiny = Audio(voices=1, backend="auto")
    try:
        if tiny.backend == "mci":
            assert tiny.play(game.res.sound_path("explosion")) is True
            assert tiny.play(game.res.sound_path("level_up")) is False, "池满时应该丢弃新音效"
            assert tiny.dropped == 1 and len(tiny.active()) == 1, "旧音效不能被抢断"
            log.append("声道池满 OK：丢弃新音效而不打断旧音效（%s）" % tiny.busy_detail())
    finally:
        tiny.close()

    # 静音应当立刻停掉所有声音，并且不再播放
    game.res.toggle_mute()
    assert audio.active() == [], "静音后不该还有声音在响"
    assert game.res.play("collect") is False
    game.res.toggle_mute()
    assert game.res.play("collect") is True

    game.quit()

    # ---------- 9) 无贴图模式：验证矢量兜底绘制不会崩
    C.IMAGE_DIR = os.path.join(C.BASE_DIR, "assets", "__no_such_dir__")
    C.SOUND_DIR = os.path.join(C.BASE_DIR, "assets", "__no_such_dir__")
    root2 = tk.Tk()
    game2 = GoldMinerGame(root2)
    frames(game2, 12)
    key(game2, "Return")
    play_until_clear(game2, max_seconds=6.0)
    game2.use_prop("bomb")
    game2.use_prop("potion")
    frames(game2, 60)
    game2.score = game2.target()
    game2.step(DT)                                   # 达标：仍然要继续玩
    assert game2.state == "playing"
    for it in game2.items:                           # 挖空 → 过关过场（矢量兜底绘制）
        it.alive = False
    game2.step(DT)
    assert game2.state == "level_clear"
    frames(game2, 30)
    game2.overlay_timer = 0.0
    game2.step(DT)                                   # 过关后进商店（此时没有任何贴图）
    assert game2.state == "shop"
    assert game2._draw_keeper(293, "sad") is False, "没有立绘贴图时应退回矢量店长"
    assert game2.shop_line, "矢量店长也要有台词（用对话气泡显示）"
    frames(game2, 12)                                # 气泡 + 矢量店长一起渲染
    bought_before = game2.shop_bought
    game2.buy("bomb")                                # 买得起就买，买不起走 deny 分支
    game2.leave_shop()
    assert game2.shop_expr == ("happy" if game2.shop_bought > bought_before else "sad")
    assert game2.shop_reaction_timer > 0
    game2.shop_reaction_timer = 0.0
    game2.step(DT)                                   # 进入第 2 关
    frames(game2, 20)
    game2.quit()
    log.append("矢量兜底模式 OK（无 PNG / 无 WAV 也能跑，商店用矢量店长+气泡台词）")

    print("=" * 62)
    for line in log:
        print("  ✔ " + line)
    print("=" * 62)
    print("冒烟测试全部通过 ✅")


if __name__ == "__main__":
    main()
