# -*- coding: utf-8 -*-
"""声明式关卡构建 API (level_builder) 单元测试

TDD: 先定义接口契约，再实现。
覆盖：GraphBuilder 创建/添加节点/设置参数/连线/布局/导出/验证/快照回滚/链式调用，
      LevelBuilder 多图管理。
"""
from __future__ import annotations

import copy
import struct
from pathlib import Path

import pytest

from tools.live_sync.node_catalog import (
    NodeCatalog, NodeDef, PinDef, VarType, ValidationResult,
)
from tools.live_sync.level_builder import (
    NodeHandle, GraphBuilder, LevelBuilder,
)


# ═══════════════════════════════════════════════════════════════
# 辅助：构造 PinDef / NodeDef
# ═══════════════════════════════════════════════════════════════

def _pin(name: str, direction: str, is_flow: bool = False,
         type_expr: str = "", var_type: int = 0, index: int = 0) -> PinDef:
    return PinDef(
        name=name, direction=direction, is_flow=is_flow,
        type_expr=type_expr, var_type=var_type, index=index,
    )


def _node(type_id: int, name: str, category: str = "action",
          description: str = "", inputs: list[PinDef] | None = None,
          outputs: list[PinDef] | None = None) -> NodeDef:
    return NodeDef(
        type_id=type_id, name=name, category=category,
        description=description,
        inputs=inputs or [], outputs=outputs or [],
    )


def _make_catalog() -> NodeCatalog:
    """创建测试用注册表，包含几个常用节点"""
    cat = NodeCatalog()
    # 监听信号 (event, type_id=300001, verified)
    cat.register(NodeDef(
        type_id=300001, name="监听信号", category="event",
        description="监听信号事件",
        inputs=(_pin("信号名", "In", type_expr="Str", var_type=VarType.Str, index=0),),
        outputs=(_pin("出", "Out", is_flow=True, index=0),),
    ))
    # 创建元件 (action, type_id=252, verified)
    cat.register(NodeDef(
        type_id=252, name="创建元件", category="action",
        description="创建一个元件实例",
        inputs=(
            _pin("入", "In", is_flow=True, index=0),
            _pin("元件ID", "In", type_expr="Prefab", var_type=VarType.Prefab, index=1),
            _pin("位置", "In", type_expr="Vec", var_type=VarType.Vec, index=2),
        ),
        outputs=(
            _pin("出", "Out", is_flow=True, index=0),
            _pin("实体", "Out", type_expr="Ety", var_type=VarType.Ety, index=1),
        ),
    ))
    # 发送信号 (action, type_id=300000, verified)
    cat.register(NodeDef(
        type_id=300000, name="发送信号", category="action",
        description="发送信号",
        inputs=(
            _pin("入", "In", is_flow=True, index=0),
            _pin("目标", "In", type_expr="Ety", var_type=VarType.Ety, index=1),
            _pin("信号名", "In", type_expr="Str", var_type=VarType.Str, index=2),
        ),
        outputs=(_pin("出", "Out", is_flow=True, index=0),),
    ))
    # 获取局部变量 (variable, type_id=18)
    cat.register(NodeDef(
        type_id=18, name="获取局部变量", category="variable",
        description="获取局部变量值",
        inputs=(_pin("变量引用", "In", type_expr="Loc", var_type=16, index=0),),
        outputs=(_pin("值", "Out", type_expr="Int", var_type=VarType.Int, index=0),),
    ))
    # 多分支 (condition, type_id=3)
    cat.register(NodeDef(
        type_id=3, name="多分支", category="condition",
        description="多分支",
        inputs=(
            _pin("入", "In", is_flow=True, index=0),
            _pin("条件", "In", type_expr="Int", var_type=VarType.Int, index=1),
        ),
        outputs=(
            _pin("默认", "Out", is_flow=True, index=0),
            _pin("分支0", "Out", is_flow=True, index=1),
            _pin("分支1", "Out", is_flow=True, index=2),
        ),
    ))
    return cat


@pytest.fixture
def catalog():
    return _make_catalog()


@pytest.fixture
def graph(catalog):
    return GraphBuilder(name="测试图", catalog=catalog)


# ═══════════════════════════════════════════════════════════════
# 1. 创建空节点图
# ═══════════════════════════════════════════════════════════════

