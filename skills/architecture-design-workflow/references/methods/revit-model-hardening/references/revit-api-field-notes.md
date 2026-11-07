> 本文件是唯一建筑设计 Skill 的内部阶段参考；所有工作由当前执行者完成，决定以用户当前授权和主入口为准。历史实测数值仅为例子，不能外推为通用阈值。

# Revit API 现场笔记

`revit-model-hardening` 的配套参考。全部条目来自实测，标注了症状与修法。
适用于 Revit 2021 + `mcp-server-for-revit` + `send_code_to_revit`。

---

## 1. 连接

### 1.1 端口只有一个

| 端口 | 是谁 | 能不能连 |
| --- | --- | --- |
| **8080** | `revit_mcp_plugin` 的 socket 服务 | 唯一可用 |
| 8088 | Revit 自带 Generative Design 的本机服务 | **不是 MCP**，连它会无限超时 |

探活失败时不要“换个端口试”。看插件日志这一行才算通：

```
[Info] Socket service initialized on port 8080
```

日志路径：`C:\ProgramData\Autodesk\Revit\Addins\<版本>\revit_mcp_plugin\Logs\mcp_<YYYYMMDD>.log`

### 1.2 服务开关必须有人点

`Revit MCP Switch` 是 ribbon 上的 ExternalCommand，插件启动**不会**自动开 socket。

- 开关状态在**正常退出**时保持，下次启动自动恢复
- **强杀进程会丢失**该状态 → 下次启动 8080 不监听，必须人工再点一次
- 这一条是“不要强杀 Revit”的最硬理由

### 1.3 不要指望 UI 自动化点开它

Revit 2021 的功能区**不暴露在 UIA 树**里。实测：从主窗口 `FindAll(Descendants, ControlType.TabItem)` 只能拿到 WPF 停靠面板的 tab（`Xceed.Wpf.AvalonDock.Layout.LayoutDocument`），拿不到「附加模块」；按名字匹配 `MCP|Switch` 的按钮也搜不到。

所以：**这一步只能由人点**。把话说清楚、说一次，不要反复要求用户重复操作。

### 1.4 插件日志里的“噪音”

```
Failed to create command instance [xxx]: RevitMCPCommandSet.dll
Assembly version conflict
```

这类每天几十上百条，**不影响** `send_code_to_revit`。真正的失败是：写操作触发警告 → 模态框 → 队列堵死。不要拿日志条数判断链路健康。

---

## 2. 单位

### 2.1 三套单位

| 场景 | 单位 |
| --- | --- |
| `send_code_to_revit` 里所有 Revit API 长度 | **英尺** |
| 专用创建 tool（部分封装）的入参 | 毫米 |
| 项目里人读的坐标/标高 | 米（中文项目习惯） |

```csharp
double Ft(double mm) => mm / 304.8;    // 毫米 → 英尺
double Ft(double m)  => m  / 0.3048;   // 米   → 英尺
```

### 2.2 最致命的那一个：NewRoom 的 UV

```csharp
// ✗ 错：从米换英尺用了毫米的除数
document.Create.NewRoom(lv, new UV(58.7/304.8, 38.0/304.8));
//   → 58.7 m 变成 0.19 ft ≈ 0.06 m，房间落到原点

// ✓ 对
document.Create.NewRoom(lv, new UV(58.7/0.3048, 38.0/0.3048));
```

**症状**：房间创建成功、`ElementId` 正常，但 `Area == 0`，`LocationPoint` 在原点附近。

**误诊路径**：以为“位置处墙没闭合”。会去查墙端点、查房间边界属性、写栅格洪泛算法——全是白费。

**正确顺序**：看到面积 0 → 先算单位 → 再查几何。

### 2.3 面积读回时机

`Transaction.Commit()` 之前读 `Room.Area` 拿到的是旧值（新建房间为 0）。
先 Commit，再**重新 GetElement** 读面积。

---

## 3. 事务与模态框

### 3.1 两种模式

| transactionMode | 谁开事务 | 适用 |
| --- | --- | --- |
| `auto` | MCP 包装器 | 单个、简单、无警告风险的写入 |
| `none` | 你在代码里显式开 | 只读、导出、批量写、需要自己控制失败处理 |

### 3.2 批量写必须自开事务并关模态

`auto` 模式下警告会变成**模态框**，堵在 UI 线程上，之后连只读调用都超时——这是最耗时的故障。

```csharp
using (var t = new Transaction(document, "batch"))
{
    var opt = t.GetFailureHandlingOptions();
    opt.SetForcedModalHandling(false);    // 关键：警告不弹框
    opt.SetClearAfterRollback(true);
    t.SetFailureHandlingOptions(opt);

    t.Start();
    // ... 写入 ...
    t.Commit();
}
```

