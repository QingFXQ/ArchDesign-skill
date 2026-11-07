# Architecture Case RAG 使用与扩充策略

Architecture Case RAG 是面向建筑设计问题的结构化案例库。它的职责是提供可追溯的案例证据和可迁移的方法，帮助 概念设计与 方案深化作判断；它不替用户选择概念，不把案例形式复制成项目方案，也不把资料缺口伪装成事实。

## 1. 目录与当前边界

```text
knowledge/architecture-case-rag/
├── cases/       Markdown 案例（运行 build_index.py 获取当前数量）
├── index/       cases.json 与 semantic-sections.json 派生索引
├── ontology/    canonical tags 与 alias 映射
├── benchmarks/  人工 ground truth 与 A/B runner
├── ingestion/   验证、入库与 source queue MVP
├── scripts/     建索引、semantic retrieval、检索与测试脚本
├── sources/     gooood 与国际来源清单
├── templates/   case-template.md
└── README.md    命令、字段与问题优先检索说明
```

每个 `cases/*.md` 是一个独立、可引用的案例单元。metadata 索引由 `scripts/build_index.py` 生成，section-level vector 索引由 `scripts/build_semantic_index.py` 通过本机 Ollama 生成；`scripts/search_cases.py` 默认按自然语言 query 运行 fast semantic retrieval（可显式 `--mode hybrid`）。它们不是云端向量数据库或自动设计系统，不能替代来源核验和设计转译。

## 2. 案例记录格式与阅读顺序

每个文件以 YAML front matter 开始，至少包括：唯一 `id`、中英文标题、建筑师、年份、地点、面积、层数、`type`/`site`/`strategy`/`problem` 标签、`quality`、带访问日期的 `sources`、图面 URL 与一句 `summary`。正文按因果链记录：

> 初始条件 → 核心问题 → 设计意图 → 概念/体量 → 总图 → 功能 → 平面 → 剖面 → 立面形体 → 流线 → 尺度 → 室内外 → 可学手法 → 可迁移条件 → 不可照搬内容

实际使用时先读 front matter 和第 2、13—15 节判断相关性；只有相关时才读第 1、4—12 节并摘录证据。任何“资料未提供”都表示资料边界，不能用常识、照片或类似项目补写成该案例的事实。

## 3. 受控词表策略

标签是检索入口，不是结论。优先复用已出现、语义稳定的英文短横线标签；新标签仅在现有词无法准确表达时新增，并在同一批入库中统一拼写。

| 字段 | 作用 | 示例 |
| --- | --- | --- |
| `type` | 建筑类型/使用制度 | `museum`、`kindergarten`、`school`、`library`、`cultural-center`、`apartments`、`housing`、`office` |
| `site` | 场地/城市条件 | `mountain`、`urban-infill`、`hillside-city`、`suburban`、`campus`、`village` |
| `strategy` | 空间或组织机制 | `courtyard`、`landscape-integration`、`urban-grid`、`repeating-bays`、`loop-circulation`、`sunken-space` |
| `problem` | 需要解决的具体矛盾 | `topography`、`play-learning`、`indoor-outdoor`、`urban-character`、`views`、`public-service` |

标签不能替代正文证据。例如 `courtyard` 只说明案例与庭院有关，不能据此断言庭院尺度、流线或气候性能。检索时结合标签、项目类型、地形/城市条件和正文关键词；输出时写明命中的是哪个问题、哪些图面或原文支持、哪些仍未知。

## 4. 检索工作流

可先按 `knowledge/architecture-case-rag/README.md` 运行命令行检索。自然语言 `--query` 是首要入口：先按章节语义召回，再结合 metadata/tag/keyword 证据混合排序并聚合案例；`--problem` 保留 AND 语义作为 baseline/精确过滤。随后仍须按以下流程阅读正文证据。

1. **把设计请求改写为检索问题。** 例如“博物馆要有气质”无效；“有 4 米高差的文化建筑如何同时组织连续参观、无障碍和后勤”可检索。
2. **列出过滤条件。** 先选 `type`，再选最影响方案的 `site`、`strategy`、`problem`；要求尺度/剖面证据时把 `quality` ≥★★★★ 作为优先条件。
3. **做两层召回。** 第一层从 front matter 找 3—8 个候选；第二层在正文检查第 1—12 节是否真正回答问题，并看 `images` 中是否有对应图面。不要因项目知名或照片好看就保留。
4. **按证据强度排序。** 优先有原始来源、平面/剖面/总图、关键尺寸和清楚适用条件的案例；摄影和宣传文字为主的案例只作氛围、语境或问题定义参考。
5. **输出转译卡。** 每个保留案例都写：案例事实与来源、所解决的矛盾、可迁移操作、适用前提、对本项目的验证图面、不能照搬的条件。只给“案例清单”不算检索完成。
6. **回写项目事实源。** 概念设计/方案深化将被采用的方法写入 `DESIGN_THESIS.md` 的操作矩阵，并把案例 ID、来源和版本登记在对应 Issue；案例不等于用户已批准决定。

## 5. 扩充流程

1. 先创建“为什么需要此案例”的研究问题，避免按风格或热度收集。
2. 优先原建筑师/业主、正式出版物和可追溯项目页；可用 gooood、ArchDaily、Divisare 等作项目入口，但保留原 URL 与访问日期。
3. 从 `templates/case-template.md` 复制字段，填写已证实的元数据与图面 URL；未知数字留空，正文明确写“资料未提供”或“基于照片推断”。
4. 至少完整填写核心问题、概念到总图/功能/平剖的链、流线、尺度、迁移方法和不可照搬项。若来源不足，降低质量等级而不是补造细节。
5. 使用既有词表标注；新词先检查是否与旧词同义。提交前检查 `id` 唯一、链接可访问、访问日期存在、图片 URL 不等于图片版权转移。
6. 新案例先作为候选入库，再核查字段和来源；涉及关键案例、低证据推断或方法深解时，深入复核。质量复核未通过的案例不得作为方案尺度或规范依据。

## 6. 来源与图像规范

- 每一条事实都能回到 `sources.name`、URL、访问日期和正文位置；案例二手摘要只能说明其实际提供的内容。
- 引用建筑师概念时使用可追溯原文并标识为引述；设计者自己的解释单列为“解释/可迁移方法”。
- 不下载或再分发图片时，保存原始 URL 及用途；使用图片进入课程成果前，按课程与来源的版权/署名规则确认。
- 不把案例的法规、尺度、结构或运营安排外推为本项目结论。它们必须经本项目场地、任务书、规范自查和用户 Gate 验证。

## 7. 质量分级与使用权限

| 等级 | 资料状态 | 可用于 | 不可用于 |
| --- | --- | --- | --- |
| ★★★★★ | 总图、平面、剖面、摄影和完整分析齐全 | 深入组织、平剖和尺度对照 | 直接复制方案 |
| ★★★★ | 主要平面、剖面、摄影齐全 | 空间/流线方法和受限尺度参考 | 代替本项目验证 |
| ★★★ | 有部分关键图纸或可核实分析 | 问题与局部方法参考 | 断言完整平剖、结构或尺寸 |
| ★★ | 主要摄影和文字 | 氛围、语境、研究候选 | 平面、剖面、尺度、后勤等具体结论 |
| ★ | 仅灵感线索 | 后续研究待办 | 任何正式设计证据 |

最终原则：案例库的价值在于让“为何这样做”有可追溯的比较对象；**不应该机械照搬**案例形式、尺度、流线或立面，它从不授予复制形式或跳过用户 Gate 的权利。
