# -*- coding: utf-8 -*-
"""GIA 加载器模块

支持读取现有 .gia 文件 → 转换为 GraphBuilder → 修改 → 重新导出的工作流。

核心类：
- LoadedLevel: 加载的关卡数据
- GIALoader: GIA 文件加载器

用法:
    loader = GIALoader(catalog=NodeCatalog.default())
    loaded = loader.load(Path("input.gia"))
    graph = loaded.get_graph(0)
    
    # 修改图...
    
    # 重新导出
    graph.to_gia(Path("output.gia"))
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from tools.live_sync.gia_utils import (
    load_gia_numeric, get_entries, get_ng_graph, get_ng_nodes,
    get_entry_name, make_binary_name, decode_binary_name,
    PIN_KIND_IN_FLOW, PIN_KIND_OUT_FLOW, PIN_KIND_IN_PARAM, PIN_KIND_OUT_PARAM,
    FLOW_KINDS, DATA_KINDS,
)
from private_extensions.ugc_file_tools.gil_dump_codec.protobuf_like import (
    parse_binary_data_hex_text,  # 原始使用（不 decode）
)
from tools.live_sync.level_builder import GraphBuilder, NodeHandle
from tools.live_sync.node_catalog import NodeCatalog, NodeDef, VarType


# ═══════════════════════════════════════════════════════════════
# LoadedLevel 数据类
# ═══════════════════════════════════════════════════════════════

@dataclass
class LoadedLevel:
    """加载的关卡数据
    
    Attributes:
        gia_path: GIA 文件路径
        entries: 所有 entries 列表
        entity_entries: Entity entries 列表（有 '11' 或 '12' 字段）
        ng_entries: NodeGraph entries 列表（有 '13' 字段）
        export_tag: 导出标签
    """
    gia_path: Path
    entries: List[Dict[str, Any]]
    entity_entries: List[Dict[str, Any]]
    ng_entries: List[Dict[str, Any]]
    export_tag: str
    _catalog: Optional[NodeCatalog] = None  # 记住加载时的catalog
    
    def get_graph(self, index: int = 0, catalog: NodeCatalog = None) -> GraphBuilder:
        """获取指定索引的节点图为 GraphBuilder
        
        Args:
            index: NG entry 索引（从0开始）
            catalog: 可选的节点目录，用于识别节点类型
        
        Returns:
            GraphBuilder 实例
        
        Raises:
            IndexError: 索引越界
            ValueError: 无效的 NG entry
        """
        if index < 0 or index >= len(self.ng_entries):
            raise IndexError(f"NG entry 索引越界: {index} (共 {len(self.ng_entries)} 个)")
        
        ng_entry = self.ng_entries[index]
        cat = catalog if catalog is not None else self._catalog
        return self._convert_ng_to_graph(ng_entry, cat)
    
    def get_graph_count(self) -> int:
        """获取节点图数量"""
        return len(self.ng_entries)
    
    def get_entity_asset_key(self) -> Optional[str]:
        """尝试推断 entity 对应的 asset key
        
        根据 entity entry 的特征（如 loc_id、payload 结构等）
        尝试推断对应的 asset key。
        
        Returns:
            asset key 字符串，如果无法推断则返回 None
        """
        if not self.entity_entries:
            return None
        
        entity = self.entity_entries[0]
        
        # 尝试从 Location 获取 loc_id
        location = entity.get('1', {})
        if isinstance(location, dict):
            loc_id = location.get('4')
            if loc_id is not None:
                # 根据 loc_id 推断 asset key
                loc_id_to_asset = {
                    1073741827: "goblet",
                    1073741828: "coin",
                    1073741829: "key",
                }
                if loc_id in loc_id_to_asset:
                    return loc_id_to_asset[loc_id]
        
        # 根据 payload 结构推断
        if '11' in entity:
            # 有 payload，可能是 coin 或 key
            return "coin"
        elif '12' in entity:
            # 有 related_ids，可能是 goblet
            return "goblet"
        
        return None
    
    def _convert_ng_to_graph(
        self, ng_entry: Dict[str, Any], catalog: Optional[NodeCatalog]
    ) -> GraphBuilder:
        """将 NG entry 转换为 GraphBuilder
        
        Args:
            ng_entry: NG entry dict
            catalog: 可选的节点目录
        
        Returns:
            GraphBuilder 实例
        """
        # 获取图名称
        name_field = ng_entry.get('3', '')
        graph_name = self._decode_name(name_field) or "LoadedGraph"
        
        # 创建 GraphBuilder
        graph = GraphBuilder(name=graph_name, catalog=catalog)
        
        # 提取节点列表
        nodes = get_ng_nodes(ng_entry)
        if not nodes:
            return graph
        
        # 确保 nodes 是列表
        if isinstance(nodes, dict):
            nodes = [nodes]
        
        # 第一遍：创建所有节点
        node_handles: List[Optional[NodeHandle]] = [None] * len(nodes)
        for node_data in nodes:
            if not isinstance(node_data, dict):
                continue
            
            node_index = node_data.get('1')
            type_id = node_data.get('2')
            x = node_data.get('5', 0)
            y = node_data.get('6', 0)
            
            if node_index is None or type_id is None:
                continue
            
            # 千星编辑器使用字典格式 type_id: {'1':10001,'2':20000,'3':22000,'5':实际ID}
            # 提取实际的整数 type_id 用于 catalog 查找
            actual_type_id: Optional[int] = None
            if isinstance(type_id, dict):
                actual_type_id = type_id.get('5')  # field 5 包含具体节点类型ID
            elif isinstance(type_id, int):
                actual_type_id = type_id
            
            if actual_type_id is None:
                continue
            
            # 尝试用 catalog 查找节点定义
            node_def: Optional[NodeDef] = None
            if catalog is not None:
                node_def = catalog.get_by_id(actual_type_id)
            
            if node_def is None:
                # 创建最小 NodeDef
                node_def = NodeDef(
                    type_id=actual_type_id,
                    name=f"Node_{actual_type_id}",
                    category="unknown",
                    description=f"Unknown node type_id={type_id}",
                )
            
            # 手动创建 NodeHandle 并添加到图中
            index = len(graph._nodes)
            handle = NodeHandle(graph, node_def, index)
            graph._nodes.append(handle)
            
            handle.x = x
            handle.y = y
            
            # 存储节点句柄，按原始索引
            if isinstance(node_index, int) and node_index >= 0:
                # 确保列表足够长
                while len(node_handles) <= node_index:
                    node_handles.append(None)
                node_handles[node_index] = handle
            
            # 提取参数
            self._extract_params(node_data, handle, catalog)
        
        # 第二遍：重建连线
        for node_data in nodes:
            if not isinstance(node_data, dict):
                continue
            
            node_index = node_data.get('1')
            if node_index is None or node_index < 0 or node_index >= len(node_handles):
                continue
            
            src_handle = node_handles[node_index]
            if src_handle is None:
                continue
            
            self._reconstruct_connections(node_data, src_handle, node_handles, graph, catalog)
        
        return graph
    
    def _extract_params(
        self,
        node_data: Dict[str, Any],
        handle: NodeHandle,
        catalog: Optional[NodeCatalog],
    ) -> None:
        """从节点数据中提取参数"""
        pins = node_data.get('4', [])
        if isinstance(pins, dict):
            pins = [pins]
        if not isinstance(pins, list):
            return
        
        # 统计每种kind的IN_PARAM端口出现次数，用于推断缺失的index
        in_param_count = 0
        
        for pin_data in pins:
            if not isinstance(pin_data, dict):
                continue
            
            # 获取 pin kind
            sig = pin_data.get('1', {})
            if not isinstance(sig, dict):
                continue
            
            pin_kind = sig.get('1')
            pin_index = sig.get('2', 0)
            
            # 只处理输入参数端口
            if pin_kind != PIN_KIND_IN_PARAM:
                continue
            
            # 如果pin_index缺失，按顺序推断（index=0 省略字段，sig.get('2',0) 已处理）
            in_param_count += 1
            
            # 获取 VarBase
            varbase = pin_data.get('3')
            if varbase is None:
                continue
            
            # 解码值
            value = self._varbase_to_value_static(varbase)
            if value is None:
                continue
            
            # 查找端口名称
            port_name = self._get_port_name(handle.node_def, pin_index, pin_kind, catalog)
            if port_name and not port_name.startswith('param_'):
                # 只设置已知名称的参数，跳过默认命名的参数
                try:
                    handle.set_param(port_name, value)
                except ValueError:
                    # 端口不存在，跳过
                    pass
    
    def _reconstruct_connections(
        self,
        node_data: Dict[str, Any],
        src_handle: NodeHandle,
        node_handles: List[Optional[NodeHandle]],
        graph: GraphBuilder,
        catalog: Optional[NodeCatalog],
    ) -> None:
        """重建节点的连线"""
        pins = node_data.get('4', [])
        if isinstance(pins, dict):
            pins = [pins]
        if not isinstance(pins, list):
            return
        
        for pin_data in pins:
            if not isinstance(pin_data, dict):
                continue
            
            # 获取 pin kind
            sig = pin_data.get('1', {})
            if not isinstance(sig, dict):
                continue
            
            pin_kind = sig.get('1')
            pin_index = sig.get('2')
            
            # 只处理输出端口
            if pin_kind not in (PIN_KIND_OUT_FLOW, PIN_KIND_OUT_PARAM):
                continue
            
            # 获取连接列表（处理单元素被编码为字典的情况）
            connections = pin_data.get('5', [])
            if isinstance(connections, dict):
                # 单元素被编码为字典，转换为列表
                connections = [connections]
            if not isinstance(connections, list):
                continue
            
            # 获取源端口名称
            src_port = self._get_port_name(src_handle.node_def, pin_index, pin_kind, catalog)
            if not src_port:
                continue
            
            # 遍历连接
            for conn in connections:
                if not isinstance(conn, dict):
                    continue
                
                target_node_idx = conn.get('1')
                if target_node_idx is None or target_node_idx < 0 or target_node_idx >= len(node_handles):
                    continue
                
                dst_handle = node_handles[target_node_idx]
                if dst_handle is None:
                    continue
                
                # 获取目标 pin kind
                dst_sig = conn.get('2', {})
                if not isinstance(dst_sig, dict):
                    continue
                
                dst_kind = dst_sig.get('1')
                dst_index = dst_sig.get('2')
                
                # 获取目标端口名称
                dst_port = self._get_port_name(dst_handle.node_def, dst_index, dst_kind, catalog)
                if not dst_port:
                    continue
                
                # 创建连接
                try:
                    if pin_kind == PIN_KIND_OUT_FLOW:
                        graph.connect_flow(src_handle, src_port, dst_handle, dst_port)
                    else:
                        graph.connect_data(src_handle, src_port, dst_handle, dst_port)
                except ValueError:
                    # 连接失败（可能是端口类型不匹配），忽略
                    pass
    
    def _get_port_name(
        self,
        node_def: NodeDef,
        pin_index: Optional[int],
        pin_kind: Optional[int],
        catalog: Optional[NodeCatalog],
    ) -> Optional[str]:
        """根据 pin index 和 kind 获取端口名称"""
        # 根据 kind 确定是输入还是输出端口
        if pin_kind in (PIN_KIND_IN_FLOW, PIN_KIND_IN_PARAM):
            pins = node_def.inputs
        elif pin_kind in (PIN_KIND_OUT_FLOW, PIN_KIND_OUT_PARAM):
            pins = node_def.outputs
        else:
            return None
        
        if pin_index is not None:
            # 查找对应 index+kind 的端口
            # index=0 的 flow 和 data 引脚共享 index，需按 kind 区分
            is_flow_pin_expected = pin_kind in (PIN_KIND_IN_FLOW, PIN_KIND_OUT_FLOW)
            for pin in pins:
                if pin.index == pin_index and pin.is_flow == is_flow_pin_expected:
                    return pin.name
        else:
            # pin_index 缺失，按顺序推断（取同kind中的第N个）
            # 需要外部传入顺序信息，这里无法推断，返回None
            pass
        
        # 如果没找到，使用默认名称
        if pin_kind == PIN_KIND_IN_FLOW:
            return "入"
        elif pin_kind == PIN_KIND_OUT_FLOW:
            return "出"
        else:
            return f"param_{pin_index}"
    
    @staticmethod
    def _decode_name(name_field: Any) -> Optional[str]:
        """解码 entry 名称"""
        if isinstance(name_field, str):
            if name_field.startswith('<binary_data>'):
                try:
                    return decode_binary_name(name_field)
                except Exception:
                    return None
            return name_field
        return None
    
    @staticmethod
    def _decode_length_delimited_string(data: bytes) -> str:
        """解码 protobuf length-delimited 字符串
        
        格式: [tag] [length] [data]
        tag: (field_number << 3) | wire_type (wire_type=2 for length-delimited)
        """
        if len(data) < 2:
            return data.decode('utf-8', errors='replace')
        
        # 检查是否是 length-delimited 格式
        # tag = (1 << 3) | 2 = 0x0A (field 1, wire type 2)
        if data[0] == 0x0A and len(data) >= 2:
            length = data[1]
            if len(data) >= 2 + length:
                return data[2:2+length].decode('utf-8')
        
        # 如果不是 length-delimited 格式，直接解码
        return data.decode('utf-8', errors='replace')
    
    @staticmethod
    def _varbase_to_value_static(varbase: Dict[str, Any]) -> Any:
        """将 VarBase 转换为 Python 值（静态方法版本）"""
        if not isinstance(varbase, dict):
            return None
        
        var_type = varbase.get('1')
        value_field = varbase.get('2', {})
        
        # 处理字符串类型的特殊情况：value_field 可能是 binary_data 字符串
        if var_type == VarType.Str:
            if isinstance(value_field, str):
                # value_field 本身就是 binary_data 字符串
                if value_field.startswith('<binary_data>'):
                    try:
                        data = parse_binary_data_hex_text(value_field)
                        return LoadedLevel._decode_length_delimited_string(data)
                    except Exception:
                        return value_field
                return value_field
            elif isinstance(value_field, dict):
                binary_data = value_field.get('1', '')
                if isinstance(binary_data, str) and binary_data.startswith('<binary_data>'):
                    try:
                        data = parse_binary_data_hex_text(binary_data)
                        return LoadedLevel._decode_length_delimited_string(data)
                    except Exception:
                        return binary_data
                return binary_data
            return None
        
        # 其他类型：value_field 应该是 dict
        if not isinstance(value_field, dict):
            return None
        
        if var_type == VarType.Int:
            return value_field.get('1')
        elif var_type == VarType.Bol:
            return bool(value_field.get('1'))
        elif var_type == VarType.Flt:
            bits = value_field.get('1', 0)
            if isinstance(bits, int):
                try:
                    return struct.unpack('>f', struct.pack('>I', bits))[0]
                except Exception:
                    return float(bits)
            return float(bits)
        elif var_type == VarType.Vec:
            # Vec 是三个 float
            x_bits = value_field.get('1', 0)
            y_bits = value_field.get('2', 0)
            z_bits = value_field.get('3', 0)
            try:
                x = struct.unpack('>f', struct.pack('>I', x_bits))[0] if isinstance(x_bits, int) else 0.0
                y = struct.unpack('>f', struct.pack('>I', y_bits))[0] if isinstance(y_bits, int) else 0.0
                z = struct.unpack('>f', struct.pack('>I', z_bits))[0] if isinstance(z_bits, int) else 0.0
                return (x, y, z)
            except Exception:
                return (0.0, 0.0, 0.0)
        elif var_type == VarType.Ety:
            return value_field.get('1')
        elif var_type == VarType.Prefab:
            return value_field.get('1')
        else:
            # 其他类型，尝试返回原始值
            return value_field.get('1')


# ═══════════════════════════════════════════════════════════════
# GIALoader 主类
# ═══════════════════════════════════════════════════════════════

class GIALoader:
    """GIA 文件加载器
    
    支持读取现有 .gia 文件并转换为 GraphBuilder。
    
    用法:
        loader = GIALoader(catalog=NodeCatalog.default())
        loaded = loader.load(Path("input.gia"))
        graph = loaded.get_graph(0)
    """
    
    def __init__(self, catalog: NodeCatalog = None):
        """初始化 GIALoader
        
        Args:
            catalog: 可选的节点目录，用于识别节点类型
        """
        self.catalog = catalog
    
    def load(self, gia_path: Path) -> LoadedLevel:
        """加载 GIA 文件
        
        Args:
            gia_path: GIA 文件路径
        
        Returns:
            LoadedLevel 实例
        
        Raises:
            FileNotFoundError: 文件不存在
            ValueError: GIA 格式错误
        """
        gia_path = Path(gia_path)
        
        # 检查文件是否存在
        if not gia_path.exists():
            raise FileNotFoundError(f"GIA 文件不存在: {gia_path}")
        
        try:
            # 加载 numeric dict
            num = load_gia_numeric(gia_path)
        except Exception as e:
            raise ValueError(f"无法加载 GIA 文件 '{gia_path}': {e}") from e
        
        # 提取 entries
        entries = get_entries(num)
        
        # 分类 entries
        entity_entries = []
        ng_entries = []
        
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            
            # 有 '13' 字段的是 NG entry
            if '13' in entry:
                ng_entries.append(entry)
            # 有 '11' (payload) 或 '12' (related_ids) 的是 entity entry
            elif '11' in entry or '12' in entry:
                entity_entries.append(entry)
            else:
                # 其他情况，根据是否有 NodeGraph 判断
                entity_entries.append(entry)
        
        # 提取 export_tag
        export_tag = num.get('3', '')
        if not isinstance(export_tag, str):
            export_tag = str(export_tag)
        
        return LoadedLevel(
            gia_path=gia_path,
            entries=entries,
            entity_entries=entity_entries,
            ng_entries=ng_entries,
            export_tag=export_tag,
            _catalog=self.catalog,
        )
    
    def load_graph_only(self, gia_path: Path, index: int = 0) -> GraphBuilder:
        """只加载指定索引的节点图
        
        便捷方法，直接返回 GraphBuilder，不返回 LoadedLevel。
        
        Args:
            gia_path: GIA 文件路径
            index: NG entry 索引（从0开始，默认0）
        
        Returns:
            GraphBuilder 实例
        """
        loaded = self.load(gia_path)
        return loaded.get_graph(index, catalog=self.catalog)
    
    def _parse_node(self, node_data: Dict, node_index: int) -> Tuple[int, int, float, float]:
        """解析节点数据返回 (index, type_id, x, y)
        
        Args:
            node_data: 节点数据 dict
            node_index: 节点索引（用于错误报告）
        
        Returns:
            (index, type_id, x, y) 元组
        """
        idx = node_data.get('1', node_index)
        type_id = node_data.get('2', 0)
        x = node_data.get('5', 0)
        y = node_data.get('6', 0)
        return idx, type_id, x, y
    
    def _parse_pin(self, pin_data: Dict) -> Tuple[int, int, Optional[Any], List[Dict]]:
        """解析端口数据返回 (kind, index, value, connections)
        
        Args:
            pin_data: 端口数据 dict
        
        Returns:
            (kind, index, value, connections) 元组
        """
        sig = pin_data.get('1', {})
        if not isinstance(sig, dict):
            return 0, 0, None, []
        
        kind = sig.get('1', 0)
        index = sig.get('2', 0)
        
        # 获取 VarBase 值
        varbase = pin_data.get('3')
        value = self._varbase_to_value(varbase) if varbase else None
        
        # 获取连接
        connections = pin_data.get('5', [])
        if not isinstance(connections, list):
            connections = []
        
        return kind, index, value, connections
    
    def _varbase_to_value(self, varbase: Dict) -> Any:
        """将 VarBase 转换为 Python 值
        
        Args:
            varbase: VarBase dict
        
        Returns:
            Python 值
        """
        return LoadedLevel._varbase_to_value_static(varbase)


# ═══════════════════════════════════════════════════════════════
# 便捷函数
# ═══════════════════════════════════════════════════════════════

def load_gia(gia_path: Path, catalog: NodeCatalog = None) -> LoadedLevel:
    """便捷加载函数
    
    Args:
        gia_path: GIA 文件路径
        catalog: 可选的节点目录
    
    Returns:
        LoadedLevel 实例
    
    Example:
        loaded = load_gia(Path("input.gia"), catalog=NodeCatalog.default())
        graph = loaded.get_graph(0)
    """
    loader = GIALoader(catalog=catalog)
    return loader.load(gia_path)


def load_graph(gia_path: Path, index: int = 0, catalog: NodeCatalog = None) -> GraphBuilder:
    """便捷加载节点图函数
    
    Args:
        gia_path: GIA 文件路径
        index: NG entry 索引（从0开始，默认0）
        catalog: 可选的节点目录
    
    Returns:
        GraphBuilder 实例
    
    Example:
        graph = load_graph(Path("input.gia"), catalog=NodeCatalog.default())
    """
    loader = GIALoader(catalog=catalog)
    return loader.load_graph_only(gia_path, index=index)