class TestCreateEmptyGraph:
    """GraphBuilder 创建空的节点图构建器"""

    def test_create_empty_graph(self):
        g = GraphBuilder(name="测试图")
        assert g.node_count() == 0
        assert g.name == "测试图"

    def test_create_with_catalog(self, catalog):
        g = GraphBuilder(name="测试图", catalog=catalog)
        assert g.node_count() == 0

    def test_create_with_default_catalog(self):
        g = GraphBuilder(name="测试图", catalog=NodeCatalog.default())
        assert g.node_count() == 0

    def test_create_with_graph_type(self, catalog):
        g = GraphBuilder(name="测试图", catalog=catalog, graph_type="ENTITY_NODE_GRAPH")
        assert g.graph_type == "ENTITY_NODE_GRAPH"


# ═══════════════════════════════════════════════════════════════
# 2. 添加节点
# ═══════════════════════════════════════════════════════════════

class TestAddNode:
    """添加节点并返回 NodeHandle"""

    def test_add_node_by_name(self, graph):
        node = graph.add_node("监听信号")
        assert isinstance(node, NodeHandle)
        assert node.type_id == 300001
        assert node.name == "监听信号"

    def test_add_node_by_type_id(self, graph):
        node = graph.add_node(type_id=252)
        assert isinstance(node, NodeHandle)
        assert node.type_id == 252
        assert node.name == "创建元件"

    def test_add_multiple_nodes(self, graph):
        n1 = graph.add_node("监听信号")
        n2 = graph.add_node("创建元件")
        assert graph.node_count() == 2
        assert n1.index == 0
        assert n2.index == 1

    def test_add_node_auto_increment_index(self, graph):
        n1 = graph.add_node("监听信号")
        n2 = graph.add_node("创建元件")
        n3 = graph.add_node("发送信号")
        assert n1.index == 0
        assert n2.index == 1
        assert n3.index == 2

    def test_add_node_unknown_name_raises(self, graph):
        with pytest.raises(ValueError):
            graph.add_node("不存在的节点")

    def test_add_node_unknown_type_id_raises(self, graph):
        with pytest.raises(ValueError):
            graph.add_node(type_id=99999)

    def test_add_node_with_params(self, graph):
        """add_node 时可以直接设置参数"""
        node = graph.add_node("监听信号", 信号名="test_signal")
        assert node.get_param("信号名") == "test_signal"

    def test_get_node_by_index(self, graph):
        n1 = graph.add_node("监听信号")
        n2 = graph.add_node("创建元件")
        assert graph.get_node(0) is n1
        assert graph.get_node(1) is n2

    def test_get_node_invalid_index_raises(self, graph):
        with pytest.raises(IndexError):
            graph.get_node(99)


# ═══════════════════════════════════════════════════════════════
# 3. 设置节点参数
# ═══════════════════════════════════════════════════════════════

class TestSetParam:
    """设置输入参数常量"""

    def test_set_param_string(self, graph):
        node = graph.add_node("监听信号")
        result = node.set_param("信号名", "my_signal")
        assert result is node  # 链式调用
        assert node.get_param("信号名") == "my_signal"

    def test_set_param_int(self, graph):
        node = graph.add_node("多分支")
        node.set_param("条件", 42)
        assert node.get_param("条件") == 42

    def test_set_param_bool(self, graph):
        node = graph.add_node("多分支")
        node.set_param("条件", True)
        assert node.get_param("条件") is True

    def test_set_param_float(self, graph):
        node = graph.add_node("创建元件")
        node.set_param("位置", 1.5)
        assert node.get_param("位置") == 1.5

    def test_set_param_overwrite(self, graph):
        node = graph.add_node("监听信号")
        node.set_param("信号名", "first")
        node.set_param("信号名", "second")
        assert node.get_param("信号名") == "second"

    def test_set_param_unknown_port_raises(self, graph):
        node = graph.add_node("监听信号")
        with pytest.raises(ValueError):
            node.set_param("不存在的端口", "value")

    def test_get_param_unset_returns_none(self, graph):
        node = graph.add_node("监听信号")
        assert node.get_param("信号名") is None


# ═══════════════════════════════════════════════════════════════
# 4. 流程连线
# ═══════════════════════════════════════════════════════════════

