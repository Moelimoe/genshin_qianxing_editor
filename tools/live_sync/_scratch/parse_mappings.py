# -*- coding: utf-8 -*-
"""解析 node_type_semantic_map.json 和 index.json，提取完整映射"""
import json, sys
from pathlib import Path

# 1. 解析语义映射 (type_id → 中文名)
sem_path = Path("private_extensions/ugc_file_tools/graph_ir/node_type_semantic_map.json")
sem = json.loads(sem_path.read_text(encoding="utf-8"))
print(f"node_type_semantic_map: {len(sem)} entries")
print("=" * 70)

# 2. 解析 index.json 获取英文名+中文翻译
idx_path = Path("private_extensions/ugc_file_tools/node_data/index.json")
idx = json.loads(idx_path.read_text(encoding="utf-8"))
nodes_list = idx.get("NodesList", [])
print(f"index.json NodesList: {len(nodes_list)} entries")
print()

# Build ID -> translations lookup
id_trans = {}
for n in nodes_list:
    tid = n.get("ID")
    trans = n.get("Translations", {})
    name_en = n.get("Name", "")
    # 找中文翻译
    zh = trans.get("zh-Hans", trans.get("zh-CN", ""))
    id_trans[tid] = {"en": name_en, "zh": zh, "class": n.get("Class", ""), "range": n.get("Range", "")}

# 3. 找我们 catalog 中关心的节点
KEY_NODES = [
    (100001, "关卡开始时"),
    (100002, "玩家进入触发器"),
    (100003, "实体碰撞时"),
    (100004, "交互时"),
    (3, "多分支"),
    (200001, "销毁实体"),
    (200005, "播放特效"),
    (200006, "播放音效"),
    (300000, "发送信号"),
    (300001, "监听信号"),
    (400001, "比较整数"),
    (500001, "设置局部变量"),
    (500003, "设置全局变量"),
    (800001, "延迟"),
    (800004, "获取玩家实体"),
    (800005, "获取实体位置"),
    ("?", "获取自定义变量"),
    ("?", "创建元件"),
    ("?", "关卡开始时"),
    ("?", "玩家进入触发器"),
]

print("关键节点在 semantic_map 中的真实 type_id:")
for search in KEY_NODES:
    cat_id, name = search
    found = False
    for tid_str, info in sem.items():
        if info.get("graph_generater_node_name") == name:
            real_id = int(tid_str)
            conf = info.get("confidence", "?")
            notes = info.get("notes", "")[:80]
            print(f"  sem[{tid_str}] -> {name} (confidence={conf}) {'<- catalog was ' + str(cat_id) + ' ❌' if cat_id != real_id else '✅ match'}")
            found = True
    if not found:
        # 反向：用 catalog_id 查
        for tid_str, info in sem.items():
            if int(tid_str) == cat_id:
                sname = info.get("graph_generater_node_name", "?")
                print(f"  sem[{tid_str}] -> {sname} (NOT '{name}'!) catalog mismatch!")
                found = True
                break
    if not found:
        print(f"  '{name}' (catalog={cat_id}) — NOT FOUND in semantic map")

print()
print("=" * 70)
print("全部 semantic_map 条目:")
entries = [(int(k), v["graph_generater_node_name"], v.get("confidence","?"), v.get("scope","")) for k,v in sem.items()]
entries.sort()
for tid, name, conf, scope in entries:
    idx_info = id_trans.get(tid, {})
    en = idx_info.get("en", "")
    scope_tag = f" [{scope}]" if scope else ""
    print(f"  {tid:>6}  {name:<20} conf={conf:<8} en={en:<30}{scope_tag}")
