# -*- coding: utf-8 -*-
"""对比工作版本和我们的GIA中 entity 的 ID 结构"""
import sys
sys.path.insert(0, 'h:\\myprojects\\genshin_qianxing_editor')
from tools.live_sync.gia_utils import load_gia_numeric
from pathlib import Path

# 工作版本
num = load_gia_numeric(Path("h:/myprojects/genshin_qianxing_editor/tools/live_sync/samples/export_examples/金币与节点图.gia"))
print("=== 工作版本 金币与节点图.gia ===")
for i, e in enumerate(num['1']):
    if not isinstance(e, dict):
        continue
    e5 = e.get('5')
    if e5 == 1:
        f1 = e['1']
        f2 = e.get('2', {})
        f11_1 = e['11']['1']
        print(f"entity[{i}]:")
        print(f"  f1.f4   (loc_id/template_root_id) = {f1['4']}")
        print(f"  f2.f4   (resource_id)             = {f2['4']}")
        print(f"  f11.f1.f1 (entity_guid/实体GUID)     = {f11_1['1']}")
        print(f"  f11.f1.f2 (prefab_type/元件类型码)     = {f11_1['2']}")
        print(f"  loc_id == entity_guid ? {f1['4'] == f11_1['1']}")
    elif e5 == 9:
        ng_f1 = e['1']
        print(f"ng[{i}]: f1.f4 (loc_id) = {ng_f1['4']}")

# 我们的版本
print()
print("=== 我们的  test_04_listen_send.gia ===")
num2 = load_gia_numeric(Path("h:/myprojects/genshin_qianxing_editor/tools/live_sync/samples/generated/test_04_listen_send.gia"))
for i, e in enumerate(num2['1']):
    if not isinstance(e, dict):
        continue
    e5 = e.get('5')
    if e5 == 1:
        f1 = e['1']
        f2 = e.get('2', {})
        f11_1 = e['11']['1']
        print(f"entity[{i}]:")
        print(f"  f1.f4   (loc_id/template_root_id) = {f1['4']}")
        print(f"  f2.f4   (resource_id)             = {f2['4']}")
        print(f"  f11.f1.f1 (entity_guid)           = {f11_1['1']}")
        print(f"  f11.f1.f2 (prefab_type)           = {f11_1['2']}")
        print(f"  loc_id == entity_guid ? {f1['4'] == f11_1['1']}")
    elif e5 == 9:
        ng_f1 = e['1']
        print(f"ng[{i}]: f1.f4 (loc_id) = {ng_f1['4']}")