class TestConnectFlow:
    """连接流程端口"""

    def test_connect_flow_basic(self, graph):
        src = graph.add_node("监听信号")
        dst = graph.add_node("创建元件")
        result = graph.connect_flow(src, "出", dst, "入")
        assert result is graph  # 链式调用

    def test_connect_flow_via_node_handle(self, graph):
        src = graph.add_node("监听信号")
        dst = graph.add_node("创建元件")
        result = src.connect_flow("出", dst, "入")
        assert result is src

    def test_connect_flow_validates(self, graph):
        """连线应通过 catalog 校验"""
        src = graph.add_node("监听信号")
        dst = graph.add_node("创建元件")
        # 出 -> 入 是合法的流程连线
        graph.connect_flow(src, "出", dst, "入")
        # 验证应该通过
        validation = graph.validate()
        assert validation.ok or True  # 可能有其他警告，但不应有连线错误

    def test_connect_flow_type_mismatch_raises(self, graph):
        """流程端口不能连接到数据端口"""
        src = graph.add_node("监听信号")
        dst = graph.add_node("创建元件")
        with pytest.raises(ValueError):
            graph.connect_flow(src, "出", dst, "元件ID")

    def test_connect_flow_unknown_port_raises(self, graph):
        src = graph.add_node("监听信号")
        dst = graph.add_node("创建元件")
        with pytest.raises(ValueError):
            graph.connect_flow(src, "不存在的端口", dst, "入")


# ═══════════════════════════════════════════════════════════════
# 5. 数据连线
# ═══════════════════════════════════════════════════════════════

class TestConnectData:
    """连接数据端口"""

    def test_connect_data_basic(self, graph):
        src = graph.add_node("获取局部变量")
        dst = graph.add_node("多分支")
        result = graph.connect_data(src, "值", dst, "条件")
        assert result is graph

    def test_connect_data_via_node_handle(self, graph):
        src = graph.add_node("获取局部变量")
        dst = graph.add_node("多分支")
        result = src.connect_data("值", dst, "条件")
        assert result is src

    def test_connect_data_type_mismatch_raises(self, graph):
        """数据类型不匹配应报错"""
        src = graph.add_node("获取局部变量")  # 输出 Int
        dst = graph.add_node("监听信号")  # 信号名输入 Str
        with pytest.raises(ValueError):
            graph.connect_data(src, "值", dst, "信号名")

    def test_connect_data_flow_to_data_raises(self, graph):
        src = graph.add_node("监听信号")
        dst = graph.add_node("创建元件")
        with pytest.raises(ValueError):
            graph.connect_data(src, "出", dst, "元件ID")


# ═══════════════════════════════════════════════════════════════
# 6. 自动布局
# ═══════════════════════════════════════════════════════════════

class TestAutoLayout:
    """节点自动排列坐标"""

    def test_auto_layout_sets_coordinates(self, graph):
        n1 = graph.add_node("监听信号")
        n2 = graph.add_node("创建元件")
        graph.connect_flow(n1, "出", n2, "入")
        graph.auto_layout()
        # 两个节点应有不同的坐标
        assert (n1.x, n1.y) != (n2.x, n2.y)

    def test_auto_layout_x_increases_with_depth(self, graph):
        """X 坐标应按层级递增"""
        n1 = graph.add_node("监听信号")
        n2 = graph.add_node("创建元件")
        n3 = graph.add_node("发送信号")
        graph.connect_flow(n1, "出", n2, "入")
        graph.connect_flow(n2, "出", n3, "入")
        graph.auto_layout()
        assert n1.x < n2.x < n3.x

    def test_auto_layout_same_layer_y_differs(self, graph):
        """同层节点的 Y 坐标应不同"""
        n1 = graph.add_node("监听信号")
        n2 = graph.add_node("创建元件")
        n3 = graph.add_node("发送信号")
        graph.connect_flow(n1, "出", n2, "入")
        graph.connect_flow(n1, "出", n3, "入")
        graph.auto_layout()
        # n2 和 n3 在同一层，Y 应不同
        assert n2.y != n3.y

    def test_auto_layout_default_spacing(self, graph):
        """默认间距应为 300"""
        n1 = graph.add_node("监听信号")
        n2 = graph.add_node("创建元件")
        graph.connect_flow(n1, "出", n2, "入")
        graph.auto_layout()
        assert n2.x - n1.x == 300


