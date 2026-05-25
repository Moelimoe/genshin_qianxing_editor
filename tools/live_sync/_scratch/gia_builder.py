# -*- coding: utf-8 -*-
"""通用 GIA 生成器：从空壳模板创建可导入的资产文件"""
import sys, time, copy
sys.path.insert(0, r'h:\myprojects\genshin_qianxing_editor')
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

from private_extensions.ugc_file_tools.gia.container import wrap_gia_container
from private_extensions.ugc_file_tools.gil_dump_codec.protobuf_like import (
    encode_message, parse_binary_data_hex_text, format_binary_data_hex_text,
)
from tools.live_sync.gia_utils import load_gia_numeric


# 源 GIA 路径（作为空壳模板来源）
_SRC_GIA = Path(r'c:\Users\77948\.trae-cn\attachments\44dedddb-d82d-4adf-8c8a-9a5fdae5ab88_06d4c733-bf5f-4234-9830-4e531d20fd9a_金币与节点图.gia')


def _decode_binary(tag: str) -> str:
    """将 binary_data hex 转为 UTF-8 文本"""
    raw = parse_binary_data_hex_text(tag)
    return raw.decode('utf-8')


def _encode_binary(text: str) -> str:
    """将 UTF-8 文本编码为 binary_data hex"""
    return format_binary_data_hex_text(text.encode('utf-8'))


def create_empty_gia(
    output_path: Path,
    name: str = "test_minimal",
    src_gia_path: Optional[Path] = None,
    uid: int = 6000061,
    entry_name: Optional[str] = None,
) -> Path:
    """
    从空壳模板创建最小 .gia 文件

    Args:
        output_path: 输出文件路径
        name: 文件名（用于 export_tag）
        src_gia_path: 源 GIA 路径（默认使用金币与节点图.gia 的 entry[0]）
        uid: 用户 ID
        entry_name: 资源条目名称（默认使用 name）

    Returns:
        生成的 GIA 文件路径
    """
    source = (src_gia_path or _SRC_GIA).resolve()
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. 加载源 GIA
    src = load_gia_numeric(source)

    # 2. 提取空壳条目
    f1 = src.get('1', [])
    if not isinstance(f1, list) or len(f1) == 0:
        raise ValueError("源 GIA 缺少 field_1 条目")
    
    shell = [copy.deepcopy(e) for e in f1 if isinstance(e, dict) and '11' in e and '13' not in e]
    if not shell:
        raise ValueError("源 GIA 缺少不含 NodeGraph 的空壳条目")
    
    entry = copy.deepcopy(shell[0])

    # 3. 修改名称
    ename = entry_name or name
    if isinstance(entry.get('3'), str) and entry['3'].startswith('<binary_data>'):
        entry['3'] = _encode_binary(ename)
    else:
        entry['3'] = ename

    # 4. 构建新 GIA
    # 源 export_tag 格式: uid-ts-graph_id-\name.gia
    old_tag_text = _decode_binary(src['3'])
    # 使用 '-\\' 作为分隔符提取 graph_id
    parts = old_tag_text.rsplit('-\\', 1)
    prefix = parts[0] if len(parts) > 1 else ''
    graph_id = prefix.rsplit('-', 1)[1] if prefix else '1073741827'
    new_tag = f'{uid}-{int(time.time())}-{graph_id}-\\{name}.gia'

    new_msg = {
        '1': [entry],
        '3': _encode_binary(new_tag),
    }

    # 5. 编码
    proto_out = encode_message(new_msg)
    gil_bytes = wrap_gia_container(proto_out)
    output_path.write_bytes(gil_bytes)

    return output_path


