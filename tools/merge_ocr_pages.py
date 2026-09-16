"""合并 OCR 分页结果（含版面还原结果）为单份 Markdown。

用法：
    python tools/merge_ocr_pages.py --pdf "计算机网络（第8版）_谢希仁_上半"
    python tools/merge_ocr_pages.py --pdf "..." --keep-toc   # 保留目录页

每页文件前插入 `<!-- page N -->` 页码标记（N 优先取 OCR 识别出的**印刷页码**，
识别不到则回退为 PDF 页序），供后续切块时写入 page_no 元数据。

**目录页要被剔除**：教材前几页是目录，OCR 后会变成一整页标题
（实测 p6–p8 全是 `# 第1章概述` / `## 1.1…` 这类行）。若照单全收：
  - 章节树里"第2章物理层"会出现两次（目录一次、正文一次）；
  - 检索"物理层"会优先命中目录页，返回的"原文"是目录行而不是正文。
判据：整页几乎只有标题行、没有实质正文段落。
过滤放在合并阶段（而不是 OCR 阶段），因为这是"整页是什么"的判断，
而且已经 OCR 过的分页文件不必重跑。

标题识别已在 OCR 阶段由 engine.layout 完成，这里不再重复处理。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from engine.config import TEXTBOOKS_MD_DIR

_META_NAME = "_meta.json"
_HEAD_RE = re.compile(r"^#{1,6}\s+")
_TOC_MIN_HEADINGS = 8       # 至少这么多标题行
_TOC_MIN_BODY_CHARS = 30    # 长度达到此值的正文行才算"实质正文"
_TOC_MAX_BODY_LINES = 1     # 实质正文行不超过这么多 → 判为目录页
_PAGENO_TOL = 3             # 印刷页码与全书偏移允许的偏差

# 表格行也要按"结构性行"看待：目录页经版面还原后，形如
#   | 6.9.2 | 具有全分布式结构的P2P文件共享程序 |
# 的目录项长度就 >= 30 字符，若不排除，会被当成"实质正文"，
# 使 body > _TOC_MAX_BODY_LINES，目录页漏剔并混进语料与检索。
_TABLE_SEP_RE = re.compile(r"^\|[\s:|-]+\|$")       # |---|---| 分隔行
_TABLE_ROW_RE = re.compile(r"^\|.*\|$")             # 任意表格数据行
_TABLE_SEC_CELL_RE = re.compile(r"^\|\s*\d+(?:\.\d+)+\s*\|")   # 首格是章节号

# 附录（多为"附录A 部分习题的解答"）：其内部用小节形式排版，OCR 后是
#   # 第1章        ← 与正文各章同为一级标题！
# 若不处理，知识树会把"附录的第1章…第9章"和正文"第6章…第9章"平铺混排，
# 点"第1章"打开的是习题答案而不是概述。判据：书末的"附录"行之后，
# 出现 >=2 条**裸"第N章"**（章号后没有标题文字）→ 判为解答区，
# 把附录行升为一级标题、其后的裸章标题降一级。
_APPENDIX_RE = re.compile(r"^附\s*录\s*[A-Za-z]?")
_BARE_CHAP_RE = re.compile(r"^(#{1,6})\s*第\s*(\d+)\s*章\s*$")
_APPENDIX_MIN_BARE = 2


def normalize_appendix(text: str) -> tuple[str, int]:
    """把书末"附录 … 解答"区整理成 附录(一级) > 第N章(二级)。返回 (文本, 降级条数)。

    注意一本书可能有多个附录（附录A 习题解答 / 附录B 缩写词 / 附录C 参考文献），
    要挑的是**其后确实跟着 >=2 条裸"第N章"**的那一个 —— 不能简单取"最后一个附录行"，
    否则会落在附录C 上，反而什么都降不了。
    """
    lines = text.splitlines()
    idx = None
    for i, l in enumerate(lines):
        s = l.strip()
        if len(s) > 30 or not _APPENDIX_RE.match(s):
            continue
        if sum(1 for x in lines[i + 1:] if _BARE_CHAP_RE.match(x.strip())) >= _APPENDIX_MIN_BARE:
            idx = i
            break                                    # 取第一个满足条件的"附录"行
    if idx is None:
        return text, 0

    s = lines[idx].strip()
    if not s.startswith("#"):
        lines[idx] = "# " + s
    n = 0
    for i in range(idx + 1, len(lines)):
        m = _BARE_CHAP_RE.match(lines[i].strip())
        if m:
            lines[i] = "## 第%s章" % m.group(2)
            n += 1
    return "\n".join(lines), n


def _estimate_offset(page_nos: dict[int, int | None]) -> int:
    """估计"印刷页码 − PDF 页序"的全书偏移（取众数）。

    实例：本书上半 PDF 第 12 页是印刷第 1 页 → 偏移 −11；下半从印刷第 240 页起。
    """
    ds = [pn - (idx + 1) for idx, pn in page_nos.items() if pn]
    if not ds:
        return 0
    best, best_n = 0, -1
    for v in ds:
        n = sum(1 for u in ds if abs(u - v) <= 1)
        if n > best_n:
            best_n, best = n, v
    return best


def _clean_page_numbers(page_nos: dict[int, int | None]) -> tuple[dict[int, int | None], int]:
    """剔除/修正识别错的印刷页码，返回 (修正后的页码表, 被修正的页数)。

    为什么必须修：实测上半有 134 页页码倒挂（PDF 第 117 页把页脚读成了 901，
    后续页码全被顶到 901；还有 90→901、60→19 这类明显误读）。
    页码是"原文所在位置"的一部分，错了比没有更糟。

    判据：印刷页码与 PDF 页序之差应当全书一致（同一本书排版连续）。
    偏差在容差内的直接采信；超出容差的按 `PDF 页序 + 全书偏移` 推算。
    """
    off = _estimate_offset(page_nos)
    fixed = 0
    out: dict[int, int | None] = {}
    for idx, pn in page_nos.items():
        guess = idx + 1 + off
        if pn is None:
            out[idx] = guess if guess >= 1 else None
            continue
        if abs((pn - (idx + 1)) - off) <= _PAGENO_TOL:
            out[idx] = pn
        else:
            fixed += 1
            out[idx] = guess if guess >= 1 else None
    return out, fixed


def looks_like_toc(md_text: str) -> bool:
    """一整页几乎只有结构性行（标题 / 目录式表格行）、没有实质正文 → 目录页。

    表格行一律不参与"实质正文"计数：目录页被版面还原成表格后，
    单元格里是 `6.9.2 | 具有全分布式结构的P2P文件共享程序` 这类目录项，
    长度会超过 _TOC_MIN_BODY_CHARS，若不排除就会把目录页误判成正文页。
    """
    heads = 0
    body = 0
    for line in md_text.splitlines():
        s = line.strip()
        if not s or s.startswith("!["):
            continue
        if _TABLE_SEP_RE.match(s):
            continue                                   # 表格分隔行，不算正文
        if _TABLE_ROW_RE.match(s):
            if _TABLE_SEC_CELL_RE.match(s):
                heads += 1                             # 首格是 6.9.2 这类章节号 → 目录项
            continue                                   # 表格行不计入正文
        if _HEAD_RE.match(s):
            heads += 1
        elif len(s) >= _TOC_MIN_BODY_CHARS:
            body += 1
    return heads >= _TOC_MIN_HEADINGS and body <= _TOC_MAX_BODY_LINES


def merge_pages(page_dir: Path, keep_toc: bool = False) -> tuple[str, dict]:
    """把 page_*.md 合并成带页码标记的 Markdown。返回 (文本, 统计)。"""
    meta: dict = {}
    meta_file = page_dir / _META_NAME
    if meta_file.exists():
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            meta = {}

    # 先把所有页读进来，页码需要整本书一起看才能判断对错
    raw: list[tuple[int, str]] = []
    for p in sorted(page_dir.glob("page_*.md")):
        idx = int(p.stem.split("_")[1])
        text = p.read_text(encoding="utf-8").strip()
        raw.append((idx, text))

    page_nos = {idx: (meta.get(str(idx), {}) or {}).get("page_no") for idx, _ in raw}
    page_nos, fixed = _clean_page_numbers(page_nos)

    parts: list[str] = []
    empty = 0
    toc = 0
    all_nos: list[int] = []
    for idx, text in raw:
        page_no = page_nos.get(idx)
        if page_no is not None:
            all_nos.append(page_no)
        if not text:
            empty += 1
            continue
        if not keep_toc and looks_like_toc(text):
            toc += 1
            continue
        parts.append(f"<!-- page {page_no if page_no is not None else idx + 1} -->\n\n{text}")

    merged = "\n\n".join(parts)
    merged, appendix_subs = normalize_appendix(merged)

    stats = {
        "pages": len(raw),
        "empty": empty,
        "toc_dropped": toc,
        "pageno_fixed": fixed,
        "appendix_subs": appendix_subs,
        "page_range": (min(all_nos), max(all_nos)) if all_nos else None,
        "chars": sum(len(x) for x in parts),
    }
    return merged, stats


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", required=True, help="PDF 文件名（不含 .pdf）")
    parser.add_argument("--out", default="", help="输出 Markdown 文件名（默认同 --pdf）")
    parser.add_argument("--keep-toc", action="store_true", help="保留目录页（默认剔除）")
    args = parser.parse_args()

    page_dir = TEXTBOOKS_MD_DIR / args.pdf
    if not page_dir.exists():
        print(f"未找到分页目录: {page_dir}")
        return 1

    merged, stats = merge_pages(page_dir, keep_toc=args.keep_toc)
    if not merged.strip():
        print("没有可合并的 OCR 分页文件")
        return 1

    out_md = TEXTBOOKS_MD_DIR / f"{args.out or args.pdf}.md"
    out_md.write_text(merged, encoding="utf-8")

    rng = stats["page_range"]
    print(f"合并完成: {stats['pages']} 页 → {out_md.name}")
    print(f"  页码范围 {rng[0]}–{rng[1]}，空页 {stats['empty']}，"
          f"剔除目录页 {stats['toc_dropped']}，修正页码 {stats['pageno_fixed']} 页，"
          f"附录降级 {stats['appendix_subs']} 条，共 {stats['chars']} 字符")
    return 0


if __name__ == "__main__":
    sys.exit(main())
