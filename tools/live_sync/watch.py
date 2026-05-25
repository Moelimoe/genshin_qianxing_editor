# -*- coding: utf-8 -*-
"""
文件监控 + 自动同步工具

监控 Graph Code 文件变化，自动触发同步到 GIL 存档
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional, Callable

# 项目路径设置
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.configs.settings import settings

from tools.live_sync import find_latest_gil_save
from tools.live_sync.sync import sync_graph_code_to_gil, SyncReport


class GraphCodeWatcher:
    """Graph Code 文件变化监控器"""

    def __init__(
        self,
        graph_code_path: Path,
        target_gil_path: Path,
        graph_id_int: int = 1073741825,
        debounce_ms: float = 500.0,
        on_sync: Optional[Callable[[SyncReport], None]] = None,
    ):
        """
        初始化监控器

        Args:
            graph_code_path: 要监控的 Graph Code 文件路径
            target_gil_path: 目标 GIL 存档路径
            graph_id_int: 注入的图 ID
            debounce_ms: 防抖时间（毫秒）
            on_sync: 同步完成后的回调函数
        """
        self.graph_code_path = graph_code_path.resolve()
        self.target_gil_path = target_gil_path.resolve()
        self.graph_id_int = graph_id_int
        self.debounce_seconds = debounce_ms / 1000.0
        self.on_sync = on_sync

        self._last_mtime: float = 0.0
        self._last_sync_time: float = 0.0
        self._running: bool = False

    def start(self) -> None:
        """启动监控循环（阻塞）"""
        if not self.graph_code_path.exists():
            raise FileNotFoundError(f"Graph Code 文件不存在: {self.graph_code_path}")
        if not self.target_gil_path.exists():
            raise FileNotFoundError(f"GIL 存档不存在: {self.target_gil_path}")

        self._last_mtime = self.graph_code_path.stat().st_mtime
        self._running = True

        print(f"开始监控: {self.graph_code_path}")
        print(f"目标存档: {self.target_gil_path}")
        print(f"图 ID: {self.graph_id_int} (0x{self.graph_id_int:08X})")
        print(f"防抖: {self.debounce_seconds * 1000:.0f} ms")
        print("\n按 Ctrl+C 停止监控\n")

        try:
            while self._running:
                self._check_and_sync()
                time.sleep(0.1)  # 100ms 轮询间隔
        except KeyboardInterrupt:
            print("\n监控已停止")
            self._running = False

    def stop(self) -> None:
        """停止监控"""
        self._running = False

    def _check_and_sync(self) -> None:
        """检查文件变化并同步"""
        try:
            current_mtime = self.graph_code_path.stat().st_mtime
        except OSError:
            return

        # 检查是否有变化
        if current_mtime <= self._last_mtime:
            return

        # 防抖：距离上次同步时间太短则跳过
        now = time.time()
        if now - self._last_sync_time < self.debounce_seconds:
            return

        # 文件有变化，触发同步
        print(f"\n检测到文件变化: {self.graph_code_path.name}")
        print(f"修改时间: {time.ctime(current_mtime)}")

        self._last_mtime = current_mtime
        self._last_sync_time = now

        # 执行同步
        report = sync_graph_code_to_gil(
            graph_code_path=self.graph_code_path,
            target_gil_path=self.target_gil_path,
            graph_id_int=self.graph_id_int,
            create_backup=True,
        )

        # 回调
        if self.on_sync:
            self.on_sync(report)

        # 输出结果
        status = "成功" if report.success else "失败"
        print(f"同步{status}: {report.message} ({report.duration_ms:.1f} ms)")


def main():
    """CLI 入口"""
    import argparse

    parser = argparse.ArgumentParser(description="Graph Code 文件监控 + 自动同步")
    parser.add_argument(
        "--graph-code",
        "-g",
        type=Path,
        required=True,
        help="要监控的 Graph Code 文件路径",
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
        "--debounce",
        "-d",
        type=float,
        default=500.0,
        help="防抖时间（毫秒，默认 500）",
    )

    args = parser.parse_args()

    # 设置工作区
    settings.set_config_path(PROJECT_ROOT)
    settings.load()

    # 确定目标 GIL
    target_gil = args.target_gil
    if target_gil is None:
        target_gil = find_latest_gil_save()
        if target_gil is None:
            print("错误: 未找到 GIL 存档，请手动指定 --target-gil")
            sys.exit(1)
        print(f"自动检测到存档: {target_gil}")

    # 创建监控器
    watcher = GraphCodeWatcher(
        graph_code_path=args.graph_code,
        target_gil_path=target_gil,
        graph_id_int=args.graph_id,
        debounce_ms=args.debounce,
    )

    # 启动监控
    try:
        watcher.start()
    except FileNotFoundError as e:
        print(f"错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
