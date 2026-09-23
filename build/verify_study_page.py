# -*- coding: utf-8 -*-
"""闭环验证：自学页对齐离线阅读器之后，**真实界面**里到底表现如何。

自学页已按 reader 重排（顶部检索条 + 左栏章节树 + 右栏正文/结果卡片），
所以这里的断言也整体跟着换了一轮 —— 旧版断言直接读 page.course_box /
page.index_label，UI 一改它们必然炸，而"炸"不等于"功能坏了"。

验证这些事：
  1. 后台预热是否完成（且失败会被如实显示）；
  2. 检索结果是**卡片列表**：章节卡带「命中 N 词」、片段卡带 BM25 分数与页码；
  3. 片段卡预览 ≤160 字、超长有省略号、命中词有高亮；
  4. 点卡片能跳该节原文，且左栏对应项被选中；
  5. 正文**不截断**，且段落前有 P 页号徽章；
  6. 书里没有的（"量子纠缠"）→ 如实拒答，**一张卡都不给**；
  7. 部分词命中（"双绞线 薛定谔"）→ 提示哪个词未出现；
  8. 插图渲染成可点击的 file:// 链接、图片文件真能加载、遮罩能开能关（Esc）。

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
from PySide6.QtCore import Qt, QUrl                          # noqa: E402
from PySide6.QtGui import QKeyEvent, QPixmap                       # noqa: E402
from PySide6.QtTest import QTest                             # noqa: E402

from services import study_service as ss                     # noqa: E402

COURSE = "计算机网络"
MARK_FRAGMENT = "background-color:#5A8DD6"      # 命中词高亮的底色（与 reader 同色）


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


def _cards(page) -> list:
    """结果区里的卡片控件（跳过"命中的章节 / 原文片段"这类小标题）。"""
    import main as appmain

    out = []
    for i in range(page.result_list.count()):
        w = page.result_list.itemWidget(page.result_list.item(i))
        if isinstance(w, appmain._ResultCard):
            out.append(w)
    return out


def _plain(html: str) -> str:
    """去标签 + 反解实体 + 抹掉空白 —— 用于"这段原文到底在不在渲染结果里"这种比对。

    抹空白是必要的：QTextDocument.toHtml() 会在块与块之间插空行，
    而教材原文自己也可能有折行，两边直接比字符会假失败（不是功能问题）。
    """
    text = re.sub(r"<[^>]+>", "", html or "")
    text = (text.replace("&nbsp;", " ").replace("&#160;", " ")
                .replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&"))
    return re.sub(r"\s+", "", text)


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
    page.set_course(COURSE)          # 自学页没有课程下拉框，课程由调用方带入
    ms._pump(app, 200)

    # ---------- 1. 后台预热 ----------
    state = _wait_state(app, page)
    results.append(("预热完成", state == "ready", f"state={state}"))
    win.grab().save(str(out_dir / "verify_00_index_ready.png"))

    # ---------- 2. 能查到的查询 → 卡片列表 ----------
    page.query_edit.setText("三次握手")
    page.ask()
    ms._pump(app, 400)
    win.grab().save(str(out_dir / "verify_01_query_ok.png"))
    cards = _cards(page)
    section_cards = [c for c in cards if c.badge_lab.text().startswith("命中")]
    row_cards = [c for c in cards if re.fullmatch(r"\d+\.\d{3}", c.badge_lab.text())]
    results.append(("结果渲染成卡片", bool(row_cards),
                    f"卡片 {len(cards)} 张（章节卡 {len(section_cards)} / 片段卡 "
                    f"{len(row_cards)}）"))
    hits_5 = [c for c in row_cards if "第5章" in c.toolTip()]
    results.append(("三次握手→第5章", bool(hits_5),
                    hits_5[0].title_lab.text() if hits_5 else "(未落到第5章)"))
    results.append(("卡片带分数与页码", bool(row_cards) and any(
        "页" in c.meta_lab.text() for c in row_cards),
        f"{row_cards[0].badge_lab.text()} · {row_cards[0].meta_lab.text()}"
        if row_cards else "(无片段卡)"))

    # ---------- 3. 预览长度 / 高亮 ----------
    longest = max((len(_plain(c.preview_lab.text())) for c in row_cards), default=0)
    results.append(("预览不超长且有省略号",
                    longest <= 161 and any(c.preview_lab.text().endswith("…")
                                           for c in row_cards),
                    f"最长 {longest} 字（上限 161 = 160 + 省略号）"))
    results.append(("命中词高亮", any(MARK_FRAGMENT in c.preview_lab.text()
                                      for c in row_cards),
                    f"含 {MARK_FRAGMENT} 的片段卡 "
                    f"{sum(1 for c in row_cards if MARK_FRAGMENT in c.preview_lab.text())} 张"))

    # ---------- 4. 点卡片 → 跳该节原文 + 左栏回选 ----------
    if row_cards:
        target = hits_5[0] if hits_5 else row_cards[0]
        # 点击后结果区会被清空（右栏换成正文了），控件随之销毁 ——
        # 所以标题必须在点击前先取下来，否则读的是已销毁的 C++ 对象。
        target_title = target.title_lab.text()
        QTest.mouseClick(target, Qt.LeftButton)
        ms._pump(app, 400)
        win.grab().save(str(out_dir / "verify_02_card_jump.png"))
        current = page.tree.currentItem()
        got = current.text(0) if current is not None else ""
        body = _plain(page.log_box.toHtml())
        results.append(("点卡片能跳正文", len(body) > 200 and page.right.currentWidget()
                        is page.log_box, f"正文 {len(body)} 字"))
        results.append(("左栏同步选中", got == target_title,
                        f"选中={got!r} 卡片={target_title!r}"))
        results.append(("跳转后结果区已让位", page.result_list.count() == 0,
                        f"结果区 {page.result_list.count()} 条目"))

    # ---------- 4b. 上限与角标格式对齐 reader（标题 6 / 片段 10） ----------
    page.query_edit.setText("物理层")
    page.ask()
    ms._pump(app, 400)
    win.grab().save(str(out_dir / "verify_02b_cards_capped.png"))
    cards_b = _cards(page)
    sec_b = [c for c in cards_b if c.badge_lab.text().startswith("命中")]
    row_b = [c for c in cards_b if re.fullmatch(r"\d+\.\d{3}", c.badge_lab.text())]
    results.append(("上限对齐 reader（6 / 10）",
                    0 < len(sec_b) <= 6 and 0 < len(row_b) <= 10,
                    f"章节卡 {len(sec_b)}（≤6）· 片段卡 {len(row_b)}（≤10）"))
    results.append(("章节卡角标为「命中 N 词」",
                    bool(sec_b) and all(re.fullmatch(r"命中 \d+ 词", c.badge_lab.text())
                                        for c in sec_b),
                    sec_b[0].badge_lab.text() if sec_b else "(无)"))

    # ---------- 4c. 下册章节：点树节点必须读到**下册**的原文 ----------
    # 左栏顶显示的是短标签（「计算机网络（第8版） · 下册」），拼路径时必须换回真实书名
    # ——否则 find_book 会回落成"取第一本"，点下册章节读到上册内容，**静默错**。
    stems = [page._book_stem(page.tree.topLevelItem(i))
             for i in range(page.tree.topLevelItemCount())]
    labels = [appmain._book_label(s) for s in stems]
    results.append(("左栏书名可区分上下册", len(set(labels)) == len(stems),
                    " / ".join(labels)))
    lower = next((s for s in stems if "下半" in s), "")
    book_ok, book_detail = False, f"树上找不到下册：{stems}"
    if lower:
        for i in range(page.tree.topLevelItemCount()):
            root = page.tree.topLevelItem(i)
            if page._book_stem(root) != lower:
                continue
            for j in range(min(root.childCount(), 8)):
                page.on_tree_click(root.child(j))
                ms._pump(app, 250)
                html = page.log_box.toHtml()
                if len(_plain(html)) > 200:
                    book_ok = lower in html
                    book_detail = root.child(j).text(0) + (
                        " → 读到下册" if book_ok else " → 读到的不是下册")
                    break
            break
    results.append(("下册章节读到下册原文", book_ok, book_detail))

    # ---------- 5. 正文不截断 + 段落页号徽章 ----------

    tree = ss.get_course_tree(COURSE)
    reading_ok = False
    href = ""
    if tree.success and tree.data:
        book = tree.data[0]
        for ch in book.children:
            path = f"{book.book} > {ch.title}"
            r = ss.get_section_reading(path, COURSE)
            if r.success and r.data and r.data.n_figures:
                page._show_reading(path, select=True)
                ms._pump(app, 600)
                win.grab().save(str(out_dir / "verify_03_reading_figures.png"))
                html = page.log_box.toHtml()
                # 取该节最长的一段，验证它**整段**都在渲染结果里 ——
                # 卡片预览会截到 160 字，正文绝不能跟着被截（旧版就踩过这个坑）
                paras = [b.text for b in r.data.blocks if b.kind == "para"
                         and len(b.text) > 200]
                if paras:
                    needle = re.sub(r"\s+", "", max(paras, key=len))
                    rendered = _plain(html)
                    reading_ok = needle[:60] in rendered and needle[-40:] in rendered
                m = re.search(r'href="(file:///[^"]+)"', html)
                href = m.group(1) if m else ""
                break
    rendered_now = _plain(page.log_box.toHtml())
    results.append(("正文整段未截断", reading_ok, "最长段落首尾都在渲染结果里"))
    results.append(("段落页号徽章", bool(re.search(r"P\d+", rendered_now)),
                    (re.search(r"P\d+", rendered_now) or ["(无)"])[0]))

    # ---------- 6. 书里没有的 → 必须拒答，且一张卡都不给 ----------
    page.query_edit.setText("量子纠缠")
    page.ask()
    ms._pump(app, 400)
    html2 = _plain(page.log_box.toHtml())
    win.grab().save(str(out_dir / "verify_04_query_notfound.png"))
    results.append(("量子纠缠→拒答", "未找到" in html2,
                    f"含'未找到'={'未找到' in html2}"))
    results.append(("拒答时不给任何卡片",
                    page.result_list.count() == 0 and "依据" not in html2,
                    f"结果区 {page.result_list.count()} 条目"))

    # ---------- 7. 部分词命中 → 提示未出现词 ----------
    page.query_edit.setText("双绞线 薛定谔")
    page.ask()
    ms._pump(app, 400)
    hint = page.hint_label.text()
    results.append(("提示未出现词", "薛定谔" in hint and "未出现" in hint,
                    f"hint={hint!r}"))

    # ---------- 8. 插图可点击 + 文件可加载 + 遮罩开合 ----------
    results.append(("插图渲染成可点击链接", bool(href), href[:96] or "(未找到 anchor)"))
    if href:
        path_str = QUrl(href).toLocalFile()
        pix = QPixmap(path_str)
        results.append(("图片文件可加载", not pix.isNull(),
                        f"{pix.width()}x{pix.height()}"))
        box = page._make_lightbox(path_str)
        ok_open = box is not None
        if box is not None:
            box.show()
            ms._pump(app, 200)
            ok_open = box.isVisible()
            # 直接驱动 keyPressEvent —— 离屏下 QTest.keyClick 的焦点投递不可靠，
            # 而 Esc 的处理逻辑本来就在这个方法里
            box.keyPressEvent(QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Escape,
                                        Qt.NoModifier))
            ms._pump(app, 200)
        results.append(("遮罩可开 + Esc 可关",
                        ok_open and box is not None and not box.isVisible(),
                        f"打开={ok_open}"))

    # ---------- 汇总 ----------
    print("\n===== 自学页闭环验证 =====")
    bad = 0
    for name, ok, detail in results:
        print(f"{'✓' if ok else '✗'} {name:<22} {detail}")
        bad += 0 if ok else 1
    print(f"\n{'全部通过 ✅' if not bad else f'{bad} 项未通过 ❌'}")
    print(f"截图：{out_dir}\\verify_*.png")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
