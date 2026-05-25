# -*- coding: utf-8 -*-
"""
Graph Code → GIL 存档同步工具（安全版本）

安全原则：
1. 默认使用工作副本模式（在临时目录操作，确认后再应用）
2. 每次修改原始存档前必须输入 "YES" 确认
3. 自动创建备份
4. 支持交互式选择账号和存档
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

from engine.configs.settings import settings

from tools.live_sync.sync import (
    compile_graph_code,
    export_graph_to_gia,
    SyncReport as BaseSyncReport,
)
from tools.live_sync.account_selector import (
    list_all_accounts,
    select_account_interactive,
    select_save_file_interactive,
    confirm_operation,
    create_working_copy,
    apply_changes_safely,
)

# UGC 文件工具
from private_extensions.ugc_file_tools.save_patchers.gil_node_graph_injector import (
    inject_gia_into_gil_node_graph,
    GilNodeGraphInjectReport,
)


@dataclass
class SafeSyncReport:
    """安全同步报告"""

    success: bool
    message: str
    graph_code_path: Path
    original_gil_path: Optional[Path] = None
    working_copy_path: Optional[Path] = None
    backup_path: Optional[Path] = None
    inject_report: Optional[GilNodeGraphInjectReport] = None
    duration_ms: float = 0.0
    applied_to_original: bool = False  # 是否已应用到原始存档


def sync_to_working_copy(
    graph_code_path: Path,
    original_gil_path: Path,
    graph_id_int: int = 1073741825,
) -> SafeSyncReport:
    """
    同步到工作副本（不修改原始存档）

    Args:
        graph_code_path: Graph Code 文件路径
        original_gil_path: 原始 GIL 存档路径（用于创建副本）
        graph_id_int: 注入的图 ID

    Returns:
        同步报告（包含工作副本路径）
    """
    start_time = time.perf_counter()

    try:
        # 1. 创建安全的工作副本
        print(f"[0/3] 创建工作副本...")
        working_copy = create_working_copy(original_gil_path, suffix="_working")
        print(f"      副本: {working_copy}")

        # 2. 编译 Graph Code
        print(f"[1/3] 编译 Graph Code: {graph_code_path}")
        from engine.graph.graph_code_parser import GraphCodeParser

        parser = GraphCodeParser()
        graph_model = parser.parse_file(str(graph_code_path))
        print(f"      节点数: {len(graph_model.nodes)}, 边数: {len(graph_model.edges)}")

        # 3. 导出为 GIA
        print(f"[2/3] 导出为 GIA...")
        temp_gia_path = working_copy.parent / f"_temp_{graph_model.graph_id}.gia"
        export_graph_to_gia(
            graph_model=graph_model,
            output_gia_path=temp_gia_path,
            graph_id_int=graph_id_int,
        )
        print(f"      GIA 文件: {temp_gia_path}")

        # 4. 注入到工作副本
        print(f"[3/3] 注入到工作副本...")
        inject_report = inject_gia_into_gil_node_graph(
            source_gia_file=str(temp_gia_path),
            target_gil_file=str(working_copy),
            output_gil_file=str(working_copy),  # 原地修改副本
            graph_id_int=graph_id_int,
            allow_overwrite_non_empty=True,
        )

        # 清理临时文件
        temp_gia_path.unlink(missing_ok=True)

        duration_ms = (time.perf_counter() - start_time) * 1000

        return SafeSyncReport(
            success=True,
            message=f"已生成工作副本: {graph_model.graph_name} ({len(graph_model.nodes)} 节点, {len(graph_model.edges)} 边)",
            graph_code_path=graph_code_path,
            original_gil_path=original_gil_path,
            working_copy_path=working_copy,
            inject_report=inject_report,
            duration_ms=duration_ms,
            applied_to_original=False,
        )

    except Exception as e:
        duration_ms = (time.perf_counter() - start_time) * 1000
        return SafeSyncReport(
            success=False,
            message=f"同步失败: {type(e).__name__}: {e}",
            graph_code_path=graph_code_path,
            original_gil_path=original_gil_path,
            duration_ms=duration_ms,
        )


def apply_working_copy(
    working_copy_path: Path,
    original_gil_path: Path,
) -> bool:
    """
    将工作副本应用到原始存档（带安全确认）

    Args:
        working_copy_path: 工作副本路径
        original_gil_path: 原始存档路径

    Returns:
        是否成功应用
    """
    # 安全确认
    if not confirm_operation(original_gil_path, "修改"):
        print("已取消应用修改")
        return False

    # 应用修改
    return apply_changes_safely(working_copy_path, original_gil_path)


def interactive_sync(
    graph_code_path: Path,
    graph_id_int: int = 1073741825,
) -> SafeSyncReport:
    """
    交互式同步（完整流程：选择账号 → 选择存档 → 生成副本 → 确认应用）

    Args:
        graph_code_path: Graph Code 文件路径
        graph_id_int: 注入的图 ID

    Returns:
        同步报告
    """
    print("=" * 60)
    print("Graph Code → GIL 存档同步工具（安全模式）")
    print("=" * 60)

    # 1. 选择账号
    accounts = list_all_accounts()
    if not accounts:
        print("错误: 未找到任何账号存档")
        print("请确认千星沙箱已保存过关卡")
        return SafeSyncReport(
            success=False,
            message="未找到账号存档",
            graph_code_path=graph_code_path,
        )

    print(f"\n找到 {len(accounts)} 个账号")
    selected_account = select_account_interactive()
    if selected_account is None:
        return SafeSyncReport(
            success=False,
            message="用户取消",
            graph_code_path=graph_code_path,
        )

    # 2. 选择存档
    selected_save = select_save_file_interactive(selected_account)
    if selected_save is None:
        return SafeSyncReport(
            success=False,
            message="用户取消",
            graph_code_path=graph_code_path,
        )

    # 3. 同步到工作副本
    print(f"\n正在生成工作副本...")
    report = sync_to_working_copy(
        graph_code_path=graph_code_path,
        original_gil_path=selected_save,
        graph_id_int=graph_id_int,
    )

    if not report.success:
        print(f"同步失败: {report.message}")
        return report

    print(f"\n✅ {report.message}")
    print(f"   工作副本: {report.working_copy_path}")

    # 4. 询问是否应用到原始存档
    print("\n" + "-" * 60)
    print("工作副本已生成，您可以：")
    print("  1. 先在千星沙箱中测试工作副本（通过导入功能）")
    print("  2. 确认无误后再应用到原始存档")
    print("-" * 60)

    choice = input("\n是否立即应用到原始存档？([y]es/[n]o/[t]est 先测试): ").strip().lower()

    if choice == "y" or choice == "yes":
        if report.working_copy_path and report.original_gil_path:
            success = apply_working_copy(
                report.working_copy_path,
                report.original_gil_path,
            )
            report.applied_to_original = success
            if success:
                report.message += "（已应用到原始存档）"
            else:
                report.message += "（应用到原始存档失败）"
        else:
            print("错误: 缺少工作副本路径")
    elif choice == "t" or choice == "test":
        print(f"\n工作副本路径: {report.working_copy_path}")
        print("请在千星沙箱中使用'导入'功能测试此文件")
        print("测试完成后再运行此工具选择'应用'")
    else:
        print("\n已跳过应用步骤")
        print(f"工作副本保留在: {report.working_copy_path}")
        print("您可以稍后手动应用或删除")

    return report


def main():
    """CLI 入口"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Graph Code → GIL 存档同步工具（安全模式）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用流程:
  1. 运行此工具，交互式选择账号和存档
  2. 工具生成工作副本（不修改原始存档）
  3. 您可以选择：
     - 先测试工作副本（推荐）
     - 直接应用到原始存档
     - 稍后手动应用

