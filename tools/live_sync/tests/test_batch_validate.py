# -*- coding: utf-8 -*-
"""批量验证所有内置节点的 GIA 生成

阶段1: 为每个内置节点生成单节点 GIA，验证结构正确性
阶段2: 为典型节点组合生成 GIA，验证连线正确性
阶段3: 为不同 asset_key 生成 GIA，验证 entity 模板
"""
import sys
import traceback
from pathlib import Path
from dataclasses import dataclass, field

PROJECT_ROOT = Path(__file__).resolve().parents[3]  # tests/live_sync/tools → project root
sys.path.insert(0, str(PROJECT_ROOT))

from tools.live_sync.level_builder import GraphBuilder
from tools.live_sync.node_catalog import NodeCatalog
from tools.live_sync.validator import GIAValidator

# ═══════════════════════════════════════════
# 输出配置
# ═══════════════════════════════════════════

OUTPUT_DIR = PROJECT_ROOT / "tools" / "live_sync" / "samples" / "validation"
OUTPUT_DIR.mkdir(exist_ok=True)


@dataclass
class CaseResult:
    name: str
    category: str
    passed: bool
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    gia_path: str = ""


# ═══════════════════════════════════════════
# 阶段1: 单节点验证
# ═══════════════════════════════════════════

# 35个内置节点（按分类）
SINGLE_NODE_CASES = [
    # 条件节点
    ("多分支", "条件", {"控制表达式": 0}),
    ("比较整数", "条件", {"值A": 1, "值B": 2}),
    ("比较浮点数", "条件", {"值A": 1.0, "值B": 2.0}),
    ("是否为空", "条件", {}),
    ("随机概率", "条件", {"概率": 50}),

    # 变量节点
    ("获取局部变量", "变量", {"变量引用": 0}),
    ("设置局部变量", "变量", {"变量引用": 0, "值": 42}),
    ("获取全局变量", "变量", {"变量名": "global_var"}),
    ("设置全局变量", "变量", {"变量名": "global_var", "值": 99}),

    # 动作节点
    ("拼装列表", "动作", {}),
    ("拼装字典", "动作", {}),
    ("创建元件", "动作", {"元件ID": 12345, "位置": [0.0, 0.0, 0.0], "旋转": [0.0, 0.0, 0.0], "拥有者实体": 0, "是否覆写等级": 0, "等级": 1}),
    ("发送信号", "动作", {}),
    ("销毁实体", "动作", {}),
    ("移动实体", "动作", {"目标位置": [100.0, 0.0, 0.0]}),
    ("设置实体可见性", "动作", {"可见": 1}),
    ("播放动画", "动作", {"动画名": "idle"}),
    ("播放特效", "动作", {"特效ID": "explosion"}),
    ("播放音效", "动作", {"音效ID": "click"}),
    ("传送玩家", "动作", {"目标位置": [0.0, 0.0, 0.0]}),
    ("添加道具", "动作", {"道具ID": 1001, "数量": 1}),

    # 事件节点
    ("监听信号", "事件", {}),
    ("关卡开始时", "事件", {}),
    ("玩家进入触发器", "事件", {}),
    ("实体碰撞时", "事件", {}),
    ("交互时", "事件", {}),

    # 数学节点
    ("整数加法", "数学", {"A": 10, "B": 20}),
    ("整数减法", "数学", {"A": 20, "B": 10}),
    ("整数乘法", "数学", {"A": 5, "B": 6}),
    ("整数除法", "数学", {"A": 100, "B": 4}),
    ("浮点数加法", "数学", {"A": 1.5, "B": 2.5}),
    ("随机整数", "数学", {"最小值": 1, "最大值": 100}),

    # 逻辑节点
    ("逻辑与", "逻辑", {"A": 1, "B": 1}),
    ("逻辑或", "逻辑", {"A": 0, "B": 1}),
    ("逻辑非", "逻辑", {"输入": 1}),

    # 实用节点
    ("延迟", "实用", {"延迟(秒)": 1.0}),
    ("只执行一次", "实用", {}),
    ("日志输出", "实用", {"消息": "hello"}),
    ("获取玩家实体", "实用", {}),
    ("获取实体位置", "实用", {}),
]

