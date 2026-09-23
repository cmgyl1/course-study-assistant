"""UI 样式层：深色 SaaS 「墨蓝夜空 + 高亮数字」设计系统（v0.5 重大升级）。

升级要点（参照深色 SaaS 产品 + WCAG AAA 文本对比度）：
- 主色背景：深墨蓝 #0F1418（不是纯黑），避免呆板、护眼；
- 卡片背景：#1A2230，与主背景形成清晰层次；
- 主文本：#E4E8EE（强对比度 13:1，远超 WCAG AA 4.5:1）；
- 60-30-10 配色：深蓝灰主色 60% + 蓝高亮 30% + SAGE 绿/GOLD 金点缀 10%；
- 侧栏保留智慧型收起逻辑，竖向墨蓝渐变（#152130 → #1F2C3D）；
- 首页新增 KPI 大数字卡 / 课程卡 4 列网格（新 objectName）；
- 强烈蓝色高亮（#5A8DD6）用作主按钮 / 选中态，强可识别；
- 类型层级：页标题 22px/300 → 组标题 13px/600 → 正文 13px → 辅助 11.5px。

换肤/换前端只需替换本层；任何业务逻辑都不在此文件。
"""
from __future__ import annotations

# ---- 配色 token（v0.5 深色 SaaS）----
# 背景层级
BG = "#0F1418"          # 主背景（深墨蓝，非纯黑）
BG_DEEP = "#161C24"     # 二级背景（对话框、分组区）
CARD = "#1A2230"        # 卡片背景
CARD_HOVER = "#222C3D"  # 卡片 hover

# 文本层级
TEXT = "#E4E8EE"        # 主文本（高对比度）
TEXT_SOFT = "#A8B0BB"   # 次级文本
TEXT_MUTED = "#7A8390"  # 辅助文本（更高亮度，深背景下重要）

# 品牌主色：明亮蓝
PRIMARY = "#5A8DD6"        # 主按钮 / 链接
PRIMARY_HOVER = "#6FA0E0"  # hover
PRIMARY_PRESSED = "#4878B6"  # pressed
PRIMARY_DEEP = "#3A5E96"   # 主色变深（用于选中态深背景）

# 侧栏（保留墨蓝渐变，更深版本以匹配深色背景）
SIDEBAR_TOP = "#152130"
SIDEBAR_BOTTOM = "#1F2C3D"
SIDEBAR_ITEM_HOVER = "#243246"

# 成功 / 警示（SAGE 绿 + GOLD 金，在深背景上要更亮）
SAGE = "#7AD18A"          # 正确/成功
SAGE_SOFT = "#1F2D24"     # 成功背景（暗绿）
GOLD = "#E0B266"          # 警示/错误
GOLD_SOFT = "#2C2618"     # 警示背景（暗金）

# 边框线 / 分割线
LINE = "#2A3340"          # 卡片边框
LINE_STRONG = "#3A4452"   # 强调边框
SELECTION_BG = "#1F2D44"  # 列表选中
HOVER_BG = "#232C3A"      # 通用 hover


