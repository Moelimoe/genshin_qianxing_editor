# -*- coding: utf-8 -*-
"""生成测试用的GIA文件"""
import sys
sys.path.insert(0, 'h:\\myprojects\\genshin_qianxing_editor')

from pathlib import Path
from tools.live_sync.level_builder import GraphBuilder, LevelBuilder
from tools.live_sync.node_catalog import NodeCatalog

# 创建输出目录
output_dir = Path('h:/myprojects/genshin_qianxing_editor/test_gias_new')
output_dir.mkdir(exist_ok=True)

# 创建默认catalog
catalog = NodeCatalog.default()

# 测试1: 简单的发送信号节点
print("生成测试1: 发送信号...")
g1 = GraphBuilder("test_01_send_signal", catalog=catalog)
node1 = g1.add_node("发送信号")
node1.set_param("信号名", "TestSignal")
g1.to_gia(output_dir / "test_01_send_signal.gia")
print(f"  ✓ 节点数: {g1.node_count()}, type_id: {node1.type_id}")

# 测试2: 多分支节点
print("生成测试2: 多分支...")
g2 = GraphBuilder("test_02_multi_branch", catalog=catalog)
node2 = g2.add_node("多分支")
node2.set_param("条件", 1)
g2.to_gia(output_dir / "test_02_multi_branch.gia")
print(f"  ✓ 节点数: {g2.node_count()}, type_id: {node2.type_id}")

# 测试3: 创建元件节点
print("生成测试3: 创建元件...")
g3 = GraphBuilder("test_03_create_prefab", catalog=catalog)
node3 = g3.add_node("创建元件")
node3.set_param("元件ID", 12345)
node3.set_param("位置", [0.0, 0.0, 0.0])
g3.to_gia(output_dir / "test_03_create_prefab.gia")
print(f"  ✓ 节点数: {g3.node_count()}, type_id: {node3.type_id}")

# 测试4: 监听信号 + 发送信号 连线
print("生成测试4: 监听信号 -> 发送信号...")
g4 = GraphBuilder("test_04_listen_send", catalog=catalog)
listen = g4.add_node("监听信号")
listen.set_param("信号名", "MyEvent")
send = g4.add_node("发送信号")
send.set_param("信号名", "Response")
# 连接流程
g4.connect_flow(listen, "出", send, "入")
g4.to_gia(output_dir / "test_04_listen_send.gia")
print(f"  ✓ 节点数: {g4.node_count()}, 连线数: {len(g4._connections)}")

# 测试5: 多分支 + 创建元件
print("生成测试5: 多分支 -> 创建元件...")
g5 = GraphBuilder("test_05_branch_create", catalog=catalog)
branch = g5.add_node("多分支")
branch.set_param("条件", 0)
create = g5.add_node("创建元件")
create.set_param("元件ID", 99999)
create.set_param("位置", [100.0, 200.0, 300.0])
# 连接: 分支0 -> 创建元件
g5.connect_flow(branch, "分支0", create, "入")
g5.to_gia(output_dir / "test_05_branch_create.gia")
print(f"  ✓ 节点数: {g5.node_count()}, 连线数: {len(g5._connections)}")

# 测试6: 复杂组合 - 监听信号 -> 多分支 -> (分支0:发送信号, 分支1:创建元件)
print("生成测试6: 复杂组合...")
g6 = GraphBuilder("test_06_complex", catalog=catalog)
listen6 = g6.add_node("监听信号")
listen6.set_param("信号名", "StartGame")
branch6 = g6.add_node("多分支")
branch6.set_param("条件", 1)
send6 = g6.add_node("发送信号")
send6.set_param("信号名", "Branch0Triggered")
create6 = g6.add_node("创建元件")
create6.set_param("元件ID", 11111)
create6.set_param("位置", [500.0, 0.0, 0.0])
# 连线
g6.connect_flow(listen6, "出", branch6, "入")
g6.connect_flow(branch6, "分支0", send6, "入")
g6.connect_flow(branch6, "分支1", create6, "入")
g6.to_gia(output_dir / "test_06_complex.gia")
print(f"  ✓ 节点数: {g6.node_count()}, 连线数: {len(g6._connections)}")

print(f"\n所有测试文件已生成到: {output_dir}")
print("文件列表:")
for f in sorted(output_dir.glob("*.gia")):
    size = f.stat().st_size
    print(f"  - {f.name} ({size} bytes)")
