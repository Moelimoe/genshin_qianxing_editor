# Live Sync - GIA 关卡编辑器工具包

AI友好的程序化GIA文件处理工具包，支持构建、修改、验证和导出千星编辑器节点图。

---

## 快速导航

### 🚀 核心模块（AI开发主要使用）

| 模块 | 用途 | 关键类/函数 |
|------|------|------------|
| [`node_catalog`](node_catalog.py) | 节点注册表查询 | `NodeCatalog`, `NodeDef`, `VarType` |
| [`level_builder`](level_builder.py) | 构建节点图 | `GraphBuilder`, `NodeHandle` |
| [`gia_loader`](gia_loader.py) | 加载GIA文件 | `GIALoader`, `LoadedLevel` |
| [`level_exporter`](level_exporter.py) | 导出GIA文件 | `LevelExporter`, `export_level` |
| [`validator`](validator.py) | 验证GIA结构 | `GIAValidator`, `ValidationReport` |
| [`batch_processor`](batch_processor.py) | 批量处理GIA | `BatchProcessor`, `modify_param_rule` |
| [`validate`](validate.py) | 验证CLI工具 | `python -m tools.live_sync.validate` |

### 📖 文档

- [API_REFERENCE.md](API_REFERENCE.md) - 完整API参考和示例代码

---

## 典型工作流

### 1. 创建新节点图

```python
from tools.live_sync.level_builder import GraphBuilder
from tools.live_sync.node_catalog import NodeCatalog
from tools.live_sync.level_exporter import LevelExporter
from pathlib import Path

catalog = NodeCatalog.default()
graph = GraphBuilder(name="MyGraph", catalog=catalog)

# 添加节点并连接
start = graph.add_node("关卡开始时")
listener = graph.add_node("监听信号")
listener.set_param("信号名", "on_trigger")

graph.connect_flow(start, "出", listener, "出")

# 导出
exporter = LevelExporter()
result = exporter.export(graph, "goblet", Path("output.gia"))
```

### 2. 修改现有GIA

```python
from tools.live_sync.gia_loader import GIALoader
from tools.live_sync.node_catalog import NodeCatalog
from pathlib import Path

catalog = NodeCatalog.default()
loader = GIALoader(catalog=catalog)

# 加载
loaded = loader.load(Path("input.gia"))
graph = loaded.get_graph(0)  # 自动使用loader的catalog

# 修改
node = graph.get_node(0)
node.set_param("信号名", "modified_signal")

# 重新导出
graph.to_gia(Path("output.gia"))
```

### 3. 批量修改多个GIA

```python
from tools.live_sync.batch_processor import BatchProcessor, modify_param_rule
from tools.live_sync.node_catalog import NodeCatalog
from pathlib import Path

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

### 4. 验证GIA文件

```bash
# 验证单个文件
python -m tools.live_sync.validate my_level.gia

# 批量验证
python -m tools.live_sync.validate "levels/*.gia" --verbose

# 输出报告
python -m tools.live_sync.validate my_level.gia -o report.txt
```

---

## 目录结构

```
tools/live_sync/
├── README.md              # 本文件
├── API_REFERENCE.md       # API完整文档
│
├── 核心模块/
│   ├── node_catalog.py    # 节点注册表
│   ├── level_builder.py   # 节点图构建
│   ├── gia_loader.py      # GIA加载
│   ├── level_exporter.py  # GIA导出
│   ├── validator.py       # 结构验证
│   ├── gia_utils.py       # 工具函数
│   ├── batch_processor.py # 批量处理
│   └── validate.py        # 验证CLI
│
├── 独立工具脚本/
│   ├── gen_goblet.py      # 生成千星文件
│   ├── batch_generate.py  # 批量生成
│   ├── batch_sync.py      # 批量同步
│   ├── sync.py            # 同步工具
│   ├── sync_safe.py       # 安全同步
│   ├── watch.py           # 文件监控
│   ├── create_entity_with_ng.py
│   ├── gia_asset_builder.py
│   ├── gia_builder.py
│   ├── catalog.py
│   ├── account_selector.py
│   └── asset_registry.py
│
├── tests/                 # 测试目录
│   ├── test_node_catalog.py
│   ├── test_level_builder.py
│   ├── test_gia_loader.py
│   ├── test_level_exporter.py
│   ├── test_validator.py
│   ├── test_validate_cli.py
│   ├── test_batch_processor.py
│   └── test_gia_generation.py
│
└── samples/               # 示例GIA文件
    ├── *.gia              # 测试用GIA文件
    └── export_examples/   # 导出示例
