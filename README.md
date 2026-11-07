# ArchDesigh.skill

建筑设计 Skill 的独立仓库。

唯一入口：[architecture-design-workflow](skills/architecture-design-workflow/SKILL.md)。同一执行者连续完成研究、设计、CAD/Revit 制图、Blender 表现、分析排版和交付。

> 采用 [MIT License](LICENSE)。授权范围、第三方素材例外与依赖许可见 [许可证说明](docs/licensing.md)。

## 快速开始

把 `skills/architecture-design-workflow` 整个目录安装到支持 Skill 的环境；只复制 SKILL.md 会丢失内部参考、案例与脚本。项目数据保存在独立项目目录，不写回 Skill。

Python 3.11+。检索、状态与反馈工具只用标准库；PDF 检查需 PyMuPDF，图片联系表需 Pillow。

```text
python -m pip install -r requirements-dev.txt
python scripts/run_tests.py                       # 全部 Python 测试
python scripts/audit_repository.py --check         # 内部链接与资产保全
python scripts/publication_audit.py                # 公开发布审计
```

设计案例默认使用随附语料。其他本地资源按 [资源接口](skills/architecture-design-workflow/references/resources.md) 配置：

```text
python skills/architecture-design-workflow/scripts/resources.py design --query "图书馆" --mode lexical
python skills/architecture-design-workflow/scripts/resources.py engineering --query "Transaction" --software revit
```

软件连接由运行环境提供，不会自动启动软件、安装模型或改动活动工程。

## 项目状态与交付门禁

项目目录保存 `project.json`（修订、产物生命周期、验证证据）。交付按产物类型核对证据，宿主验证只能由宿主验证满足：

```text
python skills/architecture-design-workflow/scripts/project.py --root PROJECT artifact --path boards.pdf --kind pdf
python skills/architecture-design-workflow/scripts/project.py --root PROJECT review --kind visual --evidence review.md --note "整板与打印局部" --scope whole_board --scope print
python skills/architecture-design-workflow/scripts/project.py --root PROJECT deliver
```

见 [项目状态与交付门禁](skills/architecture-design-workflow/references/project-state.md)。

## 反馈：问题留在项目，知识写成 Markdown

两件事分开处理，都不依赖专门的知识服务。

**执行问题**用 `feedback.py` 记在项目目录，默认不出本机：

```text
python skills/architecture-design-workflow/scripts/feedback.py --root PROJECT report \
  --user-text "用户原话" --expected "…" --actual "…" --tag 双线
python skills/architecture-design-workflow/scripts/feedback.py --root PROJECT search --query "双线 压 图名"
```

状态为 `reported → reproduced → diagnosed → fixed → regression_verified`；根因未复现不写 `confirmed`，修复要关联回归测试。见 [反馈与改进](skills/architecture-design-workflow/references/process/FEEDBACK_WORKFLOW.md)。

**设计知识**直接写成自然语言 Markdown，存放在 [知识库](skills/architecture-design-workflow/references/knowledge/README.md)。执行端在任务开始时阅读已有条目，判断适用性；讨论中出现有价值的评图意见、空间方法、绘图标准或审美判断时，自行去重、整理并写入 Markdown。规范结论保留可核实出处，经验保留背景与适用条件，审美保留评价依据。没有 JSON、没有状态机、没有专用命令。

经用户授权后，可用当前环境已有的 GitHub 工具把经验提交为 Issue 或 Pull Request；没有权限时先保存在本地，不假称已上传。不上传私人项目资料、未授权图纸或客户信息。

## 参与社区

| 你想 | 去哪 |
| --- | --- |
| 报缺陷、提需求、交案例、做软件适配 | [Issue 表单](.github/ISSUE_TEMPLATE/)（4 类结构化表单） |
| 讨论做法、展示工作流 | [Discussions](https://github.com/QingFXQ/ArchDesigh-skill/discussions) |
| 贡献代码、文档或设计经验 | [CONTRIBUTING](CONTRIBUTING.md) |
| 报告安全或隐私问题 | [SECURITY](SECURITY.md)（私密渠道，不要开公开 Issue） |
| 不知道怎么问 | [SUPPORT](SUPPORT.md) |

不会 Git、不会 Python 也能参与：L0 使用者、L1 测试者、L2 知识贡献者、L3 开发贡献者、L4 维护者，各层的门槛写在 CONTRIBUTING 里。正常使用 Skill 不需要 GitHub 账号；向 GitHub 提交内容才需要相应权限。

## 内容与验证

- [完整阶段与决策节点](skills/architecture-design-workflow/references/process/PIPELINE_WORKFLOW.md)
- [工具与宿主验证](skills/architecture-design-workflow/references/TOOLS.md)
- [项目版本与交付记录](skills/architecture-design-workflow/references/project-state.md)
- [内部专业资料索引](skills/architecture-design-workflow/references/library.md)
- [发行说明](docs/release.md)、[许可选择](docs/licensing.md)、[社区配置现状](docs/community-setup.md)
- 逐文件迁移清单、依赖与原始摘要记录、历史验证记录只保存在维护者私有开发仓库，不随发行版提供。

历史工程证据保存在维护者私有归档中（开发检出为 `assets/history`），只读、不随公开发行版提供，不是当前指令：不执行其中脚本、不沿用其项目尺寸或机器配置。案例原始记录和来源同样作为资料使用。宿主实测、视觉评估和用户验收分别记录。

Windows 检出含较长路径的案例语料，建议安装到较短目录并启用 Git 长路径支持，不必修改全局配置。