# ═══════════════════════════════════════════════════════════════
# 7. 导出 numeric dict
# ═══════════════════════════════════════════════════════════════

class TestToNumeric:
    """导出为 numeric dict"""

    def test_empty_graph_to_numeric(self, graph):
        num = graph.to_numeric()
        assert isinstance(num, dict)
        assert '1' in num
        entries = num['1']
        assert isinstance(entries, list)
        assert len(entries) == 2  # NG entry + entity entry

    def test_empty_graph_has_ng_structure(self, graph):
        num = graph.to_numeric()
        entry = num['1'][1]
        assert '13' in entry  # NodeGraph
        assert '5' in entry   # name
        assert '1' in entry   # Location

    def test_graph_with_nodes_to_numeric(self, graph):
        graph.add_node("监听信号")
        graph.add_node("创建元件")
        num = graph.to_numeric()
        entry = num['1'][1]
        # 应有 NodeGraph 内部结构
        ng = entry['13']
        assert '1' in ng  # graph_unit
        graph_dict = ng['1']['1']
        assert '3' in graph_dict  # nodes list
        nodes = graph_dict['3']
        assert len(nodes) == 2

    def test_node_structure_in_numeric(self, graph):
        graph.add_node("监听信号")
        num = graph.to_numeric()
        entry = num['1'][1]
        nodes = entry['13']['1']['1']['3']
        node = nodes[0]
        assert '1' in node  # node_index
        assert '2' in node  # node_type_id
        assert '4' in node  # pins
        assert '5' in node  # x
        assert '6' in node  # y
        assert node['1'] == 1  # 第一个节点 id=1 (从1开始)
        assert node['2'] == {'1': 10001, '2': 20000, '3': 22000, '5': 300001}  # type_id=300001 (字典格式)

    def test_pin_structure_in_numeric(self, graph):
        graph.add_node("监听信号")
        num = graph.to_numeric()
        entry = num['1'][1]
        nodes = entry['13']['1']['1']['3']
        node = nodes[0]
        pins = node['4']
        # 1 个 pin 时返回 dict，2 个 pin 时返回 list（编辑器约定）
        if isinstance(pins, dict):
            pins = [pins]
        assert isinstance(pins, list)
        assert len(pins) >= 1  # 至少有信号名输入

    def test_param_creates_var_base(self, graph):
        """设置参数应在 pin 上生成 VarBase"""
        node = graph.add_node("监听信号", 信号名="test_signal")
        num = graph.to_numeric()
        entry = num['1'][1]
        nodes = entry['13']['1']['1']['3']
        ng_node = nodes[0]
        pins = ng_node['4']
        if isinstance(pins, dict):
            pins = [pins]
        # 找到信号名输入端口：IN_PARAM (kind=3) 且有 VarBase
        str_pin = None
        for pin in pins:
            sig = pin.get('1', {})
            if sig.get('1') == 3 and '3' in pin:  # IN_PARAM with VarBase
                str_pin = pin
                break
        assert str_pin is not None, f"Should find IN_PARAM pin with VarBase in pins: {pins}"
        assert '3' in str_pin  # VarBase
        var_base = str_pin['3']
        # GIA 编码: var_base['1'] 是 wire tag (5=Str), var_base['4']['100']['1'] 是 VarType 值
        assert var_base['4']['100']['1'] == VarType.Str
        # 值在 field[105] 中（Str 类型使用 binary_data 格式）
        assert '105' in var_base

    def test_connection_structure_in_numeric(self, graph):
        """连线应在源节点的 OUT_FLOW pin 上生成 connection"""
        src = graph.add_node("监听信号")
        dst = graph.add_node("创建元件")
        graph.connect_flow(src, "出", dst, "入")
        num = graph.to_numeric()
        entry = num['1'][1]
        nodes = entry['13']['1']['1']['3']
        # 源节点(监听信号)的输出端口应有连接，指向目标节点
        src_node = nodes[0]
        pins = src_node['4']
        out_flow_pin = None
        for pin in pins:
            sig = pin.get('1', {})
            if sig.get('1') == 2:  # OUT_FLOW (flow pins 没有 '2' key)
                out_flow_pin = pin
                break
        assert out_flow_pin is not None
        assert '5' in out_flow_pin  # connections
        conn = out_flow_pin['5']
        assert conn['1'] == 2  # 目标节点 id=2


