# 反馈与改进

本文件只处理**项目执行中的问题**：工具报错、交付门禁失败、图纸返工、反复修正。专业设计经验的积累不走这里，见 [知识库说明](../knowledge/README.md)。

## 什么时候记录

- 工具异常退出、脚本报错、宿主操作失败。
- 交付检查或视觉评审发现真实缺陷。
- 同一问题被用户反复指出，或需要大量人工介入才恢复。
- 已经修好、但值得防止复发的问题。

正常方案迭代、用户改变偏好、方案比较、项目本身的特殊要求，不记为缺陷。

## 状态

```text
reported → reproduced → diagnosed → fixed → regression_verified
```

暂时不修的留 `pending`；只属于当前项目的记 `project_specific`；不成立或重复的记 `rejected`。三者都要写原因。

根因只有在当前修订复现并附证据后才能写 `confirmed`，否则写 `suspected` 或 `unknown`。修复要关联至少一个可运行的回归测试才算 `regression_verified`。

## 命令

```text
python scripts/feedback.py --root PROJECT report --user-text "用户原话" \
  --expected "…" --actual "…" --artifact boards.pdf --evidence shot.png --tag 双横线
python scripts/feedback.py --root PROJECT reproduce --id FB-0001 --note "第 1 页复现"
python scripts/feedback.py --root PROJECT diagnose --id FB-0001 \
  --root-cause-status confirmed --root-cause "标题带高度小于字形" --evidence shot.png
python scripts/feedback.py --root PROJECT fix --id FB-0001 --summary "标题带增加 2mm" \
  --commit 3f2a91c --regression-test "tests/test_delivery_gates.py::LayoutTitleBand"
python scripts/feedback.py --root PROJECT verify --id FB-0001 --result passed
python scripts/feedback.py --root PROJECT search --query "双横线 压 图名"
```

记录存放在项目目录的 `feedback.json`，不写进 Skill。`status`、`list`、`show` 用于查看；`link --duplicate-of` 关联重复问题；`mark` 处理 `pending`、`project_specific`、`rejected`。

## 边界

- 单次项目的尺寸、纸幅、作品名、教师偏好留在项目记录，不升级为通用规则。
- 修复工具缺陷后补回归测试；流程缺陷更新对应流程文档。
- 不自动改写 `SKILL.md` 或删除既有规则；通用化必须经维护者确认。
- 不上传私人项目资料、未授权图纸或客户信息。

## 与知识积累的分工

本文件回答“哪里坏了、怎么修、如何防止复发”。值得跨项目复用的设计判断——空间组织、绘图标准、评图意见、审美、失败修正——直接写成 `references/knowledge/` 下的 Markdown，由执行端自行阅读、整理和共享，不需要经过 `feedback.py`，也不需要 JSON 或专用脚本。
