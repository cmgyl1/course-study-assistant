"""知识库 + 题库冒烟测试：验证入库、检索、题库解析、错题本流程。"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from engine.config import ensure_data_dirs, QUESTION_BANKS_DIR
from engine import knowledge_base as kb
from engine import question_bank as qb

# 用**独立课程名**跑测试：向量库与错题本都是"按课程"过滤的共享存储，
# 若直接借用"计算机网络"，就会和真实教材语料/使用者的错题混在同一桶里 ——
# 实测：1 块测试文本根本排不过几百块真实教材，top1 落到"第3章高速以太网"，
# 断言"应含物理层"必然误报；错题本"应去重为 1"也会被已有错题顶成 2。
_TEST_COURSE = "测试课程（自动化）"


def _cleanup_wrong(course: str) -> None:
    """清掉该课程的历史错题残留，保证测试从干净状态开始。"""
    for it in qb.get_wrong_questions(course):
        qb.mark_wrong_question(it["key"], correct=True)


def main() -> int:
    ensure_data_dirs()
    ok = True
    _cleanup_wrong(_TEST_COURSE)

    # 1) 教材入库与检索
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        md = tmp / "计算机网络.md"
        # 每章正文必须超过 _split_markdown_by_headings 里 200 字符的"小块合并"阈值，
        # 否则两章会被并成 1 块（path 取第一章），"top1 应含物理层"就永远不可能成立
        # —— 这是本测试原先一直失败的真实原因之一。
        md.write_text(
            "# 第一章 概述\n\n"
            "计算机网络是指将地理位置不同的、具有独立功能的多台计算机及其外部设备，"
            "通过通信线路连接起来，在网络操作系统、网络管理软件及网络通信协议的管理和协调下，"
            "实现资源共享和信息传递的计算机系统。互联网是覆盖全球的计算机网络，"
            "它由边缘部分和核心部分组成：边缘部分是所有连接在互联网上的主机，又称端系统；"
            "核心部分是由大量网络和连接这些网络的路由器组成，它为边缘部分提供连通性和交换服务。"
            "计算机网络按覆盖范围可分为广域网、城域网、局域网和个人区域网，"
            "按拓扑结构可分为总线型、星形、环形和网状形。\n\n"
            "# 第二章 物理层\n\n"
            "物理层是计算机网络体系结构中的最底层，它的任务是透明地传送比特流。"
            "物理层要考虑怎样才能在连接各种计算机的传输媒体上传输数据比特流，"
            "而不是指具体的传输媒体。物理层的主要特点是把比特流送到传输媒体上，"
            "并定义了机械特性、电气特性、功能特性和过程特性这四个方面的接口标准。"
            "常用的传输媒体分为导引型传输媒体和非导引型传输媒体，"
            "前者包括双绞线、同轴电缆和光缆，后者即自由空间中的电磁波。"
            "物理层典型的互联设备是中继器和集线器，它们工作在比特流这一层。\n\n",
            encoding="utf-8",
        )
        n = kb.ingest_textbook(md, _TEST_COURSE, "计算机网络（测试）")
        print(f"[OK] 教材入库 {n} 块")
        results = kb.search_textbook("物理层 比特流", _TEST_COURSE, top_k=2)
        if not results:
            print("[FAIL] 教材检索无结果")
            ok = False
        else:
            # 只断言"有结果"等于没测 —— 检索错了章节照样算通过。
            # 这里断言命中章节确实包含查询主题，检索质量退化了会立刻暴露。
            top = results[0].get("section_path", "")
            if "物理层" in top:
                print(f"[OK] 检索到 {len(results)} 条，top1={top!r}")
            else:
                print(f"[FAIL] 检索命中章节错误：top1={top!r}（应含「物理层」）")
                ok = False
        kb.delete_textbook("计算机网络.md", _TEST_COURSE)  # 清理测试向量块

    # 2) 题库模板生成
    created = qb.ensure_question_bank_templates()
    print(f"[OK] 题库模板: {[p.name for p in created] or '已存在'}")

    # 3) 题库解析 + 入库 + 检索
    sample = QUESTION_BANKS_DIR / "计算机网络-题库.md"
    if not sample.exists():
        sample.write_text(
            "# 计算机网络 题库\n\n## 一、选择题\n\n### 1. TCP 协议位于哪一层？\n"
            "- A. 应用层\n- B. 传输层\n- C. 网络层\n- D. 数据链路层\n**答案**：B\n**解析**：TCP 是传输层协议。\n\n"
            "## 二、填空题\n\n### 1. 传输层的两个主要协议是 TCP 和 ____。\n**答案**：UDP\n**解析**：TCP/UDP 为传输层协议。\n\n",
            encoding="utf-8",
        )
    questions = qb.load_question_bank("计算机网络")
    print(f"[OK] 题库解析 {len(questions)} 题: {[(q['type'], q['no']) for q in questions]}")
    if len(questions) >= 2:
        print(f"     选择题答案={questions[0]['answer']}, 填空题答案={questions[1]['answer']}")
    else:
        ok = False
    indexed = qb.index_question_bank("计算机网络")
    print(f"[OK] 题库入库 {indexed} 题")
    q_results = qb.search_question("TCP 协议", "计算机网络", top_k=2)
    print(f"[OK] 题库检索 {len(q_results)} 条")

    # 4) 错题本流程：答错入本 → 选错保留 → 选对移除
    # 全部落在 _TEST_COURSE 上，不碰使用者的真实错题本。
    qb.add_wrong_question(_TEST_COURSE, "选择题", 1)
    qb.add_wrong_question(_TEST_COURSE, "选择题", 1)  # 去重
    wrong = qb.get_wrong_questions(_TEST_COURSE)
    print(f"[OK] 错题本 {len(wrong)} 条（应去重为 1）")
    if len(wrong) != 1:
        ok = False
    qb.mark_wrong_question(f"{_TEST_COURSE}:选择题:1", correct=False)  # 选错→保留
    wrong2 = qb.get_wrong_questions(_TEST_COURSE)
    print(f"[OK] 选错后保留 {len(wrong2)} 条, wrong_count={wrong2[0]['wrong_count']}")
    if len(wrong2) != 1 or wrong2[0]["wrong_count"] != 2:   # 入本计 1 + 选错再加 1
        ok = False
    qb.mark_wrong_question(f"{_TEST_COURSE}:选择题:1", correct=True)  # 选对→移除
    wrong3 = qb.get_wrong_questions(_TEST_COURSE)
    print(f"[OK] 选对后剩余 {len(wrong3)} 条（应为 0）")
    if wrong3:
        ok = False

    print("\n=== 结果:", "全部通过" if ok else "存在失败项", "===")
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
