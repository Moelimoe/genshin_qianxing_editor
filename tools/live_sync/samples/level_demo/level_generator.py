# -*- coding: utf-8 -*-
"""关卡生成器 v5 — 玩家实体变量方案（来自示例关卡）

关卡：「宝藏房间」
- 宝藏箱：碰撞 → 获取玩家实体 → 设置变量(钥匙数量=1) → 销毁
- 陷阱区：碰撞 → 损血 → 传送
- 胜利开关：碰撞 → 获取玩家实体 → 获取变量(钥匙数量) → 判断==1 → 胜利

用法: python -m tools.live_sync.level_generator
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
_PROJECT = Path(__file__).resolve().parents[4]
if str(_PROJECT) not in sys.path:
    sys.path.insert(0, str(_PROJECT))

_OUT = Path(__file__).resolve().parent

# 使用示例关卡中的物件 (loc_id 来自示例关卡资产.gia)
# 宝箱: 10005006, 坍塌石板: 20001033, 退出奇域装置: 10005022
LEVEL_GRAPHS = [
    (10005006, "宝藏箱",   "build_treasure"),  # 宝箱
    (20001033, "陷阱区",   "build_trap"),      # 坍塌石板
    (10005022, "胜利开关", "build_victory"),   # 退出奇域装置
]

VAR_NAME = "钥匙数量"  # 玩家变量名，需在编辑器中为玩家实体定义此属性


def build_treasure(g, catalog):
    """宝藏箱: 碰撞 → 获取玩家实体 → 设置变量=1 → 销毁"""
    n_evt  = g.add_node("进入碰撞触发器时")
    n_player = g.add_node(259)  # 纯数据节点，无 flow 端口
    n_set  = (g.add_node("设置自定义变量")
        .set_param("目标实体", None)   # 后续连线
        .set_param("变量名", VAR_NAME)
        .set_param("变量值", 1))
    n_destroy = g.add_node("销毁实体")

    g.connect_flow(n_evt, "出", n_set, "入")
    g.connect_flow(n_set, "出", n_destroy, "入")
    # 数据连线：事件→玩家实体→设置变量/销毁实体
    g.connect_data(n_evt, "进入者实体", n_player, "角色实体")
    g.connect_data(n_player, "所属玩家实体", n_set, "目标实体")
    g.connect_data(n_player, "所属玩家实体", n_destroy, "目标实体")


def build_trap(g, catalog):
    """陷阱区: 碰撞 → 损血50 → 传送回原点"""
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


def build_victory(g, catalog):
    """胜利开关: 碰撞 → 获取变量 → ==1则胜利"""
    n_evt   = g.add_node("进入碰撞触发器时")
    n_player = g.add_node(259)  # 纯数据节点，无 flow 端口
    n_get   = (g.add_node(50)  # type_id=50 服务端版本
        .set_param("目标实体", None)   # 后续连线
        .set_param("变量名", VAR_NAME))
    n_eq    = (g.add_node(14)   # type_id=14 服务端版本
        .set_param("输入1", None)      # 后续连线
        .set_param("输入2", 1))
    n_win   = g.add_node("结算关卡").set_param("是否胜利", True)
    n_branch = g.add_node(2)          # type_id=2 服务端双分支

    g.connect_flow(n_evt, "出", n_branch, "入")
    g.connect_flow(n_branch, "是", n_win, "入")
    # 数据连线：事件→玩家实体→获取变量→比较→分支
    g.connect_data(n_evt, "进入者实体", n_player, "角色实体")
    g.connect_data(n_player, "所属玩家实体", n_get, "目标实体")
    g.connect_data(n_get, "值", n_eq, "输入1")
    g.connect_data(n_eq, "结果", n_branch, "条件")


BUILDERS = {
    "build_treasure": build_treasure,
    "build_trap":     build_trap,
    "build_victory":  build_victory,
}


def generate_level():
    from tools.live_sync.level_builder import GraphBuilder, NodeCatalog
    from tools.live_sync.gia_utils import save_gia_numeric, get_entries, make_binary_name, load_gia_numeric
    from tools.live_sync.gia_viz import extract_graph, generate_html
    from pathlib import Path

    catalog = NodeCatalog.default()
    _OUT.mkdir(parents=True, exist_ok=True)

    # 加载示例关卡资产，提取原始 entity entry（保留完整结构）
    sample_level_path = Path('/mnt/h/myprojects/genshin_qianxing_editor/tools/live_sync/samples/export_examples/示例关卡资产.gia')
    sample_num = load_gia_numeric(sample_level_path)
    sample_entries = get_entries(sample_num)
    
    # 构建 loc_id → 原始 entity entry 映射（直接复制，保留完整结构）
    loc_id_to_raw_entity = {}
    for entry in sample_entries:
        if '11' in entry:
            f11 = entry.get('11', {})
            if isinstance(f11, dict) and '1' in f11:
                loc_id = f11['1'].get('2')
                if loc_id:
                    loc_id_to_raw_entity[loc_id] = entry

    all_num_entries, viz_graphs, labels = [], [], []

    for asset_key, name, fn_name in LEVEL_GRAPHS:
        g = GraphBuilder(name, catalog=catalog)
        BUILDERS[fn_name](g, catalog)

        # 获取 GraphBuilder 生成的 numeric
        gb_num = g.to_numeric()
        gb_entries = get_entries(gb_num)
        
        # 找到 NG entry
        ng_entry = None
        for e in gb_entries:
            if '13' in e:
                ng_entry = e
                break
        
        # 生成确定性 UID
        uid = 0x40000000 | (abs(hash(name + str(asset_key))) & 0x0FFFFFFF)
        
        # 直接从示例关卡复制 entity entry（保留完整结构）
        import copy
        if asset_key in loc_id_to_raw_entity:
            entity_entry = copy.deepcopy(loc_id_to_raw_entity[asset_key])
            # 更新 UID：field[1][4], field[11][1][1]
            entity_entry['1']['4'] = uid
            if '11' in entity_entry:
                f11 = entity_entry['11']
                if isinstance(f11, dict) and '1' in f11:
                    f11['1']['1'] = uid
            # field[2] 保持为空 dict（与示例关卡一致）
            entity_entry['2'] = {}
        else:
            # fallback：构建最小 entity
            entity_entry = {
                '1': {'2': 1, '3': 1, '4': uid},
                '2': {},
                '3': make_binary_name(f"{name}_entity"),
                '5': 1,
                '11': {
                    '1': {
                        '1': uid,
                        '2': asset_key,
                    },
                },
            }
        
        # 设置 NG entry
        ng_entry['3'] = make_binary_name(name)
        ng_entry['5'] = 9
        ng_f1 = ng_entry.setdefault('1', {})
        if isinstance(ng_f1, dict):
            ng_f1['4'] = uid
        ng_graph = ng_entry.get('13', {}).get('1', {}).get('1', {})
        if isinstance(ng_graph, dict):
            ng_graph['101'] = 0.3
            if '1' in ng_graph and isinstance(ng_graph['1'], dict):
                ng_graph['1']['5'] = uid
            
        # 顶层：list 包含 entity + ng
        final_num = {
            '1': [entity_entry, ng_entry],
            '3': make_binary_name(f"{name}.gia"),
        }
        
        # 直接收集原始 numeric entries（不做 decode/encode 往返）
        all_num_entries.extend(final_num['1'])
        labels.append(name)

        path = _OUT / f"{name}.gia"
        save_gia_numeric(final_num, path)
        print(f"  ✅ {name} (loc_id={asset_key})")

        gs = extract_graph(path)
        if gs: viz_graphs.append(gs[0])

    level_path = _OUT / "TreasureHunt_Demo.gia"
    level_num = {
        '1': all_num_entries,
        '3': make_binary_name("TreasureHunt_Demo.gia"),
        '5': make_binary_name("6.3.0"),  # 版本号（与示例关卡一致）
    }
    save_gia_numeric(level_num, level_path)
    print(f"\n  💾 完整关卡 → {level_path.name}")

    vdir = _OUT / "viz"; vdir.mkdir(exist_ok=True)
    for label, gr in zip(labels, viz_graphs):
        (vdir / f"{label}.html").write_text(generate_html(level_path, [gr]), encoding='utf-8')
        print(f"  📊 {label}.html")

    (_OUT / "README.md").write_text(f"""# 宝藏房间 v6 — 使用示例关卡物件

