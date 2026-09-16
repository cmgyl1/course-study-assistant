# 大学生课程学习辅助软件

> 本地离线学习工作台：**扫描版教材 PDF → OCR → 版面还原 → 检索语料 → 桌面 App + 离线网页阅读器**。
> 工作目录：`D:/atomcode/大学生软件/` · 版本：**v0.5**（文档流水线闭环）· 更新：2026-09-16

**这是本项目的唯一入口文档。** 看完这一页就能上手，需要细节再按 §5 索引跳转。

> ℹ️ **从 GitHub 克隆下来的？先看这里。**
> 本仓库只含**程序本体**：`src/`（引擎/服务/UI）、`tools/`（流水线脚本）、`build/`（验收与探针）、`tests/`、`docs/`。
> 自带运行时（约 3.4 GB）与教材数据（受第三方版权保护）**不在仓库内**，克隆后需按 **§3.1-A** 准备环境、**§3.3** 跑流水线才能出数据。

---

## 0. 新会话怎么开局（复制即用）

把下面整段粘贴给 AI：

```
接手「大学生课程学习辅助软件」项目，工作目录 D:/atomcode/大学生软件/。
Python 一律用 D:/atomcode/大学生软件/tools/Python/python.exe。

请先读这三份（按顺序）：
1. README.md            ← 项目现状与入口（本文件）
2. docs/工程操作规范.md  ← 怎么做：六条铁律 / 排查规程 / Bug 案例库 / 不可行路线 / Prompt 模板
3. docs/架构设计与长期规划.md ← 是什么：分层架构 / 产品定位 / 路线图 / 技术决定

当前基线：485 页 · 插图落位 296/296 · 表格还原 93/93 · 检索验收 9/9 · test_retrieval 8/8。
先复述你理解的「当前状态 + 下一步」，等我确认后再动手。
```

---

## 1. 这是什么

面向在校生的**个人学习工作台**：把教材、课件、题库统一收进本地知识库，提供自学 / 刷题 / 错题 / 期末冲刺全流程辅助。数据与 AI 能力本地运行，**教材原文作为权威依据**，不做无据生成。

首批 4 门课：计算机网络（谢希仁 第8版）· UML2 面向对象分析与设计 · 软件工程导论 · 算法设计与分析。
**当前已完整落地第 1 门**（485 页扫描件全流程跑通），其余 3 门待按同一流水线接入。

### 三层架构（一句话）

```
PySide6 UI  →  src/services/（编排）  →  src/engine/（核心能力）  →  data/（产物）
```

UI 与引擎解耦，引擎零 UI 依赖。详见 `docs/架构设计与长期规划.md`。

---

## 2. 当前状态（实测基线）

### 2.1 文档处理流水线（v0.5 主线，已闭环）

| 指标 | 数值 |
|---|---|
| 整书 | **485 页**（上半 250 + 下半 235） |
| 插图落位 | **296 / 296 = 100%**（每张图后紧跟同名图题、同页） |
| 表格还原 | **93 张，结构合格 93 / 93 = 100%** |
| 检索验收 | **9 / 9 通过**（含拒答、AND→OR 放宽、跨页落位） |
| 阅读器 | 241 节 / 1459 片段 / 296 图 / 93 表 / 页码 1–474 |
| 单册全量 OCR | 上半 1163s · 下半 1071s（≈4s/页） |
| 单册缓存重放 | 上半 **24s** · 下半 **14s**（≈ 50–76 倍加速） |

> **这是回归基准。** 任何改动后跑一遍 §3.4 验收，数字低于上表即视为回归。

### 2.2 应用层

| 项 | 状态 |
|---|---|
| 知识树 | 上册 5 章 / 下册 16 章 / 课件版 9 章（附录已正确归位） |
| 章节阅读 | `QTextBrowser` 内嵌原文 + 插图 + 表格，**保序**呈现（图在原位，不堆章尾） |
| 向量库 | 261 块（v0.4 重建后 0 页眉污染、0 残留） |
| 测试 | `tests/` 10 个冒烟测试全绿，且**不污染真实数据** |
| exe | `dist/大学生软件.exe` 为 **v0.4 时期产物，已过期**，需重打包 |

### 2.3 已知限制（不是 bug，别当 bug 修）

| 现象 | 说明 |
|---|---|
| 附录里出现"第1章…第9章" | 是书末**附录A 部分习题的解答**，本就应该挂在附录下 |
| 语料块数 1702 → 2485 | `list_books()` 同时命中了"课件版.md"（第三本），不是异常 |
| OCR 上下标丢失（`10⁶` → `10°`） | 扫描件识别固有限制，只能缓解不能根治 |
| 检索是**词法** BM25，非语义 | 向量升级方案见 `docs/架构设计与长期规划.md` 附录 A |
| 本地大模型（Ollama 等）**已否决** | 2026-09-16 决定不引入本地 LLM，方案材料已清出文档；「答疑」仍为预留位、底座待定。**不要再提** |

