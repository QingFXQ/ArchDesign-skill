# 获取帮助

## 先花一分钟自查

| 现象 | 先做什么 |
| --- | --- |
| 命令报错 | 看错误里的 `error` 字段；`python scripts/project.py --root 项目目录 status` 看当前状态 |
| 交付被拒绝 | 看 `deliver` 返回的 `errors`，每条都指明缺哪个验证或哪份证据失效 |
| 检索不到案例 | 确认 `--config` 或 `ARCH_LAYOUT_CATALOG` 指向的目录存在；缺失时工具会明说，不会假装检索到 |
| PDF 检查报错 | 装 `PyMuPDF`（`pip install -r requirements-dev.txt`）；没有它时纸幅检查不可用 |
| 想查看项目内的问题记录 | `python scripts/feedback.py --root 项目目录 list`；记录只在本地，不会自动上传 |

## 该去哪里问

| 你想 | 去处 |
| --- | --- |
| 问怎么用、怎么配置 | [Discussions → Questions](https://github.com/QingFXQ/ArchDesigh-skill/discussions)（未启用时用 Issue 的 Bug 表单并注明「使用问题」） |
| 报一个具体缺陷 | [Bug Report](.github/ISSUE_TEMPLATE/bug_report.yml) |
| 提一个能力需求 | [Feature Proposal](.github/ISSUE_TEMPLATE/feature_proposal.yml) |
| 贡献案例、经验、规范笔记 | [Knowledge Contribution](.github/ISSUE_TEMPLATE/knowledge_contribution.yml) |
| 适配新软件或新版本 | [Tool / Software Adapter](.github/ISSUE_TEMPLATE/tool_adapter.yml) |
| 报告安全或隐私问题 | [SECURITY.md](SECURITY.md)，走私密渠道 |

Issue 用于「可以修的具体问题」，讨论用于「还不确定是不是问题」。选错不会被打回，但选对能更快得到回应。

## 提问时请带上

- Skill 版本（`git log -1 --format=%h`）与使用的宿主软件版本。
- 发生阶段：任务书、概念、方案、施工图、表现、排版、交付。
- 你期望的结果与实际结果。
- 能否复现；能复现就给最小步骤。
- 相关截图或日志，**脱敏后**再贴。

## 不要这样做

- 不要在 Issue 里贴客户图纸、未公开方案、完整 RVT/DWG/PSD/PDF、聊天记录、密钥。
- 不要用 Issue 提交安全漏洞。
- 不要催促未回复的问题；维护者会在有能力时处理，重复催促会被合并或关闭。
- 不要把「我的方案更好看」当作缺陷报告；设计判断请走 Discussions 或知识贡献。

## 文档索引

- [README](README.md)：项目是什么、怎么装。
- [CONTRIBUTING](CONTRIBUTING.md)：怎么参与、怎么提 PR。
- [SKILL.md](skills/architecture-design-workflow/SKILL.md)：Skill 的唯一入口与执行要求。
- [项目状态与交付门禁](skills/architecture-design-workflow/references/project-state.md)：产物、验证、失效规则。
- [反馈与改进](skills/architecture-design-workflow/references/process/FEEDBACK_WORKFLOW.md)：项目问题的记录、生命周期与修复验证。
- [知识库说明](skills/architecture-design-workflow/references/knowledge/README.md)：设计经验如何用 Markdown 记录、检索和共享。
