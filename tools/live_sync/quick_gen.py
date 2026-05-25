# -*- coding: utf-8 -*-
"""快速节点图生成器 —— 一行命令生成 GIA + 可视化 HTML

用于单个节点的快速验证：对比沙箱时，生成节点图并立即预览。

用法:
  # 最简单的单节点
  python -m tools.live_sync.quick_gen 多分支

  # 带参数
  python -m tools.live_sync.quick_gen 创建实体 --param 目标GUID:50001 --param 单位标签索引列表:[1,2]

  # 两个节点 + 连线
  python -m tools.live_sync.quick_gen 监听信号 发送信号 --connect 监听信号:出:发送信号:入

  # 指定输出路径
  python -m tools.live_sync.quick_gen 多分支 -o my_test

  # 列出所有可用节点
  python -m tools.live_sync.quick_gen --list
"""

import argparse
import json
import sys
from pathlib import Path

_PROJECT = Path(__file__).resolve().parents[2]
_OUT = _PROJECT / "tools" / "live_sync" / "samples" / "quick"


def parse_param(raw: str):
    """解析 'key:value' 格式参数"""
    if ":" not in raw:
        return raw, True  # bool flag
    key, val = raw.split(":", 1)
    # 尝试解析为 JSON（列表、数字等）
    try:
        return key, json.loads(val)
    except (json.JSONDecodeError, ValueError):
        return key, val


def parse_connect(raw: str):
    """解析 'src:src_port:dst:dst_port' 格式连线"""
    parts = raw.split(":")
    if len(parts) != 4:
        raise ValueError(f"连线格式应为 源节点:源端口:目标节点:目标端口，得到: {raw}")
    return tuple(parts)


def list_nodes():
    from tools.live_sync.level_builder import NodeCatalog
    catalog = NodeCatalog.default()
    print(f"\n{'可用节点':—^60}")
    print(f"共 {len(catalog._by_name)} 个节点\n")
    for nd in sorted(catalog._by_name.values(), key=lambda n: (n.category, n.name)):
        tag = " [弃用]" if nd.deprecated else ""
        print(f"  [{nd.category:10s}] {nd.name:16s}  type_id={nd.type_id}{tag}")
    print()


def main():
    parser = argparse.ArgumentParser(description="快速生成 GIA 节点图 + 可视化")
    parser.add_argument("nodes", nargs="*", help="节点名称（按连线顺序依次创建）")
    parser.add_argument("--param", "-p", action="append", default=[],
                        help="参数 key:value，可多次使用（对最后一个创建的节点设置）")
    parser.add_argument("--connect", "-c", action="append", default=[],
                        help="连线 源:源端口:目标:目标端口")
    parser.add_argument("--output", "-o", default=None, help="输出文件名前缀（不含扩展名）")
    parser.add_argument("--list", "-l", action="store_true", help="列出所有可用节点")
    args = parser.parse_args()

    if args.list:
        list_nodes()
        return

    if not args.nodes:
        parser.print_help()
        print("\n💡 试试 --list 查看所有可用节点")
        return

    from tools.live_sync.level_builder import GraphBuilder, NodeCatalog
    from tools.live_sync.gia_viz import extract_graph, generate_html

    catalog = NodeCatalog.default()
    _OUT.mkdir(parents=True, exist_ok=True)

    name = args.output or "_".join(args.nodes)
    safe_name = name.replace(" ", "_").replace(":", "_")

    g = GraphBuilder(safe_name, catalog=catalog)
    node_map = {}

    # 创建节点
    for node_name in args.nodes:
        n = g.add_node(node_name)
        node_map[node_name] = n

    # 设置参数（对所有当前节点）
    for node_name in args.nodes:
        n = node_map[node_name]
        for p in args.param:
            if ":" in p:
                key, val = parse_param(p)
                try:
                    n.set_param(key, val)
                except ValueError:
                    pass  # 参数不属于这个节点，跳过

    # 创建连线
    for c in args.connect:
        src, src_port, dst, dst_port = parse_connect(c)
        g.connect_flow(node_map[src], src_port, node_map[dst], dst_port)

    # 生成 GIA
    gia_path = _OUT / f"{safe_name}.gia"
    g.to_gia(gia_path)

    # 生成可视化
    graphs = extract_graph(gia_path)
    html = generate_html(gia_path, graphs)
    viz_path = _OUT / f"{safe_name}.html"
    viz_path.write_text(html, encoding="utf-8")

    print(f"\n✅ 已生成:")
    print(f"   GIA: {gia_path}")
    print(f"   Viz: {viz_path}")
    print(f"   节点: {len(args.nodes)} | 连线: {len(args.connect)}")


if __name__ == "__main__":
    main()
