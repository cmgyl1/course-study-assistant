"""期末冲刺模块：复习提纲生成 / 错题重刷 / 进度看板。

- 复习提纲：基于教材知识树生成章节级复习清单；
  若本地 Ollama 可用，进一步由模型提炼重点/易考点；
  未启用时给出章节结构 + 章节标题层面的复习要点。
- 错题重刷：复用 practice.make_wrong_review_session（对/错循环机制）。
- 进度看板：聚合各模块进度（教材入库块数 / 题库题数 / 错题数 / 批注数 / Word 教材数）。
"""
from __future__ import annotations

from pathlib import Path

from .config import TEXTBOOKS_MD_DIR, TEXTBOOKS_DOCX_DIR, ANNOTATIONS_DIR
from .knowledge_base import get_course_count
from .question_bank import load_question_bank, get_wrong_questions
from .study import get_course_tree, list_annotations, _is_ai_available


# ---------- 复习提纲 ----------

def _flatten_tree(nodes: list[dict], prefix: str = "") -> list[str]:
    """把知识树展平为章节路径列表。"""
    out: list[str] = []
    for n in nodes:
        path = f"{prefix}{n['title']}"
        out.append(path)
        out.extend(_flatten_tree(n["children"], f"{path} > "))
    return out


def generate_review_outline(course: str) -> dict:
    """生成某课程复习提纲。

    返回：{course, chapters: [{book, items: [章节路径]}], ai_available, ai_summary}
    - ai_available=True 时 ai_summary 为模型生成的重点提炼；
    - 未启用 AI 时 ai_summary=""（界面显示"启用本地 AI 后可生成重点提炼"）。
    """
    trees = get_course_tree(course)
    chapters = []
    for t in trees:
        items = _flatten_tree(t["tree"])
        chapters.append({"book": t["book"], "items": items})

    ai_available = _is_ai_available()
    ai_summary = ""
    if ai_available:
        ai_summary = _ai_review_summary(course, chapters)

    return {
        "course": course,
        "chapters": chapters,
        "ai_available": ai_available,
        "ai_summary": ai_summary,
    }


def _ai_review_summary(course: str, chapters: list[dict]) -> str:
    """调用本地模型生成复习重点（仅 Ollama 启用时）。"""
    try:
        import requests

        outline_text = "\n".join(
            f"{c['book']}:\n" + "\n".join(f"  - {i}" for i in c["items"])
            for c in chapters
        )
        prompt = (
            "你是课程复习规划助手。以下是一本书的章节大纲，请为期末复习提炼："
            "1) 每章最可能考的重点；2) 整体复习顺序建议。用中文、分点回答。\n\n"
            f"课程：{course}\n大纲：\n{outline_text}"
        )
        r = requests.post(
            "http://127.0.0.1:11434/api/generate",
            json={"model": "qwen2.5:7b", "prompt": prompt, "stream": False},
            timeout=120,
        )
        r.raise_for_status()
        return r.json().get("response", "").strip()
    except Exception as e:
        return f"[AI 提炼暂不可用：{e}]"


# ---------- 进度看板 ----------

def build_dashboard() -> dict:
    """聚合全部进度信息，供期末冲刺看板展示。任何模块数据异常不影响整体。"""
    course_counts = get_course_count()
    try:
        all_questions = load_question_bank()
    except Exception:
        all_questions = []
    try:
        wrong = get_wrong_questions()
    except Exception:
        wrong = []

    # 各课程题库题数
    bank_counts: dict[str, int] = {}
    for q in all_questions:
        bank_counts[q["course"]] = bank_counts.get(q["course"], 0) + 1

    # 各课程错题数
    wrong_counts: dict[str, int] = {}
    for w in wrong:
        wrong_counts[w["course"]] = wrong_counts.get(w["course"], 0) + 1

    # Word 教材 / 批注
    docx_count = len(list(TEXTBOOKS_DOCX_DIR.glob("*.docx")))
    annotation_count = len(list_annotations())

    return {
        "course_chunks": course_counts,     # 各课程教材块数
        "question_bank": bank_counts,       # 各课程题数
        "wrong_book": wrong_counts,         # 各课程错题数
        "textbook_docx": docx_count,        # Word 版教材数
        "annotations": annotation_count,    # 批注归档数
        "ai_available": _is_ai_available(),
    }
