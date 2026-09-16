"""刷题与错题本冒烟测试：组卷、作答判分、对错反馈循环、错题重刷。

注意：make_course_session 是随机组卷，测试用 load_question_bank 的文档顺序
构造确定性会话，避免随机顺序导致断言错位；随机组卷单独验证数量。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from engine.config import ensure_data_dirs, QUESTION_BANKS_DIR
from engine import question_bank as qb
from engine.practice import (
    PracticeSession,
    make_course_session,
    make_chapter_session,
    make_wrong_review_session,
)

def _snapshot() -> dict:
    """把会被本测试改写的真实数据先快照下来。

    本测试用的是**真实课程"计算机网络"**：它会覆盖 data/question_banks/计算机网络-题库.md，
    并且第 7 步"错题重刷答对 → 移出错题本"会把**使用者自己积攒的错题一并删掉**
    （实测 data/wrong_book/wrong_book.json 里原有 计算机网络:选择题:2 一条历史错题）。
    数据不能因为跑一次测试就没了 —— 所以结尾必须原样还原。
    """
    from engine.config import WRONG_BOOK_DIR
    files = {
        WRONG_BOOK_DIR / "wrong_book.json": None,
        QUESTION_BANKS_DIR / "计算机网络-题库.md": None,
    }
    for p in files:
        files[p] = p.read_text(encoding="utf-8") if p.exists() else None
    return files


def _restore(files: dict) -> None:
    for p, text in files.items():
        if text is None:
            if p.exists():
                p.unlink()
        else:
            p.write_text(text, encoding="utf-8")


def main() -> int:
    snap = _snapshot()
    try:
        return _run()
    finally:
        _restore(snap)


def _run() -> int:
    ensure_data_dirs()
    ok = True

    # 准备题库（计算机网络：2 选择 + 1 填空）
    sample = QUESTION_BANKS_DIR / "计算机网络-题库.md"
    sample.write_text(
        "# 计算机网络 题库\n\n## 一、选择题\n\n"
        "### 1. TCP 协议位于哪一层？\n- A. 应用层\n- B. 传输层\n- C. 网络层\n- D. 数据链路层\n"
        "**答案**：B\n**解析**：TCP 是传输层协议。\n\n"
        "### 2. HTTP 协议默认端口是？\n- A. 21\n- B. 80\n- C. 443\n- D. 8080\n"
        "**答案**：B\n**解析**：HTTP 默认 80 端口。\n\n"
        "## 二、填空题\n\n### 1. 传输层的两个主要协议是 TCP 和 ____。\n**答案**：UDP\n**解析**：UDP。\n\n",
        encoding="utf-8",
    )

    # 1) 随机组卷（只验证数量）
    session = make_course_session("计算机网络", {"选择题": 2, "填空题": 1})
    print(f"[OK] 随机组卷 {session.result.total} 题")
    if session.result.total != 3:
        ok = False

    # 2) 确定性会话：按题库文档顺序 [选择1(TCP), 选择2(HTTP), 填空1]
    questions = qb.load_question_bank("计算机网络")
    ordered = [q for q in questions if q["type"] == "选择题"] + \
              [q for q in questions if q["type"] == "填空题"]
    session = PracticeSession(ordered)
    print(f"[OK] 确定性会话 {len(ordered)} 题, 顺序={[q['no'] for q in ordered]}")

    # 3) 选择1 答对 → 不入错题本
    r1 = session.submit("B")
    print(f"[OK] 选择1 答B: correct={r1['correct']}, auto={r1['auto_checked']}")
    if not r1["correct"] or not r1["auto_checked"]:
        ok = False

    # 4) 选择2 答错 → 入错题本
    r2 = session.submit("A")
    print(f"[OK] 选择2 答A: correct={r2['correct']}, auto={r2['auto_checked']}")
    if r2["correct"]:
        ok = False

    # 5) 填空自查为对
    r3 = session.submit("对")
    print(f"[OK] 填空1 自查对: correct={r3['correct']}, auto={r3['auto_checked']}")
    if not r3["correct"] or r3["auto_checked"]:
        ok = False

    result = session.finish()
    print(f"[OK] 会话统计: 答对 {result.correct}/{result.answered}, 准确率 {result.accuracy}")
    if result.correct != 2 or result.wrong != 1:
        ok = False

    # 6) 错题本：应只有 选择2
    wrong = qb.get_wrong_questions("计算机网络")
    print(f"[OK] 错题本 {len(wrong)} 条: {[w['key'] for w in wrong]}")
    if len(wrong) != 1 or "选择题:2" not in wrong[0]["key"]:
        ok = False

    # 7) 错题重刷：拉取错题 → 答对 → 移出错题本
    review = make_wrong_review_session("计算机网络")
    print(f"[OK] 错题重刷 {review.result.total} 题")
    if review.result.total != 1:
        ok = False
    review.submit("B")  # HTTP 默认端口 = 80 → B
    review.finish()
    wrong_after = qb.get_wrong_questions("计算机网络")
    print(f"[OK] 重做答对后错题本 {len(wrong_after)} 条（应清空）")
    if wrong_after:
        ok = False

    # 8) 选错则保留（循环机制）：重新答错一道题
    qb.add_wrong_question("计算机网络", "选择题", 1)
    qb.mark_wrong_question("计算机网络:选择题:1", correct=False)  # 选错 → 保留
    wrong2 = qb.get_wrong_questions("计算机网络")
    print(f"[OK] 选错保留: {len(wrong2)} 条, wrong_count={wrong2[0]['wrong_count']}")
    if len(wrong2) != 1 or wrong2[0]["wrong_count"] != 2:  # 入本计 1 + 选错再加 1 = 2
        ok = False
    qb.mark_wrong_question("计算机网络:选择题:1", correct=True)  # 清理
    print(f"[OK] 选对移除: {len(qb.get_wrong_questions('计算机网络'))} 条")

    # 9) 章节刷题（兜底）
    ch = make_chapter_session("计算机网络", "TCP")
    print(f"[OK] 章节刷题 {ch.result.total} 题")

    print("\n=== 结果:", "全部通过" if ok else "存在失败项", "===")
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
