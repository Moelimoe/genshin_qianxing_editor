# -*- coding: utf-8 -*-
"""
Graph Code → GIL 存档同步核心逻辑
"""

from __future__ import annotations

import shutil
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

# 项目路径设置
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.graph.graph_code_parser import GraphCodeParser
from engine.graph.models.graph_model import GraphModel
from engine.configs.settings import settings

# UGC 文件工具
from private_extensions.ugc_file_tools.gia_export.node_graph.asset_bundle_builder import (
    create_gia_file_from_graph_model_json,
    GiaAssetBundleGraphExportHints,
)
from private_extensions.ugc_file_tools.save_patchers.gil_node_graph_injector import (
    inject_gia_into_gil_node_graph,
    GilNodeGraphInjectReport,
)
from private_extensions.ugc_file_tools.gia.container import validate_gia_container_file


@dataclass
class SyncReport:
    """同步结果报告"""

    success: bool
    message: str
    graph_code_path: Path
    target_gil_path: Path
    backup_path: Optional[Path] = None
    inject_report: Optional[GilNodeGraphInjectReport] = None
    duration_ms: float = 0.0


def compile_graph_code(graph_code_path: Path) -> GraphModel:
    """
    编译 Graph Code 文件为 GraphModel

    Args:
        graph_code_path: Graph Code Python 文件路径

    Returns:
        编译后的 GraphModel

    Raises:
        SyntaxError: 代码语法错误
        ValueError: 图结构验证失败
    """
    parser = GraphCodeParser()
    graph_model = parser.parse_file(str(graph_code_path))
    return graph_model


def export_graph_to_gia(
    graph_model: GraphModel,
    output_gia_path: Path,
    graph_id_int: int = 1073741825,  # 0x40000001
    graph_scope: str = "server",
) -> Path:
    """
    将 GraphModel 导出为 GIA 文件

    Args:
        graph_model: 图模型
        output_gia_path: 输出 GIA 文件路径
        graph_id_int: 图的 ID（默认 0x40000001）
        graph_scope: 图的作用域（server/client）

    Returns:
        生成的 GIA 文件路径
    """
    # 构建导出提示
    hints = GiaAssetBundleGraphExportHints(
        graph_id_int=graph_id_int,
        graph_name=graph_model.graph_name or graph_model.graph_id,
        graph_scope=graph_scope,
        resource_class="ENTITY_NODE_GRAPH",  # 可根据需要调整
        graph_generater_root=PROJECT_ROOT / "assets" / "资源库",
        node_type_id_by_node_def_key={},  # 可从节点库加载
    )

    # 转换 GraphModel 为字典
    graph_dict = graph_model_to_dict(graph_model)

    # 生成 GIA 文件
    create_gia_file_from_graph_model_json(
        graph_json_object=graph_dict,
        hints=hints,
        output_gia_path=output_gia_path,
    )

    # 验证生成的文件
    if not validate_gia_container_file(output_gia_path):
        raise ValueError(f"生成的 GIA 文件验证失败: {output_gia_path}")

    return output_gia_path


def graph_model_to_dict(graph_model: GraphModel) -> dict:
    """
    将 GraphModel 转换为可序列化的字典

    Args:
        graph_model: 图模型

    Returns:
        字典表示
    """
    return {
        "graph_id": graph_model.graph_id,
        "graph_name": graph_model.graph_name,
        "description": graph_model.description,
        "nodes": {
            node_id: {
                "id": node.id,
                "title": node.title,
                "category": node.category,
                "pos": node.pos,
                "inputs": [{"name": p.name, "is_input": p.is_input} for p in node.inputs],
                "outputs": [{"name": p.name, "is_input": p.is_input} for p in node.outputs],
                "input_constants": node.input_constants,
                "composite_id": node.composite_id,
                "is_virtual_pin": node.is_virtual_pin,
            }
            for node_id, node in graph_model.nodes.items()
        },
        "edges": {
            edge_id: {
                "id": edge.id,
                "src_node": edge.src_node,
                "src_port": edge.src_port,
                "dst_node": edge.dst_node,
                "dst_port": edge.dst_port,
            }
            for edge_id, edge in graph_model.edges.items()
        },
        "graph_variables": graph_model.graph_variables,
        "metadata": graph_model.metadata,
        "event_flow_order": graph_model.event_flow_order,
        "event_flow_titles": graph_model.event_flow_titles,
    }


