"""刷题会话：做题流程 / 判分 / 对错反馈错题本（对/错循环机制）。

设计：
- PracticeSession 管理一次刷题会话：题目队列、进度、判分、结果统计；
- 选择题：比对选项字母自动判分；
- 填空题/大题：需要学生自查（界面上"对/错"按钮，由学生确认）——
  与错题本循环机制一致：答对（或自查为对）→ 移出错题本；答错 → 留在错题本并累计。
- 支持"错题重刷"：从错题本拉题目组会（期末冲刺复用）。
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from .question_bank import (
    load_question_bank,
    load_wrong_book,
    add_wrong_question,
    mark_wrong_question,
    sample_questions,
)

CORRECT_OPTION_PREFIXES = ("A", "B", "C", "D")


@dataclass
class SessionResult:
    """一次会话的统计结果。"""

    total: int = 0
    answered: int = 0
    correct: int = 0
    wrong: int = 0
    wrong_keys: list[str] = field(default_factory=list)

    @property
    def accuracy(self) -> float:
        return round(self.correct / self.answered, 3) if self.answered else 0.0


class PracticeSession:
    """刷题会话：持有一组题目，按序作答，记录结果并反馈错题本。"""

    def __init__(self, questions: list[dict], title: str = "刷题") -> None:
        self.questions = questions
        self.title = title
        self.idx = 0
        self.result = SessionResult(total=len(questions))
        self._history: list[dict] = []

    # ---- 会话状态 ----

    @property
    def done(self) -> bool:
        return self.idx >= len(self.questions)

    @property
    def current(self) -> dict | None:
        if self.done:
            return None
        return self.questions[self.idx]

    @property
    def progress(self) -> tuple[int, int]:
        return self.idx, len(self.questions)

    # ---- 作答 ----

    def submit(self, user_answer: str) -> dict:
        """提交当前题的作答，返回判分结果。

        user_answer：选择题传选项字母（如 "A"）；填空/大题传文本或 "SKIP"。
        返回 {correct: bool, expected: str, auto_checked: bool}
        """
        q = self.current
        if q is None:
            return {"correct": False, "expected": "", "auto_checked": False}

        auto = q["type"] == "选择题" and bool(q.get("options"))
        expected = q.get("answer", "").strip().upper()
        if auto:
            correct = user_answer.strip().upper() == expected
        else:
            # 填空/大题：学生自查（输入 对/错 标记）
            correct = user_answer.strip().upper() in ("对", "T", "TRUE", "1")
        # 仅选择题无参考答案时判错；自查场景尊重学生自评（答案缺失不代表答错）
        if auto and not expected:
            correct = False

        self._record(q, correct, auto)
        return {"correct": correct, "expected": expected, "auto_checked": auto}

    def _record(self, q: dict, correct: bool, auto: bool) -> None:
        key = f"{q['course']}:{q['type']}:{q['no']}"
        self.result.answered += 1
        if correct:
            self.result.correct += 1
            # 答对 → 若在错题本中则移除（循环机制）
            mark_wrong_question(key, correct=True)
        else:
            self.result.wrong += 1
            self.result.wrong_keys.append(key)
            add_wrong_question(q["course"], q["type"], q["no"])
        self._history.append({"key": key, "correct": correct, "auto": auto, "question": q})
        self.idx += 1

    def skip(self) -> None:
        """跳过当前题（不判分，但计入进度）。"""
        if self.current is not None:
            self.idx += 1

    def finish(self) -> SessionResult:
        """结束会话，返回统计。"""
        self.idx = len(self.questions)
        return self.result


# ---- 会话工厂 ----

def make_course_session(course: str, by_type: dict[str, int] | None = None) -> PracticeSession:
    """按课程 + 题型数量组卷（随机抽题）。"""
    questions = sample_questions(course, by_type)
    return PracticeSession(questions, title=f"{course} 刷题")


def make_chapter_session(course: str, section_keyword: str) -> PracticeSession:
    """按章节刷题：取题库中题干包含指定章节关键词的题。"""
    questions = [q for q in load_question_bank(course) if section_keyword in q["stem"]]
    if not questions:
        questions = load_question_bank(course)  # 无匹配则全量兜底
    return PracticeSession(questions, title=f"{course} · {section_keyword}")


def make_wrong_review_session(course: str = "") -> PracticeSession:
    """错题重刷：从错题本拉未掌握题目（期末冲刺复用）。"""
    from .question_bank import get_wrong_questions

    wrong = get_wrong_questions(course)
    questions: list[dict] = []
    for item in wrong:
        # 从题库取回完整题目
        for q in load_question_bank(item["course"]):
            if q["type"] == item["type"] and q["no"] == item["no"]:
                questions.append(q)
                break
    random.shuffle(questions)
    return PracticeSession(questions, title="错题重刷")
