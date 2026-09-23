# -*- coding: utf-8 -*-
"""探针：对比**软件自学页**与**离线阅读器**两条检索路径的实际表现。

背景：用户实测反馈"reader 查得准，软件一般般"。但两条路径在代码里是分开的：

  A. 软件自学页  src/main.py → study_service.explain_topic
                 → engine.study.explain_topic → engine.knowledge_base.search_textbook
                 → chromadb + NGramEmbeddingFunction（字符 1/2/3-gram 哈希，余弦距离）

  B. 离线阅读器  tools/build_reader.py → engine.retrieval（BM25 + 标题索引
                 + AND 降级 OR + 两条拒答判据），语料 Python 预计算后内嵌 HTML

本脚本把两条路对同一批查询的 top-5 结果并排打出来，作为改判据的第一手证据。
只读，不写任何数据。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from engine import knowledge_base as kb                      # noqa: E402
from engine import textbook_reader as reader                 # noqa: E402
from engine.retrieval import Retriever, build_from_markdown_files  # noqa: E402

COURSE = "计算机网络"
QUERIES = [
    "物理层",
    "三次握手",
    "量子纠缠",              # 全库 DF=0，应拒答
    "双绞线 薛定谔",         # 部分词命中
    "CSMA/CD",
    "TCP 拥塞控制",
    "路由选择协议",
]


def _textbooks() -> list[Path]:
    """与 tests/test_retrieval.py 同口径：排除"课件版"，只留 OCR 还原的教材。"""
    return [m for m in reader.list_books(COURSE) if "课件" not in m.stem]


def main() -> None:
    mds = _textbooks()
    print("=" * 78)
    print("教材 Markdown（参与 BM25 语料）")
    for m in mds:
        print(f"  - {m.name}")
    print()

    retriever = Retriever(build_from_markdown_files(mds, course=COURSE)) if mds else None
    n_bm25 = len(retriever.chunks) if retriever else 0

    client = kb._get_client()
    coll = client.get_or_create_collection(
        name=kb.TEXTBOOK_COLLECTION,
        embedding_function=kb.NGramEmbeddingFunction(),
    )
    n_chroma = coll.count()

    print("=" * 78)
    print(f"语料规模对比   BM25(retrieval) = {n_bm25} 块   |   chroma(knowledge_base) = {n_chroma} 块")
    if n_bm25 and n_chroma:
        print(f"               chroma 覆盖 BM25 语料的 {n_chroma / n_bm25 * 100:.1f}%")
    print()

    for q in QUERIES:
        print("=" * 78)
        print(f"查询：{q}")
        print("-" * 78)

        print("  [A] 软件自学页（chroma n-gram 余弦）")
        try:
            hits = kb.search_textbook(q, course=COURSE, top_k=5)
            if not hits:
                print("       （无结果）")
            for i, h in enumerate(hits, 1):
                sec = (h.get("section_path") or "")[:58]
                print(f"      {i}. score={h['score']:.3f}  {sec}")
                print(f"         {h['content'][:70]!r}")
        except Exception as e:                                  # noqa: BLE001
            print(f"       !! 异常：{type(e).__name__}: {e}")

        print()
        print("  [B] 离线阅读器（BM25 + 标题索引 + 拒答判据）")
        if retriever is None:
            print("       （语料为空，跳过）")
        else:
            res = retriever.search(q, top_k=5)
            print(f"      status = {res.get('status')}   message = {res.get('message')}")
            if res.get("missing_tokens"):
                print(f"      未出现词 = {res['missing_tokens']}")
            for i, s in enumerate(res.get("sections", []), 1):
                print(f"      标题{i}. {s.get('section_path', '')[:58]}")
            for i, p in enumerate(res.get("passages", []), 1):
                print(f"      段落{i}. {p.get('section_path', '')[:58]}")
                print(f"          {p.get('content', '')[:70]!r}")
        print()


if __name__ == "__main__":
    main()
