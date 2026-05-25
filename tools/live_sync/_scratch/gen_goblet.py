# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, r'h:\myprojects\genshin_qianxing_editor')

from pathlib import Path
import time

from tools.live_sync.asset_registry import get_asset, load_asset_entry
from private_extensions.ugc_file_tools.gil_dump_codec.protobuf_like import (
    encode_message, format_binary_data_hex_text,
)
from private_extensions.ugc_file_tools.gia.container import wrap_gia_container

# 配置
output = Path(r'h:\myprojects\genshin_qianxing_editor\tools\live_sync\samples\test_goblet_only.gia')
sample_root = Path(r'h:\myprojects\genshin_qianxing_editor\tools\live_sync\samples\export_examples')
uid = 6000061

# 加载酒杯资产
key = 'goblet'
at = get_asset(key)
if at is None:
    print(f"错误: 未知资产 key={key}")
    sys.exit(1)

print(f"加载资产: {at.name} ({at.category}, rc={at.resource_class})")

entry = load_asset_entry(key, sample_root=sample_root)
if entry is None:
    print(f"错误: 无法加载 key={key} 的示例数据")
    sys.exit(1)

print(f"成功加载 entry")

# 构建 export_tag
tag = format_binary_data_hex_text(
    f'{uid}-{int(time.time())}-1073741827-\\{output.stem}.gia'.encode('utf-8')
)

msg = {'1': [entry], '3': tag}
proto_out = encode_message(msg)
gil = wrap_gia_container(proto_out)

output.parent.mkdir(parents=True, exist_ok=True)
output.write_bytes(gil)

print(f"\n生成成功: {output}")
print(f"文件大小: {output.stat().st_size/1024:.1f} KB")
print(f"内容: {at.name}")
