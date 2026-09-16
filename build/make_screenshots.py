# -*- coding: utf-8 -*-
"""离屏生成界面截图 → docs/images/*.png（供 README 引用）。

为什么要离屏：本机是无人值守环境，没有可用显示器，直接 show() 抓不到画面。
QT_QPA_PLATFORM=offscreen 下 Qt 仍然完整走一遍布局与绘制，grab() 拿到的
就是真界面，不是"模拟图"。

**只读保证**：本脚本只调用各页面的 refresh/start/outline 这类"读数据"方法，
不调用 submit / self_check / finish，因此**不会写入错题本、不会改动题库**。

用法：
    python build/make_screenshots.py            # 生成全部 6 张
    python build/make_screenshots.py 首页 自学   # 只生成指定页
"""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from PySide6.QtCore import QElapsedTimer                     # noqa: E402
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette   # noqa: E402
from PySide6.QtWidgets import QApplication                    # noqa: E402

from engine.config import COURSES, ensure_data_dirs            # noqa: E402
from ui.style import DARK_PALETTE, STYLE                       # noqa: E402

OUT_DIR = ROOT / "docs" / "images"
WIN_W, WIN_H = 1280, 800
COURSE = "计算机网络"          # 当前唯一跑完全流水线的课程

# offscreen 平台不会去扫系统字体目录，不显式注册的话中文全是"豆腐块"。
# 这几个 face 覆盖了 style.py 里 QSS 声明的 "Microsoft YaHei UI" 等族名。
FONT_DIR = Path("C:/Windows/Fonts")
FONT_FILES = ("msyh.ttc", "msyhbd.ttc", "msyhl.ttc",
              "deng.ttf", "simhei.ttf", "simsun.ttc", "seguiemj.ttf")

# 页面 → 输出文件名
PAGES = {
    "首页": "01-home.png",
    "资料管理": "02-materials.png",
    "自学": "03-study.png",
    "刷题": "04-practice.png",
    "错题本": "05-wrongbook.png",
    "期末冲刺": "06-finals.png",
}


def _pump(app: QApplication, ms: int = 0) -> None:
    """跑事件循环 ms 毫秒（ms=0 时只跑一轮）。"""
    if ms <= 0:
        app.processEvents()
        return
    t = QElapsedTimer()
    t.start()
    while t.elapsed() < ms:
        app.processEvents()


def _register_fonts() -> None:
    """把中文字体塞进 Qt 字体库（offscreen 下必须先做这一步）。"""
    for fn in FONT_FILES:
        p = FONT_DIR / fn
        if p.exists():
            QFontDatabase.addApplicationFont(str(p))
    fams = QFontDatabase.families()
    hit = [f for f in fams if "YaHei" in f or "雅黑" in f]
    print("字体库已注册 %d 族；雅黑命中：%s" % (len(fams), hit or "无"))


def _build_app() -> QApplication:
    """复刻 src/main.py 的 QApplication 初始化（样式 + 深色 palette）。"""
    ensure_data_dirs()
    app = QApplication.instance() or QApplication([])
    _register_fonts()
    app.setFont(QFont("Microsoft YaHei UI", 9))
    pal = QPalette()
    for role, key in (
        (QPalette.Window, "window"),
        (QPalette.WindowText, "windowText"),
        (QPalette.Base, "base"),
        (QPalette.AlternateBase, "alternateBase"),
        (QPalette.Text, "text"),
        (QPalette.Button, "button"),
        (QPalette.ButtonText, "buttonText"),
        (QPalette.Highlight, "highlight"),
        (QPalette.HighlightedText, "highlightedText"),
        (QPalette.Link, "link"),
        (QPalette.PlaceholderText, "placeholderText"),
    ):
        pal.setColor(role, QColor(DARK_PALETTE[key]))
    app.setPalette(pal)
    app.setStyleSheet(STYLE)
    return app


