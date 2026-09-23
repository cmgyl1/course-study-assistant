"""自学模块：知识树 / 知识点讲解 / Word 教材生成与批注归档。

- 知识树：从教材 Markdown 的标题层级提取章节结构（学生按图索骥）；
- 讲解：基于教材原文做 **BM25 词法检索**（与离线阅读器同一套引擎，见 retrieval.py），
  返回命中的原文段落作为讲解依据；AI 生成讲解为预留能力，当前未启用；
- Word 教材：把教材 Markdown 转成 .docx（python-docx），交本机 Word/WPS 批注，
  软件负责把批注后的文件归档到 annotations/，可随时调出。
"""
from __future__ import annotations

import re
import threading
from pathlib import Path

from .config import TEXTBOOKS_MD_DIR, TEXTBOOKS_DOCX_DIR, ANNOTATIONS_DIR
from .retrieval import Retriever, build_from_markdown_files, infer_chapter


# ---------- 知识树 ----------

def _node_sort_key(title: str) -> tuple:
    """按标题中的章节编号排序：'8.1 xxx'→(8,1)，'第3章'→(3,0)，无编号→(999,)。"""
    import re as _re

    m = _re.match(r"^(\d+)(?:\.(\d+))?", title.strip())
    if m:
        return (int(m.group(1)), int(m.group(2) or 0))
    m = _re.match(r"^第([一二三四五六七八九十百0-9]+)章", title.strip())
    if m:
        zh = m.group(1)
        if zh.isdigit():
            return (int(zh), 0)
        num = sum({"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
                   "六": 6, "七": 7, "八": 8, "九": 9}.get(c, 0)
                  for c in zh if c in "一二三四五六七八九")
        return (num or 99, 0)
    return (999, 0)


# ---------- 知识点提取（jieba 高频术语） ----------

# 停用词：通用虚词/教材用语/编号词，不进入知识点
_STOPWORDS = {
    "一个", "一种", "一些", "这个", "这样", "这里", "这些", "那样", "那些",
    "进行", "可以", "使用", "通过", "称为", "就是", "由于", "如果", "因此",
    "以及", "其中", "之间", "上述", "下面", "上面", "首先", "然后", "同时",
    "本章", "本节", "图中", "所示", "如图", "例如", "包括", "需要", "具有",
    "对于", "关于", "过程", "方式", "方法", "情况", "时候", "主要", "重要",
    "基本", "一般", "非常", "比较", "可能", "必须", "能够", "信息", "数据",
    "网络", "计算机", "协议", "服务", "通信", "系统", "技术", "报文", "分组",
    # 课件页眉/页脚词（每页重复，非知识点）
    "希仁", "编著", "谢希仁", "第8版", "第8 版", "版",
}
_CONCEPT_CACHE: dict[str, list[str]] = {}


def _split_concepts(text: str, top_n: int = 12) -> list[str]:
    """从一段正文中提取高频术语（jieba 分词 + 词频 + 停用词过滤）。"""
    import jieba
    import re as _re

    words: dict[str, int] = {}
    for seg in jieba.cut(text):
        seg = seg.strip()
        if len(seg) < 2 or len(seg) > 12:
            continue
        if not _re.search(r"[\u4e00-\u9fffA-Za-z]", seg):
            continue
        if seg in _STOPWORDS:
            continue
        # 跳过以编号/纯数字开头的词
        if _re.match(r"^[\d\s.、,，]+$", seg):
            continue
        words[seg] = words.get(seg, 0) + 1

    ranked = sorted(words.items(), key=lambda kv: -kv[1])
    # 去掉纯子串（如 "协议" 是 "通信协议" 的子串）保留更长词
    keep: list[str] = []
    for w, c in ranked:
        if any(w in k and len(k) > len(w) for k, _ in ranked):
            continue
        keep.append(w)
        if len(keep) >= top_n:
            break
    return keep


def extract_concepts(md_path: Path | str, top_n: int = 12) -> dict[str, list[str]]:
    """按章节提取知识点：{章节路径: [知识点...]}。带缓存。"""
    md_path = Path(md_path)
    if str(md_path) in _CONCEPT_CACHE:
        return _CONCEPT_CACHE[str(md_path)]

    text = md_path.read_text(encoding="utf-8")
    result: dict[str, list[str]] = {}
    current = "全章"
    buf: list[str] = []

    def flush():
        if buf:
            result[current] = _split_concepts("\n".join(buf), top_n)
            buf.clear()

    for line in text.splitlines():
        m = re.match(r"^(#{1,4})\s+(.*)$", line.strip())
        if m:
            flush()
            current = m.group(2).strip()
        elif line.strip():
            buf.append(line)
    flush()
    _CONCEPT_CACHE[str(md_path)] = result
    return result


