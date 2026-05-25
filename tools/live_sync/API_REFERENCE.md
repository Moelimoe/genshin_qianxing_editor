# AI自动化编辑器 API 文档

## 概述

本模块提供AI友好的程序化接口，用于构建、修改和导出千星编辑器的节点图。

**核心工作流：**
```
加载GIA → 转换为GraphBuilder → 修改节点/连线 → 重新导出GIA
```

---

## 模块索引

| 模块 | 用途 |
|------|------|
| `node_catalog` | 节点语义注册表，查询节点定义和端口信息 |
| `level_builder` | 声明式节点图构建器 |
| `gia_loader` | GIA文件加载器 |
| `level_exporter` | 完整GIA导出器（entity + NG） |
| `validator` | GIA结构验证器 |
| `batch_processor` | GIA批量处理器，支持对多个GIA文件执行统一的修改操作 |
| `validate` | GIA验证命令行工具 |

---

## 快速开始

### 1. 创建节点图

```python
from tools.live_sync.level_builder import GraphBuilder
from tools.live_sync.node_catalog import NodeCatalog

# 获取默认节点注册表
catalog = NodeCatalog.default()

# 创建图
graph = GraphBuilder(name="MyGraph", catalog=catalog)

# 添加节点
start = graph.add_node("关卡开始时")
listener = graph.add_node("监听信号")
listener.set_param("信号名", "my_signal")
sender = graph.add_node("发送信号")

# 连接节点
graph.connect_flow(start, "出", listener, "出")
graph.connect_flow(listener, "出", sender, "入")

# 导出
graph.to_gia(Path("output.gia"))
```

### 2. 加载并修改现有GIA

```python
from tools.live_sync.gia_loader import GIALoader
from tools.live_sync.node_catalog import NodeCatalog

catalog = NodeCatalog.default()
loader = GIALoader(catalog=catalog)

# 加载
loaded = loader.load(Path("input.gia"))
graph = loaded.get_graph(0)

# 修改
node = graph.get_node(0)
node.set_param("信号名", "modified_signal")

# 添加新节点
new_node = graph.add_node("延迟")
new_node.set_param("延迟(秒)", 2.0)

# 重新导出
graph.to_gia(Path("output.gia"))
```

---

## API 参考

### NodeCatalog（节点注册表）

```python
from tools.live_sync.node_catalog import NodeCatalog, NodeDef, PinDef, VarType

catalog = NodeCatalog.default()

# 查询
node_def = catalog.get_by_id(300001)      # 按type_id查询
node_def = catalog.get_by_name("监听信号")  # 按名称查询
nodes = catalog.search("信号")             # 关键词搜索

# 分类
categories = catalog.list_categories()     # ["event", "action", ...]
nodes = catalog.list_by_category("event") # 获取某分类的所有节点

# 连接验证
result = catalog.can_connect(src_def, "出", dst_def, "入")
if result.ok:
    print("可以连接")
else:
    print("错误:", result.errors)
```

**内置节点分类：**

| 分类 | 说明 | 节点示例 |
|------|------|----------|
| event | 事件触发 | 关卡开始时、监听信号、玩家进入触发器 |
| action | 执行动作 | 创建元件、发送信号、播放动画、销毁实体 |
| condition | 条件分支 | 多分支、比较整数、随机概率 |
| variable | 变量操作 | 获取/设置局部变量、获取/设置全局变量 |
| math | 数学运算 | 整数加减乘除、浮点加法、随机整数 |
| logic | 逻辑运算 | 逻辑与、或、非 |
| utility | 实用工具 | 延迟、日志输出、获取玩家实体 |

---

### GraphBuilder（节点图构建器）

```python
from tools.live_sync.level_builder import GraphBuilder

graph = GraphBuilder(name="MyGraph", catalog=catalog)

# 添加节点
node = graph.add_node("节点名称")           # 按名称添加
node = graph.add_node(300001)              # 按type_id添加
node = graph.add_node("监听信号", 信号名="test")  # 直接设置参数

# 节点操作
node.set_param("参数名", 值)                # 设置参数
value = node.get_param("参数名")            # 获取参数
node.x, node.y = 100, 200                  # 设置坐标

# 连接
graph.connect_flow(src_node, "出", dst_node, "入")  # 流程连接
graph.connect_data(src_node, "数据出", dst_node, "数据入")  # 数据连接

# 查询
count = graph.node_count()                 # 节点数量
node = graph.get_node(0)                   # 按索引获取

# 验证
result = graph.validate()                  # 验证图结构
if not result.ok:
    print("错误:", result.errors)

# 导出
num = graph.to_numeric()                   # 导出为numeric dict
graph.to_gia(Path("output.gia"))           # 导出为GIA文件

# 快照/回滚
graph.snapshot()                           # 保存快照
graph.undo()                               # 回滚到上一快照

# 自动布局
graph.auto_layout(x_spacing=300, y_spacing=200)
```