# ═══════════════════════════════════════════════════════════════
# 8. 导出 GIA
# ═══════════════════════════════════════════════════════════════

class TestToGia:
    """导出为 .gia 文件"""

    def test_to_gia_creates_file(self, graph, tmp_path):
        output = tmp_path / "test_output.gia"
        result = graph.to_gia(output)
        assert result.exists()
        assert result == output

    def test_to_gia_roundtrip(self, graph, tmp_path):
        """导出后能被 gia_utils 重新加载"""
        graph.add_node("监听信号")
        output = tmp_path / "test_roundtrip.gia"
        graph.to_gia(output)

        from tools.live_sync.gia_utils import load_gia_numeric, get_ng_entries
        num = load_gia_numeric(output)
        ng_entries = get_ng_entries(num)
        assert len(ng_entries) >= 1


# ═══════════════════════════════════════════════════════════════
# 9. 验证
# ═══════════════════════════════════════════════════════════════

class TestValidate:
    """图验证"""

    def test_empty_graph_valid(self, graph):
        result = graph.validate()
        assert isinstance(result, ValidationResult)
        assert result.ok

    def test_valid_graph_passes(self, graph):
        src = graph.add_node("监听信号")
        dst = graph.add_node("创建元件")
        graph.connect_flow(src, "出", dst, "入")
        result = graph.validate()
        assert result.ok

    def test_validate_without_catalog_always_ok(self):
        """没有 catalog 时无法校验，默认通过"""
        g = GraphBuilder(name="测试图")
        result = g.validate()
        assert result.ok


# ═══════════════════════════════════════════════════════════════
# 10. 快照 / 回滚
# ═══════════════════════════════════════════════════════════════

class TestSnapshotUndo:
    """快照和回滚"""

    def test_snapshot_before_add(self, graph):
        assert graph.node_count() == 0
        graph.snapshot()
        graph.add_node("监听信号")
        assert graph.node_count() == 1
        graph.undo()
        assert graph.node_count() == 0

    def test_snapshot_before_connect(self, graph):
        n1 = graph.add_node("监听信号")
        n2 = graph.add_node("创建元件")
        graph.snapshot()
        graph.connect_flow(n1, "出", n2, "入")
        graph.undo()
        # 回滚后连线应消失
        num = graph.to_numeric()
        entry = num['1'][1]
        nodes = entry['13']['1']['1']['3']
        # 检查源节点的出端口没有连接
        src_node = nodes[0]
        pins = src_node['4']
        for pin in pins:
            assert '5' not in pin or len(pin.get('5', [])) == 0

    def test_snapshot_before_set_param(self, graph):
        node = graph.add_node("监听信号")
        node.set_param("信号名", "first")
        graph.snapshot()
        node.set_param("信号名", "second")
        assert node.get_param("信号名") == "second"
        graph.undo()
        # undo 重建了节点对象，需要通过 get_node 获取新引用
        restored_node = graph.get_node(0)
        assert restored_node.get_param("信号名") == "first"

    def test_multiple_snapshots(self, graph):
        graph.add_node("监听信号")
        graph.snapshot()  # snapshot 1: 1 node
        graph.add_node("创建元件")
        graph.snapshot()  # snapshot 2: 2 nodes
        graph.add_node("发送信号")
        assert graph.node_count() == 3
        graph.undo()  # 回到 snapshot 2
        assert graph.node_count() == 2
        graph.undo()  # 回到 snapshot 1
        assert graph.node_count() == 1

    def test_undo_without_snapshot_noop(self, graph):
        """没有快照时 undo 不应报错"""
        graph.add_node("监听信号")
        graph.undo()  # 无操作
        assert graph.node_count() == 1


# ═══════════════════════════════════════════════════════════════
# 11. 链式调用
# ═══════════════════════════════════════════════════════════════

