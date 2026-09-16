# -*- coding: utf-8 -*-
"""把 data/figures/ 根目录的早期实验产物归档到 build/fig_experiments/。

不删除 —— 这些是第 2 章图区定位实验（exp_figures1..3）的输出，可能有参考价值；
但它们和正式产物（data/figures/<书名>/）混在同一层，翻目录时极易被误导。
"""
import shutil
from pathlib import Path

ROOT = Path(r"D:\atomcode\大学生软件")
SRC = ROOT / "data" / "figures"
DST = ROOT / "build" / "fig_experiments"

KEEP_DIRS = {"计算机网络（第8版）_谢希仁_上半", "计算机网络（第8版）_谢希仁_下半"}

DST.mkdir(parents=True, exist_ok=True)
moved, kept = [], []
for p in sorted(SRC.iterdir()):
    if p.is_dir():
        if p.name not in KEEP_DIRS:
            kept.append("保留未识别目录: " + p.name)
        continue
    target = DST / p.name
    if target.exists():
        kept.append("目标已存在，跳过: " + p.name)
        continue
    shutil.move(str(p), str(target))
    moved.append(p.name)

report = ["已归档 %d 个文件 → %s" % (len(moved), DST)]
report += ["  " + m for m in moved]
report += kept
(ROOT / "build" / "_figarchive.txt").write_text("\n".join(report), encoding="utf-8")
print("\n".join(report))
