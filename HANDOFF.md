# HANDOFF v0.5 — 自学模块对齐 reader（下一会话的执行手册）

> 生成：2026-09-23 18:12 ｜ 工作目录：`D:/atomcode/大学生软件/`
> 父提交：`124cfb3`（远端 `main` 已同步，工作树 clean）
> **本文只对本轮任务负责。** 项目现状的权威文档仍是 `README.md`；方法论归 `docs/工程操作规范.md`；设计/规划归 `docs/架构设计与长期规划.md`。
> 任务完成后：把本文移入 `docs/archive/` 并改名 `HANDOFF-v0.5.md`（与 v0.4 同样处理），根目录不留。

---

## 0. 新会话开场白（整段复制粘贴）

```
接手「大学生课程学习辅助软件」，工作目录 D:/atomcode/大学生软件/。
Python 一律用 D:/atomcode/大学生软件/tools/Python/python.exe。

任务：把软件的自学模块改成和离线阅读器 reader 一模一样。

请按顺序读：
1. HANDOFF.md                  ← 本轮任务完整规格（本文，唯一入口）
2. README.md                   ← 项目现状与基线
3. docs/工程操作规范.md         ← 六条铁律 / 排查规程 / Bug 案例库
4. docs/架构设计与长期规划.md    ← 分层架构与技术决定

决策已定，直接开工，不要再问：
- 路线 = 原生复刻（PySide6 控件重做展示层，不引 Chromium / WebEngine）
- 范围 = 严格照搬 reader（自学页只留 书名分组 + 章节树 + 检索框 + 正文）

开工前先把「现状 + 第一步」复述一遍，然后按 HANDOFF §3 逐条执行。
```

---

## 1. 现状摘要（Current State Summary）

项目是本地离线的学习工作台：扫描版教材 PDF → OCR → 版面还原 → 检索语料 → **PySide6 桌面程序 + 单文件离线阅读器**。
第 1 门课「计算机网络（谢希仁 第8版，485 页扫描件）」全流程闭环，其余 3 门待接入。

**此刻的状态：**

- 代码定版在提交 `124cfb3`，远端 `main` 同步，工作树 clean。
- 打包产物 `大学生软件.exe` 已在**项目根目录**（105 MB，双击即用；`dist/` 只留历史 `.bak`）。
- 检索链路刚做完一次大收敛：**chroma 向量路已整体拆除**，全项目只剩 BM25 一条路，界面与离线阅读器同源。
- **没有任何正在进行的改动** —— 本文描述的任务尚未动一行代码，是干净起点。
- 唯一未修缺陷是 *R-7（`build_chunks` 静默丢弃短段落）*，**不在本轮范围**（见 §12）。

**本轮要做什么（一句话）**：把软件「自学」模块的界面与交互，改成和离线阅读器 `data/reader.html` 一模一样。

---

## 2. 关键上下文（Important Context）

### 2.1 环境（先照抄这几条，能省半小时）

| 项 | 值 |
|---|---|
| 工作目录 | `D:/atomcode/大学生软件/` |
| **Python（只能用这个）** | `D:/atomcode/大学生软件/tools/Python/python.exe` —— 系统 Python **没有** PySide6 / jieba |
| Bash 工具 | **默认 PATH 是坏的**（`dirname: command not found`、`cd: null directory`）。每条命令前先 `export PATH="/usr/bin:/bin:/c/Windows/System32:/c/Windows:/c/Users/CHY/.workbuddy/binaries/PortableGit/versions/1.2.0/cmd"`；或改用 PowerShell 工具 `Out-File -Encoding UTF8` 写文件、再用 Read 读回 |
| 读中文文件 | 用 Read 工具直读。**不要**走 PowerShell 的 `Get-Content -Raw \| Out-File` 管道（会转成 `鈹€` 这类乱码） |

### 2.2 最要紧的一条事实

**reader 的检索根本不是另一套实现。** `tools/build_reader.py` 里的分词、BM25（`k1=1.5, b=0.75`）、
两条拒答判据，全是 `engine.retrieval` 的 JS 复刻。所以本轮**不需要重做检索**，只需要重做**展示层**。
这是整个任务的成本判断基础 —— 不要另起一套算法。

### 2.3 架构与接缝（Architecture Overview）

```
PySide6 UI（src/main.py + src/ui/）→ src/services/（编排）→ src/engine/（核心能力）→ data/（产物）
```