def main() -> int:
    wanted = sys.argv[1:] or list(PAGES)
    unknown = [w for w in wanted if w not in PAGES]
    if unknown:
        print("未知页面：%s（可选：%s）" % (unknown, " / ".join(PAGES)))
        return 2

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    app = _build_app()

    import main as appmain                       # src/main.py（同目录已入 sys.path）
    win = appmain.MainWindow()
    win.resize(WIN_W, WIN_H)
    win.show()

    # --- 展开侧栏：默认是收起的（宽度 0），截图里必须能看到导航 ---
    # 直接定宽，绕开 QPropertyAnimation（离屏下动画推进不可靠）；同时停掉
    # 鼠标悬停轮询，否则它会把侧栏又收回去。
    win._hover_timer.stop()
    win.sidebar_wrap.setMinimumWidth(win.SIDEBAR_W)
    win.sidebar_wrap.setMaximumWidth(win.SIDEBAR_W)
    win._expanded = True
    _pump(app, 300)

    results = []
    for name in wanted:
        row = list(PAGES).index(name)
        page = win.pages[name]
        print("→ %s" % name)
        try:
            # ---- 各页灌入真实内容（全部只读）----
            if name == "首页":
                page.refresh()
            elif name == "自学":
                page.course_box.setCurrentText(COURSE)
                page.refresh_tree()
                # 树占 2/3 高度会把原文挤没，截图时压扁它，让"内嵌插图原文"露出来
                page.tree.setMaximumHeight(170)
                _fill_study_reading(app, page)
            elif name == "刷题":
                page.course_box.setCurrentText(COURSE)
                page.type_box.setCurrentText("选择题")
                page.count_spin.setValue(10)
                page.start()
            elif name == "错题本":
                page.refresh()
            elif name == "期末冲刺":
                page.course_box.setCurrentText(COURSE)
                page.outline()
        except Exception:                        # noqa: BLE001
            traceback.print_exc()
            results.append((name, "内容准备失败（截静态界面）"))

        win.nav.setCurrentRow(row)
        _pump(app, 600)                          # 等淡入动画(220ms)+图片解码

        path = OUT_DIR / PAGES[name]
        pix = win.grab()
        if not pix.save(str(path)):
            results.append((name, "❌ 保存失败"))
            continue
        results.append((name, "✓ %s (%dx%d, %.0f KB)" % (
            PAGES[name], pix.width(), pix.height(),
            path.stat().st_size / 1024)))

    print("\n===== 截图结果 =====")
    for name, msg in results:
        print("%-6s %s" % (name, msg))
    print("输出目录：%s" % OUT_DIR)
    return 0


def _fill_study_reading(app: QApplication, page) -> None:
    """在自学页灌入"第一个含插图的章节"，复刻 on_tree_click 的渲染分支。

    不直接调 on_tree_click，是因为它需要一个真实的 QTreeWidgetItem；
    这里直接走 service 层，效果等价且不依赖树的展开状态。
    """
    from services import study_service as ss

    tree = ss.get_course_tree(COURSE)
    if not (tree.success and tree.data):
        return
    book = tree.data[0]
    for ch in book.children:
        path = "%s > %s" % (book.book, ch.title)
        r = ss.get_section_reading(path, COURSE)
        if r.success and r.data and r.data.n_figures:
            reading = r.data
            head = ("【%s】  %d 块 / %d 图　—　%s"
                    % (path, len(reading.blocks), reading.n_figures, reading.book))
            page.log_box.setHtml(
                '<p style="color:#8a94a6;font-size:12px;margin:0 0 10px">%s</p>%s'
                % (head, ss.render_section_html(reading)))
            page.log_box.verticalScrollBar().setValue(0)
            # 同步在知识树里高亮该章节
            _select_tree_item(page, ch.title)
            break


def _select_tree_item(page, title: str) -> None:
    root = page.tree.topLevelItem(0)
    if root is None:
        return
    for i in range(root.childCount()):
        item = root.child(i)
        if item.text(0) == title:
            page.tree.setCurrentItem(item)
            return


if __name__ == "__main__":
    sys.exit(main())