# ═══════════════════════════════════════════
# 新增节点（2026-05-20 从 index.json + semantic_map 扩充）
# ═══════════════════════════════════════════
EXPANDED_NODE_CASES = [
    # 工具类
    ("打印字符串", "工具", {"字符串": "test_msg"}),
    # 条件
    ("双分支", "条件", {"条件": 1}),
    ("是否相等", "条件", {}),
    # 变量
    ("设置自定义变量", "变量", {"目标实体": 0, "变量名": "test_var", "变量值": 99}),
    ("获取自定义变量", "变量", {"目标实体": 0, "变量名": "test_var"}),
    # 动作
    ("创建实体", "动作", {"目标GUID": 0}),
    ("对列表插入值", "动作", {"索引": 0, "值": 1}),
    ("对列表修改值", "动作", {"索引": 0, "值": 1}),
    ("复苏角色", "动作", {}),
    ("发起攻击", "动作", {}),
    ("启动/暂停指定音效播放器", "动作", {}),
    ("启动/暂停玩家背景音乐", "动作", {}),
    ("修改玩家背景音乐", "动作", {"音乐ID": 1}),
    ("修改环境配置", "动作", {}),
    ("创建投射物", "动作", {"投射物ID": 1, "起始位置": [0.0,0.0,0.0], "方向": [0.0,0.0,1.0]}),
    # 事件
    ("实体创建时", "事件", {}),
    # 工具
    ("获取自身实体", "工具", {}),
    ("启动定时器", "工具", {"时长(秒)": 3.0}),
    ("启动全局计时器", "工具", {"时长(秒)": 5.0}),
    # 数学
    ("创建三维向量", "数学", {"X": 1.0, "Y": 2.0, "Z": 3.0}),
    ("逻辑或运算", "逻辑", {"A": 0, "B": 1}),
    # 查询
    ("列表是否包含该值", "查询", {}),
]

# ═══════════════════════════════════════════
# 第三批扩充节点测试（2026-05-20 下午）
# ═══════════════════════════════════════════
BATCH3_NODE_CASES = [
    # 循环节点
    ("有限循环", "循环", {"起始值": 0, "结束值": 10}),
    ("跳出循环", "循环", {}),
    # 数学节点
    ("获取随机浮点数", "数学", {"最小值": 0.0, "最大值": 1.0}),
    ("权重随机", "数学", {}),  # 数据节点，无 flow 端口，不传参
    ("拆分三维向量", "数学", {}),
    ("三维向量加法", "数学", {}),
    ("三维向量减法", "数学", {}),
    ("三维向量缩放", "数学", {}),
    ("三维向量夹角", "数学", {}),
    # 实体管理
    ("修改实体阵营", "动作", {"阵营": 1}),
    ("复苏玩家所有角色", "动作", {"满血": 1}),
    ("实体添加单位标签", "动作", {"标签ID": 100}),
    ("实体移除单位标签", "动作", {"标签ID": 100}),
    ("实体清空单位标签", "动作", {}),
    ("嘲讽目标", "动作", {}),
    # 实用
    ("查询角色当前移动速度", "实用", {}),
    ("以键对字典移除键值对", "动作", {}),  # 数据节点，不传参
    # Client 节点
    ("节点图开始", "事件", {}),
    ("筛选球体范围内的实体列表", "条件", {"半径": 5.0, "中心点": [0.0,0.0,0.0], "阵营过滤": 0}),
    ("筛选方形范围内的实体列表", "条件", {"X半边长": 5.0, "Y半边长": 5.0, "Z半边长": 5.0, "中心点": [0.0,0.0,0.0], "阵营过滤": 0}),
    ("查询实体是否在场", "条件", {}),
]

