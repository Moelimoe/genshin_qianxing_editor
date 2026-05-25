# 千星奇域编辑器 — 技术知识笔记

> 合并自 memory.md / learning_notes.md / analysis_report.md
> 最后更新：2026-05-24

---

## 一、项目概况

- **项目**：Ayaya_Miliastra_Editor（小王千星工坊）— 原神千星奇域离线沙箱编辑器
- **分支**：`dev/node-graph-improvement`
- **本地路径**：`h:\myprojects\genshin_qianxing_editor`
- **远端（fork）**：`git@github.com:Moelimoe/genshin_qianxing_editor.git`
- **上游（原始）**：`https://github.com/AyayaXiaowang/Ayaya_Miliastra_Editor`
- **Python 环境**：`venv\Scripts\python.exe` (Python 3.10.13)
- **运行命令**：`& 'h:\myprojects\genshin_qianxing_editor\venv\Scripts\python.exe' -X utf8 <script>`

### 当前方案

**直接生成 .gil/.gia 文件**，绕过编辑器 UI，实现程序化关卡生成。

- 已完成格式逆向：GIA 容器结构、protobuf-like 编解码、NodeGraph binary 格式
- 当前主工作区：`tools/live_sync/` — 资产注册表 + GIA 文件生成器 + 声明式关卡 API

### 远期方向

除节点图外，自动生成关卡的元件、组件、地图等全部信息。

---

## 二、GIA 文件格式

### 2.1 基本概念

- **.gil**：千星奇域本地缓存文件，包含全量关卡数据
- **.gia**：项目交付/导出格式，protobuf-like 包裹结构

### 2.2 GIA 容器结构

```
GIA 顶层字段：
  field '1' = entries（列表或单个 dict）
  field '2' = dict（全局元数据，缺失不影响导入）
  field '3' = export_tag（binary_data 格式，修改不影响导入）
  field '5' = str（全局元数据，缺失不影响导入）
```

### 2.3 Entry 结构

**Entity entry**（实体条目）：
- keys: `['1', '3', '5', '12']`
- field '1' = Location（包含 resource_class, loc_id 等）
- field '12' = related_ids（实体引用）
- field '11' = payload（可选）

**NG entry**（节点图条目）：
- keys: `['1', '3', '5', '13']`
- field '13' = NodeGraph 数据

### 2.4 核心结构规则

- **NG 必须作为独立条目**，不能嵌入 entity entry
- 正确结构：`entries = [entity_entry(['1','3','5','12']), ng_entry(['1','3','5','13']), ...]`
- 单条目时 `decoded_field_map` 可能返回 dict 而非 list，属解码器行为，不影响导入

---

## 三、节点图（Node Graph）核心概念

### 3.1 节点图是什么

- 物件默认是**静态**的，要实现运动、交互、逻辑行为，需挂载节点图
- 复杂物件按**部位**划分，每个部位可关联不同的节点图
- 节点图是**事件驱动**的（事件节点作为流程入口）

### 3.2 节点图类型

| 类型 | 说明 |
|------|------|
| Server 节点图 | 服务端逻辑，处理游戏核心逻辑 |
| Client 节点图 | 客户端逻辑，处理本地效果和 UI |
| 实体节点图 | 挂载到实体上的节点图 |
| 状态节点图 | 与角色状态相关 |
| 职业节点图 | 角色职业/技能相关 |
| 道具节点图 | 掉落物/道具相关 |
| 技能节点图 | 技能相关（客户端） |
| 过滤节点图 | 对不同物体进行筛选过滤 |

### 3.3 端口类型系统

| 端口类型 | 说明 |
|----------|------|
| 流程（Flow） | 控制执行流程，白色/灰色三角 |
| 实体（Entity） | 游戏中的物体/角色引用 |
| 整数（Integer） | 整数类型 |
| 浮点数（Float） | 小数类型 |
| 字符串（String） | 文本类型 |
| 布尔值（Boolean） | 真/假 |
| 列表（List） | 泛型列表类型 |
| 字典（Dict/Struct） | 结构体/键值对类型 |
| 枚举（Enum） | 枚举类型 |
| 向量3（Vector3） | 三维坐标 |
| 触发器（Trigger） | 碰撞/交互触发 |

