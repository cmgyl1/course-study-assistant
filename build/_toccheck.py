# -*- coding: utf-8 -*-
"""核对合并阶段会剔除哪些页，防止目录判据误杀正文/附录页。

跑法：
    python build/_toccheck.py --pdf "计算机网络（第8版）_谢希仁_上半"

对每页打印 TOC=True/False，并把被判为目录页的**第一行**打出来，
便于人工确认"剔的确实是目录，而不是附录习题解答"。
"""
import argparse
import io
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(r"D:\atomcode\大学生软件")
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from engine.config import TEXTBOOKS_MD_DIR              # noqa: E402
from merge_ocr_pages import looks_like_toc             # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    args = ap.parse_args()

    d = TEXTBOOKS_MD_DIR / args.pdf
    if not d.exists():
        print("未找到分页目录:", d)
        return 1

    dropped: list[tuple[int, str]] = []
    kept = 0
    total = 0
    for p in sorted(d.glob("page_*.md")):
        idx = int(p.stem.split("_")[1])
        text = p.read_text(encoding="utf-8").strip()
        if not text:
            continue
        total += 1
        if looks_like_toc(text):
            first = next((l.strip() for l in text.splitlines() if l.strip()), "")
            dropped.append((idx, first[:56]))
        else:
            kept += 1

    print("=" * 70)
    print("%s：非空页 %d，判为目录页 %d，保留 %d" % (args.pdf, total, len(dropped), kept))
    print("=" * 70)
    for idx, first in dropped:
        print("  剔 p%03d  %s" % (idx, first))
    return 0


if __name__ == "__main__":
    sys.exit(main())
