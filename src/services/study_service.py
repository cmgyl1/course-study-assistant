"""study_service —— 自学页业务逻辑：知识树 / 章节正文 / 知识点讲解。

UI 不再直接调 engine，而是 StudyPage → study_service.xxx → engine。

章节内容有**两条路**，用途不同：
  - get_section_reading：按原书顺序返回整节的标题/段落/插图（**阅读**场景）；
  - get_section_content：BM25 检索 top-k 相关片段（**问答**场景）。
"""
from __future__ import annotations

from pathlib import Path

from engine import study, textbook_reader as reader
from .dto import (
    ChapterContent, ExplainResultData, KnowledgeNode, Result,
    SectionBlock, SectionReading,
)


# =================== 知识树 ====================

def _node_sort_key(title: str) -> tuple:
    """按章节号排序（第 X 章 > 第 X.X 节 > 第 X.X.X 节）。"""
    import re
    parts = re.findall(r"\d+", title)
    return tuple(int(p) for p in parts) if parts else (9999,)


def _to_knowledge_node(d: dict) -> KnowledgeNode:
    """递归转换 engine dict → DTO。"""
    return KnowledgeNode(
        title=d.get("title", ""),
        book=d.get("book", ""),
        concepts=d.get("concepts", []),
        children=[_to_knowledge_node(c) for c in d.get("children", [])],
    )


def get_course_tree(course: str) -> Result[list[KnowledgeNode]]:
    """获取某课程的全部教材知识树（按教材分组）。"""
    if not course:
        return Result.fail("课程未选择")
    try:
        trees = study.get_course_tree(course)
    except Exception as e:
        return Result.fail(str(e), "❌ 知识树加载失败")
    if not trees:
        return Result.ok([], f"该课程暂无教材（请先在「资料管理」导入）")

    # ⚠ engine.get_course_tree 返回的是 [{"book": 书名, "tree": [顶层节点…]}] ——
    #   一层**包壳**；而 DTO 要求列表里每个元素就是节点（有 title/children）。
    #   把包壳直接丢给 _to_knowledge_node，会得到一批 title=""、children=[] 的空节点：
    #   UI 树里就只剩书名，**点不开任何章节**（实测就是这么坏的）。
    nodes: list[KnowledgeNode] = []
    for t in trees:
        if isinstance(t, dict) and "tree" in t:
            book = t.get("book", "")
            nodes.append(KnowledgeNode(
                title=book, book=book,
                children=[_to_knowledge_node(d) for d in (t.get("tree") or [])],
            ))
        else:
            nodes.append(_to_knowledge_node(t))

    # 按章节号排序子节点
    for root in nodes:
        root.children.sort(key=lambda n: _node_sort_key(n.title))
        _sort_recursive(root)
    return Result.ok(nodes, f"✅ 已加载 {len(nodes)} 棵知识树")


def _sort_recursive(node: KnowledgeNode) -> None:
    """递归对节点 children 排序。"""
    node.children.sort(key=lambda n: _node_sort_key(n.title))
    for c in node.children:
        _sort_recursive(c)


# =================== 章节正文 ====================

def get_section_content(section_path: str, course: str) -> Result[list[ChapterContent]]:
    """获取某章节的正文片段（top-k，按相关度排序）。

    走 BM25 词法检索（与自学页提问同一套引擎）。原实现走 chroma，已随该依赖移除。
    """
    if not section_path:
        return Result.fail("章节路径为空")
    if not course:
        return Result.fail("课程未选择")
    try:
        chunks = study.search_section(section_path, course, top_k=3)
    except Exception as e:
        return Result.fail(str(e), "❌ 章节正文加载失败")
    items = [
        ChapterContent(
            section_path=c.get("section_path", section_path),
            doc_title=c.get("doc_title", ""),
            content=c.get("content", ""),
            page_no=c.get("page_no"),
            score=c.get("score", 0.0),
        )
        for c in chunks
    ]
    if not items:
        return Result.ok(items, "（该章节暂无独立内容，试试上方输入框提问）")
    return Result.ok(items, f"✅ 已检索到 {len(items)} 个片段")


