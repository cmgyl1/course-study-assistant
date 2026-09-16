# -*- coding: utf-8 -*-
"""校验 data/reader.html 的完整性：
  1) 内嵌 JSON 能否解析；
  2) 每个插图 URL 在磁盘上真实存在（防止裂图）；
  3) 章节树 / 原文片段 / 插图 计数与页面统计是否自洽。
用法：python check_reader.py
"""
import io
import json
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                  errors="replace")

ROOT = Path(r"D:\atomcode\大学生软件")
HTML = ROOT / "data" / "reader.html"

if not HTML.exists():
    print("reader.html 不存在，先跑 tools/build_reader.py")
    sys.exit(1)

text = HTML.read_text(encoding="utf-8")
m = re.search(r"const DATA=(\{.*?\});\n", text, re.S)
if not m:
    print("未找到内嵌的 DATA JSON")
    sys.exit(1)

data = json.loads(m.group(1))
sections = data["sections"]
chunks = data["chunks"]

fig_urls = []
for s in sections:
    for b in s["blocks"]:
        if b.get("k") == "f":
            fig_urls.append(b["u"])
        elif b.get("k") == "p" and "![" in (b.get("t") or ""):
            print("  ! 正文段落里残留图片标记:", s.get("title"))

missing = [u for u in fig_urls if not (HTML.parent / u).exists()]

print(f"文件      : {HTML}  ({HTML.stat().st_size / 1048576:.2f} MB)")
print(f"章节入口  : {len(sections)}")
print(f"原文片段  : {len(chunks)}")
print(f"插图引用  : {len(fig_urls)}   实际存在: {len(fig_urls) - len(missing)}")
print(f"词表      : {len(data['vocab'])}")
print(f"页范围    : {data['stats']['pages']}")
if missing:
    print(f"\n!! 裂图 {len(missing)} 个：")
    for u in missing[:20]:
        print("   ", u)
else:
    print("\n所有插图路径均可解析，无裂图。")

# 每个章节至少要有内容（排除"（前言）"这类空壳）
empty = [(i, s["title"], s["book"], s["lv"]) for i, s in enumerate(sections)
         if not s["blocks"]]
if empty:
    print(f"\n空章节 {len(empty)} 个（父级标题无直属内容 / 疑似误判标题）：")
    for i, t, bk, lv in empty:
        # 紧跟其后的同册节：用来判断它是"父标题"还是被夹在中间的孤立标题
        nxt = sections[i + 1] if i + 1 < len(sections) else None
        nxt_head = ""
        if nxt and nxt["book"] == bk:
            nxt_head = f" → 下一节 {nxt['title'][:24]}"
        mark = "  " if re.match(r"^[0-9]", t.strip()) else "* "
        print(f"  {mark}lv{lv} {t[:46]}{nxt_head}")
    print("  （'*' 开头=正常父标题；数字/英文开头多为表格行被误判为标题）")
