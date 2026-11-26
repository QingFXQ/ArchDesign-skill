# 检查、失败样例与反馈

方案阶段可配合[几何与面积校验](geometry-area.md)记录面积、房间与开口问题。跨版归档和受控实模渲染见[建筑创作与评审](spatial-review.md)和[视觉实验](visual-studies.md)。

## 工具输入与证据边界

`scripts/resources.py`把设计方法、工程操作与原生资产的既有只读工具接到同一skill：配置缺失、工具缺失或库根不一致时报错，不重建库；原生查询要求提供宿主年份。自动连接检查和查询成功不等于已采用案例或已在Revit载入资产。设计检索当前实际是lexical还是semantic须保持原工具标记。

`scripts/cases.py`只读案例索引，匹配关键词并按需生成等比不裁切联系表，每页最多12张。需要Pillow才生成图片；单纯检索只用Python标准库。默认不选“排除”，显式ID可读取任意记录；状态、完整性和图幅均标为索引声明，不冒充本轮视觉复核。未知ID、重复ID、打不开的图明确失败。

`scripts/check_layout.py`只需标准库；加`--pdf`需PyMuPDF。它检查声明布局几何及实际PDF纸幅，不会检查PSD图层、字体字形、画风或建筑。配置文件可使用任意真实纸幅，不固定A1。命令中使用本skill内部脚本的实际路径。

最小输入示例：
```json
{
  "paper_mm": [594, 841],
  "min_text_mm": 2.5,
  "required_items": ["main", "F1", "F1-title"],
  "pages": [{
    "items": [
      {"id": "main", "role": "hero", "rect_mm": [8,8,578,296]},
      {"id": "F1", "role": "drawing", "rect_mm": [8,330,240,280],
       "source_frame_mm": [240,280], "source_scale": 300, "claimed_scale": 300},
      {"id": "F1-title", "role": "caption", "rect_mm": [8,615,240,7], "text_height_mm": 5}
    ]
  }]
}
```
这里的纸幅、字高、比例仅为合成用例，不是全项目默认。位置单位mm、原点左上、矩形为x/y/宽/高。`source_frame_mm`为注册好的整个源图边界（含同样标注边距），不能混用建筑实体宽高。旋转90/270度会交换源框宽高。`pixels_after_crop`为对应放置方向的有效裁切像素，不是整张未裁原图像素。`min_raster_ppi`由输出要求决定，低于目标给提示，不自动宣布不可打印。

标题／图形等矩形重叠默认报错，合法叠加在任一对象`allow_overlap_with`列出对方ID，不用全局禁用碰撞。双横线可另建对象矩形；其位置需要实际文字边界和图面核验，不能只凭预留框判没有压字。

`expected_revision`按需核当前版本；未声明的源给提示，声明不同则报错。`hero_min_fraction`只在该板明确有占比要求时设，不要求每板都有主图。`required_items`核交付图件是否出现；源图片含几张图不自动计成多个必交图。

`automatic_checks: passed`只说明已声明并可检查的条件没有发现错误。warnings保留未知和低质量线索，不升级“完整通过”。真实PDF字号、字形、色彩、完整范围和全部图件仍必须渲染查看。

## 四类状态

| 状态 | 登记方式 | 不能推导 |
| --- | --- | --- |
| 自动检查通过 | `project.py check` 写入 `automatic` 证据 | 美感、建筑正确、宿主可编辑、用户接受 |
| 执行者视觉评估通过 | `project.py review --kind visual`，含范围与结论 | 用户已确认或规范合规 |
| 宿主验证通过 | `project.py review --kind host`，含具体检查项与证据 | 设计质量、规范合规、自动检查已通过 |
| 用户确认通过 | 对具体版本／风格／范围的明确反馈 | 不同图件或新修订自动通过 |
| 尚未验证 | 明确缺少对象、工具或实测 | 不能用历史成功补填 |

四类互不替代：自动检查不能填宿主验证，宿主打开成功不代表图面正确，用户认可风格不代表所有图件正确。`project.py deliver` 按证据通道分别核对，`host` 项只能由宿主验证满足；PDF 的纸幅与布局由 `automatic` 项覆盖，打印局部由 `visual` 的 `print` 范围覆盖。

