# 资源与工具接入

skill内部只有一个SKILL.md；references与scripts属于同一能力，不转而要求安装其他skill。设计软件、模型生成和规范来源由当前环境提供。

## 本地绑定

可在`$CODEX_HOME/architecture-resources.json`（未设CODEX_HOME时为`~/.codex/architecture-resources.json`）登记本机资源。它不属于公共skill内容，不存凭据、浏览器令牌或私人工程。

字段：`workflow_repo`、`design_case_root`、`layout_catalog`、`engineering_catalog`、`revit_database`。排版案例脚本的目录优先级：`--catalog` > 环境变量`ARCH_LAYOUT_CATALOG` > 本地JSON的`layout_catalog`。方案设计库根目录包含cases／index／scripts；排版库与设计库用途不同，不能混为同一个索引。

## 三类库的实际使用链

统一skill内部`resources.py status`检查绑定；`design`、`engineering`、`revit`复用原有库的只读检索工具，不转调子skill，也不复制或重建数据库。使用脚本实际路径，所有示例的宿主年份服从当前项目。

| 当前问题 | 工具 | 找到之后做什么 |
| --- | --- | --- |
| 场地高差、中庭、开放梯、体量和功能 | `resources.py design --query "开放楼梯与阅览空间" --mode lexical --limit 3` | 读实际来源与图纸，模型试验并记录采用理由 |
| 宿主、单位、门切墙、剖面、导出方法 | `resources.py engineering --query "门切不开墙" --software revit` | 读命中的操作卡和相关例子，做代表对象／图面小样 |
| 真实RVT、RTE、RFA与RFT | `resources.py revit --query "窗" --asset-kind family --revit 2021` | 核版本、类别、类型参数和预览；复制工作文件后在宿主验证 |
| 展板构图和画风 | `cases.py --query "竖向 景观 爆炸"` | 打开整套案例，结合本项目真实图件做实尺预案 |

方案库默认使用本 Skill 随附 `assets/knowledge/architecture-case-rag`；本地配置可覆盖。`resources.py` 将 lexical 映射为原 `search_cases.py` 的 baseline，并用 --keyword 实际筛选正文；auto 先语义检索，失败后记录原因并回退 baseline。JSON输出包含 requested_mode、actual_mode、fallback_reasons、results。明确指定semantic／hybrid时失败不伪装语义成功。检索工具不会安装模型或启动服务；链路测试可指定lexical。旧星级、标签、图像URL不等于图纸已核或方法已适用于本方案。

未绑定外部工程目录时，engineering 直接按关键词检索本 Skill 内部 references 并返回真实命中行。已绑定时使用原 `find_asset.py`。原生库使用原`library.py search`并传入由配置数据库推导的库根及真实宿主年份。原库`types --id`可读类型；`stage --id --dest --revit`复制工作副本与类型目录，这两步只在实际选材时按原工具实时帮助执行，不在查询时批量载入或升级文件。系统族可来自RVT／RTE，RFT是作者样板，不是可直接载入族。

原有工具不可用就说明具体缺口；绑定路径存在只表示资源可定位，真实查询成功才算检索链路通过，最终仍须看案例图或工程宿主对象。

路径缺失就记录实际缺项，不重新扫描所有磁盘。找到资源后先读结构：案例JSON可以是cases／entries／顶层列表；SQLite先查表结构，不猜列名。工程样板复制后用当前宿主验证。

## 工具选择

优先现有专用连接、CLI、API或宿主脚本；UI用于真实看图与必要交互。没有工具不假装完成，先推进不依赖它的资料、构图或计算。

本地案例库已具备图面时，不默认重新抓取。用户明确要求扩库时发现当前OpenCLI命令与帮助，再使用现有登录态读取和下载；不能编造版本参数或默认批准点赞／关注／发布。登录或限频阻断时保存断点，原图、来源与运行日志分别保存。

实时站点变更的浏览器回退须遵守当前工具权限；过去某个eval或私有接口可用，不提升为通用绕过方案。遇到失败用记录定位，不在每轮重新发明爬虫。

## 便携性和边界

公共skill只含原创方法、脚本和合成样例，案例图片、作者信息、账号数据、RVT、RFA与SQLite留在本机资源目录。跨机器提供资源配置或用户参考即可，不搬动数据库来适配作者盘符。

规范引用按当前地区和项目查官方有效版本；机型、软件年版、端口、族ID与源文档状态只记在本机／项目断点。公共skill不声称已经验证所有宿主。

安装后未被当前会话发现时，下次新会话重新载入，或直接给智能体SKILL.md路径；目录存在不代表当前聊天已热加载。

配置路径统一展开 ~，相对资源路径以配置文件所在目录为基准。显式 --config 不存在时失败；未提供配置则允许使用随附案例与方法。status 中其他库为可选，只有本次所用资源必须齐备。
