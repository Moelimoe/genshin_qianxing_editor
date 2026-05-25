# -*- coding: utf-8 -*-
"""LevelExporter 模块 - 将 GraphBuilder 输出封装为完整 GIA

核心类：
- ExportResult: 导出结果数据类
- LevelExporter: 关卡导出器主类

用法:
    exporter = LevelExporter()
    result = exporter.export(graph, "goblet", Path("output.gia"))
    
    if result.ok:
        print(f"导出成功: {result.output_path}")
"""
from __future__ import annotations

import copy
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from tools.live_sync.asset_registry import load_asset_entry, get_asset, AssetType
from tools.live_sync.gia_utils import save_gia_numeric, load_gia_numeric, get_entries, make_binary_name
from tools.live_sync.validator import GIAValidator, ValidationReport
from tools.live_sync.level_builder import GraphBuilder

logger = logging.getLogger("live_sync.exporter")

from tools.live_sync.verified_type_ids import lookup_by_type_id as _lookup_verified


def _warn_unverified_type_ids(ng_entry: Dict[str, Any], output_path: Path) -> None:
    """扫描 NG entry 中所有节点的 type_id，对未验证 ID 发出警告"""
    if not ng_entry:
        return
    ng = ng_entry.get('13', {})
    graph = ng.get('1', {}).get('1', {})
    nodes = graph.get('3', [])
    if isinstance(nodes, dict):
        nodes = [nodes]

    unverified: List[tuple] = []
    verified: List[tuple] = []
    for n in nodes:
        tid = n.get('2', {})
        if isinstance(tid, dict):
            real_id = tid.get('5')
        else:
            real_id = tid
        if isinstance(real_id, int):
            info = _lookup_verified(real_id)
            if info['confidence']:
                verified.append((n.get('1'), real_id, info.get('name', '?'), info['confidence']))
            else:
                unverified.append((n.get('1'), real_id))

    if verified:
        parts = ", ".join(f"#{nid}({name}, {conf})" for nid, _, name, conf in verified)
        logger.info("✅ 文件 %s: %d 个已验证节点 — %s", output_path.name, len(verified), parts)
    
    if unverified:
        names = ", ".join(f"#{nid}(type_id={tid})" for nid, tid in unverified)
        logger.warning(
            "⚠️  文件 %s 的节点图中有 %d 个节点 type_id 未经验证: %s。"
            " 这些节点在编辑器中可能不会显示。",
            output_path.name, len(unverified), names,
        )


# ═══════════════════════════════════════════════════════════════
# ExportResult 数据类
# ═══════════════════════════════════════════════════════════════

@dataclass
class ExportResult:
    """导出结果
    
    Attributes:
        output_path: 输出文件路径
        entity_entry: entity entry字典
        ng_entry: NG entry字典
        validation_report: 验证报告（如果启用验证）
    """
    output_path: Path
    entity_entry: Dict[str, Any]
    ng_entry: Dict[str, Any]
    validation_report: Optional[ValidationReport] = None
    
    @property
    def ok(self) -> bool:
        """导出是否成功（无验证错误或验证通过）"""
        if self.validation_report is None:
            return True
        return self.validation_report.ok


# ═══════════════════════════════════════════════════════════════
# LevelExporter 主类
# ═══════════════════════════════════════════════════════════════

