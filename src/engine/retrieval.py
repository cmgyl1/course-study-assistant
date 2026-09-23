"""教材检索层：切块 + 标题索引 + BM25 词法检索 + 查询放宽 + 拒答。

设计依据（与用户确认的验收标准一致）：

- 数据源是 OCR 后的**教材原文**，不是课件摘要；
- 输出统一为 {章节出处, 原文片段, 页码}，只贴原文、不做任何概括；
- **标题索引是第一入口** —— 标题是人工写的、噪声最低，而且是唯一带"这块讲什么"
  主题信息的字段；chunk 级检索分不清"主题块"与"顺带提及块"，标题可以；
- 未命中标题时退回**段落级 BM25** 检索（学生的提问方式常常不是教材的章节名）；
- **查询放宽**按 IDF 逐级砍词，绝不降到停用词 —— "的/是/为什么"这类虚词 IDF 趋近 0，
  天然排在最后被砍，因此不需要额外黑名单，换一本教材也成立；
- 某实词 DF=0（整本书都没出现过）→ **如实拒答**，不返回垃圾。DF=0 是事实而非判断，
  比任何相似度阈值都硬。

语义向量路（bge-small-zh）作为**可选增强**：由 embed_backend 注入，模型文件不存在时
自动降级为纯词法，接口不变。

本模块零下载、零额外依赖（jieba 已随工具链提供）。
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

import jieba
import jieba.posseg as pseg

jieba.setLogLevel(60)

# ---------------------------------------------------------------- 分词

# 词性黑名单：虚词、标点、代词、副词、连词、介词、助词、量词、方位词。
# 注意必须包含 "ad"（副词性语素）—— 实测 "直接" 被 jieba 标为 ad 而非 d，
# 漏掉它会导致 "为什么不直接用两次握手" 退化成只用一个无意义副词检索。
_STOP_POS = {
    "w", "u", "p", "c", "d", "r", "y", "e", "o", "f", "q",
    "uj", "ul", "uv", "uz", "ug", "ud", "zg",
    "ad", "dg",
}

# 高频虚词与疑问词（词性标注偶尔会把它们标成实词，这里再兜一层）
_STOPWORDS = set("""
的 了 是 在 和 就 都 而 及 与 着 或 之 也 有 这 那 上 下 里 中 到 说 要 会 能 可 以 等
为 从 对 被 把 让 使 给 但 却 因 所以 因此 如果 那么 这样 那样 时候
什么 怎么 怎样 如何 为什么 哪 哪些 谁 何时 何地 多少
可以 需要 应该 必须 可能 已经 正在 将要 通过 由于 关于 对于 根据 按照
以及 并且 或者 但是 然而 不过 就是 还是 也是 都是 只是 一些 一种 一样
这个 那个 这些 那些 这里 那里
""".split())

_PAGE_MARK_RE = re.compile(r"^<!--\s*page\s+(\d+)\s*-->$")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_IMAGE_RE = re.compile(r"^!\[(.*?)\]\((.*?)\)\s*$")
_TABLE_ROW_RE = re.compile(r"^\|.*\|$")
_SENT_RE = re.compile(r"[^。！？；]*[。！？；]|[^。！？；]+")


def tokenize(text: str) -> list[str]:
    """中文分词 + 词性过滤 + 停用词过滤。返回小写化的实词列表。"""
    out: list[str] = []
    for word, flag in pseg.cut(text or ""):
        w = word.strip()
        if not w or flag in _STOP_POS or w in _STOPWORDS:
            continue
        # 过滤单个中文字（信息量太低），保留单字符英文/数字
        if len(w) < 2 and not w.isascii():
            continue
        if not w.isalnum() and not any("\u4e00" <= ch <= "\u9fff" for ch in w):
            continue
        out.append(w.lower())
    return out


# ---------------------------------------------------------------- 解析与切块

_CHAP_LEAD_RE = re.compile(r"^(\d{1,2})\s*[.．]")


def infer_chapter(title: str) -> str:
    """从"5.9TCP的运输连接管理"这类小节标题反推所属章名 → "第5章"。

    教材被拆成上下两册 PDF，**下半册是从第5章中间（5.8.2）开始的**：
    文件里第一个标题就是 `### 5.8.2…`，标题栈里没有"第5章"这一层。
    不补的话，下半册所有原文的 section_path 都是"5.8.2… > 5.9… > 5.9.1…"，
    章一级丢失，检索命中后无法回答"这段在书里哪一章"。
    """
    m = _CHAP_LEAD_RE.match(title or "")
    return f"第{m.group(1)}章" if m else ""


def parse_markdown(md_text: str) -> list[dict]:
    """Markdown → 元素序列 [{kind, level, text, path, page}]。

    kind ∈ {"heading", "para", "figure", "table"}：
    - 识别 `<!-- page N -->` 页码标记（由 OCR 合并阶段写入），
      标题行维护标题栈生成 section_path；
    - 独立成行的 `![图题](路径)` 识别为 figure 元素（原文内嵌图），
      不混进段落文本 —— 否则图片路径会被分词成 figures/png/page 之类的噪声词；
    - 连续的 `| a | b |` 行识别为 **table** 元素（OCR 阶段表格还原的产物），
      单独成块，渲染时才会还原成真正的表格，而不是一串带竖线的文本。
    """
    items: list[dict] = []
    stack: list[str] = []
    # 与 stack 平行的层级表。**不能**用 `len(stack) >= level` 弹栈：
    # 教材分册后，下半册开头就是 `### 5.8.2…`（第5章起于上半册），栈里第一个元素是
    # level=3；此后再来 `## 5.9…` 时 len(stack)=1 不满足 >=2，5.9 就被错挂到 5.8.2
    # 底下，section_path 变成"5.8.2 > 5.9 > 5.9.1"（实测三次握手就落在这种脏路径上）。
    levels: list[int] = []
    buf: list[str] = []
    table_buf: list[str] = []
    page: int | None = None

    def flush() -> None:
        nonlocal buf
        if buf:
            items.append({
                "kind": "para",
                "level": 0,
                "text": "\n".join(buf).strip(),
                "path": " > ".join(stack),
                "page": page,
            })
            buf = []

    def flush_table() -> None:
        nonlocal table_buf
        if table_buf:
            items.append({
                "kind": "table",
                "level": 0,
                "text": "\n".join(table_buf),
                "path": " > ".join(stack),
                "page": page,
            })
            table_buf = []

    for raw in md_text.splitlines():
        line = raw.strip()
        if _TABLE_ROW_RE.match(line):
            flush()                       # 表格前若有未提交段落，先落地
            table_buf.append(line)
            continue
        flush_table()                     # 非表格行 → 先把已收集的表格提交
        m = _PAGE_MARK_RE.match(line)
        if m:
            page = int(m.group(1))
            continue
        m = _HEADING_RE.match(line)
        if m:
            level = len(m.group(1))
            title = m.group(2).strip()
            while levels and levels[-1] >= level:
                levels.pop()
                stack.pop()
            if not stack:
                chap = infer_chapter(title)          # 半途开始的书 → 补章一级
                if chap:
                    levels.append(1)
                    stack.append(chap)
            levels.append(level)
            stack.append(title)
            items.append({
                "kind": "heading",
                "level": level,
                "text": title,
                "path": " > ".join(stack),
                "page": page,
            })
            continue
        m = _IMAGE_RE.match(line)
        if m:
            items.append({
                "kind": "figure",
                "level": 0,
                "text": m.group(1).strip(),
                "url": m.group(2).strip(),
                "path": " > ".join(stack),
                "page": page,
            })
            continue
        if not line:
            flush()
            continue
        buf.append(line)
    flush_table()
    flush()
    return items


def _split_sentences(text: str) -> list[tuple[str, bool]]:
    """按句切分，返回 [(句子, 是否段落首句)]。"""
    out: list[tuple[str, bool]] = []
    for para in text.split("\n"):
        para = para.strip()
        if not para:
            continue
        sents = [s.strip() for s in _SENT_RE.findall(para) if s.strip()]
        for k, s in enumerate(sents):
            out.append((s, k == 0))
    return out


def _chunk_text(text: str, target: int, overlap_sents: int) -> list[str]:
    """把一段文本切成约 target 字、相邻重叠 overlap_sents 句的块。"""
    sents = _split_sentences(text)
    if not sents:
        return []
    chunks: list[str] = []
    i, n = 0, len(sents)
    while i < n:
        buf: list[str] = []
        ln = 0
        j = i
        while j < n and ln < target:
            s, is_start = sents[j]
            buf.append(("\n" if is_start and buf else "") + s)
            ln += len(s)
            j += 1
        if not buf:
            break
        chunks.append("".join(buf).strip())
        if j >= n:
            break
        i = max(i + 1, j - overlap_sents)
    return chunks


def build_chunks(
    items: list[dict],
    doc_title: str = "",
    course: str = "",
    source_file: str = "",
    target: int = 400,
    overlap_sents: int = 1,
    min_chars: int = 60,
) -> list[dict]:
    """元素序列 → 检索块列表。

    每个 section 额外产出一个**标题块**（is_title=True）：
    它是"章节入口"，让"物理层"这类整章主题词能直接命中章节标题，
    而不必去和上百个"提到物理层"的正文块争排序。
    """
    chunks: list[dict] = []
    cur_path: str | None = None
    cur_page: int | None = None
    cur_paras: list[str] = []
    counter = 0

    def flush_section() -> None:
        nonlocal cur_paras, counter
        if not cur_paras:
            return
        body = "\n".join(cur_paras)
        for piece in _chunk_text(body, target, overlap_sents):
            if len(piece) < min_chars:
                if chunks and not chunks[-1].get("is_title"):
                    chunks[-1]["text"] += "\n" + piece
                continue
            chunks.append({
                "id": f"{source_file}#c{counter}",
                "text": piece,
                "section_path": cur_path or "",
                "page_no": cur_page,
                "doc_title": doc_title,
                "source_file": source_file,
                "course": course,
                "is_title": False,
            })
            counter += 1
        cur_paras = []

    for it in items:
        if it["kind"] == "heading":
            flush_section()
            cur_path = it["path"]
            cur_page = it["page"]
            if it["level"] <= 3:      # 章 / 节 / 小节都值得作为入口
                chunks.append({
                    "id": f"{source_file}#t{counter}",
                    "text": it["path"],
                    "section_path": it["path"],
                    "page_no": it["page"],
                    "doc_title": doc_title,
                    "source_file": source_file,
                    "course": course,
                    "is_title": True,
                    "level": it["level"],
                })
                counter += 1
        else:
            if it["kind"] == "figure":
                # 图引用不参与词法检索：路径里的 figures/png/page_0053 只会带来噪声。
                # 图的挂载位置由阅读器按 section_path 自行还原。
                continue
            if cur_path is None:
                cur_path = it["path"]
            if cur_page is None and it["page"] is not None:
                cur_page = it["page"]
            cur_paras.append(it["text"])
    flush_section()
    return chunks


# ---------------------------------------------------------------- BM25

class BM25:
    """标准 BM25（k1=1.5, b=0.75），带倒排表加速。

    IDF 是本方案的核心：它让"的"（DF 占满全库）权重趋近 0、
    "掩码"（DF 很低）权重高，从而解决"关键词被常见字淹没"。
    """

    def __init__(self, tokenized_docs: list[list[str]], k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self.n = len(tokenized_docs)
        self.doc_len = [len(d) for d in tokenized_docs]
        self.avgdl = (sum(self.doc_len) / self.n) if self.n else 0.0

        self.postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        self.doc_tokens: list[set[str]] = []
        df: Counter[str] = Counter()
        for i, tokens in enumerate(tokenized_docs):
            tf = Counter(tokens)
            self.doc_tokens.append(set(tf))
            for term, freq in tf.items():
                self.postings[term].append((i, freq))
                df[term] += 1

        self.df = dict(df)
        self.idf = {
            term: math.log((self.n - d + 0.5) / (d + 0.5) + 1.0)
            for term, d in self.df.items()
        }

    def score(self, query_tokens: list[str]) -> list[float]:
        scores = [0.0] * self.n
        for term in set(query_tokens):
            idf = self.idf.get(term)
            if idf is None:
                continue
            for idx, freq in self.postings.get(term, ()):
                dl = self.doc_len[idx] or 1
                denom = freq + self.k1 * (1 - self.b + self.b * dl / (self.avgdl or 1))
                scores[idx] += idf * freq * (self.k1 + 1) / denom
        return scores

    def idf_of(self, term: str) -> float:
        return self.idf.get(term, 0.0)


# ---------------------------------------------------------------- 标题索引

class TitleIndex:
    """标题索引：query 与标题词的重合度打分，作为检索的第一入口。"""

    def __init__(self, chunks: list[dict]) -> None:
        self.entries: list[dict] = []
        for i, c in enumerate(chunks):
            if not c.get("is_title"):
                continue
            self.entries.append({
                "idx": i,
                "chunk": c,
                "tokens": set(tokenize(c["text"])),
                "level": int(c.get("level") or 9),
            })

    def match(self, query_tokens: list[str], bm25: BM25,
              top_k: int = 5) -> list[tuple[int, float, int]]:
        """返回 [(块下标, 标题命中分, 命中词数), …]，按命中词数 → 层级 → 得分排序。

        第三个元素（命中词数）是给界面用的：离线阅读器的"命中章节"卡片右上角
        要显示「命中 N 词」，而读取器的 titleTokens 与这里的 tokens 是同一份
        分词结果，所以这个数在两处必然一致。**加性扩展**：调用方只有
        `_one_pass`，排序与筛选逻辑一字未动。
        """
        q = set(query_tokens)
        if not q:
            return []
        scored: list[tuple[int, float, int, int]] = []
        for e in self.entries:
            hit = q & e["tokens"]
            if not hit:
                continue
            # 精度因子：命中词占该标题实词总量的比例。
            # "第2章物理层"（只有"物理层"一个实词，全命中）应明显高于
            # "第2章物理层 > 2.4信道复用技术"（命中 1/4）。
            base = (sum(bm25.idf_of(t) for t in hit)
                    * len(hit) / max(len(e["tokens"]), 1))
            scored.append((e["idx"], base, len(hit), e["level"]))
        # 命中词多优先 → 层级高（章优先）→ 得分高
        scored.sort(key=lambda x: (-x[2], x[3], -x[1]))
        return [(idx, sc, h) for idx, sc, h, _l in scored[:top_k]]


# ---------------------------------------------------------------- 检索主流程

def _rank(
    scores: list[float],
    top_k: int,
    exclude: set[int],
    require_all: list[str] | None = None,
    doc_tokens: list[set[str]] | None = None,
    min_score: float = 1e-9,
):
    """按 BM25 分数取 top_k。

    require_all 非空时为 AND 语义：只保留这些词**全部出现**的块（高精度）。
    由调用方在取不到结果时降级为 None（OR 语义，高召回）。
    """
    pairs = []
    for i, s in enumerate(scores):
        if s <= min_score or i in exclude:
            continue
        if require_all is not None and doc_tokens is not None:
            dt = doc_tokens[i]
            if not all(t in dt for t in require_all):
                continue
        pairs.append((i, s))
    pairs.sort(key=lambda x: -x[1])
    return pairs[:top_k]


def _one_pass(
    tokens: list[str],
    chunks: list[dict],
    bm25: BM25,
    titles: TitleIndex,
    top_k: int,
    title_idx_all: set[int],
    require_all: bool = False,
) -> dict:
    """一轮检索：标题匹配 + 段落级 BM25。"""
    title_hits = titles.match(tokens, bm25, top_k=top_k)

    scores = bm25.score(tokens)
    # 原文段落只从内容块中取：标题块的文本就是路径本身，作为"原文"返回毫无意义。
    passage_hits = _rank(
        scores, top_k * 2, exclude=title_idx_all,
        require_all=tokens if require_all else None,
        doc_tokens=bm25.doc_tokens,
    )

    sections = [{
        "title": chunks[i]["section_path"],
        "section_path": chunks[i]["section_path"],
        "doc_title": chunks[i].get("doc_title", ""),
        "page_no": chunks[i].get("page_no"),
        "source_file": chunks[i].get("source_file", ""),
        "level": chunks[i].get("level"),
        "score": round(s, 4),
        # 标题里命中了几个查询词 —— 界面「命中 N 词」角标用（加性字段，不影响排序）
        "n_hits": n,
    } for i, s, n in title_hits]

    passages = [{
        "text": chunks[i]["text"],
        "section_path": chunks[i].get("section_path", ""),
        "doc_title": chunks[i].get("doc_title", ""),
        "page_no": chunks[i].get("page_no"),
        "source_file": chunks[i].get("source_file", ""),
        "score": round(s, 4),
    } for i, s in passage_hits[:top_k]]

    return {"sections": sections, "passages": passages}


def search(
    question: str,
    chunks: list[dict],
    bm25: BM25,
    titles: TitleIndex,
    top_k: int = 5,
) -> dict:
    """检索主入口：标题 → 段落 → 精度降级 → 拒答。

    Returns:
        dict(query, status, tokens, used_tokens, missing_tokens, relax_rounds,
             sections, passages, message)
        status ∈ {"ok", "not_found", "empty_query"}
    """
    tokens = tokenize(question)
    if not tokens:
        return {
            "query": question, "status": "empty_query", "tokens": [],
            "used_tokens": [], "missing_tokens": [], "relax_rounds": 0,
            "sections": [], "passages": [],
            "message": "未能从提问中提取出有效关键词。",
        }

    known = [t for t in tokens if bm25.df.get(t, 0) > 0]
    missing = [t for t in tokens if bm25.df.get(t, 0) == 0]

    # 拒答判据一：所有实词在全库都没出现过（DF=0）→ 如实告知，绝不返回垃圾。
    # DF=0 是事实而非判断，比任何相似度阈值都硬；虚词（的/是/为什么）已在分词阶段剔除。
    if not known:
        return {
            "query": question, "status": "not_found", "tokens": tokens,
            "used_tokens": [], "missing_tokens": missing, "relax_rounds": 0,
            "sections": [], "passages": [],
            "message": f"书中未找到与「{'、'.join(tokens)}」相关的内容。",
        }

    # 拒答判据二："只是顺带命中字面"。查询有 ≥2 个实词，而**每个命中词**
    # 在全库都只出现 ≤2 次 —— 说明书里并没有真正展开讲这个概念，只是别处顺带提过一次。
    # 实测「量子纠缠」：教材里只有第 7 章"量子密码"顺带出现过 1 次"量子"，
    # 照常返回会让用户以为书里讲过量子纠缠（那句话其实在讲量子计算机与后量子密码学）。
    # 注意判据必须落在"每个命中词都极罕见"上：只要求"命中词少"会误杀
    # 「OSI 七层模型」这类正常提问（"模型"在全库出现十几次，属正常命中）。
    _RARE_DF = 2
    if len(tokens) >= 2 and all(bm25.df.get(t, 0) <= _RARE_DF for t in known):
        return {
            "query": question, "status": "not_found", "tokens": tokens,
            "used_tokens": known, "missing_tokens": missing, "relax_rounds": 0,
            "sections": [], "passages": [],
            "message": f"书中未找到与「{'、'.join(tokens)}」相关的内容。",
        }

    title_idx_all = {i for i, c in enumerate(chunks) if c.get("is_title")}
    result: dict = {"sections": [], "passages": []}
    rounds = 0

    # 第一轮 AND（所有关键词须同时命中，高精度）；取不到结果再降级为 OR（高召回）。
    # 这才是"不断缩小查询词"在检索层面的正确形态 —— BM25 本身是 OR 语义，
    # 单纯减少查询词并不会带来新结果，只有从 AND 放宽到 OR 才会。
    for require_all in (True, False):
        result = _one_pass(known, chunks, bm25, titles, top_k, title_idx_all, require_all)
        if result["sections"] or result["passages"]:
            break
        rounds += 1

    if not result["sections"] and not result["passages"]:
        return {
            "query": question, "status": "not_found", "tokens": tokens,
            "used_tokens": known, "missing_tokens": missing, "relax_rounds": rounds,
            "sections": [], "passages": [],
            "message": f"书中未找到与「{'、'.join(tokens)}」相关的内容。",
        }

    message = ""
    if missing:
        message = (f"「{'、'.join(missing)}」在书中未出现，"
                   f"以下按其余关键词「{'、'.join(known)}」检索。")

    return {
        "query": question,
        "status": "ok",
        "tokens": tokens,
        "used_tokens": known,
        "missing_tokens": missing,
        "relax_rounds": rounds,
        "sections": result["sections"],
        "passages": result["passages"],
        "message": message,
    }


# ---------------------------------------------------------------- 语料构建与持久化

def build_from_markdown_files(md_files: list[Path], course: str = "") -> list[dict]:
    """把多份 Markdown（含页码标记）切块为检索语料。"""
    all_chunks: list[dict] = []
    for md in md_files:
        text = Path(md).read_text(encoding="utf-8")
        items = parse_markdown(text)
        all_chunks.extend(build_chunks(
            items,
            doc_title=Path(md).stem,
            course=course,
            source_file=Path(md).name,
        ))
    return all_chunks


def save_corpus(chunks: list[dict], path: Path | str) -> None:
    Path(path).write_text(
        json.dumps(chunks, ensure_ascii=False, indent=1), encoding="utf-8")


def load_corpus(path: Path | str) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


class Retriever:
    """把语料、BM25 索引、标题索引打包成一个可直接查询的对象。"""

    def __init__(self, chunks: list[dict]) -> None:
        self.chunks = chunks
        self.bm25 = BM25([tokenize(c["text"]) for c in chunks])
        self.titles = TitleIndex(chunks)

    def search(self, question: str, top_k: int = 5) -> dict:
        return search(question, self.chunks, self.bm25, self.titles, top_k=top_k)

    def stats(self) -> dict:
        n_title = sum(1 for c in self.chunks if c.get("is_title"))
        pages = [c.get("page_no") for c in self.chunks if c.get("page_no")]
        return {
            "chunks": len(self.chunks),
            "title_chunks": n_title,
            "passage_chunks": len(self.chunks) - n_title,
            "vocab": len(self.bm25.df),
            "pages": f"{min(pages)}–{max(pages)}" if pages else "-",
            "avg_len": round(sum(len(c["text"]) for c in self.chunks) / max(len(self.chunks), 1)),
        }
