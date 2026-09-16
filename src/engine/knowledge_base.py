"""教材知识库：Markdown 教材 → 章节切块 → 向量化入库 → 语义检索（RAG）。

设计要点：
- 存储：ChromaDB 持久化到 data/vector_store（教材与题库使用独立 collection，物理隔离）；
- Embedding：轻量字符 n-gram 哈希向量（零下载、零依赖、确定性），
  避免 chromadb 默认 embedding 往 C 盘用户目录下载模型（违背"不占 C 盘"偏好）；
  将来启用 Ollama + bge-m3 时，仅需替换 embedding 函数，接口不变；
- 检索：余弦相似度 top-k，返回章节片段原文 + 出处元数据。
"""
from __future__ import annotations

import re
from pathlib import Path

import chromadb
from chromadb.api.types import EmbeddingFunction, Documents, Embeddings

from .config import VECTOR_STORE_DIR
from .retrieval import infer_chapter

TEXTBOOK_COLLECTION = "textbooks"      # 教材库
QUESTION_COLLECTION = "question_bank"  # 题库（分离检索）

_CHUNK_TARGET_CHARS = 900   # 切块目标字符数
_CHUNK_MAX_CHARS = 1500     # 切块上限


class NGramEmbeddingFunction(EmbeddingFunction[Documents]):
    """字符 n-gram 哈希 embedding（768 维），确定性、零依赖、无需下载模型。

    对中文教材：n=1,2,3 字符 n-gram 足以捕捉词语级语义；对跨语言文本表现稳定。
    """

    def __init__(self, n_grams=(1, 2, 3), dims: int = 768) -> None:
        self.n_grams = n_grams
        self.dims = dims

    @staticmethod
    def name() -> str:
        """chromadb 要求 embedding function 暴露 name（用于冲突校验）。"""
        return "ngram-hash-embedding"

    def _embed(self, text: str) -> list[float]:
        import numpy as np

        vec = np.zeros(self.dims, dtype=np.float32)
        norm = 0.0
        for n in self.n_grams:
            for i in range(len(text) - n + 1):
                gram = text[i : i + n]
                h = int(hashlib_sha256(gram), 16)
                idx = h % self.dims
                sign = 1.0 if (h >> 63) & 1 else -1.0
                vec[idx] += sign
        norm = float(np.linalg.norm(vec))
        if norm > 0:
            vec /= norm
        return vec.tolist()

    def __call__(self, input: Documents) -> Embeddings:
        return [self._embed(t) for t in input]


def hashlib_sha256(s: str) -> str:
    import hashlib

    return hashlib.sha256(s.encode("utf-8")).hexdigest()


_CLIENT_CACHE: chromadb.Client | None = None


def _get_client() -> chromadb.Client:
    """获取 chromadb 客户端（模块级缓存，避免重复创建 PersistentClient）。"""
    global _CLIENT_CACHE
    if _CLIENT_CACHE is None:
        VECTOR_STORE_DIR.mkdir(parents=True, exist_ok=True)
        _CLIENT_CACHE = chromadb.PersistentClient(path=str(VECTOR_STORE_DIR))
    return _CLIENT_CACHE


def _split_markdown_by_headings(text: str) -> list[tuple[str, str]]:
    """按 Markdown 标题切块，返回 [(标题路径, 内容)]。

    标题路径形如 "第一章 概述 > 1.1 定义"，用于知识树与出处展示。
    """
    lines = text.splitlines()
    chunks: list[tuple[str, str]] = []
    heading_stack: list[str] = []
    # 与 heading_stack 平行的层级表。**不能**用 `len(stack) >= level` 弹栈：
    # 下半册从 `### 5.8.2…` 半途开始（第5章起于上半册），栈里首项 level=3，
    # 再来 `## 5.9…` 时 len=1 不满足 >=2，5.9 会被错挂到 5.8.2 名下，
    # section_path 变成"5.8.2… > 5.9…"（章一级丢失）。同 retrieval.parse_markdown。
    levels: list[int] = []
    current_path = ""
    current_lines: list[str] = []

    def flush():
        nonlocal current_lines, current_path
        if current_lines:
            content = "\n".join(current_lines).strip()
            if content:
                chunks.append((current_path, content))
            current_lines = []

    for line in lines:
        m = re.match(r"^(#{1,6})\s+(.*)$", line.strip())
        if m:
            flush()
            level = len(m.group(1))
            title = m.group(2).strip()
            # 维护标题栈：低层级标题覆盖同层或更深层
            while levels and levels[-1] >= level:
                levels.pop()
                heading_stack.pop()
            if not heading_stack:
                chap = infer_chapter(title)          # 半途开始的书 → 补章一级
                if chap:
                    levels.append(1)
                    heading_stack.append(chap)
            levels.append(level)
            heading_stack.append(title)
            current_path = " > ".join(heading_stack)
        else:
            current_lines.append(line)
    flush()

    # 合并过小的块（<200 字符的相邻块并入前一块）
    merged: list[tuple[str, str]] = []
    for path, content in chunks:
        if merged and len(content) < 200:
            last_path, last_content = merged[-1]
            merged[-1] = (last_path, f"{last_content}\n\n{content}")
        else:
            merged.append((path, content))
    return merged


