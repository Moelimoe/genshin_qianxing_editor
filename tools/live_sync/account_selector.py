# -*- coding: utf-8 -*-
"""
千星沙箱账号/存档选择器

安全原则：
1. 绝不自动修改原始存档，每次操作前必须用户确认
2. 支持列出所有账号和存档供选择
3. 默认使用"模拟模式"（复制到临时目录操作）
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from private_extensions.ugc_file_tools.beyond_local_maps import (
    get_beyond_local_root_dir,
    GilMapCandidate,
    _iter_gil_files_in_dir,
)


@dataclass
class AccountInfo:
    """账号信息"""

    user_id: str  # 数字目录名
    path: Path  # 账号目录路径
    save_level_dir: Path  # Beyond_Local_Save_Level 路径
    gil_files: List[GilMapCandidate]  # 该账号下的所有存档


@dataclass
class SaveFileInfo:
    """存档文件信息"""

    path: Path
    account_id: str
    mtime: datetime
    size_bytes: int

    @property
    def name(self) -> str:
        return self.path.name


def list_all_accounts() -> List[AccountInfo]:
    """
    列出 BeyondLocal 下的所有账号

    Returns:
        账号信息列表（按用户ID排序）
    """
    root = get_beyond_local_root_dir()
    if not root.exists():
        return []

    accounts: List[AccountInfo] = []
    for item in sorted(root.iterdir(), key=lambda p: p.name):
        if not item.is_dir():
            continue
        # 玩家目录一般是数字
        if not item.name.isdigit():
            continue

        save_dir = item / "Beyond_Local_Save_Level"
        if not save_dir.exists():
            continue

        gil_files = list(_iter_gil_files_in_dir(save_dir))
        accounts.append(
            AccountInfo(
                user_id=item.name,
                path=item,
                save_level_dir=save_dir,
                gil_files=gil_files,
            )
        )

    return accounts


def list_all_save_files() -> List[SaveFileInfo]:
    """
    列出所有账号下的所有存档文件

    Returns:
        存档文件信息列表（按修改时间倒序）
    """
    accounts = list_all_accounts()
    saves: List[SaveFileInfo] = []

    for account in accounts:
        for candidate in account.gil_files:
            stat = candidate.path.stat()
            saves.append(
                SaveFileInfo(
                    path=candidate.path,
                    account_id=account.user_id,
                    mtime=datetime.fromtimestamp(stat.st_mtime),
                    size_bytes=stat.st_size,
                )
            )

    # 按修改时间倒序排列
    saves.sort(key=lambda s: s.mtime, reverse=True)
    return saves


def select_account_interactive() -> Optional[AccountInfo]:
    """
    交互式选择账号

    Returns:
        选中的账号信息，或 None（用户取消）
    """
    accounts = list_all_accounts()

    if not accounts:
        print("错误: 未找到任何账号存档")
        print(f"请确认千星沙箱已保存过关卡，或手动指定存档路径")
        return None

    print("\n检测到以下账号：")
    print("-" * 50)
    for i, account in enumerate(accounts, 1):
        print(f"  {i}. 用户ID: {account.user_id}")
        print(f"     存档数: {len(account.gil_files)}")
        if account.gil_files:
            latest = max(account.gil_files, key=lambda c: c.mtime_ms)
            print(f"     最新存档: {latest.path.name}")
        print()

    while True:
        choice = input(f"请选择账号 (1-{len(accounts)}, 或 q 退出): ").strip()
        if choice.lower() == "q":
            return None
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(accounts):
                return accounts[idx]
            print(f"无效选择，请输入 1-{len(accounts)}")
        except ValueError:
            print("无效输入，请输入数字")


def select_save_file_interactive(account: AccountInfo) -> Optional[Path]:
    """
    交互式选择存档文件

    Args:
        account: 已选中的账号

    Returns:
        选中的存档路径，或 None（用户取消）
    """
    if not account.gil_files:
        print(f"错误: 账号 {account.user_id} 下没有存档文件")
        return None

    # 按修改时间排序
    files = sorted(account.gil_files, key=lambda c: c.mtime_ms, reverse=True)

    print(f"\n账号 {account.user_id} 的存档：")
    print("-" * 70)
    print(f"{'序号':<6}{'文件名':<30}{'修改时间':<20}{'大小':<10}")
    print("-" * 70)

    for i, candidate in enumerate(files[:10], 1):  # 只显示前10个
        path = candidate.path
        stat = path.stat()
        mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%m-%d %H:%M")
        size_kb = stat.st_size / 1024
        print(f"{i:<6}{path.name:<30}{mtime:<20}{size_kb:>8.1f} KB")

    print("-" * 70)

    while True:
        choice = input(f"请选择存档 (1-{min(len(files), 10)}, 或 q 退出): ").strip()
        if choice.lower() == "q":
            return None
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(files):
                return files[idx].path
            print(f"无效选择")
        except ValueError:
            print("无效输入")


def confirm_operation(target_path: Path, operation: str = "修改") -> bool:
    """
    安全确认：操作前要求用户明确确认

    Args:
        target_path: 目标文件路径
        operation: 操作描述

    Returns:
        是否确认执行
    """
    print("\n" + "=" * 60)
    print("⚠️  安全确认")
    print("=" * 60)
    print(f"即将 {operation} 以下文件：")
    print(f"  路径: {target_path}")
    print(f"  账号: {target_path.parent.parent.parent.name}")
    print(f"  大小: {target_path.stat().st_size / 1024:.1f} KB")
    print()
    print("⚠️  警告：")
    print("  - 此操作将直接修改千星沙箱存档")
    print("  - 建议先备份或确保可以重新导出")
    print("  - 修改后需要在千星沙箱中重新打开关卡")
    print("=" * 60)

    # 要求输入完整路径确认
    confirm_text = input(f'请输入 "YES" 确认 {operation}，或其他键取消: ').strip()
    return confirm_text == "YES"


def create_working_copy(original_path: Path, suffix: str = "_working") -> Path:
    """
    创建原始存档的工作副本

    在临时目录中创建副本，所有修改都在副本上进行，
    用户确认后再复制回原始位置。

    Args:
        original_path: 原始存档路径
        suffix: 副本文件名后缀

    Returns:
        副本路径
    """
    # 使用系统临时目录
    temp_dir = Path(os.environ.get("TEMP", "/tmp")) / "genshin_qianxing_editor"
    temp_dir.mkdir(parents=True, exist_ok=True)

    # 创建带时间戳的副本名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    copy_name = f"{original_path.stem}{suffix}_{timestamp}.gil"
    copy_path = temp_dir / copy_name

    shutil.copy2(original_path, copy_path)
    return copy_path


def apply_changes_safely(working_copy: Path, original_path: Path) -> bool:
    """
    安全地应用修改：备份 → 替换

    Args:
        working_copy: 修改后的工作副本
        original_path: 原始存档路径

    Returns:
        是否成功
    """
    if not working_copy.exists():
        print("错误: 工作副本不存在")
        return False

    try:
        # 1. 创建备份
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{original_path.stem}_backup_{timestamp}.gil"
        backup_path = original_path.parent / backup_name
        shutil.copy2(original_path, backup_path)
        print(f"已创建备份: {backup_path.name}")

        # 2. 替换原始文件
        shutil.copy2(working_copy, original_path)
        print(f"已更新: {original_path.name}")

        return True

    except Exception as e:
        print(f"应用修改失败: {e}")
        return False


def main():
    """CLI 测试入口"""
    print("千星沙箱账号/存档扫描工具")
    print("=" * 60)

    # 列出所有账号
    accounts = list_all_accounts()
    print(f"\n找到 {len(accounts)} 个账号")

    for account in accounts:
        print(f"\n账号: {account.user_id}")
        print(f"  路径: {account.path}")
        print(f"  存档数: {len(account.gil_files)}")
        for candidate in account.gil_files[:3]:
            print(f"    - {candidate.path.name}")

    # 交互式选择
    print("\n" + "=" * 60)
    selected_account = select_account_interactive()
    if selected_account is None:
        print("已取消")
        return

    selected_save = select_save_file_interactive(selected_account)
    if selected_save is None:
        print("已取消")
        return

    print(f"\n选中: {selected_save}")

    # 确认
    if confirm_operation(selected_save, "修改"):
        print("已确认，可以执行操作")
    else:
        print("已取消")


if __name__ == "__main__":
    main()
