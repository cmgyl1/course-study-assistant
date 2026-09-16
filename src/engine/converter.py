"""文档转换管线：把 PDF / Office（docx/pptx/xlsx）等转换为 Markdown。

设计要点（分层解耦）：
- 统一入口 convert_file()：按扩展名自动分派转换策略；
- PDF → Markdown：PyMuPDF 提取文本（快、稳，支持中文）；
- docx → Markdown：自写 python-docx 提取器（markitdown 对中文有拆字 bug，弃用）；
- pptx/xlsx/其他 Office → 先用 LibreOffice headless 转 PDF，再走 PDF 提取；
- 输出统一为 UTF-8 Markdown，落盘到指定的输出目录。
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .config import SOFFICE_EXE

# 支持的扩展名 → 类别
PDF_EXTS = {".pdf"}
DOCX_EXTS = {".docx"}
OFFICE_TO_PDF_EXTS = {".doc", ".pptx", ".ppt", ".xlsx", ".xls", ".odt", ".odp", ".ods"}
TEXT_EXTS = {".txt", ".md", ".markdown"}


class ConversionError(RuntimeError):
    """文档转换失败。"""


def _extract_pdf_text(pdf_path: Path) -> str:
    """用 PyMuPDF 提取 PDF 全文（含页分节）。"""
    import pymupdf  # PyMuPDF（新 API）

    doc = pymupdf.open(str(pdf_path))
    parts: list[str] = []
    for page in doc:
        text = page.get_text("text")
        if text.strip():
            parts.append(text.strip())
    doc.close()
    return "\n\n".join(parts)


def _docx_to_markdown(src: Path) -> str:
    """docx → Markdown：自写 python-docx 提取器，保证中文完整。

    处理：标题（Heading 1-9 → #）、段落、列表（List → -）、表格（→ Markdown 表）、
    粗体/斜体。逐 paragraph 输出，不跨 run 拆词。
    """
    from docx import Document
    from docx.document import Document as DocType
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    doc = Document(str(src))
    out: list[str] = []

    def iter_block_items(parent):
        # 按文档顺序遍历段落与表格（python-docx 官方示例）
        from docx.oxml.ns import qn
        parent_elm = parent.element.body
        for child in parent_elm.iterchildren():
            if child.tag == qn("w:p"):
                yield Paragraph(child, parent)
            elif child.tag == qn("w:tbl"):
                yield Table(child, parent)

    def inline_text(paragraph: Paragraph) -> str:
        """提取段落内所有 run 文本并合并，保留粗体/斜体标记。"""
        parts: list[str] = []
        for run in paragraph.runs:
            t = run.text
            if not t:
                continue
            if run.bold and run.italic:
                t = f"***{t}***"
            elif run.bold:
                t = f"**{t}**"
            elif run.italic:
                t = f"*{t}*"
            parts.append(t)
        return "".join(parts)

    def table_to_md(table: Table) -> str:
        rows = []
        for row in table.rows:
            cells = [c.text.strip().replace("\n", "<br>") for c in row.cells]
            rows.append(cells)
        if not rows:
            return ""
        md_lines = ["| " + " | ".join(rows[0]) + " |",
                    "|" + "|".join(["---"] * len(rows[0])) + "|"]
        for r in rows[1:]:
            md_lines.append("| " + " | ".join(r) + " |")
        return "\n".join(md_lines)

    for block in iter_block_items(doc):
        if isinstance(block, Paragraph):
            style = block.style.name if block.style else ""
            text = inline_text(block)
            if not text.strip():
                continue
            if style.startswith("Heading"):
                try:
                    level = int(style.replace("Heading ", "").strip())
                except ValueError:
                    level = 1
                level = min(max(level, 1), 6)
                out.append(f"{'#' * level} {text}")
            elif style.startswith("List") or style == "List Paragraph":
                out.append(f"- {text}")
            else:
                out.append(text)
        elif isinstance(block, Table):
            md = table_to_md(block)
            if md:
                out.append(md)

    return "\n\n".join(out)


def _office_to_pdf(src: Path, out_dir: Path) -> Path:
    """用 LibreOffice headless 把 Office 文档转成 PDF。"""
    if not SOFFICE_EXE.exists():
        raise ConversionError(f"LibreOffice 未找到: {SOFFICE_EXE}")
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [str(SOFFICE_EXE), "--headless", "--convert-to", "pdf",
           "--outdir", str(out_dir), str(src)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    pdf_path = out_dir / f"{src.stem}.pdf"
    if not pdf_path.exists():
        raise ConversionError(f"LibreOffice 转换失败: {proc.stderr[-500:]}")
    return pdf_path


def _is_heading_line(s: str) -> bool:
    """更严格的标题识别，避免把普通短行误判为章节标题。

    只接受两类：
    - '第X章/节/部分/篇 …'（章节式标题）；
    - '1.2 标题文字'（编号 + 空格 + 文字）。
    排除：纯数字行、年份日期（2024 年）、无编号的普通短句。
    """
    if len(s) > 60:
        return False
    if re.match(r"^第[0-9一二三四五六七八九十百]+[章节部分篇]", s):
        return True
    if re.match(r"^\d{4}\s*年", s):  # 日期行不是标题
        return False
    return bool(re.match(r"^\d+(\.\d+){0,3}\s+[\u4e00-\u9fffA-Za-z]", s))


def _pdf_to_markdown(src: Path) -> str:
    """PDF → Markdown：文本提取，严格标题归一化。"""
    text = _extract_pdf_text(src)
    if not text.strip():
        raise ConversionError(f"PDF 无可提取文本（可能是扫描件）: {src.name}")
    lines = text.splitlines()
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and _is_heading_line(stripped):
            out.append(f"\n## {stripped}")
        else:
            out.append(line)
    return "\n".join(out)


def convert_file(src: Path | str, out_dir: Path | str) -> Path:
    """统一入口：转换 src 为 Markdown，输出到 out_dir，返回输出文件路径。

    Raises: ConversionError
    """
    src = Path(src)
    out_dir = Path(out_dir)
    if not src.exists():
        raise ConversionError(f"文件不存在: {src}")
    ext = src.suffix.lower()

    if ext in TEXT_EXTS:
        # 纯文本/Markdown 直接复制
        out = out_dir / f"{src.stem}.md"
        out_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, out)
        return out

    if ext in PDF_EXTS:
        text = _pdf_to_markdown(src)
    elif ext in DOCX_EXTS:
        text = _docx_to_markdown(src)
    elif ext in OFFICE_TO_PDF_EXTS:
        with tempfile.TemporaryDirectory() as tmp:
            pdf = _office_to_pdf(src, Path(tmp))
            text = _pdf_to_markdown(pdf)
    else:
        raise ConversionError(f"不支持的格式: {ext}")

    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{src.stem}.md"
    out.write_text(text, encoding="utf-8")
    return out


def convert_batch(src_files: list[Path | str], out_dir: Path | str) -> list[Path]:
    """批量转换多个文件，逐个返回成功输出路径（跳过失败项并记录）。"""
    out_dir = Path(out_dir)
    results: list[Path] = []
    for f in src_files:
        try:
            results.append(convert_file(f, out_dir))
        except ConversionError as e:
            print(f"[跳过] {Path(f).name}: {e}")
    return results
