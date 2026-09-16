# Bug 排查与修复报告（v0.4）

> 编写时间：2026-08-31
> 排查范围：D:/atomcode/大学生软件 全量源码 + 向量库 + 教材源文件
> 方法论：codebase-design（深模块 / 接口）+ diagnosing-bugs（反馈循环优先）

---

## 一、排查方法

1. 通读 `src/` 全部 10 个 Python 文件（main.py + engine/7 个 + ui/2 个），共 2419 行
2. 阅读全部 5 个冒烟测试（`tests/`）发现测试隔离问题
3. 写探针脚本（`tools/check_knowledge_quality.py`）实测向量库
4. 阅读 handoff 中标注的失败尝试，验证是否已彻底修复

## 二、排查发现清单（11 项）

| 等级 | 编号 | 位置 | 现象 | 根因 | 修复 |
|---|---|---|---|---|---|
| 🔴 P0 | B-1 | `main.py` PracticePage.check | 填空题/大题永远判对 | UI 无"对/错"按钮 + 逻辑硬编码 `else "对"` | 加 self_check 按钮 + check() 分支 |
| 🔴 P0 | B-2 | `main.py` WrongBookPage.review | 错题重刷自动判对 → 循环失效 | 提交 `q["answer"]`（正确答案）和 `"对"` | 改为交互式重刷 |
| 🔴 P0 | B-3 | `engine/knowledge_base.py` ingest_textbook | 重入库残留旧块（数据污染） | `upsert` 不删除旧 id | 先 `delete where source_file` |
| 🔴 P0 | B-4 | `data/textbooks_md/...课件版.md` | 10 块含页眉页脚残留 | PPT 标题页未清洗 | `_strip_slide_chrome` 过滤 |
| 🟡 P1 | B-5 | `tests/test_study.py` 等 | 测试写入真实向量库，留孤儿块 | 测试无 `cleanup` | 加 `delete_textbook` |
| 🟡 P1 | B-6 | `engine/question_bank.py` load | 题库缓存永不失效 | mtime 未感知 | 加 mtime 失效 |
| 🟡 P1 | B-7 | `engine/knowledge_base.py` score | 检索分数可负 | 未归一 | `max(0, 1-dist)` |
| 🟡 P1 | B-8 | `engine/converter.py` `_pdf_to_markdown` | 标题启发式过宽 | `stripped[0].isdigit()` 太宽 | 收紧至"第X章"或"编号+文字" |
| 🟢 P2 | B-9 | `main.py` | 重复 import + `top=HBox=QHBoxLayout` | 历史遗留 | 清掉 |
| 🟢 P2 | B-10 | `engine/finals.py` build_dashboard | 数据异常会崩首页 | 无 try/except | 异常隔离 |
| 🟢 P2 | B-11 | `ui/style.py` | 设计系统偏旧、无 hover | v0.4 前的初版 | 全套升级（详见 style.py 注释） |

## 三、数据重建结果

| 指标 | 修复前 | 修复后 |
|---|---|---|
| 向量库块数 | 274（含 13 块残留） | 261（与 handoff 原数一致） |
| 含页眉词的块 | **10** | **0** |
| id 断号 / 重复 | 0 / 0 | 0 / 0 |
| 平均块长 | 788 字 | 787 字 |
| 超短块（<30 字） | 2 | 3（新增 #0 概 述——PPT 标题页遗留） |
| 检索"TCP 三次握手" 命中 | 3 条相关 | 3 条相关 |
| 检索"物理层" 命中 | 第 1 条是 2.6 宽带接入 | 第 1 条是 2.6 宽带接入（n-gram 限制，等 v0.6 切 bge-m3） |

> 重建脚本：`tools/rebuild_knowledge_base.py`，备份位置：`data/backup/2026-08-31/`

## 四、代码 Bug 修复明细

### B-1 填空/大题永远判对（核心功能 bug）

**原代码**（main.py:407-420）
```python
def check(self) -> None:
    ...
    r = self.session.submit(answer if q["type"] == "选择题" else "对")  # 非选择题恒为 "对"
```

