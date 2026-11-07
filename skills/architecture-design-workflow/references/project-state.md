# 项目状态、产物版本与交付门禁

每个项目使用独立目录。保留 PROJECT.md/BRIEF.md 等现有设计依据；`project.json` 只记录修订、阶段、产物摘要、验证证据、用户原话和检查结论，不另起竞争的设计事实源。工具不能代替执行者的设计判断或用户决定。

使用脚本绝对路径运行，`--root` 可含空格和中文。命令中的 scripts 指本 Skill 内部 scripts 目录，PROJECT 是实际项目目录，不是仓库：

```text
python scripts/project.py --root PROJECT init --brief "任务书位置和交付范围"
python scripts/project.py --root PROJECT artifact --path boards.pdf --kind pdf
python scripts/project.py --root PROJECT require --check visual_print --artifact boards.pdf --status not_applicable --reason "本次只交电子版，不打印"
python scripts/project.py --root PROJECT review --kind visual --evidence visual-review.md --note "整板与打印局部" --scope whole_board --scope print
python scripts/project.py --root PROJECT review --kind host --check cad_reopen --artifact plan.dwg --evidence cad-log.txt --note "CAD 2024 保存后重开"
python scripts/project.py --root PROJECT check --layout layout.json --pdf boards.pdf
python scripts/project.py --root PROJECT decision --scope delivery --text "用户对当前版本的实际原话"
python scripts/project.py --root PROJECT deliver
python scripts/project.py --root PROJECT status
```

成功输出 JSON 到 stdout；被拒绝或参数错误退出码 2，错误信息 JSON 到 stderr。`init` 不覆盖已有状态。

## 产物生命周期

`artifact` 为每次登记生成独立 `id`，并写入 `status`：

| status | 含义 | 是否参与交付门禁 |
| --- | --- | --- |
| `active` | 当前有效产物 | 参与 |
| `superseded` | 已被新版本替代 | 不参与 |
| `archived` | 主动留档，不属当前交付 | 不参与 |

替代关系双向记录：旧行写 `superseded_by` 与 `superseded_reason`，新行写 `supersedes`。旧行的 `path`、`sha256`、`revision` 不修改也不删除，因此历史仍可追溯到具体文件和摘要。

新登记为 `active` 时自动替代：

- 同一路径的旧 `active` 行 → `replaced_by_newer_registration`。
- 其他修订下仍为 `active` 的行 → `revision_advanced`。
- `--supersedes` 显式列出的路径 → `superseded_by_declaration`。用于同一修订内换文件名（如 `draft.pdf` → `final.pdf`）。

命令回显 `superseded` 列表，替代不会静默发生。声明了未登记的路径会直接报错且不写状态。`checkpoint` 本身不替代产物：旧修订产物保持 `active` 并触发 `Stale artifact revision`，直到你在新修订重新登记或声明替代。重新登记即确认该文件仍属当前版本。

不允许删除旧行掩盖版本问题。需要把某个产物退出当前交付而不替换它时用 `archive`，原因必填，记录仍在，之后重新登记同名文件即产生新的 `active` 行：

```text
python scripts/project.py --root PROJECT archive --path spots.pdf --reason "用户撤下该板，本轮不交"
```

## 验证要求

`project.json` 的 `requirements` 保存显式声明，`validations` 保存证据。要求由三个来源决定，优先级从高到低：

1. 项目显式声明（`require`，可写 `required` 或 `not_applicable`）。
2. 产物 `kind` 的默认要求集。
3. 无默认要求时只保留通用视觉评审。

通用要求（所有 `kind`）：`automatic_check`（项目级）+ `visual_whole_board`。各 `kind` 追加：

| kind | 追加要求 | 证据通道 |
| --- | --- | --- |
| `pdf` | `visual_print` | 视觉评审 |
| `dwg` | `cad_reopen` `cad_layers` `cad_dimensions` `cad_editability` | 宿主验证 |
| `rvt` | `revit_reopen` `revit_objects` `revit_model_state` | 宿主验证 |
| `blend` | `blender_reopen` `blender_objects` `blender_scene` | 宿主验证 |
| `psd` | `psd_layers` `psd_text` `psd_placed` `psd_reopen` | 宿主验证 |