## 变量定义

需为玩家实体定义属性：
- 名称: `{VAR_NAME}`
- 类型: 整数
- 初始值: 0

## 物件（来自示例关卡）

| 物件 | asset_key | 来源 | 节点图 |
|------|-----------|------|--------|
| 宝藏箱 | 10005006 | 示例关卡-宝箱 | 碰撞 → 获取玩家 → 设变量=1 → 销毁 |
| 陷阱区 | 20001033 | 示例关卡-坍塌石板 | 碰撞 → 损血50 → 传送原点 |
| 胜利开关 | 10005022 | 示例关卡-退出奇域装置 | 碰撞 → 获取玩家 → 取变量 → ==1则胜利 |

## 游玩流程

1. 出生 → 走到宝藏箱 → 碰到 → 钥匙数量设为1 → 宝箱消失
2. （可选）避开陷阱区（坍塌石板）
3. 走到胜利开关（退出奇域装置）→ 检查钥匙数量==1 → 是则胜利

## 关键节点

- 获取角色归属的玩家实体(259): 从触发事件的角色获取玩家实体引用
- 设置自定义变量(22): 目标实体+变量名+值 → 写入玩家变量
- 获取自定义变量(50): 目标实体+变量名 → 读取玩家变量值
- 损失生命(697): 伤害量50，忽略防御否，是否致命否
- 传送玩家(288): 目标位置(0,0,0)
- 结算关卡(77): 是否胜利=True
""", encoding='utf-8')


if __name__ == "__main__":
    print("=" * 55)
    print("  关卡生成 v5: 宝藏房间（玩家变量）")
    print("=" * 55)
    generate_level()
    print("\n  完成！")
