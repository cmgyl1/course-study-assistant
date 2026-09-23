"""Service 层 DTO（Data Transfer Object）—— service ↔ UI ↔ engine 之间的数据契约。

设计原则：
- 全部用 `@dataclass(frozen=True)` 或 frozen，明确"数据不可变"。
- `Result[T]` 泛型统一返回结构：success / data / error / message 四件套。
- 业务 DTO 不含 UI 概念（不要塞 QWidget），只描述业务实体。
- engine 已有的有状态对象（PracticeSession）原样透传，不强求 dataclass 化。

本文件只是包文档 + 统一导出入口，具体定义见 .dto 模块。
"""
from __future__ import annotations

from .dto import (
    Result,
    FileImportOutcome,
    KnowledgeNode,
    ChapterContent,
    SectionHit,
    SectionBlock,
    SectionReading,
    ExplainResultData,
    DashboardData,
    ReviewOutlineChapter,
    ReviewOutlineData,
    WrongQuestionItem,
)

__all__ = [
    "Result",
    "FileImportOutcome",
    "KnowledgeNode",
    "ChapterContent",
    "SectionHit",
    "SectionBlock",
    "SectionReading",
    "ExplainResultData",
    "DashboardData",
    "ReviewOutlineChapter",
    "ReviewOutlineData",
    "WrongQuestionItem",
]
