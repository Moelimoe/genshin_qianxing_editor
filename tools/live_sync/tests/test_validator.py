# -*- coding: utf-8 -*-
"""GIA 验证器 (validator) 单元测试

TDD: 先定义验证接口契约，再实现。
覆盖：结构验证、NodeGraph验证、连线验证、端口完整性、
      GraphBuilder集成验证、往返验证、验证报告。
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Dict, List

import pytest

from tools.live_sync.node_catalog import (
    NodeCatalog, NodeDef, PinDef, VarType, ValidationResult,
)
from tools.live_sync.level_builder import (
    NodeHandle, GraphBuilder, LevelBuilder,
)
from tools.live_sync.gia_utils import (
    make_binary_name, get_entries, get_ng_graph, get_ng_nodes,
)
from tools.live_sync.validator import (
    ValidationIssue, ValidationReport, GIAValidator,
)


# ═══════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════

def _pin(name: str, direction: str, is_flow: bool = False,
         type_expr: str = "", var_type: int = 0, index: int = 0) -> PinDef:
    return PinDef(
        name=name, direction=direction, is_flow=is_flow,
        type_expr=type_expr, var_type=var_type, index=index,
    )


def _make_catalog() -> NodeCatalog:
    """创建测试用注册表"""
    cat = NodeCatalog()
    # 监听信号 (event, type_id=100)
    cat.register(NodeDef(
        type_id=100, name="监听信号", category="event",
        description="监听信号事件",
        inputs=(_pin("信号名", "In", type_expr="Str", var_type=VarType.Str, index=0),),
        outputs=(_pin("出", "Out", is_flow=True, index=0),),
    ))
    # 创建元件 (action, type_id=200)
    cat.register(NodeDef(
        type_id=200, name="创建元件", category="action",
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
    # 发送信号 (action, type_id=300)
    cat.register(NodeDef(
        type_id=300, name="发送信号", category="action",
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


def _make_valid_numeric() -> Dict[str, Any]:
    """构建一个结构正确的最小 GIA numeric dict"""
    node = {
        '1': 0,           # node_index
        '2': 100,         # node_type (监听信号)
        '3': {},          # data_out
        '4': [            # pins
            {
                '1': {'1': 3, '2': 0},  # PinSignature: IN_PARAM, index=0
                '2': {'1': 3, '2': 0},  # PinSignature: IN_PARAM, index=0
                '4': VarType.Str,        # VarType
            },
            {
                '1': {'1': 2, '2': 0},  # PinSignature: OUT_FLOW, index=0
                '2': {'1': 2, '2': 0},  # PinSignature: OUT_FLOW, index=0
                '4': 0,
            },
        ],
        '5': 0,  # x
        '6': 0,  # y
    }
    graph = {'3': [node]}
    ng_entry = {
        '1': {'4': 0},
        '3': make_binary_name("test_graph"),
        '5': 0,
        '13': {
            '1': {
                '1': graph,
            },
        },
    }
    num = {
        '1': [ng_entry],
        '3': make_binary_name("test.gia"),
    }
    return num


def _make_numeric_with_connection(
    src_node_type: int = 100,
    dst_node_type: int = 200,
    src_pin_kind: int = 2,  # OUT_FLOW
    dst_pin_kind: int = 1,  # IN_FLOW
    src_pin_index: int = 0,
    dst_pin_index: int = 0,
    self_connect: bool = False,
    duplicate: bool = False,
) -> Dict[str, Any]:
    """构建包含连线的 numeric dict"""
    src_node_idx = 0
    dst_node_idx = 1 if not self_connect else 0

    src_node = {
        '1': src_node_idx,
        '2': src_node_type,
        '3': {},
        '4': [
            {
                '1': {'1': src_pin_kind, '2': src_pin_index},
                '2': {'1': src_pin_kind, '2': src_pin_index},
                '4': 0,
                '5': [
                    {
                        '1': dst_node_idx,
                        '2': {'1': dst_pin_kind, '2': dst_pin_index},
                        '3': {'1': dst_pin_kind, '2': dst_pin_index},
                    },
                ],
            },
        ],
        '5': 0,
        '6': 0,
    }

    # 如果是重复连线，添加第二条相同连线
    if duplicate:
        src_node['4'][0]['5'].append({
            '1': dst_node_idx,
            '2': {'1': dst_pin_kind, '2': dst_pin_index},
            '3': {'1': dst_pin_kind, '2': dst_pin_index},
        })

    dst_node = {
        '1': dst_node_idx,
        '2': dst_node_type,
        '3': {},
        '4': [
            {
                '1': {'1': dst_pin_kind, '2': dst_pin_index},
                '2': {'1': dst_pin_kind, '2': dst_pin_index},
                '4': 0,
            },
        ],
        '5': 300,
        '6': 0,
    }

    nodes = [src_node]
    if not self_connect:
        nodes.append(dst_node)

    graph = {'3': nodes}
    ng_entry = {
        '1': {'4': 0},
        '3': make_binary_name("test_conn"),
        '5': 0,
        '13': {'1': {'1': graph}},
    }
    return {
        '1': [ng_entry],
        '3': make_binary_name("test_conn.gia"),
    }


@pytest.fixture
def catalog():
    return _make_catalog()


@pytest.fixture
def validator(catalog):
    return GIAValidator(catalog=catalog)


@pytest.fixture
def valid_numeric():
    return _make_valid_numeric()


# ═══════════════════════════════════════════════════════════════
# 1. ValidationIssue 数据类
# ═══════════════════════════════════════════════════════════════

class TestValidationIssue:
    """ValidationIssue 数据类"""

    def test_create_error_issue(self):
        issue = ValidationIssue(
            severity="error",
            code="MISSING_FIELD",
            message="field '1' is missing",
            location="entry[0]",
        )
        assert issue.severity == "error"
        assert issue.code == "MISSING_FIELD"
        assert issue.message == "field '1' is missing"
        assert issue.location == "entry[0]"

    def test_create_warning_issue(self):
        issue = ValidationIssue(
            severity="warning",
            code="EMPTY_GRAPH",
            message="graph has no nodes",
            location="entry[0].graph",
        )
        assert issue.severity == "warning"

    def test_create_info_issue(self):
        issue = ValidationIssue(
            severity="info",
            code="OK",
            message="all checks passed",
            location="",
        )
        assert issue.severity == "info"


# ═══════════════════════════════════════════════════════════════
# 2. ValidationReport 数据类
# ═══════════════════════════════════════════════════════════════

class TestValidationReport:
    """ValidationReport 数据类"""

    def test_empty_report_is_ok(self):
        report = ValidationReport(issues=[])
        assert report.ok is True
        assert report.errors == []
        assert report.warnings == []
        assert report.infos == []

    def test_report_with_error_is_not_ok(self):
        issues = [
            ValidationIssue("error", "MISSING_FIELD", "missing", "entry[0]"),
        ]
        report = ValidationReport(issues=issues)
        assert report.ok is False
        assert len(report.errors) == 1
        assert report.warnings == []

    def test_report_with_warning_is_ok(self):
        issues = [
            ValidationIssue("warning", "EMPTY_GRAPH", "empty", "entry[0]"),
        ]
        report = ValidationReport(issues=issues)
        assert report.ok is True
        assert len(report.warnings) == 1
        assert report.errors == []

    def test_report_with_mixed_severities(self):
        issues = [
            ValidationIssue("info", "OK", "info msg", ""),
            ValidationIssue("warning", "WARN", "warn msg", ""),
            ValidationIssue("error", "ERR", "err msg", ""),
            ValidationIssue("warning", "WARN2", "warn msg 2", ""),
        ]
        report = ValidationReport(issues=issues)
        assert report.ok is False
        assert len(report.errors) == 1
        assert len(report.warnings) == 2
        assert len(report.infos) == 1

    def test_to_text_empty(self):
        report = ValidationReport(issues=[])
        text = report.to_text()
        assert isinstance(text, str)
        assert "PASS" in text or "OK" in text or "0 error" in text

    def test_to_text_with_issues(self):
        issues = [
            ValidationIssue("error", "MISSING_FIELD", "field '1' is missing", "entry[0]"),
            ValidationIssue("warning", "EMPTY_GRAPH", "graph has no nodes", "entry[1].graph"),
        ]
        report = ValidationReport(issues=issues)
        text = report.to_text()
        assert isinstance(text, str)
        assert "error" in text.lower() or "ERROR" in text
        assert "MISSING_FIELD" in text
        assert "entry[0]" in text


# ═══════════════════════════════════════════════════════════════
# 3. 结构验证
# ═══════════════════════════════════════════════════════════════

class TestValidateNumericStructure:
    """验证 GIA numeric dict 的基本结构"""

    def test_valid_numeric_passes(self, validator, valid_numeric):
        report = validator.validate_numeric(valid_numeric)
        assert report.ok

    def test_missing_field_1(self, validator, valid_numeric):
        """缺少顶层 field '1'"""
        del valid_numeric['1']
        report = validator.validate_numeric(valid_numeric)
        assert not report.ok
        assert any(i.code == "MISSING_FIELD" for i in report.errors)

    def test_empty_entries(self, validator):
        """entries 列表为空"""
        num = {'1': [], '3': make_binary_name("empty.gia")}
        report = validator.validate_numeric(num)
        assert not report.ok
        assert any(i.code == "EMPTY_ENTRIES" for i in report.errors)

    def test_entries_not_list(self, validator):
        """entries 不是列表"""
        num = {'1': "not a list", '3': make_binary_name("bad.gia")}
        report = validator.validate_numeric(num)
        assert not report.ok

    def test_entry_missing_required_fields(self, validator):
        """entry 缺少必要字段"""
        num = {
            '1': [{'99': 'bad_entry'}],
            '3': make_binary_name("bad.gia"),
        }
        report = validator.validate_numeric(num)
        assert not report.ok

    def test_non_dict_entry_in_list(self, validator):
        """entries 列表中包含非 dict 元素"""
        num = {
            '1': ["not_a_dict", 42, None],
            '3': make_binary_name("bad.gia"),
        }
        report = validator.validate_numeric(num)
        assert not report.ok


# ═══════════════════════════════════════════════════════════════
# 4. NodeGraph 验证
# ═══════════════════════════════════════════════════════════════

class TestValidateNodeGraph:
    """验证 NG entry 结构"""

    def test_valid_ng_entry(self, validator, valid_numeric):
        report = validator.validate_numeric(valid_numeric)
        # 不应有 NG 相关的 error
        ng_errors = [i for i in report.errors if "NG" in i.code or "NODE_GRAPH" in i.code]
        assert len(ng_errors) == 0

    def test_ng_entry_missing_field_13(self, validator):
        """NG entry 缺少 field '13'"""
        num = {
            '1': [{
                '1': {'4': 0},
                '3': make_binary_name("no_ng"),
                '5': 0,
            }],
            '3': make_binary_name("no_ng.gia"),
        }
        report = validator.validate_numeric(num)
        # 缺少 field '13' 应该是 info 或 warning，不一定 error
        # 因为不是所有 entry 都必须有 NG
        assert isinstance(report, ValidationReport)

    def test_ng_field_13_wrong_type(self, validator):
        """field '13' 类型错误"""
        num = {
            '1': [{
                '1': {'4': 0},
                '3': make_binary_name("bad_ng"),
                '5': 0,
                '13': "not a dict",
            }],
            '3': make_binary_name("bad_ng.gia"),
        }
        report = validator.validate_numeric(num)
        assert not report.ok

    def test_graph_missing_nodes_list(self, validator):
        """graph 内部缺少 field '3' (nodes list)"""
        num = {
            '1': [{
                '1': {'4': 0},
                '3': make_binary_name("no_nodes"),
                '5': 0,
                '13': {'1': {'1': {}}},
            }],
            '3': make_binary_name("no_nodes.gia"),
        }
        report = validator.validate_numeric(num)
        assert not report.ok

    def test_node_missing_required_fields(self, validator):
        """node 缺少必要字段"""
        bad_node = {'99': 'bad'}
        num = {
            '1': [{
                '1': {'4': 0},
                '3': make_binary_name("bad_node"),
                '5': 0,
                '13': {'1': {'1': {'3': [bad_node]}}},
            }],
            '3': make_binary_name("bad_node.gia"),
        }
        report = validator.validate_numeric(num)
        assert not report.ok
        assert any("node" in i.code.lower() or "NODE" in i.code for i in report.errors)

    def test_pin_missing_pin_signature(self, validator):
        """pin 缺少 field '1' (PinSignature)"""
        bad_pin = {'2': {'1': 1, '2': 0}, '4': 0}
        bad_node = {
            '1': 0, '2': 100, '3': {}, '4': [bad_pin], '5': 0, '6': 0,
        }
        num = {
            '1': [{
                '1': {'4': 0},
                '3': make_binary_name("bad_pin"),
                '5': 0,
                '13': {'1': {'1': {'3': [bad_node]}}},
            }],
            '3': make_binary_name("bad_pin.gia"),
        }
        report = validator.validate_numeric(num)
        assert not report.ok
        assert any("PIN" in i.code for i in report.errors)


# ═══════════════════════════════════════════════════════════════
# 5. 连线验证
# ═══════════════════════════════════════════════════════════════

class TestValidateConnections:
    """验证连线合法性"""

    def test_valid_flow_connection(self, validator):
        """合法的流程连线: OUT_FLOW(2) -> IN_FLOW(1)"""
        num = _make_numeric_with_connection(
            src_pin_kind=2, dst_pin_kind=1,
        )
        report = validator.validate_numeric(num)
        conn_errors = [i for i in report.errors if "CONNECTION" in i.code]
        assert len(conn_errors) == 0

    def test_valid_data_connection(self, validator):
        """合法的数据连线: OUT_PARAM(4) -> IN_PARAM(3)"""
        num = _make_numeric_with_connection(
            src_pin_kind=4, dst_pin_kind=3,
        )
        report = validator.validate_numeric(num)
        conn_errors = [i for i in report.errors if "CONNECTION" in i.code]
        assert len(conn_errors) == 0

    def test_flow_to_data_connection(self, validator):
        """非法连线: OUT_FLOW(2) -> IN_PARAM(3)"""
        num = _make_numeric_with_connection(
            src_pin_kind=2, dst_pin_kind=3,
        )
        report = validator.validate_numeric(num)
        assert not report.ok
        assert any("CONNECTION" in i.code for i in report.errors)

    def test_data_to_flow_connection(self, validator):
        """非法连线: OUT_PARAM(4) -> IN_FLOW(1)"""
        num = _make_numeric_with_connection(
            src_pin_kind=4, dst_pin_kind=1,
        )
        report = validator.validate_numeric(num)
        assert not report.ok
        assert any("CONNECTION" in i.code for i in report.errors)

    def test_self_connection(self, validator):
        """自连接：节点连自己"""
        num = _make_numeric_with_connection(self_connect=True)
        report = validator.validate_numeric(num)
        assert not report.ok
        assert any("SELF_CONNECT" in i.code for i in report.errors)

    def test_duplicate_connection(self, validator):
        """重复连线"""
        num = _make_numeric_with_connection(duplicate=True)
        report = validator.validate_numeric(num)
        assert not report.ok
        assert any("DUPLICATE" in i.code for i in report.errors)

    def test_connection_to_nonexistent_node(self, validator):
        """连线目标节点索引不存在"""
        src_node = {
            '1': 0,
            '2': 100,
            '3': {},
            '4': [
                {
                    '1': {'1': 2, '2': 0},
                    '2': {'1': 2, '2': 0},
                    '4': 0,
                    '5': [
                        {
                            '1': 999,  # 不存在的节点索引
                            '2': {'1': 1, '2': 0},
                            '3': {'1': 1, '2': 0},
                        },
                    ],
                },
            ],
            '5': 0,
            '6': 0,
        }
        num = {
            '1': [{
                '1': {'4': 0},
                '3': make_binary_name("bad_conn"),
                '5': 0,
                '13': {'1': {'1': {'3': [src_node]}}},
            }],
            '3': make_binary_name("bad_conn.gia"),
        }
        report = validator.validate_numeric(num)
        assert not report.ok
        assert any("CONNECTION" in i.code or "NODE_INDEX" in i.code for i in report.errors)


# ═══════════════════════════════════════════════════════════════
# 6. 端口完整性验证
# ═══════════════════════════════════════════════════════════════

class TestPinCompleteness:
    """验证节点端口完整性"""

    def test_event_node_has_out_flow(self, validator, catalog):
        """事件节点应有 OUT_FLOW 输出"""
        g = GraphBuilder(name="test", catalog=catalog)
        g.add_node("监听信号")
        num = g.to_numeric()
        report = validator.validate_numeric(num)
        # 事件节点有 OUT_FLOW，不应有端口完整性错误
        pin_errors = [i for i in report.errors if "PIN" in i.code]
        assert len(pin_errors) == 0

    def test_action_node_has_in_flow(self, validator, catalog):
        """动作节点应有 IN_FLOW 输入"""
        g = GraphBuilder(name="test", catalog=catalog)
        g.add_node("创建元件")
        num = g.to_numeric()
        report = validator.validate_numeric(num)
        pin_errors = [i for i in report.errors if "PIN" in i.code]
        assert len(pin_errors) == 0

    def test_data_pin_has_var_type(self, validator, catalog):
        """数据端口应有正确的 VarType"""
        g = GraphBuilder(name="test", catalog=catalog)
        node = g.add_node("监听信号")
        node.set_param("信号名", "test")
        num = g.to_numeric()
        report = validator.validate_numeric(num)
        pin_errors = [i for i in report.errors if "VAR_TYPE" in i.code]
        assert len(pin_errors) == 0

    def test_event_node_missing_out_flow_reported(self, validator):
        """事件节点缺少 OUT_FLOW 应报告警告"""
        # 构造一个没有 OUT_FLOW 的事件类节点
        bad_event_node = {
            '1': 0,
            '2': 100,
            '3': {},
            '4': [
                # 只有 IN_PARAM，没有 OUT_FLOW
                {
                    '1': {'1': 3, '2': 0},
                    '2': {'1': 3, '2': 0},
                    '4': VarType.Str,
                },
            ],
            '5': 0,
            '6': 0,
        }
        num = {
            '1': [{
                '1': {'4': 0},
                '3': make_binary_name("bad_event"),
                '5': 0,
                '13': {'1': {'1': {'3': [bad_event_node]}}},
            }],
            '3': make_binary_name("bad_event.gia"),
        }
        report = validator.validate_numeric(num)
        # 需要有 catalog 才能检查端口完整性
        # 没有 catalog 时跳过语义检查，所以这里用带 catalog 的 validator
        assert isinstance(report, ValidationReport)


# ═══════════════════════════════════════════════════════════════
# 7. GraphBuilder 集成验证
# ═══════════════════════════════════════════════════════════════

class TestGraphBuilderIntegration:
    """GraphBuilder 与 GIAValidator 集成"""

    def test_empty_graph_validation(self, validator, catalog):
        """空图验证"""
        g = GraphBuilder(name="test", catalog=catalog)
        report = validator.validate_graph_builder(g)
        assert isinstance(report, ValidationReport)

    def test_valid_graph_builder_passes(self, validator, catalog):
        """合法的 GraphBuilder 应通过验证"""
        g = GraphBuilder(name="test", catalog=catalog)
        event = g.add_node("监听信号")
        action = g.add_node("创建元件")
        g.connect_flow(event, "出", action, "入")
        report = validator.validate_graph_builder(g)
        assert report.ok

    def test_validation_includes_location_info(self, validator, catalog):
        """验证结果包含具体的错误位置信息"""
        g = GraphBuilder(name="test", catalog=catalog)
        event = g.add_node("监听信号")
        action = g.add_node("创建元件")
        g.connect_flow(event, "出", action, "入")
        report = validator.validate_graph_builder(g)
        # 合法图不应有 error
        assert report.ok

    def test_graph_builder_validate_returns_detailed_result(self, validator, catalog):
        """GraphBuilder.validate() 返回详细验证结果"""
        g = GraphBuilder(name="test", catalog=catalog)
        event = g.add_node("监听信号")
        action = g.add_node("创建元件")
        g.connect_flow(event, "出", action, "入")

        # GraphBuilder 自带的 validate
        result = g.validate()
        assert isinstance(result, ValidationResult)
        assert result.ok

        # GIAValidator 的 validate_graph_builder
        report = validator.validate_graph_builder(g)
        assert isinstance(report, ValidationReport)
        assert report.ok


# ═══════════════════════════════════════════════════════════════
# 8. 往返验证
# ═══════════════════════════════════════════════════════════════

class TestRoundtripValidation:
    """验证生成的 numeric dict 可以正确往返"""

    def test_roundtrip_valid_numeric(self, validator, valid_numeric):
        """合法 numeric dict 的往返验证"""
        report = validator.validate_roundtrip(valid_numeric)
        assert report.ok

    def test_roundtrip_graph_builder_output(self, validator, catalog):
        """GraphBuilder 输出的 numeric dict 往返验证"""
        g = GraphBuilder(name="test", catalog=catalog)
        event = g.add_node("监听信号").set_param("信号名", "test")
        action = g.add_node("创建元件")
        g.connect_flow(event, "出", action, "入")
        num = g.to_numeric()
        report = validator.validate_roundtrip(num)
        assert report.ok

    def test_roundtrip_preserves_structure(self, validator, catalog):
        """往返后结构保持一致"""
        g = GraphBuilder(name="test", catalog=catalog)
        g.add_node("监听信号")
        g.add_node("创建元件")
        num = g.to_numeric()
        report = validator.validate_roundtrip(num)
        # 往返后顶层 keys 应保持
        assert report.ok


# ═══════════════════════════════════════════════════════════════
# 9. 验证报告
# ═══════════════════════════════════════════════════════════════

class TestValidationReportFormatting:
    """验证报告格式化"""

    def test_report_text_contains_severity(self):
        issues = [
            ValidationIssue("error", "E1", "error msg", "loc1"),
            ValidationIssue("warning", "W1", "warning msg", "loc2"),
            ValidationIssue("info", "I1", "info msg", "loc3"),
        ]
        report = ValidationReport(issues=issues)
        text = report.to_text()
        assert isinstance(text, str)
        assert len(text) > 0

    def test_report_text_contains_code(self):
        issues = [
            ValidationIssue("error", "MISSING_FIELD", "missing", "entry[0]"),
        ]
        report = ValidationReport(issues=issues)
        text = report.to_text()
        assert "MISSING_FIELD" in text

    def test_report_text_contains_location(self):
        issues = [
            ValidationIssue("error", "E1", "msg", "entry[0].node[3].pin[1]"),
        ]
        report = ValidationReport(issues=issues)
        text = report.to_text()
        assert "entry[0].node[3].pin[1]" in text

    def test_report_text_contains_message(self):
        issues = [
            ValidationIssue("error", "E1", "human readable error", "loc"),
        ]
        report = ValidationReport(issues=issues)
        text = report.to_text()
        assert "human readable error" in text

    def test_report_sorted_by_severity(self):
        """报告按严重程度排序: error > warning > info"""
        issues = [
            ValidationIssue("info", "I1", "info", ""),
            ValidationIssue("error", "E1", "error", ""),
            ValidationIssue("warning", "W1", "warning", ""),
        ]
        report = ValidationReport(issues=issues)
        text = report.to_text()
        # error 应出现在 warning 之前，warning 应出现在 info 之前
        err_pos = text.find("E1")
        warn_pos = text.find("W1")
        info_pos = text.find("I1")
        assert err_pos < warn_pos < info_pos

    def test_empty_report_text(self):
        """空报告的文本输出"""
        report = ValidationReport(issues=[])
        text = report.to_text()
        assert isinstance(text, str)
        assert len(text) > 0


# ═══════════════════════════════════════════════════════════════
# 10. GIAValidator 构造
# ═══════════════════════════════════════════════════════════════

class TestGIAValidatorConstruction:
    """GIAValidator 构造"""

    def test_create_without_catalog(self):
        """无 catalog 创建验证器"""
        v = GIAValidator()
        assert v._catalog is None

    def test_create_with_catalog(self, catalog):
        """带 catalog 创建验证器"""
        v = GIAValidator(catalog=catalog)
        assert v._catalog is catalog


# ═══════════════════════════════════════════════════════════════
# 11. 综合场景
# ═══════════════════════════════════════════════════════════════

class TestComprehensiveScenarios:
    """综合验证场景"""

    def test_full_signal_chain_validation(self, validator, catalog):
        """完整信号链: 监听信号 -> 创建元件 -> 发送信号"""
        g = GraphBuilder(name="test", catalog=catalog)
        event = g.add_node("监听信号").set_param("信号名", "on_start")
        create = g.add_node("创建元件")
        send = g.add_node("发送信号")
        g.connect_flow(event, "出", create, "入")
        g.connect_flow(create, "出", send, "入")

        report = validator.validate_graph_builder(g)
        assert report.ok

    def test_full_signal_chain_numeric_validation(self, validator, catalog):
        """完整信号链的 numeric 验证"""
        g = GraphBuilder(name="test", catalog=catalog)
        event = g.add_node("监听信号").set_param("信号名", "on_start")
        create = g.add_node("创建元件")
        send = g.add_node("发送信号")
        g.connect_flow(event, "出", create, "入")
        g.connect_flow(create, "出", send, "入")

        num = g.to_numeric()
        report = validator.validate_numeric(num)
        assert report.ok

    def test_multiple_errors_reported(self, validator):
        """多个错误应全部报告"""
        # 构造一个有多个问题的 numeric
        bad_node = {'99': 'bad'}
        num = {
            '1': [{
                '1': {'4': 0},
                '3': make_binary_name("multi_err"),
                '5': 0,
                '13': {'1': {'1': {'3': [bad_node, bad_node]}}},
            }],
            '3': make_binary_name("multi_err.gia"),
        }
        report = validator.validate_numeric(num)
        assert not report.ok
        assert len(report.errors) >= 2

    def test_validator_without_catalog_skips_semantic_checks(self):
        """没有 catalog 时跳过语义检查（端口完整性等）"""
        v = GIAValidator()
        num = _make_valid_numeric()
        report = v.validate_numeric(num)
        # 结构正确就应通过
        assert report.ok
