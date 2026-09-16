"""dashboard_service 单测。"""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import services.dashboard_service as ds
from services.dto import DashboardData, ReviewOutlineData


def test_build_dashboard_success():
    raw = {
        "course_chunks": {"计算机网络": 261},
        "question_bank": {"计算机网络": 12},
        "wrong_book": {},
        "textbook_docx": 0,
        "annotations": 0,
        "ai_available": False,
    }
    with patch.object(ds, "finals") as mock_f:
        mock_f.build_dashboard.return_value = raw
        r = ds.build_dashboard()
    assert r.success is True
    assert isinstance(r.data, DashboardData)
    assert r.data.course_chunks == {"计算机网络": 261}
    assert "刷新" in r.message


def test_build_dashboard_failure():
    with patch.object(ds, "finals") as mock_f:
        mock_f.build_dashboard.side_effect = ValueError("oops")
        r = ds.build_dashboard()
    assert r.success is False
    assert "oops" in r.error


def test_generate_review_outline_success():
    raw = {
        "course": "计算机网络",
        "chapters": [
            {"book": "计算机网络（第8版）", "items": ["第1章 概述", "第2章 物理层"]},
        ],
        "ai_summary": "重点是物理层",
        "ai_available": True,
    }
    with patch.object(ds, "finals") as mock_f:
        mock_f.generate_review_outline.return_value = raw
        r = ds.generate_review_outline("计算机网络")
    assert r.success is True
    assert isinstance(r.data, ReviewOutlineData)
    assert len(r.data.chapters) == 1
    assert r.data.ai_available is True


def test_generate_review_outline_no_course():
    r = ds.generate_review_outline("")
    assert r.success is False


def test_generate_review_outline_no_textbook():
    raw = {"course": "空课程", "chapters": [], "ai_summary": "", "ai_available": False}
    with patch.object(ds, "finals") as mock_f:
        mock_f.generate_review_outline.return_value = raw
        r = ds.generate_review_outline("空课程")
    assert r.success is True
    assert r.data.chapters == []
    assert "暂无已入库教材" in r.message


def main() -> int:
    tests = [(name, fn) for name, fn in globals().items()
             if name.startswith("test_") and callable(fn)]
    failures = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ✓ {name}")
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
