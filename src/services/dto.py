"""Service 层 DTO 定义：Result 泛型 + 业务数据结构。

被 services/__init__.py 统一导出。
UI 不应直接 import 本文件，请 from services import Result, DashboardData 等。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generic, TypeVar

T = TypeVar("T")


# =================== Result 泛型（所有 service 方法都返回它）===================

@dataclass(frozen=True)
class Result(Generic[T]):
    """统一返回外壳。

    - success=True 时 data 应有有效值，error/message 为空。
    - success=False 时 error 必有值，data 可以是 None 也可以保留部分结果。
    - message 是给用户看的中文一句话（成功/失败的简短描述）。
    """
    success: bool
    data: T | None = None
    error: str = ""
    message: str = ""

    @classmethod
    def ok(cls, data: T, message: str = "") -> "Result[T]":
        return cls(success=True, data=data, message=message)

    @classmethod
    def fail(cls, error: str, message: str = "") -> "Result[T]":
        """失败且无数据返回。简单失败用这个。"""
        return cls(success=False, error=error, message=message or error)

    @classmethod
    def fail_with_data(cls, data: T, error: str, message: str = "") -> "Result[T]":
        """失败但保留数据（用于批量场景：全部失败但仍展示每文件失败原因）。"""
        return cls(success=False, data=data, error=error, message=message or error)


# =================== 导入 / 转换相关 DTO ====================

@dataclass(frozen=True)
class FileImportOutcome:
    """单文件导入结果。失败也有 entry（用于 UI 列出"哪些文件失败"）。"""
    file_name: str
    success: bool
    message: str = ""
    output_path: str = ""
    chunks: int = 0


# =================== 知识树 / 章节正文 / 讲解 DTO ====================

@dataclass(frozen=True)
class KnowledgeNode:
    """知识树节点（递归结构）。"""
    title: str
    book: str = ""
    concepts: list[str] = field(default_factory=list)
    children: list["KnowledgeNode"] = field(default_factory=list)


@dataclass(frozen=True)
class ChapterContent:
    """教材里的一段原文片段（检索命中的"依据"）。

    page_no 是它在原书里的页码（OCR 合并阶段写入），UI 显示出来便于对照纸质书。
    """
    section_path: str
    doc_title: str
    content: str
    page_no: int | None = None
    score: float = 0.0


@dataclass(frozen=True)
class SectionBlock:
    """教材正文里的一个**保序**块：heading / para / figure。

    - kind="figure" 时 url 是绝对路径，UI 直接按 file:// 加载；
      图片在块序列中的位置就是它在原书里的位置（图题之上）。
    """
    kind: str                      # heading | para | figure
    text: str = ""
    url: str = ""
    level: int = 0
    page: int | None = None
    is_caption: bool = False


@dataclass(frozen=True)
class SectionReading:
    """某章节的阅读内容（保序块 + 出处信息）。"""
    section_path: str
    book: str = ""
    md_path: str = ""
    blocks: list[SectionBlock] = field(default_factory=list)
    n_figures: int = 0


@dataclass(frozen=True)
class ExplainResultData:
    """知识点讲解的合并结果（检索依据 + 可选 AI 答案 + 可用性）。

    status 取值：
      - "ok"         有命中
      - "not_found"  书里确实没有这个概念 —— UI 必须如实告知，
                     绝不能因为"总得返回点什么"而展示不相关段落
      - "empty_query" 提问里提取不出有效关键词
      - "no_corpus"  该课程还没导入教材
    """
    query: str
    evidence: list[ChapterContent] = field(default_factory=list)
    answer: str = ""
    ai_available: bool = False
    status: str = "ok"
    related_sections: list[str] = field(default_factory=list)
    missing_tokens: list[str] = field(default_factory=list)
    message: str = ""


# =================== Dashboard / 复习提纲 DTO ====================

@dataclass(frozen=True)
class DashboardData:
    """首页 + 期末冲刺页通用的学习进度数据。"""
    course_chunks: dict[str, int] = field(default_factory=dict)
    question_bank: dict[str, int] = field(default_factory=dict)
    wrong_book: dict[str, int] = field(default_factory=dict)
    textbook_docx: int = 0
    annotations: int = 0
    ai_available: bool = False


@dataclass(frozen=True)
class ReviewOutlineChapter:
    """复习提纲一章（某本书的要点列表）。"""
    book: str
    items: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ReviewOutlineData:
    """复习提纲总览。"""
    course: str
    chapters: list[ReviewOutlineChapter] = field(default_factory=list)
    ai_summary: str = ""
    ai_available: bool = False


# =================== 错题本 DTO ====================

@dataclass(frozen=True)
class WrongQuestionItem:
    """错题本里一条记录。"""
    course: str
    type: str
    no: int
    wrong_count: int
    key: str
