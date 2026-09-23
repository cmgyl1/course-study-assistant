"""全局路径配置：所有路径相对于项目根目录（大学生软件/），保证可移植。

关键点：PyInstaller 打包后 __file__ 指向临时解压目录（_MEIxxxx），
必须用 sys.executable（exe 所在位置）向上查找真实项目根，否则 exe
会找不到 data/ 下的教材与题库。源码运行时用 __file__ 推导。
"""
import sys
from pathlib import Path


def _find_project_root() -> Path:
    if getattr(sys, "frozen", False):  # PyInstaller 打包环境
        # exe 位置不固定：2026-09-23 起打包产物直接落在项目根（便于查找），
        # 旧版落在 dist/ 下。两种布局都从 exe 所在目录逐级向上找 data/。
        exe_dir = Path(sys.executable).resolve().parent
        for base in (exe_dir, exe_dir.parent, exe_dir.parent.parent,
                     exe_dir.parent.parent.parent):
            if (base / "data").is_dir():
                return base
        return exe_dir.parent  # 回退：exe 上级目录
    return Path(__file__).resolve().parent.parent.parent  # 源码：大学生软件/


PROJECT_ROOT = _find_project_root()

TOOLS_DIR = PROJECT_ROOT / "tools"
DATA_DIR = PROJECT_ROOT / "data"

# 工具可执行文件
PANDOC_EXE = TOOLS_DIR / "pandoc" / "pandoc-3.6.4" / "pandoc.exe"
SOFFICE_EXE = TOOLS_DIR / "LibreOffice" / "program" / "soffice.exe"

# 数据目录（教材库与题库物理分离）
TEXTBOOKS_DIR = DATA_DIR / "textbooks"          # 教材 PDF 原件
TEXTBOOKS_MD_DIR = DATA_DIR / "textbooks_md"    # 教材 Markdown（转换结果）
TEXTBOOKS_DOCX_DIR = DATA_DIR / "textbooks_docx"  # Word 版教材（批注用）
ANNOTATIONS_DIR = DATA_DIR / "annotations"      # 批注归档
QUESTION_BANKS_DIR = DATA_DIR / "question_banks"  # 题库（分科文档）
WRONG_BOOK_DIR = DATA_DIR / "wrong_book"        # 错题本
MATERIALS_DIR = DATA_DIR / "materials"          # 课件/讲义归档
CORPUS_CACHE_DIR = DATA_DIR / "corpus_cache"    # 检索语料切块缓存（原 chroma 向量库目录，已改用途）
FIGURES_DIR = DATA_DIR / "figures"              # 教材插图（按坐标从 PDF 裁出）
OCR_CACHE_DIR = DATA_DIR / "ocr_cache"          # 每页 OCR 原始框缓存（版面层可秒级重放）

# 课程定义（首批 4 门）
COURSES = {
    "计算机网络": "《计算机网络》第八版 谢希仁",
    "UML面向对象分析与设计": "《UML2 面向对象分析与设计》第二版 谭火彬 清华大学出版社",
    "软件工程导论": "《软件工程导论》薛继伟主编",
    "算法设计与分析": "《算法设计与分析》第三版",
}


def ensure_data_dirs() -> None:
    """确保所有数据目录存在。"""
    for d in (TEXTBOOKS_DIR, TEXTBOOKS_MD_DIR, TEXTBOOKS_DOCX_DIR,
              ANNOTATIONS_DIR, QUESTION_BANKS_DIR, WRONG_BOOK_DIR,
              MATERIALS_DIR, CORPUS_CACHE_DIR, FIGURES_DIR, OCR_CACHE_DIR):
        d.mkdir(parents=True, exist_ok=True)
