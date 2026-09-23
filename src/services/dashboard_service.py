"""dashboard_service —— 首页 KPI + 期末冲刺的学习进度数据入口。

UI 不再直接调 finals.build_dashboard，而是 Page → dashboard_service.xxx → engine。
"""
from __future__ import annotations

from engine import finals
from .dto import DashboardData, Result, ReviewOutlineChapter, ReviewOutlineData


def build_dashboard() -> Result[DashboardData]:
    """加载首页 KPI 看板数据。"""
    try:
        d = finals.build_dashboard()
    except Exception as e:
        return Result.fail(str(e), "❌ 进度看板加载失败")
    data = DashboardData(
        course_chunks=d.get("course_chunks", {}),
        question_bank=d.get("question_bank", {}),
        wrong_book=d.get("wrong_book", {}),
        textbook_docx=d.get("textbook_docx", 0),
        annotations=d.get("annotations", 0),
        ai_available=d.get("ai_available", False),
    )
    return Result.ok(data, "✅ 进度看板已刷新")


def generate_review_outline(course: str) -> Result[ReviewOutlineData]:
    """生成某课程的复习提纲（按教材 + 章节）。"""
    if not course:
        return Result.fail("课程未选择")
    try:
        o = finals.generate_review_outline(course)
    except Exception as e:
        return Result.fail(str(e), "❌ 复习提纲生成失败")
    data = ReviewOutlineData(
        course=o.get("course", course),
        chapters=[
            ReviewOutlineChapter(book=c.get("book", ""), items=c.get("items", []))
            for c in o.get("chapters", [])
        ],
        ai_summary=o.get("ai_summary", ""),
        ai_available=o.get("ai_available", False),
    )
    if not data.chapters:
        return Result.ok(data, f"该课程暂无教材")
    return Result.ok(data, f"✅ 已生成 {len(data.chapters)} 章复习提纲")


__all__ = [
    "build_dashboard",
    "generate_review_outline",
]
