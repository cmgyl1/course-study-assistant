"""study_service 单测。"""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import services.study_service as ss
from services.dto import ChapterContent, ExplainResultData, KnowledgeNode


def test_get_course_tree_success():
    raw_tree = [{"book": "计算机网络", "title": "第1章 概述", "children": [
        {"title": "1.1 定义", "concepts": ["网络", "协议"], "children": []},
    ]}]
    with patch.object(ss, "study") as mock_study:
        mock_study.get_course_tree.return_value = raw_tree
        r = ss.get_course_tree("计算机网络")

    assert r.success is True
    assert len(r.data) == 1
    root = r.data[0]
    assert isinstance(root, KnowledgeNode)
    assert root.title == "第1章 概述"
    assert root.book == "计算机网络"
    assert len(root.children) == 1


def test_get_course_tree_empty():
    with patch.object(ss, "study") as mock_study:
        mock_study.get_course_tree.return_value = []
        r = ss.get_course_tree("无课程")
    assert r.success is True
    assert r.data == []
    assert "暂无教材" in r.message


def test_get_course_tree_no_course():
    r = ss.get_course_tree("")
    assert r.success is False


def test_get_course_tree_exception():
    with patch.object(ss, "study") as mock_study:
        mock_study.get_course_tree.side_effect = OSError("disk")
        r = ss.get_course_tree("计算机网络")
    assert r.success is False
    assert "disk" in r.error


def test_get_section_content_success():
    raw = [
        {"section_path": "第1章>1.1", "doc_title": "计算机网络", "content": "..."},
        {"section_path": "第1章>1.2", "doc_title": "计算机网络", "content": "..."},
    ]
    with patch.object(ss, "kb") as mock_kb:
        mock_kb.get_section_content.return_value = raw
        r = ss.get_section_content("第1章", "计算机网络")

    assert r.success is True
    assert len(r.data) == 2
    assert all(isinstance(c, ChapterContent) for c in r.data)


def test_get_section_content_empty():
    with patch.object(ss, "kb") as mock_kb:
        mock_kb.get_section_content.return_value = []
        r = ss.get_section_content("任意", "计算机网络")
    assert r.success is True
    assert "暂无独立内容" in r.message


def test_explain_topic_with_ai():
    raw = {
        "evidence": [{"section_path": "x", "doc_title": "x", "content": "x"}],
        "answer": "AI 生成的讲解",
        "ai_available": True,
    }
    with patch.object(ss, "study") as mock_study:
        mock_study.explain_topic.return_value = raw
        r = ss.explain_topic("物理层", "计算机网络")

    assert r.success is True
    assert isinstance(r.data, ExplainResultData)
    assert r.data.ai_available is True
    assert r.data.answer == "AI 生成的讲解"
    assert "AI 讲解" in r.message


def test_explain_topic_without_ai():
    raw = {
        "evidence": [],
        "answer": "",
        "ai_available": False,
    }
    with patch.object(ss, "study") as mock_study:
        mock_study.explain_topic.return_value = raw
        r = ss.explain_topic("物理层", "计算机网络")
    assert r.success is True
    assert r.data.ai_available is False
    assert "本地 AI 未启用" in r.message


def test_explain_topic_empty_query():
    r = ss.explain_topic("   ", "计算机网络")
    assert r.success is False


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
