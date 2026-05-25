# GIA 可视化开发进展笔记

## 当前状态

### 已完成
1. ✅ 基础可视化框架（gia_viz.py）
2. ✅ 节点 catalog 定义（部分节点已修正）
3. ✅ src_pin_index 计数方式验证（只在 OUT_PARAM 中计数）
4. ✅ 连线匹配逻辑（有 src_pin_index 按索引匹配，无则按类型推断）
5. ✅ var_base 编码格式分析（值存储在 field[101/104/105/106/107] 中）
6. ✅ _decode_var_base 函数更新（支持 Int/Str/Bool/Float/Vec/Cfg 类型）
7. ✅ 引脚补充逻辑（_supplement_missing_pins）
8. ✅ 引脚排序（按 catalog index 排序）

### 当前问题

#### 问题1：引脚索引不完整导致匹配错位

**现象**：节点7（播放限时特效）的"挂接点名称"显示值为 `:3`（实际应为 `G1_RootNode`）

**原因**：GIA 中部分引脚的 `gia_idx=None`，导致 `_assign_pin_names` 按顺序分配时错位

**GIA 引脚数据**：
```
Pin0: OUT_FLOW, gia_idx=None
Pin1: IN_PARAM, gia_idx=None, has_value=True  ← 特效资产=3
Pin2: IN_PARAM, gia_idx=1, has_value=False    ← 目标实体
Pin3: IN_PARAM, gia_idx=2, has_value=True     ← 挂接点名称=G1_RootNode
Pin4: IN_PARAM, gia_idx=5, has_value=True     ← 是否跟随目标旋转
Pin5: IN_PARAM, gia_idx=6, has_value=True     ← 位置偏移
Pin6: IN_PARAM, gia_idx=7, has_value=True     ← 旋转偏移
```

**Catalog 定义**：
```
index=0: 入 (flow)
index=1: 特效资产
index=2: 目标实体
index=3: 挂接点名称
index=4: 是否跟随目标运动
index=5: 是否跟随目标旋转
index=6: 位置偏移
index=7: 旋转偏移
index=8: 缩放倍率
index=9: 是否播放自带的音效
```

**问题分析**：
- Pin1 的 `gia_idx=None`，但有值（特效资产=3）
- Pin2-3 的 `gia_idx=1,2` 与 catalog index=1,2 匹配
- 但 Pin1 没有匹配到任何 catalog 引脚，导致按顺序分配到 index=1（特效资产）
- Pin3 的值（G1_RootNode）被分配到了错误的引脚

**修复方案**：
1. 对于 `gia_idx=None` 的引脚，尝试用值的类型（var_type）匹配 catalog 中未使用的引脚
2. 如果 var_type 也无法确定，按引脚在 GIA 中的顺序和 catalog 中未分配的引脚顺序匹配

## var_base 编码格式总结

```
{
    "1": type_code,           # 类型代码
    "2": 1,                   # 未知标志
    "4": {                    # 类型描述
        "1": 1,
        "100": {"1": var_type}  # var_type 在嵌套中
    },
    "XXX": {"1": value}       # 值存储字段（按类型不同）
}
```

### 值字段映射

| var_type | 类型名 | 值字段 | 示例 |
|----------|--------|--------|------|
| 0 | 泛型/Cfg | 101 | 3 |
| 3 | Int | 101 | 42 |
| 4 | Bool | 106 | True/空 |
| 5 | Float | 104 | 1.0 |
| 6 | Str | 105 | "G1_RootNode"（二进制） |
| 12 | Vec | 107 | (0, 0, 20)（二进制） |
| 20 | Cfg | 101 | 3 |

## 下一步

1. 修复 `_assign_pin_names` 的引脚匹配逻辑
2. 验证所有节点图的数据值正确显示
3. 生成完整的可视化图供用户验证
