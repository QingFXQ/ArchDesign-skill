# 阶段、约束和历史

## 更新项目条件

沿用已有项目记录，需要时用[简短模板](../assets/PROJECT.template.md)。一条内容如果会改变设计、模型或出图，就用一两句写当前要求和采用依据。特别容易误读的数字附任务书页、条文、原图或确认日期；项目意见按意思准确概括。

同一事项按时间更新。例如新批注改变面积区间，就替换该项，检查当前模型参数与校验是否还在用旧值；与它无关的设计条件继续适用。适用法规和规划条件查现行依据。原任务书和旧方案可查阅，上一版采用的形体和尺寸随本轮方案需要重新选择。

## 阶段、版本与决定

项目选择适合自己的阶段和门槛。课程的一草通常要能讨论形式、空间、场地和基本可行性，证据是代表平剖、白模和面积差异。二草落实净空间、结构、门窗、竖向、材料和技术条件。三草及后续按任务深化构造、场地和交付。需要用户决定的核心取舍集中用图面沟通，写下采用的结论。已授权的草模、试深化、画图和排版可连续推进。

局部调整、错误修复和技术校核在授权范围内完成。候选已经能比较、关键审美或专业条件需要决定、修改无明显收益、已完成阶段目标或用户暂停时，提交现状、未决和证据。暂停是项目状态。等待反馈时可整理授权范围内现有成果。

## 已采用阶段工具的项目

需要接续现有版本索引时，可使用这些命令。

    python scripts/project_state.py design-state.json init concept develop detail
    python scripts/project_state.py design-state.json record concept --note "首轮剖面方案" --artifact concept/V1/section.pdf
    python scripts/project_state.py design-state.json record concept --note "补场地入口"
    python scripts/project_state.py design-state.json pause --note "等待教师反馈"
    python scripts/project_state.py design-state.json check

恢复使用 `resume --note ... --approved-by ... --basis ...`。转阶段用 `record` 加同样的决定参数。`--source concept/V1` 可从旧版本另存，分别保留当前时间线的 parent 与采用的 source。阶段内编号独立。`--artifact` 记录独立版本输出，共用输入写项目记录。脚本校验顺序与授权字段，真实审批由执行者记录。脚本只写索引，建筑输出由制作者另存。遇到锁提示，确认无写入者后处理遗留锁。

## 历史与回看

每个可比较方向保留真实模型、平剖、指标口径、取舍和未决条件。选回早期方案后，把后续验证过的面积、建模和校验方法带入新工作副本。评图见[建筑创作与评审](spatial-review.md)。
