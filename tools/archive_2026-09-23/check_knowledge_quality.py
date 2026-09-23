# -*- coding: utf-8 -*-
"""数据质量探针：检查 vector_store 污染与 textbooks_md 清洗质量（只读，不修改）。"""
import sys, re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from engine import knowledge_base as kb
from engine.config import TEXTBOOKS_MD_DIR, VECTOR_STORE_DIR

print("=" * 60)
print("[1] chroma 集合概览")
client = kb._get_client()
for c in client.list_collections():
    cnt = c.count()
    print(f"  collection={c.name}  count={cnt}")

print("=" * 60)
print("[2] 教材库按 source_file / course 统计")
coll = client.get_or_create_collection(
    name=kb.TEXTBOOK_COLLECTION, embedding_function=kb.NGramEmbeddingFunction()
)
data = coll.get(include=["metadatas", "documents"])
ids, metas, docs = data["ids"], data["metadatas"], data["documents"]
from collections import Counter, defaultdict
src_count = Counter((m or {}).get("source_file", "?") for m in metas)
course_count = Counter((m or {}).get("course", "?") for m in metas)
print("  source_file:", dict(src_count))
print("  course:", dict(course_count))

print("=" * 60)
print("[3] id 模式检查（疑似残留旧块：同一文件 id 不连续/重复）")
id_by_src = defaultdict(list)
for i, m in zip(ids, metas):
    id_by_src[(m or {}).get("source_file", "?")].append(int(i.split(":")[-1]))
for src, idxs in id_by_src.items():
    idxs.sort()
    gaps = [a for a, b in zip(idxs, idxs[1:]) if b != a + 1]
    dup = len(idxs) - len(set(idxs))
    print(f"  {src}: {len(idxs)} 条, 最大索引 {idxs[-1]}, 断号 {len(gaps)}, 重复 {dup}")
    if gaps[:5]:
        print(f"    断号示例: {gaps[:5]}")

print("=" * 60)
print("[4] 内容污染抽样（页眉页脚/编号残留/垃圾字符）")
pattern_page = re.compile(r"(^|\n)\s*(第\s*\d+\s*页|page\s*\d+|\d+\s*/\s*\d+)\s*($|\n)", re.I)
pattern_header = re.compile(r"(希仁|编著|第8版|谢希仁)")
junk_chars = re.compile(r"[□■◇◆▲▼•◦⦁·・]")
n_page, n_header, n_junk, empty = 0, 0, 0, 0
sample_bad = []
for i, (d, m) in enumerate(zip(docs, metas)):
    if not d or not d.strip():
        empty += 1
        continue
    if pattern_page.search(d):
        n_page += 1
        if len(sample_bad) < 6:
            sample_bad.append(("页码残留", d[:80].replace("\n", "⏎")))
    if pattern_header.search(d):
        n_header += 1
        if len(sample_bad) < 6:
            sample_bad.append(("页眉残留", d[:80].replace("\n", "⏎")))
    if junk_chars.search(d):
        n_junk += 1
print(f"  空内容块: {empty}")
print(f"  含页码模式: {n_page}")
print(f"  含页眉词(希仁/编著/第8版): {n_header}")
print(f"  含特殊符号: {n_junk}")
for tag, s in sample_bad:
    print(f"  [{tag}] {s}")

print("=" * 60)
print("[5] 文档长度分布")
lens = [len(d) for d in docs]
print(f"  块数 {len(lens)}, 平均 {sum(lens)//max(len(lens),1)} 字, 最短 {min(lens)}, 最长 {max(lens)}")
short = [i for i, l in enumerate(lens) if l < 30]
print(f"  超短块(<30字) {len(short)} 个")
for i in short[:8]:
    print(f"    #{i} [{docs[i][:60].replace(chr(10), '⏎')}]")

print("=" * 60)
print("[6] 教材源文件结构检查")
for md in sorted(TEXTBOOKS_MD_DIR.glob("*.md")):
    text = md.read_text(encoding="utf-8")
    lines = text.splitlines()
    heads = [l for l in lines if re.match(r"^#{1,6}\s+", l.strip())]
    print(f"  {md.name}: {len(lines)} 行, {len(heads)} 个标题")
    for h in heads[:10]:
        print(f"    {h.strip()[:60]}")
    if len(heads) > 10:
        print(f"    ... 其余 {len(heads)-10} 个标题")

print("=" * 60)
print("[7] 检索质量抽查：'TCP 三次握手' 与 '物理层'")
for q in ["TCP 三次握手", "物理层"]:
    res = kb.search_textbook(q, course="计算机网络", top_k=3)
    print(f"  查询「{q}」→ {len(res)} 条")
    for r in res:
        print(f"    score={r['score']} | {r['section_path'][:50]} | {r['content'][:50].replace(chr(10),'⏎')}")

print("=" * 60)
print("[8] 题库文件解析")
from engine import question_bank as qb
for md in sorted((Path(__file__).resolve().parent.parent / "data" / "question_banks").glob("*.md")):
    qs = qb._parse_question_bank(md)
    print(f"  {md.name}: 解析出 {len(qs)} 题")
    for q in qs[:3]:
        print(f"    [{q['type']}] #{q['no']} {q['stem'][:40]} ans={q['answer'][:20]}")
print("DONE")
