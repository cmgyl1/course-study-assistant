"""大学生课程学习辅助软件 - 主程序入口（PySide6 朴素界面）。

界面结构：左侧导航（资料管理 / 自学 / 刷题 / 错题本 / 期末冲刺）
+ 右侧功能页。先核心后美化：UI 与引擎通过 service 层解耦，后续可整体替换。
"""
from __future__ import annotations

import html as _html
import sys
import threading
from dataclasses import replace as _replace
from pathlib import Path

# --- 崩溃诊断钩子：PyInstaller windowed 下未捕获异常/原生崩溃默认静默，
# --- 此钩子把 traceback 与 faulthandler 堆栈落盘到 exe/src 旁的 crash.log ---
import faulthandler
import traceback
from datetime import datetime

_CRASH_LOG = Path(
    sys.executable if getattr(sys, "frozen", False) else __file__
).resolve().parent / "crash.log"


def _crash_hook(etype, evalue, tb) -> None:
    try:
        with open(_CRASH_LOG, "a", encoding="utf-8") as f:
            f.write(f"\n===== {datetime.now().isoformat()} =====\n")
            traceback.print_exception(etype, evalue, tb, file=f)
    except Exception:
        pass
    sys.__excepthook__(etype, evalue, tb)


sys.excepthook = _crash_hook
try:
    faulthandler.enable(open(_CRASH_LOG, "a", encoding="utf-8"))
except Exception:
    pass

# 源码运行时：把 src 加入 sys.path（打包后 PyInstaller 自带模块路径，无需处理）
if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QListWidget, QStackedWidget, QLabel, QPushButton, QLineEdit,
    QTextEdit, QTextBrowser, QComboBox, QFileDialog, QMessageBox, QSplitter,
    QTreeWidget, QTreeWidgetItem, QSpinBox, QListWidgetItem,
    QGroupBox, QFormLayout, QFrame, QSizePolicy, QDialog,
)
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QUrl, QSize
from PySide6.QtGui import QColor, QFont, QBrush, QCursor, QPalette, QPixmap

from engine.config import ensure_data_dirs, COURSES
from engine import practice  # 仅用于 PracticeSession 类型注解
from ui.style import STYLE, DARK_PALETTE
from ui.animations import fade_in, pulse
from services import materials_service, study_service, practice_service, dashboard_service

# 自学页按离线阅读器砍掉了课程下拉框（reader 没有下拉），所以需要一个默认课程。
# 首页课程卡点击可以带别的课程进来 —— 见 MainWindow._goto_page(name, course)。
# 当前只有「计算机网络」跑完了整条流水线，其余 3 门接入后这里不必改。
DEFAULT_COURSE = "计算机网络"


def _book_label(book: str) -> str:
    """教材名 → 左栏分组标题用的**短标签**。

    文件名形如「计算机网络（第8版）_谢希仁_上半」，直接铺进 290px 的左栏会被截成
    「计算机网络（第8版） 谢希…」—— 上册和下册看起来一模一样，分不出来。
    reader 用一张 bookLabels 映射表解决，这里用同等效果的规则化短标签：
    书名主体 + 末段（上/下册）。
    """
    parts = [p for p in (book or "").split("_") if p]
    if len(parts) >= 2:
        return f"{parts[0]} · {parts[-1]}"
    return book or ""



class BasePage(QWidget):
    """页面基类：提供日志区与提示。"""

    def __init__(self) -> None:
        super().__init__()
        self.layout = QVBoxLayout(self)

    def log(self, text: str) -> None:
        if hasattr(self, "log_box"):
            self.log_box.append(text)


# ---------------- 首页（欢迎主界面，v0.5 重做：KPI 大数字 + 4 列课程卡） ----------------

class _KpiCard(QFrame):
    """KPI 大数字块：标签 + 大数字，单位紧凑展示。"""

    def __init__(self, label_text: str, number_object_name: str = "kpiNumber") -> None:
        super().__init__()
        self.setObjectName("kpiCard")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(96)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self.label = QLabel(label_text)
        self.label.setObjectName("kpiLabel")
        v.addWidget(self.label)
        self.number = QLabel("0")
        self.number.setObjectName(number_object_name)
        v.addWidget(self.number)

    def set_value(self, value: int | str) -> None:
        self.number.setText(str(value))


class _CourseCard(QFrame):
    """单课程卡片：课程名 + 教材块数 + 题库数。

    可点击 —— 自学页按离线阅读器砍掉了课程下拉框，课程只能从这里带进去
    （`MainWindow._goto_page("自学", course)`）。其余 3 门课接入后仍走这条入口。
    """

    def __init__(self, course_name: str, on_open=None) -> None:
        super().__init__()
        self.setObjectName("courseCard")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(96)
        self.course_name = course_name
        self._on_open = on_open
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(f"点击进入「{course_name}」自学页")
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)
        self.name_lab = QLabel(f"◆ {course_name}")
        self.name_lab.setObjectName("courseName")
        v.addWidget(self.name_lab)
        # 教材块数
        self.chunks_lab = QLabel("教材 ")
        self.chunks_lab.setObjectName("courseStat")
        self.chunks_num = QLabel("0")
        self.chunks_num.setObjectName("courseStatNum")
        chunks_row = QHBoxLayout()
        chunks_row.setContentsMargins(0, 0, 0, 0)
        chunks_row.setSpacing(2)
        chunks_row.addWidget(self.chunks_lab)
        chunks_row.addWidget(self.chunks_num)
        chunks_row.addWidget(QLabel(" 块"))
        chunks_row.addStretch()
        v.addLayout(chunks_row)
        # 题库数
        self.bank_lab = QLabel("题库 ")
        self.bank_lab.setObjectName("courseStat")
        self.bank_num = QLabel("0")
        self.bank_num.setObjectName("courseStatNum")
        bank_row = QHBoxLayout()
        bank_row.setContentsMargins(0, 0, 0, 0)
        bank_row.setSpacing(2)
        bank_row.addWidget(self.bank_lab)
        bank_row.addWidget(self.bank_num)
        bank_row.addWidget(QLabel(" 题"))
        bank_row.addStretch()
        v.addLayout(bank_row)

    def mousePressEvent(self, event) -> None:
        """整卡可点：点课程卡 = 进该课程的自学页。"""
        if callable(self._on_open):
            self._on_open(self.course_name)
        super().mousePressEvent(event)


