# -*- coding: utf-8 -*-
"""教材阅读层：按章节取**保序原文块**（含插图位置）。

与 knowledge_base（chroma 语义检索）的分工很明确：

  - `knowledge_base` 负责"跨章节找相关片段" —— 问答场景，允许打乱顺序、
    只挑 top-k；
  - 本模块负责"按章节读出原文" —— 阅读场景，**严格保留块的原始顺序**。
    插图就落在它对应的图题之上，绝不会退化成"正文一堆、图堆在末尾"。

数据源是 OCR 合并后的 Markdown（`data/textbooks_md/<书名>.md`）。
图中的引用形如 `![图2-7同轴电缆的结构](../figures/<书名>/page_0061_fig1.png)`，
相对该 Markdown 所在目录解析。
"""
from __future__ import annotations

import re
from pathlib import Path

from .config import TEXTBOOKS_MD_DIR
from .retrieval import parse_markdown

_ITEMS_CACHE: dict[str, list[dict]] = {}

# 图题行（用于渲染时居中显示）：与 layout._FIG_CAPTION_RE 同源
_CAPTION_RE = re.compile(r"^图\s*\d+\s*[-–—]\s*\d+")


def list_books(course: str = "") -> list[Path]:
    """列出某课程（或全部）的教材 Markdown —— 一本教材合并成一个文件。"""
    pattern = f"*{course}*.md" if course else "*.md"
    return sorted(TEXTBOOKS_MD_DIR.glob(pattern))


def find_book(book_stem: str) -> Path | None:
    """按书名（不含扩展名）定位教材文件。"""
    if not book_stem:
        return None
    p = TEXTBOOKS_MD_DIR / f"{book_stem}.md"
    if p.exists():
        return p
    hits = [m for m in sorted(TEXTBOOKS_MD_DIR.glob("*.md")) if book_stem in m.stem]
    return hits[0] if hits else None


def split_section_path(section_path: str) -> tuple[str, str]:
    """UI 的章节路径 → (书名, 书内标题路径)。

    UI 树的根节点是**教材名**，而 Markdown 里的标题栈不含教材名 ——
    必须先把第一段摘掉，否则永远匹配不上（这是接 UI 时最容易踩的坑）。
    """
    parts = [p.strip() for p in re.split(r"[>＞]", section_path or "") if p.strip()]
    if not parts:
        return "", ""
    return parts[0], " > ".join(parts[1:])


def load_items(md: Path) -> list[dict]:
    """读取并缓存一本教材的元素序列（heading / para / figure，带 section_path）。"""
    key = str(md)
    if key not in _ITEMS_CACHE:
        _ITEMS_CACHE[key] = parse_markdown(md.read_text(encoding="utf-8"))
    return _ITEMS_CACHE[key]


def _block(it: dict) -> dict:
    return {
        "kind": it["kind"],
        "level": it.get("level", 0),
        "text": it.get("text", ""),
        "url": it.get("url", ""),
        "page": it.get("page"),
    }


def get_section_blocks(section_path: str, course: str = "") -> dict:
    """取某章节的**保序块序列**。

    范围界定：从匹配到的那条标题开始，一直取到**下一个同级或更高级标题之前**。
    所以点"第2章物理层"会拿到整章（含全部小节），点"2.4信道复用技术"只拿该节。

    Returns:
        {"book", "md_path", "section_path", "blocks", "n_figures"}
    """
    book_stem, target = split_section_path(section_path)
    md = find_book(book_stem)
    if md is None:
        books = list_books(course)
        md = books[0] if books else None
    if md is None:
        return {"book": "", "md_path": "", "section_path": target,
                "blocks": [], "n_figures": 0}

    items = load_items(md)

    if not target:
        # 只点到教材根节点 → 给出全书的标题清单，方便继续往下点
        blocks = [_block(it) for it in items if it["kind"] == "heading"]
        return {"book": md.stem, "md_path": str(md), "section_path": "",
                "blocks": blocks, "n_figures": 0}

    start = level = None
    for i, it in enumerate(items):
        if it["kind"] == "heading" and it["path"] == target:
            start, level = i, it["level"]
            break
    if start is None:
        return {"book": md.stem, "md_path": str(md), "section_path": target,
                "blocks": [], "n_figures": 0}

    blocks: list[dict] = []
    for j in range(start, len(items)):
        it = items[j]
        if j > start and it["kind"] == "heading" and it["level"] <= level:
            break
        blocks.append(_block(it))

    return {
        "book": md.stem,
        "md_path": str(md),
        "section_path": target,
        "blocks": blocks,
        "n_figures": sum(1 for b in blocks if b["kind"] == "figure"),
    }


def is_caption(text: str) -> bool:
    """该段是否图题（渲染时居中、灰色小字）。"""
    return bool(_CAPTION_RE.match((text or "").strip()))


def figure_abs_path(url: str, md_path: str | Path) -> str:
    """Markdown 里的相对图路径 → 绝对路径字符串（UI 用 file:// 加载）。"""
    if not url:
        return ""
    return str((Path(md_path).parent / url).resolve())