安全特性:
  - 默认不修改原始存档
  - 修改前必须输入 "YES" 确认
  - 自动创建时间戳备份
  - 所有操作可撤销
        """,
    )
    parser.add_argument(
        "--graph-code",
        "-g",
        type=Path,
        required=True,
        help="Graph Code Python 文件路径",
    )
    parser.add_argument(
        "--graph-id",
        "-i",
        type=int,
        default=1073741825,
        help="注入的图 ID（默认 1073741825 = 0x40000001）",
    )
    parser.add_argument(
        "--apply",
        "-a",
        type=Path,
        default=None,
        help="直接应用指定的工作副本到原始存档（跳过生成步骤）",
    )
    parser.add_argument(
        "--original",
        "-o",
        type=Path,
        default=None,
        help="原始存档路径（与 --apply 配合使用）",
    )

    args = parser.parse_args()

    # 设置工作区
    settings.set_config_path(PROJECT_ROOT)
    settings.load()

    # 模式：直接应用工作副本
    if args.apply and args.original:
        if not args.apply.exists():
            print(f"错误: 工作副本不存在: {args.apply}")
            sys.exit(1)
        if not args.original.exists():
            print(f"错误: 原始存档不存在: {args.original}")
            sys.exit(1)

        success = apply_working_copy(args.apply, args.original)
        sys.exit(0 if success else 1)

    # 模式：交互式同步
    report = interactive_sync(
        graph_code_path=args.graph_code,
        graph_id_int=args.graph_id,
    )

    # 输出结果
    print(f"\n{'=' * 60}")
    print(f"状态: {'成功' if report.success else '失败'}")
    print(f"消息: {report.message}")
    print(f"耗时: {report.duration_ms:.1f} ms")
    if report.working_copy_path:
        print(f"工作副本: {report.working_copy_path}")
    if report.backup_path:
        print(f"备份: {report.backup_path}")
    print(f"{'=' * 60}")

    sys.exit(0 if report.success else 1)


if __name__ == "__main__":
    main()
