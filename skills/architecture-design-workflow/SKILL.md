---
name: architecture-design-workflow
description: 建筑方案研究、迭代与制图交付。从任务书和场地建立约束、比较可编辑方案和关键空间、复核平立剖与真实模型；也可接续 Revit、CAD、Blender、SketchUp、展板或可编辑交付。适用于建筑设计任务和本技能维护。
---

# 建筑设计与图纸制作

从用户当前目标、阶段和已确认的设计依据接续。用真实可编辑模型检验空间、结构、功能、主要动线与场地。只读当前问题所需参考。

## 起点与授权

- 读取任务书、场地、PROJECT.md、原件和最新反馈。分列用户要求、任务书硬约束、适用规范、已确认决策、可探索范围、假设、待确认项和建议。按控制对象标注冲突与暂行口径。交图深度、纸幅、比例和源文件按当前任务确定。
- 阶段由成果成熟度决定，版本记录每次修订。核心概念、方案选择、重大取舍及阶段变更按用户确认或已记录授权。普通调整自行推进。用户要求先收集反馈或暂停时，整理当前证据，等授权后再修改依赖该决定的工作。见[阶段、约束和历史](references/stages.md)。
- 核实软件、活动文件、坐标、单位、至少三个分散参考点、北向和场地零点。每个活动原生文档一个写入者，保存可恢复的副本。涉及规范结论时查项目所在地区、适用版本和官方来源。

## 方案与校验

1. 结合基地和项目试排最重要的公共空间、剖面、主要动线、结构与分区。形式、功能及剖面都可作为起点。按具体问题复用既有案例成果。
2. 分开维护主体、各层控制线、虚空间、屋盖和内部功能。根据空间效果和容量双向调整，裁切后查真实面积、净宽、门洞、竖向接续和独立运营。先形成能比较的实质不同方向，数量和轮次由复杂度及授权决定。
3. 从同版真实模型取关键平剖和人眼序列，判断主次、尺度、围合、明暗、视线、停留和第五立面。分列自动检查、视觉观察、技术待验证和用户决定。候选足够或收益降低时提交证据和取舍，进入人工评审。
4. 在已确认深度内制作，源头变更同步受影响图纸、表现和指标。原生制作先验证代表区，版面先用同版真实图件核纸面容量。交付前看完整图、重要局部和跨图一致性。

## 按实际任务打开模块

| 任务 | 入口 |
| --- | --- |
| 项目状态、阶段、权限与回退 | [阶段与项目约束](references/stages.md) · `scripts/project_state.py` |
| 核心空间、形式原型、同条件横评 | [建筑创作与评审](references/spatial-review.md) |
| 独立主体、楼板、屋盖、房间预算与连接 | [几何与面积](references/geometry-area.md) · `scripts/design_check.py shell/layout` |
| 地形、概念土方、纵坡和返回路线 | [场地专项](references/site-terrain.md) · `scripts/design_check.py site` |
| 真实光照、历史模型重渲染或图像辅助 | [视觉实验](references/visual-studies.md) · `scripts/render_study.py` |
| 建筑案例、工程方法和原生资产 | [资源接入](references/resources.md) · `scripts/resources.py` |
| BIM／CAD 原生制作和故障恢复 | [原生制作](references/production.md) |
| 正式展板、字体、图形表达和可编辑交付 | [排版](references/presentation.md) · [可编辑交付](references/editable-delivery.md) |
| 已有公开版项目状态、产物门禁与反馈记录 | [项目状态](references/project-state.md) · [反馈流程](references/process/FEEDBACK_WORKFLOW.md) · `scripts/project.py` / `scripts/feedback.py` |
| 交付 QA 和反馈复验 | [检查与反馈](references/verification.md) · `scripts/check_layout.py` |

示例与测试见[使用说明](README.md)。平面近似与概念土方不能作为正式面积、工程或规范验收。以受控实际模型判断空间和相对光效。生图按需使用，真实图纸和模型提供可交付的建筑证据。

## 公开版工具与资料

按[完整流程](references/process/PIPELINE_WORKFLOW.md)、[资料索引](references/library.md)和[工具接口](references/TOOLS.md)选读随附案例、方法与宿主操作。用 `project_state.py` 记录设计阶段和版本决定。公开版的 `project.py` 继续负责产物登记、证据及交付门禁。产物按 `active`、`superseded`、`archived` 标记，只对当前有效产物取证。版本或内容变更后重新验证。按实际产物类型声明 PDF、DWG、RVT、BLEND、PSD 等检查，分列自动检查、实际看图、宿主验证和用户验收。

用 `feedback.py` 记录和复验项目故障。专业经验按[知识库说明](references/knowledge/README.md)直接积累为 Markdown，说明来源、适用条件和例外。对公开共享有明确授权时再提交；私人项目资料与未授权图件留在项目外部记录。
