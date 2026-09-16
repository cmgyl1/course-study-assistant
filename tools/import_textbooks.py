"""教材一键导入脚本：扫描 data/textbooks/ 下的 PDF/Office 文件，
自动转换为 Markdown → 入库知识库（向量化）→ 可选生成 Word 版教材。

用法：
    python tools/import_textbooks.py                # 导入全部
    python tools/import_textbooks.py --course 计算机网络   # 只导入指定课程
    python tools/import_textbooks.py --dry-run      # 只列出待导入文件
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from engine.config import (
    ensure_data_dirs, TEXTBOOKS_DIR, TEXTBOOKS_MD_DIR, COURSES,
)
from engine.converter import convert_file, ConversionError
from engine.knowledge_base import ingest_textbook
from engine.study import generate_docx_textbook

SUPPORTED_EXTS = {".pdf", ".docx", ".doc", ".pptx", ".ppt", ".txt", ".md", ".epub"}


def guess_course(filename: str) -> str:
    """根据文件名猜测课程（匹配课程名关键词）。"""
    for course in COURSES:
        if course in filename:
            return course
    # 常见别名
    aliases = {
        "计算机网络": ["网络", "谢希仁"],
        "UML面向对象分析与设计": ["uml", "面向对象", "谭火彬"],
        "软件工程导论": ["软件工程", "薛继伟"],
        "算法设计与分析": ["算法", "算法设计"],
    }
    lower = filename.lower()
    for course, keys in aliases.items():
        if any(k in lower for k in keys):
            return course
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description="教材一键导入")
    parser.add_argument("--course", default="", help="只导入指定课程")
    parser.add_argument("--dry-run", action="store_true", help="只列出不执行")
    args = parser.parse_args()

    ensure_data_dirs()
    files = sorted(
        f for f in TEXTBOOKS_DIR.iterdir()
        if f.suffix.lower() in SUPPORTED_EXTS
    )
    if args.course:
        files = [f for f in files if guess_course(f.name) == args.course]

    if not files:
        print("没有找到待导入文件。请把教材 PDF/文档放入：")
        print(f"  {TEXTBOOKS_DIR}")
        print("（详见 docs/工程操作规范.md §2.6 数据来源与合法渠道）")
        return 0

    print(f"发现 {len(files)} 个文件：")
    for f in files:
        course = guess_course(f.name) or "（未识别课程，默认" + list(COURSES.keys())[0] + "）"
        print(f"  - {f.name}  →  {course}")
    if args.dry_run:
        return 0

    ok_count = 0
    for f in files:
        course = guess_course(f.name) or list(COURSES.keys())[0]
        try:
            md = convert_file(f, TEXTBOOKS_MD_DIR)
            n = ingest_textbook(md, course, f.stem)
            docx = generate_docx_textbook(md)  # 生成 Word 版供批注
            print(f"[OK] {f.name} → {md.name}（{n} 块入库）→ {docx.name}")
            ok_count += 1
        except ConversionError as e:
            print(f"[失败] {f.name}: {e}")

    print(f"\n完成：成功 {ok_count}/{len(files)}。可在软件『自学-知识树』查看。")
    return 0 if ok_count == len(files) else 1


if __name__ == "__main__":
    sys.exit(main())