---

## 3. 快速开始

### 3.1 环境

**A. 全新克隆（从 GitHub 拿到代码后）**

```bash
git clone https://github.com/cmgyl1/course-study-assistant.git
cd course-study-assistant

python -m venv .venv
source .venv/Scripts/activate        # Windows Git Bash；PowerShell 用 .venv/Scripts/Activate.ps1
pip install -r requirements.txt
```

需要额外准备两样（仅题库/课件格式转换用到，可后补）：

```bash
# pandoc   —— docx/md 互转
# LibreOffice —— pptx/ppt 转换
# 安装后把路径写进 src/engine/config.py
```

再自备教材放入 `data/textbooks/`（见 `data/README.md`），然后按 §3.3 跑流水线。

**B. 本机开发环境（自带运行时，Git Bash 需显式 PATH）**

```bash
export PATH="/c/Users/CHY/.workbuddy/binaries/PortableGit/versions/1.2.0/usr/bin:/c/Windows/System32:$PATH"
cd "D:/atomcode/大学生软件"
PY="D:/atomcode/大学生软件/tools/Python/python.exe"
```

> 项目自带 `tools/Python`（3.12.10）与全部依赖，**B 路无需 pip install**。

### 3.2 跑软件

```bash
"$PY" src/main.py
```

### 3.3 文档流水线（六层，单向依赖）

```bash
# ① 抽取：PDF → 分页 md + 裁切插图（首次全量 ~20 分钟/册）
"$PY" tools/ocr_textbook.py --pdf "计算机网络（第8版）_谢希仁_上半"
# ① 重放：改过 layout.py 后走缓存重放（~24 秒）
"$PY" tools/ocr_textbook.py --pdf "计算机网络（第8版）_谢希仁_上半" --force

# ② 清洗合并：分页 → 整册（剔目录页 / 修页码 / 附录归一）
"$PY" tools/merge_ocr_pages.py --pdf "计算机网络（第8版）_谢希仁_上半"

# ③ 语料 → ④ 阅读 → ⑤ 交付阅读器
"$PY" tools/build_corpus.py
"$PY" tools/build_reader.py          # → data/reader.html

# ⑥ 验收
"$PY" build/acceptance.py --log build/accept_full.log
```

> 完整命令（含全部测试与探针）见 `docs/工程操作规范.md` §8。

### 3.4 验收口径（低于此即回归）

```
插图落位 296/296 · 表格结构 93/93 · 检索 9/9 · test_retrieval 8/8
```

```bash
"$PY" build/acceptance.py --log build/accept_full.log   # 检索 + 插图 + 表格
"$PY" build/verify_inline.py                            # 图片文件实存（防裂图）
"$PY" tests/test_retrieval.py                           # 检索与阅读层
"$PY" tests/test_knowledge_base.py                      # 向量库
"$PY" build/_uicheck.py && build/_qtcheck.py 对比        # UI 链路 + 图片真实加载
```

### 3.5 打包 exe

```bash
"$PY" -m PyInstaller --noconfirm --onefile --windowed --name 大学生软件 \
  --paths src --collect-all chromadb --collect-all jieba \
  --distpath dist --workpath build/PyInstaller_work --specpath build src/main.py
```

---

## 4. 最常踩的三个坑（先看这里，能省几小时）

| # | 坑 | 正确做法 |
|---|---|---|
| 1 | **改完代码就跑长任务** → 整批产物作废 | Python 进程启动即定型模块。**先把代码改完落盘，再启动 OCR**（曾经 485 页整批作废，只因 `layout.py` 晚改了 9 分钟） |
| 2 | 在**全量重跑**里调判据（每次 20 分钟） | 改判据前先落盘**原始 OCR 框**（已在 `data/ocr_cache/`）。改完走 `--force` 缓存重放，**24 秒** |
| 3 | 一处判据改了，**另一处同款逻辑没改** | 本项目"标题栈弹栈"缺陷在 **3 个文件**里重复出现。修完必须全项目搜一遍同款 |

其余铁律与 17 条 Bug 案例（按症状检索）见 `docs/工程操作规范.md` §4 / §6。

---

## 5. 文档索引

**只有 3 份活文档 + 1 个归档目录。** 各管一件事，不重复：