### 3.4 核心系统

- **事件系统**：内置事件（实体创建时、碰撞触发、定时器触发等）+ 自定义事件（信号系统）
- **信号系统**：一对多通信，可携带全类型参数，定义在 `管理配置/信号/` 目录下
- **变量系统**：关卡变量（贯穿整个游戏生命周期）+ 局内存档变量（单局内有效）
- **定时器**：全局计时器（整个生命周期持续运行）+ 普通定时器
- **复合节点**：对一组节点的封装（类似函数），支持嵌套和复用，定义在 `复合节点库/` 目录下

---

## 四、已验证结论

以下结论均通过 L3（千星编辑器实际导入）验证：

- 编码管线无误（往返测试：decode -> encode 二进制 100% 一致）
- 单条目无 NG 文件可导入
- 组合资产包（物件 + 多个 NodeGraph）可导入
- 修改 entry 名称不影响导入
- 修改 export_tag 不影响导入
- 修改 NodeGraph 条目名称不影响导入
- 增减条目（保留结构完整性）不影响导入
- GIA 顶层字段 '2'(dict) 和 '5'(str) 为全局元数据，缺失不影响导入
- NG 内部修改（坐标/图名/loc_id）可导入
- 结构修改（增节点/新ID/裁剪图）可导入
- 连线修改（改输出目标/新增端口）可导入
- 从零创建 NG（分支/数据线/1-3 节点）可导入

---

## 五、开发方法论：测试驱动 GIA 生成

### 5.1 核心理念

由于 .gia 文件的正确性只能通过「导入千星编辑器」来最终验证（人工操作、反馈慢），采用**渐进式测试驱动**策略。

### 5.2 三级测试体系

| 层级 | 测试内容 | 反馈速度 |
|------|---------|---------|
| **L1 结构测试** | 生成后 decode 回来，验证顶层 keys、条目数量、字段类型 | 即时 |
| **L2 往返测试** | decode -> encode -> decode，验证二进制完全一致 | 即时 |
| **L3 导入验证** | 在千星编辑器中实际导入，确认可加载且不破坏已有资产 | 慢（人工） |

### 5.3 工作流

```
提出修改 -> L1测试 -> L2测试 -> 生成文件 -> L3人工导入验证
              ^                                          |
              +--- 失败则回退 -- 成功则固化测试 -----------+
```

- 每一步成功的 L3 验证，将其结构特征固化为 L1/L2 单元测试
- 任何新的生成逻辑，必须先通过已有的 L1/L2 测试才能进入 L3

### 5.4 测试约定

- 测试文件：`tools/live_sync/tests/test_<功能描述>.py`
- 运行：`pytest tools/live_sync/tests/ -v`
- fixture 从 `export_examples/` 加载源文件，不依赖临时样本

---

## 六、项目架构与模块

### 6.1 架构分层

```
app/            <- UI、CLI、自动化装配（顶层）
engine/         <- 图引擎（Graph Code -> GraphModel -> 验证/布局）[纯逻辑]
plugins/        <- 节点实现注册表
assets/         <- 资源库（节点图代码、复合节点、配置）
tools/live_sync/ <- 当前主工作区：资产注册表 + GIA 生成 + 声明式关卡 API
```

### 6.2 live_sync 核心模块

| 文件 | 功能 | 测试数 |
|------|------|--------|
| `asset_registry.py` | 资产注册表：编目已验证可导入的资产类型 | - |
| `node_catalog.py` | 节点语义注册表：VarType 常量、PinDef、NodeDef、NodeCatalog | 46 |
| `level_builder.py` | 声明式关卡 API：NodeHandle、GraphBuilder、LevelBuilder | 77 |
| `validator.py` | 即时验证机制：ValidationIssue、ValidationReport、GIAValidator | 51 |
| `level_exporter.py` | 完整 GIA 导出：LevelExporter、ExportResult、entity + NG 组合 | 14 |
| `create_entity_with_ng.py` | 将 NodeGraph 从源 GIA 复制到目标实体 | - |