class LevelExporter:
    """关卡导出器 - 将 GraphBuilder 输出封装为完整 GIA
    
    将 GraphBuilder 生成的节点图与实体模板组合，生成包含
    entity + NG 的完整 GIA 文件。
    
    用法:
        exporter = LevelExporter()
        result = exporter.export(graph, "goblet", Path("output.gia"))
        
        # 或者只生成 numeric dict 不保存
        num = exporter.export_to_numeric(graph, "goblet")
    """
    
    def __init__(
        self,
        sample_root: Optional[Path] = None,
        default_uid: int = 6000061,
    ):
        """初始化 LevelExporter
        
        Args:
            sample_root: 示例GIA文件目录（默认使用内置路径）
            default_uid: 默认用户ID
        """
        self._sample_root = sample_root
        self._default_uid = default_uid
        self._validator = GIAValidator()
    
    def export(
        self,
        graph: GraphBuilder,
        asset_key: str,
        output_path: Path,
        *,
        uid: Optional[int] = None,
        name: Optional[str] = None,
        validate: bool = True,
    ) -> ExportResult:
        """导出 GraphBuilder 为 GIA 文件
        
        Args:
            graph: GraphBuilder 实例
            asset_key: 资产 key（如 "goblet", "coin", "key"）
            output_path: 输出文件路径
            uid: 用户ID（默认使用构造时的 default_uid）
            name: 导出名称（默认使用 graph.name）
            validate: 是否验证 GraphBuilder（默认True）
        
        Returns:
            ExportResult: 导出结果
        
        Raises:
            ValueError: 未知 asset_key 或验证失败
        """
        # 验证 GraphBuilder（如果启用）
        validation_report = None
        if validate:
            graph_validation = graph.validate()
            if not graph_validation.ok:
                raise ValueError(f"GraphBuilder 验证失败: {'; '.join(graph_validation.errors)}")
            
            # 进行更详细的GIA结构验证
            num_check = graph.to_numeric()
            validation_report = self._validator.validate_numeric(num_check)
        
        # 构建完整的 GIA numeric dict
        final_gia = self.export_to_numeric(
            graph=graph,
            asset_key=asset_key,
            uid=uid,
            name=name,
            validate=False,  # 已在上面验证
        )
        
        # 验证最终GIA结构（如果启用）
        if validate and validation_report is not None:
            final_validation = self._validator.validate_numeric(final_gia)
            validation_report.issues.extend(final_validation.issues)
        
        # 保存GIA文件
        output_path = Path(output_path)
        save_gia_numeric(final_gia, output_path)
        
        # 提取entity和NG entry
        entries = get_entries(final_gia)
        entity_entry = entries[0] if len(entries) > 0 else {}
        ng_entry = entries[1] if len(entries) > 1 else {}
        
        # 扫描节点 type_id，检查是否已验证
        _warn_unverified_type_ids(ng_entry, output_path)
        
        return ExportResult(
            output_path=output_path,
            entity_entry=entity_entry,
            ng_entry=ng_entry,
            validation_report=validation_report,
        )
    
    def export_to_numeric(
        self,
        graph: GraphBuilder,
        asset_key: str,
        *,
        uid: Optional[int] = None,
        name: Optional[str] = None,
        validate: bool = True,
    ) -> Dict[str, Any]:
        """导出为 numeric dict（不保存文件）
        
        Args:
            graph: GraphBuilder 实例
            asset_key: 资产 key
            uid: 用户ID
            name: 导出名称
            validate: 是否验证
        
        Returns:
            完整的 GIA numeric dict
        """
        # 验证（如果启用）
        if validate:
            graph_validation = graph.validate()
            if not graph_validation.ok:
                raise ValueError(f"GraphBuilder 验证失败: {'; '.join(graph_validation.errors)}")
        
        # 1. 加载 entity entry
        entity_entry = self._load_entity_entry(asset_key)
        
        # 2. 提取 NG entry
        ng_entry = self._extract_ng_entry(graph)
        
        # 3. 组合 entries
        entries = self._combine_entries(entity_entry, ng_entry)
        
        # 4. 生成 export_tag
        export_name = name or graph.name or asset_key
        actual_uid = uid if uid is not None else self._default_uid
        export_tag = self._build_export_tag(export_name, asset_key, actual_uid)
        
        # 5. 构建最终 GIA
        final_gia = {
            '1': entries,
            '3': export_tag,
        }
        
        return final_gia
    
    def _load_entity_entry(self, asset_key: str) -> Dict[str, Any]:
        """加载 entity entry
        
        Args:
            asset_key: 资产 key
        
        Returns:
            entity entry dict
        
        Raises:
            ValueError: 未知 asset_key 或加载失败
        """
        # 检查 asset_key 是否有效
        at = get_asset(asset_key)
        if at is None:
            raise ValueError(f"未知资产 key: {asset_key}")
        
        # 加载 entity entry
        entity_entry = load_asset_entry(asset_key, self._sample_root)
        if entity_entry is None:
            raise ValueError(f"无法加载资产 '{asset_key}' 的示例数据")
        
        return copy.deepcopy(entity_entry)
    
    def _extract_ng_entry(self, graph: GraphBuilder) -> Dict[str, Any]:
        """从 GraphBuilder 提取 NG entry
        
        Args:
            graph: GraphBuilder 实例
        
        Returns:
            NG entry dict
        """
        # GraphBuilder.to_numeric() 返回 [entity_entry, ng_entry]
        gia_msg = graph.to_numeric()
        entries = get_entries(gia_msg)
        
        if not entries:
            raise ValueError("GraphBuilder 未生成任何 entry")
        
        # 找 NG entry（f5=9 或有 '13' 字段）
        ng_entry = None
        for e in entries:
            if e.get('5') == 9 or '13' in e:
                ng_entry = e
                break
        if ng_entry is None:
            ng_entry = entries[0]  # 降级
        
        return copy.deepcopy(ng_entry)
    
    def _build_export_tag(
        self,
        name: str,
        asset_key: str,
        uid: int,
    ) -> str:
        """构建 export_tag
        
        Args:
            name: 导出名称
            asset_key: 资产 key
            uid: 用户ID
        
        Returns:
            binary_data 格式的 export_tag
        """
        # 获取资产的 graph_id（使用 loc_id）
        at = get_asset(asset_key)
        graph_id = at.loc_id if at else 1073741827
        
        # 格式: uid-timestamp-graph_id-\name.gia
        tag_text = f'{uid}-{int(time.time())}-{graph_id}-\\{name}.gia'
        
        return make_binary_name(tag_text)
    
    def _combine_entries(
        self,
        entity_entry: Dict[str, Any],
        ng_entry: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """组合 entity 和 NG entry，建立关联
        
        关联机制：Entity.entry['2']['4'] == NG.entry['1']['4']
        通过相同的 asset_key 将节点图挂载到实体/组件上。
        
        Args:
            entity_entry: entity entry
            ng_entry: NG entry
        
        Returns:
            entries 列表 [entity_entry, ng_entry]
        """
        entity = copy.deepcopy(entity_entry)
        ng = copy.deepcopy(ng_entry)
        
        # 从 entity 获取 asset_key
        entity_f2 = entity.get('2', {})
        asset_key = entity_f2.get('4') if isinstance(entity_f2, dict) else None
        
        if asset_key is not None:
            # Entity 已有 asset_key → 同步到 NG
            ng_f1 = ng.setdefault('1', {})
            if isinstance(ng_f1, dict):
                ng_f1['4'] = asset_key
            logger.debug("🔗 关联 Entity↔NG: asset_key=%s", asset_key)
        else:
            # Entity 没有 asset_key → 用 NG 的 f1.4 回写 entity
            ng_f1 = ng.get('1', {})
            ng_asset_key = ng_f1.get('4') if isinstance(ng_f1, dict) else None
            if ng_asset_key is not None:
                entity['2'] = entity.get('2', {})
                if isinstance(entity['2'], dict):
                    entity['2']['4'] = ng_asset_key
                logger.debug(
                    "🔗 关联 Entity↔NG: asset_key=%s (从 NG 回写到 Entity)",
                    ng_asset_key,
                )
            else:
                logger.warning(
                    "⚠️  Entity 和 NG 都没有 asset_key，无法建立关联。"
                )
        
        return [entity, ng]


# ═══════════════════════════════════════════════════════════════
# LevelBuilder 扩展（集成导出功能）
# ═══════════════════════════════════════════════════════════════

class LevelBuilder:
    """关卡构建器（扩展）- 集成导出功能
    
    在原有 LevelBuilder 基础上添加导出到 GIA 的功能。
    
    用法:
        builder = LevelBuilder("MyLevel")
        asset_type, graph = builder.add_entity_with_graph("goblet", "Graph1")
        
        # 导出
        result = builder.to_gia(Path("output.gia"), "goblet")
    """
    
    def __init__(
        self,
        name: str,
        sample_root: Optional[Path] = None,
        default_uid: int = 6000061,
    ):
        """初始化 LevelBuilder
        
        Args:
            name: 关卡名称
            sample_root: 示例文件目录
            default_uid: 默认用户ID
        """
        self.name = name
        self._exporter = LevelExporter(
            sample_root=sample_root,
            default_uid=default_uid,
        )
        self._graphs: List[Tuple[str, GraphBuilder]] = []  # (asset_key, graph) 列表
    
    def add_entity_with_graph(
        self,
        asset_key: str,
        graph_name: str,
        catalog: Optional[Any] = None,
    ) -> Tuple[AssetType, GraphBuilder]:
        """添加实体和对应的节点图
        
        Args:
            asset_key: 资产 key
            graph_name: 图名称
            catalog: 可选的 NodeCatalog
        
        Returns:
            (AssetType, GraphBuilder) 元组
        
        Raises:
            ValueError: 未知 asset_key
        """
        at = get_asset(asset_key)
        if at is None:
            raise ValueError(f"未知资产 key: {asset_key}")
        
        graph = GraphBuilder(name=graph_name, catalog=catalog)
        self._graphs.append((asset_key, graph))
        
        return at, graph
    
    def to_gia(
        self,
        output_path: Path,
        asset_key: str,
        *,
        uid: Optional[int] = None,
        validate: bool = True,
    ) -> ExportResult:
        """导出为 GIA 文件
        
        注意：当前只支持导出第一个图。如需导出多个图，
        请直接使用 LevelExporter。
        
        Args:
            output_path: 输出路径
            asset_key: 资产 key
            uid: 用户ID
            validate: 是否验证
        
        Returns:
            ExportResult
        """
        if not self._graphs:
            raise ValueError("没有可导出的图，请先调用 add_entity_with_graph()")
        
        # 使用第一个图
        _, graph = self._graphs[0]
        
        return self._exporter.export(
            graph=graph,
            asset_key=asset_key,
            output_path=output_path,
            uid=uid,
            name=self.name,
            validate=validate,
        )
    
    def get_graph(self, index: int = 0) -> Optional[GraphBuilder]:
        """获取指定索引的图
        
        Args:
            index: 图索引
        
        Returns:
            GraphBuilder 或 None
        """
        if 0 <= index < len(self._graphs):
            return self._graphs[index][1]
        return None
    
    @property
    def graph_count(self) -> int:
        """图数量"""
        return len(self._graphs)


# ═══════════════════════════════════════════════════════════════
# 便捷函数
# ═══════════════════════════════════════════════════════════════

def export_level(
    graph: GraphBuilder,
    asset_key: str,
    output_path: Path,
    *,
    sample_root: Optional[Path] = None,
    uid: Optional[int] = None,
    name: Optional[str] = None,
    validate: bool = True,
) -> ExportResult:
    """便捷函数：导出关卡
    
    Args:
        graph: GraphBuilder 实例
        asset_key: 资产 key
        output_path: 输出路径
        sample_root: 示例文件目录
        uid: 用户ID
        name: 导出名称
        validate: 是否验证
    
    Returns:
        ExportResult
    """
    exporter = LevelExporter(sample_root=sample_root)
    return exporter.export(
        graph=graph,
        asset_key=asset_key,
        output_path=output_path,
        uid=uid,
        name=name,
        validate=validate,
    )


def quick_export(
    graph: GraphBuilder,
    asset_key: str,
    output_path: Path,
) -> Path:
    """快速导出（无验证，使用默认设置）
    
    Args:
        graph: GraphBuilder 实例
        asset_key: 资产 key
        output_path: 输出路径
    
    Returns:
        输出文件路径
    """
    exporter = LevelExporter()
    result = exporter.export(
        graph=graph,
        asset_key=asset_key,
        output_path=output_path,
        validate=False,
    )
    return result.output_path


# ═══════════════════════════════════════════════════════════════
# CLI 测试
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # 简单测试
    print("=== LevelExporter 测试 ===")
    
    # 创建简单图
    graph = GraphBuilder(name="TestGraph")
    
    # 导出
    output = Path(__file__).resolve().parent / "samples" / "test_level_exporter.gia"
    
    try:
        exporter = LevelExporter()
        result = exporter.export(graph, "goblet", output)
        
        print(f"导出成功: {result.output_path}")
        print(f"  - 文件大小: {output.stat().st_size / 1024:.1f} KB")
        print(f"  - 验证通过: {result.ok}")
        print(f"  - Entity entry keys: {list(result.entity_entry.keys())}")
        print(f"  - NG entry keys: {list(result.ng_entry.keys())}")
        
        # 验证文件
        num = load_gia_numeric(output)
        entries = get_entries(num)
        print(f"  - Entries数量: {len(entries)}")
        for i, e in enumerate(entries):
            entry_type = "Entity" if '11' in e else ("NG" if '13' in e else "Unknown")
            print(f"    [{i}]: {entry_type} - keys={list(e.keys())}")
        
    except Exception as e:
        print(f"导出失败: {e}")
        import traceback
        traceback.print_exc()