class HomePage(BasePage):
    """欢迎主界面：欢迎语 + 快捷入口 + KPI 大数字块 + 4 列课程卡。"""

    def __init__(self, on_goto: callable | None = None) -> None:
        super().__init__()
        self.on_goto = on_goto or (lambda name, course=None: None)
        self.layout.setContentsMargins(32, 28, 32, 28)
        self.layout.setSpacing(18)

        # 欢迎区
        welcome = QLabel("欢迎使用大学生课程学习辅助软件")
        welcome.setObjectName("pageTitle")
        self.layout.addWidget(welcome)

        subtitle = QLabel(
            "本地教材全文检索 · 自学 / 刷题 / 期末冲刺 一站式学习工作台")
        subtitle.setObjectName("pageSubtitle")
        self.layout.addWidget(subtitle)
        self.layout.addSpacing(4)

        # 快捷入口（横向三个主按钮）
        quick = QHBoxLayout()
        quick.setSpacing(12)
        self.study_btn = QPushButton("开始自学")
        self.study_btn.clicked.connect(lambda: self.on_goto("自学"))
        self.practice_btn = QPushButton("去刷题")
        self.practice_btn.clicked.connect(lambda: self.on_goto("刷题"))
        self.finals_btn = QPushButton("期末冲刺")
        self.finals_btn.setObjectName("secondary")  # 第三个用次级按钮，体现层级
        self.finals_btn.clicked.connect(lambda: self.on_goto("期末冲刺"))
        for b in (self.study_btn, self.practice_btn, self.finals_btn):
            quick.addWidget(b)
        quick.addStretch()
        self.layout.addLayout(quick)
        self.layout.addSpacing(8)

        # ===== 学习进度概览：4 个 KPI 大数字块（横向一行） =====
        kpi_title = QLabel("学习进度概览")
        kpi_title.setObjectName("pageSubtitle")
        kpi_title.setStyleSheet("font-size:14px;font-weight:600;color:#E4E8EE;padding-top:8px;")
        self.layout.addWidget(kpi_title)
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(14)
        self.kpi_chunks = _KpiCard("教材块 · 可检索片段", "kpiNumber")
        self.kpi_bank = _KpiCard("题库 · 已录入题目", "kpiNumber")
        self.kpi_wrong = _KpiCard("错题本 · 待复习题目", "kpiNumberGold")  # 金色，因为是警示
        self.kpi_docx = _KpiCard("Word 教材 · 可批注文档", "kpiNumberSage")  # 绿色，因为是利好
        for w in (self.kpi_chunks, self.kpi_bank, self.kpi_wrong, self.kpi_docx):
            kpi_row.addWidget(w)
        self.layout.addLayout(kpi_row)

        # ===== 我的课程：4 列网格课程卡 =====
        course_title = QLabel("我的课程")
        course_title.setObjectName("pageSubtitle")
        course_title.setStyleSheet("font-size:14px;font-weight:600;color:#E4E8EE;padding-top:8px;")
        self.layout.addWidget(course_title)
        # 用 QGridLayout 4 列（响应式：超过 4 门课自动换行）
        courses = list(COURSES.keys())
        course_grid = QGridLayout()
        course_grid.setSpacing(14)
        self.course_cards: dict[str, _CourseCard] = {}
        for idx, course in enumerate(courses):
            card = _CourseCard(course, self._open_course)
            self.course_cards[course] = card
            row, col = divmod(idx, 4)
            course_grid.addWidget(card, row, col)
        # 占位让网格靠左
        course_grid.setColumnStretch(4, 1)
        self.layout.addLayout(course_grid)
        self.layout.addStretch()

    def _open_course(self, course: str) -> None:
        """点课程卡 → 进自学页并带上该课程。

        这就是"自学页照搬 reader 砍掉课程下拉框"之后，其余 3 门课的低成本入口
        —— 自学页自己不提供课程切换，但首页卡片能把它带进去。
        """
        self.on_goto("自学", course)

    def refresh(self) -> None:
        """刷新课程进度与统计（进入首页时调用）。"""
        r = dashboard_service.build_dashboard()
        if not r.success or r.data is None:
            # 失败时全部置 0，不阻塞 UI
            self.kpi_chunks.set_value(0)
            self.kpi_bank.set_value(0)
            self.kpi_wrong.set_value(0)
            self.kpi_docx.set_value(0)
            for card in self.course_cards.values():
                card.chunks_num.setText("0")
                card.bank_num.setText("0")
            return
        d = r.data
        self.kpi_chunks.set_value(sum(d.course_chunks.values()))
        self.kpi_bank.set_value(sum(d.question_bank.values()))
        self.kpi_wrong.set_value(sum(d.wrong_book.values()))
        self.kpi_docx.set_value(d.textbook_docx)
        for course, card in self.course_cards.items():
            chunks = d.course_chunks.get(course, 0)
            qcount = d.question_bank.get(course, 0)
            card.chunks_num.setText(str(chunks))
            card.bank_num.setText(str(qcount))


# ---------------- 资料管理页 ----------------

