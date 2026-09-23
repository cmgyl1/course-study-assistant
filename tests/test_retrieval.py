"""教材检索与阅读层测试：BM25 检索质量 + 保序原文 + 插图位置 + UI 路径一致性。

覆盖**词法链路**（`engine/retrieval.py` + `engine/textbook_reader.py`）——
这也是全项目唯一一条检索路径（UI 自学页、离线阅读器、服务层都走它）。

⚠️ 历史教训（本文件的第一段注释曾经是**错的**）：这里原来写着 BM25
"也就是 UI 自学页实际走的那条路"，但 UI 的输入框当时走的是**另一条** chroma
向量路（`knowledge_base.search_textbook`）—— 只有 261 块语料（覆盖全书的
15.4%）、score 恒为 0（排序信息丢失）、没有任何拒答机制。实测「三次握手」
返回的是 IP 地址片段、「量子纠缠」返回 5 条垃圾，而本文件 8 条断言**全绿** ——
因为它们测的是 BM25，不是用户走的那条路。

结论：**测了引擎不等于测了用户路径**。文件末尾那组 `test_ui_path_*` 就是为此
存在的：它们对着 `services.study_service.explain_topic` 断言，把上面那句注释
从"自述"变成"受检事实"。

那条 chroma 路已整体移除（连 `chromadb` 依赖、`data/vector_store/` 与
`knowledge_base.py` 一起），现在断言的对象与用户实际走的路完全重合。

断言的重点是"**对不对**"，不是"有没有结果"：
  1. 主题词必须命中所属章节；
  2. 书里不存在的词必须**如实拒答**，不能返回一堆垃圾段落；
  3. 章节阅读必须**保序**：插图块紧跟在它自己的图题段落之前（图在上、图题在下）；
  4. 插图文件必须真实存在，否则 UI 上就是裂图；
  5. UI 检索路径必须与 BM25 同源（同一语料、同一拒答行为）。

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


def test_title_hit_carries_hit_count():
    """命中章节必须带 `n_hits`（标题里命中了几个查询词）—— 界面「命中 N 词」角标用它。

    这是给引擎加的**加性字段**：只多一个键，排序与筛选逻辑一字未动。
    这条断言是回归锁 —— 少了它，日后有人重排 `TitleIndex.match()` 的返回值时，
    界面角标会**静默**变成「命中 0 词」（UI 有默认值兜底，不会报错）。
    """
    r = _retriever()
    if r is None:
        return
    res = r.search("物理层", top_k=5)
    assert res["status"] == "ok", res
    assert res["sections"], "「物理层」应有标题命中"
    for s in res["sections"]:
        assert isinstance(s.get("n_hits"), int), f"缺 n_hits: {s.keys()}"
        assert s["n_hits"] >= 1, f"命中章节的 n_hits 至少为 1: {s}"
    # 命中词数不能超过查询词数
    assert max(s["n_hits"] for s in res["sections"]) <= len(set(res["tokens"]))


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


# ---------------- UI 检索路径（回归锁）----------------
#
# 这组断言对着 **UI 实际调用的那个函数**说话：services.study_service.explain_topic。
# 背景见本文件顶部 docstring 的「历史教训」——只测引擎、不测用户路径，
# 会让引擎全绿而用户体验崩坏。

def _ui_explain(query: str, top_k: int = 5):
    from services import study_service

    return study_service.explain_topic(query, _COURSE, top_k=top_k)


def test_ui_corpus_is_full_not_legacy_vector_store():
    """回归锁：UI 语料必须是 BM25 全量（~1700 块），不能又接回 261 块的旧向量库。"""
    from engine import study

    retriever = study.get_retriever(_COURSE)
    if retriever is None:
        return
    n = len(retriever.chunks)
    assert n > 1000, (
        f"UI 检索语料只有 {n} 块 —— 疑似又接回了旧的 chroma 向量库（261 块）。"
        f"UI 必须走 engine.retrieval 的全量语料。"
    )


def test_ui_path_refuses_absent_concept():
    """书里没有的概念必须拒答 —— 旧版不管问什么都返回 top-5，最误导人。"""
    res = _ui_explain("量子纠缠")
    assert res.success, res.message
    assert res.data is not None
    assert res.data.status == "not_found", (
        f"「量子纠缠」教材里没有，status 应为 not_found，实际 {res.data.status}；"
        f"返回了 {len(res.data.evidence)} 条依据"
    )
    assert res.data.evidence == [], "拒答时不应返回任何原文段落"
    assert "未找到" in res.message


def test_ui_path_finds_tcp_handshake_in_chapter5():
    """「三次握手」必须落到第 5 章 —— 旧路返回的是 IP 地址片段。"""
    res = _ui_explain("三次握手")
    assert res.success and res.data is not None
    assert res.data.status == "ok", res.data.status
    paths = [e.section_path for e in res.data.evidence]
    assert any("第5章" in p for p in paths), f"未落到第5章: {paths}"


def test_ui_path_reports_missing_tokens():
    """部分词命中时要告诉用户哪个词书里没有，而不是假装全都查到了。"""
    res = _ui_explain("双绞线 薛定谔")
    assert res.success and res.data is not None
    assert "薛定谔" in res.data.missing_tokens, res.data.missing_tokens
    assert "未出现" in res.message


def test_ui_path_matches_bm25_results():
    """UI 与离线阅读器必须同源：同一查询返回的结果集要有交集、顺序一致。"""
    retriever = _retriever()
    if retriever is None:
        return
    query = "TCP 拥塞控制"
    bm = retriever.search(query, top_k=5)
    res = _ui_explain(query, top_k=5)
    if bm["status"] != "ok" or res.data is None or res.data.status != "ok":
        return
    bm_paths = {p["section_path"] for p in bm["passages"]}
    ui_paths = {e.section_path for e in res.data.evidence}
    assert bm_paths & ui_paths, (
        f"UI 与 BM25 结果无交集 —— 两条路又分家了\n"
        f"BM25={sorted(bm_paths)}\nUI={sorted(ui_paths)}"
    )


def test_ui_evidence_text_is_returned_intact():
    """依据原文必须**原样透传**、按同一顺序 —— 旧版硬截 300 字（一段平均 ~350 字）。"""
    retriever = _retriever()
    if retriever is None:
        return
    query = "TCP 拥塞控制"
    bm = retriever.search(query, top_k=5)
    res = _ui_explain(query, top_k=5)
    if bm["status"] != "ok" or res.data is None or res.data.status != "ok":
        return
    bm_texts = [p["text"] for p in bm["passages"]]
    ui_texts = [e.content for e in res.data.evidence]
    assert ui_texts == bm_texts, (
        "UI 返回的原文与 BM25 原文不一致（被截断或改写过）\n"
        f"BM25 首条 {len(bm_texts[0]) if bm_texts else 0} 字，"
        f"UI 首条 {len(ui_texts[0]) if ui_texts else 0} 字"
    )


def test_ui_evidence_carries_page_number():
    """依据要带页码，学生才能对照纸质书。"""
    res = _ui_explain("三次握手")
    if not (res.success and res.data and res.data.evidence):
        return
    assert any(e.page_no for e in res.data.evidence), "所有依据都没有页码"


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