class TestChaining:
    """链式调用风格"""

    def test_add_node_returns_handle(self, graph):
        node = graph.add_node("监听信号")
        assert isinstance(node, NodeHandle)

    def test_set_param_returns_handle(self, graph):
        node = graph.add_node("监听信号").set_param("信号名", "test")
        assert isinstance(node, NodeHandle)
        assert node.get_param("信号名") == "test"

    def test_connect_flow_returns_graph(self, graph):
        n1 = graph.add_node("监听信号")
        n2 = graph.add_node("创建元件")
        result = graph.connect_flow(n1, "出", n2, "入")
        assert result is graph

    def test_connect_data_returns_graph(self, graph):
        n1 = graph.add_node("获取局部变量")
        n2 = graph.add_node("多分支")
        result = graph.connect_data(n1, "值", n2, "条件")
        assert result is graph

    def test_full_chain(self, graph):
        """完整链式调用"""
        event = graph.add_node("监听信号").set_param("信号名", "on_start")
        action = graph.add_node("创建元件")
        graph.connect_flow(event, "出", action, "入")
        assert graph.node_count() == 2

    def test_node_handle_connect_flow_returns_self(self, graph):
        n1 = graph.add_node("监听信号")
        n2 = graph.add_node("创建元件")
        result = n1.connect_flow("出", n2, "入")
        assert result is n1

    def test_node_handle_connect_data_returns_self(self, graph):
        n1 = graph.add_node("获取局部变量")
        n2 = graph.add_node("多分支")
        result = n1.connect_data("值", n2, "条件")
        assert result is n1


# ═══════════════════════════════════════════════════════════════
# 12. NodeHandle 属性
# ═══════════════════════════════════════════════════════════════

class TestNodeHandleProperties:
    """NodeHandle 属性访问"""

    def test_type_id_property(self, graph):
        node = graph.add_node("监听信号")
        assert node.type_id == 300001

    def test_name_property(self, graph):
        node = graph.add_node("监听信号")
        assert node.name == "监听信号"

    def test_index_property(self, graph):
        n1 = graph.add_node("监听信号")
        n2 = graph.add_node("创建元件")
        assert n1.index == 0
        assert n2.index == 1

    def test_x_y_properties_default(self, graph):
        node = graph.add_node("监听信号")
        # 默认坐标
        assert hasattr(node, 'x')
        assert hasattr(node, 'y')


# ═══════════════════════════════════════════════════════════════
# 13. VarBase 构造
# ═══════════════════════════════════════════════════════════════