引擎零 UI 依赖。**不要在 `main.py` 里直接 import engine**，一律经 `services/`。

### 2.4 主题已同族（不用重做配色）

软件 `src/ui/style.py` 用深色 token `#0F1418 / #5A8DD6 / #E0B266`；
reader 的 CSS 变量是 `--bg:#0f1115 / --accent:#5a8dd6 / --gold:#e0b266`。
reader 本来就是这套设计系统的变体，直接沿用现有 token 即可。

### 2.5 参照物在哪

- 生成器：`tools/build_reader.py` —— 看 `_CSS`、`_JS`、`_render_html` 三处就够（**本轮不改它**）
- 成品：`data/reader.html`（3.88 MB 单文件，双击即可对照；插图按相对路径 `figures/…` 引用）

---

## 3. 立即开始的第一步（Immediate Next Steps）

按顺序做，不要跳：

1. **先复述**：读懂 §1/§2/§4 后，把「现状 + 打算怎么改」复述一遍再动手。
2. **看参照物**：打开 `data/reader.html` 双击对照，重点是它的检索结果长什么样（卡片列表），
   同时读 `tools/build_reader.py` 的 `_JS` 里的 `doSearch()` / `show()` / `hl()` / `tableHtml()`。
3. **做唯一需要决策的一件事**（详见 §4 改动点①）：
   卡片右上角的「命中 N 词」在 Python 侧**当前拿不到**，要么加性扩展引擎（`sections` 加 `n_hits`，
   需重跑验收），要么卡片不显示这个角标。**选一个并说明理由**，然后开始改。
4. **第一处代码动 `src/main.py` 的 `StudyPage`**（约 322–580 行）。
5. **改完立刻同步 `build/verify_study_page.py` 的断言**（见 §6 陷阱 3），再跑 §7 验收。

---

## 4. 任务规格：六个改动点

### ① 检索结果：从"铺开段落"改成"卡片列表"（最大改动）

- **现状**：`src/main.py` 的 `ask()`（约 490 行）→ `study_service.explain_topic()` →
  `_render_answer()`（约 529 行），把 `evidence` 直接铺成"依据 1/2/3"的整段原文。
- **目标**（严格对齐 `build_reader.py` 的 `doSearch()`）：
  - **命中章节卡，最多 6 张**：`标题` + `书名 · 第 N 页` + 右上角 `命中 N 词`；点击 → 跳该节原文
  - **原文片段卡，最多 10 张**：右上角 `BM25 分数` + `第 N 页` + 该节标题 + **前 160 字预览（命中词高亮）**；点击 → 跳该节原文
  - 两段小标题：`命中的章节` / `原文片段`
  - 空结果文案：`书中未找到「X、Y」，不做猜测性作答。`
    —— 并且**只显示"未找到"，不显示任何段落**（reader 与软件都有这条硬规则，别退化）
- **实现方式（关键）**：用 `QListWidget` + `setItemWidget()` 自绘卡片 widget。
  **不要**把 reader 的卡片 CSS 搬进 `QTextBrowser` —— 它不支持 `flex` / `position:fixed`，那条路走不通。
- **top_k 对齐**：reader 是「标题 6 / 片段 10」；软件 `explain_topic(top_k=5)` 默认 5。
  → 调用时传 `top_k=10`，再 `sections[:6]`、`passages[:10]`。
- ⚠️ **引擎侧缺一个字段（开工第一件要决策的事）**：卡片上那个「命中 N 词」**当前拿不到**。
  `engine/retrieval.py` 的 `TitleIndex.match()`（约 372 行）内部算了 `len(hit)`，但只 `return [(idx, sc) …]`；
  `_one_pass()`（约 420 行）据此组出的 `sections` 里没有命中词数。
  - **要显示** → 加性扩展 `match()` 与 `sections`（加 `n_hits` 键）。这属于**改引擎**，
    按规范铁律必须重跑 `build/acceptance.py` + `tests/test_retrieval.py` 对照。
  - **不想动引擎** → 卡片不显示「命中 N 词」，其余完全一致，只差这一个角标。
  - 二选一并说明理由，**不要默默跳过**。

### ② 命中词高亮

- reader 用 `<mark>`（蓝底 `#5A8DD6` 白字），且**只高亮长度 > 1 的词**（`hl()` 里 `filter(k=>k.length>1)`）。
- `QTextBrowser` 支持背景色 span，可行。
- 软件现状：`_render_answer` 无任何高亮。

