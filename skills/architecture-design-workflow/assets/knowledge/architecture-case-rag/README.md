# Architecture Case RAG

Architecture Case RAG 是面向建筑设计问题的本地案例知识库。案例 Markdown 是唯一事实来源；检索以“问题相似度优先于类型相同”为原则，并保留来源、图纸质量和不可照搬条件。

案例数量、标签统计与索引状态由脚本生成，不在文档中写死。运行 `python3 scripts/build_index.py` 可获得当前案例数。

## 检索管线

```text
自然语言问题 → query normalization → section-level semantic retrieval
                                   + metadata/tag/keyword evidence
                                   → hybrid scoring → case aggregation
                                   → optional local LLM rerank
```

- `fast mode`：默认 semantic section retrieval（v1 Benchmark 的 Recall@5/MRR 最佳）；可显式 `--mode hybrid` 叠加 metadata/tag/keyword evidence。两者均使用本机 Ollama 的 `qwen3-embedding:0.6b`，不调用 LLM。
- `quality mode`：先取当前 semantic/hybrid Top 20，再让本机 LLM 复核最多 5 个案例的前三段证据；只在需要额外判断时使用。LLM 不可用时自动回退 fast 结果。
- `baseline`：保留既有 `problem/type/site/strategy/quality/keyword/year` 过滤与排序，用于兼容和 Benchmark。

每个可检索 section 都携带 `case_id/title/section/text/type/site/problem/strategy/quality/year`。15 个正文段落以及 summary 均可独立召回；“资料未提供”一类占位段落不会进入 semantic index。

## 使用

从仓库根目录运行：

```bash
# 初次或案例变化后：先建 metadata，再建 local embeddings
python3 knowledge/architecture-case-rag/scripts/build_index.py
python3 knowledge/architecture-case-rag/scripts/build_semantic_index.py

# 默认 fast semantic：自然语言是主要入口
python3 knowledge/architecture-case-rag/scripts/search_cases.py \
  --query "三层幼儿园如何让每个班级方便到达室外，同时避免长走廊" --max 8

# 输出可直接附入 概念至方案 的交接卡
python3 knowledge/architecture-case-rag/scripts/search_cases.py \
  --query "坡地文化建筑如何利用高差形成连续参观路径" --max 5 --format card

# 叠加明确类型与资料质量过滤
python3 knowledge/architecture-case-rag/scripts/search_cases.py \
  --query "坡地文化建筑如何利用高差形成连续参观路径" --mode hybrid --type museum --quality 4

# 可选 evidence rerank（本机 qwen3.5 模型）
python3 knowledge/architecture-case-rag/scripts/search_cases.py \
  --query "遗产工业建筑如何转化为公共文化空间" --quality-mode --rerank-top 5 --max 5

# 保留旧式可复现 metadata/keyword 检索
python3 knowledge/architecture-case-rag/scripts/search_cases.py \
  --problem indoor-outdoor --type kindergarten --quality 3
```

`--type`、`--site`、`--strategy` 是精确过滤；`--quality` 是最低星级；`--year-from/--year-to` 包含边界；`--keyword` 为全文 AND。`--query` 默认使用 section-level semantic，也可指定 `--mode hybrid`；结果会显示 evidence sections，而不是把整篇案例误当作相关。

## 标签与入库

- 受控词表：[`ontology/tags.json`](ontology/tags.json)
- 同义映射：[`ontology/aliases.json`](ontology/aliases.json)
- 仅预览旧标签可归一的提案：`python3 scripts/enhance_tags.py`
- 模板：[`templates/case-template.md`](templates/case-template.md)
- 入库流程：[`ingestion/README.md`](ingestion/README.md)

标签只协助召回，不能替代正文、图纸或来源。未知数字留空，正文写“资料未提供”；质量星级衡量证据完整度，不评价项目优劣。

## Benchmark

[`benchmarks/queries.json`](benchmarks/queries.json) 含人工定义的真实建筑问题、`must_hit`、强相关、可接受与反例。运行：

```bash
python3 knowledge/architecture-case-rag/benchmarks/run_benchmark.py --mode baseline
python3 knowledge/architecture-case-rag/benchmarks/run_benchmark.py --mode semantic
python3 knowledge/architecture-case-rag/benchmarks/run_benchmark.py --mode hybrid
python3 knowledge/architecture-case-rag/benchmarks/run_benchmark.py --mode rerank
```

输出 Recall@3/5/10、MRR、must-hit coverage 与 false-positive rate。选择默认模式必须依据结果，并回看 false positive/negative 的正文证据；检索结果始终需转成 `RAG_TRANSFER_CARD` 后交给 本项目设计，不向 Drawing 传递整篇案例。

运行 `python3 scripts/audit_case_quality.py --output benchmarks/results/case-quality-audit.json` 可审计四星以上案例是否登记 floor plan、section 与 photo；五星还必须有 site plan。该报告是数据修复队列，不会静默降低星级。
