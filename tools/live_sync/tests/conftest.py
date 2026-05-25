# -*- coding: utf-8 -*-
"""Pytest 配置文件 - 确保项目根目录在 sys.path 中

这个文件会在 pytest 收集测试时自动执行，确保所有测试都能正确导入项目模块。
"""
from __future__ import annotations

import sys
from pathlib import Path

# 计算项目根目录（当前文件的上上级目录）
PROJECT_ROOT = Path(__file__).resolve().parents[3]
PROJECT_ROOT_STR = str(PROJECT_ROOT)

# 确保项目根目录在 sys.path 的最前面
if PROJECT_ROOT_STR not in sys.path:
    sys.path.insert(0, PROJECT_ROOT_STR)

# 同时确保 tools/live_sync 目录也在路径中（用于导入 tools.live_sync 模块）
TOOLS_LIVE_SYNC = PROJECT_ROOT / "tools" / "live_sync"
TOOLS_LIVE_SYNC_STR = str(TOOLS_LIVE_SYNC)
if TOOLS_LIVE_SYNC_STR not in sys.path:
    sys.path.insert(0, TOOLS_LIVE_SYNC_STR)


# ── 全局 fixture 注册表（供自定义测试运行器使用）──────────────
GLOBAL_FIXTURES: dict = {}

def register_fixture(name: str, func):
    """将 fixture 注册到全局注册表，供 FixtureManager 发现"""
    GLOBAL_FIXTURES[name] = func


# 创建一个最小的 pytest mock
class _MockPytest:
    @staticmethod
    def fixture(*args, **kwargs):
        """Mock fixture装饰器 - 与 run_tests.py 的 fixture 检测兼容"""
        def decorator(func):
            func._pytestfixturefunction = True
            register_fixture(func.__name__, func)
            return func
        if args and callable(args[0]):
            return decorator(args[0])
        return decorator

    class mark:
        @staticmethod
        def skip(*args, **kwargs):
            def decorator(func):
                return func
            return decorator

    @staticmethod
    def raises(expected_exception, *args, **kwargs):
        class RaisesContext:
            def __enter__(self):
                return self
            def __exit__(self, exc_type, exc_val, exc_tb):
                if exc_type is None:
                    raise AssertionError(f"Expected exception {expected_exception} not raised")
                if not issubclass(exc_type, expected_exception):
                    return False
                return True
        return RaisesContext()


# 如果 pytest 不可用则注册 mock（同时绑定到局部命名空间）
try:
    import pytest as _pytest_real
    pytest = _pytest_real
except ImportError:
    _mock_pytest = _MockPytest()
    sys.modules['pytest'] = _mock_pytest
    pytest = _mock_pytest   # 绑定到局部命名空间，供后续代码使用


# ── 标准 pytest 内置 fixture（自定义运行器需要手动实现）───────

_tmp_path_counter = [0]

@pytest.fixture
def tmp_path():
    """Mock pytest 内置 tmp_path fixture - 提供临时目录路径"""
    import tempfile, os
    _tmp_path_counter[0] += 1
    base = tempfile.gettempdir()
    path = Path(base) / f"test_run_{os.getpid()}_{_tmp_path_counter[0]}"
    path.mkdir(parents=True, exist_ok=True)
    return path
