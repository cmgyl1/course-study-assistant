"""题库模块：按科目组织的 Markdown 题库文档（与教材语料物理分离、独立管理）。

题库文档规格（每科一个文件，存于 data/question_banks/）：
    # <课程名> 题库
    > 来源：...（可溯源：高校官网 / GitHub 公开库 / 用户确认来源）
    > 题型数量：选择题 N 道 / 填空题 N 道 / 大题 N 套

    ## 一、选择题
    ### 1. <题干>
    - A. ...
    - B. ...
    - C. ...
    - D. ...
    **答案**：A
    **解析**：...

    ## 二、填空题
    ### 1. <题干，空位用 ____>
    **答案**：...
    **解析**：...

    ## 三、大题
    ### 1. <题目>
    **答案**：...
    **解析**：...

设计：
- 题目从题库文档解析为结构化 dict，按科目缓存；
- 按章节刷：题目可挂 section 元数据；随机组卷：按题型+数量抽取；
- 题库与教材语料分离：各自独立的 Markdown 目录，互不干扰；
- 错题本（wrong_book/）与题库关联：记录题目标识（course + 题号）。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .config import QUESTION_BANKS_DIR, WRONG_BOOK_DIR

SECTION_HEADINGS = {
    "一": "选择题",
    "二": "填空题",
    "三": "大题",
}


def ensure_question_bank_templates() -> list[Path]:
    """为 4 门课创建题库模板文件（若不存在）。"""
    from .config import COURSES

    created: list[Path] = []
    for course, book in COURSES.items():
        path = QUESTION_BANKS_DIR / f"{course}-题库.md"
        if path.exists():
            continue
        path.write_text(
            f"# {course} 题库\n\n"
            f"> 对应教材：{book}\n"
            f"> 来源：（待录入，须为高校历年期末真题，标注出处）\n"
            f"> 题型数量：选择题 0 道 / 填空题 0 道 / 大题 0 套（数量后续按需定）\n\n"
            f"## 一、选择题\n\n<!-- 格式：\n### 1. 题干\n"
            f"- A. ...\n- B. ...\n- C. ...\n- D. ...\n**答案**：A\n**解析**：...\n-->\n\n"
            f"## 二、填空题\n\n<!-- 格式：\n### 1. 题干____\n**答案**：...\n**解析**：...\n-->\n\n"
            f"## 三、大题\n\n<!-- 格式：\n### 1. 题目\n**答案**：...\n**解析**：...\n-->\n",
            encoding="utf-8",
        )
        created.append(path)
    return created


def _parse_question_bank(md_path: Path) -> list[dict]:
    """解析单个题库文档为题目列表。"""
    text = md_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    questions: list[dict] = []
    section = ""
    current: dict | None = None

    def flush():
        nonlocal current
        if current and current.get("stem"):
            questions.append(current)
        current = None

    for line in lines:
        s = line.strip()
        # 分区标题：## 一、选择题
        m = re.match(r"^##\s+([一二三])[、.]\s*(.*)$", s)
        if m:
            flush()
            section = SECTION_HEADINGS.get(m.group(1), m.group(2))
            continue
        # 题号：### 1. 题干
        m = re.match(r"^###\s+(\d+)[.、]\s*(.*)$", s)
        if m:
            flush()
            current = {"no": int(m.group(1)), "type": section, "stem": m.group(2).strip(),
                       "options": [], "answer": "", "explanation": ""}
            continue
        if current is None:
            continue
        # 选项
        m = re.match(r"^-\s*([A-D])[.、]\s*(.*)$", s)
        if m:
            current["options"].append(f"{m.group(1)}. {m.group(2).strip()}")
            continue
        # 答案/解析
        if s.startswith("**答案**"):
            current["answer"] = s.replace("**答案**", "").strip("：: ")
            continue
        if s.startswith("**解析**"):
            current["explanation"] = s.replace("**解析**", "").strip("：: ")
            continue
        # 多行题干续行
        if current and current["stem"] and not current["answer"]:
            if s and not s.startswith("<!--"):
                current["stem"] += " " + s

    flush()
    for q in questions:
        q["course"] = md_path.stem.replace("-题库", "")
    return questions


def load_question_bank(course: str = "") -> list[dict]:
    """加载题库（可按课程过滤），带内存缓存。

    缓存按题库文件修改时间自动失效：用户编辑题库 md 后无需重启即可看到新题。
    """
    if not hasattr(load_question_bank, "_cache"):
        load_question_bank._cache = {}
    # 任一会考题库文件变更 → 整体失效重载
    mtimes = tuple(
        (p.stat().st_mtime_ns, p.name) for p in sorted(QUESTION_BANKS_DIR.glob("*.md"))
    )
    if getattr(load_question_bank, "_mtimes", None) != mtimes:
        load_question_bank._cache = {}
        load_question_bank._mtimes = mtimes
    if course and course in load_question_bank._cache:
        return load_question_bank._cache[course]
    if not course and "" in load_question_bank._cache:
        return load_question_bank._cache[""]

    all_q: list[dict] = []
    for md in sorted(QUESTION_BANKS_DIR.glob("*.md")):
        all_q.extend(_parse_question_bank(md))

    if course:
        filtered = [q for q in all_q if q["course"] == course]
        load_question_bank._cache[course] = filtered
        return filtered
    load_question_bank._cache[""] = all_q
    return all_q


# 注：原有的 index_question_bank / search_question（chroma 题库向量检索）已随
# chromadb 依赖一并移除。二者**从未被 UI 调用**（只有旧测试用过），且用的是与
# 教材旧路同一个 NGramEmbeddingFunction（实测 score 恒为 0，排名信息丢失）。
# 题库的真实使用方式是 load_question_bank（读 Markdown）+ sample_questions（随机组卷）。


def sample_questions(course: str, by_type: dict[str, int] | None = None) -> list[dict]:
    """按题型抽题（随机组卷）。by_type 形如 {"选择题": 10, "填空题": 10, "大题": 2}。"""
    import random

    questions = load_question_bank(course)
    by_type = by_type or {"选择题": 10, "填空题": 10, "大题": 2}
    picked: list[dict] = []
    for qtype, count in by_type.items():
        pool = [q for q in questions if q["type"] == qtype]
        picked.extend(random.sample(pool, min(count, len(pool))))
    random.shuffle(picked)
    return picked


# ---------- 错题本 ----------

def _wrong_book_path() -> Path:
    WRONG_BOOK_DIR.mkdir(parents=True, exist_ok=True)
    return WRONG_BOOK_DIR / "wrong_book.json"


def load_wrong_book() -> list[dict]:
    path = _wrong_book_path()
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def add_wrong_question(course: str, qtype: str, no: int) -> None:
    """答错入错题本（按 course+type+no 去重）。"""
    items = load_wrong_book()
    key = f"{course}:{qtype}:{no}"
    if any(it["key"] == key for it in items):
        return
    items.append({"key": key, "course": course, "type": qtype, "no": no,
                  "wrong_count": 1, "mastered": False})
    _wrong_book_path().write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def mark_wrong_question(key: str, correct: bool) -> None:
    """错题循环：选对→移出错题本；选错→保留并累计次数。"""
    items = load_wrong_book()
    remaining = []
    for it in items:
        if it["key"] != key:
            remaining.append(it)
            continue
        if not correct:
            it["wrong_count"] += 1
            remaining.append(it)
    _wrong_book_path().write_text(json.dumps(remaining, ensure_ascii=False, indent=2), encoding="utf-8")


def get_wrong_questions(course: str = "") -> list[dict]:
    """取错题（未掌握），可选按课程过滤。"""
    items = load_wrong_book()
    if course:
        items = [it for it in items if it["course"] == course]
    return [it for it in items if not it.get("mastered")]