def _further_split(content: str, path: str) -> list[tuple[str, str]]:
    """把超长块按段落进一步切分，返回 [(路径, 内容)]。"""
    if len(content) <= _CHUNK_MAX_CHARS:
        return [(path, content)]
    paragraphs = re.split(r"\n\s*\n", content)
    out: list[tuple[str, str]] = []
    buf = ""
    for p in paragraphs:
        if buf and len(buf) + len(p) > _CHUNK_TARGET_CHARS:
            out.append((path, buf.strip()))
            buf = ""
        buf += p + "\n\n"
    if buf.strip():
        out.append((path, buf.strip()))
    return out


# PPT 课件标题页/页脚残留（每章重复出现，非正文，入库前剔除）
_SLIDE_CHROME_PATTERNS = [
    re.compile(r"^谢希仁\s*编著$"),
    re.compile(r"^计算机网络（第\s*\d+\s*版）$"),
    re.compile(r"^课件制作人[：:].*$"),
    re.compile(r"^第\s*[一二三四五六七八九十百\d]+\s*章$"),  # 无 # 前缀的章页脚（真标题带 #）
]


def _strip_slide_chrome(text: str) -> str:
    """剔除 PPT 课件页眉/页脚残留行（如 '谢希仁 编著' / '计算机网络（第 8 版）' / 裸 '第 2 章'）。

    这类行随每章标题页反复出现，混入正文后污染检索结果与 Word 教材。
    真实章节标题以 '#' 开头（'# 第1章'），不受影响。
    """
    out = []
    for line in text.splitlines():
        s = line.strip()
        if any(p.match(s) for p in _SLIDE_CHROME_PATTERNS):
            continue
        out.append(line)
    return "\n".join(out)


def _merge_fragments(text: str) -> str:
    """把 PPT 转换出的碎片行合并为连贯段落。

    PPT 每页文本框按行输出，常常"一句一行"且句间无空行，
    导致检索返回时上下文断裂。规则：
    - 标题行（# 开头）与列表行（- 开头）原样保留；
    - 连续的普通文本行合并为一个段落（空格连接）；
    - 空行作为段落分隔。
    """
    lines = text.splitlines()
    out: list[str] = []
    buf: list[str] = []

    def flush() -> None:
        if buf:
            out.append(" ".join(buf))
            buf.clear()

    for line in lines:
        s = line.rstrip()
        stripped = s.strip()
        if not stripped:
            flush()  # 空行 → 段落结束
            continue
        if stripped.startswith("#") or stripped.startswith("-") or stripped.startswith("* "):
            flush()
            out.append(s)
        else:
            buf.append(stripped)
    flush()
    return "\n\n".join(out)


def ingest_textbook(md_path: Path | str, course: str, doc_title: str = "") -> int:
    """把一篇教材 Markdown 切块并向量化入库。返回入库块数。"""
    md_path = Path(md_path)
    text = md_path.read_text(encoding="utf-8")
    title = doc_title or md_path.stem

    # 先剔除 PPT 页眉/页脚残留，再合并碎片行 → 连贯段落，最后切块
    text = _strip_slide_chrome(text)
    text = _merge_fragments(text)

    raw_chunks = _split_markdown_by_headings(text)
    chunks: list[tuple[str, str]] = []
    for path, content in raw_chunks:
        chunks.extend(_further_split(content, path))

    client = _get_client()
    collection = client.get_or_create_collection(
        name=TEXTBOOK_COLLECTION, embedding_function=NGramEmbeddingFunction()
    )
    # 数据污染修复：先删除该文档的旧块（重导入后块数变化时，
    # 旧索引 id 若不清除会成为孤儿数据永久留在库里）。
    try:
        collection.delete(where={"source_file": md_path.name})
    except Exception:
        pass
    ids = [f"{md_path.stem}:{i}" for i in range(len(chunks))]
    docs = [c[1] for c in chunks]
    metadatas = [
        {
            "course": course,
            "doc_title": title,
            "section_path": c[0],
            "source_file": md_path.name,
        }
        for c in chunks
    ]
    collection.upsert(ids=ids, documents=docs, metadatas=metadatas)
    return len(chunks)


def ingest_textbook_dir(course: str) -> int:
    """入库某课程在 textbooks_md 下的全部 Markdown。"""
    from .config import TEXTBOOKS_MD_DIR

    total = 0
    for md in sorted(TEXTBOOKS_MD_DIR.glob(f"*{course}*.md")):
        total += ingest_textbook(md, course)
    return total


