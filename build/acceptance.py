# -*- coding: utf-8 -*-
"""验收：检索准确性与拒答 + 插图/表格是否落在原文位置。

跑法：
    python build/acceptance.py --log build/accept_full.log

一份日志覆盖三层：
  L1 检索 —— 9 条查询逐条给 PASS/FAIL。**不是"有结果就算过"**，
             而是核对命中的章节是否真的是该知识点所属的那一章/节。
  L2 拒答 —— 书里没有的词必须如实说"未找到"，不返回猜测性结果。
  L3 落位 —— 插图是否紧邻它自己的图题、图片文件是否真实存在、表格是否还原。
"""
import io
import sys
from pathlib import Path

# Windows 控制台默认 GBK，中文会乱码；重定向到 UTF-8 包装器，
# 落盘用 --log 让脚本自己写文件（不依赖 shell 重定向的编码设置）。
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(r"D:\atomcode\大学生软件")
sys.path.insert(0, str(ROOT / "src"))

from engine import textbook_reader as reader                        # noqa: E402
from engine.retrieval import Retriever, build_from_markdown_files   # noqa: E402

BOOKS = [
    "计算机网络（第8版）_谢希仁_上半",
    "计算机网络（第8版）_谢希仁_下半",
]

# (查询, 期望状态, 命中的章节路径里必须出现的关键字)
CASES = [
    ("物理层", "ok", "物理层"),
    ("物理层原理", "ok", "物理层"),
    ("什么是物理层", "ok", "物理层"),
    ("CSMA/CD", "ok", "CSMA"),
    ("双绞线", "ok", "双绞线"),
    ("信道复用", "ok", "复用"),
    ("三次握手", "ok", "第5章"),
    ("为什么不直接用两次握手", "ok", "第5章"),
    ("量子纠缠", "not_found", None),
]

buf: list[str] = []


def out(line: str = "") -> None:
    print(line)
    buf.append(line)


def main() -> int:
    argv = sys.argv[1:]
    log_path = None
    if "--log" in argv:
        i = argv.index("--log")
        log_path = Path(argv[i + 1])

    mds = [reader.TEXTBOOKS_MD_DIR / f"{b}.md" for b in BOOKS]
    mds = [m for m in mds if m.exists()]
    if not mds:
        out("没有可用的合并 Markdown，先跑 OCR 与合并。")
        return 1

    chunks = build_from_markdown_files(mds, course="计算机网络")
    r = Retriever(chunks)

    out("=" * 74)
    out("L1/L2 检索与拒答")
    out("=" * 74)
    out("语料: " + str(r.stats()))
    out("")

    passed = failed = 0
    for q, expect_status, keyword in CASES:
        res = r.search(q, top_k=5)
        paths = [s["section_path"] for s in res["sections"]] + \
                [p["section_path"] for p in res["passages"]]
        if expect_status == "not_found":
            good = res["status"] == "not_found" and not paths
        else:
            good = res["status"] == "ok" and any(keyword in p for p in paths)
        passed += good
        failed += (not good)

        out("-" * 74)
        out("%s  Q: %s   status=%s  放宽轮数=%s"
            % ("PASS" if good else "FAIL", q, res["status"], res["relax_rounds"]))
        out("      tokens=%s" % res["tokens"])
        if res["message"]:
            out("      msg: " + res["message"])
        for s in res["sections"][:3]:
            out("      [章节] %s  p%s  %s" % (s["section_path"], s["page_no"], s["score"]))
        for p in res["passages"][:2]:
            t = p["text"][:64].replace("\n", " ")
            out("      [原文] p%s | %s | %s" % (p["page_no"], p["section_path"], t))

    out("")
    out("=" * 74)
    out("L3 插图 / 表格落位")
    out("=" * 74)

    total_fig = ok_fig = 0
    n_tables = 0
    tbl_bad: list[str] = []
    bad: list[str] = []
    for book in BOOKS:
        md = reader.TEXTBOOKS_MD_DIR / f"{book}.md"
        if not md.exists():
            continue
        items = reader.load_items(md)
        cur_page, seq = None, []
        for it in items:
            if it["page"] is not None:
                cur_page = it["page"]
            seq.append((it, cur_page))
        n_fig = n_tbl = 0
        for i, (it, pg) in enumerate(seq):
            if it["kind"] == "table":
                n_tbl += 1
                # 表格质量：行数>=2、每行列数一致、列数>=2 —— 否则说明列聚类切歪了
                rows = [r.strip() for r in it["text"].splitlines() if r.strip().startswith("|")]
                cells = [len(r.strip("|").split("|")) for r in rows]
                if len(rows) < 2 or len(set(cells)) != 1 or cells[0] < 2:
                    tbl_bad.append("%s p%s 行=%d 列=%s %r"
                                   % (book[-2:], pg, len(rows), sorted(set(cells)),
                                      it["text"][:36]))
            if it["kind"] != "figure":
                continue
            n_fig += 1
            total_fig += 1
            nxt, nxt_pg = (seq[i + 1][0], seq[i + 1][1]) if i + 1 < len(seq) else (None, None)
            cap = it["text"].strip()
            nxt_text = nxt["text"].strip() if nxt else ""
            cap_ok = nxt is not None and nxt["kind"] == "para" and nxt_text == cap
            pg_ok = nxt_pg == pg
            file_ok = (md.parent / it["url"]).exists()
            if cap_ok and pg_ok and file_ok:
                ok_fig += 1
            else:
                bad.append("%s | 图题=%r | 图题紧跟=%s 同页=%s 文件存在=%s | 后续=%r"
                           % (book[-2:], cap[:24], cap_ok, pg_ok, file_ok, nxt_text[:24]))
        n_tables += n_tbl
        out("%s：插图 %d 张 / 表格 %d 张" % (book, n_fig, n_tbl))

    out("")
    out("插图落位合格：%d / %d%s"
        % (ok_fig, total_fig,
           ("（%.1f%%）" % (100.0 * ok_fig / total_fig)) if total_fig else ""))
    if bad:
        out("异常清单：")
        for b in bad[:25]:
            out("   " + b)
    out("表格：共 %d 张已还原为 Markdown 表格" % n_tables)
    out("表格结构合格：%d / %d%s"
        % (n_tables - len(tbl_bad), n_tables,
           ("（%.1f%%）" % (100.0 * (n_tables - len(tbl_bad)) / n_tables)) if n_tables else ""))
    if tbl_bad:
        out("表格异常清单：")
        for b in tbl_bad[:15]:
            out("   " + b)

    out("")
    out("=" * 74)
    out("汇总：检索 %d 通过 / %d 失败；插图落位 %d/%d；表格 %d（结构合格 %d）"
        % (passed, failed, ok_fig, total_fig, n_tables, n_tables - len(tbl_bad)))
    out("=" * 74)

    if log_path:
        log_path.write_text("\n".join(buf) + "\n", encoding="utf-8")
        print("（已写日志 %s）" % log_path)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
