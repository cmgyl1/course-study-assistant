# -*- coding: utf-8 -*-
"""列出插图目录与 OCR 缓存状态，写 build/_figlist.txt。"""
import pathlib

ROOT = pathlib.Path(r"D:\atomcode\大学生软件")
lines = []

fig = ROOT / "data" / "figures"
lines.append("== data/figures ==")
for p in sorted(fig.iterdir()):
    if p.is_dir():
        lines.append("DIR   %s  %d png" % (p.name, len(list(p.glob("*.png")))))
    else:
        lines.append("FILE  %s  %d bytes" % (p.name, p.stat().st_size))

lines.append("")
lines.append("== data/ocr_cache ==")
cache = ROOT / "data" / "ocr_cache"
if cache.exists():
    for p in sorted(cache.iterdir()):
        lines.append("%s  %d json" % (p.name, len(list(p.glob("*.json")))))
else:
    lines.append("(不存在)")

(ROOT / "build" / "_figlist.txt").write_text("\n".join(lines), encoding="utf-8")
print("ok")
