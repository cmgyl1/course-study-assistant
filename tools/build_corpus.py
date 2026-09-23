"""从合并后的教材 Markdown 构建检索语料（切块 + 索引持久化）。

用法：
    python tools/build_corpus.py --course 计算机网络
    python tools/build_corpus.py --course 计算机网络 --md "计算机网络（第8版）_谢希仁_上半.md"

输出 data/corpus_cache/corpus.json：
    每块含 {id, text, section_path, page_no, doc_title, source_file, course, is_title}
    其中 is_title=True 的是"章节入口块"，供标题索引使用。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from engine.config import TEXTBOOKS_MD_DIR, CORPUS_CACHE_DIR
from engine.retrieval import build_from_markdown_files, save_corpus, Retriever


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--course", default="计算机网络")
    parser.add_argument("--md", nargs="*", default=None,
                        help="Markdown 文件名，默认取 TEXTBOOKS_MD_DIR 下全部教材文件")
    parser.add_argument("--out", default="corpus.json")
    args = parser.parse_args()

    if args.md:
        md_files = [TEXTBOOKS_MD_DIR / name for name in args.md]
    else:
        # 排除课件版（PPT 摘要不是教材原文）
        md_files = [p for p in sorted(TEXTBOOKS_MD_DIR.glob("*.md")) if "课件版" not in p.name]

    md_files = [p for p in md_files if p.exists()]
    if not md_files:
        print(f"未找到可用教材 Markdown（{TEXTBOOKS_MD_DIR}）")
        return 1

    print("语料来源：")
    for p in md_files:
        print(f"  - {p.name}（{p.stat().st_size // 1024} KB）")

    chunks = build_from_markdown_files(md_files, course=args.course)
    CORPUS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    out_path = CORPUS_CACHE_DIR / args.out
    save_corpus(chunks, out_path)

    stats = Retriever(chunks).stats()
    print(f"\n切块完成 → {out_path}")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
