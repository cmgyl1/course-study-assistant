# -*- coding: utf-8 -*-
"""离屏实测：QTextBrowser 能否真的把教材插图加载出来。

"HTML 里有 <img src=...>" 不等于 UI 上能看见 —— 只有 Qt 真的把资源读进 QImage
才算数。这里直接问 QTextDocument 要图片资源，返回非空 QImage 才算通过。
输出：build/_qtcheck.txt
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(r"D:\atomcode\大学生软件")
sys.path.insert(0, str(ROOT / "src"))

lines = []
try:
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QTextDocument
    from PySide6.QtWidgets import QApplication, QTextBrowser
except Exception as e:                                    # noqa: BLE001
    (ROOT / "build" / "_qtcheck.txt").write_text(
        "PySide6 不可用：%r" % (e,), encoding="utf-8")
    print("no qt")
    raise SystemExit(0)

from services import study_service as ss                  # noqa: E402

app = QApplication([])

tree = ss.get_course_tree("计算机网络")
if not (tree.success and tree.data):
    lines.append("知识树不可用")
else:
    book = tree.data[0]
    # 逐章找第一个含插图的章节
    target = None
    for ch in book.children:
        t = "%s > %s" % (book.book, ch.title)
        r = ss.get_section_reading(t, "计算机网络")
        if r.success and r.data and r.data.n_figures:
            target, reading = t, r.data
            break
    if not target:
        lines.append("未找到含插图的章节")
    else:
        lines.append("章节：%s" % target)
        lines.append("块数 %d / 图 %d" % (len(reading.blocks), reading.n_figures))
        html = ss.render_section_html(reading)
        lines.append("HTML 长度 %d" % len(html))

        browser = QTextBrowser()
        browser.setHtml(html)
        doc = browser.document()
        lines.append("文档块数 %d（QTextDocument）" % doc.blockCount())

        fig_urls = [b.url for b in reading.blocks if b.kind == "figure" and b.url]
        ok = 0
        for u in fig_urls[:10]:
            res = doc.resource(QTextDocument.ResourceType.ImageResource, QUrl.fromLocalFile(u))
            img = res if hasattr(res, "isNull") else None
            loaded = bool(img) and not img.isNull() and img.width() > 0
            ok += loaded
            lines.append("   %s  加载=%s  %sx%s" % (
                Path(u).name, loaded,
                img.width() if img else "-", img.height() if img else "-"))
        lines.append("")
        lines.append("抽样 %d 张，Qt 实际加载成功 %d 张" % (len(fig_urls[:10]), ok))
        lines.append("结论：%s" % ("✅ UI 里图片可正常显示" if ok else "❌ 图片未加载"))

(ROOT / "build" / "_qtcheck.txt").write_text("\n".join(lines), encoding="utf-8")
print("ok")
