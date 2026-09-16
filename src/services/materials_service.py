"""materials_service —— 教材导入 / 课件归档 / Word 版教材 / 题库模板的编排入口。

UI 不再直接调 converter / knowledge_base / question_bank / study，而是：
    MaterialsPage → materials_service.import_textbook(...) → engine 多个模块

业务规则集中在这里：
- 教材入库：先 markdown 化 → 再 ingest（按 source_file 清理旧块由 ingest_textbook 自己负责）
- 课件归档：只转 markdown，不入向量库
- Word 版教材：用 study.generate_all_docx_textbooks
- 题库模板：4 门课程文件名按 "{课程名}-题库.md" 模板生成

返回值统一是 Result[list[FileImportOutcome]]，UI 直接遍历文件级成功/失败展示。
"""
from __future__ import annotations

from pathlib import Path

from engine import converter, knowledge_base as kb, question_bank as qb, study
from engine.config import PROJECT_ROOT
from .dto import FileImportOutcome, Result
from .errors import FileImportError


def _textbook_md_dir() -> Path:
    """教材 markdown 输出目录。"""
    d = PROJECT_ROOT / "data" / "textbooks_md"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _materials_dir(course: str) -> Path:
    """课件归档目录（按课程分目录）。"""
    d = PROJECT_ROOT / "data" / "materials" / course
    d.mkdir(parents=True, exist_ok=True)
    return d


# =================== 教材入库（最常用业务） ====================

def import_textbook(file_paths: list[Path], course: str) -> Result[list[FileImportOutcome]]:
    """批量把 PDF / DOCX / PPT 转 markdown 并入向量库。

    每文件结果独立返回（成功 / 失败各 entry），UI 用列表展示。
    """
    if not file_paths:
        return Result.fail("未选择文件", "请先选择教材文件（PDF / DOCX / PPT / TXT / MD）")

    out_dir = _textbook_md_dir()
    outcomes: list[FileImportOutcome] = []
    for f in file_paths:
        f = Path(f)
        try:
            md_out = converter.convert_file(f, out_dir)
            chunks = kb.ingest_textbook(md_out, course, f.stem)
            outcomes.append(FileImportOutcome(
                file_name=f.name,
                success=True,
                message=f"已入库 {chunks} 块",
                output_path=str(md_out),
                chunks=chunks,
            ))
        except converter.ConversionError as e:
            outcomes.append(FileImportOutcome(
                file_name=f.name,
                success=False,
                message=f"转换失败：{e}",
            ))
        except Exception as e:  # KB 写入失败等也归到导入失败
            outcomes.append(FileImportOutcome(
                file_name=f.name,
                success=False,
                message=f"入库失败：{type(e).__name__}: {e}",
            ))

    n_ok = sum(1 for o in outcomes if o.success)
    n_fail = len(outcomes) - n_ok
    if n_fail == 0:
        return Result.ok(outcomes, f"✅ 入库完成：共 {n_ok} 个文件")
    if n_ok == 0:
        # 全部失败：success=False 但保留 outcomes，让 UI 列出"哪些文件失败"
        return Result.fail_with_data(
            outcomes, f"全部 {n_fail} 个文件失败",
            f"❌ 入库失败：{n_fail} 个文件",
        )
    # 部分成功：仍 success=True（毕竟有数据入库），但消息中标注
    return Result.ok(outcomes, f"⚠️ 部分完成：{n_ok} 成功 / {n_fail} 失败")


# =================== 课件归档 ====================

def import_courseware(file_paths: list[Path], course: str) -> Result[list[FileImportOutcome]]:
    """批量归档课件（只转 markdown，不入向量库）。"""
    if not file_paths:
        return Result.fail("未选择文件", "请先选择课件文件")

    out_dir = _materials_dir(course)
    outcomes: list[FileImportOutcome] = []
    for f in file_paths:
        f = Path(f)
        try:
            md_out = converter.convert_file(f, out_dir)
            outcomes.append(FileImportOutcome(
                file_name=f.name,
                success=True,
                message="已归档",
                output_path=str(md_out),
            ))
        except converter.ConversionError as e:
            outcomes.append(FileImportOutcome(
                file_name=f.name,
                success=False,
                message=f"归档失败：{e}",
            ))

    n_ok = sum(1 for o in outcomes if o.success)
    n_fail = len(outcomes) - n_ok
    if n_fail == 0:
        return Result.ok(outcomes, f"✅ 归档完成：共 {n_ok} 个文件")
    if n_ok == 0:
        return Result.fail(f"全部 {n_fail} 个文件失败", f"❌ 归档失败")
    return Result.ok(outcomes, f"⚠️ 部分完成：{n_ok} 成功 / {n_fail} 失败")


# =================== Word 版教材生成 ====================

def generate_all_docx() -> Result[list[str]]:
    """为所有已入库教材生成 Word 版（供学生批注）。"""
    try:
        outs = study.generate_all_docx_textbooks()
    except Exception as e:
        return Result.fail(str(e), "❌ 生成 Word 教材失败")
    names = [o.name for o in outs]
    if not names:
        return Result.ok(names, "（无教材可生成；请先在「教材导入」入库）")
    return Result.ok(names, f"✅ 已生成 {len(names)} 个 Word 教材")


# =================== 题库模板生成 ====================

def ensure_question_bank_templates() -> Result[list[str]]:
    """生成 4 门课程的题库模板（已存在则跳过）。"""
    try:
        created = qb.ensure_question_bank_templates()
    except Exception as e:
        return Result.fail(str(e), "❌ 生成题库模板失败")
    names = [p.name for p in created]
    if not names:
        return Result.ok(names, "（4 个题库模板都已存在，跳过）")
    return Result.ok(names, f"✅ 新建 {len(created)} 个题库模板")


__all__ = [
    "import_textbook",
    "import_courseware",
    "generate_all_docx",
    "ensure_question_bank_templates",
]
