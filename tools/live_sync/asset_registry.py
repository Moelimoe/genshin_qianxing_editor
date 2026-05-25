# -*- coding: utf-8 -*-
"""千星资产对象注册表：编目所有已知可用的对象类型和ID

所有数据来源于用户提供的已验证可导入的 .gia 示例文件。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import copy

# ══════════════════════════════════════════════
# 资产对象类型枚举
# ══════════════════════════════════════════════
@dataclass(frozen=True, slots=True)
class AssetType:
    name: str            # 编辑器中的显示名称
    example_name: str    # 示例中的资源名称
    resource_class: int  # GIA resource_class
    loc_id: int          # Location.loc_id (template_root_id)
    type_code: int       # 模板类型码 (10005018=空模型, 20001270=钥匙等)
    category: str        # 分类: 物件/实体/战斗/高级工具/场景/配置/节点图


# ══════════════════════════════════════════════
# 已验证可导入的资产注册表（重新定义为 _original_registry 规避重复）
# ══════════════════════════════════════════════
_original_registry = {
    # ── 物件 (OBJECT) ──
    "coin": AssetType("金币", "金币", 1, 1077936129, 10005018, "物件"),
    "key": AssetType("钥匙", "钥匙", 1, 1077936140, 20001270, "物件"),
    
    # ── 实体 (OBJECT_ENTITY) ──
    "goblet": AssetType("酒杯", "酒杯20001431", 3, 1077936233, 0, "实体"),
    
    # ── 战斗 ──
    "player_template": AssetType("玩家模板", "默认模版", 18, 1086324737, 0, "战斗"),
    "custom_class": AssetType("自定义职业", "自定义职业", 17, 1090519041, 0, "战斗"),
    
    # ── 高级工具 ──
    "camera": AssetType("自定义镜头", "自定义镜头", 13, 1073741825, 0, "高级工具"),
    "layout": AssetType("默认布局", "默认布局", 20, 1073741825, 0, "高级工具"),
    "preset_point": AssetType("新建预设点", "新建预设点", 6, 1073741825, 0, "高级工具"),
    "env_config": AssetType("环境配置", "环境配置", 49, 1186988033, 0, "高级工具"),
    
    # ── 场景 ──
    "terrain": AssetType("地形01", "地形01", 5, 1073741825, 0, "场景"),
    
    # ── 配置 ──
    "normal_attack": AssetType("普通攻击", "普通攻击", 8, 1098907649, 0, "配置"),
}

ASSET_REGISTRY: Dict[str, AssetType] = dict(_original_registry)

# 按分类索引
ASSETS_BY_CATEGORY: Dict[str, List[AssetType]] = {}
for at in ASSET_REGISTRY.values():
    ASSETS_BY_CATEGORY.setdefault(at.category, []).append(at)

# 建立 key 查找（loc_id → key）
ASSET_KEY_MAP: Dict[int, str] = {}
for k, at in ASSET_REGISTRY.items():
    ASSET_KEY_MAP[at.loc_id] = k

# 分类：需要提供 GIA data 的来源路径
# 因为每个资产类型的 entry 数据来自不同的示例文件
_ASSET_SOURCE_MAP = {
    "coin": "金币与节点图.gia",
    "key": "实体.gia",
    "goblet": "实体.gia",
    "player_template": "战斗.gia",
    "custom_class": "战斗.gia",
    "camera": "高级工具.gia",
    "layout": "高级工具.gia",
    "preset_point": "高级工具.gia",
    "env_config": "高级工具.gia",
    "terrain": "场景编辑.gia",
    "normal_attack": "普通攻击.gia",
}


def list_all_assets() -> List[str]:
    """列出所有已知资产 key"""
    return sorted(ASSET_REGISTRY.keys())


def list_assets_by_category() -> Dict[str, List[str]]:
    """按分类列出资产"""
    result: Dict[str, List[str]] = {}
    for at in ASSET_REGISTRY.values():
        result.setdefault(at.category, []).append(at.name)
    return result


def get_asset(key: str) -> Optional[AssetType]:
    """获取资产定义"""
    return ASSET_REGISTRY.get(key)


def get_asset_by_name(name: str) -> Optional[AssetType]:
    """按名称查找资产"""
    for at in ASSET_REGISTRY.values():
        if at.name == name:
            return at
    return None


def load_asset_entry(key: str, sample_root: Optional[Path] = None) -> Optional[dict]:
    """
    从示例文件加载指定资产的 entry 数据
    
    Args:
        key: 资产 key
        sample_root: 示例文件目录（默认使用项目内置路径）
    
    Returns:
        资产的 entry dict (numeric_message 格式，可重新编码)
    """
    if key not in ASSET_REGISTRY:
        return None
    
    at = ASSET_REGISTRY[key]
    
    # 定位示例文件
    if sample_root is None:
        sample_root = Path(__file__).resolve().parent / "samples" / "export_examples"
    
    # 优先从 export_examples 加载
    source_file_name = _ASSET_SOURCE_MAP.get(key, "")
    source_path: Optional[Path] = None
    
    # 1. 尝试 export_examples 目录
    for p in sample_root.glob("*.gia"):
        if p.stem in source_file_name or source_file_name.startswith(p.stem):
            source_path = p
            break
    
    # 2. 尝试附件目录
    if source_path is None:
        import os
        attach_root = Path(os.environ.get("USERPROFILE", "")) / ".trae-cn" / "attachments"
        for p in attach_root.rglob("*.gia"):
            if source_file_name in p.name:
                source_path = p
                break
    
    if source_path is None:
        return None
    
    # 解析 GIA 并查找匹配的 entry
    from tools.live_sync.gia_utils import load_gia_numeric, get_entries, get_entry_name
    
    num = load_gia_numeric(source_path)
    
    for entry in get_entries(num):
        entry_name = get_entry_name(entry)
        
        # 匹配：示例名称或 loc_id
        if entry_name == at.example_name or (isinstance(entry.get('1', {}), dict) and entry['1'].get('4') == at.loc_id):
            return copy.deepcopy(entry)
    
    return None


def print_asset_catalog():
    """打印资产目录"""
    print("=" * 70)
    print("千星资产注册表（已验证可导入）")
    print("=" * 70)
    
    for category in ["物件", "实体", "战斗", "高级工具", "场景", "配置"]:
        items = ASSETS_BY_CATEGORY.get(category, [])
        if not items:
            continue
        print(f"\n── {category} ──")
        for at in items:
            k = [k for k, v in ASSET_REGISTRY.items() if v is at]
            key_str = k[0] if k else "?"
            tc_str = f"type={at.type_code}" if at.type_code else ""
            print(f"  {key_str:<20} {at.name:<12} rc={at.resource_class:<3} id=0x{at.loc_id:08X} {tc_str}")
    
    print(f"\n共 {len(ASSET_REGISTRY)} 种资产类型")
    print(f"\n可用 key: {', '.join(list_all_assets())}")