# ---- 全局 QSS ----
STYLE = f"""
/* ===== 全局 ===== */
QMainWindow, QWidget#contentArea {{
    background: {BG};
}}
QWidget {{
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", "DengXian", "Segoe UI", sans-serif;
    font-size: 13px;
    color: {TEXT};
}}
QToolTip {{
    background: {PRIMARY};
    color: #FFFFFF;
    border: none;
    border-radius: 4px;
    padding: 6px 10px;
    font-size: 12px;
}}
QMessageBox {{
    background: {CARD};
    color: {TEXT};
}}

/* ===== 页面标题（层级 1） ===== */
QLabel#pageTitle {{
    font-family: "Microsoft YaHei UI";
    font-size: 22px;
    font-weight: 300;
    color: {TEXT};
    padding: 2px 0 12px 0;
    letter-spacing: 0.5px;
}}
QLabel#pageSubtitle {{
    font-size: 12px;
    color: {TEXT_SOFT};
    padding: 0 0 8px 0;
}}

/* ===== 侧栏（书脊：墨蓝渐变） ===== */
QListWidget#sidebar {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 {SIDEBAR_TOP}, stop:1 {SIDEBAR_BOTTOM});
    border: none;
    padding: 10px 0;
    outline: none;
}}
QListWidget#sidebar::item {{
    color: #A8B0BB;
    padding: 12px 20px;
    border-left: 3px solid transparent;
    font-size: 13px;
}}
QListWidget#sidebar::item:hover {{
    background: {SIDEBAR_ITEM_HOVER};
    color: {TEXT};
}}
QListWidget#sidebar::item:selected {{
    background: rgba(90, 141, 214, 0.20);
    color: {TEXT};
    border-left: 3px solid {SAGE};
    font-weight: 600;
}}
QLabel#logo {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {PRIMARY_DEEP}, stop:1 {PRIMARY});
    color: #FFFFFF;
    font-family: "Microsoft YaHei UI";
    font-size: 22px;
    font-weight: 400;
    border-radius: 26px;
    border: 2px solid {SAGE};
}}
QLabel#sidebarFooter {{
    color: {TEXT_MUTED};
    font-size: 10px;
    padding: 8px 0;
}}
/* 蓝色竖线提示（侧栏收起时可见） */
QWidget#sidebarHint {{
    background: {PRIMARY};
    border: none;
}}
QWidget#sidebarHint:hover {{
    background: {PRIMARY_HOVER};
}}

/* ===== 分组卡片 ===== */
QGroupBox {{
    background: {CARD};
    border: 1px solid {LINE};
    border-left: 3px solid {PRIMARY};
    border-radius: 8px;
    margin-top: 12px;
    padding: 14px 12px 12px 12px;
    font-size: 13px;
    color: {TEXT};
}}
QGroupBox:hover {{
    border-color: {LINE_STRONG};
    background: {CARD_HOVER};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 8px;
    color: {PRIMARY};
    font-size: 13px;
    font-weight: 600;
    background: {CARD};
}}

/* ===== KPI 大数字卡（首页独有，v0.5 新增） ===== */
QWidget#kpiCard {{
    background: {CARD};
    border: 1px solid {LINE};
    border-radius: 10px;
    padding: 0;
}}
QWidget#kpiCard:hover {{
    border: 1px solid {PRIMARY};
    background: {CARD_HOVER};
}}
QLabel#kpiLabel {{
    color: {TEXT_SOFT};
    font-size: 12px;
    font-weight: 500;
    padding: 14px 18px 0 18px;
}}
QLabel#kpiNumber {{
    color: {PRIMARY};
    font-family: "Microsoft YaHei UI";
    font-size: 32px;
    font-weight: 300;
    padding: 4px 18px 14px 18px;
    letter-spacing: 1px;
}}
QLabel#kpiUnit {{
    color: {TEXT_MUTED};
    font-size: 12px;
    padding: 4px 18px 14px 4px;
}}
QLabel#kpiNumberGold {{
    color: {GOLD};
    font-family: "Microsoft YaHei UI";
    font-size: 32px;
    font-weight: 300;
    padding: 4px 18px 14px 18px;
    letter-spacing: 1px;
}}
QLabel#kpiNumberSage {{
    color: {SAGE};
    font-family: "Microsoft YaHei UI";
    font-size: 32px;
    font-weight: 300;
    padding: 4px 18px 14px 18px;
    letter-spacing: 1px;
}}

/* ===== 课程卡（首页独有，v0.5 新增） ===== */
QWidget#courseCard {{
    background: {CARD};
    border: 1px solid {LINE};
    border-radius: 10px;
    padding: 14px 16px;
}}
QWidget#courseCard:hover {{
    border: 1px solid {PRIMARY};
    background: {CARD_HOVER};
}}
QLabel#courseName {{
    color: {TEXT};
    font-size: 15px;
    font-weight: 600;
    padding: 0 0 8px 0;
}}
QLabel#courseStat {{
    color: {TEXT_MUTED};
    font-size: 12px;
    padding: 2px 0;
}}
QLabel#courseStatNum {{
    color: {PRIMARY};
    font-size: 13px;
    font-weight: 600;
}}

/* ===== 按钮 ===== */
QPushButton {{
    background: {PRIMARY};
    color: #FFFFFF;
    border: none;
    border-radius: 6px;
    padding: 8px 18px;
    font-size: 13px;
}}
QPushButton:hover {{
    background: {PRIMARY_HOVER};
}}
QPushButton:pressed {{
    background: {PRIMARY_PRESSED};
}}
QPushButton:disabled {{
    background: {LINE_STRONG};
    color: {TEXT_MUTED};
}}
QPushButton#secondary {{
    background: {CARD};
    color: {TEXT};
    border: 1px solid {LINE_STRONG};
}}
QPushButton#secondary:hover {{
    border-color: {PRIMARY};
    background: {HOVER_BG};
    color: {TEXT};
}}
QPushButton#success {{
    background: {SAGE};
    color: #0F1B12;
    font-weight: 600;
}}
QPushButton#success:hover {{
    background: #8DDF9B;
}}
QPushButton#danger {{
    background: {GOLD};
    color: #2A1E0A;
    font-weight: 600;
}}
QPushButton#danger:hover {{
    background: #EBC182;
}}

/* ===== 输入控件 ===== */
QLineEdit, QComboBox, QSpinBox, QTextEdit {{
    background: {CARD};
    border: 1px solid {LINE_STRONG};
    border-radius: 6px;
    padding: 7px 10px;
    font-size: 13px;
    min-height: 18px;
    color: {TEXT};
    selection-background-color: {PRIMARY};
    selection-color: #FFFFFF;
}}
QLineEdit:hover, QComboBox:hover, QSpinBox:hover {{
    border-color: {PRIMARY};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QTextEdit:focus {{
    border: 1px solid {PRIMARY};
    background: {CARD_HOVER};
}}
QComboBox::drop-down {{
    border: none;
    width: 24px;
}}
QComboBox QAbstractItemView {{
    background: {CARD};
    border: 1px solid {LINE_STRONG};
    border-radius: 6px;
    selection-background-color: {PRIMARY};
    selection-color: #FFFFFF;
    padding: 4px;
    color: {TEXT};
}}
QSpinBox::up-button, QSpinBox::down-button {{
    width: 18px;
    border: none;
    background: transparent;
}}

/* ===== 日志/文本区 ===== */
QTextEdit#logBox, QTextEdit#logBox:focus {{
    background: {BG_DEEP};
    border: 1px solid {LINE};
    border-radius: 8px;
    padding: 14px 16px;
    font-size: 13px;
    color: {TEXT};
    selection-background-color: {PRIMARY};
    selection-color: #FFFFFF;
}}

/* ===== 列表 / 树 ===== */
QListWidget, QTreeWidget {{
    background: {CARD};
    border: 1px solid {LINE};
    border-radius: 8px;
    padding: 6px;
    outline: none;
    font-size: 13px;
    color: {TEXT};
}}
QListWidget::item, QTreeWidget::item {{
    padding: 7px 10px;
    border-radius: 4px;
    color: {TEXT};
}}
QListWidget::item:hover, QTreeWidget::item:hover {{
    background: {HOVER_BG};
}}
QListWidget::item:selected, QTreeWidget::item:selected {{
    background: {SELECTION_BG};
    color: {PRIMARY};
    font-weight: 500;
}}
QTreeWidget::branch {{
    background: transparent;
}}
QHeaderView::section {{
    background: {CARD_HOVER};
    border: none;
    border-bottom: 1px solid {LINE};
    padding: 7px 10px;
    color: {TEXT_SOFT};
    font-weight: 600;
    font-size: 12.5px;
}}

/* ===== 滚动条（轻量细窄） ===== */
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {LINE_STRONG};
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {PRIMARY};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 8px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: {LINE_STRONG};
    border-radius: 4px;
    min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {PRIMARY};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}
/* ===== 状态小标签（保留兼容） ===== */
QLabel#statusOk {{
    color: {SAGE};
    font-size: 13px;
}}
QLabel#statusWarn {{
    color: {GOLD};
    font-size: 13px;
}}
/* ===== 自学页（v0.5.1：版式对齐离线阅读器 data/reader.html） =====
   reader 的 token 与本文件同族（--bg:#0f1115 / --panel:#161a21 /
   --accent:#5a8dd6 / --gold:#e0b266），这里直接复用现有变量，不另起一套配色。 */
QLabel#studyTitle {{
    color: {TEXT};
    font-size: 16px;
    font-weight: 600;
    padding-right: 6px;
}}
QLineEdit#studyQuery {{
    background: {BG_DEEP};
    border: 1px solid {LINE};
    border-radius: 8px;
    padding: 9px 14px;
}}
QLineEdit#studyQuery:focus {{
    border-color: {PRIMARY};
    background: {BG_DEEP};
}}
QLabel#studyHint {{
    color: {TEXT_MUTED};
    font-size: 12px;
}}
/* 左栏章节树（reader 的 aside：书名金色分组 + 章亮 / 节灰） */
QTreeWidget#studyTree {{
    background: {BG_DEEP};
    border: 1px solid {LINE};
    border-radius: 8px;
    padding: 8px 6px;
}}
QTreeWidget#studyTree::item {{
    padding: 4px 8px;
    border-radius: 6px;
}}
QTreeWidget#studyTree::item:selected {{
    background: {PRIMARY};
    color: #FFFFFF;
}}
/* 结果区：卡片直接浮在背景上，所以列表本身不能有卡片底与边框 */
QListWidget#resultList {{
    background: transparent;
    border: none;
    padding: 0;
}}
QListWidget#resultList::item {{
    padding: 0;
    border-radius: 10px;
}}
QLabel#resultGroup {{
    color: #CFE0F5;
    font-size: 15px;
    font-weight: 600;
    padding: 10px 2px 2px 2px;
}}
/* 单张结果卡（reader 的 .card） */
QFrame#resultCard {{
    background: {CARD};
    border: 1px solid {LINE};
    border-radius: 10px;
}}
QFrame#resultCard:hover {{
    border-color: {PRIMARY};
}}
QLabel#cardTitle {{
    color: #CFE0F5;
    font-size: 14px;
    font-weight: 600;
}}
QLabel#cardMeta {{
    color: {TEXT_MUTED};
    font-size: 12px;
}}
QLabel#cardPreview {{
    color: #C9D2DE;
    font-size: 13px;
}}
QLabel#cardBadge {{
    color: {GOLD};
    font-size: 12px;
}}
"""


# ---- 默认 QPalette（避免某些控件在深色 QSS 下颜色出错）----
DARK_PALETTE = {
    "window": BG,
    "windowText": TEXT,
    "base": BG_DEEP,
    "alternateBase": CARD,
    "text": TEXT,
    "button": CARD,
    "buttonText": TEXT,
    "brightText": "#FF8888",
    "highlight": PRIMARY_DEEP,
    "highlightedText": TEXT,
    "link": PRIMARY,
    "placeholderText": TEXT_MUTED,
}
