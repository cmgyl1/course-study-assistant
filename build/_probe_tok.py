# -*- coding: utf-8 -*-
"""实测：几个疑难查询的切分结果与各词在全库的 DF。"""
import sys
from pathlib import Path

ROOT = Path(r"D:\atomcode\大学生软件")
sys.path.insert(0, str(ROOT / "src"))

from engine import textbook_reader as reader
from engine.retrieval import Retriever, build_from_markdown_files, tokenize

QUERIES = ["量子纠缠", "双绞线 薛定谔", "为什么不直接用两次握手", "物理层",
           "OSI 七层模型", "三次握手", "拥塞控制", "TCP 拥塞控制"]

mds = reader.list_books("计算机网络")
r = Retriever(build_from_markdown_files(mds, course="计算机网络"))

lines = ["语料: %s" % r.stats(), ""]
for q in QUERIES:
    toks = tokenize(q)
    dfs = [(t, r.bm25.df.get(t, 0)) for t in toks]
    res = r.search(q, top_k=3)
    lines.append("Q: %s" % q)
    lines.append("  tokens=%s" % toks)
    lines.append("  DF=%s" % dfs)
    lines.append("  status=%s rounds=%s" % (res["status"], res["relax_rounds"]))
    lines.append("  sections=%s" % [s["section_path"][:40] for s in res["sections"][:3]])
    lines.append("  msg=%s" % res["message"][:80])
    lines.append("")

(ROOT / "build" / "_tok.txt").write_text("\n".join(lines), encoding="utf-8")
print("ok")
