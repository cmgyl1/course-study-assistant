# -*- coding: utf-8 -*-
"""核对"插图/表格是否落在原文对应位置"——不用目视，用可判定的三条准则：

  ① 图块之后**紧跟同名图题**段落（教材排版：图在上、图题在下）；
  ② 图块与图题段的**页码相同**（同一页内容被拆到不同页 = 顺序错乱）；
  ③ 图块引用的图片文件真实存在（否则 UI 上是裂图）。

再抽样打印几节的块序列，便于与 build/probe_boxes.log 的原始行顺序逐条对照。
输出：build/verify_inline.log
"""
import sys
from pathlib import Path

ROOT = Path(r"D:\atomcode\大学生软件")
sys.path.insert(0, str(ROOT / "src"))

from engine import textbook_reader as reader          # noqa: E402

BOOKS = ["计算机网络（第8版）_谢希仁_上半", "计算机网络（第8版）_谢希仁_下半"]

out: list[str] = []
total = ok = 0
bad: list[str] = []
samples: list[str] = []

for book in BOOKS:
    md = reader.TEXTBOOKS_MD_DIR / f"{book}.md"
    if not md.exists():
        out.append("[跳过] 未找到 %s.md" % book)
        continue
    items = reader.load_items(md)

    cur_page = None
    seq = []
    for it in items:
        if it["page"] is not None:
            cur_page = it["page"]
        seq.append((it, cur_page))

    n_fig = n_tbl = 0
    for i, (it, pg) in enumerate(seq):
        if it["kind"] == "table":
            n_tbl += 1
        if it["kind"] != "figure":
            continue
        total += 1
        n_fig += 1
        nxt, nxt_pg = (seq[i + 1][0], seq[i + 1][1]) if i + 1 < len(seq) else (None, None)
        cap = it["text"].strip()
        nxt_text = nxt["text"].strip() if nxt else ""
        cap_ok = nxt is not None and nxt["kind"] == "para" and nxt_text == cap
        pg_ok = nxt_pg == pg
        file_ok = (md.parent / it["url"]).exists()
        if cap_ok and pg_ok and file_ok:
            ok += 1
        else:
            bad.append(
                "%s | 图题=%r | 图块page=%s 后续page=%s | 图题紧跟=%s 同页=%s 文件存在=%s | 后续块=%r"
                % (book[-2:], cap[:26], pg, nxt_pg, cap_ok, pg_ok, file_ok, nxt_text[:26])
            )
    out.append("%s：图 %d / 表 %d" % (book, n_fig, n_tbl))

    # 抽样：每本书取前 3 个含图节的块序列
    picked = 0
    cur_section = None
    buf: list[str] = []
    for it in items:
        if it["kind"] == "heading":
            if buf and picked < 3:
                samples.append("\n".join(buf))
                picked += 1
            buf = []
            cur_section = it
        if cur_section is None:
            continue
        tag = {"heading": "H", "para": "P", "figure": "图", "table": "表"}[it["kind"]]
        body = it.get("url") or it.get("text", "")
        buf.append("   [%s] p%s  %s" % (tag, it["page"], body[:64]))
    if buf and picked < 3:
        samples.append("\n".join(buf))

out.append("")
out.append("== 插图位置校验 ==")
out.append("总计 %d 张：位置正确 %d，异常 %d" % (total, ok, total - ok))
if total:
    out.append("合格率 %.1f%%" % (100.0 * ok / total))
if bad:
    out.append("")
    out.append("异常清单（最多 40 条）：")
    out += ["  " + b for b in bad[:40]]

out.append("")
out.append("== 抽样：章节块序列（[H]标题 [P]段落 [图]插图 [表]表格）==")
out += samples[:6]

(ROOT / "build" / "verify_inline.log").write_text("\n".join(out), encoding="utf-8")
print("ok")