# ═══════════════════════════════════════════
# 第四批扩充节点测试（2026-05-20 深度扩充）
# ═══════════════════════════════════════════
BATCH4_NODE_CASES = [
    # 状态管理
    ("设置预设状态", "动作", {"预设状态索引": 1, "预设状态值": 0}),
    ("获取预设状态", "实用", {}),
    # 事件
    ("预设状态变化时", "事件", {}),
    ("实体移除/销毁时", "事件", {}),
    ("定时器触发时", "事件", {}),
    # 数学
    ("三维向量归一化", "数学", {}),
    # 实用查询
    ("以GUID查询实体", "实用", {}),
    ("以实体查询GUID", "实用", {}),
    ("获取拥有者实体", "实用", {}),
    ("获取实体拥有的实体列表", "实用", {}),
    ("获取碰撞触发器内所有实体", "实用", {}),
    ("查询当前环境时间", "实用", {}),
    ("获取角色属性", "实用", {}),
    # 动作
    ("结算关卡", "动作", {"是否胜利": 1}),
    ("暂停定时器", "实用", {}),
    ("恢复定时器", "实用", {}),
    ("终止定时器", "实用", {}),
    ("修改全局计时器", "实用", {}),
    ("设置当前环境时间", "动作", {}),
    ("开关实体光源", "动作", {"光源ID": 0, "开启": 1}),
    ("损失生命", "动作", {"伤害量": 100.0}),
    ("直接恢复生命", "动作", {"恢复量": 50.0}),
    ("创建元件组", "动作", {"元件组索引": 1, "位置": [0.0, 0.0, 0.0], "旋转": [0.0, 0.0, 0.0], "归属者实体": 0, "等级": 1, "是否覆写等级": 0}),
]


def run_single_node_validation() -> list:
    """阶段1: 为每个内置节点生成单节点 GIA 并验证"""
    print("=" * 70)
    print("阶段1: 单节点 GIA 生成验证（35个内置节点）")
    print("=" * 70)

    catalog = NodeCatalog.default()
    validator = GIAValidator()
    results = []

    for node_name, category, params in SINGLE_NODE_CASES:
        # 跳过已弃用的节点
        node_def = catalog.get_by_name(node_name)
        if node_def and node_def.deprecated:
            print(f"  ⏭️ {node_name:12s} [{category}] 已弃用，跳过")
            continue

        safe_name = node_name.replace(" ", "_")
        gia_name = f"v1_{safe_name}.gia"
        gia_path = OUTPUT_DIR / gia_name

        try:
            # 生成 GIA
            g = GraphBuilder(f"v1_{safe_name}", catalog=catalog)
            n = g.add_node(node_name)
            for k, v in params.items():
                n.set_param(k, v)
            g.to_gia(gia_path)

            # 验证
            from tools.live_sync.gia_utils import load_gia_numeric
            num = load_gia_numeric(gia_path)
            report = validator.validate_numeric(num)

            # 往返验证
            rt_report = validator.validate_roundtrip(num)

            errors = [str(e) for e in report.errors] + [str(e) for e in rt_report.errors]
            warnings = [str(w) for w in report.warnings] + [str(w) for w in rt_report.warnings]

            passed = len(errors) == 0
            results.append(CaseResult(
                name=node_name, category=category, passed=passed,
                errors=errors, warnings=warnings, gia_path=str(gia_path),
            ))

            status = "✅" if passed else "❌"
            warn_str = f" ({len(warnings)} warnings)" if warnings else ""
            print(f"  {status} {node_name:12s} [{category}]{warn_str}")
            for e in errors:
                print(f"      ERROR: {e}")

        except Exception as e:
            results.append(CaseResult(
                name=node_name, category=category, passed=False,
                errors=[f"{type(e).__name__}: {e}"], gia_path=str(gia_path),
            ))
            print(f"  ❌ {node_name:12s} [{category}] EXCEPTION: {e}")

    return results


def run_expanded_node_validation() -> list:
    """阶段1b: 为新增节点生成单节点 GIA 并验证"""
    print("\n" + "=" * 70)
    print("阶段1b: 新增节点 GIA 验证（23个节点）")
    print("=" * 70)

    catalog = NodeCatalog.default()
    validator = GIAValidator()
    results = []

    for node_name, category, params in EXPANDED_NODE_CASES:
        safe_name = node_name.replace(" ", "_").replace("/", "_")
        gia_name = f"v1b_{safe_name}.gia"
        gia_path = OUTPUT_DIR / gia_name

        try:
            g = GraphBuilder(f"v1b_{safe_name}", catalog=catalog)
            n = g.add_node(node_name)
            for k, v in params.items():
                n.set_param(k, v)
            g.to_gia(gia_path)

            from tools.live_sync.gia_utils import load_gia_numeric
            num = load_gia_numeric(gia_path)
            report = validator.validate_numeric(num)
            rt_report = validator.validate_roundtrip(num)

            errors = [str(e) for e in report.errors] + [str(e) for e in rt_report.errors]
            warnings = [str(w) for w in report.warnings] + [str(w) for w in rt_report.warnings]

            passed = len(errors) == 0
            results.append(CaseResult(
                name=node_name, category=category, passed=passed,
                errors=errors, warnings=warnings, gia_path=str(gia_path),
            ))

            status = "✅" if passed else "❌"
            warn_str = f" ({len(warnings)} warnings)" if warnings else ""
            print(f"  {status} {node_name:20s} [{category}]{warn_str}")
            for e in errors:
                print(f"      ERROR: {e}")

        except Exception as e:
            results.append(CaseResult(
                name=node_name, category=category, passed=False,
                errors=[f"{type(e).__name__}: {e}"], gia_path=str(gia_path),
            ))
            print(f"  ❌ {node_name:20s} [{category}] EXCEPTION: {e}")

    return results


