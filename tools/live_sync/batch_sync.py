# -*- coding: utf-8 -*-
"""
批量同步工具：单个项目多图同步到 GIL 存档

使用场景：
- 一个项目包含多个 Graph Code 文件（如多个事件流）
- 需要一次性全部同步到同一个 GIL 存档的不同图 ID 槽位

约定：
- 项目目录下所有 *.graph.py 文件会被识别为节点图
- 文件名格式：{图名}.graph.py
- 图 ID 自动分配（从 base_graph_id 开始递增）
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Optional, Tuple

# 项目路径设置
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.configs.settings import settings

from tools.live_sync.sync_safe import (
    sync_to_working_copy,
    apply_working_copy,
    SafeSyncReport,
)
from tools.live_sync.account_selector import (
    list_all_accounts,
    select_account_interactive,
    select_save_file_interactive,
    confirm_operation,
    create_working_copy,
    apply_changes_safely,
)


@dataclass
class BatchSyncReport:
    """批量同步报告"""

    success: bool
    message: str
    project_path: Path
    target_gil_path: Path
    total_files: int
    success_count: int
    failed_count: int
    skipped_count: int
    reports: List[Tuple[Path, SafeSyncReport]] = field(default_factory=list)
    duration_ms: float = 0.0
    final_working_copy: Optional[Path] = None


def find_graph_code_files(project_path: Path) -> List[Path]:
    """
    查找项目中的所有 Graph Code 文件

    识别规则（按优先级）：
    1. *.graph.py 文件（推荐命名）
    2. 如果没有 .graph.py，则找包含 @graph 装饰器或 Graph 类定义的 .py 文件

    Args:
        project_path: 项目目录路径

    Returns:
        Graph Code 文件路径列表（按文件名排序）
    """
    if not project_path.exists():
        return []

    # 优先查找 *.graph.py
    graph_files = sorted(project_path.rglob("*.graph.py"))
    if graph_files:
        return graph_files

    # 回退：查找可能包含节点图的 .py 文件
    candidates: List[Path] = []
    for py_file in project_path.rglob("*.py"):
        # 跳过测试文件和 __init__.py
        if py_file.name.startswith("test_") or py_file.name == "__init__.py":
            continue
        # 简单检查文件内容是否包含节点图相关关键字
        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore")
            if any(kw in content for kw in ["class", "def on_", "@graph", "GraphModel"]):
                candidates.append(py_file)
        except Exception:
            pass

    return sorted(candidates)


def assign_graph_ids(
    files: List[Path],
    base_graph_id: int = 1073741825,  # 0x40000001
) -> Dict[Path, int]:
    """
    为每个 Graph Code 文件分配图 ID

    Args:
        files: Graph Code 文件列表
        base_graph_id: 起始图 ID

    Returns:
        文件路径到图 ID 的映射
    """
    return {file: base_graph_id + i for i, file in enumerate(files)}


def batch_sync_project(
    project_path: Path,
    target_gil_path: Path,
    base_graph_id: int = 1073741825,
    create_backup: bool = True,
) -> BatchSyncReport:
    """
    批量同步项目中的所有 Graph Code 到 GIL 存档

    流程：
    1. 查找项目中的所有 Graph Code 文件
    2. 为每个文件分配图 ID
    3. 创建原始存档的工作副本
    4. 逐个同步到工作副本（使用各自的图 ID）
    5. 询问是否应用到原始存档

    Args:
        project_path: 项目目录路径
        target_gil_path: 目标 GIL 存档路径
        base_graph_id: 起始图 ID
        create_backup: 是否创建备份

    Returns:
        批量同步报告
    """
    start_time = time.perf_counter()

    # 1. 查找 Graph Code 文件
    graph_files = find_graph_code_files(project_path)
    if not graph_files:
        return BatchSyncReport(
            success=False,
            message=f"在项目 {project_path} 中未找到 Graph Code 文件",
            project_path=project_path,
            target_gil_path=target_gil_path,
            total_files=0,
            success_count=0,
            failed_count=0,
            skipped_count=0,
        )

    print(f"找到 {len(graph_files)} 个 Graph Code 文件:")
    for i, f in enumerate(graph_files, 1):
        print(f"  {i}. {f.relative_to(project_path)}")

    # 2. 分配图 ID
    graph_id_map = assign_graph_ids(graph_files, base_graph_id)
    print(f"\n图 ID 分配（起始: 0x{base_graph_id:08X}）:")
    for f, gid in graph_id_map.items():
        print(f"  {f.stem}: 0x{gid:08X} ({gid})")

    # 3. 创建工作副本
    print(f"\n创建工作副本...")
    working_copy = create_working_copy(target_gil_path, suffix="_batch")
    print(f"  副本: {working_copy}")

    # 4. 逐个同步
    reports: List[Tuple[Path, SafeSyncReport]] = []
    success_count = 0
    failed_count = 0

    print(f"\n开始批量同步...")
    print("=" * 60)

    for i, graph_file in enumerate(graph_files, 1):
        graph_id = graph_id_map[graph_file]
        print(f"\n[{i}/{len(graph_files)}] {graph_file.name}")
        print(f"      图 ID: 0x{graph_id:08X}")

        # 同步到工作副本（注意：这里传入 working_copy 作为 original，实际修改的是副本）
        report = sync_to_working_copy(
            graph_code_path=graph_file,
            original_gil_path=working_copy,
            graph_id_int=graph_id,
        )

        reports.append((graph_file, report))

        if report.success:
            success_count += 1
            print(f"      ✅ 成功")
        else:
            failed_count += 1
            print(f"      ❌ 失败: {report.message}")

    print("\n" + "=" * 60)

    # 5. 汇总
    duration_ms = (time.perf_counter() - start_time) * 1000
    skipped_count = len(graph_files) - success_count - failed_count

    success = failed_count == 0 and success_count > 0
    message = f"批量同步完成: {success_count} 成功, {failed_count} 失败, {skipped_count} 跳过"

    return BatchSyncReport(
        success=success,
        message=message,
        project_path=project_path,
        target_gil_path=target_gil_path,
        total_files=len(graph_files),
        success_count=success_count,
        failed_count=failed_count,
        skipped_count=skipped_count,
        reports=reports,
        duration_ms=duration_ms,
        final_working_copy=working_copy,
    )


def interactive_batch_sync() -> BatchSyncReport:
    """
    交互式批量同步

    完整流程：
    1. 输入项目路径
    2. 选择账号和存档
    3. 批量同步到工作副本
    4. 询问是否应用到原始存档

    Returns:
        批量同步报告
    """
    print("=" * 60)
    print("Graph Code 批量同步工具")
    print("=" * 60)

    # 1. 输入项目路径
    project_input = input("\n请输入项目目录路径（包含 .graph.py 文件）: ").strip()
    project_path = Path(project_input).expanduser().resolve()

    if not project_path.exists():
        print(f"错误: 目录不存在: {project_path}")
        return BatchSyncReport(
            success=False,
            message="目录不存在",
            project_path=project_path,
            target_gil_path=Path(),
            total_files=0,
            success_count=0,
            failed_count=0,
            skipped_count=0,
        )

    # 2. 选择账号和存档
    accounts = list_all_accounts()
    if not accounts:
        print("错误: 未找到任何账号存档")
        return BatchSyncReport(
            success=False,
            message="未找到账号存档",
            project_path=project_path,
            target_gil_path=Path(),
            total_files=0,
            success_count=0,
            failed_count=0,
            skipped_count=0,
        )

    selected_account = select_account_interactive()
    if selected_account is None:
        return BatchSyncReport(
            success=False,
            message="用户取消",
            project_path=project_path,
            target_gil_path=Path(),
            total_files=0,
            success_count=0,
            failed_count=0,
            skipped_count=0,
        )

    selected_save = select_save_file_interactive(selected_account)
    if selected_save is None:
        return BatchSyncReport(
            success=False,
            message="用户取消",
            project_path=project_path,
            target_gil_path=Path(),
            total_files=0,
            success_count=0,
            failed_count=0,
            skipped_count=0,
        )

    # 3. 批量同步
    print(f"\n开始批量同步...")
    report = batch_sync_project(
        project_path=project_path,
        target_gil_path=selected_save,
    )

    if not report.success:
        print(f"\n批量同步失败: {report.message}")
        return report

    print(f"\n✅ {report.message}")
    print(f"   工作副本: {report.final_working_copy}")

    # 4. 询问是否应用到原始存档
    print("\n" + "-" * 60)
    print("批量同步完成！您可以：")
    print("  1. 先在千星沙箱中测试工作副本")
    print("  2. 确认无误后再应用到原始存档")
    print("-" * 60)

    choice = input("\n是否立即应用到原始存档？([y]es/[n]o/[t]est): ").strip().lower()

    if choice == "y" or choice == "yes":
        if report.final_working_copy and selected_save:
            success = apply_working_copy(report.final_working_copy, selected_save)
            if success:
                report.message += "（已应用到原始存档）"
            else:
                report.message += "（应用到原始存档失败）"
        else:
            print("错误: 缺少工作副本路径")
    elif choice == "t" or choice == "test":
        print(f"\n工作副本路径: {report.final_working_copy}")
        print("请在千星沙箱中使用'导入'功能测试此文件")
    else:
        print("\n已跳过应用步骤")
        print(f"工作副本保留在: {report.final_working_copy}")

    return report


def main():
    """CLI 入口"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Graph Code 批量同步工具（单个项目多图）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用流程:
  1. 在项目目录中创建多个 .graph.py 文件
  2. 运行此工具：python -m tools.live_sync.batch_sync -p /path/to/project
  3. 选择账号和存档
  4. 工具自动为每个文件分配图 ID 并同步
  5. 选择：测试 / 立即应用 / 稍后处理

