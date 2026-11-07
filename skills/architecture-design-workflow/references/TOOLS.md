# 工具接口与宿主验证

当前执行者先发现环境里真实可用的专用连接、CLI/API或宿主脚本，读取实时工具说明，不把历史工具名、端口、版本与盘符当作当前事实。UI用于实际看图与必要交互。

| 工具 | 接口与输入 | 成功证据 | 失败处理 |
| --- | --- | --- | --- |
| 案例检索 | `scripts/resources.py design --query ... --mode lexical/auto/semantic/hybrid` | JSON结果、实际模式、原案例路径与来源 | auto记录语义失败并回退；显式语义失败不降级冒充 |
| 工程方法 | `scripts/resources.py engineering --query ... --software revit/cad/all` | 实际内部文档路径和命中行；可选外部目录 | 配置外部目录时严格核路径，不自动重建 |
| 原生族库 | `scripts/resources.py revit --query ... --revit 实际年份` | 外部工具查询结果和类型/文件 | 未绑定数据库或查询器明确失败；不静默创建空库 |
| CAD | 环境提供的连接或宿主脚本；文档路径、单位、图层、块、坐标 | DWG重开、图层/块与尺寸查询、PDF视觉对照 | 不以SVG冒充DWG；无宿主时标记未验证 |
| Revit | 环境连接；活动文档、宿主年版、恢复点、原生对象范围 | 提交后独立回读对象/参数/警告/保存，导出平剖三维 | Pending/超时先查事务和模态，有限诊断，不重放写入 |
| Blender | 环境连接或本机Python；同版几何、坐标、稳定ID、机位 | 对象核查、保存重开、真实渲染及图纸一致 | 导入失败保留源；不让图像生成填补缺失几何 |
| PDF/排版 | `scripts/check_layout.py layout.json --pdf boards.pdf` | 实际纸幅、边界、比例和碰撞报告，整板查看 | 自动报告不证明美感与字体完整 |
| PSD | Photoshop/相应宿主；文字/置入/蒙版代表小样 | 保存重开后修改文字、替换图像、检查图层与PDF一致 | 未实测标记未验证，不能以扁平图冒充可编辑源 |
| 项目状态与交付门禁 | `scripts/project.py --root … artifact/require/review/check/deliver/status` | `project.json` 的产物 id、替代关系、证据摘要与门禁报告 | 返回 `blocked` 时按 `errors` 补证据或补声明；缺宿主验证不会自动通过 |
| 反馈与经验 | `scripts/feedback.py --root … report/search/fix/verify/lesson` | 项目 `feedback.json` 的完整记录、状态流转、回归关联与审核结果 | 未验证经验不写回 Skill；工具只记录，不改写文档 |

[Revit MCP只读探测](../scripts/revit-mcp/scripts/smoke_revit_mcp.py) 保留作为可选工具，运行前读其 `--help` 并指定当前机器配置；历史验证见配套文档。具体写入须使用当前环境的宿主接口，不依赖该探测脚本完成设计。

本仓库持续集成仅验证离线工具、真实案例检索和合成项目PDF链；不证明上述设计软件已经连接。宿主实测记录应包含版本、活动文件、操作范围、前后证据、保存重开与限制。