### ③ 每段前面的页号徽章 `P123`

- reader 在**每个段落**前放 `<span class="pg">P123</span>`（小底、圆角、等宽数字）。
- 软件现状：`study_service.render_section_html()`（约 185 行）**只给标题**带页号（197–200 行）。
- `SectionBlock.page` 段落块已有页码 → 直接可用，不需动引擎。

### ④ 插图放大：`QDialog` 弹窗 → 全屏遮罩

- reader：`#lb` 全屏黑底遮罩（`rgba(0,0,0,.9)`，图 `max-width:96%`），**点任意处关、Esc 关**。
- 软件现状：`StudyPage._on_anchor_clicked()`（约 502 行）弹一个 `QDialog`，必须手动点叉。
- 改法：无边框 `QDialog`（`Qt.FramelessWindowHint`）+ 黑底 + 点击关闭 + `keyPressEvent` 吃 Esc。

### ⑤ 点击卡片 → 跳该节原文（含树节点选中）

- 渲染正文可复用现成的 `study_service.get_section_reading(section_path, course)`。
- 但 reader 同时会把左栏对应项标记为选中（`show(si)` 里 `classList.toggle('on')`）。
  软件要等效就必须写 **「节路径 → 树节点」反查** —— 现有 `on_tree_click()`（约 454 行）只有**树→路径**单向。
  **不做这个反查，点卡片会"正文变了但树不高亮"**，看起来像坏了。

### ⑥ 页面布局按 reader 重排（别漏）

- reader：**左栏章节树（约 290px，书名分组标题用金色）+ 右侧正文区**，检索框在顶部 header 横向条上。
- 软件现状：竖排 —— 课程行在上、知识树在中、检索框再下、正文最下。
- 要"长相一致"就得改成左右两栏。这是本轮唯一的结构性重排。

---

## 5. 「严格照搬」的具体含义（用户已明确选择）

自学页最终只保留：**书名分组 + 章节树 + 检索框 + 正文**。因此要**去掉**：

- 课程下拉框（`self.course_box`）
- 知识树里的 `📌` 知识点叶子（`_add_nodes` 里渲染 concepts 的那段）
- 索引预热状态标签（`self.index_label`）

⚠️ 三条执行纪律：

1. **只改渲染，不删引擎能力。** `study_service.get_course_tree()` 仍会返回 `concepts`，
   `study.warm_up()` 仍要被调用 —— 只是不再显示。删引擎能力，日后要用得重写。
2. **去掉下拉后课程从哪来**：建议在 `MainWindow._goto_page(name)` 上加可选 `course` 参数，
   并让首页 `_CourseCard` 可点击（**现在它没有 `mousePressEvent`，是不可点的**），
   点课程卡 → 进自学页并带上该课程。这样"自学页没有下拉"（满足照搬），
   但日后接入其余 3 门课仍有入口。另需一个模块级默认课程常量（当前实际只有「计算机网络」有数据）。
3. 该改动会让"其余 3 门课在自学页没有直接入口"—— 已知情并接受，上面第 2 条是低成本对冲。

---

## 6. 三个必须绕开的陷阱（Potential Gotchas）

1. **`QTextBrowser` 是 Qt 富文本子集**：不支持 `flex`、`position:fixed`、CSS 动画。
   → 卡片用 `QListWidget` + `setItemWidget`；遮罩用无边框 `QDialog`。**不要翻译 CSS。**
2. **卡片跳转需要"路径→树节点"反查**（见 §4 ⑤）。少了它，交互看起来是坏的。
3. **`build/verify_study_page.py` 会立刻炸**：它直接读 `page.log_box` / `page.query_edit` /
   `page.tree` / `page.course_box` / `page.index_label` / `page._warm_state`（约 66–122 行）。
   改 UI 后**必须同步改这些断言**，否则你会以为功能坏了。这是本轮最容易忘的一件事。

---

## 7. 验收标准（照这个逐条验，别自说自话）

**先跑基线对照，再验证新交互：**

```bash
PY="D:/atomcode/大学生软件/tools/Python/python.exe"
"$PY" build/acceptance.py --log build/accept_full.log   # 检索 + 插图 + 表格
"$PY" build/verify_inline.py                            # 图片文件实存（防裂图）
"$PY" build/verify_study_page.py                        # 自学页闭环（需同步改断言）
"$PY" tests/test_retrieval.py                           # 检索与阅读层
```