文件命名约定:
  - 推荐: {图名}.graph.py
  - 例如: player_movement.graph.py, enemy_ai.graph.py

图 ID 分配:
  - 从 base_graph_id (默认 0x40000001) 开始递增
  - 每个文件分配一个唯一的图 ID
  - 后续同步保持相同的图 ID（覆盖更新）
        """,
    )
    parser.add_argument(
        "--project",
        "-p",
        type=Path,
        default=None,
        help="项目目录路径（默认交互式输入）",
    )
    parser.add_argument(
        "--target-gil",
        "-t",
        type=Path,
        default=None,
        help="目标 GIL 存档路径（默认交互式选择）",
    )
    parser.add_argument(
        "--base-graph-id",
        "-b",
        type=int,
        default=1073741825,
        help="起始图 ID（默认 1073741825 = 0x40000001）",
    )

    args = parser.parse_args()

    # 设置工作区
    settings.set_config_path(PROJECT_ROOT)
    settings.load()

    # 交互式模式
    if args.project is None:
        report = interactive_batch_sync()
    else:
        # 命令行模式
        if args.target_gil is None:
            print("错误: 命令行模式必须指定 --target-gil")
            sys.exit(1)

        report = batch_sync_project(
            project_path=args.project,
            target_gil_path=args.target_gil,
            base_graph_id=args.base_graph_id,
        )

        # 输出结果
        print(f"\n{'=' * 60}")
        print(f"状态: {'成功' if report.success else '失败'}")
        print(f"消息: {report.message}")
        print(f"总文件: {report.total_files}")
        print(f"成功: {report.success_count}")
        print(f"失败: {report.failed_count}")
        print(f"跳过: {report.skipped_count}")
        print(f"耗时: {report.duration_ms:.1f} ms")
        if report.final_working_copy:
            print(f"工作副本: {report.final_working_copy}")
        print(f"{'=' * 60}")

    sys.exit(0 if report.success else 1)


if __name__ == "__main__":
    main()
