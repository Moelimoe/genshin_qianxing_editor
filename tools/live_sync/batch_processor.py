# -*- coding: utf-8 -*-
"""GIA 批量处理器

支持对多个GIA文件执行统一的修改操作。

Usage:
    from tools.live_sync.batch_processor import BatchProcessor, modify_param_rule

    bp = BatchProcessor(catalog=catalog)
    result = bp.process(
        input_files=["a.gia", "b.gia"],
        rules=[modify_param_rule("信号名", "new_signal")],
        output_dir=Path("output/"),
    )
    print(result.summary())
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from tools.live_sync.gia_loader import GIALoader
from tools.live_sync.level_exporter import LevelExporter
from tools.live_sync.node_catalog import NodeCatalog
from tools.live_sync.validate import validate_file


# ═══════════════════════════════════════════════════════════════
# 数据类
# ═══════════════════════════════════════════════════════════════

@dataclass
class ModifyRule:
    """单条修改规则"""
    param_name: str
    new_value: Any
    old_value: Optional[Any] = None  # 如果设置，只匹配旧值时才修改
    node_name_filter: Optional[str] = None  # 如果设置，只修改指定名称的节点
    description: str = ""


@dataclass
class BatchResult:
    """批量处理结果"""
    total: int = 0
    success: int = 0
    failed: int = 0
    skipped: int = 0
    details: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.failed == 0

    def summary(self) -> str:
        lines = [
            f"批量处理完成: {self.total} 个文件",
            f"  ✅ 成功: {self.success}",
            f"  ⏭️  跳过: {self.skipped}",
            f"  ❌ 失败: {self.failed}",
        ]
        if self.details:
            lines.append("")
            for d in self.details:
                status = d.get("status", "?")
                name = d.get("file", "?")
                msg = d.get("message", "")
                lines.append(f"  [{status}] {name}: {msg}")
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# 规则工厂函数
# ═══════════════════════════════════════════════════════════════

def modify_param_rule(
    param_name: str,
    new_value: Any,
    node_name_filter: Optional[str] = None,
) -> ModifyRule:
    """创建参数修改规则（无条件修改所有匹配节点）"""
    return ModifyRule(
        param_name=param_name,
        new_value=new_value,
        description=f"设置参数 '{param_name}' = {new_value!r}"
    )


def rename_signal_rule(
    old_signal: str,
    new_signal: str,
) -> ModifyRule:
    """创建信号重命名规则（只修改匹配旧信号名的节点）"""
    return ModifyRule(
        param_name="信号名",
        new_value=new_signal,
        old_value=old_signal,
        description=f"重命名信号 '{old_signal}' → '{new_signal}'"
    )


# ═══════════════════════════════════════════════════════════════
# BatchProcessor
# ═══════════════════════════════════════════════════════════════

class BatchProcessor:
    """GIA 批量处理器

    对多个GIA文件执行统一的修改操作，支持：
    - 批量修改参数
    - 条件修改（只修改匹配特定值的节点）
    - 节点名称过滤
    - 验证后修改
    - 干运行模式（不实际写入）
    """

    def __init__(
        self,
        catalog: Optional[NodeCatalog] = None,
        asset_key: str = "goblet",
    ) -> None:
        self._catalog = catalog or NodeCatalog.default()
        self._asset_key = asset_key

    def process(
        self,
        input_files: List[Path],
        rules: List[ModifyRule],
        output_dir: Path,
        *,
        dry_run: bool = False,
        validate_before: bool = False,
        validate_after: bool = True,
        overwrite: bool = False,
    ) -> BatchResult:
        """批量处理GIA文件

        Args:
            input_files: 输入GIA文件路径列表
            rules: 修改规则列表
            output_dir: 输出目录
            dry_run: 干运行模式，不实际写入文件
            validate_before: 修改前验证GIA结构
            validate_after: 修改后验证输出文件
            overwrite: 是否覆盖已存在的输出文件

        Returns:
            BatchResult 处理结果
        """
        result = BatchResult(total=len(input_files))
        output_dir.mkdir(parents=True, exist_ok=True)

        loader = GIALoader(catalog=self._catalog)
        exporter = LevelExporter()

        for gia_path in input_files:
            gia_path = Path(gia_path)
            detail: Dict[str, Any] = {"file": gia_path.name}

            try:
                # 1. 检查输入文件
                if not gia_path.exists():
                    detail["status"] = "SKIP"
                    detail["message"] = "文件不存在"
                    result.skipped += 1
                    result.details.append(detail)
                    continue

                # 2. 可选：修改前验证
                if validate_before:
                    report = validate_file(gia_path, catalog=self._catalog)
                    if not report.ok:
                        detail["status"] = "SKIP"
                        detail["message"] = f"验证失败: {len(report.errors)} 个错误"
                        result.skipped += 1
                        result.details.append(detail)
                        continue

                # 3. 加载GIA
                loaded = loader.load(gia_path)
                if loaded.get_graph_count() == 0:
                    detail["status"] = "SKIP"
                    detail["message"] = "没有NodeGraph"
                    result.skipped += 1
                    result.details.append(detail)
                    continue

                # 4. 应用修改规则
                modified = False
                for gi in range(loaded.get_graph_count()):
                    graph = loaded.get_graph(gi, catalog=self._catalog)
                    for ni in range(graph.node_count()):
                        node = graph.get_node(ni)
                        for rule in rules:
                            if self._apply_rule(node, rule):
                                modified = True

                if not modified and not dry_run:
                    # 没有实际修改，直接复制
                    out_path = output_dir / gia_path.name
                    if overwrite or not out_path.exists():
                        shutil.copy2(gia_path, out_path)
                    detail["status"] = "OK"
                    detail["message"] = "无修改，已复制"
                    result.success += 1
                    result.details.append(detail)
                    continue

                # 5. 导出
                if dry_run:
                    detail["status"] = "DRY"
                    detail["message"] = "干运行，未写入"
                    result.success += 1
                    result.details.append(detail)
                    continue

                out_path = output_dir / gia_path.name
                if not overwrite and out_path.exists():
                    detail["status"] = "SKIP"
                    detail["message"] = "输出文件已存在"
                    result.skipped += 1
                    result.details.append(detail)
                    continue

                export_result = exporter.export(
                    graph, self._asset_key, out_path, validate=False
                )

                if not export_result.ok:
                    detail["status"] = "FAIL"
                    detail["message"] = "导出失败"
                    result.failed += 1
                    result.details.append(detail)
                    continue

                # 6. 可选：修改后验证
                if validate_after:
                    report = validate_file(out_path, catalog=self._catalog)
                    if not report.ok:
                        detail["status"] = "FAIL"
                        detail["message"] = f"输出验证失败: {len(report.errors)} 个错误"
                        result.failed += 1
                        result.details.append(detail)
                        # 清理失败的输出
                        if out_path.exists():
                            out_path.unlink()
                        continue

                detail["status"] = "OK"
                detail["message"] = "成功"
                result.success += 1

            except Exception as e:
                detail["status"] = "FAIL"
                detail["message"] = str(e)[:100]
                result.failed += 1

            result.details.append(detail)

        return result

    def _apply_rule(self, node: Any, rule: ModifyRule) -> bool:
        """对单个节点应用修改规则

        Returns:
            True 如果实际修改了参数
        """
        # 节点名称过滤
        if rule.node_name_filter is not None:
            if node.name != rule.node_name_filter:
                return False

        # 检查参数是否存在
        current = node.get_param(rule.param_name)
        if current is None:
            return False

        # 条件匹配：如果设置了old_value，只修改匹配的
        if rule.old_value is not None and current != rule.old_value:
            return False

        # 应用修改
        node.set_param(rule.param_name, rule.new_value)
        return True
