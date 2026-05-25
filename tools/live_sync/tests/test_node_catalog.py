# -*- coding: utf-8 -*-
"""节点语义注册表 (NodeCatalog) 单元测试

TDD: 先定义接口契约，再实现。
覆盖：内置节点注册、查询、端口信息、类型安全检查、节点分类。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tools.live_sync.node_catalog import (
    PinDef,
    NodeDef,
    ValidationResult,
    NodeCatalog,
    VarType,
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


# ═══════════════════════════════════════════════════════════════
# 1. 内置节点注册
# ═══════════════════════════════════════════════════════════════

class TestBuiltinNodes:
    """默认注册表应预置常用节点"""

    def test_default_catalog_has_nodes(self):
        cat = NodeCatalog.default()
        assert len(cat) > 0, "默认注册表不应为空"

    def test_has_multiple_branches(self):
        cat = NodeCatalog.default()
        node = cat.get_by_id(3)
        assert node is not None
        assert "分支" in node.name or "Branch" in node.name

    def test_has_get_local_variable(self):
        cat = NodeCatalog.default()
        node = cat.get_by_id(18)
        assert node is not None
        assert "局部变量" in node.name or "Local" in node.name

    def test_has_assembly_list(self):
        cat = NodeCatalog.default()
        node = cat.get_by_id(169)
        assert node is not None
        assert "列表" in node.name or "List" in node.name

    def test_has_assembly_dictionary(self):
        cat = NodeCatalog.default()
        node = cat.get_by_id(1788)
        assert node is not None
        assert "字典" in node.name or "Dictionary" in node.name

    def test_has_create_prefab(self):
        cat = NodeCatalog.default()
        node = cat.get_by_id(252)
        assert node is not None
        assert "元件" in node.name or "Prefab" in node.name

    def test_has_send_signal(self):
        cat = NodeCatalog.default()
        node = cat.get_by_id(300000)
        assert node is not None
        assert "发送信号" in node.name or "Send" in node.name

    def test_has_listen_signal(self):
        cat = NodeCatalog.default()
        node = cat.get_by_id(300001)
        assert node is not None
        assert "监听信号" in node.name or "Listen" in node.name


# ═══════════════════════════════════════════════════════════════
# 2. 节点查询
# ═══════════════════════════════════════════════════════════════

class TestNodeQuery:
    """按 ID / 名称 / 关键词查询"""

    def test_get_by_id_found(self):
        cat = NodeCatalog()
        n = _node(42, "测试节点")
        cat.register(n)
        assert cat.get_by_id(42) is n

    def test_get_by_id_not_found(self):
        cat = NodeCatalog()
        assert cat.get_by_id(999) is None

    def test_get_by_name_found(self):
        cat = NodeCatalog()
        n = _node(42, "获取局部变量")
        cat.register(n)
        assert cat.get_by_name("获取局部变量") is n

    def test_get_by_name_not_found(self):
        cat = NodeCatalog()
        assert cat.get_by_name("不存在") is None

    def test_search_keyword(self):
        cat = NodeCatalog()
        cat.register(_node(1, "获取局部变量"))
        cat.register(_node(2, "设置局部变量"))
        cat.register(_node(3, "创建元件"))
        results = cat.search("变量")
        assert len(results) == 2
        ids = {r.type_id for r in results}
        assert ids == {1, 2}

    def test_search_empty_returns_all(self):
        cat = NodeCatalog()
        cat.register(_node(1, "A"))
        cat.register(_node(2, "B"))
        results = cat.search("")
        assert len(results) == 2

    def test_search_no_match(self):
        cat = NodeCatalog()
        cat.register(_node(1, "获取局部变量"))
        results = cat.search("不存在的关键词")
        assert len(results) == 0

    def test_len_and_contains(self):
        cat = NodeCatalog()
        cat.register(_node(1, "A"))
        cat.register(_node(2, "B"))
        assert len(cat) == 2
        assert 1 in cat
        assert 3 not in cat


# ═══════════════════════════════════════════════════════════════
# 3. 端口信息
# ═══════════════════════════════════════════════════════════════

class TestPinInfo:
    """获取节点的输入/输出端口列表"""

    def test_input_pins(self):
        node = _node(1, "测试", inputs=[
            _pin("入", "In", is_flow=True, index=0),
            _pin("值", "In", type_expr="Int", var_type=VarType.Int, index=1),
        ])
        assert len(node.inputs) == 2
        flow_pins = [p for p in node.inputs if p.is_flow]
        data_pins = [p for p in node.inputs if not p.is_flow]
        assert len(flow_pins) == 1
        assert len(data_pins) == 1
        assert data_pins[0].type_expr == "Int"

    def test_output_pins(self):
        node = _node(1, "测试", outputs=[
            _pin("出", "Out", is_flow=True, index=0),
            _pin("结果", "Out", type_expr="Bol", var_type=VarType.Bol, index=1),
        ])
        assert len(node.outputs) == 2
        assert node.outputs[1].var_type == VarType.Bol

    def test_flow_and_data_ports_separated(self):
        """流程端口和数据端口应可区分"""
        node = _node(1, "测试", inputs=[
            _pin("入", "In", is_flow=True, index=0),
            _pin("X", "In", type_expr="Int", var_type=VarType.Int, index=1),
        ], outputs=[
            _pin("出", "Out", is_flow=True, index=0),
            _pin("Y", "Out", type_expr="Int", var_type=VarType.Int, index=1),
        ])
        in_flow = [p for p in node.inputs if p.is_flow]
        in_data = [p for p in node.inputs if not p.is_flow]
        out_flow = [p for p in node.outputs if p.is_flow]
        out_data = [p for p in node.outputs if not p.is_flow]
        assert len(in_flow) == 1 and len(in_data) == 1
        assert len(out_flow) == 1 and len(out_data) == 1

    def test_builtin_node_has_pins(self):
        """内置节点应有端口定义"""
        cat = NodeCatalog.default()
        node = cat.get_by_id(3)  # Multiple_Branches
        assert node is not None
        # 多分支节点至少应有流程输入和流程输出
        assert len(node.inputs) > 0
        assert len(node.outputs) > 0


# ═══════════════════════════════════════════════════════════════
# 4. 类型安全检查 (can_connect)
# ═══════════════════════════════════════════════════════════════

class TestCanConnect:
    """检查两个端口是否可以连接"""

    def test_same_type_data_connect_ok(self):
        src = _node(1, "源", outputs=[
            _pin("值", "Out", type_expr="Int", var_type=VarType.Int, index=1),
        ])
        dst = _node(2, "目标", inputs=[
            _pin("值", "In", type_expr="Int", var_type=VarType.Int, index=1),
        ])
        cat = NodeCatalog()
        cat.register(src)
        cat.register(dst)
        result = cat.can_connect(src, "值", dst, "值")
        assert result.ok
        assert not result.errors

    def test_flow_to_flow_ok(self):
        src = _node(1, "源", outputs=[
            _pin("出", "Out", is_flow=True, index=0),
        ])
        dst = _node(2, "目标", inputs=[
            _pin("入", "In", is_flow=True, index=0),
        ])
        cat = NodeCatalog()
        cat.register(src)
        cat.register(dst)
        result = cat.can_connect(src, "出", dst, "入")
        assert result.ok

    def test_type_mismatch_rejected(self):
        src = _node(1, "源", outputs=[
            _pin("值", "Out", type_expr="Int", var_type=VarType.Int, index=1),
        ])
        dst = _node(2, "目标", inputs=[
            _pin("值", "In", type_expr="Str", var_type=VarType.Str, index=1),
        ])
        cat = NodeCatalog()
        cat.register(src)
        cat.register(dst)
        result = cat.can_connect(src, "值", dst, "值")
        assert not result.ok
        assert len(result.errors) > 0

    def test_flow_cannot_connect_to_data(self):
        src = _node(1, "源", outputs=[
            _pin("出", "Out", is_flow=True, index=0),
        ])
        dst = _node(2, "目标", inputs=[
            _pin("值", "In", type_expr="Int", var_type=VarType.Int, index=1),
        ])
        cat = NodeCatalog()
        cat.register(src)
        cat.register(dst)
        result = cat.can_connect(src, "出", dst, "值")
        assert not result.ok

    def test_data_cannot_connect_to_flow(self):
        src = _node(1, "源", outputs=[
            _pin("值", "Out", type_expr="Int", var_type=VarType.Int, index=1),
        ])
        dst = _node(2, "目标", inputs=[
            _pin("入", "In", is_flow=True, index=0),
        ])
        cat = NodeCatalog()
        cat.register(src)
        cat.register(dst)
        result = cat.can_connect(src, "值", dst, "入")
        assert not result.ok

    def test_output_to_output_rejected(self):
        src = _node(1, "源", outputs=[
            _pin("值", "Out", type_expr="Int", var_type=VarType.Int, index=1),
        ])
        dst = _node(2, "目标", outputs=[
            _pin("值", "Out", type_expr="Int", var_type=VarType.Int, index=1),
        ])
        cat = NodeCatalog()
        cat.register(src)
        cat.register(dst)
        result = cat.can_connect(src, "值", dst, "值")
        assert not result.ok

    def test_input_to_input_rejected(self):
        src = _node(1, "源", inputs=[
            _pin("值", "In", type_expr="Int", var_type=VarType.Int, index=1),
        ])
        dst = _node(2, "目标", inputs=[
            _pin("值", "In", type_expr="Int", var_type=VarType.Int, index=1),
        ])
        cat = NodeCatalog()
        cat.register(src)
        cat.register(dst)
        result = cat.can_connect(src, "值", dst, "值")
        assert not result.ok

    def test_port_not_found(self):
        src = _node(1, "源", outputs=[
            _pin("值", "Out", type_expr="Int", var_type=VarType.Int, index=1),
        ])
        dst = _node(2, "目标", inputs=[
            _pin("值", "In", type_expr="Int", var_type=VarType.Int, index=1),
        ])
        cat = NodeCatalog()
        cat.register(src)
        cat.register(dst)
        result = cat.can_connect(src, "不存在端口", dst, "值")
        assert not result.ok

    def test_entity_type_compatible(self):
        """Ety 类型端口应可以连接到 Ety 端口"""
        src = _node(1, "源", outputs=[
            _pin("实体", "Out", type_expr="Ety", var_type=VarType.Ety, index=1),
        ])
        dst = _node(2, "目标", inputs=[
            _pin("实体", "In", type_expr="Ety", var_type=VarType.Ety, index=1),
        ])
        cat = NodeCatalog()
        cat.register(src)
        cat.register(dst)
        result = cat.can_connect(src, "实体", dst, "实体")
        assert result.ok


# ═══════════════════════════════════════════════════════════════
# 5. 节点分类
# ═══════════════════════════════════════════════════════════════

class TestNodeCategory:
    """节点分类：event / action / condition / variable / composite"""

    def test_list_categories(self):
        cat = NodeCatalog()
        cat.register(_node(1, "事件A", category="event"))
        cat.register(_node(2, "动作B", category="action"))
        cats = cat.list_categories()
        assert "event" in cats
        assert "action" in cats

    def test_list_by_category(self):
        cat = NodeCatalog()
        cat.register(_node(1, "事件A", category="event"))
        cat.register(_node(2, "事件B", category="event"))
        cat.register(_node(3, "动作C", category="action"))
        event_nodes = cat.list_by_category("event")
        assert len(event_nodes) == 2
        assert all(n.category == "event" for n in event_nodes)

    def test_list_by_category_empty(self):
        cat = NodeCatalog()
        cat.register(_node(1, "A", category="action"))
        result = cat.list_by_category("event")
        assert len(result) == 0

    def test_default_catalog_has_categories(self):
        """默认注册表应有多种分类"""
        cat = NodeCatalog.default()
        cats = cat.list_categories()
        assert len(cats) >= 2

    def test_default_catalog_event_nodes(self):
        """默认注册表应有事件类节点"""
        cat = NodeCatalog.default()
        events = cat.list_by_category("event")
        # 监听信号属于事件节点
        assert len(events) > 0

    def test_default_catalog_action_nodes(self):
        """默认注册表应有动作类节点"""
        cat = NodeCatalog.default()
        actions = cat.list_by_category("action")
        assert len(actions) > 0


# ═══════════════════════════════════════════════════════════════
# 6. 手动注册 & 重复注册
# ═══════════════════════════════════════════════════════════════

class TestManualRegister:
    """手动注册节点"""

    def test_register_basic(self):
        cat = NodeCatalog()
        n = _node(100, "自定义节点", category="action",
                  description="一个测试用节点")
        cat.register(n)
        assert cat.get_by_id(100) is n
        assert cat.get_by_name("自定义节点") is n

    def test_register_overwrites(self):
        """重复注册同 ID 节点应覆盖"""
        cat = NodeCatalog()
        n1 = _node(100, "旧名称")
        n2 = _node(100, "新名称")
        cat.register(n1)
        cat.register(n2)
        assert cat.get_by_id(100).name == "新名称"
        assert len(cat) == 1

    def test_register_preserves_category_index(self):
        cat = NodeCatalog()
        cat.register(_node(1, "A", category="event"))
        cat.register(_node(2, "B", category="action"))
        cat.register(_node(3, "C", category="event"))
        assert sorted(cat.list_categories()) == ["action", "event"]
        assert len(cat.list_by_category("event")) == 2


# ═══════════════════════════════════════════════════════════════
# 7. 从文件加载（接口存在性 + 文件不存在时的优雅降级）
# ═══════════════════════════════════════════════════════════════

class TestFileLoading:
    """from_node_editor_pack / from_genshin_ts_report 接口"""

    def test_from_node_editor_pack_missing_file(self):
        """data.json 不存在时应返回空注册表或抛出明确异常"""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            fake = Path(td) / "nonexistent_data.json"
            # 不应抛出未处理异常
            cat = NodeCatalog.from_node_editor_pack(fake)
            assert isinstance(cat, NodeCatalog)

    def test_from_genshin_ts_report_missing_file(self):
        """report.json 不存在时应返回空注册表或抛出明确异常"""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            fake = Path(td) / "nonexistent_report.json"
            cat = NodeCatalog.from_genshin_ts_report(fake)
            assert isinstance(cat, NodeCatalog)


# ═══════════════════════════════════════════════════════════════
# 8. VarType 常量
# ═══════════════════════════════════════════════════════════════

class TestVarTypeConstants:
    """VarType 常量应与项目已有定义一致"""

    def test_basic_types(self):
        assert VarType.Ety == 1
        assert VarType.GUID == 2
        assert VarType.Int == 3
        assert VarType.Bol == 4
        assert VarType.Flt == 5
        assert VarType.Str == 6

    def test_array_types(self):
        assert VarType.GUIDArr == 7
        assert VarType.IntArr == 8
        assert VarType.BolArr == 9
        assert VarType.FltArr == 10
        assert VarType.StrArr == 11
        assert VarType.Vec == 12
        assert VarType.EtyArr == 13
        assert VarType.VecArr == 15

    def test_special_types(self):
        assert VarType.Faction == 17
        assert VarType.Config == 20
        assert VarType.Prefab == 21
        assert VarType.ConfigArr == 22
        assert VarType.PrefabArr == 23


# ═══════════════════════════════════════════════════════════════
# 9. ValidationResult
# ═══════════════════════════════════════════════════════════════

class TestValidationResult:
    """ValidationResult 数据类"""

    def test_ok_result(self):
        r = ValidationResult(ok=True, errors=[])
        assert r.ok
        assert len(r.errors) == 0

    def test_error_result(self):
        r = ValidationResult(ok=False, errors=["类型不匹配"])
        assert not r.ok
        assert "类型不匹配" in r.errors

    def test_bool_conversion(self):
        assert ValidationResult(ok=True, errors=[])
        assert not ValidationResult(ok=False, errors=["err"])
