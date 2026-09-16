# -*- coding: utf-8 -*-
"""验证 UI 链路：知识树 → 章节保序原文 → HTML（含插图/表格）。

输出：build/_uicheck.txt
"""
import sys
from pathlib import Path

ROOT = Path(r"D:\atomcode\大学生软件")
sys.path.insert(0, str(ROOT / "src"))

from services import study_service as ss          # noqa: E402

lines = []

tree = ss.get_course_tree("计算机网络")
lines.append("知识树: success=%s  message=%s" % (tree.success, tree.message))
if tree.success and tree.data:
    for root in tree.data:
        lines.append("  书: %s（%d 个一级节点）" % (root.book, len(root.children)))
        for c in root.children[:6]:
            lines.append("     - %s" % c.title)

# 从树里找一个"有小结点的章节"，拼出完整路径
target = None
if tree.success and tree.data:
    root = tree.data[0]
    if root.children:
        first = root.children[0]
        target = "%s > %s" % (root.book, first.title)
        lines.append("")
        lines.append("测试章节路径: %s" % target)

if target:
    r = ss.get_section_reading(target, "计算机网络")
    lines.append("get_section_reading: success=%s  message=%s" % (r.success, r.message))
    if r.success and r.data:
        rd = r.data
        lines.append("  book=%s  blocks=%d  figures=%d" % (rd.book, len(rd.blocks), rd.n_figures))
        from collections import Counter
        lines.append("  块类型分布: %s" % dict(Counter(b.kind for b in rd.blocks)))
        for i, b in enumerate(rd.blocks[:14]):
            if b.kind == "figure":
                exists = Path(b.url).exists() if b.url else False
                lines.append("   [%02d] 图  p%s  文件存在=%s  %s" % (i, b.page, exists, Path(b.url).name if b.url else ""))
            elif b.kind == "table":
                lines.append("   [%02d] 表  p%s  %d 行" % (i, b.page, len(b.text.splitlines())))
            elif b.kind == "heading":
                lines.append("   [%02d] 标题(L%d) p%s  %s" % (i, b.level, b.page, b.text[:40]))
            else:
                lines.append("   [%02d] 段落%s p%s  %s" % (
                    i, "（图题）" if b.is_caption else "", b.page, b.text[:40]))

        html = ss.render_section_html(rd)
        lines.append("")
        lines.append("HTML 长度=%d，头部 900 字符：" % len(html))
        lines.append(html[:900])

(ROOT / "build" / "_uicheck.txt").write_text("\n".join(lines), encoding="utf-8")
print("ok")
