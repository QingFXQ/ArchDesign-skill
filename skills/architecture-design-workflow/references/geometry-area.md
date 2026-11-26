# 几何与面积

`design_check.py shell/layout` 使用 Python 3.10+、Shapely 2.1+（GEOS 3.10+）。以本项目局部米制坐标表达 2D GeoJSON Polygon/MultiPolygon（闭合外环与孔）。同一输入含 `"schema": 1`、`"units": "m"`。坐标变换由采用原图的一端明确记录并验锚点。

## 独立主体

| 字段 | 内容 |
| --- | --- |
| `site`、`buildable` | 可选场地与建设控制面 |
| `levels` | 每层 `id, polygon, z_m, location`。`location` 按项目建面口径声明为 `above` 或 `below`；`thickness_m` 可生成板网格 |
| `voids` | `id, polygon, levels`，从明示的楼层扣减庭院、洞口或挑空 |
| `masses` | `id, polygon, z_range_m`，可用 `cuts` 切除贯穿该体量的投影区域 |
| `roofs` | `id, polygon, plane, thickness_m`，可设 `cuts`。各片面独立，`plane` 为 `[dz/dx, dz/dy, z0]`，相邻折面共享相同折线高程需另核 |

`shell` 输出扣除后楼板、多面片和可编辑网格。重复、错动、斜轮廓和曲线离散段由用户或脚本提供，底层基于多边形与定厚板。通高通过楼层之间独立扣减。需要不同板顶标高时分别表达板区，并在当前口径合并分层统计。导入 Blender 生成网格集合；独立斜墙厚度、结构、真门窗、曲面和完整 BIM 由建模端完成。`adapt_candidate()` 可以把候选裁到剩余有效控制域，并返回面积损失。保留原候选与裁切结果，再决定调整布局或主体。由房间增减反推外形时把新轮廓作为显式决策写入控制域。

## 房间级预算与统计

- `room_requirements` 独立保存预期房间。每项 `id`、可选 `required`（默认真）、`category`、`level`、`budget`、`adjacent` 和 `connected`。`rooms` 按同一 ID 提供各层实际多边形。与预算重叠的项目不能写不同的值。
- 每房 `net_polygon` 或 `net_inset_m` 二选一。净轮廓可直接来自原生模型，内缩法按各边统一扣减并处理孔和外角，结果是概念估算。由本项目选扣量。`budget` 中的 `min, target, max, deviation` 使用净面积 m²，`deviation` 与目标成对。`priority` 用于解释分配顺序，`min_width_m, min_depth_m` 为项目阈值，宽和深是旋转外包矩形的短边和长边，另做连续内缩探针识别无容量或被细颈割裂的空间。复杂房形仍要实尺检查。提供 `candidate_polygon` 和可选 `max_loss_m2` 可核裁切量。
- `area_limits_m2` 以 `gross`、`gross/above`、`gross/below`、`net_total`、`outline_total`、`net/类别` 或 `outline/类别` 施加项目约束。按项目类别分列公共、受控和竖向交通。若某类别暂未布置任何房间，可在顶层 categories 明示，以免拼写错误产生静默零值。每个房间只归一类，复合空间描述用途，按所采用归类不重复计量。建筑面积为各有效楼板的投影和，最终按项目确定封闭、雨棚、坡屋面等计量。
- 房间轮廓减净轮廓作为围护等占用的估算差。楼板内且房间外的构造用 `explained_areas`（`level, polygon, reason`，可选 `category`）单列。剩余用实际布尔差求出，并可用 `max_unexplained_m2` 给每层上限。`outdoor_areas` 用 `id, polygon` 登记，室外独立用 `outdoor_total` 和 `outdoor/ID` 核算。
- `tolerances.area_m2` 与 `tolerances.length_m` 显式设置。按输入精度声明毫米级贴边容差，报告近边小差额供复核。相交、异常和越界不自动修复。存在错误时，各类别房间和是候选记录求和，楼板已占面积则用几何并集，先解决重叠后再采用统计。

## 门洞与路径

`adjacent` 检查同层共有边；`connected` 要求通过有效连接。`connections` 以 `id/from/to/kind` 登记，同层门 `door` 的 `segment` 两端须在共有边上，并可给 `min_width_m`。对外 `entry` 的 `to` 为空，开口在房间与楼板边界上。能否抵达人行地面仍看场地和剖面。`vertical` 用 `from_xyz/to_xyz` 对比房间及楼层标高（房间可设 `z_m`），可限制 `aligned` 以核同轴。`check_reachability` 从有效外部入口检查连通图。门的实际墙洞、疏散分区、运营状态、载重和净空需要宿主模型核对。

`--mode explore` 将可调整问题列为提示，非法几何或引用仍失败。`--mode accept` 把已声明约束的违例列为失败。报告保留人工复核项。declared_checks_clear 单列本次声明的检查是否无问题；探索模式的 CLI 返回成功时仍应读偏差清单。样例见[小办公楼](../assets/office-study.json)。