> 实测：同一台机器上，`auto` 模式建房间 = 卡死重启；`none` + 上述写法 = 一次建成 35 间、零警告。

### 3.3 单次代码只承担一个可回滚目的

不要在一个代码块里混合「建模 + 删除 + 导出 + 写数据库」。回滚粒度会失控。

---

## 4. 批量与性能

### 4.1 一批 ≤3 个构件

写操作批量上限不是传输带宽，是**警告弹窗概率**。批越大，撞警告的概率越接近 1。

### 4.2 `GetBoundarySegments` 不能批量

一次扫 122 个房间的 `GetBoundarySegments` 会把 ExternalEvent 拖死，之后 `return new{X=1};` 都超时。

- 按**层**分段，一次 ≤20 间
- 只取需要的那几间：先按功能名过滤，再取边界

### 4.3 重查询前先 `WhereElementIsNotElementType()`

否则 `Cast<Wall>()` 会撞到 WallType 上抛异常。

---

## 5. 编译坑（`send_code_to_revit` 的代码体）

| 写法 | 问题 | 修法 |
| --- | --- | --- |
| `new[]{ new[]{1,2}, new[]{3,4} }` | 隐式嵌套数组推断不出类型，编译失败 | 显式：`new int[][]{ new[]{1,2}, new[]{3,4} }`，或先声明 `int[,]` |
| `Category.GetLineWeight(...)` 直接赋给 `int` | 部分版本返回 `int?` | `var a = c.GetLineWeight(GraphicsStyleType.Projection); if (a.HasValue) { ... }` |
| `LinePatternElement.GetLinePatternElement(document, id)` | 该重载不存在 | `document.GetElement(id) as LinePatternElement` |
| `warnings[i]` | `WarningSet` 不是数组 | `warnings.get_Item(i)` |
| `foreach(var c in document.Settings.Categories)` | 元素是 `object` | `foreach(Category c in document.Settings.Categories)` |
| 代码里写中文类型名 | UTF-8 分块可能截断多字节字符，报“行 N 语法错误” | 先用探针验证中文完整性；长期用 `ElementId` 或 ASCII 过滤 |
| `sym.IsActive = true` | 属性只读 | `sym.Activate();` 然后 `document.Regenerate();` |
| `NewFamilyInstance(p, sym, host, StructuralType.NonStructural)` | 门/窗需要墙宿主 | `NewFamilyInstance(XYZ, FamilySymbol, Wall, Level)` 重载 |

### 5.1 中文探针

用类型名匹配前先跑一次：

```csharp
var s = "常规 - 200mm";
return new { Len = s.Length, Code = (int)s[0] };
```

`Len` 与预期一致（含空格 11）才可用。注意：`Length` 是 .NET 的 UTF-16 长度，中文按 1 计。

---

## 6. 只读审计代码模板

每次新建项目先跑这五段。**一次一段，不要合并。**

### 6.1 标高与轴网

```csharp
var lv = new FilteredElementCollector(document).OfClass(typeof(Level)).Cast<Level>()
    .Select(l => new { Id = l.Id.IntegerValue, Name = l.Name, E = Math.Round(l.Elevation * 0.3048, 3) })
    .OrderBy(x => x.E).ToArray();
var gd = new FilteredElementCollector(document).OfClass(typeof(Grid)).Cast<Grid>()
    .Select(g => new { Id = g.Id.IntegerValue, Name = g.Name }).ToArray();
return new { Title = document.Title, Active = document.ActiveView.Name, Levels = lv, Grids = gd.Length };
```

### 6.2 墙：类型 × 宽度 × 是否围合房间 × 是否有门窗

```csharp
var rooms = new FilteredElementCollector(document).OfCategory(BuiltInCategory.OST_Rooms)
    .WhereElementIsNotElementType().Cast<Autodesk.Revit.DB.Architecture.Room>().Where(r => r.Area > 0);
var cnt = new Dictionary<int,int>();
var opts = new SpatialElementBoundaryOptions();
foreach (var r in rooms) {                       // 房间少时可直接跑；>50 间请分层
    var segs = r.GetBoundarySegments(opts);
    if (segs == null) continue;
    foreach (var loop in segs) foreach (var s in loop) {
        int id = s.ElementId.IntegerValue;
        if (id <= 0) continue;
        if (!cnt.ContainsKey(id)) cnt[id] = 0;
        cnt[id] = cnt[id] + 1;
    }
}
var agg = new Dictionary<string,double[]>();
foreach (var w in new FilteredElementCollector(document).OfCategory(BuiltInCategory.OST_Walls)
         .WhereElementIsNotElementType().Cast<Wall>()) {
    if (w.WallType.Kind == WallKind.Curtain) continue;
    int c = cnt.ContainsKey(w.Id.IntegerValue) ? cnt[w.Id.IntegerValue] : 0;
    var lc = w.Location as LocationCurve;
    double len = lc == null ? 0 : lc.Curve.Length * 0.3048;
    string k = w.WallType.Name + " | rooms=" + c;
    if (!agg.ContainsKey(k)) agg[k] = new double[]{0,0};
    agg[k][0] += 1; agg[k][1] += len;
}
var o = new List<object>();
foreach (var kv in agg) o.Add(new { K = kv.Key, N = (int)kv.Value[0], Len = Math.Round(kv.Value[1],0) });
return new { Groups = o };
```

