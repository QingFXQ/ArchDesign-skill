# 阶段、约束和历史

## 接续依据

沿用项目已有 PROJECT.md。缺项较多时使用[项目记录模板](../assets/PROJECT.template.md)。按控制对象说明场地来源、轮廓和冻结项、各层平面、标高、结构、流线、出图依据和最新有效批注。

任务书原文、用户要求、规范条款、确认决策、探索自由度、假设、未决项和建议单列。冲突记录列出原数值及口径、谁能决定、暂行值和适用范围。例如净面积与总建筑面积冲突时，保留原要求，另登记暂行净面积底线和理由。

## 阶段、版本与决定

项目选择适合自己的阶段和门槛。课程的一草通常要能讨论形式、空间、场地和基本可行性，证据是代表平剖、白模和面积差异。二草落实净空间、结构、门窗、竖向、材料和技术条件。三草及后续按任务深化构造、场地和交付。一次修改只增加当前阶段的版本。转阶段、回退及核心概念取舍须有用户决定或预先授权并记录出处。

局部调整、错误修复和技术校核在授权范围内完成。候选已经能比较、关键审美或专业条件需要决定、修改无明显收益、已完成阶段目标或用户暂停时，提交现状、未决和证据。暂停是项目状态。等待反馈时可整理授权范围内现有成果。

## 快速记录

    python scripts/project_state.py design-state.json init concept develop detail
    python scripts/project_state.py design-state.json record concept --note "首轮剖面方案" --artifact concept/V1/section.pdf
    python scripts/project_state.py design-state.json record concept --note "补场地入口"
    python scripts/project_state.py design-state.json pause --note "等待教师反馈"
    python scripts/project_state.py design-state.json check

恢复使用 `resume --note ... --approved-by ... --basis ...`。转阶段用 `record` 加同样的决定参数。`--source concept/V1` 可从旧版本另存，分别保留当前时间线的 parent 与采用的 source。阶段内编号独立。`--artifact` 记录独立版本输出，共用输入写项目记录。脚本校验顺序与授权字段，真实审批由执行者记录。脚本只写索引，建筑输出由制作者另存。遇到锁提示，确认无写入者后处理遗留锁。

## 历史与回看

每个可比较方向保留真实模型、平剖、指标口径、取舍和未决条件。选回早期方案后，把后续验证过的面积、建模和校验方法带入新工作副本。评图见[建筑创作与评审](spatial-review.md)。