**新增断言（扩进 `build/verify_study_page.py`）：**

| 断言 | 判据 |
|---|---|
| 卡片列表渲染 | 搜「三次握手」后，卡片区条目数 > 0 且卡片上含分数与页码 |
| 预览不超长 | 片段卡预览 ≤ 160 字，截断处有省略号 |
| 点卡片能跳 | 触发卡片点击后，正文控件非空，且左栏选中项标题 == 卡片所属节 |
| 命中高亮 | 正文 HTML 里含高亮标记（背景色 span / mark 等价物） |
| 段落页号徽章 | 正文段落前出现 `P<数字>` |
| 遮罩开合 | 打开后按 Esc 能关闭 |
| 拒答不退化 | 搜「量子纠缠」→ 出现「未找到」且**不出现任何"依据"段落** |

**离屏验证的两条硬要求**（否则截图必废、结论必错）：

- 必须走 `build/make_screenshots.py` 的 `ms._build_app()`，它已注册微软雅黑等字体；
  否则 offscreen 下中文全是豆腐块（识别症状：PNG 只有 10–13 KB）。
- 侧栏默认收起（宽 0），要手动定宽 + `win._hover_timer.stop()`，见 `verify_study_page.py` 约 56–61 行的现成写法。

---

## 8. 回归基线（低于此即回归，不许放过）

```
485 页 · 插图落位 296/296 · 表格结构 93/93 · 检索验收 9/9 · test_retrieval 15/15
语料 1698 块 · 9 个测试文件全绿
单册全量 OCR 1163s / 1071s；缓存重放 24s / 14s
```

`data/ocr_cache/` 是关键基础设施（改判据可秒级重放），**勿删**。

---

## 9. 关键文件地图（Critical Files）

| 文件 | 本轮要动的地方 |
|---|---|
| `src/main.py` | `StudyPage`（约 322–580 行）—— 布局重排、卡片列表、遮罩、树反查、`_render_answer` 重写；`HomePage._CourseCard`（约 97 行，加可点击）；`MainWindow._goto_page`（约 1062 行，加 course 参数） |
| `src/services/study_service.py` | `render_section_html()`（约 185 行）—— 段落加页号徽章、段落级高亮；可能需新增「DTO → 卡片」辅助函数 |
| `src/engine/retrieval.py` | **仅当要显示「命中 N 词」时**才动：`TitleIndex.match()`（约 372 行）、`_one_pass()`（约 420 行） |
| `src/ui/style.py` | 卡片 / 遮罩 / 树选中态的 QSS token |
| `build/verify_study_page.py` | 同步改断言 + 加新断言（**必改**） |
| `build/make_screenshots.py` | 改完后重跑，重生成 README 的 6 张截图（自学页 `03` 必变） |
| `tools/build_reader.py` | **本轮不改**，是"一模一样"的参照物 |
| `data/reader.html` | 参照用的成品，双击即可对照 |

---

## 10. 决策记录（Decisions Made）

| 决策 | 结论 | 理由 |
|---|---|---|
| 实现路线 | **原生复刻**（PySide6 控件） | 不引 Chromium，exe 保持 **105 MB**、内存不涨 |
| 范围 | **严格照搬 reader** | 用户明确选择；已知悉会去掉课程下拉与知识点叶子 |
| 内嵌 WebEngine | **本轮否决** | `Qt6WebEngineCore.dll` 单个 **194 MB**（实测），exe 会从 105 MB 涨到约 190–210 MB，内存 +150–250 MB，启动慢 1–2 s；且 `setHtml/setContent` 有 **2 MB 上限**（Qt 官方文档），而 `data/reader.html` 是 **3.88 MB**，必须绕临时文件 + `load(file://)`。得不偿失 |
| 本地大模型 / Ollama | **早已否决**（2026-09-16） | 见架构文档附录 B，不要再提 |
| chroma 向量路 | **已于 2026-09-23 整体拆除** | 全项目只剩 BM25 一条路；`knowledge_base.py` 与 `data/vector_store/` 已删，备份在 `data/backup/2026-09-23-vector_store/` |
| 卡片显示「命中 N 词」 | **待本轮执行者选**（见 §4 ①） | 要显示就得加性改引擎并重跑验收；不显示则零引擎改动 |

