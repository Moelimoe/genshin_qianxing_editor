# -*- coding: utf-8 -*-
"""千星资产 GIA 生成器 CLI

用法:
  # 列出所有可用资产
  python -m tools.live_sync.gia_asset_builder list

  # 生成单个资产
  python -m tools.live_sync.gia_asset_builder create coin -o my_coin.gia

  # 生成多个资产组合
  python -m tools.live_sync.gia_asset_builder create coin key camera -o combo.gia

  # 按分类导出
  python -m tools.live_sync.gia_asset_builder export 物件 -o objects.gia
"""

import sys, time
from pathlib import Path
from typing import List

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.live_sync.asset_registry import (
    ASSET_REGISTRY, ASSETS_BY_CATEGORY, get_asset, get_asset_by_name,
    print_asset_catalog, list_all_assets, load_asset_entry,
)
from private_extensions.ugc_file_tools.gil_dump_codec.protobuf_like import (
    encode_message, format_binary_data_hex_text,
)
from private_extensions.ugc_file_tools.gia.container import wrap_gia_container


class GiaAssetBuilder:
    """千星资产 GIA 文件生成器"""

    def __init__(self, sample_root: Path = None):
        if sample_root is None:
            sample_root = Path(__file__).resolve().parent / "samples"
        self._export_dir = sample_root / "export_examples"
        self._attachments = Path.home() / ".trae-cn" / "attachments"

    def create(self, asset_keys: List[str], output: Path, uid: int = 6000061) -> Path:
        """
        创建一个 GIA 文件，包含指定的资产

        Args:
            asset_keys: 资产 key 列表
            output: 输出文件路径
            uid: 用户 ID
        """
        entries = []
        names = []

        for key in asset_keys:
            at = get_asset(key)
            if at is None:
                print(f"警告: 未知资产 key={key}，跳过")
                continue

            entry = load_asset_entry(key, sample_root=self._export_dir)
            if entry is None:
                print(f"警告: 无法加载 key={key} 的示例数据，跳过")
                continue

            entries.append(entry)
            names.append(at.name)
            print(f"  + {at.name} ({at.category}, rc={at.resource_class})")

        if not entries:
            raise ValueError("没有可用的资产条目")

        # 构建 export_tag
        tag = format_binary_data_hex_text(
            f'{uid}-{int(time.time())}-1073741827-\\{output.stem}.gia'.encode('utf-8')
        )

        msg = {'1': entries, '3': tag}
        proto_out = encode_message(msg)
        gil = wrap_gia_container(proto_out)

        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(gil)

        print(f"\n生成: {output} ({len(entries)} 资产, {output.stat().st_size/1024:.1f} KB)")
        print(f"内容: {', '.join(names)}")
        return output

    def export_category(self, category: str, output: Path, uid: int = 6000061) -> Path:
        """导出整个分类的资产"""
        items = ASSETS_BY_CATEGORY.get(category, [])
        if not items:
            cats = list(ASSETS_BY_CATEGORY.keys())
            raise ValueError(f"未知分类 '{category}'，可用分类: {cats}")

        keys = []
        for at in items:
            for k, v in ASSET_REGISTRY.items():
                if v is at:
                    keys.append(k)
                    break

        return self.create(keys, output, uid=uid)


def main():
    """CLI 入口"""
    if len(sys.argv) < 2:
        print("用法:")
        print("  python -m tools.live_sync.gia_asset_builder list")
        print("  python -m tools.live_sync.gia_asset_builder create <key...> [-o output.gia]")
        print("  python -m tools.live_sync.gia_asset_builder export <category> [-o output.gia]")
        sys.exit(1)

    cmd = sys.argv[1]
    builder = GiaAssetBuilder()

    if cmd == "list":
        print_asset_catalog()

    elif cmd == "create":
        # 解析 -o 参数
        args = sys.argv[2:]
        output = None
        keys = []
        i = 0
        while i < len(args):
            if args[i] == "-o" and i + 1 < len(args):
                output = Path(args[i + 1])
                i += 2
            else:
                keys.append(args[i])
                i += 1

        if not keys:
            print("错误: 请指定至少一个资产 key")
            sys.exit(1)

        if output is None:
            output = PROJECT_ROOT / "tools" / "live_sync" / "samples" / f"build_{'_'.join(keys[:3])}.gia"

        builder.create(keys, output)

    elif cmd == "export":
        args = sys.argv[2:]
        if not args:
            print("错误: 请指定分类名称")
            sys.exit(1)

        category = args[0]
        output = None
        if len(args) >= 3 and args[1] == "-o":
            output = Path(args[2])

        if output is None:
            output = PROJECT_ROOT / "tools" / "live_sync" / "samples" / f"export_{category}.gia"

        builder.export_category(category, output)

    else:
        print(f"未知命令: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
