"""大学生课程学习辅助软件 - 主程序入口（PySide6 朴素界面）。

界面结构：左侧导航（资料管理 / 自学 / 刷题 / 错题本 / 期末冲刺）
+ 右侧功能页。先核心后美化：UI 与引擎通过 service 层解耦，后续可整体替换。
"""
from __future__ import annotations

import sys
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
    QGroupBox, QFormLayout, QFrame, QSizePolicy,
)
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QColor, QFont, QBrush, QCursor, QPalette

from engine.config import ensure_data_dirs, COURSES
from engine import practice  # 仅用于 PracticeSession 类型注解
from ui.style import STYLE, DARK_PALETTE
from ui.animations import fade_in, pulse
from services import materials_service, study_service, practice_service, dashboard_service


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
    """单课程卡片：课程名 + 教材块数 + 题库数。"""

    def __init__(self, course_name: str) -> None:
        super().__init__()
        self.setObjectName("courseCard")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(96)
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


class HomePage(BasePage):
    """欢迎主界面：欢迎语 + 快捷入口 + KPI 大数字块 + 4 列课程卡。"""

    def __init__(self, on_goto: callable | None = None) -> None:
        super().__init__()
        self.on_goto = on_goto or (lambda name: None)
        self.layout.setContentsMargins(32, 28, 32, 28)
        self.layout.setSpacing(18)

        # 欢迎区
        welcome = QLabel("欢迎使用大学生课程学习辅助软件")
        welcome.setObjectName("pageTitle")
        self.layout.addWidget(welcome)

        subtitle = QLabel(
            "本地知识库 · 教材权威依据 · 自学 / 刷题 / 期末冲刺 一站式学习工作台")
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
        self.kpi_chunks = _KpiCard("教材块 · 入库知识片段", "kpiNumber")
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
            card = _CourseCard(course)
            self.course_cards[course] = card
            row, col = divmod(idx, 4)
            course_grid.addWidget(card, row, col)
        # 占位让网格靠左
        course_grid.setColumnStretch(4, 1)
        self.layout.addLayout(course_grid)
        self.layout.addStretch()

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
        grp = QGroupBox("教材导入（PDF → Markdown → 知识库）")
        form = QFormLayout(grp)
        self.md_btn = QPushButton("选择教材 PDF/文档并转换入库")
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


# ---------------- 自学页 ----------------