def run_batch3_validation() -> list:
    """阶段1c: 为第三批扩充节点生成 GIA 并验证"""
    print("\n" + "=" * 70)
    print("阶段1c: 第三批扩充节点验证（20个节点）")
    print("=" * 70)

    catalog = NodeCatalog.default()
    validator = GIAValidator()
    results = []

    for node_name, category, params in BATCH3_NODE_CASES:
        safe_name = node_name.replace(" ", "_").replace("/", "_")
        gia_name = f"v1c_{safe_name}.gia"
        gia_path = OUTPUT_DIR / gia_name

        try:
            g = GraphBuilder(f"v1c_{safe_name}", catalog=catalog)
            n = g.add_node(node_name)
            for k, v in params.items():
                n.set_param(k, v)
            g.to_gia(gia_path)

            from tools.live_sync.gia_utils import load_gia_numeric
            num = load_gia_numeric(gia_path)
            report = validator.validate_numeric(num)
            rt_report = validator.validate_roundtrip(num)

            errors = [str(e) for e in report.errors] + [str(e) for e in rt_report.errors]
            warnings = [str(w) for w in report.warnings] + [str(w) for w in rt_report.warnings]

            passed = len(errors) == 0
            results.append(CaseResult(
                name=node_name, category=category, passed=passed,
                errors=errors, warnings=warnings, gia_path=str(gia_path),
            ))

            status = "✅" if passed else "❌"
            warn_str = f" ({len(warnings)} warnings)" if warnings else ""
            print(f"  {status} {node_name:25s} [{category}]{warn_str}")
            for e in errors:
                print(f"      ERROR: {e}")

        except Exception as e:
            results.append(CaseResult(
                name=node_name, category=category, passed=False,
                errors=[f"{type(e).__name__}: {e}"], gia_path=str(gia_path),
            ))
            print(f"  ❌ {node_name:25s} [{category}] EXCEPTION: {e}")

    return results


def run_batch4_validation() -> list:
    """阶段1d: 为第四批深度扩充节点生成 GIA 并验证"""
    print("\n" + "=" * 70)
    print("阶段1d: 第四批深度扩充节点验证（23个节点）")
    print("=" * 70)

    catalog = NodeCatalog.default()
    validator = GIAValidator()
    results = []

    for node_name, category, params in BATCH4_NODE_CASES:
        safe_name = node_name.replace(" ", "_").replace("/", "_")
        gia_name = f"v1d_{safe_name}.gia"
        gia_path = OUTPUT_DIR / gia_name

        try:
            g = GraphBuilder(f"v1d_{safe_name}", catalog=catalog)
            n = g.add_node(node_name)
            for k, v in params.items():
                n.set_param(k, v)
            g.to_gia(gia_path)

            from tools.live_sync.gia_utils import load_gia_numeric
            num = load_gia_numeric(gia_path)
            report = validator.validate_numeric(num)
            rt_report = validator.validate_roundtrip(num)

            errors = [str(e) for e in report.errors] + [str(e) for e in rt_report.errors]
            warnings = [str(w) for w in report.warnings] + [str(w) for w in rt_report.warnings]

            passed = len(errors) == 0
            results.append(CaseResult(
                name=node_name, category=category, passed=passed,
                errors=errors, warnings=warnings, gia_path=str(gia_path),
            ))

            status = "✅" if passed else "❌"
            warn_str = f" ({len(warnings)} warnings)" if warnings else ""
            print(f"  {status} {node_name:25s} [{category}]{warn_str}")
            for e in errors:
                print(f"      ERROR: {e}")

        except Exception as e:
            results.append(CaseResult(
                name=node_name, category=category, passed=False,
                errors=[f"{type(e).__name__}: {e}"], gia_path=str(gia_path),
            ))
            print(f"  ❌ {node_name:25s} [{category}] EXCEPTION: {e}")

    return results