### 6.3 关键目录

| 路径 | 用途 |
|------|------|
| `tools/live_sync/` | 当前主工作区 |
| `tools/live_sync/samples/` | 生成的 .gia 测试样本 |
| `tools/live_sync/tests/` | 单元测试 |
| `private_extensions/ugc_file_tools/` | GIA/GIL 解析/导出核心库 |
| `engine/` | Graph Code 引擎（勿改） |
| `assets/资源库/` | 节点图代码（共享 + 项目存档） |

---

## 七、已知限制与注意事项

### 7.1 旧方案（PyAutoGUI/OCR）的已知问题

以下问题属于旧的 UI 自动化方案，当前 GIA 直写方案已绕过，影响低：

- 连线验证永远返回 True（`_verify_drag_effect()` 所有失败路径也 return True）
- 缩放确认标志永不重置（`zoom_50_confirmed`）
- `scale_ratio` 恒为 1.0，非标准 DPI 下坐标累积误差
- `_resolve_builtin_node_def_ref_by_title` 在三处完全重复定义
- 复合节点模糊名称匹配过于宽松
- `validate_graph_model` 边遍历至少执行 3 次全量扫描

### 7.2 当前注意事项

- `private_extensions/third_party/` 目录不存在，NodeEditorPack data.json 和 genshin_ts report.json 均不可用
- 注册表支持手动注册 + 文件加载降级（文件不存在时返回空）
- GraphBuilder 的 `to_numeric()` 生成的是纯节点图结构，不含 entity entry
- VarBase 构造是核心难点：不同 VarType 有不同的内部结构（field_1=类型, field_2=值）
- 验证器需要同时支持 numeric dict 和 GraphBuilder 两种输入格式

---

## 八、社区工具参考

| 工具 | 说明 |
|------|------|
| **genshin-ts** | TypeScript -> 节点图编译，支持直接注入 .gia 文件（https://github.com/josStorer/genshin-ts） |
| **NodeEditorPack** | 节点图和 GIA/GIL 文件格式的逆向工程数据，含 500+ 节点完整定义（https://github.com/Wu-Yijun/Genshin-Impact-Miliastra-Wonderland-Code-Node-Editor-Pack） |
| **Genshin-Impact-UGC-File-Converter** | GIA/GIL 文件格式转换工具 |

### 项目内的参考数据源

- `asset_bundle_builder_node_editor_pack.py` — 完整的 NEP data.json 消费代码
- `genshin_ts_node_schema.py` — 节点画像校验能力
- `refs/genshin_ts/genshin_ts__node_schema.report.json` — 另一个节点数据源

---

## 九、游戏目录结构（参考）

| 路径 | 内容 |
|------|------|
| `...\Resource\Json\Beyond\Node\` | 节点库（加密 .mihoyobin） |
| `...\Resource\Json\Beyond\Official\` | 官方蓝图/节点图 |
| `...\Resource\Json\Beyond\OfficialPrefab\` | 物件/造物配置 |
| `...\Resource\Json\Beyond\Struct\` | 结构体定义 |
| `...\Resource\Json\TextMap\CHS\` | 中文文本映射（加密） |

---

## 十、经验教训

### ⚠️ 不要用 CC/SubAgent 执行 git 操作

**事故**：2026-05-26，让 CC 修复测试回归时，CC 在 WSL 中执行了 `git stash` / `git reset` 等操作，导致 `.git` 目录丢失，本地所有 commit 历史丢失。

**根因**：CC/sub-agent 运行在 WSL 环境，对 Windows 文件系统（NTFS）上的 git 仓库操作可能有兼容性问题。CC 遇到冲突后尝试 `git reset` 清理，结果删除了 `.git`。

**教训**：
1. **永远不要让 CC/sub-agent 执行 git 操作**（commit、stash、reset、rebase 等）
2. 需要对比旧代码时，用 `git show HEAD~1:path` 等只读命令，或让 SOLO 本身执行
3. 定期 push 到远端，确保远端有完整历史备份
4. 如果必须让 CC 操作 git，先在本地备份 `.git` 目录
