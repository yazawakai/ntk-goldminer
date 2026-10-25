# -*- coding: utf-8 -*-
"""新三国黄金矿工 (New Three Kingdom Gold Miner) —— Python + tkinter 零第三方依赖实现。

模块
----
config      全局配置（窗口 / 物理 / 物品 / 关卡 / 道具）
resources   贴图与音效加载（支持自定义 PNG / WAV）
entities    钩子、物品、粒子、飘字
scoreboard  计分板持久化
game        主程序（状态机 / 主循环 / 绘制 / 玩法）
"""

__version__ = "1.0.0"
__all__ = ["config", "resources", "entities", "scoreboard", "game"]