## 评审范围与失效

视觉评审必须写清实际看过的范围，并按图件绑定摘要：

```text
python scripts/project.py --root PROJECT review --kind visual --evidence review.md \
  --note "整板、打印局部与两图一致性" --scope whole_board --scope print --scope cross_drawing \
  --artifact boards.pdf --artifact section.pdf --conclusion accepted_with_notes
```

范围取 `whole_board`（整板）、`drawing_local`（图纸局部）、`print`（打印效果）、`cross_drawing`（多图一致性）。结论取 `accepted`、`accepted_with_notes`、`needs_rework`；`needs_rework` 会阻止交付。省略 `--artifact` 表示本次评审覆盖当前修订全部有效产物，被覆盖的每个文件都记录 SHA256。

图件被修改、替换或重新登记后，原评审与宿主验证立即不再支持交付（`reviewed file changed on disk`、`artifact re-registered`），必须重新看图与重新实测。工具保留旧证据而不删除，失效状态在交付报告中可见。

## 失败样例作为回归依据

| 具体失败 | 应采取的动作 | 复验 |
| --- | --- | --- |
| 单面窄版、重复180度 | 核分层轮廓、共享变换及锚点 | 对照真实源平立轴测；不是重放生成器 |
| 工字柱／柱墙脱节 | 功能尺寸→结构概念→轴网及工程样板 | 原生代表平剖、实际连接；截面不冒充计算 |
| 外墙像开门、窗不能切墙 | 分符号显示、真门和族切洞机制 | 门窗原位平立三维及洞口 |
| 二层梯段“存在但看不见” | 查墙遮挡、平台、裁剪与楼层接通 | 沿行走方向真实剖面 |
| AI加桌加玻璃或漏门 | 比较当前底图与生成结果 | 模型、图纸和相机对应；不只修照片 |
| 总平出口被AI挪位 | 用真实正投影几何；只用允许材质 | 世界坐标→像素→纸面位置与箭头 |
| 双横线压图名 | 标题带与实际字形留距 | 最终打印局部；碰撞检查作辅助 |
| 整板像图片拼盘 | 回真实图件预案，重做主次与图组 | 整套和整板视觉比较，不只数图 |
| 流线伪三角形 | 图形库折线显式不闭合 | 实际路径叠在模型通路；参数因库而异 |
| PDF每张多出无用大字体 | 清理未用资源与字体子集 | 渲染前后画面一致，矢量保留 |
| PSD实际只有扁平图 | 宿主小样，检查文字、置入和蒙版 | 保存重开并修改验证，不只看文件扩展名 |

PyMuPDF中绘制开放流线时，`Shape.finish`明确指定`closePath=False`；只将箭头头部多边形闭合。其他绘图库检查自身路径机制，不照搬参数名。该修复需在实际输出中看线路，而非仅检查代码含有该参数。

## 如何接收下一轮反馈

在项目反馈记录中写：版本和图件、用户原意、可复现现象、证据、根因状态、修复范围、复验结果。根因未知就写待核，不把推断写成教程。记录与检索用 `scripts/feedback.py`，字段和状态流转见[反馈与自迭代](process/FEEDBACK_WORKFLOW.md)：

```text
python scripts/feedback.py --root PROJECT report --user-text "用户原话" \
  --expected "预期" --actual "实际" --artifact boards.pdf --evidence shot.png \
  --step "打开第1页" --category layout --tag 双横线
python scripts/feedback.py --root PROJECT search --query "双横线 压 图名"
```

新问题先检索同类记录，避免从零分析；根因只有在本修订复现并有证据时才能写成 `confirmed`。修复后关联回归测试再声明 `regression_verified`。

可自动化的问题先加到已有工具与回归样例；语义、审美和规范判断保留实际复核。通用经验经人工审核后才写回本 Skill（`lesson validate` 后 `lesson apply`），单次项目的尺寸、作品名、机器端口和数据库路径留在项目或本地配置。保留有效旧方法，不另造旧执行机制或无限自修改机制。
