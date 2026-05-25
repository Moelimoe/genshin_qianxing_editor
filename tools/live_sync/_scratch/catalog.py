# -*- coding: utf-8 -*-
"""编目所有示例中的组件/物件类型"""
import sys; sys.path.insert(0, r'h:\myprojects\genshin_qianxing_editor')
from pathlib import Path
from private_extensions.ugc_file_tools.gia.container import unwrap_gia_container
from private_extensions.ugc_file_tools.gil_dump_codec.protobuf_like import *
from private_extensions.ugc_file_tools.gil_dump_codec.protobuf_like_bridge import decoded_field_map_to_numeric_message
from private_extensions.ugc_file_tools.gil_dump_codec.dump_json_tree import load_gil_payload_as_dump_json_object

RESOURCE_CLASS = {1:"OBJECT(物件)", 2:"CREATION(造物)", 3:"OBJECT_ENTITY(物件实体)", 9:"ENTITY_NODE_GRAPH", 12:"COMPOSITE_NODE_DECL", 14:"SIGNAL_NODE_DECL", 29:"STRUCTURE", 49:"ENVIRONMENT_CONFIG"}

def analyze_gia(path, label):
    print(f'\n{"="*60}')
    print(f'{label}: {path.name}')
    print(f'{"="*60}')
    proto = unwrap_gia_container(path)
    fm, c = decode_message_to_field_map(data_bytes=proto, start_offset=0, end_offset=len(proto), remaining_depth=64)
    num = decoded_field_map_to_numeric_message(fm, prefer_raw_hex_for_utf8=True)
    f1 = num.get('1',[])
    if not isinstance(f1, list): f1 = [f1] if isinstance(f1,dict) else []
    print(f'GIA 条目数: {len(f1)}')
    f2 = num.get('2',[])
    deps = len(f2) if isinstance(f2,list) else 0
    if deps: print(f'依赖数: {deps}')
    for i, entry in enumerate(f1):
        keys = sorted(entry.keys(), key=lambda x: int(x) if str(x).isdigit() else 999)
        loc = entry.get('1', {})
        loc4 = loc.get('4', '?') if isinstance(loc,dict) else '?'
        rc = entry.get('5', '?')
        rc_label = RESOURCE_CLASS.get(rc, f'unknown({rc})') if isinstance(rc, int) else str(rc)
        name = entry.get('3','?')
        if isinstance(name, str) and name.startswith('<binary_data>'):
            name = parse_binary_data_hex_text(name).decode('utf-8')
        elif isinstance(name, dict):
            name = '(nested)'
        has_ng = 'Yes' if '13' in entry else 'No'
        has_payload = 'Yes' if '11' in entry else 'No'
        # 检查 payload 中的 template_type_code
        tt = '?'
        f11 = entry.get('11', {})
        if isinstance(f11, dict) and '1' in f11:
            tt = f11['1'].get('2', '?')
        print(f'  [{i}] name="{name}" class={rc_label} loc_id={loc4} NG={has_ng} payload={has_payload} type_code={tt}')

def analyze_gil(path, label):
    print(f'\n{"="*60}')
    print(f'{label}: {path.name}')
    print(f'{"="*60}')
    data = load_gil_payload_as_dump_json_object(path)
    pr = data.get('4', {})
    # 实体摆放段
    f5 = pr.get('5', {})
    if isinstance(f5, dict):
        f5_1 = f5.get('1', [])
        if isinstance(f5_1, list):
            print(f'实体摆放 (field_5.1): {len(f5_1)} 个实体')
            for i, e in enumerate(f5_1[:5]):
                if isinstance(e, dict):
                    meta5 = e.get('5', [])
                    name = '?'
                    for m in meta5 if isinstance(meta5, list) else []:
                        if isinstance(m, dict) and m.get('1') == 1:
                            n11 = m.get('11', {})
                            if isinstance(n11, dict):
                                name = n11.get('1', '?')
                    tid = e.get('8', '?')
                    print(f'    [{i}] name="{name}" type_code={tid}')
            if len(f5_1) > 5: print(f'    ... 共 {len(f5_1)} 个实体')
    # 元件库模板
    f4 = pr.get('4', {})
    if isinstance(f4, dict):
        f4_1 = f4.get('1', [])
        if isinstance(f4_1, list):
            print(f'元件库模板 (field_4.1): {len(f4_1)} 个模板')
            for i, t in enumerate(f4_1[:5]):
                if isinstance(t, dict):
                    meta4 = t.get('5', [])
                    name = '?'
                    for m in meta4 if isinstance(meta4, list) else []:
                        if isinstance(m, dict) and m.get('1') == 1:
                            n11 = m.get('11', {})
                            if isinstance(n11, dict):
                                name = n11.get('1', '?')
                    tid = t.get('8', '?')
                    tid2 = t.get('2', '?')
                    print(f'    [{i}] name="{name}" type_code={tid} tid2={tid2}')
            if len(f4_1) > 5: print(f'    ... 共 {len(f4_1)} 个模板')

# 分析所有文件
gia1 = Path(r'c:\Users\77948\.trae-cn\attachments\44dedddb-d82d-4adf-8c8a-9a5fdae5ab88_06d4c733-bf5f-4234-9830-4e531d20fd9a_金币与节点图.gia')
gia2 = Path(r'c:\Users\77948\.trae-cn\attachments\6cd02385-5af1-44c5-a5f3-c04e911e1fdf_adacc945-9c6f-4ff4-8268-b01c4eb2e5cc_普通攻击.gia')
gil1 = Path(r'c:\Users\77948\.trae-cn\attachments\b126d67a-f205-4aa8-96fb-9afe32596e0d_24215554-72aa-4c26-8ab5-ee9d848eb6ad_场景地形.gil')

analyze_gia(gia1, 'GIA')
analyze_gia(gia2, 'GIA')
analyze_gil(gil1, 'GIL')

print(f'\n{"="*60}')
print('编目完成')
print(f'{"="*60}')
