# -*- coding: utf-8 -*-
"""
live_sync: Graph Code 实时同步到千星沙箱存档

功能：
1. 监控 Graph Code 文件变化
2. 自动编译为 GraphModel
3. 生成 GIA 并注入到 GIL 存档
4. 提供手动刷新 CLI 和 API

使用：
    # 启动监控
    python -m tools.live_sync.watch --target-gil "path/to/save.gil"
    
    # 手动刷新
    python -m tools.live_sync.sync --graph-code "path/to/graph.py" --target-gil "path/to/save.gil"
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional


def get_default_beyond_local_save_dir() -> Path:
    """获取千星沙箱默认存档目录"""
    return (
        Path.home()
        / "AppData"
        / "LocalLow"
        / "miHoYo"
        / "原神"
        / "BeyondLocal"
        / "Beyond_Local_Save_Level"
    )


def find_latest_gil_save() -> Optional[Path]:
    """在 BeyondLocal 中查找最新的 .gil 存档文件"""
    save_dir = get_default_beyond_local_save_dir()
    if not save_dir.exists():
        return None
    
    gil_files = list(save_dir.rglob("*.gil"))
    if not gil_files:
        return None
    
    # 按修改时间排序，返回最新的
    return max(gil_files, key=lambda p: p.stat().st_mtime)


__all__ = ["get_default_beyond_local_save_dir", "find_latest_gil_save"]
