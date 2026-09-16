# -*- coding: utf-8 -*-
"""原始 OCR 框 + 版面判定探针（表格还原 / 图区定位共用）。

输出：build/probe_boxes.log
用法：python probe_boxes.py [页码...]   (1-based，默认表格页 + 漏图页)
"""
import sys
from pathlib import Path

ROOT = Path(r"D:\atomcode\大学生软件")
sys.path.insert(0, str(ROOT / "src"))

import pymupdf
from rapidocr_onnxruntime import RapidOCR
from engine.config import TEXTBOOKS_DIR
from engine.layout import (_as_boxes, split_chrome, group_lines, join_line,
                           figure_regions, heading_level, restore_page)

PDF = "计算机网络（第8版）_谢希仁_上半"
DPI = 200
DEFAULT_PAGES = [24, 159, 160, 181, 61, 62, 63]


def main(pages):
    log_path = ROOT / "build" / "probe_boxes.log"
    ocr = RapidOCR()
    doc = pymupdf.open(str(TEXTBOOKS_DIR / f"{PDF}.pdf"))
    tmp = ROOT / "build" / "_probe.png"
    with log_path.open("w", encoding="utf-8") as log:
        for pno in pages:
            page = doc[pno - 1]
            pix = page.get_pixmap(dpi=DPI)
            pix.save(str(tmp))
            res, _ = ocr(str(tmp))
            W, H = pix.width, pix.height
            log.write(f"\n{'=' * 78}\n===== p{pno}  W={W} H={H} =====\n")
            boxes = _as_boxes(res)
            log.write(f"-- 原始框 {len(boxes)} 个（按 y 排序）--\n")
            for b in sorted(boxes, key=lambda r: (r.cy, r.x0)):
                log.write(f"  x{b.x0:6.0f}-{b.x1:6.0f} y{b.y0:6.0f}-{b.y1:6.0f} "
                          f"w={b.w:5.0f} c={(b.x0 + b.x1) / 2:6.0f} | {b.text}\n")

            body, dropped, pn = split_chrome(boxes, W, H)
            lines = group_lines(body)
            log.write(f"-- 合并行 {len(lines)} 条（页码字节={pn}，丢弃={len(dropped)}）--\n")
            for i, ln in enumerate(lines):
                x0 = min(r.x0 for r in ln)
                x1 = max(r.x1 for r in ln)
                y0 = min(r.y0 for r in ln)
                y1 = max(r.y1 for r in ln)
                t = join_line(ln)
                lv = heading_level(t)
                log.write(f"  [{i:02d}] y{y0:5.0f}-{y1:5.0f} x{x0:5.0f}-{x1:5.0f} "
                          f"w={x1 - x0:5.0f} nbox={len(ln)}"
                          f"{(' H' + str(lv)) if lv else ''} | {t}\n")

            regions = figure_regions(body, lines, W)
            log.write(f"-- 图区 {len(regions)} 个 --\n")
            for r in regions:
                log.write(f"  y{r['y0']:.0f}-{r['y1']:.0f} h={r['y1'] - r['y0']:.0f} "
                          f"x{r['x0']:.0f}-{r['x1']:.0f} | {r['caption']}\n")

            info = restore_page(res, W, H)
            log.write("-- markdown --\n")
            log.write(info["markdown"] + "\n")
    doc.close()
    print("done:", log_path)


if __name__ == "__main__":
    main([int(a) for a in sys.argv[1:]] or DEFAULT_PAGES)
