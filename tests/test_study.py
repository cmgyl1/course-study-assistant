"""自学模块冒烟测试：知识树 / 讲解（检索原文）/ Word 教材生成与归档。

隔离说明（重要）：检索语料是"扫描 `data/textbooks_md/` + 按课程名 glob 文件名"
得到的，所以测试教材只要文件名里带真实课程名，就会**污染该课程的真实检索结果**
（库里有 2 册谢希仁教材时尤其隐蔽）。

因此本测试用**独立课程名**「冒烟测试课」：`list_books("计算机网络")` 的 pattern 是
`*计算机网络*.md`，不会命中测试教材。所有落盘产物在 `finally` 里清理。

检索断言则反过来必须用**真实课程** —— 拒答判据在几十块的极小语料上必然误判（见步骤 3 注释）。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from engine.config import ensure_data_dirs, TEXTBOOKS_MD_DIR, TEXTBOOKS_DOCX_DIR
from engine import study, textbook_reader as reader

TEST_COURSE = "冒烟测试课"
STEM = f"{TEST_COURSE}-测试教材"


def main() -> int:
    ensure_data_dirs()
    ok = True

    md = TEXTBOOKS_MD_DIR / f"{STEM}.md"
    # 段落必须写够长度：`retrieval.build_chunks` 的 min_chars=60 会把过短的段落
    # 并入前一块，若前一块正好是标题块则**直接丢弃** —— 用十几个字的假段落
    # 会导致语料里只剩标题块、检索必然 not_found（本测试踩过）。
    md.write_text(
        "# 第一章 概述\n\n"
        "计算机网络是一个将分散的、具有独立功能的计算机系统，通过通信设备与线路连接起来，"
        "由功能完善的软件实现资源共享和信息传递的系统。计算机网络最本质的功能是资源共享。\n\n"
        "## 1.1 网络的组成\n\n"
        "网络由若干节点和连接这些节点的链路组成。节点可以是计算机、集线器、交换机或路由器，"
        "链路则指连接节点的物理线路。多个网络还可以通过路由器互连，构成覆盖范围更大的网络。\n\n"
        "# 第二章 物理层\n\n"
        "物理层的主要任务是确定与传输媒体的接口有关的一些特性，包括机械特性、电气特性、"
        "功能特性和过程特性。物理层传输的是比特流，也就是一个一个的二进制比特。\n\n",
        encoding="utf-8",
    )
    docx_path = TEXTBOOKS_DOCX_DIR / f"{STEM}.docx"
    archived: Path | None = None

    try:
        # 1) 知识树
        tree = study.build_knowledge_tree(md)
        print(f"[OK] 知识树顶层 {len(tree)} 章")
        for ch in tree:
            print(f"     {ch['title']} -> {len(ch['children'])} 节")
        if len(tree) != 2:
            ok = False

        # 2) 课程知识树（读真实课程，只读操作）
        course_trees = study.get_course_tree("计算机网络")
        print(f"[OK] 课程知识树: {len(course_trees)} 本教材")

        # 3) 讲解（检索语料按需从 Markdown 构建，无需预先"入库"）
        #    ⚠ 这里必须用**真实课程**：拒答判据二规定"查询含 ≥2 个实词、且每个命中词
        #    在全库出现 ≤2 次 → 视为顺带提及，拒答"。该判据在几十块的极小语料上必然
        #    误判 —— 同一个词就算在正文里重复出现，DF 也就 2。所以拿自建的测试教材做
        #    检索断言会稳定 not_found（实测踩过）。检索链路本身由 test_retrieval.py
        #    对着真实教材验证。
        if not reader.list_books("计算机网络"):
            print("[SKIP] 讲解：本机无《计算机网络》教材（需先跑 OCR 流水线）")
        else:
            result = study.explain_topic("三次握手", "计算机网络", top_k=2)
            print(f"[OK] 讲解: status={result['status']}, ai_available={result['ai_available']}, "
                  f"evidence={len(result['evidence'])} 条")
            if result["evidence"]:
                print(f"     依据: {result['evidence'][0]['section_path']!r}")
            else:
                ok = False

        # 4) Word 教材生成
        docx = study.generate_docx_textbook(md)
        docx_path = docx
        print(f"[OK] Word 教材: {docx.name} ({docx.stat().st_size} 字节)")
        if not docx.exists():
            ok = False

        # 5) 批注归档
        archived = study.archive_annotation(docx, TEST_COURSE)
        print(f"[OK] 批注归档: {archived.name}")
        anns = study.list_annotations(TEST_COURSE)
        print(f"[OK] 归档列表: {len(anns)} 个")
    finally:
        # 清理全部落盘产物（即使中途抛异常也不残留）
        md.unlink(missing_ok=True)
        docx_path.unlink(missing_ok=True)
        if archived is not None:
            archived.unlink(missing_ok=True)
            parent = archived.parent
            if parent.name == TEST_COURSE and parent.exists() and not any(parent.iterdir()):
                parent.rmdir()

    print("\n=== 结果:", "全部通过" if ok else "存在失败项", "===")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