### 6.3 对象样式线宽

```csharp
var o = new List<object>();
foreach (Category c in document.Settings.Categories) {
    if (c.CategoryType != CategoryType.Model) continue;
    int pw = -1, cw = -1, sub = 0;
    var a = c.GetLineWeight(GraphicsStyleType.Projection); if (a.HasValue) pw = a.Value;
    var b = c.GetLineWeight(GraphicsStyleType.Cut);        if (b.HasValue) cw = b.Value;
    try { sub = c.SubCategories.Size; } catch { }
    o.Add(new { N = c.Name, P = pw, C = cw, S = sub });
}
return new { Cats = o };
```

### 6.4 警告

```csharp
var w = document.GetWarnings();
var l = new List<object>();
for (int i = 0; i < w.Size; i++) {
    var x = w.get_Item(i);
    l.Add(new { Code = x.FailureDefinitionId.Guid.ToString(), Msg = x.GetDescriptionText() });
}
return new { N = w.Size, Items = l };
```

### 6.5 重复墙检测

```csharp
var g = new Dictionary<string,List<int>>();
foreach (var w in new FilteredElementCollector(document).OfCategory(BuiltInCategory.OST_Walls)
         .WhereElementIsNotElementType().Cast<Wall>()) {
    if (w.WallType.Kind == WallKind.Curtain) continue;
    var ln = (w.Location as LocationCurve)?.Curve as Line;
    if (ln == null) continue;
    var a = ln.GetEndPoint(0); var b = ln.GetEndPoint(1);
    int ax = (int)Math.Round(a.X*304.8), ay = (int)Math.Round(a.Y*304.8);
    int bx = (int)Math.Round(b.X*304.8), by = (int)Math.Round(b.Y*304.8);
    string k1 = ax+","+ay+"|"+bx+","+by, k2 = bx+","+by+"|"+ax+","+ay;
    string key = document.GetElement(w.LevelId).Name + "#" + (k1.CompareTo(k2) < 0 ? k1 : k2);
    if (!g.ContainsKey(key)) g[key] = new List<int>();
    g[key].Add(w.Id.IntegerValue);
}
var dup = new List<object>();
foreach (var kv in g) if (kv.Value.Count > 1) dup.Add(new { K = kv.Key, Ids = kv.Value.ToArray() });
return new { Groups = dup, Redundant = dup.Count };
```

---

## 7. 故障恢复

### 7.1 判定树

```
写入超时
├─ 短超时只读探活（return new{X=1}; 30s）
│   ├─ 通 → 上一次写入其实成功了，回读确认，不要重试
│   └─ 不通 → 队列被堵
│       ├─ 查进程 Responding / 有无模态窗口
│       ├─ 查插件日志最新行
│       └─ 不要点重试，不要强杀
```

### 7.2 恢复顺序

1. 确认模型已保存：`document.IsModified == false`，磁盘 SHA 与上次一致
2. 优先 `CloseMainWindow()`（正常关闭，保住服务开关状态）
3. 无响应且已确认无未保存内容 → 才考虑强制结束
4. 重启后 8080 若未监听 → 只能请人点开关，同时说明是强杀导致的

### 7.3 保存

`document.Save()` 在某些情况下报 `open transaction phase`——通常是上一次超时把事务挂在了打开状态。此时 API 存不了，改用界面保存按钮。**下次写之前先确认 `document.IsModified`**。

---

## 8. 编码与路径

- 中文路径：把路径写进 UTF-8 文件，C# 用 `File.ReadAllText(path, Encoding.UTF8)` 读；不要靠命令行参数传中文
- Python 侧统一 `PYTHONUTF8=1`，脚本用 `-B` 避免生成 `__pycache__`
- 文档路径比较忽略大小写：`StringComparison.OrdinalIgnoreCase`

---

## 9. 一页速记

```
端口 8080，不是 8088
开关要人点，强杀会丢
单位是英尺，米除 0.3048，毫米除 304.8
NewRoom 的 UV 也是英尺
一批 3 个构件
批量写：transactionMode=none + SetForcedModalHandling(false)
Commit 后再读值
GetBoundarySegments 一次 ≤20 间
超时先探活，不重试，不强杀
```
