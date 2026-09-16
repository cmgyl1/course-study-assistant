"""教材检索与阅读层测试：BM25 检索质量 + 保序原文 + 插图位置。

与 `test_knowledge_base.py` 的分工：那个测 chroma 向量库；这个测新的**词法链路**
（`engine/retrieval.py` + `engine/textbook_reader.py`）—— 也就是 UI 自学页实际走的那条路。

断言的重点是"**对不对**"，不是"有没有结果"：
  1. 主题词必须命中所属章节；
  2. 书里不存在的词必须**如实拒答**，不能返回一堆垃圾段落；
  3. 章节阅读必须**保序**：插图块紧跟在它自己的图题段落之前（图在上、图题在下）；
  4. 插图文件必须真实存在，否则 UI 上就是裂图。

数据缺失时（还没跑过 OCR 合并）自动跳过，不误报失败。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from engine import textbook_reader as reader
from engine.retrieval import Retriever, build_from_markdown_files

_COURSE = "计算机网络"
_RETRIEVER: Retriever | None = None
_LOADED = False


def _textbooks() -> list[Path]:
    """只取 OCR 还原的教材（上/下册）——排除"课件版"等来源不同的资料，
    否则语料规模、标题层级都会混入噪声，断言就不稳。"""
    return [m for m in reader.list_books(_COURSE) if "课件" not in m.stem]


def _retriever() -> Retriever | None:
    global _RETRIEVER, _LOADED
    if not _LOADED:
        mds = _textbooks()
        _RETRIEVER = Retriever(build_from_markdown_files(mds, course=_COURSE)) if mds else None
        _LOADED = True
    return _RETRIEVER


def _first_book_with_figures():
    """找第一本含插图的教材，返回 (md_path, figure_item)。"""
    for md in _textbooks():
        for it in reader.load_items(md):
            if it["kind"] == "figure":
                return md, it
    return None


# ---------------- 检索质量 ----------------

def test_topic_word_hits_its_chapter():
    r = _retriever()
    if r is None:
        return
    res = r.search("物理层", top_k=5)
    assert res["status"] == "ok", res
    paths = [s["section_path"] for s in res["sections"]]
    assert any("物理层" in p for p in paths), f"命中章节里没有「物理层」: {paths}"


def test_three_way_handshake_lands_on_transport_chapter():
    """教材用的是 RFC 译名"**三报文**握手"，"三次握手"只在注脚里出现过一次 ——
    所以这条要看**原文段落的章节归属**，不能看标题命中（标题里根本没有"握手"）。
    同时它守住了"整本两册都入库"：三次握手在第 5 章，只跑上册必然找不到。"""
    r = _retriever()
    if r is None:
        return
    res = r.search("三次握手", top_k=5)
    assert res["status"] == "ok", res
    paths = [p["section_path"] for p in res["passages"]]
    assert paths, "三次握手应有原文段落命中"
    assert any("第5章" in p for p in paths), f"未落到第5章: {paths}"


def test_unknown_topic_is_refused_not_garbage():
    """「量子纠缠」全库 DF=0 → 必须拒答，且不返回任何段落。"""
    r = _retriever()
    if r is None:
        return
    res = r.search("量子纠缠", top_k=5)
    assert res["status"] == "not_found", f"未拒答: {res['status']}"
    assert res["sections"] == [] and res["passages"] == []
    assert "未找到" in res["message"]


def test_mixed_query_reports_missing_term():
    """部分词不在书里时：仍按存在的词检索，并**明确告知**哪个词没出现。"""
    r = _retriever()
    if r is None:
        return
    res = r.search("双绞线 薛定谔", top_k=5)
    assert res["status"] == "ok", res
    assert "薛定谔" in " ".join(res["missing_tokens"]), res["missing_tokens"]


# ---------------- 阅读保序与插图位置 ----------------

def test_figure_sits_right_above_its_own_caption():
    """图块后面必须紧跟它自己的图题段落（原书排版：图在上、图题在下）。"""
    hit = _first_book_with_figures()
    if hit is None:
        return
    md, fig = hit
    data = reader.get_section_blocks(f"{md.stem} > {fig['path']}", _COURSE)
    blocks = data["blocks"]
    idx = [i for i, b in enumerate(blocks) if b["kind"] == "figure"]
    assert idx, "该章节应含插图"
    for i in idx:
        cap = blocks[i]["text"].strip()
        nxt = blocks[i + 1]["text"].strip() if i + 1 < len(blocks) else ""
        assert nxt == cap, (
            f"图 {cap!r} 之后应紧跟同名图题段落，实际是 {nxt[:40]!r}"
            "（图题被并进别处或图被退化成追加到章节末尾）"
        )


def test_every_figure_file_exists():
    """所有 figure 块的图片路径都必须落在磁盘上（否则 UI 裂图）。"""
    missing, total = [], 0
    for md in _textbooks():
        for it in reader.load_items(md):
            if it["kind"] != "figure":
                continue
            total += 1
            p = Path(reader.figure_abs_path(it["url"], md))
            if not p.exists():
                missing.append(str(p))
    if total == 0:
        return
    assert not missing, f"{len(missing)}/{total} 张插图文件缺失，例如 {missing[:3]}"


def test_section_blocks_preserve_source_order():
    """块序列必须按原书顺序：页码单调不减（同一节内不应出现页码倒挂）。"""
    hit = _first_book_with_figures()
    if hit is None:
        return
    md, fig = hit
    data = reader.get_section_blocks(f"{md.stem} > {fig['path']}", _COURSE)
    pages = [b["page"] for b in data["blocks"] if b["page"]]
    assert pages == sorted(pages), f"页码未保持递增: {pages[:20]}"


def test_section_path_needs_book_prefix():
    """UI 的章节路径第一段是教材名 —— 摘掉它才能匹配上标题栈。"""
    book, inner = reader.split_section_path("计算机网络（第8版）_谢希仁_上半 > 第2章物理层")
    assert book.endswith("上半")
    assert inner == "第2章物理层"


def main() -> int:
    tests = [(name, fn) for name, fn in globals().items()
             if name.startswith("test_") and callable(fn)]
    failures = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ✓ {name}")
        except Exception as e:
            failures += 1
            print(f"  ✗ {name}: {type(e).__name__}: {e}")
    total = len(tests)
    if failures:
        print(f"\n{failures}/{total} 个测试失败")
        return 1
    print(f"\n全部 {total} 个测试通过 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
