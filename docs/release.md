# 公开发行版说明

本仓库是 ArchDesigh.skill 的**公开发行快照**。它从维护者的私有开发仓库按白名单构建，使用独立的 Git 历史，不包含旧提交、旧 LFS 对象或私人工程资产。

## 包含什么

| 内容 | 路径 |
| --- | --- |
| Skill 唯一入口与全部专业参考 | `skills/architecture-design-workflow/`（`SKILL.md`、`references/`、`assets/knowledge/`、`assets/templates/`） |
| 项目状态与交付门禁 | `skills/architecture-design-workflow/scripts/project.py` |
| 问题记录与改进 | `skills/architecture-design-workflow/scripts/feedback.py` |
| 专业知识库 | `skills/architecture-design-workflow/references/knowledge/`（Markdown） |
| 检索与检查工具 | `check_layout.py`、`resources.py`、案例 RAG 脚本 |
| 社区文件与 Issue 表单 | `CONTRIBUTING.md`、`CODE_OF_CONDUCT.md`、`SECURITY.md`、`SUPPORT.md`、`.github/` |
| 测试与 CI | `tests/`、`.github/workflows/test.yml` |
| 许可证 | `LICENSE`（MIT）、`docs/licensing.md` |

案例语料（128 条中文摘要 + 来源链接 + 检索索引）随发行版提供，图片仅保留外链，不转载原文或图片本体。

## 不包含什么

| 内容 | 原因 |
| --- | --- |
| `assets/history/` | 真实课程作业与工程文件（含 RVT 模型、图册、评图记录），属于私人过程证据 |
| `audit/` 下的迁移、依赖与检查报告 | 含本机目录结构，且只对私有仓库的迁移历史有意义 |
| `docs/open-source-audit.md` | 私有仓库的公开审计记录，含不可公开的项目细节 |
| `.gitattributes` 中的 LFS 规则 | 只服务于被移除的历史模型 |
| 任何凭据、密钥、私人配置 | 从不入库 |

## 缺少私人素材时会怎样

- **案例检索**：随发行版提供 `index/cases.json` 与语义索引，默认 `resources.py design` 可直接使用。
- **工程资产与 Revit 库**：属于外部本地资源，按 `references/resources.md` 用 `~/.codex/architecture-resources.json` 配置；未配置时相关命令报“资源未配置”，不影响设计流程与文档读取。
- **历史工程证据**：不参与任何运行时逻辑，缺失不影响 Skill 执行，也不影响测试（`test_package.py` 在没有历史目录时跳过保全校验）。
- **专业知识库**：初始为空，Agent 直接读 Markdown；没有条目时按通用设计方法与现行规范工作，不影响设计流程。

## 安装

```text
git clone <this-repo>
# 把整个 skills/architecture-design-workflow 安装到支持 Skill 的环境
python -m pip install -r requirements-dev.txt
python scripts/run_tests.py
python scripts/audit_repository.py --check
```

只复制 `SKILL.md` 会丢失参考、案例和脚本。

## 如何重建发行快照

维护者在私有开发仓库执行：

```text
python scripts/build_release.py --out ../ArchDesigh-public --check
```

构建器按白名单复制文件，跳过上表“不包含”的内容，写出 `RELEASE-MANIFEST.json`（逐文件 SHA256），并在 `--check` 模式下拒绝任何私有路径、凭据或超限文件。快照目录随后执行 `git init` 建立独立历史。

## 已知状态

- 采用 MIT License，见 [LICENSE](../LICENSE) 与 [licensing.md](licensing.md)。
- 当前发行快照尚未创建远程仓库，也未改变原仓库可见性。