# ═══════════════════════════════════════════
# 阶段2: 节点组合 + 连线验证
# ═══════════════════════════════════════════

COMBO_CASES = [
    # (名称, 节点列表, 连线列表, 描述)
    ("事件→动作", [
        ("监听信号", {}),
        ("发送信号", {}),
    ], [
        ("监听信号", "出", "发送信号", "入"),
    ], "事件触发动作"),

    ("事件→分支→动作", [
        ("监听信号", {}),
        ("多分支", {"控制表达式": 1}),
        ("发送信号", {}),
    ], [
        ("监听信号", "出", "多分支", "入"),
        ("多分支", "默认", "发送信号", "入"),
    ], "事件→分支→动作"),

    ("事件→创建元件", [
        ("关卡开始时", {}),
        ("创建元件", {"元件ID": 99999, "位置": [0.0, 0.0, 0.0]}),
    ], [
        ("关卡开始时", "出", "创建元件", "入"),
    ], "关卡开始创建元件"),

    ("事件→销毁实体", [
        ("交互时", {}),
        ("销毁实体", {}),
    ], [
        ("交互时", "出", "销毁实体", "入"),
    ], "交互后销毁"),

    # 注意：获取局部变量是纯数据节点，无flow端口，不能connect_flow
    # 简化测试：只测试设置局部变量（有flow端口）
    ("变量设置", [
        ("监听信号", {}),
        ("设置局部变量", {"变量引用": 0, "值": 42}),
    ], [
        ("监听信号", "出", "设置局部变量", "入"),
    ], "事件→设置变量"),

    # 数学节点是纯数据节点，无flow端口，用数据连接
    ("数学运算", [
        ("整数加法", {"A": 10, "B": 20}),
        ("发送信号", {}),
    ], [
        # 数学节点无flow端口，不能connect_flow
        # 只验证节点能正常创建
    ], "数学节点创建"),

    ("条件判断", [
        ("比较整数", {"值A": 10, "值B": 20}),
        ("发送信号", {}),
    ], [
        # 比较整数是纯数据节点，输出是数据不是flow
        # 只验证节点能正常创建
    ], "比较节点创建"),

    ("延迟执行", [
        ("监听信号", {}),
        ("延迟", {"延迟(秒)": 2.0}),
        ("发送信号", {}),
    ], [
        ("监听信号", "出", "延迟", "入"),
        ("延迟", "出", "发送信号", "入"),
    ], "事件→延迟→动作"),

    # 逻辑节点也是纯数据节点
    ("逻辑运算", [
        ("逻辑与", {"A": 1, "B": 1}),
        ("发送信号", {}),
    ], [
        # 逻辑与无flow端口
    ], "逻辑节点创建"),

    ("传送+音效", [
        ("交互时", {}),
        ("传送玩家", {"目标位置": [100.0, 200.0, 300.0]}),
        ("播放音效", {"音效ID": "teleport"}),
    ], [
        ("交互时", "出", "传送玩家", "入"),
        ("传送玩家", "出", "播放音效", "入"),
    ], "交互→传送→音效"),

    ("随机+分支", [
        ("随机概率", {"概率": 30}),
        ("发送信号", {}),
        ("日志输出", {"消息": "unlucky"}),
    ], [
        ("随机概率", "成功", "发送信号", "入"),
        ("随机概率", "失败", "日志输出", "入"),
    ], "随机→分支"),

    # 获取玩家实体是纯数据节点，输出端口叫"玩家"不是"出"
    ("获取玩家+移动", [
        ("关卡开始时", {}),
        ("获取玩家实体", {}),
        ("移动实体", {"目标位置": [100.0, 0.0, 0.0]}),
    ], [
        ("关卡开始时", "出", "移动实体", "入"),
        # 获取玩家实体无flow端口，数据连接用connect_data（这里简化测试）
    ], "获取玩家→移动"),
]


