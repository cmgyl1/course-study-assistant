"""practice_service —— 刷题 + 错题本复盘的会话工厂。

UI 不再直接调 practice / qb，而是 Page → practice_service.start_xxx → engine。
PracticeSession 内部状态由 engine PracticeSession 管理，service 只是工厂。
"""
from __future__ import annotations

from engine import practice, question_bank as qb
from .dto import Result, WrongQuestionItem
from engine.practice import PracticeSession


# =================== 刷题会话 ====================

def start_course_session(course: str, by_type: dict[str, int] | None = None) -> Result[PracticeSession]:
    """按课程 + 题型配额创建刷题会话。"""
    if not course:
        return Result.fail("课程未选择")
    try:
        session = practice.make_course_session(course, by_type)
    except Exception as e:
        return Result.fail(str(e), "❌ 刷题会话创建失败")
    total = session.result.total if hasattr(session, "result") else 0
    return Result.ok(session, f"✅ 已创建刷题会话（{total} 道题）")


# =================== 错题本 ====================

def list_wrong_questions() -> Result[list[WrongQuestionItem]]:
    """加载全部错题列表。"""
    try:
        raw = qb.get_wrong_questions()
    except Exception as e:
        return Result.fail(str(e), "❌ 错题加载失败")
    items = [
        WrongQuestionItem(
            course=w.get("course", ""),
            type=w.get("type", ""),
            no=w.get("no", 0),
            wrong_count=w.get("wrong_count", 0),
            key=w.get("key", ""),
        )
        for w in raw
    ]
    if not items:
        return Result.ok(items, "（暂无错题，刷题答错后自动加入）")
    return Result.ok(items, f"✅ 已加载 {len(items)} 道错题")


def start_wrong_review_session(course: str = "") -> Result[PracticeSession]:
    """创建错题重刷会话。"""
    try:
        session = practice.make_wrong_review_session(course)
    except Exception as e:
        return Result.fail(str(e), "❌ 错题重刷会话创建失败")
    total = session.result.total if hasattr(session, "result") else 0
    if total == 0:
        return Result.ok(session, "暂无错题可重刷。")
    return Result.ok(session, f"✅ 已创建错题重刷会话（{total} 道题）")


__all__ = [
    "start_course_session",
    "list_wrong_questions",
    "start_wrong_review_session",
]
