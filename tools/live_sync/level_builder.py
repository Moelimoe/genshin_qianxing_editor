# -*- coding: utf-8 -*-
"""声明式关卡构建 API

在 NodeCatalog 之上提供高层语义 API，让 AI 可以用声明式方式构建节点图。
核心类：
- NodeHandle: 节点句柄，AI 操作节点的入口
- GraphBuilder: 声明式节点图构建器
- LevelBuilder: 关卡构建器，管理多个节点图
"""
from __future__ import annotations

import copy
import logging
import struct
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from tools.live_sync.node_catalog import (
    NodeCatalog, NodeDef, PinDef, VarType, ValidationResult,
)
from tools.live_sync.verified_type_ids import lookup_by_name as _lookup_verified
from tools.live_sync.gia_utils import (
    save_gia_numeric, make_binary_name, load_gia_numeric,
    format_binary_data_hex_text,
    PIN_KIND_IN_FLOW, PIN_KIND_OUT_FLOW, PIN_KIND_IN_PARAM, PIN_KIND_OUT_PARAM,
)
from private_extensions.ugc_file_tools.gil_dump_codec.protobuf_like import (
    encode_varint,
)

logger = logging.getLogger("live_sync.builder")


# ═══════════════════════════════════════════════════════════════
# 金币实体模板（从编辑器导出的合法 GIA 加载）
# ═══════════════════════════════════════════════════════════════

_ENTITY_TEMPLATE_PATH = Path(__file__).resolve().parent / "samples" / "test_z_three_nodes.gia"

def _load_entity_template() -> Dict[str, Any]:
    """从参考 GIA 加载金币 entity entry 作为模板"""
    if not _ENTITY_TEMPLATE_PATH.exists():
        logger.error("找不到实体模板: %s", _ENTITY_TEMPLATE_PATH)
        return {}
    num = load_gia_numeric(_ENTITY_TEMPLATE_PATH)
    for e in num.get('1', []):
        if isinstance(e, dict) and e.get('5') == 1:
            return copy.deepcopy(e)
    return {}

_ENTITY_TEMPLATE: Optional[Dict[str, Any]] = None

def _get_entity_template() -> Dict[str, Any]:
    global _ENTITY_TEMPLATE
    if _ENTITY_TEMPLATE is None:
        _ENTITY_TEMPLATE = _load_entity_template()
    return _ENTITY_TEMPLATE


# ═══════════════════════════════════════════════════════════════
# 内部辅助
# ═══════════════════════════════════════════════════════════════

