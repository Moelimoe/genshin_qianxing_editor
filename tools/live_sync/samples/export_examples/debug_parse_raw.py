# -*- coding: utf-8 -*-
# 直接看field_map（底层解码结果，未经bridge转换）
from private_extensions.ugc_file_tools.gil_dump_codec.protobuf_like import decode_message_to_field_map
from private_extensions.ugc_file_tools.gia.container import unwrap_gia_container
import json
from pathlib import Path

proto = unwrap_gia_container(Path("石板坍塌.gia"))
fm, _ = decode_message_to_field_map(data_bytes=proto, start_offset=0, end_offset=len(proto), remaining_depth=64)

# 递归打印结构
def dump(obj, indent=0):
    prefix = "  " * indent
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, dict) and 'message' in v:
                print(f"{prefix}{k}: message")
                dump(v['message'], indent+1)
            elif isinstance(v, dict) and 'int' in v:
                print(f"{prefix}{k}: int={v['int']}")
            elif isinstance(v, list):
                print(f"{prefix}{k}: list[{len(v)}]")
                for i, item in enumerate(v[:3]):
                    dump(item, indent+1)
                if len(v) > 3:
                    print(f"{prefix}  ... ({len(v)-3} more)")
            else:
                print(f"{prefix}{k}: {json.dumps(v, default=str)[:80]}")
    elif isinstance(obj, list):
        for i, item in enumerate(obj[:3]):
            dump(item, indent)
        if len(obj) > 3:
            print(f"{'  ' * indent}... ({len(obj)-3} more)")

dump(fm)