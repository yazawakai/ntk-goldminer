# -*- coding: utf-8 -*-
"""计分板：把最高分持久化到 ``data/scoreboard.json``。"""
from __future__ import annotations

import json
import os
import time

from . import config as C

MAX_ENTRIES = 8


def load():
    """读取排行榜（按分数降序，最多 MAX_ENTRIES 条）。文件损坏时返回空表。"""
    try:
        with open(C.SCORE_FILE, "r", encoding="utf-8") as fp:
            data = json.load(fp)
        rows = [r for r in data if isinstance(r, dict) and "score" in r]
    except Exception:
        rows = []
    rows.sort(key=lambda r: int(r.get("score", 0)), reverse=True)
    return rows[:MAX_ENTRIES]


def save(rows):
    """写回排行榜；目录不存在会自动创建。"""
    try:
        os.makedirs(C.DATA_DIR, exist_ok=True)
        with open(C.SCORE_FILE, "w", encoding="utf-8") as fp:
            json.dump(rows[:MAX_ENTRIES], fp, ensure_ascii=False, indent=2)
    except Exception:
        pass


def add(name, score, level, cleared):
    """插入一条成绩并返回新的排行榜。"""
    rows = load()
    rows.append({
        "name": (name or "天意爷")[:12],
        "score": int(score),
        #"level": int(level),
        #"cleared": bool(cleared),
        "date": time.strftime("%Y-%m-%d %H:%M"),
    })
    rows.sort(key=lambda r: int(r.get("score", 0)), reverse=True)
    rows = rows[:MAX_ENTRIES]
    save(rows)
    return rows


def best():
    """当前最高分。"""
    rows = load()
    return int(rows[0]["score"]) if rows else 0