def _build_var_base(var_type: int, value: Any, for_output: bool = False) -> Dict[str, Any]:
    """根据 VarType 构造 VarBase dict（编辑器真实导入格式）

    从编辑器导出的 示例关卡资产.gia 中提取的真实格式:

    关键发现（CC分析）：
    - Int 类型必须使用 tag=10000，嵌套在 field[110].field[2] 中
    - 输出数据引脚也需要 VarBase（即使值为空）

    基础结构:
    {
        "1": data_tag,              # 数据标记 (决定数据放在哪个 field)
        "2": 1,                     # 固定标志
        "4": {"1": 1, "100": {"1": var_type}},  # 类型描述嵌套
        "XXX": value_data           # 值字段
    }

    data_tag 映射 (决定数据存储位置):
        VarType.Int (3)  → tag=10000, field[110].field[2] = {...}
        VarType.Str (6)  → tag=5, field[105] = binary_data
        VarType.Bol (4)  → tag=6, field[106] = {"1": 0 或 1} 或 binary_data (False)
        VarType.Flt (5)  → tag=4, field[104] = {"1": float_value}
        VarType.Vec (12) → tag=7, field[107] = binary_data
        VarType.Cfg (20) → tag=1, field[101] = {"1": int_value}
        VarType.Ety (1)  → tag=1, field[101] = {"1": int_value}
        未知/Int-like    → tag=10000, field[110].field[2] = {...}
    """
    if var_type == VarType.Str:
        # 样本使用 protobuf-wrapped 格式：field[105] = protobuf_msg({1: string})
        if value is not None:
            raw = str(value).encode('utf-8')
            wrapped = b'\x0A' + encode_varint(len(raw)) + raw
        else:
            wrapped = b'\x0A\x00'  # 空字符串
        return {
            '1': 5, '2': 1,
            '4': {'1': 1, '100': {'1': var_type}},
            '105': format_binary_data_hex_text(wrapped),
        }
    elif var_type == VarType.Bol:
        if value is True:
            return {
                '1': 6, '2': 1,
                '4': {'1': 1, '100': {'1': var_type}},
                '106': {'1': 1},
            }
        else:
            # Bool=False: 使用空 binary_data（与编辑器导出格式一致）
            return {
                '1': 6, '2': 1,
                '4': {'1': 1, '100': {'1': var_type}},
                '106': format_binary_data_hex_text(b''),
            }
    elif var_type == VarType.Enum:
        # 枚举类型和 Bool 一样用 cls=6/field[106]，值是 enum_item_id
        if value is not None:
            return {
                '1': 6, '2': 1,
                '4': {'1': 1, '100': {'1': var_type}},
                '106': {'1': int(value)},
            }
        else:
            return {
                '1': 6, '2': 1,
                '4': {'1': 1, '100': {'1': var_type}},
                '106': make_binary_name(''),
            }
    elif var_type == VarType.Flt:
        if value is not None:
            return {
                '1': 4, '2': 1,
                '4': {'1': 1, '100': {'1': var_type}},
                '104': {'1': float(value)},
            }
        else:
            return {
                '1': 4, '2': 1,
                '4': {'1': 1, '100': {'1': var_type}},
                '104': format_binary_data_hex_text(b''),
            }
    elif var_type == VarType.Vec:
        if isinstance(value, (list, tuple)) and len(value) == 3:
            x, y, z = (float(v) for v in value)
        else:
            x, y, z = float(value) if value is not None else 0.0, 0.0, 0.0
        import struct as _struct
        data = _struct.pack('>fff', x, y, z)
        # 编辑器格式：field[107] 必须包裹在 dict 的 '1' 键中
        # 零向量使用空 binary_data（与编辑器导出格式一致）
        if x == 0.0 and y == 0.0 and z == 0.0:
            vec_data = format_binary_data_hex_text(b'')
        else:
            vec_data = format_binary_data_hex_text(data)
        return {
            '1': 7, '2': 1,
            '4': {'1': 1, '100': {'1': var_type}},
            '107': {'1': vec_data},
        }
    elif var_type in (VarType.Config, VarType.Ety, VarType.GUID):
        # Config/Ety/GUID → tag=1, field[101]
        if value is not None:
            return {
                '1': 1, '2': 1,
                '4': {'1': 1, '100': {'1': var_type}},
                '101': {'1': int(value)},
            }
        else:
            # 空值（输出引脚）
            return {
                '1': 1, '2': 1,
                '4': {'1': 1, '100': {'1': var_type}},
                '101': format_binary_data_hex_text(b''),
            }
    else:
        # Int/未知 → tag=10000, field[110].field[2]（CC分析的关键修复）
        # 样本格式：{'1': 10000, '110': {'2': {...}}, '2': 1}
        inner = {
            '1': 2,  # inner tag
            '4': {'1': 1, '100': {'1': var_type if var_type else 3}},
        }
        if value is not None and value != 0:
            inner['2'] = 1
            inner['102'] = {'1': int(value)}
        else:
            # 空值/默认值：用于输出引脚或仅连线无值的输入引脚
            inner['102'] = format_binary_data_hex_text(b'')
        return {
            '1': 10000,
            '110': {'2': inner},
            '2': 1,
        }


def _pin_kind(direction: str, is_flow: bool) -> int:
    """根据方向和类型确定 pin kind"""
    if is_flow:
        return PIN_KIND_IN_FLOW if direction == "In" else PIN_KIND_OUT_FLOW
    else:
        return PIN_KIND_IN_PARAM if direction == "In" else PIN_KIND_OUT_PARAM


def _find_pin_by_name(pins: tuple[PinDef, ...], name: str) -> Optional[PinDef]:
    """按名称查找端口"""
    for p in pins:
        if p.name == name:
            return p
    return None


# ═══════════════════════════════════════════════════════════════
# NodeHandle
# ═══════════════════════════════════════════════════════════════

class NodeHandle:
    """节点句柄 - AI 操作节点的入口

    持有对 GraphBuilder 的反向引用，支持链式调用。
    """

    def __init__(self, graph: GraphBuilder, node_def: NodeDef, index: int) -> None:
        self._graph = graph
        self._node_def = node_def
        self._index = index
        self._params: Dict[str, Any] = {}
        self._x: int = 0
        self._y: int = 0

    @property
    def type_id(self) -> int:
        return self._node_def.type_id

    @property
    def name(self) -> str:
        return self._node_def.name

    @property
    def index(self) -> int:
        return self._index

    @property
    def x(self) -> int:
        return self._x

    @x.setter
    def x(self, value: int) -> None:
        self._x = value

    @property
    def y(self) -> int:
        return self._y

    @y.setter
    def y(self, value: int) -> None:
        self._y = value

    @property
    def node_def(self) -> NodeDef:
        return self._node_def

    def set_param(self, port_name: str, value: Any) -> NodeHandle:
        """设置输入参数常量，返回 self 支持链式调用

        优先查找输入引脚，其次查找 node_params。
        """
        # 先查找输入端口
        pin = _find_pin_by_name(self._node_def.inputs, port_name)
        if pin is None:
            # 再查找 node_params
            pin = _find_pin_by_name(self._node_def.node_params, port_name)
        if pin is None:
            raise ValueError(
                f"节点 '{self._node_def.name}' 没有名为 '{port_name}' 的输入端口或节点参数"
            )
        self._params[port_name] = value
        return self

    def get_param(self, port_name: str) -> Any:
        """获取已设置的参数值"""
        return self._params.get(port_name)

    def connect_flow(self, out_port: str, dst: NodeHandle, dst_port: str) -> NodeHandle:
        """连接流程端口，返回 self 支持链式调用"""
        self._graph.connect_flow(self, out_port, dst, dst_port)
        return self

    def connect_data(self, out_port: str, dst: NodeHandle, dst_port: str) -> NodeHandle:
        """连接数据端口，返回 self 支持链式调用"""
        self._graph.connect_data(self, out_port, dst, dst_port)
        return self