def build_knowledge_tree(md_path: Path | str) -> list[dict]:
    """从教材 Markdown 提取标题层级，生成知识树（同级按章节编号排序）。"""
    md_path = Path(md_path)
    text = md_path.read_text(encoding="utf-8")
    tree: list[dict] = []
    stack: list[dict] = []  # 各级最近节点

    for line in text.splitlines():
        m = re.match(r"^(#{1,6})\s+(.*)$", line.strip())
        if not m:
            continue
        level = len(m.group(1))
        node = {"title": m.group(2).strip(), "level": level, "children": []}
        while stack and stack[-1]["level"] >= level:
            stack.pop()
        if not stack:
            # 下半册从"5.8.2…"半途开始（第5章起于上半册），栈里没有章这一层。
            # 不补的话，下半册每个小节都会**平铺成树的顶层**（实测"5.8.2TCP的
            # 拥塞控制方法"就是这么冒出来的），树里看不出它们属于第5章。
            chap = infer_chapter(node["title"])
            if chap:
                stack.append({"title": chap, "level": 1, "children": []})
                tree.append(stack[-1])
        if stack:
            stack[-1]["children"].append(node)
        else:
            tree.append(node)
        stack.append(node)

    # 去掉 level 字段，同级按编号排序
    def strip_level(nodes: list[dict]) -> list[dict]:
        out = []
        for n in sorted(nodes, key=lambda x: _node_sort_key(x["title"])):
            out.append({"title": n["title"], "children": strip_level(n["children"])})
        return out

    return strip_level(tree)


def _attach_concepts(nodes: list[dict], concepts: dict[str, list[str]]) -> list[dict]:
    """把知识点合并进树节点：每个节点携带 concepts 列表（供 UI 展示/检索）。"""
    for n in nodes:
        title = n["title"]
        n["concepts"] = concepts.get(title, [])
        n["children"] = _attach_concepts(n["children"], concepts)
    return nodes


def get_course_tree(course: str) -> list[dict]:
    """取某课程全部教材的知识树（每本教材一个子树，节点携带知识点）。"""
    trees: list[dict] = []
    for md in sorted(TEXTBOOKS_MD_DIR.glob(f"*{course}*.md")):
        tree = build_knowledge_tree(md)
        if tree:
            concepts = extract_concepts(md)
            trees.append({"book": md.stem, "tree": _attach_concepts(tree, concepts)})
    return trees


# ---------- 教材检索（BM25 词法链路） ----------

# 语料与 tools/build_reader.py、tests/test_retrieval.py **同源**：该课程的教材
# Markdown，排除"课件版"（那是 PPT 摘要、不是教材原文）。
#
# 为什么必须缓存：建 BM25 索引约 6s（1698 块），而查询只要 0.3ms。所以按课程在
# **进程内只建一次**，并由 UI 启动时调 warm_up() 在后台线程预热，用户不会有感知。
#
# 历史教训：这里原本走 knowledge_base.search_textbook（chromadb + 字符 n-gram
# 哈希 embedding）。那条路只有 261 块语料（覆盖 15.4%），score 恒为 0（排序信息
# 丢失），且没有任何拒答机制 —— 实测「三次握手」返回的是 IP 地址片段，
# 「量子纠缠」照样返回 5 条垃圾。改用 BM25 后同一批查询 7:0 全胜。
_RETRIEVER_CACHE: dict[str, Retriever | None] = {}
_RETRIEVER_LOCK = threading.Lock()


def _course_markdowns(course: str) -> list[Path]:
    from .textbook_reader import list_books

    return [m for m in list_books(course) if "课件" not in m.name]


def get_retriever(course: str = "") -> Retriever | None:
    """取某课程的 BM25 检索器（进程内缓存）。该课程没有教材时返回 None。"""
    if course in _RETRIEVER_CACHE:
        return _RETRIEVER_CACHE[course]
    with _RETRIEVER_LOCK:
        # 双重检查：等锁期间可能已被另一个线程建好了
        if course in _RETRIEVER_CACHE:
            return _RETRIEVER_CACHE[course]
        mds = _course_markdowns(course)
        retriever = (Retriever(build_from_markdown_files(mds, course=course))
                     if mds else None)
        _RETRIEVER_CACHE[course] = retriever
        return retriever


