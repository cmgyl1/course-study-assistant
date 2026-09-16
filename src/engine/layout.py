"""OCR 版面还原：把检测框还原成阅读顺序的段落、标题与页码。

解决的问题（实测依据见 build/boxes.json，样本页 p25 / p55）：

1. 边栏文字（"扫一扫" / "视频讲解"）被按检测框顺序插进正文段落中间，
   导致一句话读起来断裂 —— 它们其实是教材侧边的二维码提示，不是正文；
2. 同一行的文字被 OCR 切成多个框（p55 "(2）双向交替通信" + "言又称为…"，
   两框 y 重叠、x 相邻），按框顺序输出会把一句话拆成两行；
3. OCR 逐行输出没有空行，段落边界全丢，无法区分"新段落"与"上一段的续行"；
4. 页脚页码（p25 "14" / p55 "·44·"）被当成正文行入库。

判据全部来自实测坐标，不依赖任何具体文字内容（换一本教材依然成立）：

- 边栏：框宽 < 12% 页宽 且 左边界 > 75% 页宽
        （实测"扫一扫" w=53、x0=1174；"视频讲解" w=74、x0=1165；
          而那两页的正文行 x0 均在 126–195、宽度 > 700）；
- 页脚：框中心 y > 92% 页高 且 文本 ≤ 12 字
        （实测页码 y0=1941/2062 = 94%，其余脚注最高只到 91%）；
- 同行：两框 y 中心差 < 较小框高的 55%
        （实测同行两框 y 范围 942–978 与 937–973，高度均约 35）；
- 段落：行左边界比本页最左正文行再缩进 > 40px
        （实测首行缩进 55–65px，而顶格行的 x0 抖动 ≤ 15px）。

本模块只做几何计算，零下载、零外部依赖。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_SIDEBAR_MAX_W_RATIO = 0.12
_SIDEBAR_MIN_X_RATIO = 0.75
_FOOTER_MIN_Y_RATIO = 0.92
_FOOTER_MAX_CHARS = 12

_INDENT_PX = 40.0          # 段落首行缩进阈值
_HEADING_MAX_CHARS = 60    # 超长行不视为标题
_LINE_GAP_PX = 20.0        # 同行拼接时插入空格的间距阈值
_LINE_Y_TOLERANCE = 0.55   # 同行判定：y 中心差 < 较小框高 × 该系数

# 图内文字判据（三条需同时满足，缺一不可）：
# 实测样本为 p25 的图 1-9 标注 —— "报文"(w=45) / "发送在前"(w=79) / "首部"(w=51)
# / "001101011100101"(w=143)，它们的共同点是小框、短文本、且明显偏离左边距；
# 而 "图1-9以分组为基本单位在网络中传送"(w=440) 是图题需保留，
# "CYCLADES。"(w=119，x0 紧贴左边距) 是正文续行也需保留。
_FIGURE_MAX_CHARS = 16
_FIGURE_ASCII_MAX_CHARS = 40   # 纯 ASCII 串（如示意用的二进制串）放宽长度
_FIGURE_MAX_W_RATIO = 0.18
_FIGURE_MIN_X_RATIO = 0.07

# ---- 图区定位（实验3，第2章 25 张图命中 24 张）----
# 目标：不是"识别图的内容"，而是"按坐标从 PDF 裁出图"——零识别误差、零幻觉。
# 教材惯例：图题排在图的下方。所以只要准确定位图题，再向上找图的上边界即可。
#
# 判据全部来自实测坐标（build/diag*.log），不依赖具体文字：
#
#   1. 图题：短（≤40 字）、无中文句读、不够宽（< 55% 页宽）、**居中**。
#      缺"居中"或"无句读"会把正文里的"图2-9画出了光波在纤芯中传输的示意图"当成图题，
#      实测 p62 会从 3 张图变成 5 张（假图）。
#   2. 图的上边界 = 向上最近一条**触到右页边**的行（x1 > 85% 页宽）的下沿，
#      再向下吃掉该段正文的收尾行（起点仍在左边距）。
#      ⚠ 不能用"够宽"当通栏判据：实测 p54 图2-1 的**图内部**就有横跨大半页的标注行
#        （"输入输入发送的信号接收的信号输出" w=852），满足"够宽"却被误当作正文行，
#        图区上边界压到图内部 → 只剩 66px → 整张图丢失。正文行是从左边距起到右页边止的，
#        而图内标注碰不到右页边，用"触右页边"才分得开。
_FIG_CAPTION_RE = re.compile(r"^图\s*\d+\s*[-–—]\s*\d+")
_FIG_CAPTION_MAX_CHARS = 40
_FIG_CAPTION_BAN = "。！？，；："
_FIG_WIDE_RATIO = 0.55          # 图题判据：宽度不得超过页宽的 55%
_FIG_CENTER_TOL_RATIO = 0.06    # 图题判据：中心偏离页心在此比例内 → 视为居中（加分项）
_FIG_NARROW_RATIO = 0.36        # 图题判据：不居中时的替代约束（要够窄）
_FIG_INDENT_TOL_RATIO = 0.05    # 正文行起点相对版心左边距的容差
_FIG_RIGHT_REACH_RATIO = 0.85   # 行终点超过此比例 → 触到右页边（正文）
_FIG_MIN_H = 70                 # 图区最小高度（像素），低于此视为误判

# ⚠ "正文行"= 触右页边 **且** 起点贴版心左边距，两条缺一不可：
#   - 只用"触右页边"：实测 p24 图1-7 的**图内小图题**"（a）两部电话直接相连(b）…"
#     x1=1250、页宽 1456、阈值 1237.6 —— 只越线 12px 就被当成正文，图区上边界
#     被推到图内部，只剩 51px → 整张图丢失。
#   - 只用"贴左边距"：实测 p63 正文尾行"意图。"x0=135 贴边距，但它属于正文。
#   起点容差取 5% 页宽（≈72px）：正文首行缩进实测 61–68px 在容差内，
#   而图内文字的缩进实测 ≥85px（p24 为 114px、p159 的 PING 输出为 85px）在容差外。

_CHAPTER_RE = re.compile(r"^第\s*[0-9一二三四五六七八九十百]+\s*[章节篇]")
# 标题号后**不得**紧跟数字/点号/空白：教材节标题写作"2.3导引型传输媒体"，数字与标题连写；
# 而扫描件里的表格行（如 SONET 速率表 "51.840 OC-1/STS-1"、CIDR 表 "128.96.39.0/25接口m0"）
# 会在数字后跟空格或继续跟点号，实测这两类被误判成 ## 标题，往导航树里塞了 12 个垃圾条目。
_NUM3_RE = re.compile(r"^\d+\.\d+\.\d+(?![\d.\s])")
_NUM2_RE = re.compile(r"^\d+\.\d+(?![\d.\s])")
_LISTNUM_RE = re.compile(r"^\d{1,2}\s*[.、]\s*[\u4e00-\u9fff]")
_PAGENO_RE = re.compile(r"^[·•.\-—\s]*(\d{1,4})[·•.\-—\s]*$")


@dataclass
class _Box:
    """一个 OCR 检测框（外接矩形 + 文本）。"""

    x0: float
    x1: float
    y0: float
    y1: float
    text: str
    score: float = 1.0

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2

    @property
    def h(self) -> float:
        return self.y1 - self.y0

    @property
    def w(self) -> float:
        return self.x1 - self.x0


def _as_boxes(items) -> list[_Box]:
    """把 RapidOCR 的原始结果（[四点框, 文本, 置信度]）转为 _Box 列表。"""
    boxes: list[_Box] = []
    for it in items or []:
        try:
            box, text = it[0], it[1]
            score = float(it[2]) if len(it) > 2 else 1.0
        except (TypeError, IndexError):
            continue
        text = str(text).strip()
        if not text or not box:
            continue
        xs = [float(p[0]) for p in box]
        ys = [float(p[1]) for p in box]
        boxes.append(_Box(min(xs), max(xs), min(ys), max(ys), text, score))
    return boxes


def split_chrome(boxes: list[_Box], page_w: float, page_h: float):
    """剔除边栏与页脚，并尝试从页脚提取印刷页码。

    Returns:
        (正文框列表, 被剔除文本列表, 印刷页码或 None)
    """
    body: list[_Box] = []
    dropped: list[str] = []
    footers: list[_Box] = []

    for b in boxes:
        # 顺序很重要：必须先判页脚。教材奇数页的页码排在右侧，
        # 若先执行边栏判据（窄框 + 靠右），页码会被误当成边栏剔除。
        if b.cy > page_h * _FOOTER_MIN_Y_RATIO and len(b.text) <= _FOOTER_MAX_CHARS:
            footers.append(b)
            continue
        if b.w < page_w * _SIDEBAR_MAX_W_RATIO and b.x0 > page_w * _SIDEBAR_MIN_X_RATIO:
            dropped.append(b.text)          # 侧边栏
            continue
        body.append(b)

    page_no = None
    for b in footers:
        m = _PAGENO_RE.match(b.text)
        if m:
            value = int(m.group(1))
            if 0 < value < 2000 and page_no is None:
                page_no = value
        else:
            dropped.append(b.text)          # 不是页码的页脚（如残句）一并剔除
    return body, dropped, page_no


def group_lines(boxes: list[_Box]) -> list[list[_Box]]:
    """按 y 中心聚类成行，行内按 x 排序，行间按 y 排序。"""
    lines: list[list[_Box]] = []
    for b in sorted(boxes, key=lambda r: r.cy):
        for line in lines:
            ref = line[0]
            h = min(b.h, ref.h)
            if h > 0 and abs(b.cy - ref.cy) < h * _LINE_Y_TOLERANCE:
                line.append(b)
                break
        else:
            lines.append([b])
    for line in lines:
        line.sort(key=lambda r: r.x0)
    lines.sort(key=lambda line: min(r.y0 for r in line))
    return lines


def _need_space(left: str, right: str) -> bool:
    """同行拼接时是否需要补空格（仅英文/数字之间）。"""
    if not left or not right:
        return False
    a, b = left[-1], right[0]
    return a.isascii() and b.isascii() and a.isalnum() and b.isalnum()


def join_line(items: list[_Box]) -> str:
    """把同一行的多个框按 x 顺序拼接为一行文本。"""
    text = items[0].text
    prev_x1 = items[0].x1
    for b in items[1:]:
        if b.x0 - prev_x1 > _LINE_GAP_PX and _need_space(text, b.text):
            text += " " + b.text
        else:
            text += b.text
        prev_x1 = b.x1
    return text


def heading_level(text: str) -> int | None:
    """识别标题行并给出层级（1=章 / 2=节 / 3=小节 / 4=正文内编号）。"""
    s = text.strip()
    if not s or len(s) > _HEADING_MAX_CHARS:
        return None
    # 含中文句读的绝不是标题：实测 "802.3ah，较新的版本是802.3ah-2008。EPON在…"
    # 会被 "^\d+\.\d+" 误判成节标题（顿号 "、" 是标题合法字符，不列入）。
    if any(ch in s for ch in "。，；：！？"):
        return None
    if _CHAPTER_RE.match(s):
        return 1
    if _NUM3_RE.match(s):
        return 3
    if _NUM2_RE.match(s):
        return 2
    if len(s) <= 30 and _LISTNUM_RE.match(s):
        return 4
    return None


def split_figure_lines(lines: list[list[_Box]], page_w: float, keep=None):
    """把"图内标注文字"从正文行中分离出来。

    图内文字（示意图里的"报文""首部""数据"、设备名、二进制串等）会污染正文段落，
    但它们的三条特征同时成立，可与正文区分：
      1. 该行所有框都是小框（宽 < 18% 页宽）；
      2. 该行所有框都明显偏离左边距（左边界 - 左边距 > 7% 页宽）；
      3. 拼接后文本很短（≤ 16 字）。

    Args:
        keep: 必须保留的行文本集合（已定位到的**图题**）。
            ⚠ 这个参数不能省：短图题（如"图1-15划分层次举例"9 字、居中、窄框）
            同时满足上面三条，会被当成图内文字**从正文里删掉** —— 实测
            p41 / p92 就这样丢掉了图题行，而且图也会因为找不到图题位置被挤到页尾。

    Returns:
        (正文行, 图内文字列表)
    """
    if not lines:
        return lines, []
    keep = keep or set()
    left = min(min(r.x0 for r in line) for line in lines)
    max_w = page_w * _FIGURE_MAX_W_RATIO
    min_off = page_w * _FIGURE_MIN_X_RATIO

    body: list[list[_Box]] = []
    figures: list[str] = []
    for line in lines:
        text = join_line(line)
        if text in keep:                       # 图题永远属于正文
            body.append(line)
            continue
        narrow = all(r.w < max_w for r in line)
        offset = all((r.x0 - left) > min_off for r in line)
        if not (narrow and offset):
            body.append(line)
            continue
        if len(text) <= _FIGURE_MAX_CHARS:
            figures.append(text)
        elif len(text) <= _FIGURE_ASCII_MAX_CHARS and not re.search(r"[\u4e00-\u9fff]", text):
            # 纯 ASCII 短串（如示意用的二进制序列 "001101011100101"）同属图内标注
            figures.append(text)
        else:
            body.append(line)
    return body, figures


def _line_rows(lines: list[list[_Box]]) -> list[dict]:
    """把"行"列表压成几何行记录，供图区定位使用。"""
    rows: list[dict] = []
    for ln in lines:
        x0 = min(r.x0 for r in ln)
        x1 = max(r.x1 for r in ln)
        rows.append({
            "y0": min(r.y0 for r in ln),
            "y1": max(r.y1 for r in ln),
            "x0": x0,
            "x1": x1,
            "w": x1 - x0,
            "text": join_line(ln),
        })
    return rows


def is_figure_caption(row: dict, page_w: float) -> bool:
    """判断某一几何行是否真的是图题（"图2-1数据通信系统的模型"）。

    三条硬条件：匹配 `图X-Y`、短（≤40 字）、无中文句读。
    再要求"够窄"（< 55% 页宽），最后看**居中与否**：

      - 居中（中心偏离页心 ≤ 6% 页宽）→ 直接通过；
      - 不居中 → 降级为**加分项**，改要求"更窄"（< 36% 页宽）。

    为什么"居中"不能当必要条件：实测 p181 图4-47 的图题 x 范围 353–859、
    中心 606，而页心 725 —— 偏差 119 > 容差 87，被一票否决。这张图**本身就是
    偏左排版的**，"居中"根本不是它的属性。而补上的"< 36% 页宽"条件足以拦住
    正文里以"图X-Y"开头的句子（实测那些句子宽度都在 700px 以上，远超 36%×1450=522）。
    """
    text = row["text"]
    if not _FIG_CAPTION_RE.match(text):
        return False
    if len(text) > _FIG_CAPTION_MAX_CHARS:
        return False
    if any(ch in text for ch in _FIG_CAPTION_BAN):
        return False
    if row["w"] >= page_w * _FIG_WIDE_RATIO:
        return False
    center = (row["x0"] + row["x1"]) / 2
    if abs(center - page_w / 2) <= page_w * _FIG_CENTER_TOL_RATIO:
        return True
    return row["w"] < page_w * _FIG_NARROW_RATIO


def figure_regions(body_boxes: list[_Box], lines: list[list[_Box]],
                   page_w: float) -> list[dict]:
    """定位每张图的矩形区域。

    Args:
        body_boxes: 剔除边栏/页脚后的正文框（用于求内容左右边界）
        lines:      group_lines 的结果（**未**分离图内文字，图区内文字是重要线索）
        page_w:     页面宽度（像素）

    Returns:
        [{"y0","y1","x0","x1","caption"}, ...]，坐标为像素，
        x0/x1 为整页内容的左右边界（裁图时按此左右裁齐）。
    """
    if not lines:
        return []
    rows = _line_rows(lines)
    if body_boxes:
        content_x0 = min(b.x0 for b in body_boxes)
        content_x1 = max(b.x1 for b in body_boxes)
    else:
        content_x0 = min(r["x0"] for r in rows)
        content_x1 = max(r["x1"] for r in rows)

    # 版心左边距：正文行的起点基准。只取"实质行"（宽 ≥ 半版心）的最左边界，
    # 这样首行缩进行、图内标注都不会把它算小 —— 见 _left_margin 的说明。
    margin = _left_margin([(r["x0"], r["x1"], r["text"]) for r in rows], content_x1)
    left_tol = margin + page_w * _FIG_INDENT_TOL_RATIO
    right_reach = page_w * _FIG_RIGHT_REACH_RATIO

    def is_body_row(r: dict) -> bool:
        """正文行 = 触右页边 且 起点贴版心左边距。"""
        return r["x1"] > right_reach and r["x0"] < left_tol

    out: list[dict] = []
    prev_bottom: float | None = None
    for i, row in enumerate(rows):
        if not is_figure_caption(row, page_w):
            continue
        # 向上找最近一条真正的正文行
        k = None
        for j in range(i - 1, -1, -1):
            if is_body_row(rows[j]):
                k = j
                break
        if k is None:
            top = rows[0]["y0"]
        else:
            # 从 k 向下吃掉该段正文的收尾行（这些行起点仍在版心左边距内）。
            # ⚠ 判据必须是"贴版心左边距"而不能是"x0 < 22% 页宽"：实测 p159
            #   图4-30 / p160 图4-31 是 PING、tracert 控制台截图，图内文字起点
            #   x0≈216–276，恰好落在 0.22×页宽（≈319）以内 —— 收尾行循环于是
            #   一路穿过整张截图，把上边界推到图题正上方，图区只剩 57px / 61px，
            #   两张图双双被 _FIG_MIN_H 判为误判丢弃。
            m = k
            for j in range(k + 1, i):
                if rows[j]["x0"] < left_tol:
                    m = j
                else:
                    break
            top = rows[m]["y1"]
        # 同一页相邻的两张图不得互相吞并
        if prev_bottom is not None:
            top = max(top, prev_bottom)
        # 图区下边界取**图题的上沿**，而不是图题的下沿。
        # 教材图题排在图的下方，如果连图题一起裁进去，正文里又保留图题行，
        # 阅读器就会出现"图题文字 + 含图题的图片"重复一次 —— 裁到图题上方，
        # 图题归属正文，图片插在图题之前，排出来就是原书的样子（图在上、图题在下）。
        bottom = row["y0"]
        prev_bottom = bottom
        if bottom - top < _FIG_MIN_H:
            continue
        out.append({
            "y0": top, "y1": bottom,
            "x0": content_x0, "x1": content_x1,
            "caption": row["text"],
        })
    return out


def _insert_before_caption(markdown: str, caption: str, url: str) -> str:
    """把图片引用插到**图题段落之前**（"原文内嵌图"的关键一步）。

    教材图题在图的下方，所以"图题段落 + 图"的正确顺序是 **图在前、图题在后** ——
    把引用插在图题段落前面即可得到这个顺序，读起来与原书一致。

    三级降级：
      1. 图题**独立成段** → 直接插在该段之前；
      2. 图题被并进别的段落 → 段内按图题位置切开，拼成「前文 / 图 / 图题 / 后文」。
         这一步不能省：图区会被从行流里切走，于是**图上方那行正文和图下方那行图题
         在段落里变成相邻**，两者粘成一段——实测 p74 图3-5 就是这么粘的，
         只做精确匹配会让图退化到页尾；
      3. 图题压根没找到 → 追加到页尾（保图不丢，也不破坏段落结构）。
    """
    ref = f"![{caption}]({url})"
    cap = caption.strip()

    blocks = markdown.split("\n\n")
    for i, blk in enumerate(blocks):
        if blk.strip() == cap:
            blocks.insert(i, ref)
            return "\n\n".join(blocks)

    if cap:
        for i, blk in enumerate(blocks):
            if cap not in blk:
                continue
            head, _, tail = blk.partition(cap)
            parts = [p for p in (head.strip(), ref, cap, tail.strip()) if p]
            blocks[i:i + 1] = parts
            return "\n\n".join(blocks)

    return markdown + "\n\n" + ref + "\n\n"


def _strip_figure_lines_by_region(lines: list[list[_Box]], regions: list[dict],
                                  page_w: float):
    """用已定位的图区，把"落在图区内部且仍是窄框行"的行判为图内标注。

    为什么需要这一步：`split_figure_lines` 的判据是"偏离左边距 > 7% 页宽"，
    实测 p54 图2-1 的标注行 x0=254、左边距 153 → 偏移 101px，阈值 102px，
    **差 1 像素**就被当成正文混进了段落。有了图区矩形后，位置信息可以一票判定。

    但仍要求"窄框行"：v3 图区上边界向上多含 1–2 行正文（这是已知的轻微过取），
    若不加窄框约束，那些正文行会被误删——正文丢失比图内文字混入严重得多。

    Returns:
        (保留的正文行, 追加识别出的图内标注文字)
    """
    if not regions or not lines:
        return lines, []
    captions = {r["caption"] for r in regions}
    max_w = page_w * _FIGURE_MAX_W_RATIO

    body: list[list[_Box]] = []
    extra: list[str] = []
    for line in lines:
        text = join_line(line)
        if text in captions:                 # 图题本身必须留在正文里
            body.append(line)
            continue
        cy = sum(r.cy for r in line) / len(line)
        inside = any(r["y0"] - 4 <= cy <= r["y1"] for r in regions)
        narrow = all(r.w < max_w for r in line)
        if inside and narrow:
            extra.append(text)
        else:
            body.append(line)
    return body, extra


# ---- 表格还原（B 档：列对齐检测 + 复用已有 OCR 文字，零新依赖）----
# 实测依据（build/probe_boxes.log，p61 的 表2-2 续表）：
#   表头"绞合线类别 / 带宽 / 线缆特点 / 典型应用"是**四个独立检测框**，
#   每一行数据同样是四个独立框。也就是说 —— 扫描件即使把表格线丢掉，
#   单元格也会天然被 OCR 切成独立框，同一列的框在行间反复落在同一个 x 区间。
#   所以不需要表格结构识别模型（RapidTable / PP-Structure / MinerU …），只要：
#     ① 找出"多框行"连成的块 → ② 按 x 区间聚类出列 → ③ 按列回填文字 → ④ 输出管道表格。
#   收益双重：规则表格变回真表格，而误判成 `## 标题` 的表格行也随之一并消失。
_TABLE_MIN_ROWS = 3            # 至少 3 行（表头 + 2 数据行）才成表
_TABLE_MIN_COLS = 2
_TABLE_MIN_BOXES = 2           # 单行至少这么多框才可能是表格行
_TABLE_COL_TOL_RATIO = 0.024   # 同列框起点容差（≈35px @1450 宽）
_TABLE_ROW_GAP_RATIO = 1.5     # 行间距超过 行高×该系数 即视为表格中断


def _cluster_columns(boxes: list[_Box], page_w: float) -> list[dict]:
    """把一块表格里的所有框按 x 区间聚成列。

    贪心两步：先按起点相近归并，再让区间重叠的列合并 —— 后者是必需的，
    因为**表头居中、数据左对齐**，同一列的起点能差 100px 以上
    （实测表头"线缆特点" x0=601，而该列数据 x0=446，靠区间重叠才归到同一列）。
    """
    tol = page_w * _TABLE_COL_TOL_RATIO
    cols: list[dict] = []
    for b in sorted(boxes, key=lambda r: r.x0):
        for c in cols:
            if b.x0 - c["x0"] <= tol or b.x0 <= c["x1"]:
                c["x0"] = min(c["x0"], b.x0)
                c["x1"] = max(c["x1"], b.x1)
                break
        else:
            cols.append({"x0": b.x0, "x1": b.x1})
    cols.sort(key=lambda c: c["x0"])
    return cols


def _col_of(box: _Box, cols: list[dict]) -> int:
    """一个框属于哪一列（取 x 区间重叠最多者，无重叠返回 -1）。"""
    best, best_ov = -1, 0.0
    for i, c in enumerate(cols):
        ov = min(box.x1, c["x1"]) - max(box.x0, c["x0"])
        if ov > best_ov:
            best_ov, best = ov, i
    return best


def detect_tables(lines: list[list[_Box]], regions: list[dict],
                  page_w: float) -> list[dict]:
    """识别表格块，返回 [{"i0","i1","rows"}]（rows 为二维文本，首行为表头）。

    ⚠ 必须**先**剔除落在图区内的行：PING / tracert 的控制台输出同样是
    一列列对齐的多框行（实测 p160 每行 5 框、列起点 292/355/469/584/674 高度重复），
    不排除就会被误认成表格。图区判据已经在 figure_regions 里算好了，直接复用。
    """
    if not lines:
        return []
    rows = _line_rows(lines)

    def in_region(i: int) -> bool:
        cy = (rows[i]["y0"] + rows[i]["y1"]) / 2
        return any(r["y0"] - 4 <= cy <= r["y1"] for r in regions)

    cand = [i for i in range(len(lines))
            if len(lines[i]) >= _TABLE_MIN_BOXES and not in_region(i)]
    if not cand:
        return []

    blocks: list[list[int]] = []
    cur = [cand[0]]
    for i in cand[1:]:
        h = rows[cur[-1]]["y1"] - rows[cur[-1]]["y0"]
        gap = rows[i]["y0"] - rows[cur[-1]]["y1"]
        if i == cur[-1] + 1 and gap < max(h * _TABLE_ROW_GAP_RATIO, 30.0):
            cur.append(i)
        else:
            blocks.append(cur)
            cur = [i]
    blocks.append(cur)

    out: list[dict] = []
    for blk in blocks:
        if len(blk) < _TABLE_MIN_ROWS:
            continue
        cols = _cluster_columns([b for i in blk for b in lines[i]], page_w)
        if len(cols) < _TABLE_MIN_COLS:
            continue
        col_rows = [set() for _ in cols]
        table_rows: list[list[str]] = []
        ok = True
        for k, i in enumerate(blk):
            cells = [""] * len(cols)
            for b in lines[i]:
                c = _col_of(b, cols)
                if c < 0:
                    continue
                cells[c] = (cells[c] + b.text) if cells[c] else b.text
                col_rows[c].add(k)
            if sum(1 for c in cells if c) < _TABLE_MIN_COLS:
                ok = False                       # 该行填不满两列 → 不是表格行
                break
            table_rows.append(cells)
        # 每一列都要在 ≥2 个不同行里出现，否则只是偶然的区间重叠而非真列
        if not ok or sum(1 for s in col_rows if len(s) >= 2) < _TABLE_MIN_COLS:
            continue
        out.append({"i0": blk[0], "i1": blk[-1], "rows": table_rows})
    return out


def table_to_markdown(rows2d: list[list[str]]) -> str:
    """二维单元格 → Markdown 管道表格。"""
    n = max(len(r) for r in rows2d)

    def fmt(cells: list[str]) -> str:
        padded = list(cells) + [""] * (n - len(cells))
        return "| " + " | ".join(c.strip().replace("|", "\\|") for c in padded) + " |"

    head, *body = rows2d
    md = [fmt(head), "| " + " | ".join(["---"] * n) + " |"]
    md += [fmt(r) for r in body]
    return "\n".join(md)


def _left_margin(metrics: list[tuple[float, float, str]], right: float) -> float:
    """求版心左边距。

    只取**实质行**（宽度 ≥ 半个版心宽）的最左边界，这样能同时避开两类干扰：
      - 图内标注、居中短行等窄行混进来把边距拉小；
      - 反过来若用"众数"，实测 p54 这种带大量缩进条目的页会把缩进值当成版心，
        于是所有正文行都"不缩进"，整页被并成一段（实测 p55 也会整页并成一段）。
    """
    lefts = [m[0] for m in metrics if m[1] - m[0] >= right * 0.5]
    if not lefts:
        lefts = [m[0] for m in metrics]
    return min(lefts)


def assemble_paragraphs(lines, page_w: float | None = None) -> list[tuple[str, int]]:
    """行 → 段落。返回 [(文本, 标题层级)]，层级 0 表示正文段落，-1 表示预渲染块。

    元素除了"行"（`list[_Box]`）也可以是 `(marker, markdown)` 元组 —— 表示
    已经渲染好的整块内容（目前用于**表格**），原样输出、不与相邻段落合并。

    新起一段需**同时**满足：
      1. 行起点比版心左边距再缩进 > 40px —— 中文排版只在首行缩进，
         贴左边距的行永远是上一段的续行；
      2. 该行比上一行再缩进 > 40px，**或**上一行没排满（说明上一段已结束）。

    三条实测教训，缺任何一条都会出问题：
      - 只比"版心左边距"（1）：实测 p54 有一块条目区，整块所有行 x0 都在 272、
        而版心是 153，于是每行都"缩进 119px"被切成独立段落，一句话被拆成
        "…计" + "算机…"。加上"比上一行"（2）后整块正确合回一段。
      - 只看"上一行没排满"：实测 p63 的 2.3.2 节连续三行都止于 x1097（比版心窄），
        会被逐行切断。加上"比版心再缩进"（1）后这三行正确合回。
      - 漏掉"上一行没排满"：图题行（居中、短）会被并进后面的正文段落。
    """
    if not lines:
        return []
    body = [ln for ln in lines if not isinstance(ln, tuple)]
    metrics = [(min(r.x0 for r in line), max(r.x1 for r in line), join_line(line))
               for line in body]
    if metrics:
        right = max(m[1] for m in metrics)
        base = _left_margin(metrics, right)
    else:
        right, base = 0.0, 0.0
    full_tol = (page_w * 0.06) if page_w else max(30.0, right * 0.06)

    paras: list[tuple[str, int]] = []
    prev_x0: float | None = None
    prev_x1: float | None = None
    mi = 0
    for ln in lines:
        if isinstance(ln, tuple):            # 预渲染块（表格）：原样输出，断开段落链
            paras.append((ln[1], -1))
            prev_x0 = prev_x1 = None
            continue
        x0, x1, text = metrics[mi]
        mi += 1
        level = heading_level(text)
        if level:
            paras.append((text, level))
        elif not paras or paras[-1][1]:
            paras.append((text, 0))                       # 页首 / 紧跟标题 → 新段
        else:
            indent_vs_base = (x0 - base) > _INDENT_PX
            indent_vs_prev = prev_x0 is not None and (x0 - prev_x0) > _INDENT_PX
            prev_short = prev_x1 is not None and prev_x1 <= right - full_tol
            if indent_vs_base and (indent_vs_prev or prev_short):
                paras.append((text, 0))
            else:
                prev_text, _ = paras[-1]
                paras[-1] = (prev_text + text, 0)         # 上一段的续行
        prev_x0, prev_x1 = x0, x1
    return paras


def to_markdown(paras: list[tuple[str, int]]) -> str:
    """段落列表 → Markdown 文本（层级 -1 的预渲染块原样输出）。"""
    blocks = []
    for text, level in paras:
        if level == -1:
            blocks.append(text)
        else:
            blocks.append(f"{'#' * level} {text}" if level else text)
    return "\n\n".join(blocks)


def restore_page(items, page_w: float, page_h: float, on_figure=None) -> dict:
    """把一页的 OCR 检测框还原为阅读顺序的 Markdown。

    Args:
        items: RapidOCR 原始结果 [[四点框, 文本, 置信度], ...]
        page_w / page_h: 该页渲染位图的宽高（像素）
        on_figure: 可选回调 `f(region) -> str | None`。
            对每个定位到的图区调用一次；返回图片 URL（如 `../figures/x/p1_fig1.png`）
            时，该图会**内嵌到图题所在位置**（"原文内嵌图"）。
            本模块不做任何文件 I/O，裁图由调用方完成。

    Returns:
        dict(markdown, page_no, dropped, figure_text, figures, n_boxes, n_paras, n_tables)
        - markdown    : 还原后的 Markdown（含内嵌图片引用；不含图内标注文字）
        - page_no     : 从页脚识别出的印刷页码（识别不到为 None）
        - dropped     : 被剔除的边栏 / 非页码页脚文本
        - figure_text : 从正文流中分离出的图内标注文字
        - figures     : 定位到的图区 [{y0,y1,x0,x1,caption,url}, ...]
        - n_tables    : 本页还原出的表格数量
    """
    boxes = _as_boxes(items)
    if not boxes:
        return {"markdown": "", "page_no": None, "dropped": [],
                "figure_text": [], "figures": [], "n_boxes": 0, "n_paras": 0,
                "n_tables": 0}

    body, dropped, page_no = split_chrome(boxes, page_w, page_h)
    all_lines = group_lines(body)
    regions = figure_regions(body, all_lines, page_w)
    # 图题必须保留在正文里，否则短图题会被当成图内文字删掉（见 split_figure_lines）
    lines, figure_text = split_figure_lines(all_lines, page_w,
                                            keep={r["caption"] for r in regions})
    lines, extra_text = _strip_figure_lines_by_region(lines, regions, page_w)
    figure_text += extra_text

    # 表格还原：识别"多框对齐块" → 预渲染成管道表格，替换掉原来的线性文本行。
    # 必须在图区剔除**之后**做 —— PING / tracert 的控制台输出同样是列对齐的多框行，
    # 不先排除就会把截图误认成表格（实测 p160）。
    tables = detect_tables(lines, regions, page_w)
    if tables:
        drop_idx: set[int] = set()
        inject: dict[int, tuple] = {}
        for t in tables:
            drop_idx.update(range(t["i0"], t["i1"] + 1))
            inject[t["i0"]] = ("table", table_to_markdown(t["rows"]))
        merged: list = []
        for i, ln in enumerate(lines):
            if i in inject:
                merged.append(inject[i])
            if i not in drop_idx:
                merged.append(ln)
        lines = merged

    paras = assemble_paragraphs(lines, page_w)
    markdown = to_markdown(paras)

    figures: list[dict] = []
    for reg in regions:
        url = None
        if on_figure is not None:
            try:
                url = on_figure(reg)
            except Exception:                       # noqa: BLE001 —— 裁图失败不该中断该页
                url = None
        fig = dict(reg)
        fig["url"] = url
        figures.append(fig)
        if url:
            markdown = _insert_before_caption(markdown, reg["caption"], url)

    return {
        "markdown": markdown,
        "page_no": page_no,
        "dropped": dropped,
        "figure_text": figure_text,
        "figures": figures,
        "n_boxes": len(boxes),
        "n_paras": len(paras),
        "n_tables": len(tables),
    }