def sync_graph_code_to_gil(
    graph_code_path: Path,
    target_gil_path: Path,
    graph_id_int: int = 1073741825,
    create_backup: bool = True,
) -> SyncReport:
    """
    将 Graph Code 同步到 GIL 存档

    完整流程：
    1. 编译 Graph Code → GraphModel
    2. GraphModel → GIA 文件
    3. GIA 注入到 GIL 存档

    Args:
        graph_code_path: Graph Code 文件路径
        target_gil_path: 目标 GIL 存档路径
        graph_id_int: 要注入的图 ID
        create_backup: 是否创建备份

    Returns:
        同步报告
    """
    start_time = time.perf_counter()

    try:
        # 1. 编译 Graph Code
        print(f"[1/3] 编译 Graph Code: {graph_code_path}")
        graph_model = compile_graph_code(graph_code_path)
        print(f"      节点数: {len(graph_model.nodes)}, 边数: {len(graph_model.edges)}")

        # 2. 导出为 GIA
        print(f"[2/3] 导出为 GIA...")
        temp_gia_path = target_gil_path.parent / f"_temp_{graph_model.graph_id}.gia"
        export_graph_to_gia(
            graph_model=graph_model,
            output_gia_path=temp_gia_path,
            graph_id_int=graph_id_int,
        )
        print(f"      GIA 文件: {temp_gia_path}")

        # 3. 注入到 GIL
        print(f"[3/3] 注入到 GIL: {target_gil_path}")

        # 创建备份
        backup_path: Optional[Path] = None
        if create_backup:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = target_gil_path.parent / f"{target_gil_path.stem}_backup_{timestamp}.gil"
            shutil.copy2(target_gil_path, backup_path)
            print(f"      备份: {backup_path}")

        # 执行注入
        inject_report = inject_gia_into_gil_node_graph(
            source_gia_file=str(temp_gia_path),
            target_gil_file=str(target_gil_path),
            output_gil_file=str(target_gil_path),  # 原地修改
            graph_id_int=graph_id_int,
            allow_overwrite_non_empty=True,  # 允许覆盖非空图
        )

        # 清理临时文件
        temp_gia_path.unlink(missing_ok=True)

        duration_ms = (time.perf_counter() - start_time) * 1000

        return SyncReport(
            success=True,
            message=f"同步成功: {graph_model.graph_name} ({len(graph_model.nodes)} 节点, {len(graph_model.edges)} 边)",
            graph_code_path=graph_code_path,
            target_gil_path=target_gil_path,
            backup_path=backup_path,
            inject_report=inject_report,
            duration_ms=duration_ms,
        )

    except Exception as e:
        duration_ms = (time.perf_counter() - start_time) * 1000
        return SyncReport(
            success=False,
            message=f"同步失败: {type(e).__name__}: {e}",
            graph_code_path=graph_code_path,
            target_gil_path=target_gil_path,
            duration_ms=duration_ms,
        )


def main():
    """CLI 入口"""
    import argparse

    parser = argparse.ArgumentParser(description="Graph Code → GIL 存档同步工具")
    parser.add_argument(
        "--graph-code",
        "-g",
        type=Path,
        required=True,
        help="Graph Code Python 文件路径",
    )
    parser.add_argument(
        "--target-gil",
        "-t",
        type=Path,
        default=None,
        help="目标 GIL 存档路径（默认自动查找最新存档）",
    )
    parser.add_argument(
        "--graph-id",
        "-i",
        type=int,
        default=1073741825,
        help="注入的图 ID（默认 1073741825 = 0x40000001）",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="不创建备份",
    )

    args = parser.parse_args()

    # 设置工作区
    settings.set_config_path(PROJECT_ROOT)
    settings.load()

    # 确定目标 GIL
    target_gil = args.target_gil
    if target_gil is None:
        from tools.live_sync import find_latest_gil_save

        target_gil = find_latest_gil_save()
        if target_gil is None:
            print("错误: 未找到 GIL 存档，请手动指定 --target-gil")
            sys.exit(1)
        print(f"自动检测到存档: {target_gil}")

    # 执行同步
    report = sync_graph_code_to_gil(
        graph_code_path=args.graph_code,
        target_gil_path=target_gil,
        graph_id_int=args.graph_id,
        create_backup=not args.no_backup,
    )

    # 输出结果
    print(f"\n{'=' * 50}")
    print(f"状态: {'成功' if report.success else '失败'}")
    print(f"消息: {report.message}")
    print(f"耗时: {report.duration_ms:.1f} ms")
    if report.backup_path:
        print(f"备份: {report.backup_path}")
    print(f"{'=' * 50}")

    sys.exit(0 if report.success else 1)


if __name__ == "__main__":
    main()