def warm_up(course: str = "") -> bool:
    """预热检索索引（供 UI 在后台线程调用，避免首次提问卡 6 秒）。"""
    return get_retriever(course) is not None


# ---------- 语料规模统计（首页 KPI / 期末看板） ----------

def count_textbook_chunks(md_path: Path | str, course: str = "") -> int:
    """单份教材 Markdown 的检索片段数（只切块、不建索引，毫秒级）。"""
    return len(build_from_markdown_files([Path(md_path)], course=course))


def count_course_chunks(course: str) -> int:
    """某课程全部教材的检索片段数（排除课件版）。"""
    mds = _course_markdowns(course)
    if not mds:
        return 0
    return len(build_from_markdown_files(mds, course=course))


def get_course_count() -> dict[str, int]:
    """各课程的教材检索片段数（只列出有教材的课程）。

    替代原 `knowledge_base.get_course_count()`（chroma 块数）。语义一致 ——
    都是"该课程教材切成了多少可检索片段"；但数据源改为**真实检索语料**
    （`retrieval.build_from_markdown_files`），因此首页 KPI 与自学页实际
    检索到的块数**完全对齐**（旧实现两者差 6.5 倍：261 vs 1698）。
    切块实测 0.03s/册，可放心在 UI 线程调用。
    """
    from .config import COURSES

    out: dict[str, int] = {}
    for course in COURSES:
        n = count_course_chunks(course)
        if n:
            out[course] = n
    return out


def explain_topic(query: str, course: str = "", top_k: int = 5) -> dict:
    """基于教材原文检索讲解知识点 —— BM25 词法链路，与离线阅读器同一套。

    返回：{query, status, tokens, used_tokens, evidence, sections, answer,
          ai_available, missing_tokens, message}
    - status ∈ {"ok", "not_found", "empty_query", "no_corpus"}。
      **not_found 必须被 UI 如实展示** —— 书里没有的概念就说没有，不能像旧路
      那样不管问什么都返回 top-5（用户会以为书里讲过）。
    - used_tokens：真正参与检索的词（= tokens 去掉 missing_tokens）。界面拿它做
      命中词高亮，与离线阅读器的 `r.known` 完全对应。
    - missing_tokens：提问里有、但全库都没出现过的词（如「薛定谔」），
      用于提示"已按其余关键词检索"。
    - ai_available=False 表示当前是"检索原文"模式（AI 讲解为预留能力）。
    """
    retriever = get_retriever(course)
    if retriever is None:
        return {
            "query": query, "status": "no_corpus", "tokens": [],
            "used_tokens": [], "evidence": [], "sections": [], "answer": "",
            "ai_available": False, "missing_tokens": [],
            "message": "该课程暂无教材，请先在「资料管理」导入教材。",
        }

    res = retriever.search(query, top_k=top_k)
    evidence = [
        {
            "content": p.get("text", ""),
            "doc_title": p.get("doc_title", ""),
            "section_path": p.get("section_path", ""),
            "page_no": p.get("page_no"),
            "source_file": p.get("source_file", ""),
            "score": p.get("score", 0.0),
        }
        for p in res.get("passages", [])
    ]
    ai_available = _is_ai_available()
    answer = (generate_ai_answer(query, evidence)
              if ai_available and evidence else "")
    return {
        "query": query,
        "status": res.get("status", "ok"),
        "tokens": res.get("tokens", []),
        "used_tokens": res.get("used_tokens", []),
        "evidence": evidence,
        "sections": res.get("sections", []),
        "answer": answer,
        "ai_available": ai_available,
        "missing_tokens": res.get("missing_tokens", []),
        "message": res.get("message", ""),
    }


