# -*- coding: utf-8 -*-
"""典型关卡用例生成器 —— 模拟常见关卡逻辑的节点图

用途：
  1. 生成接近真实使用的 GIA 节点图，供沙箱验证
  2. 自动生成可视化 HTML，方便快速预览
  3. 只使用简单的流程连线（复杂逻辑等节点确认后再补）
"""

import json
from pathlib import Path

_PROJECT = Path(__file__).resolve().parents[2]
_OUT = _PROJECT / "tools" / "live_sync" / "samples" / "examples"
_VIZ = _OUT / "viz"

# ═══════════════════════════════════════════
# 用例定义 — (名称, 节点列表, 连线列表, 描述)
# 节点: (节点名, {参数})
# 连线: (源节点名, 源端口, 目标节点名, 目标端口)
# ═══════════════════════════════════════════

EXAMPLES = [
    # ── 1. 触碰宝箱 → 获得道具 + 音效 ──
    ("宝箱拾取", [
        ("玩家进入触发器", {}),
        ("添加道具", {"道具ID": 11001, "数量": 1}),
        ("播放音效", {"音效ID": 8001}),
    ], [
        ("玩家进入触发器", "出", "添加道具", "入"),
        ("添加道具", "出", "播放音效", "入"),
    ], "触碰宝箱→获得道具→播放音效"),

    # ── 2. 定时刷怪 ──
    ("定时刷怪", [
        ("关卡开始时", {}),
        ("启动定时器", {"时长(秒)": 5.0}),
        ("定时器触发时", {}),
        ("创建实体", {"目标GUID": 50001}),
    ], [
        ("关卡开始时", "出", "启动定时器", "入"),
        ("定时器触发时", "出", "创建实体", "入"),
    ], "关卡开始→启动定时器→定时触发→创建实体"),

    # ── 3. 触碰传送门 ──
    ("传送门", [
        ("玩家进入触发器", {}),
        ("传送玩家", {"目标位置": [50.0, 10.0, 30.0]}),
        ("播放特效", {"特效ID": 9001, "位置": [50.0, 10.0, 30.0]}),
    ], [
        ("玩家进入触发器", "出", "传送玩家", "入"),
        ("传送玩家", "出", "播放特效", "入"),
    ], "进入触发器→传送→特效"),

    # ── 4. 击败敌人后结算 ──
    ("击败结算", [
        ("实体移除/销毁时", {}),
        ("结算关卡", {"是否胜利": True}),
    ], [
        ("实体移除/销毁时", "出", "结算关卡", "入"),
    ], "敌人被销毁→结算胜利"),

    # ── 5. 触碰开关 → 显隐 + 动画 ──
    ("机关开门", [
        ("玩家进入触发器", {}),
        ("设置实体可见性", {"可见": False}),
        ("播放动画", {"动画名": "open_door"}),
    ], [
        ("玩家进入触发器", "出", "设置实体可见性", "入"),
        ("设置实体可见性", "出", "播放动画", "入"),
    ], "进入触发器→隐藏物件→播放开启动画"),

    # ── 6. 陷阱：碰撞扣血 + 传送回起点 ──
    ("陷阱扣血传送", [
        ("实体碰撞时", {}),
        ("损失生命", {"伤害量": 50.0}),
        ("传送玩家", {"目标位置": [0.0, 0.0, 0.0]}),
    ], [
        ("实体碰撞时", "出", "损失生命", "入"),
        ("损失生命", "出", "传送玩家", "入"),
    ], "碰撞→扣血→传送回起点"),
]


# ═══════════════════════════════════════════
# 生成逻辑
# ═══════════════════════════════════════════

def generate_all():
    from tools.live_sync.level_builder import GraphBuilder, NodeCatalog
    from tools.live_sync.gia_viz import extract_graph, generate_html

    catalog = NodeCatalog.default()
    _OUT.mkdir(parents=True, exist_ok=True)
    _VIZ.mkdir(parents=True, exist_ok=True)

    results = []

    for name, nodes_def, conns_def, desc in EXAMPLES:
        safe_name = name.replace(" ", "_")
        gia_path = _OUT / f"{safe_name}.gia"

        try:
            g = GraphBuilder(safe_name, catalog=catalog)
            node_map = {}

            for node_name, params in nodes_def:
                n = g.add_node(node_name)
                for k, v in params.items():
                    n.set_param(k, v)
                node_map[node_name] = n

            for src_name, src_port, dst_name, dst_port in conns_def:
                g.connect_flow(node_map[src_name], src_port, node_map[dst_name], dst_port)

            g.to_gia(gia_path)

            # 生成可视化
            graphs = extract_graph(gia_path)
            html = generate_html(gia_path, graphs)
            viz_path = _VIZ / f"{safe_name}.html"
            viz_path.write_text(html, encoding='utf-8')

            results.append((name, True, str(gia_path), str(viz_path), ""))
            print(f"  ✅ {name:12s} → {gia_path.name} (+ {viz_path.name})")

        except Exception as e:
            import traceback
            results.append((name, False, str(gia_path), "", f"{type(e).__name__}: {e}"))
            print(f"  ❌ {name:12s} 失败: {e}")
            traceback.print_exc()

    # 汇总
    passed = sum(1 for r in results if r[1])
    print(f"\n{'='*50}")
    print(f"  用例生成完成: {passed}/{len(results)} 通过")
    print(f"  GIA 文件 → {_OUT}")
    print(f"  可视化   → {_VIZ}")
    return results


def dump_catalog_json():
    """输出当前节点目录的 JSON 摘要，方便查看已有哪些节点可用"""
    from tools.live_sync.level_builder import NodeCatalog
    catalog = NodeCatalog.default()
    nodes = []
    for nd in catalog._by_name.values():
        nodes.append({
            "type_id": nd.type_id,
            "name": nd.name,
            "category": nd.category,
            "description": nd.description,
            "deprecated": nd.deprecated,
            "input_count": len(nd.inputs),
            "output_count": len(nd.outputs),
            "has_node_params": len(nd.node_params) > 0,
        })
    path = _OUT / "_catalog_snapshot.json"
    path.write_text(json.dumps(nodes, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"  📋 节点快照 → {path}")


if __name__ == "__main__":
    print("生成典型关卡用例...\n")
    generate_all()
    print()
    dump_catalog_json()