---

### GIALoader（GIA加载器）

```python
from tools.live_sync.gia_loader import GIALoader, load_gia, load_graph

loader = GIALoader(catalog=catalog)

# 加载
loaded = loader.load(Path("input.gia"))
loaded = load_gia(Path("input.gia"), catalog=catalog)  # 便捷函数

# LoadedLevel属性
print(loaded.gia_path)        # 文件路径
print(loaded.entries)         # 所有entries
print(loaded.entity_entries)  # entity entries
print(loaded.ng_entries)      # NG entries
print(loaded.export_tag)      # 导出标签

# 获取节点图
graph = loaded.get_graph(0)                    # 第一个NG entry
graph = loaded.get_graph(0, catalog=catalog)   # 指定catalog
count = loaded.get_graph_count()               # NG entry数量

# 推断asset key
asset_key = loaded.get_entity_asset_key()  # "goblet", "coin", "key" 等

# 便捷函数
graph = load_graph(Path("input.gia"), index=0, catalog=catalog)
```

---

### LevelExporter（完整GIA导出器）

```python
from tools.live_sync.level_exporter import LevelExporter, export_level

exporter = LevelExporter()

# 导出（包含entity + NG）
result = exporter.export(
    graph=graph,
    asset_key="goblet",      # "goblet", "coin", "key"
    output_path=Path("output.gia"),
    validate=True            # 是否验证
)

print(result.ok)             # 是否成功
print(result.output_path)    # 输出路径
print(result.entity_entry)   # entity entry
print(result.ng_entry)       # NG entry

# 导出为numeric dict（不保存文件）
num = exporter.export_to_numeric(graph, "goblet")

# 便捷函数
result = export_level(graph, "goblet", Path("output.gia"))
```

---

### BatchProcessor（GIA批量处理器）

```python
from tools.live_sync.batch_processor import BatchProcessor, modify_param_rule, rename_signal_rule

bp = BatchProcessor(catalog=catalog)

# 批量修改参数
result = bp.process(
    input_files=["a.gia", "b.gia"],
    rules=[modify_param_rule("信号名", "new_signal")],
    output_dir=Path("output/"),
)

# 条件修改（只改匹配旧值的）
result = bp.process(
    input_files=["a.gia", "b.gia"],
    rules=[rename_signal_rule("old_signal", "new_signal")],
    output_dir=Path("output/"),
    dry_run=True,          # 干运行，不写入
    validate_before=True,  # 修改前验证
    validate_after=True,   # 修改后验证
)

print(result.summary())  # 打印结果摘要
print(result.ok)         # 是否全部成功
```

---

### validate CLI（GIA验证命令行工具）

```bash
# 验证单个文件
python -m tools.live_sync.validate my_level.gia

# 详细报告
python -m tools.live_sync.validate my_level.gia --verbose

# 批量验证
python -m tools.live_sync.validate "levels/*.gia"

# 输出到文件
python -m tools.live_sync.validate my_level.gia -o report.txt

# 不使用节点注册表
python -m tools.live_sync.validate my_level.gia --no-catalog
```

---

### VarType（变量类型常量）

```python
from tools.live_sync.node_catalog import VarType

VarType.Ety      # 1  - 实体
VarType.GUID     # 2  - GUID
VarType.Int      # 3  - 整数
VarType.Bol      # 4  - 布尔
VarType.Flt      # 5  - 浮点
VarType.Str      # 6  - 字符串
VarType.Vec      # 12 - 向量
VarType.Prefab   # 21 - 预制件
```

---

## 完整示例

### 示例1：创建简单的信号触发流程

