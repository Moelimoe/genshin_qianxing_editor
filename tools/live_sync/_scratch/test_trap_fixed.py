# -*- coding: utf-8 -*-
"""快速测试：只生成陷阱区GIA，验证损失生命节点引脚修复

修复内容：
1. node_catalog.py: type_id=697 引脚定义更新（NODE_REFERENCE.md + node_library.json）
   - 数据引脚 index 从0开始
   - 添加缺失引脚：是否可被无敌抵挡、是否可被锁定生命值抵挡、伤害跳字类型
   - 引脚名修正：伤害量→生命损失量
2. node_catalog.py: type_id=288 传送玩家引脚定义更新
   - 添加缺失引脚：玩家实体、目标旋转
3. level_builder.py: _build_var_base 添加 Enum 类型处理（VarType=14）

运行: python _scratch/test_trap_fixed.py
"""
import sys
from pathlib import Path

_PROJECT = Path(__file__).resolve().parents[3]
if str(_PROJECT) not in sys.path:
    sys.path.insert(0, str(_PROJECT))

from tools.live_sync.level_builder import GraphBuilder, NodeCatalog
from tools.live_sync.gia_utils import save_gia_numeric

catalog = NodeCatalog.default()
OUT = Path(__file__).resolve().parent

def build_trap(g, catalog):
    n_evt = g.add_node("进入碰撞触发器时")
    n_dmg = (g.add_node("损失生命")
        .set_param("生命损失量", 50.0)
        .set_param("是否致命", False)
        .set_param("是否可被无敌抵挡", False)
        .set_param("是否可被锁定生命值抵挡", False)
        .set_param("伤害跳字类型", 5401))  # 无跳字
    n_tp = (g.add_node("传送玩家")
        .set_param("目标位置", [0.0, 0.0, 0.0])
        .set_param("目标旋转", [0.0, 0.0, 0.0]))
    g.connect_flow(n_evt, "出", n_dmg, "入")
    g.connect_flow(n_dmg, "出", n_tp, "入")

g = GraphBuilder("陷阱区", catalog=catalog)
build_trap(g, catalog)

# 直接用 to_numeric() 输出（已包含 entity + NG）
num = g.to_numeric()

path = OUT / "_test_trap_fixed.gia"
save_gia_numeric(num, path)
print(f"Generated: {path}")
