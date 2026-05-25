# -*- coding: utf-8 -*-
"""批量生成各类资产的独立GIA测试文件"""
import sys; sys.path.insert(0, r'h:\myprojects\genshin_qianxing_editor')
from pathlib import Path
from private_extensions.ugc_file_tools.gia.container import unwrap_gia_container, wrap_gia_container
from private_extensions.ugc_file_tools.gil_dump_codec.protobuf_like import *
from private_extensions.ugc_file_tools.gil_dump_codec.protobuf_like_bridge import decoded_field_map_to_numeric_message
import copy, time

SAMPLE_DIR = Path(r'h:\myprojects\genshin_qianxing_editor\tools\live_sync\samples')

def load_gia_entries(path):
    proto = unwrap_gia_container(path)
    fm, _ = decode_message_to_field_map(data_bytes=proto, start_offset=0, end_offset=len(proto), remaining_depth=64)
    num = decoded_field_map_to_numeric_message(fm, prefer_raw_hex_for_utf8=True)
    f1 = num.get('1', [])
    if not isinstance(f1, list): f1 = [f1] if isinstance(f1, dict) else []
    return f1, num

def make_tag(src_num, new_name):
    old_tag = src_num.get('3', '')
    tag_text = parse_binary_data_hex_text(old_tag).decode('utf-8') if isinstance(old_tag,str) and old_tag.startswith('<binary_data>') else str(old_tag)
    parts = tag_text.rsplit('-\\', 1)
    prefix = parts[0] if len(parts) > 1 else ''
    graph_id = prefix.rsplit('-', 1)[1] if prefix else '1073741827'
    uid = prefix.rsplit('-', 1)[0].rsplit('-', 1)[0] if '-' in prefix else '6000061'
    return format_binary_data_hex_text(f'{uid}-{int(time.time())}-{graph_id}-\\{new_name}.gia'.encode('utf-8'))

def write_gia(path, entries, src_num, name):
    tag = make_tag(src_num, name)
    new_msg = {'1': entries, '3': tag}
    proto_out = encode_message(new_msg)
    gil = wrap_gia_container(proto_out)
    path.write_bytes(gil)
    return path.stat().st_size

# 源文件
attia_gia = Path(r'c:\Users\77948\.trae-cn\attachments\44dedddb-d82d-4adf-8c8a-9a5fdae5ab88_06d4c733-bf5f-4234-9830-4e531d20fd9a_金币与节点图.gia')
export_entity = SAMPLE_DIR / 'export_examples' / '实体.gia'
export_battle = SAMPLE_DIR / 'export_examples' / '战斗.gia'
export_scene = SAMPLE_DIR / 'export_examples' / '场景编辑.gia'
export_adv = SAMPLE_DIR / 'export_examples' / '高级工具.gia'

entries_coin, num_coin = load_gia_entries(attia_gia)
entries_entity, num_entity = load_gia_entries(export_entity)
entries_battle, num_battle = load_gia_entries(export_battle)
entries_scene, num_scene = load_gia_entries(export_scene)
entries_adv, num_adv = load_gia_entries(export_adv)

results = []

# ── 独立组件 ──
# 钥匙 (type_code=20001270)
key_entry = [e for e in entries_entity if isinstance(e,dict) and '3' in e and isinstance(e['3'],str) and e['3'].startswith('<binary_data>') and parse_binary_data_hex_text(e['3']).decode('utf-8')=='钥匙']
if key_entry:
    p = SAMPLE_DIR / 'test_key.gia'
    sz = write_gia(p, [copy.deepcopy(key_entry[0])], num_entity, 'key')
    results.append(('钥匙', p, sz))

# ── 实体类型 ──
# 酒杯实体 (resource_class=3, OBJECT_ENTITY)
goblet = [e for e in entries_entity if isinstance(e,dict) and e.get('5') == 3]
if goblet:
    p = SAMPLE_DIR / 'test_goblet_entity.gia'
    sz = write_gia(p, [copy.deepcopy(goblet[0])], num_entity, 'goblet_entity')
    results.append(('酒杯(实体)', p, sz))

# ── 战斗类 ──
for e in entries_battle:
    rc = e.get('5', '?')
    name = '?'
    if isinstance(e.get('3',''), str) and e['3'].startswith('<binary_data>'):
        name = parse_binary_data_hex_text(e['3']).decode('utf-8')
    if rc == 18:  # EFFECT
        p = SAMPLE_DIR / 'test_effect_template.gia'
        sz = write_gia(p, [copy.deepcopy(e)], num_battle, 'effect_template')
        results.append((f'{name}(特效)', p, sz))
    elif rc == 17:
        p = SAMPLE_DIR / 'test_custom_class.gia'
        sz = write_gia(p, [copy.deepcopy(e)], num_battle, 'custom_class')
        results.append((f'{name}(自定义职业)', p, sz))

# ── 高级工具类 ──
for e in entries_adv:
    rc = e.get('5', '?')
    name = '?'
    if isinstance(e.get('3',''), str) and e['3'].startswith('<binary_data>'):
        name = parse_binary_data_hex_text(e['3']).decode('utf-8')
    tag = f'{name}'
    if rc == 13:
        p = SAMPLE_DIR / 'test_camera.gia'
        sz = write_gia(p, [copy.deepcopy(e)], num_adv, 'camera')
        results.append((f'{name}(镜头)', p, sz))
    elif rc == 20:
        p = SAMPLE_DIR / 'test_layout.gia'
        sz = write_gia(p, [copy.deepcopy(e)], num_adv, 'layout')
        results.append((f'{name}(布局)', p, sz))
    elif rc == 49:
        p = SAMPLE_DIR / 'test_env_config.gia'
        sz = write_gia(p, [copy.deepcopy(e)], num_adv, 'env_config')
        results.append((f'{name}(环境配置)', p, sz))

# ── 场景类 ──
for e in entries_scene:
    rc = e.get('5', '?')
    name = '?'
    if isinstance(e.get('3',''), str) and e['3'].startswith('<binary_data>'):
        name = parse_binary_data_hex_text(e['3']).decode('utf-8')
    if rc == 5:
        p = SAMPLE_DIR / 'test_terrain.gia'
        sz = write_gia(p, [copy.deepcopy(e)], num_scene, 'terrain')
        results.append((f'{name}(地形)', p, sz))

# ── 豪华组合包 ──
combo_entries = []
for e in entries_entity[:2]:
    combo_entries.append(copy.deepcopy(e))
for e in entries_battle:
    combo_entries.append(copy.deepcopy(e))
for e in entries_adv[3:5]:  # 环境配置+镜头
    combo_entries.append(copy.deepcopy(e))

p = SAMPLE_DIR / 'test_rich_combo.gia'
sz = write_gia(p, combo_entries, num_entity, 'rich_combo')
results.append(('豪华组合包', p, sz))

# 输出结果
print(f'{"名称":<25} {"文件":<55} {"大小":>8}')
print('-' * 90)
for name, path, size in results:
    print(f'{name:<25} {path.name:<55} {size/1024:>7.1f} KB')
print(f'\n共生成 {len(results)} 个测试文件')
print(f'请在千星沙箱逐一测试导入!')
