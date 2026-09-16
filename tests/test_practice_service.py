"""practice_service 单测。"""
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import services.practice_service as ps
from services.dto import Result, WrongQuestionItem


def test_start_course_session_success():
    fake_session = MagicMock()
    fake_session.result.total = 10
    with patch.object(ps, "practice") as mock_p:
        mock_p.make_course_session.return_value = fake_session
        r = ps.start_course_session("计算机网络", {"选择题": 10})
    assert r.success is True
    assert r.data is fake_session
    assert "10" in r.message


def test_start_course_session_no_course():
    r = ps.start_course_session("")
    assert r.success is False


def test_start_course_session_failure():
    with patch.object(ps, "practice") as mock_p:
        mock_p.make_course_session.side_effect = KeyError("no questions")
        r = ps.start_course_session("计算机网络")
    assert r.success is False
    assert "no questions" in r.error


def test_list_wrong_questions_success():
    raw = [
        {"course": "计算机网络", "type": "填空题", "no": 1, "wrong_count": 3, "key": "x"},
        {"course": "UML", "type": "大题", "no": 2, "wrong_count": 1, "key": "y"},
    ]
    with patch.object(ps, "qb") as mock_qb:
        mock_qb.get_wrong_questions.return_value = raw
        r = ps.list_wrong_questions()
    assert r.success is True
    assert len(r.data) == 2
    assert isinstance(r.data[0], WrongQuestionItem)
    assert r.data[0].course == "计算机网络"
    assert "2" in r.message


def test_list_wrong_questions_empty():
    with patch.object(ps, "qb") as mock_qb:
        mock_qb.get_wrong_questions.return_value = []
        r = ps.list_wrong_questions()
    assert r.success is True
    assert r.data == []
    assert "暂无错题" in r.message


def test_start_wrong_review_session_with_items():
    fake_session = MagicMock()
    fake_session.result.total = 5
    with patch.object(ps, "practice") as mock_p:
        mock_p.make_wrong_review_session.return_value = fake_session
        r = ps.start_wrong_review_session()
    assert r.success is True
    assert "5" in r.message


def test_start_wrong_review_session_empty():
    fake_session = MagicMock()
    fake_session.result.total = 0
    with patch.object(ps, "practice") as mock_p:
        mock_p.make_wrong_review_session.return_value = fake_session
        r = ps.start_wrong_review_session()
    assert r.success is True
    assert "暂无错题" in r.message


def test_start_wrong_review_session_failure():
    with patch.object(ps, "practice") as mock_p:
        mock_p.make_wrong_review_session.side_effect = IOError("file")
        r = ps.start_wrong_review_session()
    assert r.success is False
    assert "file" in r.error


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
