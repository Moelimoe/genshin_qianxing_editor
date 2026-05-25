# -*- coding: utf-8 -*-
"""简易测试运行器 - 绕过pytest环境问题

用法:
    python tools/live_sync/tests/run_tests.py [测试模块名]

示例:
    python tools/live_sync/tests/run_tests.py test_node_catalog
    python tools/live_sync/tests/run_tests.py test_level_builder
    python tools/live_sync/tests/run_tests.py all
"""
from __future__ import annotations

import sys
import traceback
import inspect
from pathlib import Path
from typing import List, Tuple, Dict, Any, Callable

# 确保项目根目录在路径中
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 确保 tools/live_sync 在路径中
TOOLS_LIVE_SYNC = PROJECT_ROOT / "tools" / "live_sync"
if str(TOOLS_LIVE_SYNC) not in sys.path:
    sys.path.insert(0, str(TOOLS_LIVE_SYNC))

# 先导入conftest来设置pytest mock
import importlib.util
conftest_path = Path(__file__).parent / "conftest.py"
spec = importlib.util.spec_from_file_location("conftest", conftest_path)
conftest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(conftest)
# 确保 conftest 注册到 sys.modules，后续 import conftest 能找到同一模块
sys.modules['conftest'] = conftest


class FixtureManager:
    """简单的fixture管理器

    行为模拟 pytest 默认的 "function" scope：
    每个测试函数运行前清除所有缓存，确保测试间完全隔离。
    """

    def __init__(self):
        self.fixtures: Dict[str, Callable] = {}
        self._cached: Dict[str, Any] = {}  # 当前缓存

    def register(self, name: str, func: Callable):
        """注册一个 fixture"""
        self.fixtures[name] = func

    def get(self, name: str) -> Any:
        """获取 fixture 值

        每次调用前清除缓存（function scope），确保测试隔离。
        如果缓存为空则创建新实例。
        """
        if name not in self.fixtures:
            raise KeyError(
                f"Fixture '{name}' not found "
                f"(available: {list(self.fixtures.keys())})"
            )

        # function scope: 每次 get 都重新创建（确保测试隔离）
        sig = inspect.signature(self.fixtures[name])
        kwargs = {}
        for param_name in sig.parameters:
            if param_name == 'self':
                continue
            if param_name in self.fixtures:
                kwargs[param_name] = self.get(param_name)
            else:
                raise KeyError(
                    f"Fixture '{name}' depends on unknown fixture '{param_name}'"
                )

        return self.fixtures[name](**kwargs)

    def clear_cache(self):
        """清除缓存（每个测试函数后调用，确保下次获取全新实例）"""
        self._cached.clear()


def run_test_class(cls, fixture_manager: FixtureManager) -> Tuple[int, int, List[str]]:
    """运行一个测试类中的所有测试方法
    
    Returns:
        (passed_count, failed_count, error_messages)
    """
    passed = 0
    failed = 0
    errors = []
    
    # 获取测试方法的签名
    test_methods = []
    for method_name in dir(cls):
        if method_name.startswith('test_'):
            method = getattr(cls, method_name)
            if callable(method):
                test_methods.append((method_name, method))
    
    if not test_methods:
        return 0, 0, []
    
    # 创建实例
    try:
        instance = cls()
    except Exception as e:
        print(f"  ✗ 创建实例失败: {e}")
        return 0, len(test_methods), [f"{cls.__name__}.__init__: {e}"]
    
    for method_name, method in test_methods:
        try:
            # 获取方法签名
            sig = inspect.signature(method)
            kwargs = {}
            
            # 为每个参数查找fixture
            for param_name in sig.parameters:
                if param_name == 'self':
                    continue
                try:
                    kwargs[param_name] = fixture_manager.get(param_name)
                except KeyError:
                    raise RuntimeError(f"Fixture '{param_name}' not found for {cls.__name__}.{method_name}")
            
            # 调用 setup 如果存在
            if hasattr(instance, 'setup_method'):
                instance.setup_method()
            elif hasattr(instance, 'setup'):
                instance.setup()
            
            # 运行测试
            method(instance, **kwargs)
            passed += 1
            print(f"  ✓ {method_name}")
            
        except Exception as e:
            failed += 1
            error_msg = f"{cls.__name__}.{method_name}: {e}"
            errors.append(error_msg)
            print(f"  ✗ {method_name}")
            print(f"    Error: {e}")
            import traceback as tb_module
            tb_module.print_exc()
    
    return passed, failed, errors