```python
from pathlib import Path
from tools.live_sync.level_builder import GraphBuilder
from tools.live_sync.node_catalog import NodeCatalog
from tools.live_sync.level_exporter import LevelExporter

# 初始化
catalog = NodeCatalog.default()
graph = GraphBuilder(name="SignalDemo", catalog=catalog)

# 构建流程：关卡开始 → 监听信号 → 发送信号
start = graph.add_node("关卡开始时")

listener = graph.add_node("监听信号")
listener.set_param("信号名", "on_trigger")

sender = graph.add_node("发送信号")
sender.set_param("信号名", "on_complete")

# 连接
graph.connect_flow(start, "出", listener, "出")
graph.connect_flow(listener, "出", sender, "出")

# 自动布局
graph.auto_layout()

# 导出
exporter = LevelExporter()
result = exporter.export(graph, "goblet", Path("signal_demo.gia"))
print(f"导出成功: {result.ok}")
```

### 示例2：加载并修改现有关卡

```python
from pathlib import Path
from tools.live_sync.gia_loader import GIALoader
from tools.live_sync.node_catalog import NodeCatalog
from tools.live_sync.level_exporter import LevelExporter

catalog = NodeCatalog.default()
loader = GIALoader(catalog=catalog)

# 加载
loaded = loader.load(Path("original.gia"))
graph = loaded.get_graph(0, catalog=catalog)

print(f"加载了 {graph.node_count()} 个节点")

# 修改第一个节点的参数
if graph.node_count() > 0:
    node = graph.get_node(0)
    if node.name == "监听信号":
        node.set_param("信号名", "modified_signal")

# 在末尾添加延迟节点
delay = graph.add_node("延迟")
delay.set_param("延迟(秒)", 1.5)

# 获取最后一个节点并连接
last_node = graph.get_node(graph.node_count() - 2)
graph.connect_flow(last_node, "出", delay, "入")

# 重新导出
exporter = LevelExporter()
result = exporter.export(graph, "goblet", Path("modified.gia"))
print(f"导出成功: {result.ok}")
```

### 示例3：使用条件分支

```python
from tools.live_sync.level_builder import GraphBuilder
from tools.live_sync.node_catalog import NodeCatalog

catalog = NodeCatalog.default()
graph = GraphBuilder(name="BranchDemo", catalog=catalog)

# 创建分支结构
start = graph.add_node("关卡开始时")
branch = graph.add_node("多分支")
branch.set_param("条件", 1)  # 条件值

action1 = graph.add_node("播放音效")
action1.set_param("音效ID", "sound_001")

action2 = graph.add_node("播放音效")
action2.set_param("音效ID", "sound_002")

# 连接分支
graph.connect_flow(start, "出", branch, "入")
graph.connect_flow(branch, "分支0", action1, "入")
graph.connect_flow(branch, "分支1", action2, "入")

# 导出
graph.to_gia(Path("branch_demo.gia"))
```

### 示例4：批量修改GIA文件

```python
from pathlib import Path
from tools.live_sync.batch_processor import BatchProcessor, modify_param_rule

catalog = NodeCatalog.default()
bp = BatchProcessor(catalog=catalog)

result = bp.process(
    input_files=list(Path("levels").glob("*.gia")),
    rules=[modify_param_rule("信号名", "unified_signal")],
    output_dir=Path("levels_modified"),
    validate_before=True,
    validate_after=True,
)
print(result.summary())
```

---

## 注意事项

1. **catalog必须一致** - 加载和导出时使用相同的NodeCatalog
2. **端口名称** - 使用中文端口名称（如"入"、"出"、"信号名"）
3. **连接验证** - 连接时会自动验证端口类型兼容性
4. **坐标设置** - 使用 `auto_layout()` 或手动设置 `node.x, node.y`
5. **快照机制** - 修改前可调用 `snapshot()`，失败时用 `undo()` 回滚
6. **GIALoader自动记住catalog** - `loader.load()` 后 `get_graph(0)` 自动使用loader的catalog，无需再次传入

---

## 错误处理

```python
from tools.live_sync.level_builder import GraphBuilder

graph = GraphBuilder(name="Test", catalog=catalog)

# 验证连接
try:
    graph.connect_flow(node1, "出", node2, "入")
except ValueError as e:
    print(f"连接失败: {e}")

# 验证图结构
result = graph.validate()
if not result.ok:
    for error in result.errors:
        print(f"错误: {error}")
```