```

---

## 开发原则

1. **TDD开发** - 先写测试再实现功能
2. **API文档优先** - 新功能必须更新API_REFERENCE.md
3. **核心功能优先** - 优先开发实用功能，优化放后
4. **向后兼容** - 不破坏现有API

---

## 开发规则

### 文件与数据

1. **绝不修改游戏客户端和千星编辑器的任何文件**
2. **临时脚本、测试中间产物放 `_scratch/`**，不要污染项目目录
3. **变量名用中文**（如"钥匙数量"），与编辑器保持一致

### 节点定义

4. **引脚名称、数量、类型以 `NODE_REFERENCE.md` 为准**，不要自己猜测命名
5. **修改 `node_catalog.py` 前必须对照 `NODE_REFERENCE.md`**，不一致的以 NODE_REFERENCE.md 为准
6. **NODE_REFERENCE.md 未覆盖的节点**，先查 `node_library.json`，再请用户截图确认
7. **使用服务端 type_id**（小数字），避免客户端版本（20xxxxx）

### 引脚与连线

8. **数据引脚 index 从 0 开始**（流程引脚不计入数据引脚 index）
9. **引脚匹配用 `PinDef.index` 精确匹配**，禁止用 kind_counter 顺序猜测
10. **解析 GIA 时读取 `sig['2']`（pin_index）**，与 catalog 中 `PinDef.index` 做精确匹配
11. **flow 引脚名统一为"入"/"出"**，保持所有节点一致
12. **数据连线的 field[5] 需要包含源引脚索引**：`{"1": node_id, "2": {"1": 4, "2": pin_idx}, "3": {"1": 4, "2": pin_idx}}`

### 代码规范

13. **预期必存在的字段直接用 `dict[key]`**，不要用 `dict.get(key, default)` 掩盖缺失
14. **合并多个 GIA 时直接合并原始 numeric entries**，不要做 decode/encode 往返（会损坏数据）

### 查找节点定义的优先级

1. `NODE_REFERENCE.md`（官方文档汇总，最高文本权威）
2. `node_library.json`（编辑器节点库缓存，最高运行时权威）
3. [官方节点介绍页](https://act.mihoyo.com/ys/ugc/tutorial/detail/mhsok60iqlxk)
4. 千星沙箱编辑器实际查看（解决文档与实际不一致）

---

## 开发环境

### Python 虚拟环境

项目使用 venv，**必须用以下路径运行 Python**：

```
H:\myprojects\genshin_qianxing_editor\venv\Scripts\python.exe
```

> ⚠️ 系统 PATH 中的 `python.exe` 是 TRAE SOLO CN 的嵌入式 Python，缺少编码支持，**无法正常使用**。

PowerShell 运行命令格式：
```powershell
# 运行脚本/测试的正确格式
& H:\myprojects\genshin_qianxing_editor\venv\Scripts\python.exe script.py

# 注意：路径含空格用引号括起来，使用 & 调用符，不要用 cd + && 链式
```

---

## 运行测试

```bash
# 运行所有测试
python -m pytest tools/live_sync/tests/ -v

# 运行特定模块测试
python -m pytest tools/live_sync/tests/test_batch_processor.py -v

# 快速检查
python -m pytest tools/live_sync/tests/ -q
```

---

## 项目目标

将项目改造为AI全自动化/半自动化运行千星关卡编辑。

当前工作模式：
```
用户操作编辑器 ↔ 导出GIA ↔ AI处理GIA ↔ 导入编辑器
```

---

*最后更新：2026-05-19*
