"""materials_service 单测（unittest 风格，与项目其他测试一致）。

策略：mock engine 的 IO 函数（converter.convert_file 等），专注于 service 编排：
- 每文件 outcomes
- Result 成功/失败 + 中文消息
- 异常归一化
"""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import services.materials_service as ms
from engine import converter
from services.dto import FileImportOutcome


def test_import_textbook_empty():
    r = ms.import_textbook([], "计算机网络")
    assert r.success is False
    assert r.data is None
    assert "未选择" in r.error  # "未选择文件" 在 error 字段


def test_import_textbook_success():
    """3 个文件全部成功。"""
    fakes_in = [Path(f"教材{i}.pdf") for i in range(3)]
    fake_md = {f"教材{i}": Path(f"教材{i}.md") for i in range(3)}

    def fake_convert(f, out_dir):
        return fake_md[f.stem]

    def fake_ingest(md_path, course, doc_title):
        return 261

    with patch.object(converter, "convert_file", side_effect=fake_convert), \
         patch("services.materials_service.kb") as mock_kb:
        mock_kb.ingest_textbook.side_effect = fake_ingest
        r = ms.import_textbook(fakes_in, "计算机网络")

    assert r.success is True
    assert len(r.data) == 3
    for i, o in enumerate(r.data):
        assert isinstance(o, FileImportOutcome)
        assert o.success is True
        assert o.file_name == f"教材{i}.pdf"
        assert "261 块" in o.message
        assert o.chunks == 261
    assert "3" in r.message


def test_import_textbook_partial_failure():
    """2 个文件：第一个成功，第二个 converter 抛 ConversionError。"""
    fakes_in = [Path("好.pdf"), Path("坏.pdf")]

    def fake_convert(f, out_dir):
        if "好" in f.name:
            return Path("好.md")
        raise converter.ConversionError("PDF 损坏")

    with patch.object(converter, "convert_file", side_effect=fake_convert), \
         patch("services.materials_service.kb") as mock_kb:
        mock_kb.ingest_textbook.return_value = 10
        r = ms.import_textbook(fakes_in, "计算机网络")

    assert r.success is True  # 部分成功仍 success=true
    assert len(r.data) == 2
    assert r.data[0].success is True
    assert r.data[1].success is False
    assert "PDF 损坏" in r.data[1].message
    assert "部分完成" in r.message  # ⚠️ 部分完成：1 成功 / 1 失败


def test_import_textbook_all_failure():
    """全部失败：success=False。"""
    fakes_in = [Path("a.pdf"), Path("b.pdf")]

    def fake_convert(f, out_dir):
        raise converter.ConversionError("x")

    with patch.object(converter, "convert_file", side_effect=fake_convert), \
         patch("services.materials_service.kb") as mock_kb:
        r = ms.import_textbook(fakes_in, "计算机网络")

    assert r.success is False
    assert "全部" in r.error  # "全部 N 个文件失败"
    assert r.data is not None
    assert all(not o.success for o in r.data)


def test_import_courseware_success():
    fakes_in = [Path("课件1.pptx")]
    fake_md = Path("课件1.md")
    with patch.object(converter, "convert_file", return_value=fake_md):
        r = ms.import_courseware(fakes_in, "计算机网络")

    assert r.success is True
    assert len(r.data) == 1
    assert r.data[0].success is True
    assert "归档" in r.data[0].message


def test_import_courseware_empty():
    r = ms.import_courseware([], "计算机网络")
    assert r.success is False


def test_generate_all_docx_with_results():
    fake_outs = [Path("a.docx"), Path("b.docx")]
    with patch("services.materials_service.study") as mock_study:
        mock_study.generate_all_docx_textbooks.return_value = fake_outs
        r = ms.generate_all_docx()

    assert r.success is True
    assert r.data == ["a.docx", "b.docx"]
    assert "2" in r.message


def test_generate_all_docx_empty():
    with patch("services.materials_service.study") as mock_study:
        mock_study.generate_all_docx_textbooks.return_value = []
        r = ms.generate_all_docx()

    assert r.success is True
    assert r.data == []
    assert "无教材" in r.message


def test_generate_all_docx_failure():
    with patch("services.materials_service.study") as mock_study:
        mock_study.generate_all_docx_textbooks.side_effect = OSError("disk full")
        r = ms.generate_all_docx()

    assert r.success is False
    assert "disk full" in r.error


def test_ensure_question_bank_templates_created():
    fake_outs = [Path("计算机网络-题库.md"), Path("UML面向对象分析与设计-题库.md")]
    with patch("services.materials_service.qb") as mock_qb:
        mock_qb.ensure_question_bank_templates.return_value = fake_outs
        r = ms.ensure_question_bank_templates()

    assert r.success is True
    assert len(r.data) == 2
    assert "2" in r.message


def test_ensure_question_bank_templates_all_exist():
    with patch("services.materials_service.qb") as mock_qb:
        mock_qb.ensure_question_bank_templates.return_value = []
        r = ms.ensure_question_bank_templates()

    assert r.success is True
    assert r.data == []
    assert "已存在" in r.message


def main() -> int:
    """运行所有 test_ 开头的函数，报告失败个数。"""
    tests = [(name, fn) for name, fn in globals().items()
             if name.startswith("test_") and callable(fn)]
    failures = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ✓ {name}")
        except AssertionError as e:
            failures += 1
            print(f"  ✗ {name}: {e}")
        except Exception as e:
            failures += 1
            print(f"  ✗ {name}: {type(e).__name__}: {e}")
    total = len(tests)
    if failures:
        print(f"\n{failures}/{total} 个测试失败")
        return 1
    print(f"\n全部 {total} 个测试通过 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