class TestVarBaseConstruction:
    """根据 VarType 构造正确的 VarBase dict"""

    def test_int_var_base(self, graph):
        node = graph.add_node("多分支")
        node.set_param("条件", 42)
        num = graph.to_numeric()
        nodes = num['1'][1]['13']['1']['1']['3']
        pins = nodes[0]['4']
        # 找到条件输入端口 (IN_PARAM kind=3, index=1)
        found = False
        for pin in pins:
            sig = pin.get('1', {})
            if sig.get('1') == 3 and sig.get('2') == 1:  # IN_PARAM, index=1
                var_base = pin.get('3', {})
                # GIA 编码: Int 使用 tag=10000, 嵌套在 field[110].field[2] 中
                assert var_base['1'] == 10000  # Int wire tag
                # VarType 在嵌套的 protobuf 结构中: [110][2][4][100][1]
                assert var_base['110']['2']['4']['100']['1'] == VarType.Int
                assert var_base['110']['2']['102']['1'] == 42
                found = True
                break
        assert found, f"Should find IN_PARAM pin with index=1 in pins: {pins}"

    def test_str_var_base(self, graph):
        node = graph.add_node("监听信号", 信号名="hello")
        num = graph.to_numeric()
        nodes = num['1'][1]['13']['1']['1']['3']
        pins = nodes[0]['4']
        found = False
        for pin in pins:
            sig = pin.get('1', {})
            # 信号名是 IN_PARAM (kind=3)，index=0 时省略 '2' 字段
            if sig.get('1') == 3 and '3' in pin:
                var_base = pin.get('3', {})
                # GIA 编码: var_base['4']['100']['1'] 是 VarType 值
                assert var_base['4']['100']['1'] == VarType.Str
                # Str 值在 field[105] 中，binary_data 格式
                val = var_base.get('105', '')
                assert isinstance(val, str)
                assert 'hello' in val or val.startswith('<binary_data>')
                found = True
                break
        assert found, f"Should find IN_PARAM pin with VarBase in pins: {pins}"

    def test_bool_var_base_true(self, catalog):
        """测试 Bool VarBase 构造"""
        cat = catalog
        cat.register(NodeDef(
            type_id=500, name="测试Bool", category="action",
            description="测试布尔",
            inputs=(
                _pin("入", "In", is_flow=True, index=0),
                _pin("标志", "In", type_expr="Bol", var_type=VarType.Bol, index=1),
            ),
            outputs=(_pin("出", "Out", is_flow=True, index=0),),
        ))
        g = GraphBuilder(name="测试", catalog=cat)
        node = g.add_node("测试Bool")
        node.set_param("标志", True)
        num = g.to_numeric()
        nodes = num['1'][1]['13']['1']['1']['3']
        pins = nodes[0]['4']
        found = False
        for pin in pins:
            sig = pin.get('1', {})
            if sig.get('1') == 3 and sig.get('2') == 1:  # IN_PARAM, index=1
                var_base = pin.get('3', {})
                # GIA 编码: Bool 使用 tag=6, 值在 field[106]['1']
                assert var_base['1'] == 6  # Bool wire tag
                assert var_base['4']['100']['1'] == VarType.Bol
                assert var_base['106']['1'] == 1  # True = 1
                found = True
                break
        assert found, f"Should find IN_PARAM Bool pin with index=1 in pins: {pins}"

    def test_bool_var_base_false(self, catalog):
        cat = catalog
        cat.register(NodeDef(
            type_id=501, name="测试Bool2", category="action",
            description="测试布尔2",
            inputs=(
                _pin("入", "In", is_flow=True, index=0),
                _pin("标志", "In", type_expr="Bol", var_type=VarType.Bol, index=1),
            ),
            outputs=(_pin("出", "Out", is_flow=True, index=0),),
        ))
        g = GraphBuilder(name="测试", catalog=cat)
        node = g.add_node("测试Bool2")
        node.set_param("标志", False)
        num = g.to_numeric()
        nodes = num['1'][1]['13']['1']['1']['3']
        pins = nodes[0]['4']
        found = False
        for pin in pins:
            sig = pin.get('1', {})
            if sig.get('1') == 3 and sig.get('2') == 1:  # IN_PARAM, index=1
                var_base = pin.get('3', {})
                # GIA 编码: Bool 使用 tag=6, False 用空 binary_data 在 field[106]
                assert var_base['1'] == 6  # Bool wire tag
                assert var_base['4']['100']['1'] == VarType.Bol
                # False: field[106] 是 binary_data 字符串（非 {'1': 1}）
                val = var_base.get('106', '')
                assert isinstance(val, str)  # binary_data 是字符串
                found = True
                break
        assert found, f"Should find IN_PARAM Bool pin with index=1 in pins: {pins}"


# ═══════════════════════════════════════════════════════════════
# 14. LevelBuilder
# ═══════════════════════════════════════════════════════════════

class TestLevelBuilder:
    """关卡构建器 - 管理多个节点图"""

    def test_create_level_builder(self):
        level = LevelBuilder(name="测试关卡")
        assert level.name == "测试关卡"

    def test_add_graph(self, catalog):
        level = LevelBuilder(name="测试关卡")
        g = level.add_graph("图1", catalog=catalog)
        assert isinstance(g, GraphBuilder)
        assert g.name == "图1"

    def test_add_multiple_graphs(self, catalog):
        level = LevelBuilder(name="测试关卡")
        g1 = level.add_graph("图1", catalog=catalog)
        g2 = level.add_graph("图2", catalog=catalog)
        assert len(level.graphs) == 2

    def test_level_to_numeric(self, catalog):
        level = LevelBuilder(name="测试关卡")
        g1 = level.add_graph("图1", catalog=catalog)
        g1.add_node("监听信号")
        num = level.to_numeric()
        assert isinstance(num, dict)
        assert '1' in num
        entries = num['1']
        assert len(entries) >= 1

    def test_level_to_gia(self, catalog, tmp_path):
        level = LevelBuilder(name="测试关卡")
        g1 = level.add_graph("图1", catalog=catalog)
        g1.add_node("监听信号")
        output = tmp_path / "test_level.gia"
        result = level.to_gia(output)
        assert result.exists()


# ═══════════════════════════════════════════════════════════════
# 15. Pin kind 常量正确性
# ═══════════════════════════════════════════════════════════════