def search_section(section_path: str, course: str = "", top_k: int = 3) -> list[dict]:
    """按章节路径检索该节原文片段（用节点标题当查询词）。

    与 `textbook_reader.get_section_blocks`（按原序读整节）分工不同：
    本函数返回**按相关度排序**的 top-k 片段，服务"问答/速览"场景；
    阅读场景请用保序版本。

    原实现走 chroma（`knowledge_base.get_section_content`），已随该依赖移除，
    改为复用自学页同一套 BM25 引擎。
    """
    retriever = get_retriever(course)
    if retriever is None:
        return []
    tail = (section_path or "").split(" > ")[-1].strip()
    if not tail:
        return []
    res = retriever.search(tail, top_k=top_k)
    return [
        {
            "content": p.get("text", ""),
            "doc_title": p.get("doc_title", ""),
            "section_path": p.get("section_path", ""),
            "page_no": p.get("page_no"),
            "score": p.get("score", 0.0),
        }
        for p in res.get("passages", [])
    ]


_AI_AVAILABLE_CACHE: tuple[float, bool] | None = None
_AI_PROBE_TIMEOUT = 0.3  # 本地端口探测，0.3s 足够（连接拒绝立即返回）


def _is_ai_available() -> bool:
    """检测 Ollama 是否已启用（结果缓存 30s，避免每次提问都探测端口）。"""
    import time as _time

    global _AI_AVAILABLE_CACHE
    now = _time.time()
    if _AI_AVAILABLE_CACHE and now - _AI_AVAILABLE_CACHE[0] < 30:
        return _AI_AVAILABLE_CACHE[1]
    try:
        import requests

        r = requests.get("http://127.0.0.1:11434/api/tags",
                         timeout=_AI_PROBE_TIMEOUT)
        ok = r.status_code == 200
    except Exception:
        ok = False
    _AI_AVAILABLE_CACHE = (now, ok)
    return ok


def generate_ai_answer(query: str, evidence: list[dict]) -> str:
    """调用本地 Ollama（qwen2.5:7b）基于教材原文生成讲解。

    约束：只依据 evidence 提供的教材内容组织讲解，不自行编造。
    """
    import requests

    context = "\n\n".join(
        f"[{e['doc_title']} | {e['section_path']}]\n{e['content']}" for e in evidence
    )
    prompt = (
        "你是基于指定教材讲解知识点的助手。请严格依据以下教材原文回答学生提问，"
        "如果原文不足，明确说明教材未覆盖。\n\n"
        f"学生提问：{query}\n\n教材原文：\n{context}\n\n"
        "请用中文、分点、通俗地讲解。"
    )
    try:
        r = requests.post(
            "http://127.0.0.1:11434/api/generate",
            json={"model": "qwen2.5:7b", "prompt": prompt, "stream": False},
            timeout=120,
        )
        r.raise_for_status()
        return r.json().get("response", "").strip()
    except Exception as e:
        return f"[AI 讲解暂不可用：{e}]"


# ---------- Word 教材生成与批注归档 ----------

def generate_docx_textbook(md_path: Path | str, out_dir: Path | str | None = None) -> Path:
    """把教材 Markdown 转成 .docx（供 Word/WPS 批注），输出到 textbooks_docx/。"""
    from docx import Document

    md_path = Path(md_path)
    out_dir = Path(out_dir) if out_dir else TEXTBOOKS_DOCX_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{md_path.stem}.docx"

    doc = Document()
    for line in md_path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        m = re.match(r"^(#{1,6})\s+(.*)$", s)
        if m:
            level = min(len(m.group(1)), 4)
            doc.add_heading(m.group(2).strip(), level=level)
        elif s.startswith("- "):
            doc.add_paragraph(s[2:], style="List Bullet")
        elif s:
            doc.add_paragraph(s)
        else:
            doc.add_paragraph("")
    doc.save(str(out))
    return out


def generate_all_docx_textbooks() -> list[Path]:
    """把 textbooks_md/ 下所有教材生成 Word 版，返回生成的文件列表。"""
    out: list[Path] = []
    for md in sorted(TEXTBOOKS_MD_DIR.glob("*.md")):
        docx = generate_docx_textbook(md)
        out.append(docx)
    return out


def archive_annotation(docx_path: Path | str, course: str) -> Path:
    """归档批注后的 Word 教材到 annotations/（按课程分目录），返回归档路径。"""
    docx_path = Path(docx_path)
    target_dir = ANNOTATIONS_DIR / course
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / docx_path.name
    target.write_bytes(docx_path.read_bytes())
    return target


def list_annotations(course: str = "") -> list[Path]:
    """列出批注归档（可按课程过滤）。"""
    base = ANNOTATIONS_DIR if not course else ANNOTATIONS_DIR / course
    if not base.exists():
        return []
    return sorted(p for p in base.rglob("*.docx"))
