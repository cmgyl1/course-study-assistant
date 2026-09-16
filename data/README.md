# data/ —— 运行期数据目录（不入库）

本目录**不随仓库分发**。原因是其中的内容分三类，都不适合放进公开仓库：

| 子目录 | 内容 | 为何不入库 |
|---|---|---|
| `textbooks/` | 教材扫描件 PDF | 受版权保护的商业教材，且单册 60 MB+ |
| `textbooks_md/` | OCR 还原出的整本 Markdown | 同上（教材全文） |
| `figures/` | 从教材裁切出的插图（约 300 张） | 同上 |
| `reader.html` | 生成的整书阅读器 | 内嵌教材全文与插图 |
| `textbooks_docx/` | 教材转换出的 docx | 同上 |
| `vector_store/` | chroma 向量库 | 可由教材重新生成 |
| `ocr_cache/` | OCR 原始检测框缓存 | 可由扫描件重新生成 |
| `backup/` | 数据快照 | 冗余 |
| `question_banks/`<br>`wrong_book/`<br>`materials/`<br>`annotations/` | 题库 / 错题本 / 资料 / 笔记 | 个人学习数据 |

---

## 如何从零复现

仓库自带完整的生产脚本，按顺序执行即可重建全部数据：

```bash
# 0) 准备：把自有教材放入 data/textbooks/（见下「教材来源」）
# 1) OCR + 版面还原（产出 data/textbooks_md/<册>/page_NNNN.md 与 data/figures/）
python tools/ocr_textbook.py --pdf "<教材名>_上册"
python tools/ocr_textbook.py --pdf "<教材名>_下册"

# 2) 逐页结果合并为整册 Markdown（剔除目录页、修正页码、归一化附录）
python tools/merge_ocr_pages.py --pdf "<教材名>_上册"
python tools/merge_ocr_pages.py --pdf "<教材名>_下册"

# 3) 教材入库（切块 + 向量化，构建 data/vector_store/）
python tools/import_textbooks.py

# 4) 生成整书 HTML 阅读器（data/reader.html）
python tools/build_reader.py

# 5) 验收（检索用例 + 插图落位 + 表格结构）
python build/acceptance.py --log build/accept.log
```

`ocr_textbook.py` 会把每页的**原始检测框**缓存到 `data/ocr_cache/`。
调完版面判据后加 `--force` 可按缓存重放，无需重新跑 OCR
（实测整册从约 20 分钟降到 20 秒级）。

---

## 教材来源

本项目**不附带、也不分发任何教材文件**。请自行准备合法取得的学习资料：

- 购买正版纸质书 / 电子书后自行扫描或使用随书附带的合法电子版；
- 使用出版社或课程平台提供的、允许个人离线使用的教材文件；
- 或直接换用开放许可（CC / 公有领域）的教材自测整条流水线。

放入 `data/textbooks/` 后，第 1 步即可跑通。目录结构与命名约定见
`docs/工程操作规范.md` §2.6。

---

## 注意

- 目录内所有路径均可在 `src/engine/config.py` 中调整；
  另可用 `src/engine/config.py` 顶部的 `DATA_DIR` 常量整体搬家。
- `.gitignore` 对本目录的规则是「除本文件外全部忽略」，
  因此请勿把需要入库的文件放到这里。
