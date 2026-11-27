# Architecture Design Workflow

调用 `$architecture-design-workflow`，提供实际项目目录、任务书／场地、最近确认的方案、当前目标与授权范围。先看 [SKILL.md](SKILL.md)，从当前设计、制图或排版问题接续。优先寻找完整案例原图，将具体做法试到自己的草模或图面；现行条件可用[简短项目记录](assets/PROJECT.template.md)更新。

## 第一次试用

以下命令从本 Skill 目录执行。输出路径可改为你的项目工作目录。阶段、场地和离线检索使用 Python 3.10+ 标准库；几何和面积另需 Shapely 2.1+。在现有环境安装需要的可选库即可。

    python scripts/project_state.py study-state.json init concept develop
    python scripts/project_state.py study-state.json record concept --note "研究首层入口和上层挑空"
    python scripts/design_check.py shell assets/office-study.json --report office-shell.json
    python scripts/design_check.py layout assets/office-study.json --mode accept --report office-area.json
    python scripts/design_check.py site assets/site-study.json --report site-study-report.json

先把小办公楼样例分解为独立楼层、房间预算、与上层对应的梯间和屋盖，再换成项目实际数据。`shell`、`layout` 可分别运行。布局迭代可用 `--mode explore`。项目采用确认方案后以 `accept` 查明示约束，再看实模和剖面、核专业需求。场地与路径有实际问题时启用 `site`；大部分项目不必建立参数化地形。

需要可编辑三维草模时运行下列命令，或使用项目已有三维工具。Blender 实际输出为网格集合。

    blender --background --python-exit-code 2 --python scripts/blender_shell.py -- office-shell.json office.blend

[视觉实验](references/visual-studies.md) 提供 Blender 比较与自然光变元输入。生图、Revit／CAD、正式排版和 PSD 各按需求选择，无需同时启用。案例与工程资产复用原有配置，见[资源接入](references/resources.md)。

## 验证与维护

    python -m unittest discover -s scripts -p "test_*.py"
    blender --background --python-exit-code 2 --python scripts/smoke_blender.py

第一条需要 Shapely 2.1+ 执行几何测试；既有可选的真实 PDF 和接触图用到 PyMuPDF 与 Pillow。第二条为独立 Blender 后台烟测，也可在已有 bpy 的相容 Python 中直接执行。离线、模型宿主、真实图面和设计决策四种检查分别记录。

[真实项目审计和后续计划](references/practice-audit.md) · [变更记录](CHANGELOG.md)