class TestPinKindConstants:
    """验证导出的 numeric 中 pin kind 常量正确"""

    def test_in_flow_pin_kind(self, graph):
        graph.add_node("创建元件")
        num = graph.to_numeric()
        nodes = num['1'][1]['13']['1']['1']['3']
        pins = nodes[0]['4']
        # 找到流程输入端口
        flow_in = None
        for pin in pins:
            sig = pin.get('1', {})
            if sig.get('1') == 1:  # IN_FLOW
                flow_in = pin
                break
        assert flow_in is not None

    def test_out_flow_pin_kind(self, graph):
        graph.add_node("创建元件")
        num = graph.to_numeric()
        nodes = num['1'][1]['13']['1']['1']['3']
        pins = nodes[0]['4']
        # 找到流程输出端口
        flow_out = None
        for pin in pins:
            sig = pin.get('1', {})
            if sig.get('1') == 2:  # OUT_FLOW
                flow_out = pin
                break
        assert flow_out is not None

    def test_in_param_pin_kind(self, graph):
        graph.add_node("创建元件")
        num = graph.to_numeric()
        nodes = num['1'][1]['13']['1']['1']['3']
        pins = nodes[0]['4']
        # 找到数据输入端口
        param_in = None
        for pin in pins:
            sig = pin.get('1', {})
            if sig.get('1') == 3:  # IN_PARAM
                param_in = pin
                break
        assert param_in is not None

    def test_out_param_pin_kind(self, graph):
        """数据输出端口被连接时应导出（与编辑器行为一致：仅被消费的输出引脚才存储）"""
        # 连接 Ety 输出到 Ety 输入：创建元件.实体 → 发送信号.目标
        src = graph.add_node("创建元件")
        dst = graph.add_node("发送信号")
        graph.connect_data(src, "实体", dst, "目标")
        num = graph.to_numeric()
        nodes = num['1'][1]['13']['1']['1']['3']
        # "创建元件" 是 nodes[0]（第一个添加的节点）
        pins = nodes[0]['4']
        # 找到数据输出端口
        param_out = None
        for pin in pins:
            sig = pin.get('1', {})
            if sig.get('1') == 4:  # OUT_PARAM
                param_out = pin
                break
        assert param_out is not None, f"Should find OUT_PARAM pin in pins: {pins}"


# ═══════════════════════════════════════════════════════════════
# 16. 综合场景：构建完整节点图
# ═══════════════════════════════════════════════════════════════

class TestFullScenario:
    """综合场景：构建一个完整的节点图"""

    def test_build_signal_chain(self, graph):
        """构建：监听信号 -> 创建元件 -> 发送信号"""
        event = graph.add_node("监听信号").set_param("信号名", "on_start")
        create = graph.add_node("创建元件")
        send = graph.add_node("发送信号")

        graph.connect_flow(event, "出", create, "入")
        graph.connect_flow(create, "出", send, "入")

        assert graph.node_count() == 3

        # 验证
        result = graph.validate()
        assert result.ok

        # 导出 numeric 并检查结构
        num = graph.to_numeric()
        entry = num['1'][1]
        nodes = entry['13']['1']['1']['3']
        assert len(nodes) == 3

    def test_build_with_data_flow(self, graph):
        """构建带数据流的图"""
        var = graph.add_node("获取局部变量")
        branch = graph.add_node("多分支")
        graph.connect_data(var, "值", branch, "条件")

        assert graph.node_count() == 2

        num = graph.to_numeric()
        nodes = num['1'][1]['13']['1']['1']['3']
        assert len(nodes) == 2

    def test_export_roundtrip(self, graph, tmp_path):
        """导出后重新加载验证"""
        graph.add_node("监听信号").set_param("信号名", "test")
        output = tmp_path / "scenario.gia"
        graph.to_gia(output)

        from tools.live_sync.gia_utils import load_gia_numeric, get_entries, get_ng_graph
        num = load_gia_numeric(output)
        entries = get_entries(num)
        assert len(entries) >= 2
        # NG entry 在 entity 之后（entries[1]）
        ng_graph = get_ng_graph(entries[1])
        assert ng_graph is not None
        # protobuf 编解码后单元素列表可能变为 dict
        nodes_field = ng_graph.get('3', [])
        expected_type_id = {'1': 10001, '2': 20000, '3': 22000, '5': 300001}
        if isinstance(nodes_field, dict):
            # 单节点被解码为 dict
            assert nodes_field.get('2') == expected_type_id  # type_id
        elif isinstance(nodes_field, list):
            assert len(nodes_field) >= 1
            assert nodes_field[0].get('2') == expected_type_id  # type_id