# =================== 章节阅读（原文 + 插图，严格保序）===================

def get_section_reading(section_path: str, course: str) -> Result[SectionReading]:
    """取某章节的**保序原文**（含插图，位置与原书一致）。

    与 `get_section_content` 的分工：
      - `get_section_content` 走 BM25 检索，只取相关 top-k 片段、按相关度排序（问答）；
      - 本方法按原书顺序返回整节的 heading / 段落 / 插图（阅读）——
        图片落在它对应的图题之上，**不会**被聚合成"正文一堆、图堆在末尾"。
    """
    if not section_path:
        return Result.fail("章节路径为空")
    try:
        data = reader.get_section_blocks(section_path, course)
    except Exception as e:
        return Result.fail(str(e), "❌ 章节原文加载失败")

    md_path = data.get("md_path", "")
    blocks = [
        SectionBlock(
            kind=b["kind"],
            text=b["text"],
            url=(reader.figure_abs_path(b["url"], md_path)
                 if b["kind"] == "figure" else ""),
            level=b["level"],
            page=b["page"],
            is_caption=(b["kind"] == "para" and reader.is_caption(b["text"])),
        )
        for b in data.get("blocks", [])
    ]
    reading = SectionReading(
        section_path=data.get("section_path", section_path),
        book=data.get("book", ""),
        md_path=md_path,
        blocks=blocks,
        n_figures=data.get("n_figures", 0),
    )
    if not blocks:
        return Result.ok(reading, "（该章节暂无独立内容，试试上方输入框提问）")
    n_para = sum(1 for b in blocks if b.kind == "para")
    return Result.ok(reading, f"✅ 已加载 {n_para} 段 / {reading.n_figures} 图（原文顺序）")


def _esc(text: str) -> str:
    """HTML 转义（教材原文里含 < > & 的公式与代码片段不少）。"""
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _table_html(md_table: str) -> str:
    """Markdown 管道表格 → HTML 表格（教材里的对照表必须按表格看，否则一团糟）。"""
    rows: list[list[str]] = []
    for line in (md_table or "").splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip().replace("\\|", "|") for c in line.strip("|").split("|")]
        if cells and all(set(c) <= {"-", ":", " "} for c in cells):
            continue                       # `| --- | --- |` 分隔行
        rows.append(cells)
    if not rows:
        return ""
    out = ['<table width="100%" cellspacing="0" cellpadding="5" '
           'style="border-collapse:collapse;font-size:13px;margin:10px 0">']
    for i, r in enumerate(rows):
        if i == 0:
            out.append("<tr>" + "".join(
                f'<th style="border:1px solid #d8dde5;background:#f2f5fa;'
                f'text-align:left;font-weight:bold">{_esc(c)}</th>' for c in r) + "</tr>")
        else:
            out.append("<tr>" + "".join(
                f'<td style="border:1px solid #d8dde5;text-align:left">{_esc(c)}</td>'
                for c in r) + "</tr>")
    out.append("</table>")
    return "".join(out)