def run_combo_validation() -> list:
    """阶段2: 为典型节点组合生成 GIA 并验证"""
    print("\n" + "=" * 70)
    print("阶段2: 节点组合 + 连线验证（12个场景）")
    print("=" * 70)

    catalog = NodeCatalog.default()
    validator = GIAValidator()
    results = []

    for case_name, nodes_def, connections_def, desc in COMBO_CASES:
        # 跳过包含已弃用节点的组合
        if any(catalog.get_by_name(nn) and catalog.get_by_name(nn).deprecated for nn, _ in nodes_def):
            print(f"  ⏭️ {case_name:20s} 包含已弃用节点，跳过")
            continue

        safe_name = case_name.replace(" ", "_").replace("→", "_to_")
        gia_name = f"v2_{safe_name}.gia"
        gia_path = OUTPUT_DIR / gia_name

        try:
            g = GraphBuilder(f"v2_{safe_name}", catalog=catalog)

            # 创建节点
            node_map = {}
            for node_name, params in nodes_def:
                n = g.add_node(node_name)
                for k, v in params.items():
                    n.set_param(k, v)
                node_map[node_name] = n

            # 创建连线
            for src_name, src_port, dst_name, dst_port in connections_def:
                g.connect_flow(node_map[src_name], src_port, node_map[dst_name], dst_port)

            # 生成 GIA
            g.to_gia(gia_path)

            # 验证
            from tools.live_sync.gia_utils import load_gia_numeric
            num = load_gia_numeric(gia_path)
            report = validator.validate_numeric(num)
            rt_report = validator.validate_roundtrip(num)

            errors = [str(e) for e in report.errors] + [str(e) for e in rt_report.errors]
            warnings = [str(w) for w in report.warnings] + [str(w) for w in rt_report.warnings]

            passed = len(errors) == 0
            results.append(CaseResult(
                name=case_name, category="组合", passed=passed,
                errors=errors, warnings=warnings, gia_path=str(gia_path),
            ))

            status = "✅" if passed else "❌"
            conn_count = len(connections_def)
            warn_str = f" ({len(warnings)} warnings)" if warnings else ""
            print(f"  {status} {case_name:20s} [{desc}] {conn_count} 连线{warn_str}")
            for e in errors:
                print(f"      ERROR: {e}")

        except Exception as e:
            tb = traceback.format_exc()
            results.append(CaseResult(
                name=case_name, category="组合", passed=False,
                errors=[f"{type(e).__name__}: {e}"], gia_path=str(gia_path),
            ))
            print(f"  ❌ {case_name:20s} EXCEPTION: {e}")
            print(f"      {tb}")

    return results


# ═══════════════════════════════════════════
# 阶段3: 不同 asset_key 的 entity 模板验证
# ═══════════════════════════════════════════

ASSET_CASES = [
    ("coin", "金币", "创建元件"),
    ("key", "钥匙", "创建元件"),
    ("goblet", "酒杯", "创建元件"),
]


