# 社区配置现状与手动步骤

本文区分"已经生效"和"需要在 GitHub 网页上完成"。仓库当前仍是 **private**，本轮没有修改可见性。

## 已生效

| 项 | 状态 | 说明 |
| --- | --- | --- |
| Issue Forms | 已生效 | `.github/ISSUE_TEMPLATE/` 下 4 个表单与 `config.yml`，推送到默认分支后自动出现在 New issue 页 |
| PR 模板 | 已生效 | `.github/PULL_REQUEST_TEMPLATE.md` |
| 标签 | 已创建 18 个 | 名单见下；如需调整，在仓库 Labels 页手工维护 |
| Discussions | 已启用 | `has_discussions: true`，但分类需在网页端创建（见下） |
| 社区文档 | 已添加 | `CONTRIBUTING.md`、`CODE_OF_CONDUCT.md`、`SECURITY.md`、`SUPPORT.md` |

标签体系（18 个，分四组，不再扩张）：

```text
type:bug  type:feature  type:knowledge  type:tool-adapter  type:documentation
scope:universal  scope:tool-specific  scope:environment-specific  scope:project-specific
status:needs-triage  status:reproduced  status:confirmed  status:fixed  status:needs-feedback
priority:critical  priority:major  priority:minor  priority:usability
```

GitHub 自带的 `bug`、`documentation`、`enhancement` 等默认标签仍在，可按需手工清理。

## 需要手动完成：Discussions 分类

GitHub 的公开 API 不提供创建/改名讨论分类的接口（`Mutation` 类型中只有 `createDiscussion`、`updateDiscussion` 等，没有分类相关字段），因此以下步骤必须在网页端完成：

1. 打开 <https://github.com/QingFXQ/ArchDesigh-skill/discussions>
2. 点击分类栏右侧的铅笔图标（Edit categories）
3. 按下表调整。默认已有 Announcements、General、Ideas、Polls、Q&A、Show and tell：

| 目标分类 | 操作 | 说明 |
| --- | --- | --- |
| Announcements | 保留 | 版本公告 |
| General | 保留 | 项目交流 |
| Ideas | 保留 | 功能建议 |
| Architecture Practice | **新建** | 建筑设计经验、评图反馈、规范适用性讨论；建议 emoji `:building_construction:` |
| Workflow Showcase | 把 Show and tell **改名** | 用户工作流展示；保留原有格式 |
| Questions | 把 Q&A **改名** | 使用问题；必须保留 Q&A 格式，才能标记答案 |
| Polls | 删除 | 不在本轮分类体系内，避免分类膨胀 |

创建后把分类说明补成一句话，例如 "Architecture Practice：只谈设计判断与规范适用，不提 bug；bug 走 Issues"。

完成前，`SUPPORT.md` 与 `config.yml` 中的 Discussions 链接会指向一个只有默认分类的页面，不会报错。

## 需要手动完成：公开前的仓库设置

| 设置 | 位置 | 建议 |
| --- | --- | --- |
| Private vulnerability reporting | Settings → Code security | 公开后立即开启，`SECURITY.md` 依赖它 |
| Dependabot alerts | Settings → Code security | 开启；本轮未引入运行时依赖，风险主要在开发依赖 |
| Discussions 可见性 | Settings → General | 私有仓库下 Discussions 仅协作者可见，公开后自动对所有人可见 |
| 许可证 | 根目录 `LICENSE` | MIT 已生效，见 [licensing.md](licensing.md) |
| 仓库可见性 | Settings → General → Danger Zone | **本轮未改动**，由维护者决定 |

## 验证配置是否生效

```text
gh label list --limit 50 | grep -E '^(type|scope|status|priority)'
gh api repos/QingFXQ/ArchDesigh.skill --jq '{has_discussions,has_issues,visibility}'
gh issue list --limit 1        # 新建 Issue 时应能看到 4 个表单入口
```

Issue Forms 是 GitHub 的静态配置，不依赖额外服务；字段调整直接在 `.github/ISSUE_TEMPLATE/` 里改。

## 维护方式

分类、标签、仓库可见性与分支保护都在 GitHub 网页端手工维护。它们变化不频繁，不需要同步脚本或定期任务。