---

## 11. 工程纪律（假设与铁律，沿用项目规范）

1. **改代码必须在启动长任务之前** —— Python 进程启动即定型模块（曾导致 485 页整批作废）。
2. **改判据前先 dump 原始数据**：`build/probe_boxes.py --pages N`；优先几何判据，不用距离阈值。
3. **一次只改一个变量**，同一批样本对照。
4. **全局判断放最晚层**（合并层秒级重跑），不放分页层。
5. **一个 bug 常有 N 处同款** —— 修完全项目搜一遍。
6. **测试默认隔离** —— 不写真实数据；用独立课程名 / 临时目录 / 快照-还原。
7. **归档不删除**；个人目录（桌面/下载/文档）只读，任何移动删除先告警 + 列清单 + 等确认。
8. **禁止 `except: return 0` 静默兜底**（曾让 `delete_textbook` 长期静默失效）。
9. **测了引擎 ≠ 测了用户路径** —— 断言必须落在"UI 实际调用的那个函数"上
   （案例 R-6：软件曾接了差的检索路而测试全绿）。
10. **缩小语料上不能验证"阈值型判据"** —— 拒答判据二（每个命中词 DF ≤ 2 即视为顺带提及）
    按 1698 块定标；几十块的语料里任何词 DF 都 ≤2，必然误判为"书里没讲过"。
    要验检索就用**真实教材**（只读）。诊断线索：`missing_tokens=[]` 却 `status=not_found`。

---

## 12. 待修缺陷（**不在本轮，别顺手改**）

**R-7：`build_chunks` 静默丢弃短段落。**
`engine/retrieval.py` 的 `build_chunks` 里 `min_chars=60` 的合并分支，
在"前一块恰好是标题块"时直接 `continue` → **小节首段若短于 60 字会整段消失**
（搜不到、阅读页也没有）。真实教材影响有限（首段通常较长），但它属于"静默丢数据"。
改的是**语料构建判据**，必须单独一轮重跑 `acceptance.py` + `test_retrieval.py` 对照，不能搭车。

---

## 13. 收尾清单（做完功能必须走完，否则等于没做完）

1. 跑 §7 全部验收 + 全部 9 个测试文件，基线不退。
2. 重生成 README 的 6 张截图：`"$PY" build/make_screenshots.py`（**自学页那张一定变了**）。
3. 重新打包 exe（产物直接落**项目根**，别落 `dist/`）：
   ```bash
   "D:/atomcode/大学生软件/tools/Python/python.exe" -m PyInstaller --noconfirm --onefile \
     --windowed --name 大学生软件 --paths src --collect-all jieba \
     --distpath . --workpath build/PyInstaller_work --specpath build src/main.py
   ```
4. 离屏启动根目录 exe 取证：进程存活 + `crash.log` 为 0 字节。
   （`Start-Process` 会被安全策略拦，用 `Invoke-Item`；且必须在**同一条命令内**完成"启动+等待+取证"）
5. 提交（中文，首行 `<type>: <主题>`）+ 用 API 通道推送：
   ```bash
   "$PY" tools/push_via_api.py
   ```
   本机**无法直连 github.com**（`git push` / `fetch` / `pull` 一律不可用）。
   推送后因无法 fetch，需手工写 `.git/refs/remotes/origin/main`，否则 `git status` 显示 `[gone]`。
6. 更新 `README.md` §2.2/§7、`.workbuddy/memory/` 当日日志；
   把本文移入 `docs/archive/` 并改名 `HANDOFF-v0.5.md`。

---

## 14. 参考文档（权威三件套，别另建文档）

| 文档 | 管什么 |
|---|---|
| `README.md` | **现在到哪了** —— 状态 / 基线 / 命令 / 下一步。唯一入口 |
| `docs/工程操作规范.md` | **怎么做** —— 六条铁律 / 排查规程 / §6 全项目唯一 Bug 案例库 / 不可行路线黑名单 / Prompt 模板库 |
| `docs/架构设计与长期规划.md` | **是什么、往哪去** —— 产品定位 / 分层架构 / 接缝 / 路线图 / 附录 A 向量路 / 附录 B 技术决定（含已否决项） |

**归位规则**：状态→README；方法/坑→规范；设计/规划→架构。**禁止再往 `docs/` 根目录新增主题文档。**
