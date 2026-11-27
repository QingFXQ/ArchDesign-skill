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

## 4. 在设计中使用案例库

从[案例工具](../assets/knowledge/architecture-case-rag/README.md)或[本地资源](resources.md)查当前要解决的问题，例如滨水场地如何连续到达、楼梯剖面如何表达平台、横向图册怎样放长剖面。按实际图面筛选候选，打开来源页的总图、平剖或完整图页。图册关注整套阅读节奏，照片只能支持实际看得到的内容。

保留原图或原始链接与出处，写几句可复用的做法、使用条件和当前项目怎样试。把方法落到实际模型、图纸样张或版式预案，再决定是否采用。已有工程项目使用检索回溯时可附检索工具原输出。

## 5. 维护现有索引时

以下字段与流程用于正式维护带索引的案例语料。项目查图和日常案例笔记按上一节组织。

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
