# -*- coding: utf-8 -*-
"""GIA 文件验证器

提供即时验证机制，对 GIA numeric dict 进行全面的结构和语义检查。
核心类：
- ValidationIssue: 单条验证问题
- ValidationReport: 验证报告（聚合多条问题）
- GIAValidator: 验证器主类
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from tools.live_sync.node_catalog import NodeCatalog, NodeDef, VarType
from tools.live_sync.gia_utils import (
    get_entries, get_ng_graph, get_ng_nodes,
    FLOW_KINDS, DATA_KINDS,
)


# ═══════════════════════════════════════════════════════════════
# 数据类
# ═══════════════════════════════════════════════════════════════

@dataclass
class ValidationIssue:
    """单条验证问题"""
    severity: str       # "error" | "warning" | "info"
    code: str           # 错误代码（如 "MISSING_FIELD", "INVALID_CONNECTION"）
    message: str        # 人类可读的错误描述
    location: str       # 错误位置（如 "entry[0].node[3].pin[1]"）


@dataclass
class ValidationReport:
    """验证报告 - 聚合多条验证问题"""
    issues: List[ValidationIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """没有 error 级别问题"""
        return not any(i.severity == "error" for i in self.issues)

    @property
    def errors(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def infos(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == "info"]

    def to_text(self) -> str:
        """生成人类可读的验证报告"""
        if not self.issues:
            return "Validation PASSED: 0 errors, 0 warnings"

        # 按严重程度排序: error > warning > info
        severity_order = {"error": 0, "warning": 1, "info": 2}
        sorted_issues = sorted(self.issues, key=lambda i: severity_order.get(i.severity, 99))

        lines: List[str] = []
        lines.append(f"Validation FAILED: {len(self.errors)} error(s), "
                     f"{len(self.warnings)} warning(s), {len(self.infos)} info(s)")
        lines.append("")

        for issue in sorted_issues:
            loc_str = f"[{issue.location}] " if issue.location else ""
            lines.append(f"  [{issue.severity.upper()}] {issue.code}: {loc_str}{issue.message}")

        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# GIAValidator
# ═══════════════════════════════════════════════════════════════

class GIAValidator:
    """GIA 文件结构验证器

    对 GIA numeric dict 进行全面的结构和语义检查，包括：
    - 顶层结构验证
    - Entry 结构验证
    - NodeGraph 结构验证
    - Node 结构验证
    - Pin 结构验证
    - 连线合法性验证
    - 端口完整性验证（需要 NodeCatalog）
    - 往返编码验证
    """

    def __init__(self, catalog: Optional[NodeCatalog] = None) -> None:
        self._catalog = catalog

    # ── 顶层验证 ──────────────────────────────────────────

    def validate_numeric(self, num: Dict[str, Any]) -> ValidationReport:
        """验证 GIA numeric dict 的完整结构"""
        issues: List[ValidationIssue] = []

        # 检查顶层 field '1'
        if '1' not in num:
            issues.append(ValidationIssue(
                severity="error",
                code="MISSING_FIELD",
                message="top-level field '1' (entries) is missing",
                location="",
            ))
            return ValidationReport(issues=issues)

        entries_raw = num['1']
        # entries 必须是 list 或 dict（单元素时 protobuf 可能解码为 dict）
        if isinstance(entries_raw, dict):
            entries = [entries_raw]
        elif isinstance(entries_raw, list):
            entries = entries_raw
        else:
            issues.append(ValidationIssue(
                severity="error",
                code="INVALID_TYPE",
                message=f"field '1' must be list or dict, got {type(entries_raw).__name__}",
                location="",
            ))
            return ValidationReport(issues=issues)

        if len(entries) == 0:
            issues.append(ValidationIssue(
                severity="error",
                code="EMPTY_ENTRIES",
                message="entries list is empty",
                location="",
            ))
            return ValidationReport(issues=issues)

        # 逐条验证 entry
        for idx, entry in enumerate(entries):
            if not isinstance(entry, dict):
                issues.append(ValidationIssue(
                    severity="error",
                    code="INVALID_TYPE",
                    message=f"entry[{idx}] is not a dict, got {type(entry).__name__}",
                    location=f"entry[{idx}]",
                ))
                continue
            issues.extend(self.validate_entry(entry, idx))

        return ValidationReport(issues=issues)

    # ── Entry 验证 ─────────────────────────────────────────

    def validate_entry(self, entry: Dict[str, Any], index: int) -> List[ValidationIssue]:
        """验证单个 entry 的结构"""
        issues: List[ValidationIssue] = []
        loc = f"entry[{index}]"

        # 检查必要字段
        if '1' not in entry:
            issues.append(ValidationIssue(
                severity="error",
                code="MISSING_FIELD",
                message="entry missing field '1' (Location)",
                location=loc,
            ))

        # 如果有 field '13'，说明是 NodeGraph entry
        if '13' in entry:
            issues.extend(self.validate_node_graph(entry, index))

        return issues

    # ── NodeGraph 验证 ─────────────────────────────────────

    def validate_node_graph(self, ng_entry: Dict[str, Any], index: int) -> List[ValidationIssue]:
        """验证 NodeGraph entry 的结构"""
        issues: List[ValidationIssue] = []
        loc = f"entry[{index}]"

        ng_field = ng_entry.get('13')
        if not isinstance(ng_field, dict):
            issues.append(ValidationIssue(
                severity="error",
                code="INVALID_NG_FIELD",
                message=f"field '13' must be a dict, got {type(ng_field).__name__}",
                location=f"{loc}.13",
            ))
            return issues

        # 提取 graph_unit: ng_field['1']['1']
        graph_unit = ng_field.get('1')
        if not isinstance(graph_unit, dict):
            issues.append(ValidationIssue(
                severity="error",
                code="INVALID_NG_FIELD",
                message="NodeGraph field '13.1' (graph_unit) is missing or not a dict",
                location=f"{loc}.13.1",
            ))
            return issues

        graph = graph_unit.get('1')
        if not isinstance(graph, dict):
            # 空的NodeGraph entry，graph字段可能是binary_data字符串，千星允许
            if graph is None or isinstance(graph, str):
                issues.append(ValidationIssue(
                    severity="info",
                    code="EMPTY_GRAPH",
                    message="NodeGraph entry has no graph data (empty graph), this is valid",
                    location=f"{loc}.13.1.1",
                ))
            else:
                issues.append(ValidationIssue(
                    severity="error",
                    code="INVALID_NG_FIELD",
                    message=f"graph_unit field '1' (graph) must be dict, got {type(graph).__name__}",
                    location=f"{loc}.13.1.1",
                ))
            return issues

        # 提取 nodes list
        nodes_raw = graph.get('3')
        if nodes_raw is None:
            issues.append(ValidationIssue(
                severity="error",
                code="MISSING_FIELD",
                message="graph missing field '3' (nodes list)",
                location=f"{loc}.graph",
            ))
            return issues

        if isinstance(nodes_raw, dict):
            nodes = [nodes_raw]
        elif isinstance(nodes_raw, list):
            nodes = nodes_raw
        else:
            issues.append(ValidationIssue(
                severity="error",
                code="INVALID_TYPE",
                message=f"graph field '3' must be list or dict, got {type(nodes_raw).__name__}",
                location=f"{loc}.graph.3",
            ))
            return issues

        total_nodes = len(nodes)

        # 逐节点验证
        for node_idx, node in enumerate(nodes):
            if not isinstance(node, dict):
                issues.append(ValidationIssue(
                    severity="error",
                    code="INVALID_TYPE",
                    message=f"node[{node_idx}] is not a dict, got {type(node).__name__}",
                    location=f"{loc}.node[{node_idx}]",
                ))
                continue
            issues.extend(self.validate_node(node, node_idx, total_nodes))

        # 验证连线（需要完整的节点列表）
        valid_nodes = [n for n in nodes if isinstance(n, dict)]
        for node_idx, node in enumerate(valid_nodes):
            issues.extend(self.validate_connections(node, node_idx, valid_nodes))

        return issues

    # ── Node 验证 ──────────────────────────────────────────

    def validate_node(
        self, node: Dict[str, Any], node_index: int, total_nodes: int
    ) -> List[ValidationIssue]:
        """验证单个 node 的结构"""
        issues: List[ValidationIssue] = []
        loc = f"node[{node_index}]"

        # 检查必要字段（field '4' pins 可缺失，千星允许空节点/注释节点）
        required_fields = {'1', '2'}
        for f in required_fields:
            if f not in node:
                issues.append(ValidationIssue(
                    severity="error",
                    code="MISSING_NODE_FIELD",
                    message=f"node missing field '{f}'",
                    location=loc,
                ))

        # 验证 pins（field '4'）
        pins_raw = node.get('4')
        if pins_raw is None:
            # 空节点，没有pins，千星允许
            return issues
        if isinstance(pins_raw, str):
            # binary_data 编码的pins，千星某些节点使用此格式
            issues.append(ValidationIssue(
                severity="warning",
                code="BINARY_PINS",
                message="node field '4' (pins) is binary_data encoded, skipping pin validation",
                location=f"{loc}.4",
            ))
            return issues
        if isinstance(pins_raw, dict):
            pins = [pins_raw]
        elif isinstance(pins_raw, list):
            pins = pins_raw
        else:
            issues.append(ValidationIssue(
                severity="error",
                code="INVALID_TYPE",
                message=f"node field '4' (pins) must be list or dict, got {type(pins_raw).__name__}",
                location=f"{loc}.4",
            ))
            return issues

        for pin_idx, pin in enumerate(pins):
            if not isinstance(pin, dict):
                issues.append(ValidationIssue(
                    severity="error",
                    code="INVALID_TYPE",
                    message=f"pin[{pin_idx}] is not a dict",
                    location=f"{loc}.pin[{pin_idx}]",
                ))
                continue
            issues.extend(self.validate_pin(pin, node_index, pin_idx))

        return issues

    # ── Pin 验证 ───────────────────────────────────────────

    def validate_pin(
        self, pin: Dict[str, Any], node_index: int, pin_index: int
    ) -> List[ValidationIssue]:
        """验证单个 pin 的结构"""
        issues: List[ValidationIssue] = []
        loc = f"node[{node_index}].pin[{pin_index}]"

        # 检查 PinSignature (field '1')
        sig = pin.get('1')
        if not isinstance(sig, dict):
            issues.append(ValidationIssue(
                severity="error",
                code="MISSING_PIN_SIGNATURE",
                message=f"pin missing field '1' (PinSignature) or it is not a dict",
                location=loc,
            ))
            return issues

        # 检查 PinSignature 内部结构
        if '1' not in sig:
            issues.append(ValidationIssue(
                severity="error",
                code="MISSING_PIN_FIELD",
                message="PinSignature missing field '1' (kind)",
                location=f"{loc}.1",
            ))
        if '2' not in sig:
            # pin index 缺失不是致命错误，千星编辑器允许隐式按顺序推断
            issues.append(ValidationIssue(
                severity="warning",
                code="MISSING_PIN_INDEX",
                message="PinSignature missing field '2' (index), will be inferred by order",
                location=f"{loc}.1",
            ))

        return issues

    # ── 连线验证 ───────────────────────────────────────────

    def validate_connections(
        self, node: Dict[str, Any], node_index: int,
        all_nodes: List[Dict[str, Any]],
    ) -> List[ValidationIssue]:
        """验证节点的所有连线"""
        issues: List[ValidationIssue] = []
        loc = f"node[{node_index}]"

        pins_raw = node.get('4', [])
        if isinstance(pins_raw, dict):
            pins = [pins_raw]
        elif isinstance(pins_raw, list):
            pins = pins_raw
        else:
            return issues

        # 构建节点索引集合用于快速查找
        node_indices: Set[int] = set()
        for n in all_nodes:
            idx = n.get('1')
            if isinstance(idx, int):
                node_indices.add(idx)

        # 用于检测重复连线
        seen_connections: Set[Tuple[int, int, int, int]] = set()

        for pin_idx, pin in enumerate(pins):
            if not isinstance(pin, dict):
                continue

            connections = pin.get('5')
            if not isinstance(connections, list):
                continue

            # 获取源 pin 的 kind
            src_sig = pin.get('1')
            if not isinstance(src_sig, dict):
                continue
            src_kind = src_sig.get('1')
            src_pin_index = src_sig.get('2')
            if not isinstance(src_kind, int) or not isinstance(src_pin_index, int):
                continue

            for conn_idx, conn in enumerate(connections):
                if not isinstance(conn, dict):
                    continue

                conn_loc = f"{loc}.pin[{pin_idx}].conn[{conn_idx}]"

                # 检查目标节点索引
                target_node_idx = conn.get('1')
                if not isinstance(target_node_idx, int):
                    issues.append(ValidationIssue(
                        severity="error",
                        code="INVALID_CONNECTION",
                        message="connection missing target node index (field '1')",
                        location=conn_loc,
                    ))
                    continue

                # 检查目标节点是否存在
                if target_node_idx not in node_indices:
                    issues.append(ValidationIssue(
                        severity="error",
                        code="INVALID_CONNECTION",
                        message=f"connection target node index {target_node_idx} does not exist",
                        location=conn_loc,
                    ))
                    continue

                # 检查自连接
                if target_node_idx == node_index:
                    issues.append(ValidationIssue(
                        severity="error",
                        code="SELF_CONNECT",
                        message=f"node[{node_index}] connects to itself",
                        location=conn_loc,
                    ))

                # 获取目标 pin 的 kind
                dst_sig = conn.get('2')
                if not isinstance(dst_sig, dict):
                    continue
                dst_kind = dst_sig.get('1')
                dst_pin_index = dst_sig.get('2')
                if not isinstance(dst_kind, int) or not isinstance(dst_pin_index, int):
                    continue

                # 检查流程/数据端口匹配
                if src_kind in FLOW_KINDS and dst_kind in DATA_KINDS:
                    issues.append(ValidationIssue(
                        severity="error",
                        code="INVALID_CONNECTION",
                        message=(
                            f"flow pin (kind={src_kind}) cannot connect to "
                            f"data pin (kind={dst_kind})"
                        ),
                        location=conn_loc,
                    ))
                elif src_kind in DATA_KINDS and dst_kind in FLOW_KINDS:
                    issues.append(ValidationIssue(
                        severity="error",
                        code="INVALID_CONNECTION",
                        message=(
                            f"data pin (kind={src_kind}) cannot connect to "
                            f"flow pin (kind={dst_kind})"
                        ),
                        location=conn_loc,
                    ))

                # 检查重复连线
                conn_key = (node_index, src_kind, src_pin_index,
                            target_node_idx, dst_kind, dst_pin_index)
                # 简化 key: (src_node, src_kind, src_idx, dst_node, dst_kind, dst_idx)
                dup_key = (node_index, src_kind, src_pin_index,
                           target_node_idx, dst_kind, dst_pin_index)
                if dup_key in seen_connections:
                    issues.append(ValidationIssue(
                        severity="error",
                        code="DUPLICATE_CONNECTION",
                        message=(
                            f"duplicate connection: node[{node_index}].pin(kind={src_kind},"
                            f"idx={src_pin_index}) -> node[{target_node_idx}]."
                            f"pin(kind={dst_kind},idx={dst_pin_index})"
                        ),
                        location=conn_loc,
                    ))
                seen_connections.add(dup_key)

        return issues

    # ── GraphBuilder 集成验证 ──────────────────────────────

    def validate_graph_builder(self, graph: Any) -> ValidationReport:
        """验证 GraphBuilder 构建的图

        将 GraphBuilder 导出为 numeric dict，然后进行全面验证。
        """
        issues: List[ValidationIssue] = []

        # 导出 numeric dict
        num = graph.to_numeric()

        # 结构验证
        structural_report = self.validate_numeric(num)
        issues.extend(structural_report.issues)

        # 如果有 catalog，进行语义验证
        if self._catalog is not None:
            issues.extend(self._validate_graph_builder_semantics(graph))

        return ValidationReport(issues=issues)

    def _validate_graph_builder_semantics(self, graph: Any) -> List[ValidationIssue]:
        """GraphBuilder 的语义验证（端口完整性等）"""
        issues: List[ValidationIssue] = []

        # 遍历所有节点，检查端口完整性
        for i in range(graph.node_count()):
            handle = graph.get_node(i)
            node_def = handle.node_def
            loc = f"node[{i}] ({node_def.name})"

            # 事件节点应有 OUT_FLOW
            if node_def.category == "event":
                has_out_flow = any(p.is_flow and p.direction == "Out"
                                   for p in node_def.outputs)
                if not has_out_flow:
                    issues.append(ValidationIssue(
                        severity="warning",
                        code="MISSING_OUT_FLOW",
                        message=f"event node '{node_def.name}' has no OUT_FLOW output",
                        location=loc,
                    ))

            # 动作节点应有 IN_FLOW
            if node_def.category == "action":
                has_in_flow = any(p.is_flow and p.direction == "In"
                                  for p in node_def.inputs)
                if not has_in_flow:
                    issues.append(ValidationIssue(
                        severity="warning",
                        code="MISSING_IN_FLOW",
                        message=f"action node '{node_def.name}' has no IN_FLOW input",
                        location=loc,
                    ))

        return issues

    # ── 往返验证 ───────────────────────────────────────────

    def validate_roundtrip(self, num: Dict[str, Any]) -> ValidationReport:
        """验证 numeric dict 的 encode→decode 往返一致性"""
        issues: List[ValidationIssue] = []

        try:
            from private_extensions.ugc_file_tools.gil_dump_codec.protobuf_like import (
                encode_message, decode_message_to_field_map,
            )
            from private_extensions.ugc_file_tools.gil_dump_codec.protobuf_like_bridge import (
                decoded_field_map_to_numeric_message,
            )
        except ImportError:
            issues.append(ValidationIssue(
                severity="warning",
                code="ROUNDTRIP_SKIP",
                message="cannot import encoding modules, roundtrip check skipped",
                location="",
            ))
            return ValidationReport(issues=issues)

        try:
            # encode
            proto = encode_message(num)
            # decode
            fm, _ = decode_message_to_field_map(
                data_bytes=proto, start_offset=0, end_offset=len(proto), remaining_depth=64
            )
            re_num = decoded_field_map_to_numeric_message(fm, prefer_raw_hex_for_utf8=True)

            # 比较顶层 keys
            orig_keys = set(num.keys())
            re_keys = set(re_num.keys())
            if orig_keys != re_keys:
                issues.append(ValidationIssue(
                    severity="error",
                    code="ROUNDTRIP_KEY_MISMATCH",
                    message=(
                        f"top-level keys changed after roundtrip: "
                        f"original={sorted(orig_keys)}, roundtrip={sorted(re_keys)}"
                    ),
                    location="",
                ))

            # 比较 entries 数量
            orig_entries = num.get('1', [])
            re_entries = re_num.get('1', [])
            if isinstance(orig_entries, dict):
                orig_count = 1
            elif isinstance(orig_entries, list):
                orig_count = len(orig_entries)
            else:
                orig_count = 0

            if isinstance(re_entries, dict):
                re_count = 1
            elif isinstance(re_entries, list):
                re_count = len(re_entries)
            else:
                re_count = 0

            if orig_count != re_count:
                issues.append(ValidationIssue(
                    severity="error",
                    code="ROUNDTRIP_ENTRY_COUNT_MISMATCH",
                    message=(
                        f"entry count changed after roundtrip: "
                        f"original={orig_count}, roundtrip={re_count}"
                    ),
                    location="",
                ))

        except Exception as e:
            issues.append(ValidationIssue(
                severity="error",
                code="ROUNDTRIP_ERROR",
                message=f"roundtrip encode/decode failed: {e}",
                location="",
            ))

        return ValidationReport(issues=issues)
