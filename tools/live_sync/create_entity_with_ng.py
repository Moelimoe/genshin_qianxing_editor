# -*- coding: utf-8 -*-
"""创建包含节点图的实体 GIA 文件

用法:
    python -m tools.live_sync.create_entity_with_ng goblet -n 2 -o output.gia

已通过 L3 编辑器验证的结构：
  条目列表 = [实体 entry, NG entry, NG entry, ...]
  关键规则：NG 必须是独立条目，不能嵌入到实体 entry 的字段中
"""
import sys, time, copy
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.live_sync.asset_registry import load_asset_entry, get_asset
from tools.live_sync.gia_utils import load_gia_numeric, get_ng_entries
from private_extensions.ugc_file_tools.gia.container import wrap_gia_container
from private_extensions.ugc_file_tools.gil_dump_codec.protobuf_like import (
    encode_message, format_binary_data_hex_text,
)


DEFAULT_NG_SOURCE = Path(__file__).resolve().parent / "samples" / "test_clone_minimal_v2.gia"


def load_ng_entries(ng_source: Path) -> list:
    """从源 GIA 加载所有独立的 NG 条目"""
    num = load_gia_numeric(ng_source)
    return [copy.deepcopy(e) for e in get_ng_entries(num)]


def create_entity_with_nodegraph(
    asset_key: str,
    output: Path,
    ng_count: int = 1,
    ng_source_path: Path = None,
    uid: int = 6000061,
) -> Path:
    """
    创建包含节点图的实体 GIA 文件

    正确结构：entries = [entity_entry, ng_entry, ng_entry, ...]
    NG 作为独立条目，不与实体 entry 合并。

    Args:
        asset_key: 资产 key
        output: 输出路径
        ng_count: 要包含的 NG 条目数量
        ng_source_path: NG 源 GIA 文件
        uid: 用户 ID
    """
    sample_root = Path(__file__).resolve().parent / "samples" / "export_examples"
    ng_source = ng_source_path or DEFAULT_NG_SOURCE

    at = get_asset(asset_key)
    if at is None:
        raise ValueError(f"未知资产 key={asset_key}")

    # 1. 加载实体 entry（保持原样，包括 '12' related_ids）
    entity_entry = load_asset_entry(asset_key, sample_root=sample_root)
    if entity_entry is None:
        raise ValueError(f"无法加载 asset_key={asset_key} 的示例数据")

    print(f"实体: {at.name}  keys={list(entity_entry.keys())}")

    # 2. 加载独立 NG 条目
    ng_entries = load_ng_entries(ng_source)
    if not ng_entries:
        raise ValueError(f"NG 源中未找到 NodeGraph: {ng_source}")

    if ng_count > len(ng_entries):
        raise ValueError(f"请求 {ng_count} 个 NG，但源只有 {len(ng_entries)} 个")
    selected_ng = ng_entries[:ng_count]

    print(f"NG 条目: {len(selected_ng)} 个 (源共 {len(ng_entries)} 个)")
    for i, ng in enumerate(selected_ng):
        print(f"  NG[{i}]: keys={list(ng.keys())}")

    # 3. 构建条目列表：实体 + 独立 NG
    entries = [copy.deepcopy(entity_entry)] + selected_ng
    for i, e in enumerate(entries):
        print(f"  entry[{i}]: keys={list(e.keys())}")

    # 4. 生成 GIA
    tag = format_binary_data_hex_text(
        f'{uid}-{int(time.time())}-1073741827-\\{output.stem}.gia'.encode('utf-8')
    )

    msg = {'1': entries, '3': tag}
    proto_out = encode_message(msg)
    gil = wrap_gia_container(proto_out)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(gil)

    print(f"\n✅ {output.name} ({output.stat().st_size/1024:.1f} KB)")
    return output


def main():
    if len(sys.argv) < 2:
        print("用法:")
        print("  python -m tools.live_sync.create_entity_with_ng <asset_key> [-n count] [-o output.gia]")
        print("\n可用资产:")
        from tools.live_sync.asset_registry import list_all_assets
        for k in list_all_assets():
            print(f"  - {k}")
        sys.exit(1)

    asset_key = sys.argv[1]

    # 解析参数
    output = None
    ng_count = 1
    i = 2
    while i < len(sys.argv):
        if sys.argv[i] == "-o" and i + 1 < len(sys.argv):
            output = Path(sys.argv[i + 1])
            i += 2
        elif sys.argv[i] == "-n" and i + 1 < len(sys.argv):
            ng_count = int(sys.argv[i + 1])
            i += 2
        else:
            i += 1

    if output is None:
        output = PROJECT_ROOT / "tools" / "live_sync" / "samples" / f"{asset_key}_ng{ng_count}.gia"

    try:
        create_entity_with_nodegraph(asset_key, output, ng_count=ng_count)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