def render_section_html(reading: SectionReading) -> str:
    """保序块 → HTML（供只读浏览器显示，插图按原位置内嵌）。

    渲染时**不做任何排序或分组** —— 顺序即 `reading.blocks` 的顺序，
    这正是"图和原文位置一致"的保证：块从 Markdown 里按原序读出，
    这里只是逐块转成标签，中间没有任何聚合步骤可以打乱它。
    """
    out: list[str] = []
    for b in reading.blocks:
        if b.kind == "heading":
            lv = min(max(b.level, 1) + 1, 5)
            size = {2: "18px", 3: "16px", 4: "14px", 5: "13px"}.get(lv, "13px")
            pg = (f'<span style="color:#8a94a6;font-size:11px;font-weight:normal">'
                  f'  p{b.page}</span>') if b.page else ""
            out.append(f'<p style="font-size:{size};font-weight:bold;color:#5A8DD6;'
                       f'margin:20px 0 8px">{_esc(b.text)}{pg}</p>')
        elif b.kind == "figure":
            if not b.url:
                continue
            uri = Path(b.url).as_uri()
            # 图外面包一层 <a href="file://…">：桌面端把"点击"接管成弹窗放大
            # （教材里的协议帧图/电路图不放大看不清）。见 main.StudyPage._on_anchor_clicked。
            out.append(f'<p style="text-align:center;margin:16px 0">'
                       f'<a href="{uri}"><img src="{uri}" style="max-width:92%"></a></p>')
        elif b.kind == "table":
            html = _table_html(b.text)
            if html:
                out.append(html)
        else:
            body = _esc(b.text).replace("\n", "<br>")
            if b.is_caption:
                out.append(f'<p style="text-align:center;color:#8a94a6;font-size:13px;'
                           f'margin:6px 0 18px">{body}</p>')
            else:
                out.append(f'<p style="margin:8px 0;line-height:1.7">{body}</p>')
    return "\n".join(out)


# =================== 知识点讲解 ====================

# =================== 检索索引预热 ====================

def warm_up(course: str) -> bool:
    """预热该课程的检索索引，返回是否可用。

    建 BM25 索引约 6s / 1698 块（而查询只要 0.3ms），所以由 UI 在**后台线程**
    启动时调用，避免第一次提问卡住界面。这里**不吞异常** —— 索引没建起来必须
    让人看见，否则用户只会觉得"什么都查不到"却不知道原因。
    """
    if not course:
        return False
    return study.warm_up(course)


# =================== 知识点讲解 ====================

def explain_topic(query: str, course: str, top_k: int = 5) -> Result[ExplainResultData]:
    """查询知识点讲解：教材原文检索（BM25）+ (可选) AI 总结。

    与离线阅读器**共用同一个检索引擎**，所以行为也一致：书里没有的概念会如实
    拒答（status="not_found"），而不是硬凑 top-5 让用户以为书里讲过。
    """
    if not query.strip():
        return Result.fail("问题为空")
    if not course:
        return Result.fail("课程未选择")
    try:
        result = study.explain_topic(query, course, top_k=top_k)
    except Exception as e:
        return Result.fail(str(e), "❌ 讲解生成失败")

    status = result.get("status", "ok")
    data = ExplainResultData(
        query=query,
        evidence=[
            ChapterContent(
                section_path=ev.get("section_path", ""),
                doc_title=ev.get("doc_title", ""),
                content=ev.get("content", ""),
                page_no=ev.get("page_no"),
                score=ev.get("score", 0.0),
            )
            for ev in result.get("evidence", [])
        ],
        answer=result.get("answer", ""),
        ai_available=result.get("ai_available", False),
        status=status,
        related_sections=[s.get("section_path", "")
                          for s in result.get("sections", [])
                          if s.get("section_path")],
        missing_tokens=list(result.get("missing_tokens", [])),
        message=result.get("message", ""),
    )

    # 拒答是**正确结果**而非失败：书里确实没讲过，如实告知即可（success 仍为 True，
    # 这样 UI 走正常渲染分支，用中性样式展示"未找到"，而不是弹一个像报错的提示）。
    if status in ("not_found", "no_corpus", "empty_query"):
        return Result.ok(data, data.message or "书中未找到相关内容")

    msg = f"✅ 已检索到 {len(data.evidence)} 条依据" + (
        " + AI 讲解" if data.ai_available else "（本地 AI 未启用，仅展示教材原文）"
    )
    if data.message:            # 如「薛定谔」在书中未出现，已按其余关键词检索
        msg = f"{data.message}　{msg}"
    return Result.ok(data, msg)


__all__ = [
    "get_course_tree",
    "get_section_content",
    "get_section_reading",
    "render_section_html",
    "explain_topic",
    "warm_up",
]
