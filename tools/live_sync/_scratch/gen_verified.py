# -*- coding: utf-8 -*-
"""从 semantic_map.json 重新生成 verified_type_ids.py"""
import json
from pathlib import Path

sem = json.loads((Path("private_extensions/ugc_file_tools/graph_ir/node_type_semantic_map.json").read_text("utf-8")))

verified = []   # (tid, name, conf)
inferred = []
by_name = {}    # name -> tid
by_id = {}      # tid -> name

for k, v in sem.items():
    tid = int(k)
    name = v.get("graph_generater_node_name", "")
    conf = v.get("confidence", "manual")
    if not name:
        continue
    entry = (tid, name, conf)
    if conf in ("high", "medium"):
        verified.append(entry)
    else:
        inferred.append(entry)
    by_name[name] = tid
    by_id[tid] = name

verified.sort()
inferred.sort()

lines = []
L = lines.append
L("# -*- coding: utf-8 -*-")
L('"""已验证的 node type_id 映射表')
L("")
L(f"从 node_type_semantic_map.json 生成。")
L(f"Verified (high+medium): {len(verified)} 条")
L(f"Inferred (manual): {len(inferred)} 条")
L('"""')
L("")
L("# ── lookup tables ──────────────────────────────")
L("_BY_NAME: dict[str, int] = {")
for name, tid in sorted(by_name.items()):
    L(f"    {name!r}: {tid},")
L("}")
L("")
L("_BY_ID: dict[int, str] = {")
for tid, name in sorted(by_id.items()):
    L(f"    {tid}: {name!r},")
L("}")
L("")
L("# ── confidence-based partitions ───────────────")
L("VERIFIED: set[int] = {  # high + medium")
vids = [str(tid) for tid, _, _ in verified]
L("    " + ", ".join(vids))
L("}")
L("")
L("INFERRED: set[int] = {  # manual")
iids = [str(tid) for tid, _, _ in inferred]
L("    " + ", ".join(iids))
L("}")
L("")
L("")
L("def lookup_by_name(name: str) -> dict[str, int | str | None]:")
L('    """按节点名称查找 type_id。"""')
L("    tid = _BY_NAME.get(name)")
L("    if tid is None:")
L("        return {'type_id': None, 'confidence': None}")
L("    conf = 'verified' if tid in VERIFIED else 'inferred'")
L("    return {'type_id': tid, 'confidence': conf}")
L("")
L("")
L("def lookup_by_type_id(type_id: int) -> dict[str, str | None]:")
L('    """按 type_id 查找节点名称。"""')
L("    name = _BY_ID.get(type_id)")
L("    if name is None:")
L("        return {'name': None, 'category': None, 'confidence': None}")
L("    conf = 'verified' if type_id in VERIFIED else 'inferred'")
L("    return {'name': name, 'category': None, 'confidence': conf}")

out = Path("tools/live_sync/verified_type_ids.py")
out.write_text("\n".join(lines), encoding="utf-8")
print(f"Generated verified_type_ids.py: {len(verified)} verified, {len(inferred)} inferred")
