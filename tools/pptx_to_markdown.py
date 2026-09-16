"""PPTX 课件 → Markdown 教材转换（文字层，无 OCR 乱版）。

谢希仁《计算机网络》第8版官方配套课件按章组织，每章一个 .pptx。
本脚本提取每页标题/正文层级，归一化为 Markdown 章节结构，
输出到 data/textbooks_md/ 供知识库入库。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from engine.config import TEXTBOOKS_MD_DIR

# 章节编号模式：1.1 / 1.2.1 / 1.2.1.3 / 第X章
_SEC = re.compile(r"^(\d+(?:\.\d+)*)[.、]?\s*(.*)$")
_ZH_CH = re.compile(r"^第[一二三四五六七八九十百0-9]+章")


def _is_real_heading(text: str) -> bool:
    """判断文本是否为真正的章节标题（有编号，且编号后带短标题或编号本身）。

    页面上其他文字（正文、图注、版式文本）一律不是标题。
    """
    s = text.strip()
    if not s or len(s) > 60:
        return False
    if _ZH_CH.match(s):
        return True
    m = _SEC.match(s)
    if not m:
        return False
    num, rest = m.group(1), m.group(2).strip()
    # 数字编号必须带点（1.1 而不是纯 "1"），且后面必须带标题文本（纯编号如 "1.1" 不是标题）
    return "." in num and len(rest) > 0


def _heading_level(text: str) -> int:
    """根据编号深度返回 Markdown 标题级别：第X章→1，X.Y→2，X.Y.Z→3。"""
    m = _SEC.match(text.strip())
    if _ZH_CH.match(text.strip()):
        return 1
    if m:
        depth = m.group(1).count(".")
        return min(2 + (depth - 1), 4)  # 1.1→2, 1.2.1→3, 1.2.1.3→4
    return 2


def _normalize_heading(text: str) -> str:
    """标题清洗：压缩多余空格（'1.1      概述' → '1.1 概述'）。"""
    return re.sub(r"\s+", " ", text.strip())


def pptx_to_markdown(pptx_path: Path) -> str:
    """把单个 PPTX 转成 Markdown 文本（仅章节编号行生成标题，其余为正文）。"""
    from pptx import Presentation

    prs = Presentation(str(pptx_path))
    out: list[str] = []
    seen_heads: set[str] = set()

    for slide_idx, slide in enumerate(prs.slides, 1):
        blocks: list[tuple[int, str]] = []  # (层级, 文本)
        for shape in slide.shapes:
            if not shape.has_text_frame:
                continue
            for para in shape.text_frame.paragraphs:
                text = "".join(run.text for run in para.runs).strip()
                if not text:
                    continue
                level = para.level  # 0=标题/正文, 1..n=缩进层级
                blocks.append((level, text))
        if not blocks:
            continue

        for level, text in blocks:
            if _is_real_heading(text):
                key = _normalize_heading(text)
                if key in seen_heads:  # 同一标题重复出现（PPT 每页页眉）→ 只留一次
                    continue
                seen_heads.add(key)
                lv = _heading_level(text)
                out.append(f"{'#' * lv} {key}")
            else:
                # 正文：按缩进层级输出为列表项或段落
                if level >= 1:
                    out.append("  " * (level - 1) + f"- {text}")
                else:
                    out.append(text)

    return "\n\n".join(out)


def chapter_num(pptx_path: Path) -> int:
    """从文件名提取章号（如 '第3章-数据链路层' → 3）。"""
    m = re.search(r"第(\d+)章", pptx_path.name)
    return int(m.group(1)) if m else 99


def main() -> int:
    src_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else \
        PROJECT_ROOT / "tools" / "downloads" / "cn_book2" / \
        "Computer_Network_PPT-BOOK-main" / \
        "谢希仁老师的计算机网络（第八版）课本及PPT讲义"
    course = sys.argv[2] if len(sys.argv) > 2 else "计算机网络"

    pptx_files = sorted(src_dir.glob("*.pptx"), key=chapter_num)
    if not pptx_files:
        print(f"未找到 PPTX: {src_dir}")
        return 1

    TEXTBOOKS_MD_DIR.mkdir(parents=True, exist_ok=True)
    book_parts: list[str] = []
    for f in pptx_files:
        md_text = pptx_to_markdown(f)
        ch = chapter_num(f)
        book_parts.append(f"# 第{ch}章\n\n{md_text}")
        print(f"[OK] {f.name}: {len(md_text)} 字符")

    merged = "\n\n".join(book_parts)
    out = TEXTBOOKS_MD_DIR / f"计算机网络（第8版）课件版.md"
    out.write_text(merged, encoding="utf-8")
    print(f"\n合并完成: {len(pptx_files)} 章 → {out.name}（{len(merged)} 字符）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