`visual_drawing_local` 与 `visual_cross_drawing` 不默认要求，需要时用 `require` 加到指定产物。PDF 的实际纸幅、布局、当前版本由 `check` 覆盖；PSD 的图层结构、文字可编辑、置入内容、保存重开由宿主验证覆盖。

`require --status not_applicable --reason "..."` 表示本任务不需要该验证，原因必填，交付报告会列出全部豁免。不要因为没装某个软件就默认不适用；只在该产物确实不需要这类验证时声明，并在原因里写清依据。

## 三条证据通道

| lane | 产生方式 | 能证明 | 不能证明 |
| --- | --- | --- | --- |
| `automatic` | `check` | 声明几何、实际纸幅、必要图件、声明比例 | 美感、模型正确、宿主可编辑 |
| `visual` | `review --kind visual` | 执行者实际看过的图与结论 | 用户验收、宿主操作 |
| `host` | `review --kind host` | 指定宿主中做过的具体操作 | 设计质量、规范合规 |

宿主验证只能来自 `review --kind host`，并且必须写明 `--check`、单一 `--artifact`、`--result passed|failed` 和项目内的证据文件。以下情况直接拒绝，不允许用自动检查冒充宿主验证：

- 证据文件名为 `automatic-checks.json`。
- 证据内容与任一自动检查报告摘要相同（改名副本）。
- `--check` 与产物 `kind` 不匹配，例如给 `pdf` 记 `cad_reopen`。

## 视觉评审证据

`review --kind visual` 记录 `revision`、`scopes`、`conclusion`、`artifacts`（路径 + `sha256` + `artifact_id`）与评审文件自身摘要。`--artifact` 可重复，一次评审可覆盖多个产物；省略时绑定当前修订全部 `active` 产物。评审对象必须是已登记的 `active` 产物。

`--scope` 取 `whole_board`、`drawing_local`、`print`、`cross_drawing`，省略时按 `whole_board` 记。`--conclusion` 取 `accepted`、`accepted_with_notes`、`needs_rework`，省略按 `accepted` 记；`needs_rework` 会阻止交付。评审范围写实际看过的部分，不要把局部检查记成整板。

## 失效机制

交付时重新计算，不依赖写入时的一次性清理；证据记录本身保留，因此失效可见、可追溯：

- 产物文件内容与会话记录不一致 → `Artifact changed`。
- 被评审或被验证的文件内容变化 → `reviewed file changed on disk`。
- 产物被替代或重新登记 → `artifact superseded` / `artifact re-registered`。
- `check` 所用输入（layout、PDF）变化 → `Checked input changed`。
- 评审文件自身变化 → `review evidence changed`。
- 修订变化但证据仍在旧修订 → `recorded for revision R1`。

所以修改图件后必须重新看图、重新做宿主验证、再交付；仅重新登记不够。

## 交付判定

`deliver` 依次核对：存在 `active` 产物且内容与修订一致；项目级 `automatic_check` 有效并通过；每个产物的每条要求都有当前修订的有效证据，或有不适用声明；本修订存在 `scope=delivery` 的用户决定。任一项不满足即 `{"delivery":"blocked"}`，退出码 2，并列出全部 `errors`。

通过时返回 `validated`（逐项证据 id）、`waived`（豁免项与原因）、`warnings`、`active_artifacts`、`superseded_artifacts` 与 `archived_artifacts`。`host_integrations` 字段只是声明边界：离线检查不验证任何设计软件。

它不检查自然语言原话真实性、规范合规或宿主运行；执行者必须如实登记，不得把 `automatic` 结果写成 `host`。

## 状态与兼容

`status` 返回完整状态，附加 `gate_summary`（当前门禁的错误、警告、豁免与已满足项），不改写文件。

`schema_version` 当前为 2。旧版 `schema_version: 1` 项目读取时自动迁移：旧 `reviews.automatic` 转为 `automatic` 证据，旧 `reviews.visual` 转为 `visual` 证据并绑定当时修订的产物，旧 `reviews.host` 只保留为历史（`legacy_host_review`，不满足任何要求）。迁移记录标 `legacy: true`，交付报告照实显示；旧记录只在被绑定文件变化或产物重新登记时失效。迁移后的状态在下次写入时落盘。

一个项目目录只由当前执行者顺序更新，避免并发写覆盖。