# ═══════════════════════════════════════════════════════════════
# GraphBuilder
# ═══════════════════════════════════════════════════════════════

class GraphBuilder:
    """声明式节点图构建器

    支持添加节点、设置参数、连线、验证、快照/回滚、自动布局、导出。
    """

    def __init__(
        self,
        name: str,
        catalog: Optional[NodeCatalog] = None,
        graph_type: str = "ENTITY_NODE_GRAPH",
    ) -> None:
        self.name = name
        self._catalog = catalog
        self.graph_type = graph_type
        self._nodes: List[NodeHandle] = []
        self._connections: List[Dict[str, Any]] = []
        self._snapshots: List[Dict[str, Any]] = []

    # ── 添加节点 ──────────────────────────────────────────

    def add_node(self, name_or_id: Union[str, int, None] = None, **params) -> NodeHandle:
        """添加节点，返回 NodeHandle

        Args:
            name_or_id: 节点名称(str)或 type_id(int)
            **params: 直接设置输入参数

        Returns:
            NodeHandle 节点句柄
        """
        # 支持 type_id 作为关键字参数传入
        if name_or_id is None and 'type_id' in params:
            name_or_id = params.pop('type_id')

        node_def: Optional[NodeDef] = None
        user_specified_type_id = isinstance(name_or_id, int)  # 用户是否明确指定了 type_id

        if isinstance(name_or_id, str):
            # 按名称查找
            if self._catalog is not None:
                node_def = self._catalog.get_by_name(name_or_id)
            if node_def is None:
                raise ValueError(f"未找到名为 '{name_or_id}' 的节点")
        elif isinstance(name_or_id, int):
            # 按 type_id 查找
            if self._catalog is not None:
                node_def = self._catalog.get_by_id(name_or_id)
            if node_def is None:
                raise ValueError(f"未找到 type_id={name_or_id} 的节点")
        else:
            raise ValueError("必须提供节点名称(str)或 type_id(int)")

        # 检查 type_id 是否已验证
        # 如果用户明确指定了 type_id，优先使用用户指定的值，不覆盖
        if not user_specified_type_id:
            verified = _lookup_verified(node_def.name)
            real_type_id = verified['type_id']

            if real_type_id is not None:
                # 使用已验证的真实 type_id 覆盖 catalog 中的值
                from dataclasses import replace
                node_def = replace(node_def, type_id=real_type_id)
                logger.debug(
                    "✅ 节点 '%s' type_id=%d (已验证, confidence=%s)",
                    node_def.name, real_type_id, verified['confidence'],
                )
            else:
                logger.warning(
                    "⚠️  节点 '%s' 的 type_id 未经验证。"
                    "当前使用 catalog 中的 type_id=%d，编辑器可能无法识别此节点。",
                    node_def.name, node_def.type_id,
                )
        else:
            # 用户明确指定了 type_id，直接使用
            logger.debug(
                "✅ 节点 '%s' type_id=%d (用户指定)",
                node_def.name, node_def.type_id,
            )

        index = len(self._nodes)
        handle = NodeHandle(self, node_def, index)
        # 设置参数
        for k, v in params.items():
            handle.set_param(k, v)
        self._nodes.append(handle)
        return handle

    # ── 连线 ──────────────────────────────────────────────

    def connect_flow(
        self,
        src: NodeHandle,
        src_port: str,
        dst: NodeHandle,
        dst_port: str,
    ) -> GraphBuilder:
        """连接流程端口，返回 self 支持链式调用"""
        self._validate_connection(src, src_port, dst, dst_port, expect_flow=True)
        self._connections.append({
            'type': 'flow',
            'src': src,
            'src_port': src_port,
            'dst': dst,
            'dst_port': dst_port,
        })
        return self

    def connect_data(
        self,
        src: NodeHandle,
        src_port: str,
        dst: NodeHandle,
        dst_port: str,
    ) -> GraphBuilder:
        """连接数据端口，返回 self 支持链式调用"""
        self._validate_connection(src, src_port, dst, dst_port, expect_flow=False)
        self._connections.append({
            'type': 'data',
            'src': src,
            'src_port': src_port,
            'dst': dst,
            'dst_port': dst_port,
        })
        return self

    def _validate_connection(
        self,
        src: NodeHandle,
        src_port: str,
        dst: NodeHandle,
        dst_port: str,
        expect_flow: bool,
    ) -> None:
        """校验连接合法性"""
        src_pin = _find_pin_by_name(src.node_def.outputs, src_port)
        if src_pin is None:
            # 也检查 inputs（方向错误）
            if _find_pin_by_name(src.node_def.inputs, src_port) is not None:
                raise ValueError(f"源端口 '{src_port}' 是输入端口，不能作为连接源")
            raise ValueError(f"源节点 '{src.name}' 没有名为 '{src_port}' 的输出端口")

        dst_pin = _find_pin_by_name(dst.node_def.inputs, dst_port)
        if dst_pin is None:
            if _find_pin_by_name(dst.node_def.outputs, dst_port) is not None:
                raise ValueError(f"目标端口 '{dst_port}' 是输出端口，不能作为连接目标")
            raise ValueError(f"目标节点 '{dst.name}' 没有名为 '{dst_port}' 的输入端口")

        # 流程/数据类型检查
        if src_pin.is_flow != expect_flow:
            actual = "流程" if src_pin.is_flow else "数据"
            expected = "流程" if expect_flow else "数据"
            raise ValueError(
                f"端口类型不匹配：源 '{src_port}' 是{actual}端口，期望{expected}端口"
            )

        if dst_pin.is_flow != expect_flow:
            actual = "流程" if dst_pin.is_flow else "数据"
            expected = "流程" if expect_flow else "数据"
            raise ValueError(
                f"端口类型不匹配：目标 '{dst_port}' 是{actual}端口，期望{expected}端口"
            )

        # 使用 catalog 做更严格的类型检查
        if self._catalog is not None:
            result = self._catalog.can_connect(src.node_def, src_port, dst.node_def, dst_port)
            if not result.ok:
                raise ValueError("; ".join(result.errors))

    # ── 验证 ──────────────────────────────────────────────

    def validate(self) -> ValidationResult:
        """验证图的正确性"""
        errors: list[str] = []

        # 检查所有连线
        for conn in self._connections:
            src = conn['src']
            src_port = conn['src_port']
            dst = conn['dst']
            dst_port = conn['dst_port']

            src_pin = _find_pin_by_name(src.node_def.outputs, src_port)
            dst_pin = _find_pin_by_name(dst.node_def.inputs, dst_port)

            if src_pin is None:
                errors.append(f"连线错误：源节点 '{src.name}' 没有输出端口 '{src_port}'")
            if dst_pin is None:
                errors.append(f"连线错误：目标节点 '{dst.name}' 没有输入端口 '{dst_port}'")

        return ValidationResult(ok=len(errors) == 0, errors=errors)

    # ── 快照 / 回滚 ──────────────────────────────────────

    def snapshot(self) -> None:
        """保存当前状态快照"""
        state = {
            'nodes': [
                {
                    'type_id': n.type_id,
                    'name': n.name,
                    'params': dict(n._params),
                    'x': n.x,
                    'y': n.y,
                }
                for n in self._nodes
            ],
            'connections': [
                {
                    'type': c['type'],
                    'src_index': c['src'].index,
                    'src_port': c['src_port'],
                    'dst_index': c['dst'].index,
                    'dst_port': c['dst_port'],
                }
                for c in self._connections
            ],
        }
        self._snapshots.append(state)

    def undo(self) -> None:
        """回滚到上一个快照"""
        if not self._snapshots:
            return

        state = self._snapshots.pop()

        # 重建节点
        new_nodes: List[NodeHandle] = []
        for node_data in state['nodes']:
            node_def = self._catalog.get_by_id(node_data['type_id']) if self._catalog else None
            if node_def is None:
                # 尝试按名称查找
                if self._catalog:
                    node_def = self._catalog.get_by_name(node_data['name'])
                if node_def is None:
                    # 创建一个最小的 NodeDef
                    node_def = NodeDef(
                        type_id=node_data['type_id'],
                        name=node_data['name'],
                        category="action",
                        description="",
                    )
            index = len(new_nodes)
            handle = NodeHandle(self, node_def, index)
            handle._params = dict(node_data['params'])
            handle._x = node_data['x']
            handle._y = node_data['y']
            new_nodes.append(handle)
        self._nodes = new_nodes

        # 重建连线
        new_connections: List[Dict[str, Any]] = []
        for conn_data in state['connections']:
            src_idx = conn_data['src_index']
            dst_idx = conn_data['dst_index']
            if src_idx < len(self._nodes) and dst_idx < len(self._nodes):
                new_connections.append({
                    'type': conn_data['type'],
                    'src': self._nodes[src_idx],
                    'src_port': conn_data['src_port'],
                    'dst': self._nodes[dst_idx],
                    'dst_port': conn_data['dst_port'],
                })
        self._connections = new_connections

    # ── 自动布局 ──────────────────────────────────────────

    def auto_layout(self, x_spacing: int = 300, y_spacing: int = 200) -> None:
        """自动排列节点坐标

        使用 BFS 按流程连线确定层级，X 按层级递增，Y 按同层节点递增。
        纯数据节点（无 flow 连线）放在其连接目标节点的上方。
        """
        if not self._nodes:
            return

        # 区分 flow 节点和纯数据节点
        flow_nodes = [n for n in self._nodes if any(
            c['type'] == 'flow' and (c['src'] is n or c['dst'] is n)
            for c in self._connections
        )]
        data_only_nodes = [n for n in self._nodes if n not in flow_nodes]

        # 构建邻接表（仅 flow 连线）
        children: Dict[int, List[int]] = {n.index: [] for n in flow_nodes}
        in_degree: Dict[int, int] = {n.index: 0 for n in flow_nodes}

        for conn in self._connections:
            if conn['type'] == 'flow':
                src_idx = conn['src'].index
                dst_idx = conn['dst'].index
                if src_idx in children:
                    children[src_idx].append(dst_idx)
                if dst_idx in in_degree:
                    in_degree[dst_idx] += 1

        # BFS 分层（仅 flow 节点）
        layers: List[List[int]] = []
        visited: set[int] = set()

        queue = [idx for idx, deg in in_degree.items() if deg == 0]
        if not queue and flow_nodes:
            queue = [flow_nodes[0].index]

        while queue:
            layers.append(list(queue))
            next_queue: List[int] = []
            for idx in queue:
                visited.add(idx)
                for child in children[idx]:
                    if child not in visited:
                        next_queue.append(child)
            queue = next_queue

        # 未被访问的 flow 节点放到最后一层
        unvisited = [n.index for n in flow_nodes if n.index not in visited]
        if unvisited:
            layers.append(unvisited)

        # 分配坐标（flow 节点）
        node_index_map = {n.index: n for n in self._nodes}
        for layer_idx, layer in enumerate(layers):
            x = layer_idx * x_spacing
            for pos_in_layer, node_idx in enumerate(layer):
                y = pos_in_layer * y_spacing
                node_index_map[node_idx].x = x
                node_index_map[node_idx].y = y

        # 纯数据节点：放在其数据连接目标节点的上方（y 减小），x 与目标相同
        # 按拓扑排序处理：先处理目标不是纯数据节点的，再处理依赖其他纯数据节点的
        data_index_set = {n.index for n in data_only_nodes}
        target_y_offsets: Dict[int, int] = {}  # target.index -> next_y_offset

        # 多轮处理，每轮处理目标不是未处理纯数据节点的
        remaining = list(data_only_nodes)
        max_rounds = len(remaining) + 1
        for _ in range(max_rounds):
            if not remaining:
                break
            next_remaining = []
            for data_node in remaining:
                # 找这个数据节点的输出连接目标
                target = None
                for conn in self._connections:
                    if conn['src'] is data_node:
                        target = conn['dst']
                        break
                if target is None:
                    data_node.x = 0
                    data_node.y = 0
                    continue
                # 如果目标还未处理（是纯数据节点且坐标还是默认值），跳过
                if target.index in data_index_set and target.x == 0 and target.y == 0:
                    next_remaining.append(data_node)
                    continue
                # 分配坐标：放在目标下方，y 递增避免重叠
                offset = target_y_offsets.get(target.index, 0)
                data_node.x = target.x
                data_node.y = target.y + y_spacing + offset * y_spacing
                target_y_offsets[target.index] = offset + 1
            remaining = next_remaining

    # ── 导出 numeric dict ─────────────────────────────────

    def to_numeric(self) -> Dict[str, Any]:
        """导出为 numeric dict（用于测试或进一步处理）"""
        return self._build_numeric()

    def _build_numeric(self) -> Dict[str, Any]:
        """构建完整的 GIA numeric dict"""
        # 自动布局（确保节点不重叠）
        if self._nodes:
            self.auto_layout()

        # 从模板获取 entity 的固定 loc_id（如金币=1077936129）
        template = _get_entity_template()
        entity_loc_id = template['1']['4'] if template else 1077936129

        # 确定性计算 ng_loc_id（相同 entity + 图名 = 相同 loc_id，可复现）
        name_hash = abs(hash(self.name)) & 0xFFFFFF
        ng_loc_id = 0x40000000 | (((entity_loc_id >> 4) ^ name_hash) & 0x0FFFFFFF)

        # 构建 graph dict（graph_id = ng_loc_id，匹配编辑器导出格式）
        graph_dict = self._build_graph_dict(graph_id=ng_loc_id)

        # 构建 NG entry
        ng_entry = self._build_ng_entry(graph_dict, ng_loc_id=ng_loc_id)

        # 构建 entity entry（保留模板固定 loc_id，仅替换 NG 引用）
        entity_entry = self._build_entity_entry(ng_loc_id=ng_loc_id)

        # 构建 GIA 顶层（entity 在前，NG 在后 — 编辑器依赖此顺序识别归属）
        msg = {
            '1': [entity_entry, ng_entry],
            '3': make_binary_name(f"{self.name}.gia"),
        }

        return msg

    def _build_entity_entry(self, ng_loc_id: int = 0) -> Dict[str, Any]:
        """构建 entity entry（deep-copy 自编辑器导出的金币模板）

        关键规则：
        - entity 自身 loc_id (f1.f4) 保留模板中的固定值（金币=1077936129），绝不修改
        - entity.f2.f4 和 payload 中的 NG 引用必须替换为实际 NG loc_id
        - entity.f11.f1.f2 (prefab type_code) 保留模板值（10005018=金币）
        """
        template = _get_entity_template()
        if not template:
            # 降级：极简 entity
            entity_id = 1077936129  # 金币固定 loc_id
            return {
                '1': {'2': 1, '3': 1, '4': entity_id},
                '3': make_binary_name(f"{self.name}_entity"),
                '5': 1,
                '11': {'1': {'1': entity_id, '2': 10005018, '6': [], '7': [], '8': [], '10': 1}},
            }

        entry = copy.deepcopy(template)
        # old_ng_id = 模板中 entity.f2.f4，即与 NG entry 关联的那个 ID
        # 注意：entity 自身 f1.f4 是固定值（金币=1077936129），绝对不能替换
        old_ng_id = template.get('2', {}).get('4', 0)

        # 仅递归替换 entity 中指向旧 NG 的引用，不改 entity 自身 loc_id
        def _replace_ng_refs(obj: Any) -> Any:
            if isinstance(obj, dict):
                return {k: _replace_ng_refs(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [_replace_ng_refs(v) for v in obj]
            elif isinstance(obj, int):
                if obj == old_ng_id and old_ng_id != 0:
                    return ng_loc_id
            return obj

        entry = _replace_ng_refs(entry)
        entry['3'] = make_binary_name(f"{self.name}_entity")
        return entry

    def _build_graph_dict(self, graph_id: int = 0) -> Dict[str, Any]:
        """构建 graph 内部 dict"""
        nodes_list = []
        for handle in self._nodes:
            node_dict = self._build_node_dict(handle)
            nodes_list.append(node_dict)

        graph = {
            '1': {  # graph identity
                '1': 10000,
                '2': 20000,
                '3': 21001,
                '5': graph_id,  # 与 NG loc_id 一致
            },
            '2': make_binary_name(self.name),  # graph name
            '3': nodes_list,                    # nodes
            '101': 0.3,                        # zoom level
        }
        return graph

    def _build_node_dict(self, handle: NodeHandle) -> Dict[str, Any]:
        """构建单个 node dict"""
        pins_list = self._build_pins(handle)

        # 千星编辑器要求 type_id 为字典格式（非纯整数）
        # 格式: {'1': 10001, '2': 20000, '3': 22000, '5': 实际类型ID}
        type_id_dict = {
            '1': 10001,
            '2': 20000,
            '3': 22000,
            '5': handle.type_id,
        }

        # 坐标必须为 float：protobuf 编码为 wire type 5 (32-bit)
        # 若使用 int 会编码为 varint (wire type 0)，编辑器无法正确解码
        node = {
            '1': handle.index + 1,     # node ID 从 1 开始
            '2': type_id_dict,
            '3': type_id_dict,          # data_out type 描述符
            '5': float(handle.x),
            '6': float(handle.y),
        }
        # field[4]: 只在有引脚时设置（0 个引脚时不设置）
        if pins_list is not None:
            node['4'] = pins_list
        return node

    def _build_pins(self, handle: NodeHandle) -> Any:
        """构建节点的端口列表

        编辑器导出的 GIA 规则：
        - Flow 引脚始终导出（即使无连线/无值），数据引脚仅当有值或有连线时导出
        - sig['2'] 使用 catalog 定义的原始引脚索引 (pin_def.index)
        - sig['2']=0 的引脚省略 '2' 字段（编辑器约定）
        - 1 个 pin 时返回单个 dict（不是 list）
        - 0 个 pin 时不设置 field[4]

        重要：sig['2'] 必须使用 pin_def.index（catalog 原始索引），不能使用
        顺序计数器重编号。因为编辑器按 catalog 定义顺序匹配引脚——若某个
        引脚因无值/无连线被过滤，后续引脚索引必须保持不变，否则会错位。
        """
        pins: List[Dict[str, Any]] = []
        node_def = handle.node_def

        # 收集所有引脚，标记是否有内容
        # 顺序：flow 引脚在前，data 引脚在后（与编辑器导出一致）
        all_pins = []  # (pin_dict, pin_def, is_flow)
        for raw_idx, pin_def in enumerate(node_def.inputs):
            pin = self._build_pin_dict(pin_def, handle, raw_index=raw_idx)
            all_pins.append((pin, pin_def, pin_def.is_flow))
        for raw_idx, pin_def in enumerate(node_def.outputs):
            pin = self._build_pin_dict(pin_def, handle, raw_index=raw_idx)
            all_pins.append((pin, pin_def, pin_def.is_flow))

        # 排序：flow 引脚在前，data 引脚在后
        all_pins.sort(key=lambda x: (0 if x[2] else 1))

        # 保留引脚：flow 引脚始终保留；data 引脚仅当有内容时保留
        # sig['2'] 已在 _build_pin_dict 中设为 pin_def.index（原始索引）
        # 不再重编号——保留原始索引确保与编辑器 pin 列表一致
        kept: List[Dict[str, Any]] = []
        for pin, pin_def, _is_flow in all_pins:
            has_conn = '5' in pin
            has_vb = '3' in pin
            if pin_def.is_flow or has_conn or has_vb:
                kept.append(pin)

        if len(kept) == 0:
            return None
        return kept

    def _build_pin_dict(self, pin_def: PinDef, handle: NodeHandle, raw_index: int = 0) -> Dict[str, Any]:
        """构建单个 pin dict"""
        kind = _pin_kind(pin_def.direction, pin_def.is_flow)
        var_type = pin_def.var_type

        # Pin signature: flow pins 不包含 '2' (index) 字段
        # 数据引脚: sig['2'] = pin_def.index（catalog 原始索引）
        # 索引 0 省略 '2' 字段（编辑器约定）
        sig_shell: Dict[str, Any] = {'1': kind}
        sig_kernel: Dict[str, Any] = {'1': kind}
        if not pin_def.is_flow and pin_def.index != 0:
            sig_shell['2'] = pin_def.index
            sig_kernel['2'] = pin_def.index

        pin: Dict[str, Any] = {
            '1': sig_shell,
            '2': sig_kernel,
            '4': var_type,
        }

        # VarBase: 输入数据端口始终生成 VarBase（即使值为空），以声明类型和保持引脚索引。
        # 输出数据端口仅当被其他节点消费时才生成 VarBase（声明输出类型）。
        if not pin_def.is_flow:
            if pin_def.direction == "In":
                # 输入数据端口：始终生成 VarBase（空值用 empty binary_data）
                param_value = handle.get_param(pin_def.name)
                pin['3'] = _build_var_base(var_type, param_value)
            else:
                # 输出数据端口：仅当被其他节点消费时才生成 VarBase（声明输出类型）
                # 未被消费的输出引脚不存储（样本行为：事件节点的 5 个输出数据引脚仅存被连接的）
                is_consumed = any(
                    conn['src'] is handle and conn['src_port'] == pin_def.name
                    for conn in self._connections
                )
                if is_consumed:
                    pin['3'] = _build_var_base(var_type, None, for_output=True)

        # 连接信息 field[5]
        if pin_def.direction == "Out" and pin_def.is_flow:
            # flow 输出端口：记录到目标节点的连接
            conn_info = self._build_output_connection(handle, pin_def)
            if conn_info:
                pin['5'] = conn_info
        elif pin_def.direction == "In" and not pin_def.is_flow:
            # 数据输入端口：记录到来源节点的连接
            conn_info = self._build_input_connection(handle, pin_def)
            if conn_info:
                pin['5'] = conn_info

        return pin

    def _build_output_connection(
        self, src_handle: NodeHandle, pin_def: PinDef
    ) -> Optional[Dict[str, Any]]:
        """为输出端口构建连接信息（指向目标节点）

        编辑器格式：
        - flow 连接: shell/kernel kind=1 (IN_FLOW)
        - data 连接: shell/kernel kind=目标输入端口的 kind
        - '1': 目标节点 ID
        - '2'/'3': 目标端口的 kind（不是源端口的 kind）
        """
        for conn in self._connections:
            if conn['src'] is src_handle and conn['src_port'] == pin_def.name:
                dst = conn['dst']
                dst_port_name = conn['dst_port']
                # 查找目标端口，获取其 kind
                dst_pin = _find_pin_by_name(dst.node_def.inputs, dst_port_name)
                if dst_pin is None:
                    dst_pin = _find_pin_by_name(dst.node_def.outputs, dst_port_name)
                if dst_pin is None:
                    continue
                # 使用目标端口的 kind
                conn_kind = _pin_kind(dst_pin.direction, dst_pin.is_flow)
                return {
                    '1': dst.index + 1,          # 目标节点 ID
                    '2': {'1': conn_kind},       # shell
                    '3': {'1': conn_kind},       # kernel
                }
        return None

    def _build_input_connection(
        self, dst_handle: NodeHandle, pin_def: PinDef
    ) -> Optional[Dict[str, Any]]:
        """为输入数据端口构建反向连接信息（指向来源节点）

        格式（根据编辑器导出文件）：
        - '1': 来源节点 ID
        - '2': {'1': 4, '2': out_param_index}  ← OUT_PARAM + 源引脚在OUT_PARAM中的0-based序号
        - '3': {'1': 4, '2': out_param_index}
        - out_param_index=0 时省略 '2' 字段
        """
        for conn in self._connections:
            if conn['dst'] is dst_handle and conn['dst_port'] == pin_def.name:
                src = conn['src']
                src_pin_def = _find_pin_by_name(src.node_def.outputs, conn['src_port'])
                if src_pin_def is not None:
                    # 获取源引脚在 OUT_PARAM 中的 0-based 序号
                    out_params = [p for p in src.node_def.outputs if not p.is_flow]
                    out_param_index = None
                    for i, p in enumerate(out_params):
                        if p.name == src_pin_def.name:
                            out_param_index = i
                            break
                    
                    if out_param_index is not None and out_param_index > 0:
                        return {
                            '1': src.index + 1,
                            '2': {'1': 4, '2': out_param_index},
                            '3': {'1': 4, '2': out_param_index},
                        }
                # out_param_index == 0 或找不到引脚：省略 '2'
                return {
                    '1': src.index + 1,
                    '2': {'1': 4},
                    '3': {'1': 4},
                }
        return None

    def _build_ng_entry(self, graph_dict: Dict[str, Any], ng_loc_id: int = 0) -> Dict[str, Any]:
        """构建 NG entry dict"""
        return {
            '1': {
                '2': 5,        # resource_class: NodeGraph
                '4': ng_loc_id,  # 确定性 location ID
            },
            '3': make_binary_name(self.name),
            '5': 9,            # entry type: NodeGraph (=9)
            '13': {
                '1': {
                    '1': graph_dict,
                },
            },
        }

    # ── 导出 GIA ──────────────────────────────────────────

    def to_gia(self, output_path: Path) -> Path:
        """导出为 .gia 文件"""
        num = self.to_numeric()
        return save_gia_numeric(num, Path(output_path))

    # ── 查询 ──────────────────────────────────────────────

    def node_count(self) -> int:
        """返回节点数量"""
        return len(self._nodes)

    def get_node(self, index: int) -> NodeHandle:
        """按索引获取节点句柄"""
        if index < 0 or index >= len(self._nodes):
            raise IndexError(f"节点索引越界: {index} (共 {len(self._nodes)} 个节点)")
        return self._nodes[index]


# ═══════════════════════════════════════════════════════════════
# LevelBuilder
# ═══════════════════════════════════════════════════════════════

class LevelBuilder:
    """关卡构建器 - 管理多个节点图"""

    def __init__(self, name: str) -> None:
        self.name = name
        self._graphs: List[GraphBuilder] = []

    @property
    def graphs(self) -> List[GraphBuilder]:
        return list(self._graphs)

    def add_graph(
        self,
        name: str,
        catalog: Optional[NodeCatalog] = None,
        graph_type: str = "ENTITY_NODE_GRAPH",
    ) -> GraphBuilder:
        """添加一个节点图"""
        g = GraphBuilder(name=name, catalog=catalog, graph_type=graph_type)
        self._graphs.append(g)
        return g

    def to_numeric(self) -> Dict[str, Any]:
        """导出为 numeric dict"""
        entries: List[Dict[str, Any]] = []
        for g in self._graphs:
            num = g.to_numeric()
            # 提取 entries
            g_entries = num.get('1', [])
            if isinstance(g_entries, dict):
                entries.append(g_entries)
            elif isinstance(g_entries, list):
                entries.extend(g_entries)

        return {
            '1': entries,
            '3': make_binary_name(f"{self.name}.gia"),
        }

    def to_gia(self, output_path: Path) -> Path:
        """导出为 .gia 文件"""
        num = self.to_numeric()
        return save_gia_numeric(num, Path(output_path))
