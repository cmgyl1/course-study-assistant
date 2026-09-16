# HANDOFF — 大学生课程学习辅助软件（交接清单 v0.4）

> 更新时间：2026-09-16
> 最近一轮（09-11 ~ 09-16）：扫描版教材 OCR + 版面还原（图/表/章节）+ 整书阅读器 + 检索链路重做 + 闭环验收
> 详细报告：`docs/bug-report-v0.4.md` · 架构规划：`docs/架构设计与长期规划.md`
> **⭐ 操作规范（先读这份）：`docs/工程操作规范.md`** —— 铁律 / 难问题排查规程 / Bug 案例库 / 不可行路线 / Prompt 模板库

## 📂 工作目录

```
D:/atomcode/大学生软件/
```

## 1. 目标

本地运行的学习辅助软件：教材 RAG 知识库 + 自学/刷题/错题/冲刺全流程，PySide6 桌面程序 + onefile exe。

## 2. 当前状态（v0.4）

- 最新 exe：`dist/大学生软件.exe`（**建议重打包**——UI 设计与 bug 修复已落到 src，需 `tools/Python/python.exe -m PyInstaller …`）
- 向量库：**261 块**（v0.4 重建后，0 页眉污染，0 残留）
- 备份位置：`data/backup/2026-08-31/`（重建前的旧版本）
- 测试：5 个冒烟测试全部通过（tests/）

## 3. 已完成变更（v0.4 本轮）

### 3.1 Bug 修复（11 项，详见 bug-report-v0.4.md）

P0：
- 填空题/大题永远判对 → 加自查按钮
- 错题重刷自动判对 → 改交互式
- 教材重入库残留 → delete-before-upsert
- 教材页眉污染 → _strip_slide_chrome

P1：测试污染真实数据、题库缓存不失效、检索分数可负、PDF 标题启发式过宽
P2：重复 import、看板异常保护、设计系统升级

### 3.2 数据重建

- `tools/rebuild_knowledge_base.py` 一键清洗+重建
- `tools/check_knowledge_quality.py` 数据健康探针

### 3.3 UI 升级（style.py v0.4）

莫兰迪墨蓝书脊保留并深化：墨蓝渐变侧栏 + 4 类按钮态 + 卡片 hover + 圆角统一 + 类型层级清晰。

### 3.4 架构文档

`docs/架构设计与长期规划.md`：分层架构（UI / Service / Engine / Infrastructure）+ 接缝定义 + 长期路线图（v0.4→v0.8）。

## 4. 下一步（按优先级）

1. **重新打包 exe**（必须，UI 与代码变更已落到 src）
   ```
   tools/Python/python.exe -m PyInstaller --noconfirm --onefile --windowed --name 大学生软件 \
     --paths src --collect-all chromadb --collect-all jieba \
     --distpath dist --workpath build --specpath build src/main.py
   ```
2. 实测新版 exe 视觉与交互（重点：填空自查、错题重刷、首页 261 块）
3. v0.5 Service 层抽离（详见架构文档）

## 5. 故障尝试（沿用 handoff 旧版，新增）

- ~~测试写共享数据~~（v0.4 已修）
- ~~数据残留~~（v0.4 已修）

## 6. 新会话开场白

```
继续「大学生课程学习辅助软件」v0.4 项目（D:/atomcode/大学生软件/）。
本轮已完成 Bug 修复 11 项 + 数据重建（261 块 0 污染）+ UI 升级 + 架构文档。
变更详情：`docs/bug-report-v0.4.md` 与 `docs/架构设计与长期规划.md`。
向量库已重建干净，UI 设计系统 v0.4 已生效（侧栏渐变 + 自查按钮等）。
下一步：重打包 exe → 实测 → 决策 v0.5 Service 层方向。
先读 HANDOFF 与 bug 报告，再动手。
```
