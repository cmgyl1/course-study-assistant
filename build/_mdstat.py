# -*- coding: utf-8 -*-
"""核对合并后 Markdown 的真实状态：规模、标题数、表格数、图数，以及关键检索词的出处。"""
import re
import time
from pathlib import Path

ROOT = Path(r"D:\atomcode\大学生软件")
MD = ROOT / "data" / "textbooks_md"
out = []

for md in sorted(MD.glob("*.md")):
    text = md.read_text(encoding="utf-8")
    lines = text.splitlines()
    n_head2 = sum(1 for l in lines if re.match(r"^##\s", l))
    n_head1 = sum(1 for l in lines if re.match(r"^#\s", l))
    n_head3 = sum(1 for l in lines if re.match(r"^###\s", l))
    n_tbl = sum(1 for l in lines if l.strip().startswith("|"))
    n_fig = sum(1 for l in lines if re.match(r"^!\[", l.strip()))
    n_page = sum(1 for l in lines if l.strip().startswith("<!-- page"))
    out.append("== %s ==" % md.name)
    out.append("  mtime=%s  size=%d  chars=%d  lines=%d" % (
        time.strftime("%Y-%m-%d %H:%M", time.localtime(md.stat().st_mtime)),
        md.stat().st_size, len(text), len(lines)))
    out.append("  H1=%d H2=%d H3=%d  表格行=%d  图=%d  页码标记=%d" % (
        n_head1, n_head2, n_head3, n_tbl, n_fig, n_page))

out.append("")
out.append("== 关键词出处（合并后 Markdown）==")
for kw in ["量子", "纠缠", "三次握手", "握手"]:
    hits = []
    for md in sorted(MD.glob("*.md")):
        for i, line in enumerate(md.read_text(encoding="utf-8").splitlines(), 1):
            if kw in line:
                hits.append("%s:%d  %s" % (md.stem[-2:], i, line.strip()[:70]))
    out.append("「%s」命中 %d 行" % (kw, len(hits)))
    for h in hits[:6]:
        out.append("    " + h)

(ROOT / "build" / "_mdstat.txt").write_text("\n".join(out), encoding="utf-8")
print("ok")
