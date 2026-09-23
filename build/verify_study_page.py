# -*- coding: utf-8 -*-
"""闭环验证：自学页的新检索路径（BM25）在**真实界面**里到底表现如何。

验证五件事：
  1. 后台预热是否完成、状态标签是否如实更新；
  2. 能查到的（"三次握手"）→ 是否给出正确章节 + 页码 + **完整**原文；
  3. 书里没有的（"量子纠缠"）→ 是否**如实拒答**，而不是返回 5 条垃圾；
  4. 部分词命中（"双绞线 薛定谔"）→ 是否提示哪个词未出现；
  5. 插图是否渲染成可点击的 <a href="file://…">，且图片文件真能加载。

只读：不 submit、不写错题本、不改题库。截图落到 build/verify_*.png。
用法：python build/verify_study_page.py
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "build"))

import make_screenshots as ms                                # noqa: E402
from PySide6.QtCore import QUrl                              # noqa: E402
from PySide6.QtGui import QPixmap                            # noqa: E402

from services import study_service as ss                     # noqa: E402

COURSE = "计算机网络"


def _wait_state(app, page, timeout_ms: int = 60000) -> str:
    """等后台预热结束，返回最终状态。"""
    from PySide6.QtCore import QElapsedTimer

    t = QElapsedTimer()
    t.start()
    while t.elapsed() < timeout_ms:
        app.processEvents()
        if page._warm_state != "idle":
            return page._warm_state
    return "timeout"


def main() -> int:
    out_dir = ROOT / "build"
    results: list[tuple[str, bool, str]] = []

    app = ms._build_app()
    import main as appmain
    win = appmain.MainWindow()
    win.resize(1280, 800)
    win.show()
    win._hover_timer.stop()
    win.sidebar_wrap.setMinimumWidth(win.SIDEBAR_W)
    win.sidebar_wrap.setMaximumWidth(win.SIDEBAR_W)
    win._expanded = True
    win.nav.setCurrentRow(list(win.pages).index("自学"))
    ms._pump(app, 400)

    page = win.pages["自学"]
    page.course_box.setCurrentText(COURSE)
    page.refresh_tree()
    page.tree.setMaximumHeight(170)

    # ---------- 1. 后台预热 ----------
    state = _wait_state(app, page)
    label = page.index_label.text()
    results.append(("预热完成", state == "ready", f"state={state} label={label!r}"))
    win.grab().save(str(out_dir / "verify_00_index_ready.png"))

    # ---------- 2. 能查到的查询 ----------
    page.query_edit.setText("三次握手")
    page.ask()
    ms._pump(app, 400)
    html = page.log_box.toHtml()
    win.grab().save(str(out_dir / "verify_01_query_ok.png"))
    results.append(("三次握手→第5章", "第5章" in html and "5.9" in html,
                    f"含'第5章'={'第5章' in html} 含'5.9'={'5.9' in html}"))
    results.append(("三次握手有页码", bool(re.search(r"p2\d\d", html)),
                    (re.search(r"p\d+", html) or ["(无页码)"])[0]))
    results.append(("原文未截断", "…" not in re.sub(r"<[^>]+>", "", html)[:4000],
                    "正文里没有截断省略号"))
    results.append(("相关章节已列出", "相关章节" in html or "依据 1" in html,
                    "有依据或章节块"))

    # ---------- 3. 书里没有的 → 必须拒答 ----------
    page.query_edit.setText("量子纠缠")
    page.ask()
    ms._pump(app, 400)
    html2 = page.log_box.toHtml()
    win.grab().save(str(out_dir / "verify_02_query_notfound.png"))
    results.append(("量子纠缠→拒答", "未找到" in html2,
                    f"含'未找到'={'未找到' in html2}"))
    results.append(("拒答时不给垃圾段落", "依据 1" not in html2,
                    f"含'依据 1'={'依据 1' in html2}"))

    # ---------- 4. 部分词命中 → 提示未出现词 ----------
    page.query_edit.setText("双绞线 薛定谔")
    page.ask()
    ms._pump(app, 400)
    html3 = page.log_box.toHtml()
    results.append(("提示未出现词", "薛定谔" in html3 and "未出现" in html3,
                    f"含'未出现'={'未出现' in html3}"))

    # ---------- 5. 插图可点击 + 文件可加载 ----------
    tree = ss.get_course_tree(COURSE)
    href = ""
    if tree.success and tree.data:
        book = tree.data[0]
        for ch in book.children:
            r = ss.get_section_reading(f"{book.book} > {ch.title}", COURSE)
            if r.success and r.data and r.data.n_figures:
                rendered = ss.render_section_html(r.data)
                m = re.search(r'href="(file:///[^"]+)"', rendered)
                if m:
                    href = m.group(1)
                page.log_box.setHtml(rendered)
                ms._pump(app, 600)
                win.grab().save(str(out_dir / "verify_03_reading_figures.png"))
                break
    results.append(("插图渲染成可点击链接", bool(href), href[:96] or "(未找到 anchor)"))
    if href:
        ok_pix = not QPixmap(QUrl(href).toLocalFile()).isNull()
        pix = QPixmap(QUrl(href).toLocalFile())
        results.append(("图片文件可加载", ok_pix,
                        f"{pix.width()}x{pix.height()}"))

    # ---------- 汇总 ----------
    print("\n===== 自学页闭环验证 =====")
    bad = 0
    for name, ok, detail in results:
        print(f"{'✓' if ok else '✗'} {name:<20} {detail}")
        bad += 0 if ok else 1
    print(f"\n{'全部通过 ✅' if not bad else f'{bad} 项未通过 ❌'}")
    print(f"截图：{out_dir}\\verify_*.png")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
