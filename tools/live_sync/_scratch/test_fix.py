# -*- coding: utf-8 -*-
"""测试 CC 修复后的代码"""
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.live_sync.level_builder import _build_var_base, GraphBuilder
from tools.live_sync.node_catalog import VarType
from tools.live_sync.gia_utils import save_gia_numeric

def test_int_var_base():
    """测试 Int VarBase 编码（关键修复）"""
    print("=" * 60)
    print("测试 Int VarBase 编码")
    print("=" * 60)

    # 有值的 Int
    vb_with_value = _build_var_base(VarType.Int, 42)
    print(f"\nInt with value=42:")
    print(f"  tag = {vb_with_value.get('1')} (应该是 10000)")
    print(f"  has field[110] = {'110' in vb_with_value}")
    if '110' in vb_with_value:
        inner = vb_with_value['110'].get('2', {})
        print(f"  inner tag = {inner.get('1')} (应该是 2)")
        print(f"  inner field[102] = {inner.get('102')}")

    # 空值的 Int（用于输出引脚）
    vb_empty = _build_var_base(VarType.Int, None)
    print(f"\nInt with value=None:")
    print(f"  tag = {vb_empty.get('1')} (应该是 10000)")
    print(f"  has field[110] = {'110' in vb_empty}")
    if '110' in vb_empty:
        inner = vb_empty['110'].get('2', {})
        print(f"  inner field[102] = {inner.get('102')} (应该是 binary_data)")

    # 验证 tag=10000
    assert vb_with_value['1'] == 10000, f"Expected tag=10000, got {vb_with_value['1']}"
    assert vb_empty['1'] == 10000, f"Expected tag=10000, got {vb_empty['1']}"
    print("\n✅ Int VarBase 编码正确！")

def test_simple_graph():
    """测试简单节点图生成"""
    print("\n" + "=" * 60)
    print("测试简单节点图")
    print("=" * 60)

    from tools.live_sync.node_catalog import NodeCatalog

    catalog = NodeCatalog()
    g = GraphBuilder("test_fix", catalog=catalog)

    # 添加节点（使用 type_id 避免名称查找问题）
    n1 = g.add_node(type_id=100001)  # 关卡开始时
    n2 = g.add_node(type_id=22)  # 设置自定义变量
    n2.set_param("变量名", "test_var")
    n2.set_param("变量值", 100)

    # 连线
    n1.connect_flow("输出流程", n2, "输入流程")

    # 导出
    output_path = Path(__file__).parent / "test_fix_output.gia"
    g.to_gia(output_path)
    print(f"\n生成测试文件: {output_path}")

    # 检查结构
    num = g.to_numeric()
    entries = num.get('1', [])
    print(f"\nEntries count: {len(entries)}")

    # 找到 NG entry
    ng_entry = None
    for e in entries:
        if e.get('5') == 9:  # NodeGraph entry
            ng_entry = e
            break

    if ng_entry:
        graph = ng_entry.get('13', {}).get('1', {}).get('1', {})
        nodes = graph.get('3', [])
        print(f"Nodes count: {len(nodes)}")

        # 检查设置自定义变量节点 (type_id=22)
        for node in nodes:
            type_id = node.get('2', {}).get('5')
            if type_id == 22:
                print(f"\n节点 '设置自定义变量' (type_id=22):")
                pins = node.get('4', [])
                if isinstance(pins, dict):
                    pins = [pins]
                print(f"  Pins count: {len(pins)}")

                for i, pin in enumerate(pins):
                    sig = pin.get('1', {})
                    kind = sig.get('1')
                    idx = sig.get('2', 'N/A')
                    has_vb = '3' in pin
                    print(f"  Pin {i}: kind={kind}, sig2={idx}, has_varbase={has_vb}")

    print("\n✅ 简单节点图测试完成！")

if __name__ == "__main__":
    test_int_var_base()
    test_simple_graph()
    print("\n" + "=" * 60)
    print("所有测试完成！")
    print("=" * 60)