def run_module_tests(module_name: str) -> Tuple[int, int, List[str]]:
    """运行一个测试模块中的所有测试类"""
    import importlib
    
    print(f"\n{'='*60}")
    print(f"运行测试模块: {module_name}")
    print('='*60)
    
    try:
        module = importlib.import_module(module_name)
    except Exception as e:
        print(f"导入模块失败: {e}")
        import traceback
        traceback.print_exc()
        return 0, 0, [f"导入失败: {e}"]
    
    # 收集 fixtures（从测试模块）
    fixture_manager = FixtureManager()
    for name, obj in inspect.getmembers(module):
        if callable(obj) and hasattr(obj, '_pytestfixturefunction'):
            fixture_manager.register(name, obj)

    # 也从 conftest 的 GLOBAL_FIXTURES 加载（内置 fixture 如 tmp_path）
    # conftest 已在上面通过 importlib 导入（名为 'conftest'）
    import conftest as _conftest_module
    if hasattr(_conftest_module, 'GLOBAL_FIXTURES'):
        for name, func in _conftest_module.GLOBAL_FIXTURES.items():
            if name not in fixture_manager.fixtures:
                fixture_manager.register(name, func)
    
    # 查找所有测试类
    test_classes = []
    for name, obj in inspect.getmembers(module):
        if inspect.isclass(obj) and name.startswith('Test'):
            test_classes.append(obj)
    
    print(f"发现 {len(test_classes)} 个测试类")
    
    total_passed = 0
    total_failed = 0
    all_errors = []
    
    for cls in test_classes:
        print(f"\n▶ {cls.__name__}")
        fixture_manager.clear_cache()
        passed, failed, errors = run_test_class(cls, fixture_manager)
        total_passed += passed
        total_failed += failed
        all_errors.extend(errors)
    
    return total_passed, total_failed, all_errors


def main():
    """主函数"""
    # 获取命令行参数
    args = sys.argv[1:] if len(sys.argv) > 1 else ['all']
    
    # 定义所有测试模块
    test_modules = {
        'node_catalog': 'test_node_catalog',
        'level_builder': 'test_level_builder',
        'validator': 'test_validator',
        'level_exporter': 'test_level_exporter',
        'gia_generation': 'test_gia_generation',
    }
    
    # 确定要运行的模块
    if 'all' in args:
        modules_to_run = list(test_modules.values())
    else:
        modules_to_run = []
        for arg in args:
            if arg in test_modules:
                modules_to_run.append(test_modules[arg])
            elif arg in test_modules.values():
                modules_to_run.append(arg)
            else:
                print(f"未知测试模块: {arg}")
                print(f"可用模块: {', '.join(test_modules.keys())}")
                return 1
    
    # 运行所有测试
    grand_total_passed = 0
    grand_total_failed = 0
    all_errors = []
    
    for module in modules_to_run:
        passed, failed, errors = run_module_tests(module)
        grand_total_passed += passed
        grand_total_failed += failed
        all_errors.extend(errors)
    
    # 打印总结
    print(f"\n{'='*60}")
    print("测试总结")
    print('='*60)
    print(f"通过: {grand_total_passed}")
    print(f"失败: {grand_total_failed}")
    print(f"总计: {grand_total_passed + grand_total_failed}")
    
    if grand_total_failed > 0:
        print(f"\n失败详情 ({len(all_errors)} 个):")
        for i, error in enumerate(all_errors[:10], 1):
            print(f"  {i}. {error}")
        if len(all_errors) > 10:
            print(f"  ... 还有 {len(all_errors) - 10} 个错误")
    
    # 返回退出码
    return 0 if grand_total_failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