class MaterialsPage(BasePage):
    def __init__(self) -> None:
        super().__init__()
        title = QLabel("资料管理")
        title.setObjectName("pageTitle")
        self.layout.addWidget(title)

        # 课程选择
        self.course_box = QComboBox()
        self.course_box.addItems(list(COURSES.keys()))
        self.layout.addWidget(self.course_box)

        # 教材导入
        grp = QGroupBox("教材导入（PDF → Markdown → 检索语料）")
        form = QFormLayout(grp)
        self.md_btn = QPushButton("选择教材 PDF/文档并导入")
        self.md_btn.clicked.connect(self.import_textbook)
        form.addRow(self.md_btn)
        self.layout.addWidget(grp)

        # 课件归档
        grp2 = QGroupBox("课件/讲义归档（PPT/Word/PDF → Markdown 资料库）")
        form2 = QFormLayout(grp2)
        self.courseware_btn = QPushButton("选择课件文件（可多选）并转换归档")
        self.courseware_btn.clicked.connect(self.import_courseware)
        form2.addRow(self.courseware_btn)
        self.layout.addWidget(grp2)

        # Word 教材生成 + 题库模板
        grp3 = QGroupBox("Word 教材 / 题库")
        form3 = QFormLayout(grp3)
        self.docx_btn = QPushButton("生成全部 Word 版教材（供批注）")
        self.docx_btn.clicked.connect(self.gen_docx)
        self.bank_btn = QPushButton("生成 4 科题库模板（若不存在）")
        self.bank_btn.clicked.connect(self.gen_banks)
        form3.addRow(self.docx_btn)
        form3.addRow(self.bank_btn)
        self.layout.addWidget(grp3)

        self.log_box = QTextEdit()
        self.log_box.setObjectName("logBox")
        self.log_box.setReadOnly(True)
        self.log_box.setMinimumHeight(120)
        self.layout.addWidget(self.log_box, 1)

    def import_textbook(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择教材", "", "文档 (*.pdf *.docx *.doc *.txt *.md)")
        if not files:
            return
        r = materials_service.import_textbook([Path(f) for f in files], self.course_box.currentText())
        # 先逐文件打 log，最后打总结消息
        if r.data:
            for o in r.data:
                sym = "✓" if o.success else "✗"
                self.log(f"[{sym}] {o.file_name} → {o.message}")
        self.log(f"--- {r.message} ---")

    def import_courseware(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择课件", "", "课件 (*.pptx *.ppt *.docx *.doc *.pdf *.xlsx *.xls)")
        if not files:
            return
        r = materials_service.import_courseware([Path(f) for f in files], self.course_box.currentText())
        if r.data:
            for o in r.data:
                sym = "✓" if o.success else "✗"
                self.log(f"[{sym}] {o.file_name} → {o.message}")
        self.log(f"--- {r.message} ---")

    def gen_docx(self) -> None:
        r = materials_service.generate_all_docx()
        self.log(r.message)
        for name in r.data or []:
            self.log(f"  - {name}（可用 Word/WPS 打开批注）")

    def gen_banks(self) -> None:
        r = materials_service.ensure_question_bank_templates()
        self.log(r.message)
        for name in r.data or []:
            self.log(f"  - {name}")


# ---------------- 自学页：卡片 / 卡片列表 / 全屏遮罩 ----------------

class _ResultCard(QFrame):
    """检索结果卡片（对照 reader 的 `.card`，自绘，不翻译 CSS）。

    QTextBrowser 只认 Qt 富文本子集：`flex` / `position:fixed` 一律不支持，
    所以卡片**不能**靠把 reader 的 CSS 搬进富文本来做，只能用
    QListWidget + setItemWidget 拼真控件。本类就是那"一张卡"。

    版式：右上角一个角标（章节卡=命中 N 词，片段卡=BM25 分数），
    左侧主标题 + 元信息（书名 · 页码），片段卡多一行前 160 字预览（命中词高亮）。
    """

    def __init__(self, title: str, meta: str = "", badge: str = "",
                 preview: str = "", tip: str = "", on_click=None) -> None:
        super().__init__()
        self.setObjectName("resultCard")
        self.setCursor(Qt.PointingHandCursor)
        self._on_click = on_click
        if tip:
            self.setToolTip(tip)

        v = QVBoxLayout(self)
        v.setContentsMargins(14, 11, 14, 12)
        v.setSpacing(3)

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(10)
        self.title_lab = QLabel(title)
        self.title_lab.setObjectName("cardTitle")
        self.title_lab.setWordWrap(True)
        head.addWidget(self.title_lab, 1)
        self.badge_lab = QLabel(badge)
        self.badge_lab.setObjectName("cardBadge")
        self.badge_lab.setAlignment(Qt.AlignRight | Qt.AlignTop)
        self.badge_lab.setVisible(bool(badge))
        head.addWidget(self.badge_lab, 0)
        v.addLayout(head)

        # 三个标签**恒建**，空就隐藏 —— 验收脚本要直接读它们做断言，
        # 条件创建会让断言脚本被迫去猜布局里有几个子控件。
        self.meta_lab = QLabel(meta)
        self.meta_lab.setObjectName("cardMeta")
        self.meta_lab.setVisible(bool(meta))
        v.addWidget(self.meta_lab)

        self.preview_lab = QLabel(preview)
        self.preview_lab.setObjectName("cardPreview")
        self.preview_lab.setTextFormat(Qt.RichText)
        self.preview_lab.setWordWrap(True)
        self.preview_lab.setVisible(bool(preview))
        v.addWidget(self.preview_lab)

    def mousePressEvent(self, event) -> None:
        """整卡可点（点标题、空白处都算）。子 QLabel 不收鼠标事件，会自动冒泡到这里。"""
        if callable(self._on_click):
            self._on_click()
        super().mousePressEvent(event)


class _CardList(QListWidget):
    """检索结果卡片列表。

    QListWidget 用 setItemWidget 时**不会**跟着 viewport 宽度重算 item 高度：
    窗口一拉宽，卡片里的预览文字就被裁掉。所以每次 resize 补算一遍。
    """

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("resultList")
        self.setSelectionMode(QListWidget.NoSelection)
        self.setFocusPolicy(Qt.NoFocus)
        self.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.setSpacing(10)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._relayout()

    def _relayout(self) -> None:
        width = max(self.viewport().width() - 18, 160)
        for i in range(self.count()):
            item = self.item(i)
            widget = self.itemWidget(item)
            if widget is None:
                continue
            widget.setFixedWidth(width)
            item.setSizeHint(QSize(width, widget.sizeHint().height()))


class _Lightbox(QDialog):
    """全屏遮罩放大（对照 reader 的 `#lb`：黑底、图最多占 96%、点任意处关、Esc 关）。

    旧的实现弹一个带标题栏的 QDialog，必须用鼠标去点右上角的叉才能关 ——
    reader 是"点哪都关、Esc 也关"。这里用无边框对话框 + 自身吃鼠标事件还原。
    """

    def __init__(self, parent, pixmap: QPixmap) -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setModal(True)
        self.setAutoFillBackground(True)
        pal = self.palette()
        pal.setColor(QPalette.Window, QColor(0, 0, 0, 230))     # reader: rgba(0,0,0,.9)
        self.setPalette(pal)
        self.setCursor(Qt.PointingHandCursor)
        # 盖住整个应用窗口（reader 的 #lb 是 position:fixed inset:0，即盖住视口）
        win = parent.window() if parent is not None else None
        if win is not None:
            self.setGeometry(win.frameGeometry())
            box = QSize(int(win.width() * 0.96), int(win.height() * 0.96))
        else:
            box = QSize(1229, 768)
        if pixmap.width() > box.width() or pixmap.height() > box.height():
            pixmap = pixmap.scaled(box, Qt.KeepAspectRatio, Qt.SmoothTransformation)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        canvas = QLabel()
        canvas.setAlignment(Qt.AlignCenter)
        # 让点击穿透到对话框本身 —— 否则点在图上是"点了个 QLabel"，遮罩不关
        canvas.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        canvas.setPixmap(pixmap)
        lay.addWidget(canvas)

    def mousePressEvent(self, event) -> None:
        self.accept()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.accept()
            return
        super().keyPressEvent(event)


# ---------------- 自学页 ----------------

class StudyPage(BasePage):
    """课前课后自学 —— 界面与离线阅读器 `data/reader.html` 保持同构。

    版式（与 reader 一致）：
        顶部 header 横向条：标题 + 检索框 + 检索按钮 + 提示
        主体左右两栏：左 = 章节树（290px，书名分组 + 章/节/小节），
                      右 = 正文（点章节）或检索结果卡片（提问后）

    刻意**不含**这三样（reader 没有）：课程下拉框、📌 知识点叶子、索引预热状态标签。
    课程改由首页课程卡带入（`MainWindow._goto_page(name, course)`）。
    渲染层的能力一个都没删：`get_course_tree()` 照旧返回 concepts，
    `warm_up()` 照旧被调用，只是不再显示。
    """

    TREE_W = 290          # 左栏宽度，对齐 reader 的 aside{width:290px}

    def __init__(self, course: str = DEFAULT_COURSE) -> None:
        super().__init__()
        self._course = course
        self._marks: list[str] = []
        self._warm_state = "idle"
        self._path_index: dict[tuple[str, str], QTreeWidgetItem] = {}
        self.layout.setContentsMargins(20, 16, 20, 16)
        self.layout.setSpacing(12)

        # ===== 顶部 header 横向条（reader: header{display:flex}）=====
        header = QHBoxLayout()
        header.setSpacing(14)
        self.title_label = QLabel("")
        self.title_label.setObjectName("studyTitle")
        self.title_label.setTextFormat(Qt.RichText)
        header.addWidget(self.title_label)
        self.query_edit = QLineEdit()
        self.query_edit.setObjectName("studyQuery")
        self.query_edit.setPlaceholderText(
            "输入知识点，如：物理层 / 什么是物理层 / CSMA/CD")
        self.query_edit.setMaximumWidth(560)      # reader: #q{max-width:560px}
        self.query_edit.returnPressed.connect(self.ask)
        header.addWidget(self.query_edit, 1)
        self.ask_btn = QPushButton("检索")
        self.ask_btn.clicked.connect(self.ask)
        header.addWidget(self.ask_btn)
        self.hint_label = QLabel("")
        self.hint_label.setObjectName("studyHint")
        header.addWidget(self.hint_label, 2)
        self.layout.addLayout(header)

        # ===== 主体：左栏章节树 + 右栏（结果卡片 / 正文）=====
        body = QHBoxLayout()
        body.setSpacing(16)

        self.tree = QTreeWidget()
        self.tree.setObjectName("studyTree")
        self.tree.setHeaderHidden(True)           # reader 的左栏没有表头
        self.tree.setMinimumHeight(150)
        self.tree.setFixedWidth(self.TREE_W)
        self.tree.itemClicked.connect(self.on_tree_click)
        body.addWidget(self.tree)

        # 右栏两种形态，共用一个位置：卡片列表 / 正文浏览器
        self.result_list = _CardList()
        self.log_box = QTextBrowser()
        self.log_box.setObjectName("logBox")
        self.log_box.setOpenExternalLinks(False)
        # 插图在 HTML 里是 <a href="file:///…"><img …></a>，点击由我们自己接管成
        # 全屏遮罩放大。必须关掉 Qt 的默认链接处理，否则它会去"用系统程序打开这张图"。
        self.log_box.setOpenLinks(False)
        self.log_box.anchorClicked.connect(self._on_anchor_clicked)
        self.log_box.setMinimumHeight(120)
        self.right = QStackedWidget()
        self.right.addWidget(self.result_list)
        self.right.addWidget(self.log_box)
        body.addWidget(self.right, 1)
        self.layout.addLayout(body, 1)

        # 检索索引预热：建 BM25 索引约 6s / 1698 块，而查询只要 0.3ms —— 不预热的
        # 话第一次提问会卡住界面 6 秒。放到后台线程建，主线程只轮询状态。
        self._warm_poll = QTimer(self)
        self._warm_poll.setInterval(400)
        self._warm_poll.timeout.connect(self._on_warm_tick)
        self.set_course(course)

    # ---------------- 课程切换 ----------------

    def set_course(self, course: str) -> None:
        """切换课程：标题 / 章节树 / 索引预热 / 首页态，一次全换。"""
        if course:
            self._course = course
        self.title_label.setText(
            f'{self._course}　<span style="color:#93A0B4;font-size:12px">'
            f'教材原文阅读器</span>')
        self.refresh_tree()
        self.show_home()
        self._restart_warm()

    # ---------------- 检索索引预热 ----------------

    def _restart_warm(self) -> None:
        """启动后台预热。

        自学页按 reader 去掉了课程下拉框，预热**只能靠这里显式触发** ——
        旧版挂在 `course_box.currentIndexChanged` 上，删掉下拉后会永远不预热，
        表现为"第一次提问卡 6 秒"。课程是普通字符串，跨线程读是安全的。
        """
        self._warm_state = "idle"
        threading.Thread(target=self._warm_worker, daemon=True).start()
        self._warm_poll.start()

    def _warm_worker(self) -> None:
        """后台建索引。**这里绝不能碰任何 Qt 控件**（跨线程访问会崩）。"""
        try:
            ok = study_service.warm_up(self._course)
            self._warm_state = "ready" if ok else "no_corpus"
        except Exception as e:      # 预热失败要让用户看见，不静默吞掉
            self._warm_state = f"failed:{type(e).__name__}: {e}"

    def _on_warm_tick(self) -> None:
        """主线程轮询：预热**没成功**才吭声。

        reader 没有"索引状态"这个标签，成功就不该多一行字；但失败和"没教材"
        必须如实显示 —— 否则用户只会觉得"什么都查不到"却不知道原因。
        """
        if self._warm_state == "idle":
            return
        self._warm_poll.stop()
        if self._warm_state == "ready":
            return
        if self._warm_state == "no_corpus":
            self._show_notice("该课程暂无教材，请先在「资料管理」导入教材。")
        else:
            self._show_notice(
                f"检索索引构建失败：{self._warm_state[len('failed:'):]}", "#e06c6c")

    def refresh_tree(self) -> None:
        self.tree.clear()
        self._path_index.clear()
        r = study_service.get_course_tree(self._course)
        if not r.success:
            self._show_notice(f"❌ {r.message}", "#e06c6c")
            return
        if not r.data:
            self._show_notice(r.message)
            return
        for root_node in r.data:
            # 书名分组标题（reader: aside .book{color:var(--gold)}）——
            # 它只是分组标签，不响应点击，所以设成不可选。
            # 显示用短标签，**真实书名存在 UserRole 里**：拼章节路径、建反查表都得用真名。
            root = QTreeWidgetItem([_book_label(root_node.book)])
            root.setData(0, Qt.UserRole, root_node.book)
            root.setForeground(0, QBrush(QColor("#E0B266")))
            root_font = QFont()
            root_font.setBold(True)
            root_font.setPointSize(13)
            root.setFont(0, root_font)
            root.setFlags(root.flags() & ~Qt.ItemIsSelectable)
            for ch in root_node.children:
                self._add_nodes(root, ch, 1)
            self.tree.addTopLevelItem(root)
        self._build_path_index()
        self.tree.expandAll()

    def _add_nodes(self, parent: QTreeWidgetItem, node, depth: int = 1) -> None:
        """递归添加 DTO 节点 → QTreeWidgetItem。

        配色对齐 reader 的 aside：一级（章）用亮色，二级往下用灰。
        旧版还会在这里挂 📌 知识点叶子，reader 没有，已去掉 ——
        但 `get_course_tree()` 仍然返回 concepts，能力没删，只是不再显示。
        """
        from services.dto import KnowledgeNode as KN
        item = QTreeWidgetItem([node.title])
        item.setForeground(0, QBrush(QColor("#E6EAF2" if depth <= 1 else "#93A0B4")))
        if depth > 1:
            node_font = QFont()
            node_font.setPointSize(12)
            item.setFont(0, node_font)
        parent.addChild(item)
        if isinstance(node, KN):
            for c in node.children:
                self._add_nodes(item, c, depth + 1)

    # ---------------- 「节路径 → 树节点」反查 ----------------

    def _build_path_index(self) -> None:
        """建反查表，供"点卡片 → 左栏回选"用（reader 的 show(si) 会切 .on）。

        **不能按整条路径精确匹配**：语料里的 `section_path` 与树上的标题在顶层
        章名上可能不一致 —— 实测教材里是「第5章」，而树上是「第5章运输层」。
        所以按"从末级往上的所有后缀"建索引，查的时候优先匹配最长的后缀。
        """
        self._path_index.clear()

        def walk(item: QTreeWidgetItem, titles: list[str], book: str) -> None:
            chain = titles + [item.text(0).strip()]
            for k in range(1, len(chain) + 1):
                self._path_index.setdefault((book, " > ".join(chain[-k:])), item)
            for j in range(item.childCount()):
                walk(item.child(j), chain, book)

        for i in range(self.tree.topLevelItemCount()):
            book_item = self.tree.topLevelItem(i)
            walk(book_item, [], self._book_stem(book_item))

    def _book_stem(self, book_item: QTreeWidgetItem) -> str:
        """取分组节点代表的**真实教材名**（显示的是短标签，别拿 text(0) 当书名）。"""
        return book_item.data(0, Qt.UserRole) or book_item.text(0).strip()

    def _find_tree_item(self, doc_title: str, section_path: str) -> QTreeWidgetItem | None:
        """按（书名, 节路径）找树节点；对不上就返回 None（不抛异常）。"""
        parts = [p.strip() for p in (section_path or "").split(" > ") if p.strip()]
        if not parts:
            return None
        books = [doc_title] if doc_title else []
        books += [self._book_stem(self.tree.topLevelItem(i))
                  for i in range(self.tree.topLevelItemCount())]
        for k in range(len(parts), 0, -1):              # 后缀由长到短
            key = " > ".join(parts[-k:])
            for book in books:
                item = self._path_index.get((book, key))
                if item is not None:
                    return item
        return None

    def _select_tree_item(self, doc_title: str, section_path: str) -> bool:
        """把左栏对应项标记为选中并滚到可见。对不上就**不动**（正文照跳）。"""
        item = self._find_tree_item(doc_title, section_path)
        if item is None:
            return False
        parent = item.parent()
        while parent is not None:
            parent.setExpanded(True)
            parent = parent.parent()
        self.tree.setCurrentItem(item)
        self.tree.scrollToItem(item)
        return True

    def on_tree_click(self, item: QTreeWidgetItem) -> None:
        """点树节点 → 读该节保序原文（reader 的 show(si)）。"""
        if item.parent() is None:      # 书名分组只是标签（reader 里同样不可点）
            return
        parts = []
        node = item
        while node is not None:
            # 顶层分组显示的是短标签，拼路径必须换回真实书名，否则 find_book 找不到书
            text = self._book_stem(node) if node.parent() is None else node.text(0).strip()
            if text:
                parts.insert(0, text)
            node = node.parent()
        self._show_reading(" > ".join(parts))

    # ---------------- 检索 ----------------

    def ask(self) -> None:
        """检索入口（reader 的 doSearch()）。

        top_k 传 10 再各切一段：reader 是「标题 6 / 片段 10」，而引擎默认 5 ——
        不传 10 的话片段卡只有 5 张，看着就比 reader 少一半。
        """
        query = self.query_edit.text().strip()
        if not query:
            self.show_home()
            return
        r = study_service.explain_topic(query, self._course, top_k=10)
        if not r.success or r.data is None:
            self._show_notice(f"❌ {r.message}", "#e06c6c")
            return
        data = r.data
        if data.status in ("not_found", "no_corpus", "empty_query"):
            self._show_not_found(data)
            return
        self._fill_results(data)

    def _fill_results(self, data) -> None:
        """检索结果 → 卡片列表（对照 reader 的 doSearch()）。"""
        marks = list(data.used_tokens)
        hits = list(data.section_hits)[:6]        # reader: hits.slice(0,6)
        rows = list(data.evidence)[:10]           # reader: rows 已是 10 条
        self._marks = marks

        self.result_list.clear()
        if hits:
            self._add_group("命中的章节")
            for h in hits:
                self._add_card(_ResultCard(
                    title=h.title or study_service.section_title(h.section_path),
                    meta=" · ".join(x for x in (
                        h.doc_title,
                        f"第 {h.page_no} 页" if h.page_no else "") if x),
                    badge=f"命中 {h.n_hits} 词",
                    tip=h.section_path,
                    on_click=lambda h=h: self._jump_card(h.doc_title, h.section_path),
                ))
        if rows:
            self._add_group("原文片段")
            for ev in rows:
                self._add_card(_ResultCard(
                    title=study_service.section_title(ev.section_path),
                    meta=f"第 {ev.page_no} 页" if ev.page_no else "",
                    badge=f"{ev.score:.3f}",
                    preview=study_service.preview_html(ev.content, marks),
                    tip=ev.section_path,
                    on_click=lambda ev=ev: self._jump_card(ev.doc_title, ev.section_path),
                ))

        # 一条都没命中：如实说"没检索到"，不摆空列表
        if not hits and not rows:
            self._show_notice("未检索到原文段落。")
            return

        self.right.setCurrentWidget(self.result_list)
        self.result_list.scrollToTop()
        self.result_list._relayout()
        hint = f"标题命中 {len(hits)} · 原文片段 {len(rows)}"
        if data.missing_tokens:
            hint = (f"「{'、'.join(data.missing_tokens)}」未出现，按其余关键词检索 · "
                    + hint)
        self.hint_label.setText(hint)

    def _add_group(self, text: str) -> None:
        """结果区的小标题（reader 的 `<h4>命中的章节 / 原文片段</h4>`）。"""
        lab = QLabel(text)
        lab.setObjectName("resultGroup")
        item = QListWidgetItem()
        item.setFlags(Qt.ItemIsEnabled)           # 可显示但不可选中、不可点
        item.setSizeHint(lab.sizeHint())
        self.result_list.addItem(item)
        self.result_list.setItemWidget(item, lab)

    def _add_card(self, card: _ResultCard) -> None:
        item = QListWidgetItem()
        item.setFlags(Qt.ItemIsEnabled)
        self.result_list.addItem(item)
        self.result_list.setItemWidget(item, card)

    def _jump_card(self, doc_title: str, section_path: str) -> None:
        """点卡片 → 跳该节原文，并把左栏对应项标记为选中（reader 的 show(si)）。"""
        full = f"{doc_title} > {section_path}" if doc_title else section_path
        self._show_reading(full, doc_title=doc_title, select=True)

    # ---------------- 右栏的三种形态 ----------------

    def show_home(self) -> None:
        """进入自学页 / 清空输入框时的首页态（reader 的 showHome()）。"""
        self._marks = []
        self.hint_label.setText("")
        self.log_box.setHtml(
            '<p style="font-size:22px;font-weight:bold;color:#E6EAF2;'
            'margin:0 0 12px;padding-bottom:10px;border-bottom:1px solid #2A313D">'
            f'{_html.escape(self._course)}</p>'
            '<p style="margin:0;line-height:1.9;text-indent:2em;text-align:justify">'
            '左栏点章节看该节<b>原文</b>：插图内嵌在它原来的位置（点击放大），'
            '表格按表格显示 —— 块的顺序就是原书的顺序，没有做任何重排。'
            '顶部输入框按知识点检索：先命中标题，标题不中再给原文段落；'
            '整本书都没有的词会直接说明“未找到”，不做猜测性作答。</p>')
        self.right.setCurrentWidget(self.log_box)

    def _show_reading(self, section_path: str, doc_title: str = "",
                      marks=(), select: bool = True) -> None:
        """渲染某节保序原文（reader 的 show(si)）。

        走 `get_section_reading`（保序原文），**不是** `get_section_content`
        （BM25 top-3 按相关度重排）—— 后者会把图和正文的顺序打乱。
        """
        r = study_service.get_section_reading(section_path, self._course)
        if not r.success or r.data is None:
            self._show_notice(f"❌ {r.message}", "#e06c6c")
            return
        reading = r.data
        title = study_service.section_title(reading.section_path or section_path)
        # 面包屑的页码取"该节标题自己的页"，与 reader 的 s.page 一致
        sec_page = reading.blocks[0].page if reading.blocks else None
        blocks = list(reading.blocks)
        # get_section_blocks 从命中的那条标题开始返回，所以首块就是该节自己的标题；
        # 标题马上由下面的 h2 呈现，留着会重复一行（reader 的节内块不含节标题）。
        if (title and blocks and blocks[0].kind == "heading"
                and blocks[0].text.strip() == title):
            blocks = blocks[1:]
        reading = _replace(reading, blocks=blocks)

        crumb = " · ".join(x for x in (
            reading.book, f"第 {sec_page} 页" if sec_page else "") if x)
        head = (
            f'<div style="color:#93A0B4;font-size:12.5px;margin:0 0 16px">'
            f'{_html.escape(crumb)}</div>'
            '<p style="font-size:22px;font-weight:bold;color:#E6EAF2;'
            'margin:0 0 16px;padding-bottom:10px;border-bottom:2px solid #2A313D">'
            f'{_html.escape(title or reading.book)}</p>')
        self.hint_label.setText("")
        self.result_list.clear()      # 右栏换成正文了，结果卡片不再保留
        self.log_box.setHtml(head + study_service.render_section_html(reading, marks))
        self.log_box.verticalScrollBar().setValue(0)
        self.right.setCurrentWidget(self.log_box)
        if select:
            self._select_tree_item(doc_title,
                                   reading.section_path or section_path)

    def _show_notice(self, text: str, color: str = "#e0b266") -> None:
        """在正文区显示一段提示，**不显示任何段落**。"""
        self.hint_label.setText("")
        self.result_list.clear()      # 与 _show_reading / _show_not_found 同理：
        self.log_box.setHtml(         # 右栏换了内容，旧卡片不能留在隐藏层里
            f'<p style="margin:24px 0;color:{color};font-size:14px;line-height:1.7">'
            f'{_html.escape(text)}</p>')
        self.right.setCurrentWidget(self.log_box)

    def _show_not_found(self, data) -> None:
        """书里没有这个词 —— 如实说没有，**一个段落都不给**。

        这是 reader 与软件的共同硬规则：旧版无论问什么都返回 top-5，
        用户会以为书里讲过。这里连"依据 1/2/3"的骨架都不建立。
        """
        msg = (data.message or "书中未找到相关内容。").rstrip("。")
        self.hint_label.setText(msg + "。")
        self.result_list.clear()      # 拒答时结果区必须是空的（不留上一次的卡片）
        self.log_box.setHtml(
            '<p style="font-size:22px;font-weight:bold;color:#E6EAF2;'
            'margin:0 0 12px;padding-bottom:10px;border-bottom:2px solid #2A313D">'
            '未找到</p>'
            '<p style="margin:0;line-height:1.9;text-indent:2em;text-align:justify">'
            f'{_html.escape(msg)}，不做猜测性作答。</p>')
        self.right.setCurrentWidget(self.log_box)

    # ---------------- 插图放大 ----------------

    def _make_lightbox(self, image_path: str) -> _Lightbox | None:
        """建遮罩（不 exec）—— 拆出来是为了让验收脚本能驱动它开合。"""
        pix = QPixmap(image_path)
        if pix.isNull():
            return None
        return _Lightbox(self, pix)

    def _on_anchor_clicked(self, url: QUrl) -> None:
        """点插图 → 全屏遮罩放大（教材里的协议帧图、电路图不放大根本看不清）。"""
        if url.scheme() != "file":
            return
        box = self._make_lightbox(url.toLocalFile())
        if box is None:
            return
        box.exec()


# ---------------- 刷题页 ----------------

class PracticePage(BasePage):
    def __init__(self) -> None:
        super().__init__()
        title = QLabel("刷题备考")
        title.setObjectName("pageTitle")
        self.layout.addWidget(title)

        top = QHBoxLayout()
        self.course_box = QComboBox()
        self.course_box.addItems(list(COURSES.keys()))
        self.type_box = QComboBox()
        self.type_box.addItems(["选择题", "填空题", "大题", "综合组卷"])
        self.count_spin = QSpinBox()
        self.count_spin.setRange(1, 200)
        self.count_spin.setValue(10)
        self.start_btn = QPushButton("开始刷题")
        self.start_btn.clicked.connect(self.start)
        self.check_btn = QPushButton("提交答案")
        self.check_btn.clicked.connect(self.check)
        self.check_btn.setEnabled(False)
        # 填空题/大题自查按钮（选择题自动判分，无需显示）
        self.good_btn = QPushButton("我答对了")
        self.good_btn.setObjectName("success")
        self.good_btn.clicked.connect(lambda: self.self_check(True))
        self.bad_btn = QPushButton("我答错了")
        self.bad_btn.setObjectName("danger")
        self.bad_btn.clicked.connect(lambda: self.self_check(False))
        self.good_btn.setVisible(False)
        self.bad_btn.setVisible(False)
        top.addWidget(QLabel("课程："))
        top.addWidget(self.course_box)
        top.addWidget(QLabel("题型："))
        top.addWidget(self.type_box)
        top.addWidget(QLabel("数量："))
        top.addWidget(self.count_spin)
        top.addWidget(self.start_btn)
        top.addWidget(self.check_btn)
        top.addWidget(self.good_btn)
        top.addWidget(self.bad_btn)
        top.addStretch()
        self.layout.addLayout(top)

        self.log_box = QTextEdit()
        self.log_box.setObjectName("logBox")
        self.log_box.setReadOnly(True)
        self.log_box.setMinimumHeight(120)
        self.layout.addWidget(self.log_box, 1)
        self.session: practice.PracticeSession | None = None
        self.answer_edit: QLineEdit | None = None

    def start(self) -> None:
        course = self.course_box.currentText()
        t = self.type_box.currentText()
        n = self.count_spin.value()
        by_type = None
        if t == "选择题":
            by_type = {"选择题": n}
        elif t == "填空题":
            by_type = {"填空题": n}
        elif t == "大题":
            by_type = {"大题": n}
        r = practice_service.start_course_session(course, by_type)
        if not r.success or r.data is None:
            self.log_box.clear()
            self.log_box.append(f"❌ {r.message}")
            return
        self.session = r.data
        self.log_box.clear()
        self.log_box.append(f"📝 {r.message}")
        self.show_current()
        self.check_btn.setEnabled(True)

    def show_current(self) -> None:
        q = self.session.current
        if q is None:
            self.log_box.append("本次刷题结束。")
            self.check_btn.setEnabled(False)
            self.good_btn.setVisible(False)
            self.bad_btn.setVisible(False)
            return
        self.good_btn.setVisible(False)
        self.bad_btn.setVisible(False)
        idx, total = self.session.progress
        self.log_box.append(f"—— 第 {idx + 1}/{total} 题（{q['type']}）——")
        self.log_box.append(q["stem"])
        for opt in q["options"]:
            self.log_box.append(f"  {opt}")
        self.log_box.append("")
        if q["type"] == "选择题":
            self.log_box.append("请在下方输入 A/B/C/D，然后点「提交答案」。")
        else:
            self.log_box.append("请在下方输入你的答案，点「提交答案」后对照参考答案自查。")
        if self.answer_edit is None:
            self.answer_edit = QLineEdit()
            self.answer_edit.setPlaceholderText("输入答案（选择题填 A/B/C/D）")
            self.layout.addWidget(self.answer_edit)

    def check(self) -> None:
        """提交答案：选择题自动判分；填空/大题进入自查流程。"""
        if self.session is None or self.session.current is None:
            return
        answer = self.answer_edit.text().strip() if self.answer_edit else ""
        q = self.session.current
        if q["type"] == "选择题":
            if not answer:
                self.log_box.append("请先输入答案（A/B/C/D）。")
                return
            r = self.session.submit(answer)
            self.log_box.append(f"判定：{'✓ 正确' if r['correct'] else '✗ 错误'}（期望答案：{r['expected']}）")
            self.log_box.append("")
            self.advance()
        else:
            if not answer:
                self.log_box.append("请先输入你的答案，再点「提交答案」。")
                return
            expected = q.get("answer", "").strip()
            self.log_box.append(f"你的答案：{answer}")
            if expected:
                self.log_box.append(f"参考答案：{expected}")
            self.log_box.append("请对照后点击「我答对了 / 我答错了」自查判分。")
            self.good_btn.setVisible(True)
            self.bad_btn.setVisible(True)

    def self_check(self, correct: bool) -> None:
        """填空/大题自查：学生确认对错后判分进错题本循环。"""
        if self.session is None or self.session.current is None:
            return
        r = self.session.submit("对" if correct else "错")
        self.log_box.append(f"自查判定：{'✓ 答对' if r['correct'] else '✗ 答错（已加入错题本）'}")
        self.log_box.append("")
        self.good_btn.setVisible(False)
        self.bad_btn.setVisible(False)
        self.advance()

    def advance(self) -> None:
        """进入下一题或结束本场。"""
        if self.session.done:
            res = self.session.finish()
            self.log_box.append(f"=== 本场统计：答对 {res.correct}/{res.answered}，准确率 {res.accuracy:.1%} ===")
            self.check_btn.setEnabled(False)
            self.good_btn.setVisible(False)
            self.bad_btn.setVisible(False)
        else:
            self.show_current()


# ---------------- 错题本页 ----------------

class WrongBookPage(BasePage):
    def __init__(self) -> None:
        super().__init__()
        title = QLabel("错题本（对/错循环机制）")
        title.setObjectName("pageTitle")
        self.layout.addWidget(title)

        top = QHBoxLayout()
        self.refresh_btn = QPushButton("刷新错题")
        self.refresh_btn.clicked.connect(self.refresh)
        self.review_btn = QPushButton("错题重刷")
        self.review_btn.clicked.connect(self.review)
        self.submit_btn = QPushButton("提交答案")
        self.submit_btn.clicked.connect(self.submit_review)
        self.good_btn = QPushButton("我答对了")
        self.good_btn.setObjectName("success")
        self.good_btn.clicked.connect(lambda: self.self_check(True))
        self.bad_btn = QPushButton("我答错了")
        self.bad_btn.setObjectName("danger")
        self.bad_btn.clicked.connect(lambda: self.self_check(False))
        top.addWidget(self.refresh_btn)
        top.addWidget(self.review_btn)
        top.addWidget(self.submit_btn)
        top.addWidget(self.good_btn)
        top.addWidget(self.bad_btn)
        top.addStretch()
        self.layout.addLayout(top)

        self.list_widget = QListWidget()
        self.list_widget.setMinimumHeight(120)
        self.layout.addWidget(self.list_widget, 1)
        self.log_box = QTextEdit()
        self.log_box.setObjectName("logBox")
        self.log_box.setReadOnly(True)
        self.log_box.setMinimumHeight(120)
        self.layout.addWidget(self.log_box, 1)

        # 重刷输入与自查控件（默认隐藏，开始重刷后显示）
        self.answer_edit = QLineEdit()
        self.answer_edit.setPlaceholderText("输入答案（选择题填 A/B/C/D）")
        self.answer_edit.setVisible(False)
        self.layout.addWidget(self.answer_edit)
        self.submit_btn.setVisible(False)
        self.good_btn.setVisible(False)
        self.bad_btn.setVisible(False)
        self.session: practice.PracticeSession | None = None

    def refresh(self) -> None:
        self.list_widget.clear()
        r = practice_service.list_wrong_questions()
        if not r.success or r.data is None:
            self.list_widget.addItem(f"❌ {r.message}")
            return
        if not r.data:
            self.list_widget.addItem(r.message)
            return
        for w in r.data:
            self.list_widget.addItem(
                QListWidgetItem(f"{w.course} | {w.type} #{w.no} | 错 {w.wrong_count} 次"))

    def review(self) -> None:
        """错题重刷：逐题作答——选择题自动判分，填空/大题自查，答对移出、答错保留。"""
        r = practice_service.start_wrong_review_session()
        if not r.success or r.data is None:
            self.log_box.clear()
            self.log_box.append(f"❌ {r.message}")
            return
        self.session = r.data
        if self.session.result.total == 0:
            self.log_box.clear()
            self.log_box.append(r.message)
            return
        self.log_box.clear()
        self.log_box.append(f"🔁 {r.message}")
        self.answer_edit.clear()
        self.answer_edit.setVisible(True)
        self.submit_btn.setVisible(True)
        self.show_review_current()

    def show_review_current(self) -> None:
        q = self.session.current
        if q is None:
            res = self.session.finish()
            self.log_box.append(f"=== 错题重刷完成：答对 {res.correct}/{res.answered} ===")
            self.answer_edit.setVisible(False)
            self.submit_btn.setVisible(False)
            self.good_btn.setVisible(False)
            self.bad_btn.setVisible(False)
            self.refresh()
            return
        self.good_btn.setVisible(False)
        self.bad_btn.setVisible(False)
        idx, total = self.session.progress
        self.log_box.append(f"—— 第 {idx + 1}/{total} 题（{q['type']}）——")
        self.log_box.append(q["stem"])
        for opt in q["options"]:
            self.log_box.append(f"  {opt}")
        self.log_box.append("")
        if q["type"] == "选择题":
            self.log_box.append("输入 A/B/C/D 后点「提交答案」。")
        else:
            self.log_box.append("输入你的答案后点「提交答案」，再对照参考答案自查。")

    def submit_review(self) -> None:
        if self.session is None or self.session.current is None:
            return
        answer = self.answer_edit.text().strip()
        q = self.session.current
        if q["type"] == "选择题":
            if not answer:
                self.log_box.append("请先输入答案（A/B/C/D）。")
                return
            r = self.session.submit(answer)
            self.log_box.append(f"判定：{'✓ 答对（已移出错题本）' if r['correct'] else '✗ 答错（保留，继续循环）'}"
                                f"（期望答案：{r['expected']}）")
            self.log_box.append("")
            self.answer_edit.clear()
            self.show_review_current()
        else:
            if not answer:
                self.log_box.append("请先输入你的答案。")
                return
            expected = q.get("answer", "").strip()
            self.log_box.append(f"你的答案：{answer}")
            if expected:
                self.log_box.append(f"参考答案：{expected}")
            self.log_box.append("请对照后点击「我答对了 / 我答错了」自查判分。")
            self.good_btn.setVisible(True)
            self.bad_btn.setVisible(True)

    def self_check(self, correct: bool) -> None:
        if self.session is None or self.session.current is None:
            return
        r = self.session.submit("对" if correct else "错")
        self.log_box.append(f"自查判定：{'✓ 答对（已移出错题本）' if r['correct'] else '✗ 答错（保留，继续循环）'}")
        self.log_box.append("")
        self.answer_edit.clear()
        self.good_btn.setVisible(False)
        self.bad_btn.setVisible(False)
        self.show_review_current()


# ---------------- 期末冲刺页 ----------------

class FinalsPage(BasePage):
    def __init__(self) -> None:
        super().__init__()
        title = QLabel("期末冲刺")
        title.setObjectName("pageTitle")
        self.layout.addWidget(title)

        top = HBox = QHBoxLayout()
        self.course_box = QComboBox()
        self.course_box.addItems(list(COURSES.keys()))
        self.outline_btn = QPushButton("生成复习提纲")
        self.outline_btn.clicked.connect(self.outline)
        self.dash_btn = QPushButton("进度看板")
        self.dash_btn.clicked.connect(self.dashboard)
        top.addWidget(QLabel("课程："))
        top.addWidget(self.course_box)
        top.addWidget(self.outline_btn)
        top.addWidget(self.dash_btn)
        top.addStretch()
        self.layout.addLayout(top)

        self.log_box = QTextEdit()
        self.log_box.setObjectName("logBox")
        self.log_box.setReadOnly(True)
        self.log_box.setMinimumHeight(120)
        self.layout.addWidget(self.log_box, 1)

    def outline(self) -> None:
        self.log_box.clear()
        r = dashboard_service.generate_review_outline(self.course_box.currentText())
        if not r.success or r.data is None:
            self.log_box.append(f"❌ {r.message}")
            return
        o = r.data
        self.log_box.append(f"== {o.course} 复习提纲 ==")
        for c in o.chapters:
            self.log_box.append(f"\n【{c.book}】")
            for item in c.items:
                self.log_box.append(f"  - {item}")
        if o.ai_available and o.ai_summary:
            self.log_box.append("\n【AI 重点提炼】\n" + o.ai_summary)
        else:
            self.log_box.append("\n（本地 AI 未启用，暂不自动生成重点/易考点提炼）")

    def dashboard(self) -> None:
        self.log_box.clear()
        r = dashboard_service.build_dashboard()
        if not r.success or r.data is None:
            self.log_box.append(f"❌ {r.message}")
            return
        d = r.data
        self.log_box.append("== 学习进度看板 ==")
        for course in COURSES:
            chunks = d.course_chunks.get(course, 0)
            qcount = d.question_bank.get(course, 0)
            wcount = d.wrong_book.get(course, 0)
            self.log_box.append(f"\n【{course}】教材块 {chunks} | 题库 {qcount} 题 | 错题 {wcount} 道")
        self.log_box.append(f"\nWord 版教材 {d.textbook_docx} 个 | 批注归档 {d.annotations} 个")
        self.log_box.append(f"本地 AI：{'已启用' if d.ai_available else '未启用'}")


# ---------------- 主窗口 ----------------

class LogoLabel(QLabel):
    """LOGO 环：悬停时脉冲呼吸（签名元素动画）。"""

    def __init__(self, text: str) -> None:
        super().__init__(text)
        self.setObjectName("logo")
        self.setFixedSize(52, 52)
        self.setAlignment(Qt.AlignCenter)
        self._hovered = False

    def enterEvent(self, event) -> None:
        self._hovered = True
        pulse(self)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        super().leaveEvent(event)


# ---------------- 侧栏自动隐藏（窗口级鼠标轮询） ----------------

class MainWindow(QMainWindow):
    SIDEBAR_W = 170      # 展开宽度
    SIDEBAR_DUR = 180    # 动画时长 ms
    HOVER_POLL_MS = 60   # 鼠标位置轮询间隔
    EXPAND_ZONE = 24     # 展开感应区宽度（蓝色竖线附近）

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("大学生课程学习辅助软件")
        self.resize(1080, 720)

        # ---- 布局：QHBoxLayout（侧栏收起宽度 0，stack 占满剩余 → 真全屏）----
        central = QWidget()
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ---- 蓝色竖线提示（收起时可见：提示鼠标移到这里可展开侧栏）----
        self.sidebar_hint = QWidget()
        self.sidebar_hint.setObjectName("sidebarHint")
        self.sidebar_hint.setFixedWidth(6)
        self.sidebar_hint.setCursor(Qt.PointingHandCursor)
        root_layout.addWidget(self.sidebar_hint)

        # ---- 侧栏（书脊签名：LOGO 环 + 导航 + 版本）----
        self.sidebar_wrap = QWidget()
        self.sidebar_wrap.setObjectName("sidebarWrap")
        sidebar_layout = QVBoxLayout(self.sidebar_wrap)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)

        logo = LogoLabel("学")
        sidebar_layout.addSpacing(14)
        sidebar_layout.addWidget(logo, 0, Qt.AlignHCenter)

        self.nav = QListWidget()
        self.nav.setObjectName("sidebar")
        self.nav.addItems(["首页", "资料管理", "自学", "刷题", "错题本", "期末冲刺"])
        self.nav.setFixedWidth(158)
        sidebar_layout.addSpacing(14)
        sidebar_layout.addWidget(self.nav)

        sidebar_footer = QLabel("大学生软件 v0.5")
        sidebar_footer.setObjectName("sidebarFooter")
        sidebar_layout.addWidget(sidebar_footer, 0, Qt.AlignHCenter)
        sidebar_layout.addStretch()

        self.stack = QStackedWidget()
        self.home_page = HomePage()
        self.pages = {
            "首页": self.home_page,
            "资料管理": MaterialsPage(),
            "自学": StudyPage(),
            "刷题": PracticePage(),
            "错题本": WrongBookPage(),
            "期末冲刺": FinalsPage(),
        }
        for name, page in self.pages.items():
            self.stack.addWidget(page)
        self.home_page.on_goto = self._goto_page

        # 侧栏在前、stack 弹性占满剩余（收起时 stack 全屏）
        root_layout.addWidget(self.sidebar_wrap)
        root_layout.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        # ---- 侧栏宽度动画（同步 min/max，避免布局抖动）----
        self._anim_max = QPropertyAnimation(self.sidebar_wrap, b"maximumWidth", self)
        self._anim_min = QPropertyAnimation(self.sidebar_wrap, b"minimumWidth", self)
        for a in (self._anim_max, self._anim_min):
            a.setDuration(self.SIDEBAR_DUR)
            a.setEasingCurve(QEasingCurve.OutCubic)

        self._expanded = False

        # 页面切换：淡入动画（刻意编排，仅切换时一次）
        def on_nav_change(row: int) -> None:
            self.stack.setCurrentIndex(row)
            page = self.stack.currentWidget()
            # 进入首页时刷新进度数据
            if isinstance(page, HomePage):
                page.refresh()
            fade_in(page)

        self.nav.currentRowChanged.connect(on_nav_change)
        self.nav.setCurrentRow(0)  # 默认首页

        # ---- 鼠标位置轮询：左侧原侧栏区域 → 展开；其他区域 → 收起 ----
        self._hover_timer = QTimer(self)
        self._hover_timer.timeout.connect(self._poll_hover)
        self._hover_timer.start(self.HOVER_POLL_MS)

        # 初始收起（不经动画直接归零宽度 → 内容区全屏）
        self._anim_max.stop()
        self._anim_min.stop()
        self.sidebar_wrap.setMinimumWidth(0)
        self.sidebar_wrap.setMaximumWidth(0)
        self._expanded = False

    # ---- 页面快捷跳转（首页按钮用） ----

    def _goto_page(self, name: str, course: str | None = None) -> None:
        """页面快捷跳转（首页按钮 / 课程卡用）。

        `course` 非空时顺带把它带进目标页 —— 自学页没有课程下拉框，
        课程只能这样传进去（页面上要提供 `set_course` 才生效）。
        """
        if name not in self.pages:
            return
        page = self.pages[name]
        if course and hasattr(page, "set_course"):
            page.set_course(course)
        self.nav.setCurrentRow(list(self.pages.keys()).index(name))

    # ---- 展开 / 收起 ----

    def _expand_sidebar(self) -> None:
        if self._expanded:
            return
        self._expanded = True
        end = self.SIDEBAR_W
        for a in (self._anim_max, self._anim_min):
            a.stop()
            a.setStartValue(self.sidebar_wrap.width())
            a.setEndValue(end)
            a.start()

    def _collapse_sidebar(self) -> None:
        if not self._expanded:
            return
        self._expanded = False
        for a in (self._anim_max, self._anim_min):
            a.stop()
            a.setStartValue(self.sidebar_wrap.width())
            a.setEndValue(0)
            a.start()

    def _poll_hover(self) -> None:
        """每 60ms 检查鼠标位置，三段式感应：

        - x < EXPAND_ZONE（竖线附近）→ 展开侧栏
        - x >= SIDEBAR_W+10（明显在内容区）→ 收起侧栏
        - 中间滞回区 → 保持当前状态（防止边缘抖动，且内容区按钮不受影响）
        """
        if not self.isVisible():
            return
        pos = self.mapFromGlobal(QCursor.pos())
        if not self.rect().contains(pos):
            self._collapse_sidebar()
            return
        x = pos.x()
        if x < self.EXPAND_ZONE:
            self._expand_sidebar()
        elif x >= self.SIDEBAR_W + 10:
            self._collapse_sidebar()
        # 滞回区（EXPAND_ZONE ≤ x < SIDEBAR_W+10）：保持当前状态


def main() -> int:
    ensure_data_dirs()
    app = QApplication(sys.argv)
    # 应用深色 QPalette（让 QMessageBox 等原生对话框在深色 QSS 下颜色正确）
    from ui.style import DARK_PALETTE
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(DARK_PALETTE["window"]))
    palette.setColor(QPalette.WindowText, QColor(DARK_PALETTE["windowText"]))
    palette.setColor(QPalette.Base, QColor(DARK_PALETTE["base"]))
    palette.setColor(QPalette.AlternateBase, QColor(DARK_PALETTE["alternateBase"]))
    palette.setColor(QPalette.Text, QColor(DARK_PALETTE["text"]))
    palette.setColor(QPalette.Button, QColor(DARK_PALETTE["button"]))
    palette.setColor(QPalette.ButtonText, QColor(DARK_PALETTE["buttonText"]))
    palette.setColor(QPalette.Highlight, QColor(DARK_PALETTE["highlight"]))
    palette.setColor(QPalette.HighlightedText, QColor(DARK_PALETTE["highlightedText"]))
    palette.setColor(QPalette.Link, QColor(DARK_PALETTE["link"]))
    palette.setColor(QPalette.PlaceholderText, QColor(DARK_PALETTE["placeholderText"]))
    app.setPalette(palette)
    app.setStyleSheet(STYLE)
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