**新代码**
```python
def check(self) -> None:
    if q["type"] == "选择题":
        r = self.session.submit(answer)              # 自动判分
        ...
        self.advance()
    else:
        if not answer: return  # 强制先输入
        # 显示参考答案供对照
        self.log_box.append(f"你的答案：{answer}")
        self.log_box.append(f"参考答案：{expected}")
        self.log_box.append("请对照后点击「我答对了 / 我答错了」自查判分。")
        self.good_btn.setVisible(True)
        self.bad_btn.setVisible(True)
```

并新增 `self_check(correct)` 方法接收自查判分。同时修改 `practice.submit`：

```python
# 修复前：所有无答案题都被判错
if not expected:
    correct = False

# 修复后：仅选择题（自动判分）需要参考答案
if auto and not expected:
    correct = False
```

### B-3 重入库残留旧块（数据污染修复）

**原代码**
```python
collection = client.get_or_create_collection(...)
ids = [f"{md_path.stem}:{i}" for i in range(len(chunks))]
collection.upsert(ids=ids, documents=docs, metadatas=metadatas)
```

**新代码**
```python
collection = client.get_or_create_collection(...)
# 先删除该文档旧块（防残留：上次入库 300 块，本次清洗后只剩 261，
# 旧 261-299 的 id 会永久留在库里成为脏数据）
try:
    collection.delete(where={"source_file": md_path.name})
except Exception:
    pass
ids = [f"{md_path.stem}:{i}" for i in range(len(chunks))]
collection.upsert(ids=ids, documents=docs, metadatas=metadatas)
```

并新增公开助手供测试与重建脚本使用：
```python
def delete_textbook(source_file: str, course: str = "") -> int: ...
```

### B-4 教材源文件 PPT 页眉残留

新增 `_strip_slide_chrome(text)`，剔除以下行：
- `谢希仁  编著`（PPT 标题页页眉）
- `计算机网络（第 8 版）`（同）
- `课件制作人：...`（PPT 页脚）
- `第 X 章`（裸章号，无 `#` 前缀，真章节标题都有 `#`）

应用时机：ingest_textbook 在 `_merge_fragments` 之前调用；同时 `tools/rebuild_knowledge_base.py` 把清洗后内容写回源 md，让知识树 + Word 教材也受益。

### B-5 测试污染真实数据

修改 `tests/test_study.py`、`tests/test_finals.py`、`tests/test_knowledge_base.py` 收尾处加：

```python
from engine.knowledge_base import delete_textbook
delete_textbook("<source_file_name>")  # 清理测试向量块
```

## 五、UI 升级（style.py v0.4）

| 维度 | 升级 |
|---|---|
| 侧栏 | 墨蓝渐变 (`qlineargradient`)，选中态 SAGE 书签条 + 字重 600 |
| 卡片 | 圆角 8px，hover 加深边框 + 微亮底色 |
| 按钮 | 主 / 次级 / 成功 / 危险 四类，独立 hover/pressed 态 |
| 输入控件 | 圆角 6px，hover 边框加深，聚焦 1px 墨蓝 |
| 滚动条 | 收窄至 8px，hover 变墨蓝 |
| 类型层级 | 页标题 22px/300，组标题 13px/600，正文 13px |
| 色彩 | 中性色带墨蓝冷相，MUTED #7A848E 提升对比度 |

QSS-only 实现，不改业务代码。离屏验证全部页面切换正常（`build/tmp/shots/`）。

## 六、未修项（见架构文档 §1.2）

下列 8 项作为 v0.5+ 路线，本轮不修：
- main.py 718 行膨胀（拆 6 页面文件）
- engine 直耦 UI（缺 service 层）
- chromadb 耦合（缺存储抽象）
- n-gram 检索质量（待混合检索）
- 测试仍写共享 question_bank 文件（深隔离）
- 知识点提取词频启发（待规则/统计改进）
- 导出格式单一
- 无数据迁移机制

---

_本报告的根因分析与代码片段可直接用于代码审查或新人交接。_