def create_gia_with_node_graphs(
    output_path: Path,
    name: str,
    entries: List[Dict[str, Any]],
    src_gia_path: Optional[Path] = None,
    uid: int = 6000061,
) -> Path:
    """
    创建包含自定义条目的 .gia 文件

    Args:
        output_path: 输出文件路径
        name: 导出名称
        entries: 条目列表，每个条目是一个 numeric_message dict
                 可以包含 '13' (NodeGraph binary) 字段
        src_gia_path: 源 GIA 路径
        uid: 用户 ID

    Returns:
        生成的 GIA 文件路径
    """
    source = (src_gia_path or _SRC_GIA).resolve()
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    src = load_gia_numeric(source)

    # 构建 export_tag
    old_tag_text = _decode_binary(src['3'])
    parts = old_tag_text.rsplit('-\\', 1)
    prefix = parts[0] if len(parts) > 1 else ''
    graph_id = prefix.rsplit('-', 1)[1] if prefix else '1073741827'
    new_tag = f'{uid}-{int(time.time())}-{graph_id}-\\{name}.gia'

    new_msg = {
        '1': entries,
        '3': _encode_binary(new_tag),
    }

    proto_out = encode_message(new_msg)
    gil_bytes = wrap_gia_container(proto_out)
    output_path.write_bytes(gil_bytes)

    return output_path


def get_empty_shell_entry(src_gia_path: Optional[Path] = None) -> Dict[str, Any]:
    """获取一个空壳 entry 作为模板（已有 Location, related_ids, resource_class, payload）"""
    source = (src_gia_path or _SRC_GIA).resolve()
    src = load_gia_numeric(source)
    f1 = src.get('1', [])
    shells = [copy.deepcopy(e) for e in f1 if isinstance(e, dict) and '11' in e and '13' not in e]
    if not shells:
        raise ValueError("源 GIA 缺少不含 NodeGraph 的空壳条目")
    return shells[0]


def get_node_graph_entry(src_gia_path: Optional[Path] = None, index: int = 1) -> Dict[str, Any]:
    """获取一个包含 NodeGraph 的 entry 作为模板"""
    source = (src_gia_path or _SRC_GIA).resolve()
    src = load_gia_numeric(source)
    f1 = src.get('1', [])
    graphs = [copy.deepcopy(e) for e in f1 if isinstance(e, dict) and '13' in e]
    if not graphs:
        raise ValueError("源 GIA 缺少含 NodeGraph 的条目")
    if index >= len(graphs):
        raise IndexError(f"只有 {len(graphs)} 个 NodeGraph 条目，请求 index={index}")
    return graphs[index]


# ══════════════════════════════════════════════
# CLI：测试生成最小 GIA
# ══════════════════════════════════════════════
if __name__ == '__main__':
    OUTPUT = Path(r'h:\myprojects\genshin_qianxing_editor\tools\live_sync\samples\test_from_scratch.gia')

    # 方案A：纯空壳（无节点图）
    print('=== 方案A：纯空壳 GIA ===')
    r = create_empty_gia(OUTPUT, name='test_empty_shell', entry_name='空壳测试')
    print(f'生成: {r} ({r.stat().st_size / 1024:.1f} KB)')

    from private_extensions.ugc_file_tools.gil_dump_codec.protobuf_like import ProtobufLikeParseOptions, parse_message
    from private_extensions.ugc_file_tools.gia.container import read_gia_container_header  
    h = read_gia_container_header(r)
    pb = unwrap_gia_container(r)
    OPT = ProtobufLikeParseOptions(max_depth=64, bytes_preview_length=200, max_length_delimited_string_bytes=200000, max_packed_items=10000, max_message_bytes_for_probe=2000000)
    mj, _, ok, _ = parse_message(byte_data=pb, start_offset=0, end_offset=len(pb), depth=0, options=OPT)
    cl = {k:v for k,v in mj.items() if not k.startswith('_')}
    f1v = cl.get('1',[])
    if isinstance(f1v, list):
        print(f'条目: {len(f1v)}')
        for i, item in enumerate(f1v):
            inner = item.get('value',{}).get('message',{})
            ik = [k for k in inner.keys() if not k.startswith('_')]
            n = inner.get('3','?')
            if isinstance(n,dict) and 'value' in n: n = n['value'].get('text','?')
            print(f'  [{i}]: keys={ik}, name={n}')
    f3v = cl.get('3',[])
    if isinstance(f3v, list) and len(f3v)>0:
        print(f'标签: {f3v[0].get("value",{}).get("text","?")}')
    print('请在千星沙箱测试导入')
