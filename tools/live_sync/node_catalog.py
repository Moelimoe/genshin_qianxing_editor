# -*- coding: utf-8 -*-
"""节点语义注册表 (NodeCatalog)

AI 可查询的节点知识库，提供：
- 节点注册 / 查询（按 ID、名称、关键词、分类）
- 端口信息（流程端口 + 数据端口）
- 类型安全检查（端口连接兼容性）
- 从 NodeEditorPack data.json / genshin-ts report.json 批量加载
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("live_sync.catalog")

# ═══════════════════════════════════════════════════════════════
# 已知可用的 type_id 范围（从编辑器导出的GIA中提取）
# 当前已知 ID: 1, 2, 14, 22, 36, 50, 69, 77, 92, 200, 233, 259, 652
# ═══════════════════════════════════════════════════════════════
_REAL_TYPE_ID_MIN = 1
_REAL_TYPE_ID_MAX = 1000


# ═══════════════════════════════════════════════════════════════
# VarType 常量（与 server VarType int 对齐）
# ═══════════════════════════════════════════════════════════════

class VarType:
    """Server-side VarType int 常量"""
    Ety = 1
    GUID = 2
    Int = 3
    Bol = 4
    Flt = 5
    Str = 6
    GUIDArr = 7
    IntArr = 8
    BolArr = 9
    FltArr = 10
    StrArr = 11
    Vec = 12
    EtyArr = 13
    VecArr = 15
    Enum = 14
    Faction = 17
    Config = 20
    Prefab = 21
    ConfigArr = 22
    PrefabArr = 23


# ═══════════════════════════════════════════════════════════════
# 数据类
# ═══════════════════════════════════════════════════════════════

@dataclass(frozen=True, slots=True)
class PinDef:
    """端口定义"""
    name: str           # 端口名称（中文）
    direction: str      # "In" | "Out"
    is_flow: bool       # 是否流程端口
    type_expr: str      # 类型表达式（如 "Int", "Bol", "Ety"）
    var_type: int       # server VarType int
    index: int          # 端口索引
    default_value: Any = None  # 引脚默认值（仅可视化用，不写入 GIA）
    is_configurable: bool = False  # 类型可选的引脚（如多分支的"控制表达式"可选择 Int/Str）


@dataclass(frozen=True, slots=True)
class NodeDef:
    """节点定义"""
    type_id: int        # 节点类型 ID
    name: str           # 节点名称（中文）
    category: str       # 分类：event / action / condition / variable / composite
    description: str    # 自然语言描述（AI 可读）
    inputs: tuple[PinDef, ...] = ()
    outputs: tuple[PinDef, ...] = ()
    node_params: tuple[PinDef, ...] = ()  # 节点参数（非引脚，如监听信号的"信号名"）
    deprecated: bool = False  # 标记为不可用（沙箱中找不到，可能已改名或移除）


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """连接校验结果"""
    ok: bool
    errors: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.ok


# ═══════════════════════════════════════════════════════════════
# 类型表达式 → VarType 映射
# ═══════════════════════════════════════════════════════════════

_TYPE_EXPR_TO_VARTYPE: Dict[str, int] = {
    "Ety": VarType.Ety,
    "GUID": VarType.GUID,
    "Gid": VarType.GUID,
    "Int": VarType.Int,
    "Bol": VarType.Bol,
    "Flt": VarType.Flt,
    "Str": VarType.Str,
    "Vec": VarType.Vec,
    "Faction": VarType.Faction,
    "Config": VarType.Config,
    "Prefab": VarType.Prefab,
    "GUIDArr": VarType.GUIDArr,
    "IntArr": VarType.IntArr,
    "BolArr": VarType.BolArr,
    "FltArr": VarType.FltArr,
    "StrArr": VarType.StrArr,
    "EtyArr": VarType.EtyArr,
    "VecArr": VarType.VecArr,
    "ConfigArr": VarType.ConfigArr,
    "PrefabArr": VarType.PrefabArr,
}


def _type_expr_to_var_type(type_expr: str) -> int:
    """将类型表达式映射到 VarType int，未知类型返回 0"""
    t = type_expr.strip()
    if t in _TYPE_EXPR_TO_VARTYPE:
        return _TYPE_EXPR_TO_VARTYPE[t]
    # L<T> 列表语法
    if t.startswith("L<") and t.endswith(">"):
        inner = t[2:-1].strip()
        inner_vt = _type_expr_to_var_type(inner)
        list_map: Dict[int, int] = {
            VarType.GUID: VarType.GUIDArr,
            VarType.Int: VarType.IntArr,
            VarType.Bol: VarType.BolArr,
            VarType.Flt: VarType.FltArr,
            VarType.Str: VarType.StrArr,
            VarType.Ety: VarType.EtyArr,
            VarType.Vec: VarType.VecArr,
            VarType.Config: VarType.ConfigArr,
            VarType.Prefab: VarType.PrefabArr,
        }
        return list_map.get(inner_vt, 0)
    return 0


# ═══════════════════════════════════════════════════════════════
# NodeCatalog 实现
# ═══════════════════════════════════════════════════════════════

class NodeCatalog:
    """节点语义注册表 - AI 可查询的节点知识库"""

    def __init__(self) -> None:
        self._by_id: Dict[int, NodeDef] = {}
        self._by_name: Dict[str, NodeDef] = {}

    # ── 注册 ──────────────────────────────────────────────

    def register(self, node: NodeDef) -> None:
        """注册（或覆盖）一个节点定义"""
        self._by_id[node.type_id] = node
        self._by_name[node.name] = node

    # ── 查询 ──────────────────────────────────────────────

    def get_by_id(self, type_id: int) -> Optional[NodeDef]:
        """按 type_id 查询"""
        return self._by_id.get(type_id)

    def get_by_name(self, name: str) -> Optional[NodeDef]:
        """按名称查询（精确匹配）"""
        return self._by_name.get(name)

    def search(self, keyword: str) -> List[NodeDef]:
        """按关键词模糊搜索（匹配名称和描述）"""
        kw = keyword.strip()
        if not kw:
            return list(self._by_id.values())
        kw_lower = kw.lower()
        return [
            n for n in self._by_id.values()
            if kw_lower in n.name.lower() or kw_lower in n.description.lower()
        ]

    def list_categories(self) -> List[str]:
        """列出所有已注册的分类"""
        cats: set[str] = set()
        for n in self._by_id.values():
            cats.add(n.category)
        return sorted(cats)

    def list_by_category(self, category: str) -> List[NodeDef]:
        """按分类列出节点"""
        return [n for n in self._by_id.values() if n.category == category]

    # ── 连接校验 ──────────────────────────────────────────

    def can_connect(
        self,
        src: NodeDef,
        src_port: str,
        dst: NodeDef,
        dst_port: str,
    ) -> ValidationResult:
        """检查 src 的输出端口能否连接到 dst 的输入端口"""
        errors: list[str] = []

        # 查找源端口（必须在 outputs 中）
        src_pin = self._find_pin(src.outputs, src_port)
        if src_pin is None:
            # 也检查 inputs（如果是输入端口则方向错误）
            if self._find_pin(src.inputs, src_port) is not None:
                errors.append(f"源端口 '{src_port}' 是输入端口，不能作为连接源")
            else:
                errors.append(f"源节点 '{src.name}' 没有名为 '{src_port}' 的输出端口")
            return ValidationResult(ok=False, errors=errors)

        # 查找目标端口（必须在 inputs 中）
        dst_pin = self._find_pin(dst.inputs, dst_port)
        if dst_pin is None:
            # 也检查 outputs（如果是输出端口则方向错误）
            if self._find_pin(dst.outputs, dst_port) is not None:
                errors.append(f"目标端口 '{dst_port}' 是输出端口，不能作为连接目标")
            else:
                errors.append(f"目标节点 '{dst.name}' 没有名为 '{dst_port}' 的输入端口")
            return ValidationResult(ok=False, errors=errors)

        # 流程/数据端口类型必须一致
        if src_pin.is_flow != dst_pin.is_flow:
            errors.append(
                f"端口类型不匹配：源 '{src_port}' 是{'流程' if src_pin.is_flow else '数据'}端口，"
                f"目标 '{dst_port}' 是{'流程' if dst_pin.is_flow else '数据'}端口"
            )
            return ValidationResult(ok=False, errors=errors)

        # 数据端口：检查类型兼容性
        if not src_pin.is_flow:
            if src_pin.var_type != dst_pin.var_type:
                errors.append(
                    f"数据类型不匹配：源 '{src_port}'({src_pin.type_expr}) "
                    f"vs 目标 '{dst_port}'({dst_pin.type_expr})"
                )
                return ValidationResult(ok=False, errors=errors)

        return ValidationResult(ok=True, errors=[])

    # ── 容器协议 ──────────────────────────────────────────

    def __len__(self) -> int:
        return len(self._by_id)

    def __contains__(self, type_id: object) -> bool:
        return int(type_id) in self._by_id if isinstance(type_id, int) else False

    # ── 工厂方法 ──────────────────────────────────────────

    @classmethod
    def default(cls) -> NodeCatalog:
        """创建预置常用节点的默认注册表"""
        cat = cls()
        for node in _BUILTIN_NODES:
            cat.register(node)
        for node in _EXPANDED_NODES:
            cat.register(node)
        return cat

    @classmethod
    def from_node_editor_pack(cls, data_json_path: Path) -> NodeCatalog:
        """
        从 NodeEditorPack 的 data.json 加载节点。

        data.json 结构：
        {
          "Nodes": [
            {
              "ID": 3,
              "Name": {"zh-Hans": "多分支"},
              "FlowPins": [...],
              "DataPins": [...]
            }
          ]
        }
        """
        cat = cls()
        path = Path(data_json_path)
        if not path.is_file():
            return cat

        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return cat

        nodes = obj.get("Nodes") if isinstance(obj, dict) else None
        if not isinstance(nodes, list):
            return cat

        for item in nodes:
            if not isinstance(item, dict):
                continue
            raw_id = item.get("ID")
            if not isinstance(raw_id, int):
                continue

            # 名称
            name_obj = item.get("Name")
            if isinstance(name_obj, dict):
                name = str(name_obj.get("zh-Hans") or name_obj.get("en") or str(raw_id))
            elif isinstance(name_obj, str):
                name = name_obj
            else:
                name = str(raw_id)

            # 分类推断
            category = _infer_category(name, int(raw_id))

            # 端口
            inputs: list[PinDef] = []
            outputs: list[PinDef] = []
            _parse_pins(item, "FlowPins", True, inputs, outputs)
            _parse_pins(item, "DataPins", False, inputs, outputs)

            cat.register(NodeDef(
                type_id=int(raw_id),
                name=name,
                category=category,
                description=f"NodeEditorPack 节点 ID={raw_id}",
                inputs=tuple(inputs),
                outputs=tuple(outputs),
            ))

        return cat

    @classmethod
    def from_genshin_ts_report(cls, report_path: Path) -> NodeCatalog:
        """
        从 genshin-ts 的 node_schema report.json 加载节点。

        report.json 结构：
        {
          "node_pin_records": [
            {"id": 3, "name": "Multiple_Branches", "inputs": [...], "outputs": [...]}
          ]
        }
        """
        cat = cls()
        path = Path(report_path)
        if not path.is_file():
            return cat

        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return cat

        records = obj.get("node_pin_records") if isinstance(obj, dict) else None
        if not isinstance(records, list):
            return cat

        for rec in records:
            if not isinstance(rec, dict):
                continue
            raw_id = rec.get("id")
            if not isinstance(raw_id, int):
                continue
            name = str(rec.get("name") or str(raw_id))
            category = _infer_category(name, int(raw_id))

            inputs: list[PinDef] = []
            outputs: list[PinDef] = []

            raw_inputs = rec.get("inputs")
            if isinstance(raw_inputs, list):
                for idx, t in enumerate(raw_inputs):
                    if not isinstance(t, str) or not t.strip():
                        continue
                    inputs.append(PinDef(
                        name=f"in_{idx}",
                        direction="In",
                        is_flow=False,
                        type_expr=t.strip(),
                        var_type=_type_expr_to_var_type(t.strip()),
                        index=idx,
                    ))

            raw_outputs = rec.get("outputs")
            if isinstance(raw_outputs, list):
                for idx, t in enumerate(raw_outputs):
                    if not isinstance(t, str) or not t.strip():
                        continue
                    outputs.append(PinDef(
                        name=f"out_{idx}",
                        direction="Out",
                        is_flow=False,
                        type_expr=t.strip(),
                        var_type=_type_expr_to_var_type(t.strip()),
                        index=idx,
                    ))

            cat.register(NodeDef(
                type_id=int(raw_id),
                name=name,
                category=category,
                description=f"genshin-ts schema 节点 ID={raw_id}",
                inputs=tuple(inputs),
                outputs=tuple(outputs),
            ))

            # reflectMap
            reflect_map = rec.get("reflectMap")
            if isinstance(reflect_map, list):
                for item in reflect_map:
                    if isinstance(item, (list, tuple)) and len(item) >= 1 and isinstance(item[0], int):
                        cat.register(NodeDef(
                            type_id=int(item[0]),
                            name=name,
                            category=category,
                            description=f"genshin-ts schema 节点 (concrete) ID={item[0]}",
                            inputs=tuple(inputs),
                            outputs=tuple(outputs),
                        ))

        return cat

    # ── 内部工具 ──────────────────────────────────────────

    @staticmethod
    def _find_pin(pins: tuple[PinDef, ...], name: str) -> Optional[PinDef]:
        """按名称查找端口"""
        for p in pins:
            if p.name == name:
                return p
        return None


# ═══════════════════════════════════════════════════════════════
# 内部辅助
# ═══════════════════════════════════════════════════════════════

def _parse_pins(
    node_record: Dict[str, Any],
    key: str,
    is_flow: bool,
    inputs: list[PinDef],
    outputs: list[PinDef],
) -> None:
    """从 NodeEditorPack 节点记录解析端口"""
    raw = node_record.get(key)
    if not isinstance(raw, list):
        return
    for p in raw:
        if not isinstance(p, dict):
            continue
        direction = str(p.get("Direction") or "").strip()
        if direction not in {"In", "Out"}:
            continue
        type_expr = str(p.get("Type") or "").strip()
        label_zh = ""
        label_obj = p.get("Label")
        if isinstance(label_obj, dict):
            label_zh = str(label_obj.get("zh-Hans") or "").strip()
        identifier = str(p.get("Identifier") or "").strip()
        # 优先使用中文标签，其次 Identifier
        port_name = label_zh or identifier or f"{'in' if direction == 'In' else 'out'}_{len(inputs) + len(outputs)}"
        shell_index = int(p.get("ShellIndex") or 0)
        pin = PinDef(
            name=port_name,
            direction=direction,
            is_flow=is_flow,
            type_expr=type_expr,
            var_type=_type_expr_to_var_type(type_expr) if type_expr else 0,
            index=shell_index,
        )
        if direction == "In":
            inputs.append(pin)
        else:
            outputs.append(pin)


_EVENT_KEYWORDS = {"监听", "事件", "触发", "进入", "离开", "碰撞", "交互", "拾取"}
_ACTION_KEYWORDS = {"创建", "设置", "发送", "删除", "移动", "播放", "停止", "添加", "移除", "拼装"}
_CONDITION_KEYWORDS = {"判断", "条件", "比较", "分支", "过滤", "如果", "Switch", "Branch"}
_VARIABLE_KEYWORDS = {"获取", "变量", "读取", "写入"}
_COMPOSITE_KEYWORDS = {"复合", "子图", "Composite"}


def _infer_category(name: str, type_id: int) -> str:
    """根据节点名称和 ID 推断分类"""
    # 信号类特殊处理
    if "监听信号" in name or "Listen" in name:
        return "event"
    if "发送信号" in name or "Send" in name:
        return "action"
    # 事件类
    for kw in _EVENT_KEYWORDS:
        if kw in name:
            return "event"
    # 条件类
    for kw in _CONDITION_KEYWORDS:
        if kw in name:
            return "condition"
    # 变量类
    for kw in _VARIABLE_KEYWORDS:
        if kw in name:
            return "variable"
    # 动作类
    for kw in _ACTION_KEYWORDS:
        if kw in name:
            return "action"
    # 复合节点
    if type_id >= 0x60000000:
        return "composite"
    for kw in _COMPOSITE_KEYWORDS:
        if kw in name:
            return "composite"
    return "action"


# ═══════════════════════════════════════════════════════════════
# 预置常用节点
# ═══════════════════════════════════════════════════════════════

def _p(name: str, direction: str, is_flow: bool = False,
       type_expr: str = "", var_type: int = 0, index: int = 0,
       default_value = None, is_configurable: bool = False) -> PinDef:
    """PinDef 简写构造"""
    return PinDef(name=name, direction=direction, is_flow=is_flow,
                  type_expr=type_expr, var_type=var_type, index=index,
                  default_value=default_value, is_configurable=is_configurable)


_BUILTIN_NODES: List[NodeDef] = [
    # ── type_id=3: Multiple_Branches (多分支) ──
    NodeDef(
        type_id=3,
        name="多分支",
        category="condition",
        description="根据控制表达式（整数/字符串）的值匹配不同分支路径。默认展示「默认」出端口，最多可扩展至 49 个分支（分支0~48），上限 50 个输出端口",
        inputs=(
            _p("入", "In", is_flow=True, index=0),
            _p("控制表达式", "In", var_type=0, index=1, is_configurable=True),
        ),
        outputs=(
            _p("默认", "Out", is_flow=True, index=0),
            *(_p(f"分支{i}", "Out", is_flow=True, index=i+1, default_value=i) for i in range(49)),
        ),
    ),

    # ── type_id=18: Get_Local_Variable (获取局部变量) ──
    NodeDef(
        type_id=18,
        name="获取局部变量",
        category="variable",
        description="读取当前作用域的局部变量值",
        inputs=(
            _p("变量引用", "In", type_expr="Loc", var_type=16, index=0),
        ),
        outputs=(
            _p("值", "Out", type_expr="", var_type=0, index=0),
        ),
    ),

    # ── type_id=169: Assembly_List (拼装列表) ──
    NodeDef(
        type_id=169,
        name="拼装列表",
        category="action",
        description="将多个元素拼装成一个列表，元素数量动态可变",
        inputs=(
            _p("入", "In", is_flow=True, index=0),
            _p("元素", "In", type_expr="", var_type=0, index=1),
        ),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
            _p("列表", "Out", type_expr="", var_type=0, index=1),
        ),
    ),

    # ── type_id=1788: Assembly_Dictionary (拼装字典) ──
    NodeDef(
        type_id=1788,
        name="拼装字典",
        category="action",
        description="将键值对拼装成字典，键值对数量动态可变",
        inputs=(
            _p("入", "In", is_flow=True, index=0),
            _p("键", "In", type_expr="Str", var_type=VarType.Str, index=1),
            _p("值", "In", type_expr="", var_type=0, index=2),
        ),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
            _p("字典", "Out", type_expr="", var_type=0, index=1),
        ),
    ),

    # ── type_id=252: Create_Prefab (创建元件) ──
    NodeDef(
        type_id=252,
        name="创建元件",
        category="action",
        description="根据元件ID创建一个实体",
        inputs=(
            _p("入", "In", is_flow=True, index=0),
            _p("元件ID", "In", type_expr="Prefab", var_type=VarType.Prefab, index=1),
            _p("位置", "In", type_expr="Vec", var_type=VarType.Vec, index=2),
            _p("旋转", "In", type_expr="Vec", var_type=VarType.Vec, index=3),
            _p("拥有者实体", "In", type_expr="Ety", var_type=VarType.Ety, index=4),
            _p("是否覆写等级", "In", type_expr="Bol", var_type=VarType.Bol, index=5),
            _p("等级", "In", type_expr="Int", var_type=VarType.Int, index=6),
            _p("单位标签索引列表", "In", type_expr="IntArr", var_type=VarType.IntArr, index=7),
        ),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
            _p("创建后实体", "Out", type_expr="Ety", var_type=VarType.Ety, index=1),
        ),
    ),

    # ── type_id=300000: Send_Signal (发送信号) ──
    NodeDef(
        type_id=300000,
        name="发送信号",
        category="action",
        description="向服务器节点图发送信号",
        inputs=(
            _p("入", "In", is_flow=True, index=0),
        ),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
        ),
        node_params=(
            _p("信号名", "In", type_expr="Str", var_type=VarType.Str, default_value=""),
        ),
    ),

    # ── type_id=300001: Listen_Signal (监听信号) ──
    NodeDef(
        type_id=300001,
        name="监听信号",
        category="event",
        description="监听指定信号并在收到时触发。节点参数：信号名(Str)。出参：事件源实体/事件源GUID/信号来源实体",
        inputs=(),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
            _p("事件源实体", "Out", type_expr="Ety", var_type=VarType.Ety, index=1),
            _p("事件源GUID", "Out", type_expr="Gid", var_type=VarType.GUID, index=2),
            _p("信号来源实体", "Out", type_expr="Ety", var_type=VarType.Ety, index=3),
        ),
        node_params=(
            _p("信号名", "In", type_expr="Str", var_type=VarType.Str, index=0, default_value=""),
        ),
    ),

    # ═══════════════════════════════════════════════════════════════
    # 事件节点 (Event Nodes)
    # ═══════════════════════════════════════════════════════════════

    # ── type_id=100001: On_Level_Start (关卡开始时) ──
    NodeDef(
        type_id=100001,
        name="关卡开始时",
        category="event",
        description="当关卡开始时触发",
        inputs=(),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
        ),
    ),

    # ── type_id=100002: On_Player_Enter (玩家进入时) ──
    NodeDef(
        type_id=100002,
        name="玩家进入触发器",
        category="event",
        description="当玩家进入触发器区域时触发",
        inputs=(
            _p("触发器", "In", type_expr="Ety", var_type=VarType.Ety, index=0),
        ),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
            _p("玩家", "Out", type_expr="Ety", var_type=VarType.Ety, index=1),
        ),
    ),

    # ── type_id=100003: On_Entity_Collide (实体碰撞时) ──
    NodeDef(
        type_id=100003,
        name="实体碰撞时",
        category="event",
        description="当实体发生碰撞时触发",
        inputs=(
            _p("实体", "In", type_expr="Ety", var_type=VarType.Ety, index=0),
        ),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
            _p("碰撞对象", "Out", type_expr="Ety", var_type=VarType.Ety, index=1),
        ),
    ),

    # ── type_id=92: On_Enter_Collision_Trigger (进入碰撞触发器时) [VERIFIED: 示例关卡] ──
    NodeDef(
        type_id=92,
        name="进入碰撞触发器时",
        category="event",
        description="当实体进入碰撞触发器范围时触发（与100002不同，此为真实编辑器type_id）",
        inputs=(),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
            _p("进入者实体", "Out", type_expr="Ety", var_type=VarType.Ety, index=1),
            _p("进入者实体GUID", "Out", type_expr="GUID", var_type=VarType.GUID, index=2),
            _p("触发器实体", "Out", type_expr="Ety", var_type=VarType.Ety, index=3),
            _p("触发器实体GUID", "Out", type_expr="GUID", var_type=VarType.GUID, index=4),
            _p("触发器序号", "Out", type_expr="Int", var_type=VarType.Int, index=5),
        ),
    ),

    # ── type_id=100004: On_Interact (交互时) ──  [DEPRECATED: 沙箱中搜不到，可能已改名或移除]
    NodeDef(
        type_id=100004,
        name="交互时",
        category="event",
        description="[已弃用] 当玩家与实体交互时触发（沙箱中找不到此节点，可能已改名）",
        inputs=(
            _p("交互对象", "In", type_expr="Ety", var_type=VarType.Ety, index=0),
        ),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
            _p("玩家", "Out", type_expr="Ety", var_type=VarType.Ety, index=1),
        ),
        deprecated=True,
    ),

    # ═══════════════════════════════════════════════════════════════
    # 动作节点 (Action Nodes)
    # ═══════════════════════════════════════════════════════════════

    # ── type_id=69: Destroy_Entity (销毁实体) ──  [真实 ID=69, 原名 "销毁实体"]
    # 编辑器: 流程入, 目标实体(Ety,idx=0), 流程出
    NodeDef(
        type_id=69,
        name="销毁实体",
        category="action",
        description="销毁指定的实体",
        inputs=(
            _p("入", "In", is_flow=True, index=0),
            _p("目标实体", "In", type_expr="Ety", var_type=VarType.Ety, index=0),
        ),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
        ),
    ),

    # ── type_id=200002: Move_Entity (移动实体) ──
    NodeDef(
        type_id=200002,
        name="移动实体",
        category="action",
        description="将实体移动到指定位置",
        inputs=(
            _p("入", "In", is_flow=True, index=0),
            _p("实体", "In", type_expr="Ety", var_type=VarType.Ety, index=1),
            _p("目标位置", "In", type_expr="Vec", var_type=VarType.Vec, index=2),
        ),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
        ),
    ),

    # ── type_id=200003: Set_Entity_Visible (设置实体可见性) ──
    NodeDef(
        type_id=200003,
        name="设置实体可见性",
        category="action",
        description="设置实体是否可见",
        inputs=(
            _p("入", "In", is_flow=True, index=0),
            _p("实体", "In", type_expr="Ety", var_type=VarType.Ety, index=1),
            _p("可见", "In", type_expr="Bol", var_type=VarType.Bol, index=2),
        ),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
        ),
    ),

    # ── type_id=200004: Play_Animation (播放动画) ──
    NodeDef(
        type_id=200004,
        name="播放动画",
        category="action",
        description="在实体上播放指定动画",
        inputs=(
            _p("入", "In", is_flow=True, index=0),
            _p("实体", "In", type_expr="Ety", var_type=VarType.Ety, index=1),
            _p("动画名", "In", type_expr="Str", var_type=VarType.Str, index=2),
        ),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
        ),
    ),

    # ── type_id=200005: Play_Effect (播放特效) ──
    NodeDef(
        type_id=200005,
        name="播放特效",
        category="action",
        description="在指定位置播放特效",
        inputs=(
            _p("入", "In", is_flow=True, index=0),
            _p("特效ID", "In", type_expr="Prefab", var_type=VarType.Prefab, index=1),
            _p("位置", "In", type_expr="Vec", var_type=VarType.Vec, index=2),
        ),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
        ),
    ),

    # ── type_id=200006: Play_Sound (播放音效) ──
    NodeDef(
        type_id=200006,
        name="播放音效",
        category="action",
        description="播放指定音效",
        inputs=(
            _p("入", "In", is_flow=True, index=0),
            _p("音效ID", "In", type_expr="Str", var_type=VarType.Str, index=1),
        ),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
        ),
    ),

    # ── type_id=288: Teleport_Player (传送玩家) ──  [真实 ID=288]
    # 来源: node_library.json - 传送指定玩家实体，会根据传送距离决定是否有加载界面
    NodeDef(
        type_id=288,
        name="传送玩家",
        category="action",
        description="传送指定玩家实体，会根据传送距离决定是否有加载界面",
        inputs=(
            _p("入", "In", is_flow=True, index=0),
            _p("玩家实体", "In", type_expr="Ety", var_type=VarType.Ety, index=0),
            _p("目标位置", "In", type_expr="Vec", var_type=VarType.Vec, index=1),
            _p("目标旋转", "In", type_expr="Vec", var_type=VarType.Vec, index=2),
        ),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
        ),
    ),

    # ── type_id=200008: Add_Item (添加道具) ──
    NodeDef(
        type_id=200008,
        name="添加道具",
        category="action",
        description="给玩家添加道具",
        inputs=(
            _p("入", "In", is_flow=True, index=0),
            _p("道具ID", "In", type_expr="Int", var_type=VarType.Int, index=1),
            _p("数量", "In", type_expr="Int", var_type=VarType.Int, index=2),
        ),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
        ),
    ),

    # ═══════════════════════════════════════════════════════════════
    # 条件节点 (Condition Nodes)
    # ═══════════════════════════════════════════════════════════════

    # ── type_id=400001: Compare_Int (比较整数) ──
    NodeDef(
        type_id=400001,
        name="比较整数",
        category="condition",
        description="比较两个整数的大小关系",
        inputs=(
            _p("入", "In", is_flow=True, index=0),
            _p("值A", "In", type_expr="Int", var_type=VarType.Int, index=1),
            _p("值B", "In", type_expr="Int", var_type=VarType.Int, index=2),
        ),
        outputs=(
            _p("等于", "Out", is_flow=True, index=0),
            _p("大于", "Out", is_flow=True, index=1),
            _p("小于", "Out", is_flow=True, index=2),
        ),
    ),

    # ── type_id=400002: Compare_Float (比较浮点数) ──
    NodeDef(
        type_id=400002,
        name="比较浮点数",
        category="condition",
        description="比较两个浮点数的大小关系",
        inputs=(
            _p("入", "In", is_flow=True, index=0),
            _p("值A", "In", type_expr="Flt", var_type=VarType.Flt, index=1),
            _p("值B", "In", type_expr="Flt", var_type=VarType.Flt, index=2),
        ),
        outputs=(
            _p("等于", "Out", is_flow=True, index=0),
            _p("大于", "Out", is_flow=True, index=1),
            _p("小于", "Out", is_flow=True, index=2),
        ),
    ),

    # ── type_id=400003: Is_Null (是否为空) ──
    NodeDef(
        type_id=400003,
        name="是否为空",
        category="condition",
        description="检查实体是否为空（不存在）",
        inputs=(
            _p("入", "In", is_flow=True, index=0),
            _p("实体", "In", type_expr="Ety", var_type=VarType.Ety, index=1),
        ),
        outputs=(
            _p("是", "Out", is_flow=True, index=0),
            _p("否", "Out", is_flow=True, index=1),
        ),
    ),

    # ── type_id=400004: Random_Chance (随机概率) ──
    NodeDef(
        type_id=400004,
        name="随机概率",
        category="condition",
        description="根据概率随机选择分支",
        inputs=(
            _p("入", "In", is_flow=True, index=0),
            _p("概率", "In", type_expr="Flt", var_type=VarType.Flt, index=1),
        ),
        outputs=(
            _p("成功", "Out", is_flow=True, index=0),
            _p("失败", "Out", is_flow=True, index=1),
        ),
    ),

    # ═══════════════════════════════════════════════════════════════
    # 变量节点 (Variable Nodes)
    # ═══════════════════════════════════════════════════════════════

    # ── type_id=19: Set_Local_Variable (设置局部变量) ──  [真实 ID=19]
    NodeDef(
        type_id=19,
        name="设置局部变量",
        category="variable",
        description="设置当前作用域的局部变量值",
        inputs=(
            _p("入", "In", is_flow=True, index=0),
            _p("变量引用", "In", type_expr="Loc", var_type=16, index=1),
            _p("值", "In", type_expr="Int", var_type=VarType.Int, index=2),
        ),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
        ),
    ),

    # ── type_id=500002: Get_Global_Variable (获取全局变量) ──
    NodeDef(
        type_id=500002,
        name="获取全局变量",
        category="variable",
        description="读取全局变量的值",
        inputs=(
            _p("变量名", "In", type_expr="Str", var_type=VarType.Str, index=0),
        ),
        outputs=(
            _p("值", "Out", type_expr="Int", var_type=VarType.Int, index=0),
        ),
    ),

    # ── type_id=500003: Set_Global_Variable (设置全局变量) ──
    NodeDef(
        type_id=500003,
        name="设置全局变量",
        category="variable",
        description="设置全局变量的值",
        inputs=(
            _p("入", "In", is_flow=True, index=0),
            _p("变量名", "In", type_expr="Str", var_type=VarType.Str, index=1),
            _p("值", "In", type_expr="Int", var_type=VarType.Int, index=2),
        ),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
        ),
    ),

    # ═══════════════════════════════════════════════════════════════
    # 数学节点 (Math Nodes)
    # ═══════════════════════════════════════════════════════════════

    # ── type_id=600001: Add_Int (整数加法) ──
    NodeDef(
        type_id=600001,
        name="整数加法",
        category="math",
        description="两个整数相加",
        inputs=(
            _p("A", "In", type_expr="Int", var_type=VarType.Int, index=0),
            _p("B", "In", type_expr="Int", var_type=VarType.Int, index=1),
        ),
        outputs=(
            _p("结果", "Out", type_expr="Int", var_type=VarType.Int, index=0),
        ),
    ),

    # ── type_id=600002: Subtract_Int (整数减法) ──
    NodeDef(
        type_id=600002,
        name="整数减法",
        category="math",
        description="两个整数相减",
        inputs=(
            _p("A", "In", type_expr="Int", var_type=VarType.Int, index=0),
            _p("B", "In", type_expr="Int", var_type=VarType.Int, index=1),
        ),
        outputs=(
            _p("结果", "Out", type_expr="Int", var_type=VarType.Int, index=0),
        ),
    ),

    # ── type_id=600003: Multiply_Int (整数乘法) ──
    NodeDef(
        type_id=600003,
        name="整数乘法",
        category="math",
        description="两个整数相乘",
        inputs=(
            _p("A", "In", type_expr="Int", var_type=VarType.Int, index=0),
            _p("B", "In", type_expr="Int", var_type=VarType.Int, index=1),
        ),
        outputs=(
            _p("结果", "Out", type_expr="Int", var_type=VarType.Int, index=0),
        ),
    ),

    # ── type_id=600004: Divide_Int (整数除法) ──
    NodeDef(
        type_id=600004,
        name="整数除法",
        category="math",
        description="两个整数相除",
        inputs=(
            _p("A", "In", type_expr="Int", var_type=VarType.Int, index=0),
            _p("B", "In", type_expr="Int", var_type=VarType.Int, index=1),
        ),
        outputs=(
            _p("结果", "Out", type_expr="Int", var_type=VarType.Int, index=0),
        ),
    ),

    # ── type_id=600005: Add_Float (浮点数加法) ──
    NodeDef(
        type_id=600005,
        name="浮点数加法",
        category="math",
        description="两个浮点数相加",
        inputs=(
            _p("A", "In", type_expr="Flt", var_type=VarType.Flt, index=0),
            _p("B", "In", type_expr="Flt", var_type=VarType.Flt, index=1),
        ),
        outputs=(
            _p("结果", "Out", type_expr="Flt", var_type=VarType.Flt, index=0),
        ),
    ),

    # ── type_id=600006: Random_Int (随机整数) ──
    NodeDef(
        type_id=600006,
        name="随机整数",
        category="math",
        description="生成指定范围内的随机整数",
        inputs=(
            _p("最小值", "In", type_expr="Int", var_type=VarType.Int, index=0),
            _p("最大值", "In", type_expr="Int", var_type=VarType.Int, index=1),
        ),
        outputs=(
            _p("结果", "Out", type_expr="Int", var_type=VarType.Int, index=0),
        ),
    ),

    # ═══════════════════════════════════════════════════════════════
    # 逻辑节点 (Logic Nodes)
    # ═══════════════════════════════════════════════════════════════

    # ── type_id=700001: And (逻辑与) ──
    NodeDef(
        type_id=700001,
        name="逻辑与",
        category="logic",
        description="逻辑与运算",
        inputs=(
            _p("A", "In", type_expr="Bol", var_type=VarType.Bol, index=0),
            _p("B", "In", type_expr="Bol", var_type=VarType.Bol, index=1),
        ),
        outputs=(
            _p("结果", "Out", type_expr="Bol", var_type=VarType.Bol, index=0),
        ),
    ),

    # ── type_id=700002: Or (逻辑或) ──
    NodeDef(
        type_id=700002,
        name="逻辑或",
        category="logic",
        description="逻辑或运算",
        inputs=(
            _p("A", "In", type_expr="Bol", var_type=VarType.Bol, index=0),
            _p("B", "In", type_expr="Bol", var_type=VarType.Bol, index=1),
        ),
        outputs=(
            _p("结果", "Out", type_expr="Bol", var_type=VarType.Bol, index=0),
        ),
    ),

    # ── type_id=700003: Not (逻辑非) ──
    NodeDef(
        type_id=700003,
        name="逻辑非",
        category="logic",
        description="逻辑非运算",
        inputs=(
            _p("输入", "In", type_expr="Bol", var_type=VarType.Bol, index=0),
        ),
        outputs=(
            _p("结果", "Out", type_expr="Bol", var_type=VarType.Bol, index=0),
        ),
    ),

    # ═══════════════════════════════════════════════════════════════
    # 实用节点 (Utility Nodes)
    # ═══════════════════════════════════════════════════════════════

    # ── type_id=800001: Delay (延迟) ──
    NodeDef(
        type_id=800001,
        name="延迟",
        category="utility",
        description="延迟指定时间后继续执行",
        inputs=(
            _p("入", "In", is_flow=True, index=0),
            _p("延迟(秒)", "In", type_expr="Flt", var_type=VarType.Flt, index=1),
        ),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
        ),
    ),

    # ── type_id=800002: Once (只执行一次) ──
    NodeDef(
        type_id=800002,
        name="只执行一次",
        category="utility",
        description="只在第一次被触发时执行",
        inputs=(
            _p("入", "In", is_flow=True, index=0),
        ),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
        ),
    ),

    # ── type_id=800003: Log (日志输出) ──
    NodeDef(
        type_id=800003,
        name="日志输出",
        category="utility",
        description="输出日志信息",
        inputs=(
            _p("入", "In", is_flow=True, index=0),
            _p("消息", "In", type_expr="Str", var_type=VarType.Str, index=1),
        ),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
        ),
    ),

    # ── type_id=800004: Get_Player (获取玩家实体) ──
    NodeDef(
        type_id=800004,
        name="获取玩家实体",
        category="utility",
        description="获取当前玩家实体",
        inputs=(),
        outputs=(
            _p("玩家", "Out", type_expr="Ety", var_type=VarType.Ety, index=0),
        ),
    ),

    # ── type_id=200030: Get_Entity_Position (获取实体位置) ──  [真实 ID=200030]
    NodeDef(
        type_id=200030,
        name="获取实体位置",
        category="utility",
        description="获取实体的当前位置",
        inputs=(
            _p("实体", "In", type_expr="Ety", var_type=VarType.Ety, index=0),
        ),
        outputs=(
            _p("位置", "Out", type_expr="Vec", var_type=VarType.Vec, index=0),
        ),
    ),

    # ── 来自示例关卡资产的节点（16个） ──────────────────────

    # type_id=36: 自定义变量变化时（事件）
    NodeDef(
        type_id=36,
        name="自定义变量变化时",
        category="event",
        description="当自定义变量发生变化时触发",
        inputs=(),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
            _p("事件源实体", "Out", type_expr="Ety", var_type=VarType.Ety, index=1),
            _p("事件源GUID", "Out", type_expr="GUID", var_type=VarType.GUID, index=2),
            _p("变量名", "Out", type_expr="Str", var_type=VarType.Str, index=3),
            _p("变化前值", "Out", type_expr="gen", var_type=0, index=4),
            _p("变化后值", "Out", type_expr="gen", var_type=0, index=5),
        ),
    ),

    # type_id=90: 激活/关闭碰撞触发器
    NodeDef(
        type_id=90,
        name="激活/关闭碰撞触发器",
        category="entity",
        description="设置碰撞触发器的激活状态",
        inputs=(
            _p("入", "In", is_flow=True, index=0),
            _p("目标实体", "In", type_expr="Ety", var_type=VarType.Ety, index=1),
            _p("触发器索引", "In", type_expr="Int", var_type=VarType.Int, index=2),
            _p("激活", "In", type_expr="Bol", var_type=VarType.Bol, index=3),
        ),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
        ),
    ),

    # type_id=93: 播放限时特效
    # type_id=94: 挂载循环特效（结构类似）
    # 根据官方定义修正，添加默认值
    # 注意：特效资产的 var_type=20 (Cfg)，不是 0
    NodeDef(
        type_id=93,
        name="播放限时特效",
        category="effect",
        description="在实体位置播放限时特效",
        inputs=(
            _p("入", "In", is_flow=True, index=0),
            _p("特效资产", "In", type_expr="cfg", var_type=20, index=1, default_value=3),  # var_type=20 (Cfg)
            _p("目标实体", "In", type_expr="Ety", var_type=VarType.Ety, index=2),
            _p("挂接点名称", "In", type_expr="Str", var_type=VarType.Str, index=3, default_value="G1_RootNode"),
            _p("是否跟随目标运动", "In", type_expr="Bol", var_type=VarType.Bol, index=4, default_value=True),
            _p("是否跟随目标旋转", "In", type_expr="Bol", var_type=VarType.Bol, index=5, default_value=True),
            _p("位置偏移", "In", type_expr="Vec", var_type=VarType.Vec, index=6, default_value="(0, 0, 20)"),
            _p("旋转偏移", "In", type_expr="Vec", var_type=VarType.Vec, index=7, default_value="(0, 0, 0)"),
            _p("缩放倍率", "In", type_expr="Flt", var_type=VarType.Flt, index=8, default_value=1.0),
            _p("是否播放自带的音效", "In", type_expr="Bol", var_type=VarType.Bol, index=9, default_value=True),
        ),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
        ),
    ),
    NodeDef(
        type_id=94,
        name="挂载循环特效",
        category="effect",
        description="在实体位置挂载循环特效",
        inputs=(
            _p("入", "In", is_flow=True, index=0),
            _p("特效资产配置ID", "In", type_expr="cfg", var_type=0, index=1),
            _p("位置", "In", type_expr="Vec", var_type=VarType.Vec, index=2),
            _p("旋转", "In", type_expr="Vec", var_type=VarType.Vec, index=3),
            _p("缩放倍率", "In", type_expr="Flt", var_type=VarType.Flt, index=4),
            _p("是否播放默认音效", "In", type_expr="Bol", var_type=VarType.Bol, index=5),
        ),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
        ),
    ),

    # type_id=99: 获取实体位置与旋转
    NodeDef(
        type_id=99,
        name="获取实体位置与旋转",
        category="query",
        description="获取实体的位置和旋转",
        inputs=(
            _p("目标实体", "In", type_expr="Ety", var_type=VarType.Ety, index=0),
        ),
        outputs=(
            _p("位置", "Out", type_expr="Vec", var_type=VarType.Vec, index=0),
            _p("旋转", "Out", type_expr="Vec", var_type=VarType.Vec, index=1),
        ),
    ),

    # type_id=200: 加法运算
    NodeDef(
        type_id=200,
        name="加法运算",
        category="calc",
        description="A + B",
        inputs=(
            _p("A", "In", type_expr="Int", var_type=VarType.Int, index=0),
            _p("B", "In", type_expr="Int", var_type=VarType.Int, index=1),
        ),
        outputs=(
            _p("结果", "Out", type_expr="Int", var_type=VarType.Int, index=0),
        ),
    ),

    # type_id=233: 数值大于等于
    NodeDef(
        type_id=233,
        name="数值大于等于",
        category="calc",
        description="A >= B",
        inputs=(
            _p("A", "In", type_expr="Int", var_type=VarType.Int, index=0),
            _p("B", "In", type_expr="Int", var_type=VarType.Int, index=1),
        ),
        outputs=(
            _p("结果", "Out", type_expr="Bol", var_type=VarType.Bol, index=0),
        ),
    ),

    # type_id=267: 激活基础运动器
    NodeDef(
        type_id=267,
        name="激活基础运动器",
        category="entity",
        description="激活实体的基础运动组件",
        inputs=(
            _p("入", "In", is_flow=True, index=0),
            _p("目标实体", "In", type_expr="Ety", var_type=VarType.Ety, index=1),
            _p("运动器类型", "In", type_expr="Str", var_type=VarType.Str, index=2),
        ),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
        ),
    ),

    # type_id=306: 激活/关闭选项卡
    NodeDef(
        type_id=306,
        name="激活/关闭选项卡",
        category="ui",
        description="设置选项卡的激活状态",
        inputs=(
            _p("目标实体", "In", type_expr="Ety", var_type=VarType.Ety, index=0),
            _p("选项卡索引", "In", type_expr="Int", var_type=VarType.Int, index=1),
            _p("激活", "In", type_expr="Bol", var_type=VarType.Bol, index=2),
        ),
        outputs=(),
    ),

    # type_id=307: 选项卡选中时（事件）
    NodeDef(
        type_id=307,
        name="选项卡选中时",
        category="event",
        description="当选项卡被选中时触发（官方定义）",
        inputs=(),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
            _p("事件源实体", "Out", type_expr="Ety", var_type=VarType.Ety, index=1),
            _p("事件源GUID", "Out", type_expr="GUID", var_type=VarType.GUID, index=2),
            _p("选项卡序号", "Out", type_expr="Int", var_type=VarType.Int, index=3),
            _p("选择者实体", "Out", type_expr="Ety", var_type=VarType.Ety, index=4),
        ),
    ),

    # type_id=373: 实体销毁时（事件）
    NodeDef(
        type_id=373,
        name="实体销毁时",
        category="event",
        description="当实体被销毁时触发（NODE_REFERENCE.md 定义）",
        inputs=(),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
            _p("事件源实体", "Out", type_expr="Ety", var_type=VarType.Ety, index=1),
            _p("事件源GUID", "Out", type_expr="GUID", var_type=VarType.GUID, index=2),
            _p("位置", "Out", type_expr="Vec", var_type=VarType.Vec, index=3),
            _p("朝向", "Out", type_expr="Vec", var_type=VarType.Vec, index=4),
            _p("实体类型", "Out", type_expr="Eum", var_type=0, index=5),
            _p("阵营", "Out", type_expr="Eum", var_type=0, index=6),
            _p("伤害来源", "Out", type_expr="Ety", var_type=VarType.Ety, index=7),
            _p("归属者实体", "Out", type_expr="Ety", var_type=VarType.Ety, index=8),
            _p("自定义变量组件快照", "Out", type_expr="Cus", var_type=0, index=9),
        ),
    ),

    # type_id=389: 更改玩家职业
    # 可变参数节点：支持多个目标实体
    NodeDef(
        type_id=389,
        name="更改玩家职业",
        category="player",
        description="更改玩家的职业",
        inputs=(
            _p("入", "In", is_flow=True, index=0),
            _p("目标实体", "In", type_expr="Ety", var_type=VarType.Ety, index=1),
        ),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
        ),
    ),

    # type_id=391: 更改玩家当前职业等级
    NodeDef(
        type_id=391,
        name="更改玩家当前职业等级",
        category="player",
        description="设置玩家的当前职业等级",
        inputs=(
            _p("目标实体", "In", type_expr="Ety", var_type=VarType.Ety, index=0),
            _p("等级", "In", type_expr="Int", var_type=VarType.Int, index=1),
        ),
        outputs=(),
    ),

    # type_id=473: 根据特效资产清除特效
    NodeDef(
        type_id=473,
        name="根据特效资产清除特效",
        category="effect",
        description="清除指定特效资产的特效",
        inputs=(
            _p("入", "In", is_flow=True, index=0),
            _p("目标实体", "In", type_expr="Ety", var_type=VarType.Ety, index=1),
        ),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
        ),
    ),

    # type_id=652: 设置玩家结算成功状态
    NodeDef(
        type_id=652,
        name="设置玩家结算成功状态",
        category="player",
        description="设置玩家的关卡结算成功状态",
        inputs=(
            _p("入", "In", is_flow=True, index=0),
            _p("目标实体", "In", type_expr="Ety", var_type=VarType.Ety, index=1),
            _p("结算状态", "In", type_expr="UInt", var_type=14, index=2),
        ),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
        ),
    ),

    # type_id=3360: 查询自定义变量快照
    NodeDef(
        type_id=3360,
        name="查询自定义变量快照",
        category="query",
        description="查询玩家自定义变量的历史快照",
        inputs=(
            _p("目标实体", "In", type_expr="Ety", var_type=VarType.Ety, index=0),
            _p("变量名", "In", type_expr="Str", var_type=VarType.Str, index=1),
        ),
        outputs=(
            _p("快照值", "Out", type_expr="Str", var_type=VarType.Str, index=0),
        ),
    ),
]

# ═══════════════════════════════════════════════════════════════
# 🔄 2026-05-20 扩充节点（从 index.json + semantic_map，均为高/中置信度）
# ═══════════════════════════════════════════════════════════════
_EXPANDED_NODES: List[NodeDef] = [
    # ── type_id=1: Print_String (打印字符串) [high] ──
    NodeDef(
        type_id=1,
        name="打印字符串",
        category="utility",
        description="在日志中打印字符串信息",
        inputs=(
            _p("入", "In", is_flow=True, index=0),
            _p("字符串", "In", type_expr="Str", var_type=VarType.Str, index=1),
        ),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
        ),
    ),

    # ── type_id=2: Branch (双分支) [medium] ──
    # 编辑器: 流程入, 条件(Bol,idx=0), 是(flow), 否(flow)
    NodeDef(
        type_id=2,
        name="双分支",
        category="condition",
        description="根据布尔条件分支：是时执行「是」，否时执行「否」（if/else）",
        inputs=(
            _p("入", "In", is_flow=True, index=0),
            _p("条件", "In", type_expr="Bol", var_type=VarType.Bol, index=0, default_value=False),
        ),
        outputs=(
            _p("是", "Out", is_flow=True, index=0),
            _p("否", "Out", is_flow=True, index=1),
        ),
    ),

    # ── type_id=14: Equal (是否相等) [high] ──
    # 编辑器: 输入1(gen,idx=0), 输入2(gen,idx=1) → 结果(Bol,idx=0)
    NodeDef(
        type_id=14,
        name="是否相等",
        category="condition",
        description="比较两个值是否相等，返回布尔结果",
        inputs=(
            _p("输入1", "In", type_expr="gen", var_type=VarType.Int, index=0),
            _p("输入2", "In", type_expr="gen", var_type=VarType.Int, index=1),
        ),
        outputs=(
            _p("结果", "Out", type_expr="Bol", var_type=VarType.Bol, index=0),
        ),
    ),

    # ── type_id=19: Set_Local_Variable (设置局部变量) ── [已在主列表中修复]
    
    # ── type_id=22: Set_Custom_Variable (设置自定义变量) [high] ──
    # 编辑器: 流程入, 目标实体(Ety,idx=0), 变量名(Str,idx=1), 变量值(gen,idx=2), 是否触发事件(Bol,idx=3)
    NodeDef(
        type_id=22,
        name="设置自定义变量",
        category="variable",
        description="为实体设置自定义变量值",
        inputs=(
            _p("入", "In", is_flow=True, index=0),
            _p("目标实体", "In", type_expr="Ety", var_type=VarType.Ety, index=0),
            _p("变量名", "In", type_expr="Str", var_type=VarType.Str, index=1),
            _p("变量值", "In", type_expr="gen", var_type=VarType.Int, index=2),
            _p("是否触发事件", "In", type_expr="Bol", var_type=VarType.Bol, index=3, default_value=False),
        ),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
        ),
    ),

    # ── type_id=50: Get_Custom_Variable (获取自定义变量) [high] ──
    # 从示例关卡提取的真实引脚：3个端口
    NodeDef(
        type_id=50,
        name="获取自定义变量",
        category="variable",
        description="读取玩家的自定义变量值",
        inputs=(
            _p("目标实体", "In", type_expr="", var_type=1, index=0),    # Ety 类型（玩家实体）
            _p("变量名", "In", type_expr="", var_type=6, index=1),      # Str 类型
        ),
        outputs=(
            _p("值", "Out", type_expr="", var_type=3, index=0),        # Int 类型
        ),
    ),

    # ── type_id=259: Get_Player_Entity (获取角色归属的玩家实体) ──
    # 编辑器: 角色实体(Ety,idx=0) → 所属玩家实体(Ety,idx=0)
    NodeDef(
        type_id=259,
        name="获取角色归属的玩家实体",
        category="entity",
        description="从角色获取对应的玩家实体引用（用于设置/读取玩家身上的变量）",
        inputs=(
            _p("角色实体", "In", type_expr="Ety", var_type=VarType.Ety, index=0),
        ),
        outputs=(
            _p("所属玩家实体", "Out", type_expr="Ety", var_type=VarType.Ety, index=0),
        ),
    ),

    # ── type_id=70: Create_Entity (创建实体) [high] ──
    NodeDef(
        type_id=70,
        name="创建实体",
        category="action",
        description="根据GUID创建实体。要求预先将其布设在场景内",
        inputs=(
            _p("入", "In", is_flow=True, index=0),
            _p("目标GUID", "In", type_expr="Gid", var_type=VarType.GUID, index=1),
            _p("单位标签索引列表", "In", type_expr="IntArr", var_type=VarType.IntArr, index=2),
        ),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
        ),
    ),

    # ── type_id=71: On_Entity_Created (实体创建时) [high] ──
    NodeDef(
        type_id=71,
        name="实体创建时",
        category="event",
        description="当实体被创建时触发",
        inputs=(
            _p("实体", "In", type_expr="Ety", var_type=VarType.Ety, index=0),
        ),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
        ),
    ),

    # ── type_id=73: Get_Self (获取自身实体) [high] ──
    NodeDef(
        type_id=73,
        name="获取自身实体",
        category="utility",
        description="获取当前执行上下文的自身实体",
        inputs=(),
        outputs=(
            _p("实体", "Out", type_expr="Ety", var_type=VarType.Ety, index=0),
        ),
    ),

    # ── type_id=79: Start_Timer (启动定时器) [high] ──
    # 根据截图修正：目标实体、定时器名称、是否循环、定时器序列
    NodeDef(
        type_id=79,
        name="启动定时器",
        category="utility",
        description="启动一个定时器，时间到后触发后续逻辑",
        inputs=(
            _p("入", "In", is_flow=True, index=0),
            _p("目标实体", "Target", type_expr="Ety", var_type=VarType.Ety, index=1),
            _p("定时器名称", "Name", type_expr="Str", var_type=VarType.Str, index=2),
            _p("是否循环", "Loop", type_expr="Bol", var_type=VarType.Bol, index=3),
            _p("定时器序列", "Sequence", type_expr="Int", var_type=VarType.Int, index=4),
        ),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
        ),
    ),

    # ── type_id=114: List_Contains (列表是否包含该值) [medium] ──
    NodeDef(
        type_id=114,
        name="列表是否包含该值",
        category="condition",
        description="检查列表中是否包含指定的值",
        inputs=(
            _p("列表", "In", type_expr="", var_type=0, index=0),
            _p("值", "In", type_expr="", var_type=0, index=1),
        ),
        outputs=(
            _p("结果", "Out", type_expr="Bol", var_type=VarType.Bol, index=0),
        ),
    ),

    # ── type_id=135: List_Insert (对列表插入值) [medium] ──
    NodeDef(
        type_id=135,
        name="对列表插入值",
        category="action",
        description="向列表中指定位置插入一个值",
        inputs=(
            _p("入", "In", is_flow=True, index=0),
            _p("列表", "In", type_expr="", var_type=0, index=1),
            _p("索引", "In", type_expr="Int", var_type=VarType.Int, index=2),
            _p("值", "In", type_expr="", var_type=0, index=3),
        ),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
        ),
    ),

    # ── type_id=160: List_Modify (对列表修改值) [medium] ──
    NodeDef(
        type_id=160,
        name="对列表修改值",
        category="action",
        description="修改列表中指定索引位置的元素",
        inputs=(
            _p("入", "In", is_flow=True, index=0),
            _p("列表", "In", type_expr="", var_type=0, index=1),
            _p("索引", "In", type_expr="Int", var_type=VarType.Int, index=2),
            _p("值", "In", type_expr="", var_type=0, index=3),
        ),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
        ),
    ),

    # ── type_id=225: Create_Vector3 (创建三维向量) [medium] ──
    NodeDef(
        type_id=225,
        name="创建三维向量",
        category="math",
        description="通过三个浮点数分量创建三维向量 (x, y, z)",
        inputs=(
            _p("X", "In", type_expr="Flt", var_type=VarType.Flt, index=0),
            _p("Y", "In", type_expr="Flt", var_type=VarType.Flt, index=1),
            _p("Z", "In", type_expr="Flt", var_type=VarType.Flt, index=2),
        ),
        outputs=(
            _p("向量", "Out", type_expr="Vec", var_type=VarType.Vec, index=0),
        ),
    ),

    # ── type_id=227: Logic_Or_Op (逻辑或运算) [medium] ──
    NodeDef(
        type_id=227,
        name="逻辑或运算",
        category="logic",
        description="对两个布尔值进行逻辑或运算",
        inputs=(
            _p("A", "In", type_expr="Bol", var_type=VarType.Bol, index=0),
            _p("B", "In", type_expr="Bol", var_type=VarType.Bol, index=1),
        ),
        outputs=(
            _p("结果", "Out", type_expr="Bol", var_type=VarType.Bol, index=0),
        ),
    ),

    # ── type_id=279: Revive_Character (复苏角色) [medium] ──
    NodeDef(
        type_id=279,
        name="复苏角色",
        category="action",
        description="复活一个已死亡的角色",
        inputs=(
            _p("入", "In", is_flow=True, index=0),
            _p("角色", "In", type_expr="Ety", var_type=VarType.Ety, index=1),
        ),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
        ),
    ),

    # ── type_id=303: Attack (发起攻击) [medium] ──
    NodeDef(
        type_id=303,
        name="发起攻击",
        category="action",
        description="对目标发起攻击",
        inputs=(
            _p("入", "In", is_flow=True, index=0),
            _p("攻击者", "In", type_expr="Ety", var_type=VarType.Ety, index=1),
            _p("目标", "In", type_expr="Ety", var_type=VarType.Ety, index=2),
        ),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
        ),
    ),

    # ── type_id=311: Start_Global_Timer (启动全局计时器) [high] ──
    NodeDef(
        type_id=311,
        name="启动全局计时器",
        category="utility",
        description="启动一个全局计时器（不依赖实体），时间到后触发事件",
        inputs=(
            _p("入", "In", is_flow=True, index=0),
            _p("时长(秒)", "In", type_expr="Flt", var_type=VarType.Flt, index=1),
        ),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
        ),
    ),

    # ── type_id=592: Start_Stop_Audio_Player (启动/暂停指定音效播放器) [medium] ──
    NodeDef(
        type_id=592,
        name="启动/暂停指定音效播放器",
        category="action",
        description="启动或暂停指定的音效播放器",
        inputs=(
            _p("入", "In", is_flow=True, index=0),
            _p("播放器", "In", type_expr="Ety", var_type=VarType.Ety, index=1),
        ),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
        ),
    ),

    # ── type_id=595: Start_Stop_BGM (启动/暂停玩家背景音乐) [medium] ──
    NodeDef(
        type_id=595,
        name="启动/暂停玩家背景音乐",
        category="action",
        description="启动或暂停玩家的背景音乐",
        inputs=(
            _p("入", "In", is_flow=True, index=0),
        ),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
        ),
    ),

    # ── type_id=597: Modify_BGM (修改玩家背景音乐) [medium] ──
    NodeDef(
        type_id=597,
        name="修改玩家背景音乐",
        category="action",
        description="修改玩家的背景音乐",
        inputs=(
            _p("入", "In", is_flow=True, index=0),
            _p("音乐ID", "In", type_expr="Int", var_type=VarType.Int, index=1),
        ),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
        ),
    ),

    # ── type_id=763: Modify_Env_Config (修改环境配置) [medium] ──
    NodeDef(
        type_id=763,
        name="修改环境配置",
        category="action",
        description="修改游戏环境配置参数",
        inputs=(
            _p("入", "In", is_flow=True, index=0),
            _p("配置", "In", type_expr="", var_type=0, index=1),
        ),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
        ),
    ),

    # ── type_id=256: Create_Projectile (创建投射物) [high] ──
    NodeDef(
        type_id=256,
        name="创建投射物",
        category="action",
        description="在场景中创建一个投射物",
        inputs=(
            _p("入", "In", is_flow=True, index=0),
            _p("投射物ID", "In", type_expr="Prefab", var_type=VarType.Prefab, index=1),
            _p("起始位置", "In", type_expr="Vec", var_type=VarType.Vec, index=2),
            _p("方向", "In", type_expr="Vec", var_type=VarType.Vec, index=3),
        ),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
            _p("投射物", "Out", type_expr="Ety", var_type=VarType.Ety, index=1),
        ),
    ),

    # ═══════════════════════════════════════════════════════════════
    # 🔄 第三批扩充节点（2026-05-20 下午）：循环、数学向量、实体管理
    # ═══════════════════════════════════════════════════════════════

    # ── type_id=5: Finite_Loop (有限循环) [manual] ──
    NodeDef(
        type_id=5,
        name="有限循环",
        category="loop",
        description="执行指定次数的循环，类似 for 循环",
        inputs=(
            _p("入", "In", is_flow=True, index=0),
            _p("起始值", "In", type_expr="Int", var_type=VarType.Int, index=1),
            _p("结束值", "In", type_expr="Int", var_type=VarType.Int, index=2),
        ),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
            _p("索引", "Out", type_expr="Int", var_type=VarType.Int, index=1),
        ),
    ),

    # ── type_id=6: Break_Loop (跳出循环) [manual] ──
    NodeDef(
        type_id=6,
        name="跳出循环",
        category="loop",
        description="跳出当前循环",
        inputs=(
            _p("入", "In", is_flow=True, index=0),
        ),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
        ),
    ),

    # ── type_id=7: Get_Random_Float (获取随机浮点数) [manual] ──
    NodeDef(
        type_id=7,
        name="获取随机浮点数",
        category="math",
        description="生成指定范围内的随机浮点数",
        inputs=(
            _p("最小值", "In", type_expr="Flt", var_type=VarType.Flt, index=0),
            _p("最大值", "In", type_expr="Flt", var_type=VarType.Flt, index=1),
        ),
        outputs=(
            _p("结果", "Out", type_expr="Flt", var_type=VarType.Flt, index=0),
        ),
    ),

    # ── type_id=8: Weighted_Random (权重随机) [manual] ──
    NodeDef(
        type_id=8,
        name="权重随机",
        category="math",
        description="根据权重列表随机选择一个索引",
        inputs=(
            _p("权重列表", "In", type_expr="IntArr", var_type=VarType.IntArr, index=0),
        ),
        outputs=(
            _p("索引", "Out", type_expr="Int", var_type=VarType.Int, index=0),
        ),
    ),

    # ── type_id=9: Split_Vector (拆分三维向量) [manual] ──
    NodeDef(
        type_id=9,
        name="拆分三维向量",
        category="math",
        description="将三维向量拆分为三个浮点数分量 (x, y, z)",
        inputs=(
            _p("向量", "In", type_expr="Vec", var_type=VarType.Vec, index=0),
        ),
        outputs=(
            _p("X", "Out", type_expr="Flt", var_type=VarType.Flt, index=0),
            _p("Y", "Out", type_expr="Flt", var_type=VarType.Flt, index=1),
            _p("Z", "Out", type_expr="Flt", var_type=VarType.Flt, index=2),
        ),
    ),

    # ── type_id=10: Vector_Add (三维向量加法) [manual] ──
    NodeDef(
        type_id=10,
        name="三维向量加法",
        category="math",
        description="两个三维向量相加",
        inputs=(
            _p("A", "In", type_expr="Vec", var_type=VarType.Vec, index=0),
            _p("B", "In", type_expr="Vec", var_type=VarType.Vec, index=1),
        ),
        outputs=(
            _p("结果", "Out", type_expr="Vec", var_type=VarType.Vec, index=0),
        ),
    ),

    # ── type_id=11: Vector_Subtract (三维向量减法) [manual] ──
    NodeDef(
        type_id=11,
        name="三维向量减法",
        category="math",
        description="两个三维向量相减",
        inputs=(
            _p("A", "In", type_expr="Vec", var_type=VarType.Vec, index=0),
            _p("B", "In", type_expr="Vec", var_type=VarType.Vec, index=1),
        ),
        outputs=(
            _p("结果", "Out", type_expr="Vec", var_type=VarType.Vec, index=0),
        ),
    ),

    # ── type_id=12: Vector_Scale (三维向量缩放) [manual] ──
    NodeDef(
        type_id=12,
        name="三维向量缩放",
        category="math",
        description="对三维向量进行缩放（乘以一个浮点数）",
        inputs=(
            _p("向量", "In", type_expr="Vec", var_type=VarType.Vec, index=0),
            _p("倍数", "In", type_expr="Flt", var_type=VarType.Flt, index=1),
        ),
        outputs=(
            _p("结果", "Out", type_expr="Vec", var_type=VarType.Vec, index=0),
        ),
    ),

    # ── type_id=13: Vector_Angle (三维向量夹角) [manual] ──
    NodeDef(
        type_id=13,
        name="三维向量夹角",
        category="math",
        description="计算两个三维向量之间的夹角（弧度）",
        inputs=(
            _p("A", "In", type_expr="Vec", var_type=VarType.Vec, index=0),
            _p("B", "In", type_expr="Vec", var_type=VarType.Vec, index=1),
        ),
        outputs=(
            _p("角度", "Out", type_expr="Flt", var_type=VarType.Flt, index=0),
        ),
    ),

    # ── type_id=250: Modify_Entity_Faction (修改实体阵营) [high] ──
    NodeDef(
        type_id=250,
        name="修改实体阵营",
        category="action",
        description="修改实体的阵营",
        inputs=(
            _p("入", "In", is_flow=True, index=0),
            _p("实体", "In", type_expr="Ety", var_type=VarType.Ety, index=1),
            _p("阵营", "In", type_expr="Faction", var_type=VarType.Faction, index=2),
        ),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
        ),
    ),

    # ── type_id=283: Revive_All_Characters (复苏玩家所有角色) [high] ──
    NodeDef(
        type_id=283,
        name="复苏玩家所有角色",
        category="action",
        description="复活玩家所有已死亡的角色",
        inputs=(
            _p("入", "In", is_flow=True, index=0),
            _p("玩家", "In", type_expr="Ety", var_type=VarType.Ety, index=1),
            _p("满血", "In", type_expr="Bol", var_type=VarType.Bol, index=2),
        ),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
        ),
    ),

    # ── type_id=586: Add_Unit_Tag (实体添加单位标签) [high] ──
    NodeDef(
        type_id=586,
        name="实体添加单位标签",
        category="action",
        description="给实体添加一个单位标签，用于分组和筛选",
        inputs=(
            _p("入", "In", is_flow=True, index=0),
            _p("实体", "In", type_expr="Ety", var_type=VarType.Ety, index=1),
            _p("标签ID", "In", type_expr="Int", var_type=VarType.Int, index=2),
        ),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
        ),
    ),

    # ── type_id=587: Remove_Unit_Tag (实体移除单位标签) [high] ──
    NodeDef(
        type_id=587,
        name="实体移除单位标签",
        category="action",
        description="从实体移除一个单位标签",
        inputs=(
            _p("入", "In", is_flow=True, index=0),
            _p("实体", "In", type_expr="Ety", var_type=VarType.Ety, index=1),
            _p("标签ID", "In", type_expr="Int", var_type=VarType.Int, index=2),
        ),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
        ),
    ),

    # ── type_id=588: Clear_Unit_Tags (实体清空单位标签) [high] ──
    NodeDef(
        type_id=588,
        name="实体清空单位标签",
        category="action",
        description="清除实体的所有单位标签",
        inputs=(
            _p("入", "In", is_flow=True, index=0),
            _p("实体", "In", type_expr="Ety", var_type=VarType.Ety, index=1),
        ),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
        ),
    ),

    # ── type_id=602: Taunt_Target (嘲讽目标) [high] ──
    NodeDef(
        type_id=602,
        name="嘲讽目标",
        category="action",
        description="让一个实体嘲讽另一个实体",
        inputs=(
            _p("入", "In", is_flow=True, index=0),
            _p("嘲讽者", "In", type_expr="Ety", var_type=VarType.Ety, index=1),
            _p("目标", "In", type_expr="Ety", var_type=VarType.Ety, index=2),
        ),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
        ),
    ),

    # ── type_id=947: Query_Move_Speed (查询角色当前移动速度) [manual] ──
    NodeDef(
        type_id=947,
        name="查询角色当前移动速度",
        category="utility",
        description="查询角色的当前移动速度",
        inputs=(
            _p("实体", "In", type_expr="Ety", var_type=VarType.Ety, index=0),
        ),
        outputs=(
            _p("速度", "Out", type_expr="Flt", var_type=VarType.Flt, index=0),
            _p("方向", "Out", type_expr="Vec", var_type=VarType.Vec, index=1),
        ),
    ),

    # ── type_id=1298: Remove_Dict_Entry (以键对字典移除键值对) [high] ──
    NodeDef(
        type_id=1298,
        name="以键对字典移除键值对",
        category="action",
        description="从字典中移除指定键的键值对",
        inputs=(
            _p("入", "In", is_flow=True, index=0),
            _p("字典", "In", type_expr="", var_type=0, index=1),
            _p("键", "In", type_expr="", var_type=0, index=2),
        ),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
        ),
    ),

    # ═══════════════════════════════════════════════════════════════
    # 🔄 Client 节点（客户端专用）
    # ═══════════════════════════════════════════════════════════════

    # ── type_id=200042: Graph_Start (节点图开始) [high] ──
    NodeDef(
        type_id=200042,
        name="节点图开始",
        category="event",
        description="客户端节点图的开始节点",
        inputs=(),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
        ),
    ),

    # ── type_id=200043: Filter_Sphere (筛选球体范围内的实体列表) [manual] ──
    NodeDef(
        type_id=200043,
        name="筛选球体范围内的实体列表",
        category="condition",
        description="筛选球体范围内的实体列表",
        inputs=(
            _p("半径", "In", type_expr="Flt", var_type=VarType.Flt, index=0),
            _p("中心点", "In", type_expr="Vec", var_type=VarType.Vec, index=1),
            _p("阵营过滤", "In", type_expr="Int", var_type=VarType.Int, index=2),
            _p("标签过滤", "In", type_expr="", var_type=0, index=3),
        ),
        outputs=(
            _p("实体列表", "Out", type_expr="EtyArr", var_type=VarType.EtyArr, index=0),
        ),
    ),

    # ── type_id=200044: Filter_Box (筛选方形范围内的实体列表) [manual] ──
    NodeDef(
        type_id=200044,
        name="筛选方形范围内的实体列表",
        category="condition",
        description="筛选方形范围内的实体列表",
        inputs=(
            _p("X半边长", "In", type_expr="Flt", var_type=VarType.Flt, index=0),
            _p("Y半边长", "In", type_expr="Flt", var_type=VarType.Flt, index=1),
            _p("Z半边长", "In", type_expr="Flt", var_type=VarType.Flt, index=2),
            _p("中心点", "In", type_expr="Vec", var_type=VarType.Vec, index=3),
            _p("阵营过滤", "In", type_expr="Int", var_type=VarType.Int, index=4),
            _p("标签过滤", "In", type_expr="", var_type=0, index=5),
        ),
        outputs=(
            _p("实体列表", "Out", type_expr="EtyArr", var_type=VarType.EtyArr, index=0),
        ),
    ),

    # ── type_id=200056: Client_Branch (双分支-客户端) [manual] ──
    NodeDef(
        type_id=200056,
        name="双分支",
        category="condition",
        description="根据布尔条件分支（客户端版本）",
        inputs=(
            _p("条件", "In", type_expr="Bol", var_type=VarType.Bol, index=0),
        ),
        outputs=(
            _p("真", "Out", is_flow=True, index=0, default_value="True"),
            _p("假", "Out", is_flow=True, index=1, default_value="False"),
        ),
    ),

    # ── type_id=200079: Client_Finite_Loop (有限循环-客户端) [manual] ──
    NodeDef(
        type_id=200079,
        name="有限循环",
        category="loop",
        description="执行指定次数的循环（客户端版本）",
        inputs=(
            _p("起始值", "In", type_expr="Int", var_type=VarType.Int, index=0),
            _p("结束值", "In", type_expr="Int", var_type=VarType.Int, index=1),
        ),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
            _p("索引", "Out", type_expr="Int", var_type=VarType.Int, index=1),
        ),
    ),

    # ── type_id=200080: Client_Break_Loop (跳出循环-客户端) [manual] ──
    NodeDef(
        type_id=200080,
        name="跳出循环",
        category="loop",
        description="跳出当前循环（客户端版本）",
        inputs=(),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
        ),
    ),

    # ── type_id=200031: Get_Entity_Rotation (获取实体旋转) [manual] ──
    NodeDef(
        type_id=200031,
        name="获取实体旋转",
        category="query",
        description="获取实体的旋转角度",
        inputs=(
            _p("实体", "In", type_expr="Ety", var_type=VarType.Ety, index=0),
        ),
        outputs=(
            _p("旋转", "Out", type_expr="Vec", var_type=VarType.Vec, index=0),
        ),
    ),

    # ── type_id=200033: Get_Self_Entity (获取自身实体) [manual] ──
    NodeDef(
        type_id=200033,
        name="获取自身实体",
        category="query",
        description="获取当前节点图所属的实体",
        inputs=(),
        outputs=(
            _p("实体", "Out", type_expr="Ety", var_type=VarType.Ety, index=0),
        ),
    ),

    # ── type_id=200038: Play_Effect_Client (播放限时特效-客户端) [manual] ──
    NodeDef(
        type_id=200038,
        name="播放限时特效",
        category="effect",
        description="在指定位置播放限时特效（客户端版本）",
        inputs=(
            _p("特效资产配置ID", "In", type_expr="cfg", var_type=0, index=0),
            _p("位置", "In", type_expr="Vec", var_type=VarType.Vec, index=1),
            _p("旋转", "In", type_expr="Vec", var_type=VarType.Vec, index=2),
            _p("缩放倍率", "In", type_expr="Flt", var_type=VarType.Flt, index=3),
            _p("是否播放默认音效", "In", type_expr="Bol", var_type=VarType.Bol, index=4),
        ),
        outputs=(),
    ),

    # ── type_id=200050: Get_Entity_Type_List (获取实体类型列表) [manual] ──
    NodeDef(
        type_id=200050,
        name="获取实体类型列表",
        category="query",
        description="获取指定类型的实体列表",
        inputs=(
            _p("实体类型", "In", type_expr="Int", var_type=VarType.Int, index=0),
            _p("阵营过滤", "In", type_expr="Int", var_type=VarType.Int, index=1),
            _p("标签过滤", "In", type_expr="Str", var_type=VarType.Str, index=2),
            _p("是否包含子标签", "In", type_expr="Bol", var_type=VarType.Bol, index=3),
            _p("最大数量", "In", type_expr="Int", var_type=VarType.Int, index=4),
            _p("排序方式", "In", type_expr="Int", var_type=VarType.Int, index=5),
            _p("中心点", "In", type_expr="Vec", var_type=VarType.Vec, index=6),
            _p("半径", "In", type_expr="Flt", var_type=VarType.Flt, index=7),
            _p("是否按距离排序", "In", type_expr="Bol", var_type=VarType.Bol, index=8),
            _p("排除自身", "In", type_expr="Bol", var_type=VarType.Bol, index=9),
        ),
        outputs=(
            _p("实体列表", "Out", type_expr="EtyArr", var_type=VarType.EtyArr, index=0),
        ),
    ),

    # ── type_id=200051: Attack_Box_At_Position (特定位置打攻击盒) [manual] ──
    NodeDef(
        type_id=200051,
        name="特定位置打攻击盒",
        category="combat",
        description="在指定位置创建攻击盒，对范围内目标造成伤害",
        inputs=(
            _p("位置", "In", type_expr="Vec", var_type=VarType.Vec, index=0),
            _p("旋转", "In", type_expr="Vec", var_type=VarType.Vec, index=1),
            _p("缩放", "In", type_expr="Vec", var_type=VarType.Vec, index=2),
            _p("攻击盒形状", "In", type_expr="Int", var_type=VarType.Int, index=3),
            _p("攻击盒大小", "In", type_expr="Vec", var_type=VarType.Vec, index=4),
            _p("伤害值", "In", type_expr="Flt", var_type=VarType.Flt, index=5),
            _p("伤害类型", "In", type_expr="Int", var_type=VarType.Int, index=6),
            _p("是否暴击", "In", type_expr="Bol", var_type=VarType.Bol, index=7),
            _p("攻击者", "In", type_expr="Ety", var_type=VarType.Ety, index=8),
            _p("技能ID", "In", type_expr="Int", var_type=VarType.Int, index=9),
            _p("伤害来源", "In", type_expr="Int", var_type=VarType.Int, index=10),
            _p("是否无视防御", "In", type_expr="Bol", var_type=VarType.Bol, index=11),
            _p("是否无视无敌", "In", type_expr="Bol", var_type=VarType.Bol, index=12),
            _p("伤害倍率", "In", type_expr="Flt", var_type=VarType.Flt, index=13),
            _p("额外伤害", "In", type_expr="Flt", var_type=VarType.Flt, index=14),
            _p("伤害浮动率", "In", type_expr="Flt", var_type=VarType.Flt, index=15),
            _p("是否显示伤害数字", "In", type_expr="Bol", var_type=VarType.Bol, index=16),
            _p("伤害数字颜色", "In", type_expr="Int", var_type=VarType.Int, index=17),
            _p("是否击退", "In", type_expr="Bol", var_type=VarType.Bol, index=18),
            _p("击退方向", "In", type_expr="Vec", var_type=VarType.Vec, index=19),
            _p("击退力度", "In", type_expr="Flt", var_type=VarType.Flt, index=20),
            _p("是否眩晕", "In", type_expr="Bol", var_type=VarType.Bol, index=21),
            _p("眩晕时间", "In", type_expr="Flt", var_type=VarType.Flt, index=22),
            _p("是否定身", "In", type_expr="Bol", var_type=VarType.Bol, index=23),
            _p("定身时间", "In", type_expr="Flt", var_type=VarType.Flt, index=24),
            _p("是否沉默", "In", type_expr="Bol", var_type=VarType.Bol, index=25),
            _p("沉默时间", "In", type_expr="Flt", var_type=VarType.Flt, index=26),
            _p("是否致盲", "In", type_expr="Bol", var_type=VarType.Bol, index=27),
            _p("致盲时间", "In", type_expr="Flt", var_type=VarType.Flt, index=28),
            _p("是否减速", "In", type_expr="Bol", var_type=VarType.Bol, index=29),
            _p("减速比例", "In", type_expr="Flt", var_type=VarType.Flt, index=30),
            _p("减速时间", "In", type_expr="Flt", var_type=VarType.Flt, index=31),
            _p("是否吸血", "In", type_expr="Bol", var_type=VarType.Bol, index=32),
            _p("吸血比例", "In", type_expr="Flt", var_type=VarType.Flt, index=33),
            _p("是否反弹", "In", type_expr="Bol", var_type=VarType.Bol, index=34),
            _p("反弹比例", "In", type_expr="Flt", var_type=VarType.Flt, index=35),
            _p("是否穿透", "In", type_expr="Bol", var_type=VarType.Bol, index=36),
            _p("穿透数量", "In", type_expr="Int", var_type=VarType.Int, index=37),
            _p("是否连锁", "In", type_expr="Bol", var_type=VarType.Bol, index=38),
            _p("连锁次数", "In", type_expr="Int", var_type=VarType.Int, index=39),
            _p("连锁范围", "In", type_expr="Flt", var_type=VarType.Flt, index=40),
            _p("是否追踪", "In", type_expr="Bol", var_type=VarType.Bol, index=41),
            _p("追踪速度", "In", type_expr="Flt", var_type=VarType.Flt, index=42),
            _p("追踪角度", "In", type_expr="Flt", var_type=VarType.Flt, index=43),
            _p("持续时间", "In", type_expr="Flt", var_type=VarType.Flt, index=44),
            _p("触发间隔", "In", type_expr="Flt", var_type=VarType.Flt, index=45),
        ),
        outputs=(
            _p("命中实体列表", "Out", type_expr="EtyArr", var_type=VarType.EtyArr, index=0),
        ),
    ),

    # ── type_id=200103: Entity_Is_In_Scene (查询实体是否在场) [manual] ──
    NodeDef(
        type_id=200103,
        name="查询实体是否在场",
        category="condition",
        description="检查实体是否在场（未被销毁）",
        inputs=(
            _p("实体", "In", type_expr="Ety", var_type=VarType.Ety, index=0),
        ),
        outputs=(
            _p("结果", "Out", type_expr="Bol", var_type=VarType.Bol, index=0),
        ),
    ),

    # ═══════════════════════════════════════════════════════════════
    # 🔄 第四批扩充节点（2026-05-20 深度扩充）：关卡制作核心节点
    # ═══════════════════════════════════════════════════════════════

    # ── type_id=66: Set_Preset_Status (设置预设状态) [manual] ──
    NodeDef(
        type_id=66,
        name="设置预设状态",
        category="action",
        description="设置指定目标实体的预设状态",
        inputs=(
            _p("入", "In", is_flow=True, index=0),
            _p("目标实体", "In", type_expr="Ety", var_type=VarType.Ety, index=1),
            _p("预设状态索引", "In", type_expr="Int", var_type=VarType.Int, index=2),
            _p("预设状态值", "In", type_expr="Int", var_type=VarType.Int, index=3),
        ),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
        ),
    ),

    # ── type_id=67: On_Preset_Status_Changes (预设状态变化时) [manual] ──
    NodeDef(
        type_id=67,
        name="预设状态变化时",
        category="event",
        description="当实体的预设状态发生变化时触发",
        inputs=(),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
            _p("实体", "Out", type_expr="Ety", var_type=VarType.Ety, index=1),
            _p("玩家", "Out", type_expr="Gid", var_type=VarType.GUID, index=2),
            _p("旧状态", "Out", type_expr="Int", var_type=VarType.Int, index=3),
            _p("新状态", "Out", type_expr="Int", var_type=VarType.Int, index=4),
        ),
    ),

    # ── type_id=68: Get_Preset_Status (获取预设状态) [manual] ──
    NodeDef(
        type_id=68,
        name="获取预设状态",
        category="utility",
        description="获取实体的当前预设状态值",
        inputs=(
            _p("实体", "In", type_expr="Ety", var_type=VarType.Ety, index=0),
            _p("状态ID", "In", type_expr="Int", var_type=VarType.Int, index=1),
        ),
        outputs=(
            _p("状态值", "Out", type_expr="Int", var_type=VarType.Int, index=0),
        ),
    ),

    # ── type_id=72: On_Entity_Destroyed (实体移除/销毁时) [manual] ──
    NodeDef(
        type_id=72,
        name="实体移除/销毁时",
        category="event",
        description="当实体被移除或销毁时触发",
        inputs=(),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
            _p("实体GUID", "Out", type_expr="Gid", var_type=VarType.GUID, index=1),
        ),
    ),

    # ── type_id=74: Vector_Normalize (三维向量归一化) [manual] ──
    NodeDef(
        type_id=74,
        name="三维向量归一化",
        category="math",
        description="将三维向量归一化为单位向量",
        inputs=(
            _p("向量", "In", type_expr="Vec", var_type=VarType.Vec, index=0),
        ),
        outputs=(
            _p("结果", "Out", type_expr="Vec", var_type=VarType.Vec, index=0),
        ),
    ),

    # ── type_id=75: Query_Entity_By_GUID (以GUID查询实体) [manual] ──
    NodeDef(
        type_id=75,
        name="以GUID查询实体",
        category="utility",
        description="通过 GUID 查询对应的实体",
        inputs=(
            _p("GUID", "In", type_expr="Gid", var_type=VarType.GUID, index=0),
        ),
        outputs=(
            _p("实体", "Out", type_expr="Ety", var_type=VarType.Ety, index=0),
        ),
    ),

    # ── type_id=76: Query_GUID_By_Entity (以实体查询GUID) [manual] ──
    NodeDef(
        type_id=76,
        name="以实体查询GUID",
        category="utility",
        description="通过实体查询对应的 GUID",
        inputs=(
            _p("实体", "In", type_expr="Ety", var_type=VarType.Ety, index=0),
        ),
        outputs=(
            _p("GUID", "Out", type_expr="Gid", var_type=VarType.GUID, index=0),
        ),
    ),

    # ── type_id=77: Settle_Stage (结算关卡) [manual] ──
    # 编辑器: 流程入, 是否胜利(Bol,idx=0), 流程出
    NodeDef(
        type_id=77,
        name="结算关卡",
        category="action",
        description="触发关卡结算（胜利/失败）",
        inputs=(
            _p("入", "In", is_flow=True, index=0),
            _p("是否胜利", "In", type_expr="Bol", var_type=VarType.Bol, index=0),
        ),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
        ),
    ),

    # ── type_id=80: Pause_Timer (暂停定时器) [manual] ──
    NodeDef(
        type_id=80,
        name="暂停定时器",
        category="utility",
        description="暂停指定名称的定时器",
        inputs=(
            _p("入", "In", is_flow=True, index=0),
            _p("实体", "In", type_expr="Ety", var_type=VarType.Ety, index=1),
            _p("定时器名", "In", type_expr="Str", var_type=VarType.Str, index=2),
        ),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
        ),
    ),

    # ── type_id=81: Resume_Timer (恢复定时器) [manual] ──
    NodeDef(
        type_id=81,
        name="恢复定时器",
        category="utility",
        description="恢复指定名称的定时器",
        inputs=(
            _p("入", "In", is_flow=True, index=0),
            _p("实体", "In", type_expr="Ety", var_type=VarType.Ety, index=1),
            _p("定时器名", "In", type_expr="Str", var_type=VarType.Str, index=2),
        ),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
        ),
    ),

    # ── type_id=82: Stop_Timer (终止定时器) [manual] ──
    NodeDef(
        type_id=82,
        name="终止定时器",
        category="utility",
        description="终止指定名称的定时器",
        inputs=(
            _p("入", "In", is_flow=True, index=0),
            _p("实体", "In", type_expr="Ety", var_type=VarType.Ety, index=1),
            _p("定时器名", "In", type_expr="Str", var_type=VarType.Str, index=2),
        ),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
        ),
    ),

    # ── type_id=83: On_Timer_Triggered (定时器触发时) [官方定义] ──
    NodeDef(
        type_id=83,
        name="定时器触发时",
        category="event",
        description="定时器运行到指定时间节点时，触发该事件（官方定义）",
        inputs=(),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
            _p("事件源实体", "Out", type_expr="Ety", var_type=VarType.Ety, index=1),
            _p("事件源GUID", "Out", type_expr="GUID", var_type=VarType.GUID, index=2),
            _p("定时器名称", "Out", type_expr="Str", var_type=VarType.Str, index=3),
            _p("定时器序列序号", "Out", type_expr="Int", var_type=VarType.Int, index=4),
            _p("循环次数", "Out", type_expr="Int", var_type=VarType.Int, index=5),
        ),
    ),

    # ── type_id=314: Modify_Global_Timer (修改全局计时器) [high] ──
    NodeDef(
        type_id=314,
        name="修改全局计时器",
        category="utility",
        description="修改全局计时器的剩余时间",
        inputs=(
            _p("入", "In", is_flow=True, index=0),
            _p("实体", "In", type_expr="Ety", var_type=VarType.Ety, index=1),
            _p("计时器名", "In", type_expr="Str", var_type=VarType.Str, index=2),
            _p("时间", "In", type_expr="Flt", var_type=VarType.Flt, index=3),
        ),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
        ),
    ),

    # ── type_id=664: Query_Env_Time (查询当前环境时间) [manual] ──
    NodeDef(
        type_id=664,
        name="查询当前环境时间",
        category="utility",
        description="查询当前环境时间",
        inputs=(),
        outputs=(
            _p("时间", "Out", type_expr="Flt", var_type=VarType.Flt, index=0),
            _p("时段", "Out", type_expr="Int", var_type=VarType.Int, index=1),
        ),
    ),

    # ── type_id=665: Set_Env_Time (设置当前环境时间) [manual] ──
    NodeDef(
        type_id=665,
        name="设置当前环境时间",
        category="action",
        description="设置当前环境时间",
        inputs=(
            _p("入", "In", is_flow=True, index=0),
            _p("时间", "In", type_expr="Flt", var_type=VarType.Flt, index=1),
        ),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
        ),
    ),

    # ── type_id=667: Toggle_Entity_Light (开关实体光源) [manual] ──
    NodeDef(
        type_id=667,
        name="开关实体光源",
        category="action",
        description="开启或关闭实体的光源",
        inputs=(
            _p("入", "In", is_flow=True, index=0),
            _p("实体", "In", type_expr="Ety", var_type=VarType.Ety, index=1),
            _p("光源ID", "In", type_expr="Int", var_type=VarType.Int, index=2),
            _p("开启", "In", type_expr="Bol", var_type=VarType.Bol, index=3),
        ),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
        ),
    ),

    # ── type_id=669: Get_Entities_In_Trigger (获取碰撞触发器内所有实体) [manual] ──
    NodeDef(
        type_id=669,
        name="获取碰撞触发器内所有实体",
        category="utility",
        description="获取碰撞触发器范围内的所有实体",
        inputs=(
            _p("触发器", "In", type_expr="Ety", var_type=VarType.Ety, index=0),
            _p("过滤", "In", type_expr="Int", var_type=VarType.Int, index=1),
        ),
        outputs=(
            _p("实体列表", "Out", type_expr="EtyArr", var_type=VarType.EtyArr, index=0),
        ),
    ),

    # ── type_id=697: HP_Loss (损失生命) [manual] ──
    # 编辑器实际引脚（来自 node_library.json）：
    #   流程入(flow, idx=0), 目标实体(Ety, idx=0), 生命损失量(Flt, idx=1),
    #   是否致命(Bol, idx=2), 是否可被无敌抵挡(Bol, idx=3),
    #   是否可被锁定生命值抵挡(Bol, idx=4), 伤害跳字类型(Enum=14, idx=5)
    # 流程出(flow, idx=0)
    NodeDef(
        type_id=697,
        name="损失生命",
        category="action",
        description="对实体造成生命值损失",
        inputs=(
            _p("入", "In", is_flow=True, index=0),
            _p("目标实体", "In", type_expr="Ety", var_type=VarType.Ety, index=0),
            _p("生命损失量", "In", type_expr="Flt", var_type=VarType.Flt, index=1),
            _p("是否致命", "In", type_expr="Bol", var_type=VarType.Bol, index=2, default_value=False),
            _p("是否可被无敌抵挡", "In", type_expr="Bol", var_type=VarType.Bol, index=3, default_value=False),
            _p("是否可被锁定生命值抵挡", "In", type_expr="Bol", var_type=VarType.Bol, index=4, default_value=False),
            _p("伤害跳字类型", "In", type_expr="Enum", var_type=VarType.Enum, index=5, default_value=5401),
        ),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
        ),
    ),

    # ── type_id=698: Recover_HP (直接恢复生命) [manual] ──
    NodeDef(
        type_id=698,
        name="直接恢复生命",
        category="action",
        description="直接恢复实体的生命值",
        inputs=(
            _p("入", "In", is_flow=True, index=0),
            _p("治疗者", "In", type_expr="Ety", var_type=VarType.Ety, index=1),
            _p("目标", "In", type_expr="Ety", var_type=VarType.Ety, index=2),
            _p("恢复量", "In", type_expr="Flt", var_type=VarType.Flt, index=3),
        ),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
        ),
    ),

    # ── type_id=738: Get_Character_Attribute (获取角色属性) [manual] ──
    NodeDef(
        type_id=738,
        name="获取角色属性",
        category="utility",
        description="获取角色的各种属性值",
        inputs=(
            _p("实体", "In", type_expr="Ety", var_type=VarType.Ety, index=0),
        ),
        outputs=(
            _p("属性ID", "Out", type_expr="Int", var_type=VarType.Int, index=0),
            _p("最大生命", "Out", type_expr="Flt", var_type=VarType.Flt, index=1),
            _p("攻击力", "Out", type_expr="Flt", var_type=VarType.Flt, index=2),
            _p("防御力", "Out", type_expr="Flt", var_type=VarType.Flt, index=3),
        ),
    ),

    # ── type_id=744: Get_Owner_Entity (获取拥有者实体) [manual] ──
    NodeDef(
        type_id=744,
        name="获取拥有者实体",
        category="utility",
        description="获取实体的拥有者实体（如装备的持有者）",
        inputs=(
            _p("实体", "In", type_expr="Ety", var_type=VarType.Ety, index=0),
        ),
        outputs=(
            _p("拥有者", "Out", type_expr="Ety", var_type=VarType.Ety, index=0),
        ),
    ),

    # ── type_id=745: Get_Owned_Entities (获取实体拥有的实体列表) [manual] ──
    NodeDef(
        type_id=745,
        name="获取实体拥有的实体列表",
        category="utility",
        description="获取实体所拥有的所有实体列表",
        inputs=(
            _p("实体", "In", type_expr="Ety", var_type=VarType.Ety, index=0),
        ),
        outputs=(
            _p("实体列表", "Out", type_expr="EtyArr", var_type=VarType.EtyArr, index=0),
        ),
    ),

    # ── type_id=757: Create_Prefab_Group (创建元件组) [manual] ──
    NodeDef(
        type_id=757,
        name="创建元件组",
        category="action",
        description="根据元件组索引创建该元件组内包含的实体",
        inputs=(
            _p("入", "In", is_flow=True, index=0),
            _p("元件组索引", "In", type_expr="Int", var_type=VarType.Int, index=1),
            _p("位置", "In", type_expr="Vec", var_type=VarType.Vec, index=2),
            _p("旋转", "In", type_expr="Vec", var_type=VarType.Vec, index=3),
            _p("归属者实体", "In", type_expr="Ety", var_type=VarType.Ety, index=4),
            _p("等级", "In", type_expr="Int", var_type=VarType.Int, index=5),
            _p("单位标签索引列表", "In", type_expr="IntArr", var_type=VarType.IntArr, index=6),
            _p("是否覆写等级", "In", type_expr="Bol", var_type=VarType.Bol, index=7),
        ),
        outputs=(
            _p("出", "Out", is_flow=True, index=0),
            _p("创建后实体列表", "Out", type_expr="EtyArr", var_type=VarType.EtyArr, index=1),
        ),
    ),
]
