# -*- coding: utf-8 -*-
"""GIA 文件编解码共享工具

消除项目中 4 处重复的 unwrap→decode→numeric 管道代码。
统一 Pin Kind 常量和 export_tag 生成逻辑。
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from private_extensions.ugc_file_tools.gia.container import unwrap_gia_container, wrap_gia_container
from private_extensions.ugc_file_tools.gil_dump_codec.protobuf_like import (
    decode_message_to_field_map, encode_message,
    parse_binary_data_hex_text, format_binary_data_hex_text,
)
from private_extensions.ugc_file_tools.gil_dump_codec.protobuf_like_bridge import decoded_field_map_to_numeric_message

# ═══════════════════════════════════════════
#  Pin Kind 常量（统一来源，避免硬编码）
# ═══════════════════════════════════════════
PIN_KIND_IN_FLOW = 1
PIN_KIND_OUT_FLOW = 2
PIN_KIND_IN_PARAM = 3
PIN_KIND_OUT_PARAM = 4

FLOW_KINDS = {PIN_KIND_IN_FLOW, PIN_KIND_OUT_FLOW}
DATA_KINDS = {PIN_KIND_IN_PARAM, PIN_KIND_OUT_PARAM}

# Human-readable names for pin kinds
PIN_KIND_NAMES = {
    PIN_KIND_IN_FLOW: "入",
    PIN_KIND_OUT_FLOW: "出",
    PIN_KIND_IN_PARAM: "入参",
    PIN_KIND_OUT_PARAM: "出参",
}


def load_gia_numeric(gia_path: Path) -> Dict[str, Any]:
    """加载 .gia 文件 → numeric_message dict（单次调用完成三条管道）"""
    proto = unwrap_gia_container(gia_path)
    fm, _ = decode_message_to_field_map(
        data_bytes=proto, start_offset=0, end_offset=len(proto), remaining_depth=64
    )
    return decoded_field_map_to_numeric_message(fm, prefer_raw_hex_for_utf8=True)


def save_gia_numeric(num: Dict[str, Any], output_path: Path) -> Path:
    """将 numeric_message dict 写入 .gia 文件"""
    proto = encode_message(num)
    gil = wrap_gia_container(proto)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(gil)
    return output_path


def get_entries(num: Dict[str, Any]) -> List[Dict[str, Any]]:
    """从 numeric_message 提取 entries 列表（兼容单 dict 条目）"""
    f1 = num.get('1', [])
    if isinstance(f1, dict):
        return [f1]
    if isinstance(f1, list):
        return [e for e in f1 if isinstance(e, dict)]
    return []


def get_entry_name(entry: Dict[str, Any]) -> str:
    """提取 entry 的可读名称"""
    name_field = entry.get('3', '')
    if isinstance(name_field, str) and name_field.startswith('<binary_data>'):
        try:
            return parse_binary_data_hex_text(name_field).decode('utf-8')
        except Exception:
            return '[binary]'
    return str(name_field)


def make_binary_name(text: str) -> str:
    """将 UTF-8 文本编码为 binary_data hex 格式"""
    return format_binary_data_hex_text(text.encode('utf-8'))


def get_ng_graph(graph_entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """从 NG entry 提取内部图 dict（entry['13']['1']['1']）"""
    try:
        return graph_entry['13']['1']['1']
    except (KeyError, TypeError):
        return None


def get_ng_nodes(graph_entry: Dict[str, Any]) -> List[Dict[str, Any]]:
    """从 NG entry 提取节点列表"""
    graph = get_ng_graph(graph_entry)
    if graph is None:
        return []
    nodes = graph.get('3', [])
    if isinstance(nodes, dict):
        # 单元素被 protobuf 解码为字典
        return [nodes]
    if isinstance(nodes, list):
        return nodes
    return []


def get_ng_entries(num: Dict[str, Any]) -> List[Dict[str, Any]]:
    """从 GIA 提取所有含 NodeGraph 的 entry"""
    entries = get_entries(num)
    return [e for e in entries if '13' in e]


def decode_binary_name(hex_text: str) -> str:
    """逆操作 make_binary_name：binary_data hex → UTF-8 文本"""
    try:
        return parse_binary_data_hex_text(hex_text).decode('utf-8')
    except Exception:
        return hex_text


def make_export_tag(uid: int, graph_id: int, name: str) -> str:
    """生成 GIA export_tag

    格式: uid-{timestamp}-graph_id-\{name}.gia
    """
    ts = int(time.time() * 1000)
    return format_binary_data_hex_text(
        f"{uid}-{ts}-{graph_id}-\\{name}.gia".encode('utf-8')
    )


def parse_export_tag(tag: str) -> Optional[Tuple[int, int, str]]:
    """解析 export_tag → (uid, graph_id, name)

    返回 None 表示解析失败。
    """
    try:
        decoded = decode_binary_name(tag)
        # 格式: uid-timestamp-graph_id-name.gia
        parts = decoded.rsplit('.', 1)[0].split('-', 3)
        if len(parts) >= 4:
            uid = int(parts[0])
            graph_id = int(parts[2])
            name = parts[3].lstrip('\\')
            return uid, graph_id, name
    except (ValueError, IndexError):
        pass
    return None
