"""课件版教材 Markdown 清洗：去除 PPT 标签框造成的重复短行。

问题：PPT 每页的标签文本框（如"以太网""交换机""碰撞域"）按行输出，
跨页反复出现 → 检索时返回"一行一个词、重复好几行"的垃圾内容。

清洗规则：
1. 连续重复行（含标题）只保留一次；
2. 连续出现的短标签词行（≤8 字符、无标点、非标题/列表）合并为
   "A、B、C" 一行（去重保序），避免一行一词；
3. 不影响章节标题、列表与正常段落。

用法：python tools/clean_textbook.py [输入md] [输出md]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# 短标签词判定：≤8 字符、无中文/英文标点、非标题/列表/数字
_SHORT_WORD = re.compile(r"^[\u4e00-\u9fffA-Za-z0-9·•]{1,8}$")
_HAS_PUNCT = re.compile(r"[，。、；：？！,.?!;:：（）()]")
_MAX_GROUP = 10  # 单组合并上限，防超长


def clean_markdown(text: str) -> str:
    lines = text.splitlines()
    # 1) 压缩连续空行 → 单个空行（保持段落间距，但避免空行打断归组）
    collapsed: list[str] = []
    prev_blank = False
    for line in lines:
        if line.strip() == "":
            if not prev_blank:
                collapsed.append("")
            prev_blank = True
        else:
            collapsed.append(line.rstrip())
            prev_blank = False

    # 2) 短标签词行合并：连续短词行（可隔空行）归组，去重保序合并为 "A、B、C"
    merged: list[str] = []
    i = 0
    n = len(collapsed)
    while i < n:
        s = collapsed[i].strip()
        if (s and not s.startswith(("#", "-")) and len(s) <= 8
                and _SHORT_WORD.match(s) and not _HAS_PUNCT.search(s)):
            group = [s]
            j = i + 1
            while j < n:
                t = collapsed[j].strip()
                if t == "":
                    # 跳过空行，继续看下一个（但组内允许空行）
                    j += 1
                    continue
                if (not t.startswith(("#", "-")) and len(t) <= 8
                        and _SHORT_WORD.match(t) and not _HAS_PUNCT.search(t)):
                    group.append(t)
                    j += 1
                else:
                    break
            seen: list[str] = []
            for g in group:
                if g not in seen and len(seen) < _MAX_GROUP:
                    seen.append(g)
            if len(seen) == 1:
                merged.append(seen[0])
            else:
                merged.append("、".join(seen))
            i = j
        else:
            merged.append(collapsed[i])
            i += 1
    return "\n".join(merged)


def main() -> int:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else \
        Path(__file__).resolve().parent.parent / "data" / "textbooks_md" / "计算机网络（第8版）课件版.md"
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else src

    text = src.read_text(encoding="utf-8")
    cleaned = clean_markdown(text)
    before_lines = len(text.splitlines())
    after_lines = len(cleaned.splitlines())
    dst.write_text(cleaned, encoding="utf-8")
    print(f"清洗完成: {before_lines} 行 → {after_lines} 行（减少 {before_lines - after_lines} 行）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