class StudyPage(BasePage):
    def __init__(self) -> None:
        super().__init__()
        title = QLabel("课前课后自学")
        title.setObjectName("pageTitle")
        self.layout.addWidget(title)

        top = QHBoxLayout()
        self.course_box = QComboBox()
        self.course_box.addItems(list(COURSES.keys()))
        self.refresh_btn = QPushButton("刷新知识树")
        self.refresh_btn.clicked.connect(self.refresh_tree)
        top.addWidget(QLabel("课程："))
        top.addWidget(self.course_box)
        top.addWidget(self.refresh_btn)
        top.addStretch()
        self.layout.addLayout(top)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("教材知识树")
        self.tree.setMinimumHeight(150)
        self.tree.itemClicked.connect(self.on_tree_click)
        self.layout.addWidget(self.tree, 2)

        grp = QGroupBox("知识点讲解（基于教材知识库检索）")
        form = QHBoxLayout(grp)
        self.query_edit = QLineEdit()
        self.query_edit.setPlaceholderText("输入知识点，如：物理层 比特流 / TCP 三次握手")
        self.ask_btn = QPushButton("讲解")
        self.ask_btn.clicked.connect(self.ask)
        form.addWidget(self.query_edit)
        form.addWidget(self.ask_btn)
        self.layout.addWidget(grp)

        # 自学页要同时显示原文段落与插图 —— 用只读 HTML 浏览器（支持本地图片）
        self.log_box = QTextBrowser()
        self.log_box.setObjectName("logBox")
        self.log_box.setOpenExternalLinks(False)
        self.log_box.setMinimumHeight(120)
        self.layout.addWidget(self.log_box, 1)

    def refresh_tree(self) -> None:
        self.tree.clear()
        r = study_service.get_course_tree(self.course_box.currentText())
        if not r.success:
            self.log(f"❌ {r.message}")
            return
        if not r.data:
            self.log(r.message)
            return
        for root_node in r.data:
            root = QTreeWidgetItem([f"📚 {root_node.book}"])
            root.setForeground(0, QBrush(QColor("#5A8DD6")))
            f = QFont()
            f.setBold(True)
            f.setPointSize(13)
            root.setFont(0, f)
            self._add_nodes(root, root_node)
            self.tree.addTopLevelItem(root)
        self.tree.expandAll()

    def _add_nodes(self, parent: QTreeWidgetItem, node) -> None:
        """递归添加 DTO 节点 → QTreeWidgetItem（知识点小字用金色）。"""
        from services.dto import KnowledgeNode as KN
        item = QTreeWidgetItem([node.title])
        parent.addChild(item)
        # 章节标题样式
        item.setForeground(0, QBrush(QColor("#A8B0BB")))
        if isinstance(node, KN) and node.children:
            for c in node.children:
                self._add_nodes(item, c)
        if isinstance(node, KN) and node.concepts:
            for concept in node.concepts[:8]:
                leaf = QTreeWidgetItem([f"📌 {concept}"])
                leaf.setForeground(0, QBrush(QColor("#E0B266")))
                leaf_font = QFont()
                leaf_font.setPointSize(11)
                leaf.setFont(0, leaf_font)
                item.addChild(leaf)

    def on_tree_click(self, item: QTreeWidgetItem) -> None:
        """点击树节点：知识点 → 检索讲解；章节 → 取章节正文。"""
        text = item.text(0)
        course = self.course_box.currentText()
        if text.startswith("📌"):
            query = text[2:].strip()
            self.query_edit.setText(query)
            self.ask()
            return
        # 章节节点 → 拼出完整路径
        parts = []
        node = item
        while node is not None:
            t = node.text(0)
            if not t.startswith("📌"):
                if t.startswith("📚"):
                    t = t[2:].strip()
                parts.insert(0, t)
            node = node.parent()
        path = " > ".join(parts)
        # 读"保序原文"：标题/段落/插图按原书顺序返回，图落在图题之上 ——
        # 不走 RAG（那会按相关度重排、只取 top-3，位置就全乱了）。
        r = study_service.get_section_reading(path, course)
        self.log_box.clear()
        if not r.success or r.data is None:
            self.log_box.setPlainText(f"❌ {r.message}")
            return
        reading = r.data
        head = (f"【{path}】  {len(reading.blocks)} 块 / {reading.n_figures} 图"
                f"　—　{reading.book}")
        self.log_box.setHtml(
            f'<p style="color:#8a94a6;font-size:12px;margin:0 0 10px">{head}</p>'
            + study_service.render_section_html(reading)
        )
        self.log_box.verticalScrollBar().setValue(0)

    def ask(self) -> None:
        query = self.query_edit.text().strip()
        if not query:
            return
        r = study_service.explain_topic(query, self.course_box.currentText(), top_k=5)
        self.log_box.clear()
        if not r.success or r.data is None:
            self.log_box.append(f"❌ {r.message}")
            return
        data = r.data
        self.log_box.append(f"问题：{data.query}\n")
        for i, ev in enumerate(data.evidence, 1):
            self.log_box.append(f"依据 {i}：{ev.doc_title} | {ev.section_path}")
            self.log_box.append(ev.content[:300] + ("…" if len(ev.content) > 300 else ""))
            self.log_box.append("")
        if data.ai_available and data.answer:
            self.log_box.append("【AI 讲解】\n" + data.answer)
        else:
            self.log_box.append("（本地 AI 未启用，以上为教材原文检索结果）")
        self.log_box.verticalScrollBar().setValue(0)


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

    def _goto_page(self, name: str) -> None:
        if name in self.pages:
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
