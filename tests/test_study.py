"""自学模块冒烟测试：知识树 / 讲解（检索原文）/ Word 教材生成与归档。"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from engine.config import ensure_data_dirs, TEXTBOOKS_MD_DIR, TEXTBOOKS_DOCX_DIR, ANNOTATIONS_DIR
from engine import study

def main() -> int:
    ensure_data_dirs()
    ok = True

    # 准备测试教材
    md = TEXTBOOKS_MD_DIR / "计算机网络-测试教材.md"
    md.write_text(
        "# 第一章 概述\n\n计算机网络是互联的计算机集合。\n\n"
        "## 1.1 网络的组成\n\n网络由节点和链路组成。\n\n"
        "# 第二章 物理层\n\n物理层传输比特流。\n\n",
        encoding="utf-8",
    )

    # 1) 知识树
    tree = study.build_knowledge_tree(md)
    print(f"[OK] 知识树顶层 {len(tree)} 章")
    for ch in tree:
        print(f"     {ch['title']} -> {len(ch['children'])} 节")
    if len(tree) != 2:
        ok = False

    # 2) 课程知识树
    course_trees = study.get_course_tree("计算机网络")
    print(f"[OK] 课程知识树: {len(course_trees)} 本教材")

    # 3) 讲解（先入库再检索）
    from engine.knowledge_base import ingest_textbook
    ingest_textbook(md, "计算机网络", "计算机网络（测试）")
    result = study.explain_topic("物理层 比特流", "计算机网络", top_k=2)
    print(f"[OK] 讲解: ai_available={result['ai_available']}, evidence={len(result['evidence'])} 条")
    if result["evidence"]:
        print(f"     依据: {result['evidence'][0]['section_path']!r}")
    else:
        ok = False

    # 4) Word 教材生成
    docx = study.generate_docx_textbook(md)
    print(f"[OK] Word 教材: {docx.name} ({docx.stat().st_size} 字节)")
    if not docx.exists():
        ok = False

    # 5) 批注归档
    archived = study.archive_annotation(docx, "计算机网络")
    print(f"[OK] 批注归档: {archived.relative_to(ANNOTATIONS_DIR)}")
    anns = study.list_annotations("计算机网络")
    print(f"[OK] 归档列表: {len(anns)} 个")

    # 清理测试教材（保留目录结构）
    md.unlink(missing_ok=True)
    (TEXTBOOKS_DOCX_DIR / "计算机网络-测试教材.docx").unlink(missing_ok=True)
    archived.unlink(missing_ok=True)
    from engine.knowledge_base import delete_textbook
    delete_textbook("计算机网络-测试教材.md")  # 清理入库的测试向量块，避免污染真实知识库
    print("\n=== 结果:", "全部通过" if ok else "存在失败项", "===")
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