def run_asset_validation() -> list:
    """阶段3: 为不同 asset_key 生成 GIA（通过 LevelExporter）"""
    print("\n" + "=" * 70)
    print("阶段3: 不同 asset_key 的 entity 模板验证")
    print("=" * 70)

    results = []

    for asset_key, display_name, node_name in ASSET_CASES:
        gia_name = f"v3_{asset_key}.gia"
        gia_path = OUTPUT_DIR / gia_name

        try:
            from tools.live_sync.level_exporter import LevelExporter

            catalog = NodeCatalog.default()
            g = GraphBuilder(f"v3_{asset_key}", catalog=catalog)
            n = g.add_node(node_name)
            n.set_param("元件ID", 12345)
            n.set_param("位置", [0.0, 0.0, 0.0])

            exporter = LevelExporter()
            exporter.export(g, asset_key, gia_path)

            # 验证
            from tools.live_sync.gia_utils import load_gia_numeric
            num = load_gia_numeric(gia_path)

            validator = GIAValidator()
            report = validator.validate_numeric(num)
            rt_report = validator.validate_roundtrip(num)

            errors = [str(e) for e in report.errors] + [str(e) for e in rt_report.errors]
            warnings = [str(w) for w in report.warnings] + [str(w) for w in rt_report.warnings]

            # 额外检查：entity entry 是否存在
            # 注意：不同 asset_key 的 entry type 不同
            # 物件(coin/key) type=1, 实体(goblet) type=3
            from tools.live_sync.asset_registry import get_asset
            asset_def = get_asset(asset_key)
            expected_type = asset_def.resource_class if asset_def else 1

            raw_entries = num.get('1', [])
            if isinstance(raw_entries, dict):
                raw_entries = [raw_entries]

            has_entity = any(
                e.get('5') == expected_type
                for e in raw_entries if isinstance(e, dict)
            )
            has_ng = any('13' in e for e in raw_entries if isinstance(e, dict))

            if not has_entity:
                errors.append(f"缺少 entity entry (期望 type={expected_type})")
            if not has_ng:
                errors.append("缺少 NG entry (field '13')")

            passed = len(errors) == 0
            results.append(CaseResult(
                name=f"{asset_key} ({display_name})", category="资产模板", passed=passed,
                errors=errors, warnings=warnings, gia_path=str(gia_path),
            ))

            status = "✅" if passed else "❌"
            warn_str = f" ({len(warnings)} warnings)" if warnings else ""
            print(f"  {status} {asset_key:12s} ({display_name}) entity={has_entity} ng={has_ng}{warn_str}")
            for e in errors:
                print(f"      ERROR: {e}")

        except Exception as e:
            tb = traceback.format_exc()
            results.append(CaseResult(
                name=f"{asset_key} ({display_name})", category="资产模板", passed=False,
                errors=[f"{type(e).__name__}: {e}"], gia_path=str(gia_path),
            ))
            print(f"  ❌ {asset_key:12s} ({display_name}) EXCEPTION: {e}")
            print(f"      {tb}")

    return results


# ═══════════════════════════════════════════
# 主函数
# ═══════════════════════════════════════════

def print_summary(all_results: list):
    """打印汇总报告"""
    total = len(all_results)
    passed = sum(1 for r in all_results if r.passed)
    failed = total - passed

    print("\n" + "=" * 70)
    print(f"汇总: {passed}/{total} 通过, {failed} 失败")
    print("=" * 70)

    if failed > 0:
        print("\n❌ 失败列表:")
        for r in all_results:
            if not r.passed:
                print(f"  [{r.category}] {r.name}")
                for e in r.errors:
                    print(f"    - {e}")

    # 按类别统计
    categories = {}
    for r in all_results:
        if r.category not in categories:
            categories[r.category] = {"total": 0, "passed": 0, "failed": 0}
        categories[r.category]["total"] += 1
        if r.passed:
            categories[r.category]["passed"] += 1
        else:
            categories[r.category]["failed"] += 1

    print("\n按类别统计:")
    for cat, stats in categories.items():
        status = "✅" if stats["failed"] == 0 else "❌"
        print(f"  {status} {cat:8s}: {stats['passed']}/{stats['total']} 通过")

    return failed == 0


def main():
    all_results = []

    # 阶段1
    r1 = run_single_node_validation()
    all_results.extend(r1)

    # 阶段1b - 新增节点
    r1b = run_expanded_node_validation()
    all_results.extend(r1b)

    # 阶段1c - 第三批扩充节点
    r1c = run_batch3_validation()
    all_results.extend(r1c)

    # 阶段1d - 第四批深度扩充节点
    r1d = run_batch4_validation()
    all_results.extend(r1d)

    # 阶段2
    r2 = run_combo_validation()
    all_results.extend(r2)

    # 阶段3
    r3 = run_asset_validation()
    all_results.extend(r3)

    # 汇总
    ok = print_summary(all_results)

    # 生成可视化
    print("\n生成可视化 HTML...")
    from tools.live_sync.gia_viz import extract_graph, generate_html
    viz_dir = OUTPUT_DIR / "viz"
    viz_dir.mkdir(exist_ok=True)

    viz_count = 0
    for r in all_results:
        if r.passed and r.gia_path:
            try:
                gia_path = Path(r.gia_path)
                if gia_path.exists():
                    graphs = extract_graph(gia_path)
                    if graphs:
                        html = generate_html(gia_path, graphs)
                        viz_path = viz_dir / gia_path.with_suffix('.html').name
                        viz_path.write_text(html, encoding='utf-8')
                        viz_count += 1
            except Exception:
                pass

    print(f"  生成 {viz_count} 个可视化文件 → {viz_dir}")

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