| 文档 | 管什么 | 什么时候看 |
|---|---|---|
| **`README.md`**（本文） | **现在到哪了** —— 状态、基线、命令、下一步 | 每次开工第一眼 |
| **`docs/工程操作规范.md`** | **怎么做** —— 六条铁律 / 难问题排查规程 / Bug 案例库 / 不可行路线黑名单 / Prompt 模板库 | 遇到难问题、要改判据、要投喂 AI 时 |
| **`docs/架构设计与长期规划.md`** | **是什么、往哪去** —— 产品定位 / 分层架构与接缝 / 数据来源 / 路线图 / 技术决定 | 要动架构、要加功能、要做技术选型时 |
| `docs/archive/` | **历史归档** —— 已被上述 3 份吸收的旧文档（方案草案 / 工具清单 / 导入指南 / bug-report-v0.4） | 极少。查历史决策时 |

### 写文档的归位规则（**防止再次碎片化**）

新增知识时，按"这份知识回答什么问题"决定放哪：

| 问题 | 归位 |
|---|---|
| 现在什么状态？下一步做什么？ | `README.md` §2 / §6 |
| 怎么做 / 别做什么 / 踩过什么坑？ | `docs/工程操作规范.md` |
| 为什么这样设计？未来怎么走？ | `docs/架构设计与长期规划.md` |
| 日常流水账（改动记录、验证数字） | `.workbuddy/memory/YYYY-MM-DD.md` |

> ⚠️ **不要再往 `docs/` 根目录新增主题文档。** 先判断能否并入上述 3 份的现有章节；确实无法归入时才新建，并同步更新本表。

---

## 6. 目录结构

```
大学生软件/
├── README.md                  ← 唯一入口（本文件）
├── docs/                      ← 3 份活文档 + archive/ 归档
│   ├── 工程操作规范.md
│   ├── 架构设计与长期规划.md
│   └── archive/
├── src/
│   ├── engine/                ← 核心能力（无 UI 依赖）
│   │   ├── layout.py          ← 🔴 版面还原核心（行→段→标题→图区→表格）
│   │   ├── retrieval.py       ← 🟡 切块 / 标题索引 / BM25 / 放宽 / 拒答
│   │   ├── textbook_reader.py ← 🟡 按章节取保序块序列
│   │   ├── knowledge_base.py  ← chroma 向量库（n-gram 哈希，旧链路）
│   │   ├── study.py / practice.py / finals.py / question_bank.py / converter.py / config.py
│   ├── services/              ← 编排层（UI 只调这里）
│   ├── ui/                    ← 设计系统 / 动效
│   └── main.py                ← PySide6 主程序
├── tools/                     ← 生产脚本 + 自带运行时（Python / pandoc / LibreOffice）
│   ├── ocr_textbook.py  merge_ocr_pages.py  build_corpus.py  build_reader.py
│   └── rebuild_knowledge_base.py  check_knowledge_quality.py  import_textbooks.py …
├── build/                     ← 探针与验收脚本（一次性问题用一次，但先留着）
│   ├── acceptance.py          ← 主验收
│   ├── probe_boxes.py         ← 改版面判据的第一手证据
│   └── archive_2026-09-11/    ← 早期一次性实验（已归档，勿删）
├── tests/                     ← 10 个冒烟测试，默认隔离、不写真实数据
├── data/                      ← 全部产物
│   ├── textbooks/               原始 PDF（唯一权威源，勿删）
│   ├── ocr_cache/<册>/          原始 OCR 框缓存（改判据秒级重放的关键，勿删）
│   ├── textbooks_md/<册>/       分页 md
│   ├── textbooks_md/<册>.md     合并后的整册 md
│   ├── figures/<册>/            裁切插图
│   ├── reader.html              离线阅读器（单文件）
│   ├── vector_store/            向量库
│   └── backup/<日期>/           回滚点（保留 ≥30 天，不是垃圾）
├── dist/                      ← 打包产物
└── reserved/                  ← 预留模块位（答疑 / 课程同步 / 移动端）
```

---

## 7. 下一步（按优先级）

1. **重打包 exe** —— `dist/大学生软件.exe` 是 v0.4 产物，未含 OCR 流水线与新版界面。命令见 §3.5。
2. **实测新版 exe** —— 重点看：知识树章节、原文内嵌图是否在原位、表格是否正确渲染。
3. **接入其余 3 门课** —— 走同一条流水线；扫描件质量不同可能需微调 `layout.py` 判据（改判据流程见规范 §7-P7）。
4. **v0.6 语义检索升级（可选）** —— 引入 `bge-small-zh-v1.5`（~95MB）+ `onnxruntime`，与现有 BM25 做 RRF 混合检索。属增益项，不阻塞交付。详见架构文档附录 A。

> **已否决项不进路线图**：本地大模型方案（Ollama）已于 2026-09-16 否决，论证见架构文档附录 B —— **不要再提**。

---

_本文档是项目唯一入口。状态变化时更新 §2 与 §7；新增文档时先读 §5 的归位规则。_
