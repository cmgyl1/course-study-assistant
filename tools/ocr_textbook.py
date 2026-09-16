"""教材扫描件 OCR 转 Markdown（版面还原 + 裁图内嵌 + 断点续传）。

用法：
    python tools/ocr_textbook.py --pdf "计算机网络（第8版）_谢希仁_上半" --start 0 --end 250
    python tools/ocr_textbook.py --pdf "..." --start 100 --end 150   # 继续

每页 OCR 结果经版面还原后存为 data/textbooks_md/<name>/page_XXXX.md，已存在的页自动跳过
（断点续传，中断不丢进度）。失败页会记录并在整批结束后自动重试一轮。

版面还原由 engine.layout.restore_page 完成，解决四类问题：
边栏文字混入正文、同行被切成多个框、段落边界丢失、页脚页码当正文。

**裁图（原文内嵌图的来源）**：由 engine.layout.figure_regions 定位图区，
再按坐标从 PDF 直接裁剪成 PNG 存到 data/figures/<name>/——是"裁"不是"识别"，
所以零识别误差、零幻觉。图片引用会内嵌到图题所在的正文位置，
后续阅读器/UI 即可把原文和图排在一起。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from engine.config import TEXTBOOKS_DIR, TEXTBOOKS_MD_DIR, FIGURES_DIR, OCR_CACHE_DIR
from engine.layout import restore_page

_META_NAME = "_meta.json"
_FIG_PAD = 12          # 裁图时四周留白（像素，200dpi 下约 4pt）


def _load_meta(out_dir: Path) -> dict:
    f = out_dir / _META_NAME
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_meta(out_dir: Path, meta: dict) -> None:
    (out_dir / _META_NAME).write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8"
    )


def _ocr_cached(doc, ocr, index: int, tmp_img: Path, dpi: int,
                cache_dir: Path | None):
    """取某页的 OCR 原始检测框与渲染宽高，带落盘缓存。

    OCR 是整条链里唯一耗时的一步（全书 485 页约 34 分钟），而版面还原
    （engine/layout.py）的判据经常要调整重跑。把**原始检测框**按页落盘后，
    改版面只需秒级重放，不必再等一次整书 OCR —— 这是"发现 bug 及时修"的前提。
    缓存的是 OCR 输出（不可变），不是版面结果（会变），所以改了 layout 也不会读到旧结论。
    """
    if cache_dir is not None:
        f = cache_dir / f"page_{index:04d}.json"
        if f.exists():
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
                return d["items"], d["w"], d["h"]
            except (json.JSONDecodeError, OSError, KeyError):
                pass                              # 缓存损坏 → 重新 OCR 覆盖

    page = doc[index]
    pix = page.get_pixmap(dpi=dpi)
    pix.save(str(tmp_img))
    items, _ = ocr(str(tmp_img))
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / f"page_{index:04d}.json").write_text(
            json.dumps({"w": pix.width, "h": pix.height, "items": items or []},
                       ensure_ascii=False),
            encoding="utf-8")
    return items, pix.width, pix.height


def _process_page(doc, ocr, index: int, out_dir: Path, fig_dir: Path,
                  fig_rel: str, tmp_img: Path, dpi: int,
                  do_figures: bool = True, cache_dir: Path | None = None) -> dict:
    """渲染 + OCR + 版面还原 + 裁图一页，落盘 page_XXXX.md，返回该页统计。"""
    import pymupdf

    page = doc[index]
    result, img_w, img_h = _ocr_cached(doc, ocr, index, tmp_img, dpi, cache_dir)
    scale = dpi / 72.0

    counter = {"n": 0}

    def crop(region: dict) -> str | None:
        """按图区坐标从 PDF 裁剪一张图，返回可内嵌的 URL。"""
        counter["n"] += 1
        name = f"page_{index:04d}_fig{counter['n']}.png"
        clip = pymupdf.Rect(
            max(0.0, region["x0"] - _FIG_PAD) / scale,
            max(0.0, region["y0"] - _FIG_PAD) / scale,
            min(img_w, region["x1"] + _FIG_PAD) / scale,
            min(img_h, region["y1"] + _FIG_PAD) / scale,
        )
        shot = page.get_pixmap(dpi=dpi, clip=clip)
        shot.save(str(fig_dir / name))
        return f"{fig_rel}/{name}"

    if do_figures:
        # 重跑该页前先清掉旧图，避免上一版多出来的图残留在目录里
        for old in fig_dir.glob(f"page_{index:04d}_fig*.png"):
            try:
                old.unlink()
            except OSError:
                pass
        on_figure = crop
    else:
        on_figure = None

    info = restore_page(result, img_w, img_h, on_figure=on_figure)
    (out_dir / f"page_{index:04d}.md").write_text(info["markdown"], encoding="utf-8")
    return {
        "page_no": info["page_no"],
        "n_boxes": info["n_boxes"],
        "n_paras": info["n_paras"],
        "n_tables": info["n_tables"],
        "n_chars": len(info["markdown"]),
        "dropped": info["dropped"],
        "figure_text": info["figure_text"],
        "figures": [
            {
                "file": Path(f["url"]).name if f["url"] else None,
                "caption": f["caption"],
                "h_px": round(f["y1"] - f["y0"]),
            }
            for f in info["figures"]
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", required=True, help="PDF 文件名（不含 .pdf）")
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--end", type=int, default=99999)
    parser.add_argument("--dpi", type=int, default=200,
                        help="渲染 dpi（实测 200 能认出 150 会漏掉的表格行号）")
    parser.add_argument("--no-retry", action="store_true", help="跳过失败页重试")
    parser.add_argument("--force", action="store_true", help="忽略已存在的分页文件，全部重跑")
    parser.add_argument("--no-figures", action="store_true", help="只还原文字，不裁图")
    parser.add_argument("--no-cache", action="store_true",
                        help="忽略 OCR 缓存，强制重新识别（默认走缓存，改版面判据时可秒级重放）")
    parser.add_argument("--force-cache-rebuild", action="store_true",
                        help="先删除该册的 OCR 缓存再跑（缓存被污染时用）")
    args = parser.parse_args()

    pdf_path = TEXTBOOKS_DIR / f"{args.pdf}.pdf"
    if not pdf_path.exists():
        print(f"未找到: {pdf_path}")
        return 1

    import pymupdf
    from rapidocr_onnxruntime import RapidOCR

    out_dir = TEXTBOOKS_MD_DIR / args.pdf
    out_dir.mkdir(parents=True, exist_ok=True)
    fig_dir = FIGURES_DIR / args.pdf
    fig_dir.mkdir(parents=True, exist_ok=True)
    # 合并后的 Markdown 位于 data/textbooks_md/<name>.md，图位于 data/figures/<name>/
    fig_rel = f"../figures/{args.pdf}"

    cache_dir = OCR_CACHE_DIR / args.pdf
    if args.no_cache:
        cache_dir = None
    elif args.force_cache_rebuild and cache_dir.exists():
        for old in cache_dir.glob("*.json"):
            try:
                old.unlink()
            except OSError:
                pass

    doc = pymupdf.open(str(pdf_path))
    total = doc.page_count
    end = min(args.end, total)
    ocr = RapidOCR()
    tmp_img = out_dir / "_page_tmp.png"
    meta = _load_meta(out_dir)

    print(f"OCR {args.pdf}: 处理页 {args.start + 1}–{end} / {total}"
          f"（版面还原 + {'仅文字' if args.no_figures else '裁图'}"
          f" + 断点续传 + {'无缓存' if cache_dir is None else 'OCR 缓存'}）")
    t0 = time.time()
    done = 0
    n_figs = 0
    n_tables = 0
    failed: list[int] = []

    for i in range(args.start, end):
        if not args.force and (out_dir / f"page_{i:04d}.md").exists():
            continue
        try:
            st = _process_page(doc, ocr, i, out_dir, fig_dir, fig_rel, tmp_img,
                               args.dpi, do_figures=not args.no_figures,
                               cache_dir=cache_dir)
            meta[str(i)] = st
            n_figs += len(st["figures"])
            n_tables += st.get("n_tables") or 0
            done += 1
            if done % 10 == 0:
                el = time.time() - t0
                print(f"  进度 {i + 1}/{end}，已处理 {done} 页 / {n_figs} 图"
                      f" / {n_tables} 表，耗时 {el:.0f}s",
                      flush=True)
        except Exception as e:                      # noqa: BLE001 —— 单页失败不应中断整批
            failed.append(i)
            print(f"  [失败] 第 {i + 1} 页: {type(e).__name__}: {e}", flush=True)

    if failed and not args.no_retry:
        print(f"重试 {len(failed)} 个失败页…", flush=True)
        still: list[int] = []
        for i in failed:
            try:
                st = _process_page(doc, ocr, i, out_dir, fig_dir, fig_rel, tmp_img,
                                   args.dpi, cache_dir=cache_dir)
                meta[str(i)] = st
                n_figs += len(st["figures"])
                n_tables += st.get("n_tables") or 0
                done += 1
            except Exception as e:                  # noqa: BLE001
                still.append(i)
                print(f"  [仍失败] 第 {i + 1} 页: {e}", flush=True)
        failed = still

    _save_meta(out_dir, meta)
    doc.close()
    if tmp_img.exists():
        tmp_img.unlink()

    total_figs = sum(len(v.get("figures") or []) for v in meta.values())
    total_tables = sum(v.get("n_tables") or 0 for v in meta.values())
    print(f"完成：本次处理 {done} 页（{n_figs} 图 / {n_tables} 表），"
          f"累计 {total_figs} 图 / {total_tables} 表，耗时 {time.time() - t0:.0f}s")
    if failed:
        print(f"仍有 {len(failed)} 页失败：{[p + 1 for p in failed]}（可重跑本命令续传）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
