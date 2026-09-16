# -*- coding: utf-8 -*-
"""知识库重建脚本：清洗教材源文件（剔除 PPT 页眉页脚残留）→ 重建向量库。

用法：
    python tools/rebuild_knowledge_base.py          # 全量重建
    python tools/rebuild_knowledge_base.py --dry-run # 只报告将受影响的内容，不写入

说明：
- 入库前会先删除旧块（ingest_textbook 内置防残留逻辑），本脚本额外做整库重建；
- 对源 md 应用 _strip_slide_chrome 清洗（谢希仁 编著 / 计算机网络（第8版）/
  课件制作人： / 裸"第 X 章"行），并写回 textbooks_md（知识树与 Word 教材同步受益）。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from engine.config import TEXTBOOKS_MD_DIR
from engine.knowledge_base import (
    ingest_textbook,
    _strip_slide_chrome,
    _get_client,
    TEXTBOOK_COLLECTION,
    NGramEmbeddingFunction,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="知识库重建")
    parser.add_argument("--dry-run", action="store_true", help="只报告不写入")
    args = parser.parse_args()

    mds = sorted(TEXTBOOKS_MD_DIR.glob("*.md"))
    print(f"发现 {len(mds)} 个教材源文件")

    removed_total = 0
    for md in mds:
        original = md.read_text(encoding="utf-8")
        cleaned = _strip_slide_chrome(original)
        if cleaned != original:
            removed = sum(
                1 for l in original.splitlines() if l.strip() and l.strip() not in cleaned.splitlines()
            )
            removed_total += 1
            print(f"  [清洗] {md.name}: 源文件含页眉页脚残留，待清理后重建")
            if not args.dry_run:
                md.write_text(cleaned, encoding="utf-8")
        else:
            print(f"  [OK]   {md.name}: 源文件无需清洗")

    if args.dry_run:
        print("--dry-run：未写入任何内容。")
        return 0

    # 整库重建：删除 textbooks 集合 → 重新入库
    client = _get_client()
    try:
        client.delete_collection(TEXTBOOK_COLLECTION)
        print("[重建] 已删除旧集合 textbooks")
    except Exception:
        print("[重建] 集合不存在或删除失败，将重建")

    total = 0
    for md in mds:
        course = "计算机网络" if "计算机" in md.name else "未分类"
        n = ingest_textbook(md, course, md.stem)
        total += n
        print(f"  [入库] {md.name} → {n} 块（course={course}）")

    # 验证
    coll = client.get_or_create_collection(
        name=TEXTBOOK_COLLECTION, embedding_function=NGramEmbeddingFunction()
    )
    print(f"[完成] 新知识库共 {coll.count()} 块")
    return 0


if __name__ == "__main__":
    sys.exit(main())