def delete_textbook(source_file: str, course: str = "") -> int:
    """删除某教材在库中的全部块（测试清理 / 数据重建用）。返回删除数。

    ⚠ chromadb 的 where **不支持多键直接并列**：
        {"a": 1, "b": 2}          → ValueError: Expected where to have exactly one operator
        {"$and": [{"a": 1}, {"b": 2}]}  → 正确
    之前这里直接把两个键拼成一个 dict，删除必然抛异常，又被 `except` 吞掉 →
    **清理静默失效**（实测测试课程在库里残留 2 块，还进了看板统计）。
    """
    client = _get_client()
    collection = client.get_or_create_collection(
        name=TEXTBOOK_COLLECTION, embedding_function=NGramEmbeddingFunction()
    )
    conds = [{"source_file": source_file}]
    if course:
        conds.append({"course": course})
    where: dict = conds[0] if len(conds) == 1 else {"$and": conds}
    try:
        res = collection.delete(where=where)
    except Exception:
        return 0
    return len(res) if res else 0


def search_textbook(query: str, course: str = "", top_k: int = 5) -> list[dict]:
    """语义检索教材知识库。返回 [{content, course, doc_title, section_path, distance}]。"""
    client = _get_client()
    collection = client.get_or_create_collection(
        name=TEXTBOOK_COLLECTION, embedding_function=NGramEmbeddingFunction()
    )
    where = {"course": course} if course else None
    result = collection.query(
        query_texts=[query], n_results=top_k, where=where
    )
    items: list[dict] = []
    docs = (result.get("documents") or [[]])[0]
    metas = (result.get("metadatas") or [[]])[0]
    dists = (result.get("distances") or [[]])[0]
    for d, m, dist in zip(docs, metas, dists):
        items.append(
            {
                "content": d,
                "course": (m or {}).get("course", ""),
                "doc_title": (m or {}).get("doc_title", ""),
                "section_path": (m or {}).get("section_path", ""),
                "source_file": (m or {}).get("source_file", ""),
                # 余弦距离可能 >1（n-gram 向量相似度可负），归一化到 [0,1]
                "score": max(0.0, round(1.0 - float(dist), 4)),
            }
        )
    return items


def get_section_content(section_path: str, course: str = "", top_k: int = 3) -> list[dict]:
    """按章节路径取回教材原文片段（供知识树点击查看）。

    库中 section_path 是标题栈累积路径（如 '第5章 > 5.9 … > 5.3.2 …'），
    与单个节点标题无法精确相等，因此采用：
    1) 语义检索节点标题；2) 按"编号前缀"或"标题文本"宽松匹配过滤。
    """
    import re as _re

    client = _get_client()
    collection = client.get_or_create_collection(
        name=TEXTBOOK_COLLECTION, embedding_function=NGramEmbeddingFunction()
    )
    where = {"course": course} if course else None
    tail = section_path.split(" > ")[-1].strip()
    # 节点标题的编号前缀，如 "5.3" / "5.3.2"
    m = _re.match(r"^([\d.]+)\s*", tail)
    num = m.group(1) if m else ""

    result = collection.query(query_texts=[tail], n_results=top_k * 8, where=where)
    docs = (result.get("documents") or [[]])[0]
    metas = (result.get("metadatas") or [[]])[0]
    dists = (result.get("distances") or [[]])[0]

    items: list[dict] = []
    for d, meta, dist in zip(docs, metas, dists):
        sp = (meta or {}).get("section_path", "")
        if not sp:
            continue
        segs = [s.strip() for s in sp.split(">")]
        hit = False
        if num:
            # 库中某段以相同编号开头（5.3 匹配 5.3 / 5.3.2 段）
            hit = any(s.startswith(num) for s in segs)
        if not hit and tail:
            hit = any(tail in s or s in tail for s in segs)
        if not hit:
            continue
        items.append({
            "content": d,
            "doc_title": (meta or {}).get("doc_title", ""),
            "section_path": sp,
            "score": max(0.0, round(1.0 - float(dist), 4)),
        })
        if len(items) >= top_k:
            break
    return items


def get_course_count() -> dict[str, int]:
    """统计教材库各课程块数（用于进度看板）。"""
    client = _get_client()
    collection = client.get_or_create_collection(
        name=TEXTBOOK_COLLECTION, embedding_function=NGramEmbeddingFunction()
    )
    try:
        data = collection.get(include=["metadatas"])
    except Exception:
        return {}
    counts: dict[str, int] = {}
    for m in data.get("metadatas", []) or []:
        c = (m or {}).get("course", "未知")
        counts[c] = counts.get(c, 0) + 1
    return counts
