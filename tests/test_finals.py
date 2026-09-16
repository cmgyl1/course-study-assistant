"""期末冲刺冒烟测试：复习提纲 / 进度看板 / 错题重刷联动。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from engine.config import ensure_data_dirs, TEXTBOOKS_MD_DIR
from engine import finals
from engine.knowledge_base import ingest_textbook
from engine.practice import make_wrong_review_session

def main() -> int:
    ensure_data_dirs()
    ok = True

    # 准备教材并入库（用于看板统计）
    md = TEXTBOOKS_MD_DIR / "算法设计与分析-测试教材.md"
    md.write_text(
        "# 第一章 算法基础\n\n算法复杂度分析是核心。\n\n## 1.1 渐近记号\n\nO、Ω、Θ 记号。\n\n"
        "# 第二章 分治法\n\n分而治之思想。\n\n",
        encoding="utf-8",
    )
    ingest_textbook(md, "算法设计与分析", "算法设计与分析（测试）")

    # 1) 复习提纲
    outline = finals.generate_review_outline("算法设计与分析")
    print(f"[OK] 复习提纲: {len(outline['chapters'])} 本教材, ai_available={outline['ai_available']}")
    if outline["chapters"]:
        ch = outline["chapters"][0]
        print(f"     章节项: {ch['items'][:2]}")
    else:
        ok = False

    # 2) 进度看板
    dash = finals.build_dashboard()
    print(f"[OK] 看板: 教材块={dash['course_chunks']}, 题库={dash['question_bank']}, "
          f"错题={dash['wrong_book']}, Word教材={dash['textbook_docx']}, 批注={dash['annotations']}")
    if "算法设计与分析" not in dash["course_chunks"]:
        ok = False

    # 3) 错题重刷会话可创建（与刷题模块联动）
    review = make_wrong_review_session()
    print(f"[OK] 错题重刷会话可创建: {review.result.total} 题")

    # 清理测试数据（保留目录）
    md.unlink(missing_ok=True)
    from engine.knowledge_base import delete_textbook
    delete_textbook("算法设计与分析-测试教材.md")  # 清理入库的测试向量块
    print("\n=== 结果:", "全部通过" if ok else "存在失败项", "===")
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
