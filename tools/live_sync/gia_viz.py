# -*- coding: utf-8 -*-
"""GIA 节点图可视化工具

用法: python tools/live_sync/gia_viz.py <gia_file> [--output html_path]
生成自包含 HTML 文件，浏览器打开即可查看节点图。

增强功能:
- 连线连接到正确的输入端口（按 kind 匹配）
- 缩放/平移交互
- flow 连接（橙色）vs data 连接（紫色）区分显示
- 连接 kind 标签
"""
import sys, json, argparse, struct
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.live_sync.gia_utils import (
    load_gia_numeric, get_entries,
    PIN_KIND_IN_FLOW, PIN_KIND_OUT_FLOW, PIN_KIND_IN_PARAM, PIN_KIND_OUT_PARAM,
    PIN_KIND_NAMES,
)
from tools.live_sync.verified_type_ids import lookup_by_type_id as _lookup_type_id
from tools.live_sync.node_catalog import NodeCatalog, VarType

# 全局 NodeCatalog 实例（延迟初始化）
_catalog = None

def get_catalog():
    global _catalog
    if _catalog is None:
        _catalog = NodeCatalog.default()
    return _catalog

def pin_name_to_out_name(pin_name, src_kind, src_nd):
    """为需要创建的虚拟输出端口找一个合适的名称"""
    # 优先用源节点已有的同 kind 输出端口名称
    for p in src_nd['pins']:
        if not p['is_input'] and p['kind'] == src_kind:
            return p['kind_name']
    # 回退：用连接到此输出的输入引脚名
    if pin_name:
        return pin_name
    # 最后回退：通用名
    return "输出" if src_kind == PIN_KIND_OUT_PARAM else "出"


# ═══════════════════════════════════════════
# 颜色配置
# ═══════════════════════════════════════════

PIN_KIND_COLORS = {
    1: "#4fc3f7",  # IN_FLOW  - 青
    2: "#4fc3f7",  # OUT_FLOW - 青（同色，方向由箭头区分）
    3: "#81c784",  # IN_DATA  - 绿
    4: "#81c784",  # OUT_DATA - 绿（同色，方向由箭头区分）
}

# ═══════════════════════════════════════════
# GIA 解析
# ═══════════════════════════════════════════

def extract_graph(gia_path: Path):
    """提取所有节点图数据"""
    num = load_gia_numeric(gia_path)
    entries = get_entries(num)
    graphs = []

    for entry in entries:
        if '13' not in entry:
            continue
        try:
            graph_wrapper = entry['13']['1']
            gkey = list(graph_wrapper.keys())[0]
            g = graph_wrapper[gkey]

            name_bytes = g.get('2', '')
            if isinstance(name_bytes, str) and name_bytes.startswith('<binary_data>'):
                import re
                hex_str = name_bytes.split('>')[1].strip() if '>' in name_bytes else ''
                try:
                    name = bytes.fromhex(hex_str.replace(' ', '')).decode('utf-8')
                except:
                    name = hex_str[:40]
            else:
                name = str(name_bytes)[:40]

            nodes = g.get('3', [])
            if isinstance(nodes, dict):
                nodes = [nodes]

            graphs.append({
                'name': name,
                'nodes': nodes,
                'entry_name': str(entry.get('3', ''))[:40],
            })
        except (KeyError, TypeError) as e:
            continue

    return graphs


def node_label(node):
    """提取节点标签（含中文名）"""
    type_info = node.get('2', {})
    type_id = type_info.get('5') if isinstance(type_info, dict) else str(type_info)
    name_info = _lookup_type_id(type_id)
    cn_name = name_info.get('name', '') if name_info else ''
    if cn_name:
        return f"{cn_name} ({type_id})"
    return f"ID:{type_id}"


def node_params_text(node):
    """获取节点的 node_params 显示文本（如监听信号的「信号名」）"""
    type_info = node.get('2', {})
    type_id = type_info.get('5') if isinstance(type_info, dict) else type_info
    if not type_id:
        return None
    catalog = get_catalog()
    node_def = catalog.get_by_id(type_id)
    if not node_def or not node_def.node_params:
        return None
    parts = []
    for p in node_def.node_params:
        val_str = str(p.default_value) if p.default_value else ""
        parts.append(f"{p.name}:{p.type_expr}" if not val_str else f"{p.name}={val_str}")
    return "  ".join(parts)


def get_pin_label(node, kind, is_input, gia_pin_index, param_value=None):
    """从 NodeCatalog 获取端口的实际名称和参数值

    Args:
        node: GIA 节点 dict
        kind: pin kind (1/2/3/4)
        is_input: 是否输入
        gia_pin_index: GIA 中该引脚的索引值（sig['2']），用于精确匹配 catalog
        param_value: 已解码的参数值

    Returns:
        (label, extra, is_configurable) 元组
    """
    type_info = node.get('2', {})
    type_id = type_info.get('5') if isinstance(type_info, dict) else type_info
    if not type_id:
        return PIN_KIND_NAMES.get(kind, f'K{kind}'), None, False

    catalog = get_catalog()
    node_def = catalog.get_by_id(type_id)
    if not node_def:
        return PIN_KIND_NAMES.get(kind, f'K{kind}'), None, False

    pins = node_def.inputs if is_input else node_def.outputs
    kind_pins = [p for p in pins if _pin_kind_from_def(p) == kind]

    if not kind_pins:
        return PIN_KIND_NAMES.get(kind, f'K{kind}'), None, False

    # ── 精确匹配：按 GIA 中的 pin_index 匹配 catalog 中的 PinDef.index ──
    if gia_pin_index is not None:
        for p in kind_pins:
            if p.index == gia_pin_index:
                name = p.name
                configurable = p.is_configurable
                if is_input and kind == PIN_KIND_IN_PARAM and param_value is not None:
                    return name, str(param_value), configurable
                if not is_input and p.default_value is not None:
                    return name, str(p.default_value), configurable
                return name, None, configurable

    # ── 回退：按顺序匹配（flow 引脚或旧版 GIA）──
    # 对于 flow 引脚，通常只有 1 个，顺序安全
    # 对于数据引脚，NODE_DATA_GEN 生成的 + 编辑器导出的都应有 index
    # 如果一个 kind 有多个引脚且没有 index，可能错位，但这是旧数据兼容
    if len(kind_pins) == 1:
        p = kind_pins[0]
        name = p.name
        configurable = p.is_configurable
        if is_input and kind == PIN_KIND_IN_PARAM and param_value is not None:
            return name, str(param_value), configurable
        if not is_input and p.default_value is not None:
            return name, str(p.default_value), configurable
        return name, None, configurable

    # 多个同 kind 引脚且无 index → 无法区分，报告问题
    return PIN_KIND_NAMES.get(kind, f'K{kind}'), None, False


def _pin_kind_from_def(pin_def):
    """从 PinDef 推断 kind 值"""
    if pin_def.is_flow:
        return 1 if pin_def.direction == "In" else 2
    else:
        return 3 if pin_def.direction == "In" else 4


def _cfg_type_name(var_type):
    """将 VarType int 转为可读类型名"""
    _map = {0: "泛型", 3: "Int", 4: "Bol", 5: "Flt", 6: "Str", 12: "Vec"}
    return _map.get(var_type, f"T{var_type}")


def parse_pins(node):
    """解析节点端口

    两遍匹配 catalog 引脚名：
    1. 精确匹配：GIA sig['2'](pin_index) → PinDef.index
    2. 回退匹配：未匹配的 GIA 引脚按顺序分配给未使用的 catalog 引脚
    3. 补充缺失的 flow 引脚

    Returns: 端口列表
    """
    pins = node.get('4', [])
    if isinstance(pins, dict):
        pins = [pins]
    if not isinstance(pins, list):
        pins = []

    # ── 获取 catalog 定义 ──
    type_info = node.get('2', {})
    type_id = type_info.get('5') if isinstance(type_info, dict) else type_info
    catalog = get_catalog()
    node_def = catalog.get_by_id(type_id) if type_id else None

    # ── 第一遍：解析 GIA 原始数据 ──
    raw_pins = []
    for pi, p in enumerate(pins):
        if isinstance(p, str):
            continue
        sig = p['1']
        kind = sig['1']
        gia_idx = sig.get('2') if isinstance(sig, dict) and kind in (PIN_KIND_IN_PARAM, PIN_KIND_OUT_PARAM) else None

        conn = p.get('5')
        target_id = None; conn_kind = None; src_pin_index = None
        if isinstance(conn, dict):
            target_id = conn['1']
            sh = conn.get('2', {})
            if isinstance(sh, dict):
                conn_kind = sh.get('1')       # 对端引脚的 kind
                src_pin_index = sh.get('2')    # 源引脚索引
        elif isinstance(conn, list) and conn:
            c0 = conn[0] if isinstance(conn[0], dict) else {}
            target_id = c0.get('1')
            sh = c0.get('2', {})
            if isinstance(sh, dict):
                conn_kind = sh.get('1')       # 对端引脚的 kind
                src_pin_index = sh.get('2')    # 源引脚索引

        var_base = p.get('3')
        param_value = _decode_var_base(var_base)
        is_input = kind in (PIN_KIND_IN_FLOW, PIN_KIND_IN_PARAM)
        vt = _var_base_type(var_base)
        pin_var_type = vt if vt else p.get('4', 0)

        raw_pins.append({
            'kind': kind, 'is_input': is_input, 'target_id': target_id,
            'conn_kind': conn_kind, 'src_pin_index': src_pin_index,  # 保存源引脚索引
            'param': param_value, 'var_type': pin_var_type,
            'pin_index': pi, 'gia_pin_index': gia_idx,
            'field4': p.get('4'),  # 保存 field4 用于连线匹配
        })

    # ── 第二遍：分配 catalog 引脚名 ──
    named = _assign_pin_names(node_def, raw_pins)

    # ── 补充缺失的隐含 flow 引脚 ──
    named = _supplement_missing_pins(node, node_def, named)

    # ── 过滤空值空连接的可变参数扩展引脚 ──
    named = _filter_empty_var_arity(named, node_def)

    # ── 按 catalog index 排序，确保引脚顺序与官方定义一致 ──
    if node_def:
        def get_sort_key(pin):
            # 优先使用 catalog_pin_index，其次是 gia_pin_index，最后是 pin_index
            idx = pin.get('catalog_pin_index')
            if idx is not None:
                return (pin['kind'], idx)
            idx = pin.get('gia_pin_index')
            if idx is not None:
                return (pin['kind'], idx)
            # 补充的引脚 pin_index=-1，按 kind 分组放在最后
            return (pin['kind'], pin.get('pin_index', 999))
        
        named.sort(key=get_sort_key)
        
        # ── 排序后重新分配 pin_extra，确保值和名称对应 ──
        # 按 (is_input, kind) 分组，每组内按 catalog_pin_index 匹配值
        for pin in named:
            kind = pin['kind']
            is_input = pin['is_input']
            catalog_idx = pin.get('catalog_pin_index')
            param = pin.get('param')
            
            if catalog_idx is not None and kind in (PIN_KIND_IN_PARAM, PIN_KIND_OUT_PARAM):
                # 找到对应的 catalog 引脚
                pool = node_def.inputs if is_input else node_def.outputs
                for p_def in pool:
                    if p_def.index == catalog_idx:
                        # 重新分配 pin_extra
                        if param is not None:
                            pin['pin_extra'] = str(param)
                        elif p_def.default_value is not None:
                            pin['pin_extra'] = str(p_def.default_value)
                        break

    return named


def _filter_empty_var_arity(pins, node_def):
    """隐藏没有数据的槽位，合并同名重复

    GIA 导出时的物理槽位比编辑器逻辑引脚多，空槽位只占位不展示。

    策略（按基名分组处理）：
    1. 只有 CAT 槽位有数据 → 保留 CAT，丢弃 EXT
    2. CAT 空，但有 EXT 有数据 → 丢弃 CAT
       - 只剩 1 个 EXT → 去掉数字后缀（如 目标实体1→目标实体）
       - 还有多个 EXT → 各自保留编号（如 时长(秒)1/时长(秒)3）
    3. 全部空 → 只保留 CAT（展示节点接口）
    """
    if not node_def:
        return pins

    import re
    cat_names = {p.name for p in node_def.inputs} | {p.name for p in node_def.outputs}

    # ── 按基名分组 ──
    data_pins = []   # (index, pin)  for data pins
    other_pins = []  # flow + virtual pins
    for i, p in enumerate(pins):
        if p['kind'] in (1, 2) or p.get('pin_index', 0) < 0:
            other_pins.append(p)
        else:
            data_pins.append((i, p))

    groups = {}  # base_name → [(idx, pin, is_cat, has_data)]
    for idx, p in data_pins:
        name = p['kind_name']
        base = re.sub(r'\d+$', '', name)
        is_cat = name in cat_names
        has_data = p.get('target_id') is not None or (
            p.get('param') is not None and p.get('param') != ''
        )
        groups.setdefault(base, []).append((idx, p, is_cat, has_data))

    # ── 处理每个组 ──
    keep = set()
    for base, items in groups.items():
        cat_items = [(i, p, d) for i, p, is_cat, d in items if is_cat]
        ext_items = [(i, p, d) for i, p, is_cat, d in items if not is_cat]

        if len(ext_items) == 0:
            # 只有 CAT → 全部保留
            keep.update(i for i, p, d in cat_items)
        else:
            cats_with_data = [(i, p, d) for i, p, d in cat_items if d]
            exts_with_data = [(i, p, d) for i, p, d in ext_items if d]

            if cats_with_data:
                # CAT 有数据 → 保留 CAT，丢弃所有 EXT（防止重复）
                keep.update(i for i, p, d in cat_items)
            else:
                # CAT 全部空 → 丢弃 CAT
                if exts_with_data:
                    # 有 EXT 有数据
                    if len(exts_with_data) == 1:
                        # 只有一个有数据的 EXT → 去掉数字后缀
                        i, p, _ = exts_with_data[0]
                        p['kind_name'] = base
                        keep.add(i)
                    else:
                        # 多个有数据的 EXT → 各自保留编号
                        keep.update(i for i, p, _ in exts_with_data)
                    # 有数据的 EXT 全部保留后，空的 EXT 丢弃
                else:
                    # 全部空 → CAT 全保留，EXT 全丢弃
                    keep.update(i for i, p, d in cat_items)

    # ── 重组 ──
    result = list(other_pins)
    for idx, p in data_pins:
        if idx in keep:
            result.append(p)

    return result


def _assign_pin_names(node_def, raw_pins):
    """两遍匹配分配 catalog 引脚名"""
    result = []
    # 建立可用引脚池：{(is_input, kind): [PinDef, ...]}
    pool = {}
    if node_def:
        for d, pins in [('input', node_def.inputs), ('output', node_def.outputs)]:
            is_in = d == 'input'
            for p in pins:
                k = _pin_kind_from_def(p)
                key = (is_in, k)
                pool.setdefault(key, []).append(p)

    # 用于追踪已使用的 catalog 引脚（per kind，防止同名重复分配）
    used_idx = {}  # {(is_input, kind): set(indices)}
    unmatched = []  # 收集未匹配的 raw_pins

    for raw in raw_pins:
        kind = raw['kind']; is_input = raw['is_input']
        gia_idx = raw['gia_pin_index']; param = raw['param']
        var_type = raw.get('var_type', 0)
        key = (is_input, kind)
        used_idx.setdefault(key, set())

        pin_name = PIN_KIND_NAMES.get(kind, f'K{kind}')
        extra = None; configurable = False
        catalog_idx = None  # 默认值为 None

        if key in pool:
            available = [p for p in pool[key] if p.index not in used_idx[key]]
            matched = None

            # 第一优先：精确匹配 gia_idx（sig['2'] 是 GIA 中的显式索引，最可靠）
            if gia_idx is not None:
                for p in available:
                    if p.index == gia_idx:
                        matched = p; break

            # 第二优先：有值且 var_type 匹配
            if not matched and param is not None and var_type != 0:
                for p in available:
                    if p.var_type == var_type:
                        matched = p; break

            if matched:
                used_idx[key].add(matched.index)
                pin_name = matched.name
                configurable = matched.is_configurable
                catalog_idx = matched.index  # 保存 catalog index
                # 设置 pin_extra：优先使用 GIA 中的 param，否则使用 catalog 的 default_value
                if is_input and kind == PIN_KIND_IN_PARAM:
                    if param is not None:
                        extra = str(param)
                    elif matched.default_value is not None:
                        extra = str(matched.default_value)
                elif not is_input and matched.default_value is not None:
                    extra = str(matched.default_value)
            else:
                unmatched.append(len(result))

        result.append({
            **raw,
            'kind_name': pin_name, 'pin_extra': extra, 'is_configurable': configurable,
            'catalog_pin_index': catalog_idx,  # 保存 catalog pin index 用于连线匹配
        })

    # ── 第二遍：类型匹配（对于 gia_idx=None 的引脚）──
    for idx in unmatched[:]:  # 遍历副本，因为会修改 unmatched
        raw = result[idx]
        key = (raw['is_input'], raw['kind'])
        var_type = raw.get('var_type', 0)
        param = raw.get('param')
        
        # 只有有值的引脚才尝试类型匹配
        if param is None or var_type == 0:
            continue
        
        if key in pool:
            available = [p for p in pool[key] if p.index not in used_idx.get(key, set())]
            # 按 var_type 匹配
            for p in available:
                if p.var_type == var_type:
                    used_idx.setdefault(key, set()).add(p.index)
                    result[idx]['kind_name'] = p.name
                    result[idx]['is_configurable'] = p.is_configurable
                    result[idx]['catalog_pin_index'] = p.index
                    result[idx]['pin_extra'] = str(param)
                    unmatched.remove(idx)  # 从未匹配列表移除
                    break

    # ── 第三遍：按顺序回填剩余未匹配的 ──
    var_arity_cnt = {}  # 可变参数计数器
    for idx in unmatched:
        raw = result[idx]
        key = (raw['is_input'], raw['kind'])
        if key in pool and pool[key]:
            available = [p for p in pool[key] if p.index not in used_idx.get(key, set())]
            if available:
                p = available[0]
                used_idx.setdefault(key, set()).add(p.index)
                result[idx]['kind_name'] = p.name
                result[idx]['is_configurable'] = p.is_configurable
                result[idx]['catalog_pin_index'] = p.index  # 保存 catalog index
            else:
                # 所有 catalog 引脚已用完 → 可变参数节点：按计数器扩展命名
                base = pool[key][0]
                n = var_arity_cnt.get(key, 0) + 1
                var_arity_cnt[key] = n
                # 可变参数命名：元素1~元素99（无前导零）
                result[idx]['kind_name'] = f"{base.name}{n}"
                result[idx]['is_configurable'] = base.is_configurable
                result[idx]['catalog_pin_index'] = base.index  # 保存 base index

    return result


def _var_base_type(var_base):
    """从 var_base dict 提取类型码

    var_type 存储在 var_base['4']['100']['1'] 中
    tag=10000 封装格式：类型在 field[110].field[2].field[4] 中
    """
    if not isinstance(var_base, dict):
        return 0
    # tag=10000: Int 类型的嵌套封装
    if var_base.get('1') == 10000:
        inner = var_base.get('110', {}).get('2', {})
        if isinstance(inner, dict):
            type_desc = inner.get('4', {})
            if isinstance(type_desc, dict):
                vt_info = type_desc.get('100', {})
                if isinstance(vt_info, dict):
                    return vt_info.get('1', 0)
        return 3  # 默认 Int
    type_desc = var_base.get('4', {})
    if isinstance(type_desc, dict):
        vt_info = type_desc.get('100', {})
        if isinstance(vt_info, dict):
            return vt_info.get('1', 0)
    return 0


def _decode_var_base(var_base):
    """解码 var_base 为可读字符串
    
    支持两种格式:
    
    格式A（examples/可用文件）:
    {
        "1": var_type,
        "2": {"1": value}        # 值直接存储在 field[2] 的子字段中
    }
    
    格式B（export_examples/导出文件）:
    {
        "1": type_code,
        "2": 1,                   # 未知标志
        "4": {"1": 1, "100": {"1": var_type}},
        "101"/"104"/"105"/...: {"1": value}
    }
    """
    if not isinstance(var_base, dict):
        return None

    # ── tag=10000: Int 类型的嵌套封装格式 ──
    # 格式: {'1': 10000, '110': {'2': {标准 VarBase}}, '2': 1}
    # 递归解码内层 VarBase
    if var_base.get('1') == 10000:
        inner = var_base.get('110', {}).get('2', {})
        if isinstance(inner, dict):
            return _decode_var_base(inner)
        return None

    # ── 判断格式并获取 var_type 和 value ──
    field2 = var_base.get('2')
    field4 = var_base.get('4')
    
    # 格式A: field[2] 是 dict {'1': value}，field[4] 不存在
    # 格式B: field[2] 是 int 1，field[4] 是 dict
    is_format_a = isinstance(field2, dict) and not isinstance(field4, dict)
    
    if is_format_a:
        # 格式A: var_type 在 field[1]，value 在 field[2]['1']
        var_type = var_base.get('1', 0)
        raw_value = field2.get('1') if isinstance(field2, dict) else None
    else:
        # 格式B: var_type 在 field[4][100][1]，value 在对应字段
        type_desc = var_base.get('4', {})
        if isinstance(type_desc, dict):
            vt_info = type_desc.get('100', {})
            var_type = vt_info.get('1', 0) if isinstance(vt_info, dict) else 0
        else:
            var_type = 0
        
        # value_field_map: 根据 var_type 找到存储值的字段
        # 注意：这与 _build_var_base 中的 tag 对应
        # tag=1 → field[101] (Ety/GUID/Config)
        # tag=2 → field[102] (Int)
        # tag=4 → field[104] (Float)
        # tag=5 → field[105] (Str)
        # tag=6 → field[106] (Bool/Enum)
        # tag=7 → field[107] (Vec)
        value_field_map = {
            0: '102',  # 泛型 → Int 默认
            1: '101',  # Ety
            3: '102',  # Int → field[102]
            4: '106',  # Bool → field[106]
            5: '104',  # Float → field[104]
            6: '105',  # Str → field[105]
            12: '107', # Vec → field[107]
            14: '106', # Enum → field[106] (和 Bool 一样)
            17: '101', # Faction
            20: '101', # Cfg → field[101]
        }
        value_field = value_field_map.get(var_type, '102')
        vdata = var_base.get(value_field)
        
        if vdata is None:
            return None
        raw_value = vdata.get('1') if isinstance(vdata, dict) else vdata
    
    if raw_value is None:
        return None
    
    # 根据类型解码
    if var_type == 6:  # Str
        if isinstance(raw_value, str):
            if raw_value.startswith('<binary_data'):
                hex_str = raw_value.split('>')[1].strip() if '>' in raw_value else ''
                try:
                    data = bytes.fromhex(hex_str.replace(' ', ''))
                    # 跳过长度前缀（通常是前2字节）
                    # 常见格式：0A 0B 表示长度，后面是实际字符串
                    # 找到第一个可打印 ASCII 字符的位置
                    start = 0
                    for i, b in enumerate(data):
                        if 32 <= b <= 126:  # 可打印 ASCII
                            start = i
                            break
                    return data[start:].decode('utf-8')
                except Exception:
                    return hex_str[:20]
            return raw_value[:50]
        return str(raw_value)[:50]
    
    elif var_type == 4:  # Bool
        # Bool 编码规则：
        # True  → field[106] = {'1': 1}  (dict, raw_value = 1)
        # False → field[106] = '<binary_data>' (空 binary, raw_value 是字符串)
        if isinstance(raw_value, str):
            # binary_data 格式表示 False（空值）
            return "否"
        return "是" if raw_value else "否"
    
    elif var_type == 5:  # Float
        import struct as _struct
        if isinstance(raw_value, int):
            # 格式A: IEEE 754 bits (uint32) -> float
            try:
                return str(_struct.unpack('>f', _struct.pack('>I', raw_value))[0])
            except Exception:
                return str(raw_value)
        elif isinstance(raw_value, float):
            return str(raw_value)
        return str(raw_value)
    
    elif var_type == 12:  # Vec
        import struct as _struct
        # 格式A: field[2] = {'1': bits_x, '2': bits_y, '3': bits_z}
        if isinstance(raw_value, dict):
            try:
                def _bits_to_float(b):
                    return _struct.unpack('>f', _struct.pack('>I', int(b)))[0]
                x = _bits_to_float(raw_value.get('1', 0))
                y = _bits_to_float(raw_value.get('2', 0))
                z = _bits_to_float(raw_value.get('3', 0))
                return f"({x:.1f}, {y:.1f}, {z:.1f})"
            except Exception:
                pass
        # 格式B: binary_data
        elif isinstance(raw_value, str) and raw_value.startswith('<binary_data'):
            hex_str = raw_value.split('>')[1].strip() if '>' in raw_value else ''
            try:
                data = bytes.fromhex(hex_str.replace(' ', ''))
                if len(data) >= 12:
                    x = _struct.unpack('>f', data[0:4])[0]
                    y = _struct.unpack('>f', data[4:8])[0]
                    z = _struct.unpack('>f', data[8:12])[0]
                    return f"({x:.1f}, {y:.1f}, {z:.1f})"
            except Exception:
                pass
        return "(0, 0, 0)"
    
    elif var_type == 14:  # Enum
        # 枚举值是 enum_item_id（如 5401=无跳字, 5402=普通跳字, 5403=暴击跳字）
        # 尝试从 node_library.json 的 enum_options 中查找名称
        enum_name = _resolve_enum_name(var_base, raw_value)
        if enum_name:
            return enum_name
        return str(raw_value)
    
    elif var_type in (0, 1, 2, 3, 20):  # 泛型, Ety, GUID, Int, Cfg
        if isinstance(raw_value, str) and raw_value.startswith('<binary_data'):
            return ''  # 空 binary_data → 空字符串
        return str(raw_value)
    
    return str(raw_value)[:50]


# 枚举 ID → 名称的缓存（懒加载）
_enum_id_cache = None

def _load_enum_id_map():
    """从 node_library.json 加载所有枚举选项的 ID→名称映射"""
    global _enum_id_cache
    if _enum_id_cache is not None:
        return _enum_id_cache
    
    _enum_id_cache = {}
    try:
        import json
        lib_path = Path(r'h:\myprojects\genshin_qianxing_editor\assets\资源库\app\runtime\cache\node_cache\node_library.json')
        if lib_path.exists():
            data = json.loads(lib_path.read_text(encoding='utf-8'))
            # 遍历所有节点，收集 enum_options
            for node in data if isinstance(data, list) else data.values():
                if not isinstance(node, dict):
                    continue
                enum_opts = node.get('input_enum_options', {})
                for pin_name, options in enum_opts.items():
                    if isinstance(options, list):
                        for i, opt_name in enumerate(options):
                            # 枚举 ID 规律: 基础ID + 选项索引
                            # 但我们不知道基础 ID，所以用另一种方式
                            # 从 node 的 enum_values 或其他字段获取
                            pass
                # 也检查 enum_values 字段（如果有）
                enum_values = node.get('input_enum_values', {})
                for pin_name, values in enum_values.items():
                    if isinstance(values, list):
                        for val in values:
                            if isinstance(val, dict):
                                eid = val.get('id')
                                name = val.get('name')
                                if eid is not None and name:
                                    _enum_id_cache[int(eid)] = name
    except Exception:
        pass
    
    return _enum_id_cache


def _resolve_enum_name(var_base, raw_value):
    """尝试将枚举 ID 解析为名称"""
    if raw_value is None:
        return None
    
    enum_id = int(raw_value) if isinstance(raw_value, (int, float)) else None
    if enum_id is None:
        return None
    
    # 加载缓存
    enum_map = _load_enum_id_map()
    if enum_id in enum_map:
        return enum_map[enum_id]
    
    # 常见枚举 ID 的硬编码映射（作为 fallback）
    _known_enums = {
        5401: "无跳字",
        5402: "普通跳字",
        5403: "暴击跳字",
    }
    return _known_enums.get(enum_id)


def _supplement_missing_pins(node, node_def, existing_pins):
    """补充 GIA 中缺失的引脚（flow + data 输入 + data 输出）
    
    对于事件节点，GIA 导出时可能只包含部分引脚，缺少其他引脚。
    此时需要根据 catalog 定义补充缺失的引脚。
    """
    if not node_def:
        return existing_pins

    existing_kinds = {p['kind'] for p in existing_pins}
    
    # 构建已存在引脚的索引集合（用于精确匹配）
    # 同时检查 gia_pin_index 和 catalog_pin_index，防止重复补充
    existing_in_data_indices = set()
    for p in existing_pins:
        if p['is_input'] and p['kind'] == PIN_KIND_IN_PARAM:
            if p.get('gia_pin_index') is not None:
                existing_in_data_indices.add(p['gia_pin_index'])
            if p.get('catalog_pin_index') is not None:
                existing_in_data_indices.add(p['catalog_pin_index'])
    
    existing_out_data_indices = set()
    for p in existing_pins:
        if not p['is_input'] and p['kind'] == PIN_KIND_OUT_PARAM:
            if p.get('gia_pin_index') is not None:
                existing_out_data_indices.add(p['gia_pin_index'])
            if p.get('catalog_pin_index') is not None:
                existing_out_data_indices.add(p['catalog_pin_index'])

    # 补充缺失的 flow 引脚
    if PIN_KIND_IN_FLOW not in existing_kinds:
        flow_ins = [p for p in node_def.inputs if p.is_flow]
        if flow_ins:
            existing_pins.insert(0, {
                'kind': PIN_KIND_IN_FLOW, 'kind_name': flow_ins[0].name,
                'is_input': True, 'target_id': None, 'conn_kind': None,
                'param': None, 'pin_extra': None, 'is_configurable': False,
                'var_type': 0, 'pin_index': -1,
            })
    if PIN_KIND_OUT_FLOW not in existing_kinds:
        flow_outs = [p for p in node_def.outputs if p.is_flow]
        if flow_outs:
            existing_pins.append({
                'kind': PIN_KIND_OUT_FLOW, 'kind_name': flow_outs[0].name,
                'is_input': False, 'target_id': None, 'conn_kind': None,
                'param': None, 'pin_extra': None, 'is_configurable': False,
                'var_type': 0, 'pin_index': -1,
            })

    # 补充缺失的数据输入引脚（根据 catalog 定义）
    in_data_pins = [p for p in node_def.inputs if not p.is_flow]
    for p_def in in_data_pins:
        # 检查该引脚是否已存在（按 index 精确匹配）
        if p_def.index not in existing_in_data_indices:
            existing_pins.append({
                'kind': PIN_KIND_IN_PARAM,
                'kind_name': p_def.name,
                'is_input': True,
                'target_id': None,
                'conn_kind': None,
                'param': None,
                'pin_extra': str(p_def.default_value) if p_def.default_value is not None else None,
                'is_configurable': p_def.is_configurable,
                'var_type': p_def.var_type,
                'pin_index': -1,  # 标记为补充的引脚
                'gia_pin_index': p_def.index,  # 保留 catalog index 用于匹配
            })
            existing_in_data_indices.add(p_def.index)

    # 补充缺失的数据输出引脚（根据 catalog 定义）
    out_data_pins = [p for p in node_def.outputs if not p.is_flow]
    for p_def in out_data_pins:
        # 检查该引脚是否已存在（按 index 精确匹配）
        if p_def.index not in existing_out_data_indices:
            existing_pins.append({
                'kind': PIN_KIND_OUT_PARAM,
                'kind_name': p_def.name,
                'is_input': False,
                'target_id': None,
                'conn_kind': None,
                'param': None,
                'pin_extra': str(p_def.default_value) if p_def.default_value is not None else None,
                'is_configurable': p_def.is_configurable,
                'var_type': p_def.var_type,
                'pin_index': -1,  # 标记为补充的引脚
                'gia_pin_index': p_def.index,  # 保留 catalog index 用于匹配
                'catalog_pin_index': p_def.index,  # 同时设置 catalog_pin_index
            })
            existing_out_data_indices.add(p_def.index)

    return existing_pins


def build_input_pin_lookup(node_data):
    """为每个节点构建输入端口查找表

    返回: {(node_id, kind): [(pin_index, pin_y_offset, pin, use_count), ...]}

    改进：按 (node_id, kind) 分组，支持多同类型端口的正确匹配。
    use_count 用于跟踪端口使用次数，避免多条线连到同一端口。

    重要：pin_y_offset 的计算方式必须与渲染代码完全一致——
    从 PIN_START_Y 开始，每个引脚都前进 PIN_H + PIN_GAP。
    """
    lookup = {}

    for nd in node_data:
        node_id = nd['id']
        params_offset = 14 if nd.get('params_text') else 0
        # 模拟渲染代码的 pin_y 累进
        pin_y = PIN_START_Y + params_offset

        for pi, pin in enumerate(nd['pins']):
            if pin['is_input']:
                kind = pin['kind']
                key = (node_id, kind)
                if key not in lookup:
                    lookup[key] = []
                # 用当前累进的 pin_y + 半高 = 端口中心
                pin_y_offset = pin_y + PIN_H / 2
                lookup[key].append([pi, pin_y_offset, pin, 0])
            # 每个引脚都前进（与渲染代码一致）
            pin_y += PIN_H + PIN_GAP

    return lookup


def find_best_input_pin(lookup, node_id, conn_kind, pin_name=None):
    """找到最佳目标输入端口

    Args:
        lookup: build_input_pin_lookup 返回的查找表
        node_id: 目标节点 ID
        conn_kind: 连接类型（1=flow, 3/4=data — 自动映射到输入 kind）
        pin_name: 可选的源引脚名称，用于名称匹配

    Returns:
        (pin_index, pin_y_offset, pin) 或 None
    """
    key = (node_id, conn_kind)
    if key not in lookup or not lookup[key]:
        return None

    candidates = lookup[key]

    # ── 优先按名称匹配 ──
    if pin_name:
        for c in candidates:
            if c[2]['kind_name'] == pin_name and c[3] == 0:
                c[3] += 1
                return c[0], c[1], c[2]

    # ── 回退：最少使用次数 ──
    best = min(candidates, key=lambda x: x[3])
    best[3] += 1
    return best[0], best[1], best[2]


# ═══════════════════════════════════════════
# HTML 生成
# ═══════════════════════════════════════════

NODE_W = 180
NODE_H_MIN = 50
PIN_H = 22
PIN_W = 14
PIN_GAP = 2
HEADER_H = 22
PIN_START_Y = 26
X_SPACING = 280
Y_SPACING = 80


def generate_html(gia_path: Path, graphs: list) -> str:
    """生成自包含 HTML（含缩放/平移交互）"""
    svg_parts = []
    svg_ids = []

    for gi, graph in enumerate(graphs):
        nodes = graph['nodes']
        if not nodes:
            continue

        # ── 解析节点数据 ──────────────────────────────
        node_data = []
        for ni, node in enumerate(nodes):
            nid = node.get('1', ni + 1)
            x = float(node['5'])
            y = float(node['6'])
            label = node_label(node)
            params = node_params_text(node)  # 节点参数（如监听信号的"信号名"）
            pins = parse_pins(node)
            in_count = sum(1 for p in pins if p['is_input'])
            out_count = sum(1 for p in pins if not p['is_input'])
            # 有 node_params 时增加一行高度
            params_h = 14 if params else 0
            h = max(NODE_H_MIN, max(in_count, out_count) * (PIN_H + PIN_GAP) + 30 + params_h)

            node_data.append({
                'id': nid,
                'x': x,
                'y': y,
                'label': label,
                'params_text': params,
                'pins': pins,
                'in_count': in_count,
                'out_count': out_count,
                'h': h,
            })

        # ── 转移连接信息：GIA 中连线记录在输入端口上，需要转移到输出端口 ──
        # 构建节点 ID → node_data 的映射
        id_to_nd = {nd['id']: nd for nd in node_data}
        for nd in node_data:
            for pin in nd['pins']:
                if not pin['is_input'] or not pin['target_id']:
                    continue
                src_id = pin['target_id']
                src_nd = id_to_nd.get(src_id)
                if not src_nd:
                    continue

                src_kind = (
                    PIN_KIND_OUT_PARAM if pin['kind'] == PIN_KIND_IN_PARAM
                    else PIN_KIND_OUT_FLOW
                )
                pin_name = pin['kind_name']
                src_pin_idx = pin.get('src_pin_index')  # 获取源引脚索引

                matched = False

                # ── 优先按 src_pin_index 匹配（最准确） ──
                # src_pin_index 是 GIA 中记录的源引脚索引，
                # 经验证：它只在 OUT_PARAM（数据输出）中计数，不包含 OUT_FLOW
                if src_pin_idx is not None and src_kind == PIN_KIND_OUT_PARAM:
                    out_param_pins = [
                        sp for sp in src_nd['pins']
                        if not sp['is_input'] and sp['kind'] == PIN_KIND_OUT_PARAM
                    ]
                    if src_pin_idx < len(out_param_pins):
                        target_src_pin = out_param_pins[src_pin_idx]
                        # 支持一对多：用列表存储所有目标节点
                        if 'target_ids' not in target_src_pin:
                            target_src_pin['target_ids'] = []
                        target_src_pin['target_ids'].append(nd['id'])
                        target_src_pin['conn_kind'] = pin['kind']
                        matched = True

                # ── 按名称匹配（回退方案） ──
                if not matched:
                    for src_pin in src_nd['pins']:
                        if (not src_pin['is_input']
                                and src_pin['kind'] == src_kind
                                and src_pin['kind_name'] == pin_name):
                            if 'target_ids' not in src_pin:
                                src_pin['target_ids'] = []
                            src_pin['target_ids'].append(nd['id'])
                            src_pin['conn_kind'] = pin['kind']
                            matched = True
                            break

                # ── 按 kind 匹配（最后回退，仅用于原始引脚） ──
                if not matched:
                    for src_pin in src_nd['pins']:
                        if (not src_pin['is_input']
                                and src_pin['kind'] == src_kind
                                and src_pin.get('pin_index') != -1):  # 排除补充引脚
                            if 'target_ids' not in src_pin:
                                src_pin['target_ids'] = []
                            src_pin['target_ids'].append(nd['id'])
                            src_pin['conn_kind'] = pin['kind']
                            matched = True
                            break

                # ── 按类型匹配（最后回退，用于缺少 src_pin_index 的情况） ──
                # 当 GIA 文件缺少 src_pin_index 时，尝试按类型匹配
                if not matched and src_pin_idx is None:
                    # 获取目标引脚的 var_type
                    tgt_var_type = pin.get('var_type', 0)
                    
                    # 新增：尝试用目标引脚的 gia_idx 作为源引脚的 catalog index
                    tgt_gia_idx = pin.get('gia_pin_index')
                    if tgt_gia_idx is not None:
                        for src_pin in src_nd['pins']:
                            if (not src_pin['is_input']
                                    and src_pin['kind'] == src_kind):
                                src_catalog_idx = src_pin.get('catalog_pin_index')
                                if src_catalog_idx == tgt_gia_idx:
                                    if 'target_ids' not in src_pin:
                                        src_pin['target_ids'] = []
                                    src_pin['target_ids'].append(nd['id'])
                                    src_pin['conn_kind'] = pin['kind']
                                    matched = True
                                    break
                    
                    # 新增：尝试用目标引脚的 field4 作为源引脚的 catalog index
                    if not matched:
                        tgt_field4 = pin.get('field4')
                        if tgt_field4 is not None:
                            for src_pin in src_nd['pins']:
                                if (not src_pin['is_input']
                                        and src_pin['kind'] == src_kind):
                                    src_catalog_idx = src_pin.get('catalog_pin_index')
                                    if src_catalog_idx == tgt_field4:
                                        if 'target_ids' not in src_pin:
                                            src_pin['target_ids'] = []
                                        src_pin['target_ids'].append(nd['id'])
                                        src_pin['conn_kind'] = pin['kind']
                                        matched = True
                                        break
                    
                    # 在源节点的 OUT_PARAM 中查找类型匹配的引脚
                    if not matched:
                        for src_pin in src_nd['pins']:
                            if (not src_pin['is_input']
                                    and src_pin['kind'] == src_kind):
                                # 检查类型是否匹配
                                src_var_type = src_pin.get('var_type', 0)
                                if src_var_type == tgt_var_type and tgt_var_type != 0:
                                    if 'target_ids' not in src_pin:
                                        src_pin['target_ids'] = []
                                    src_pin['target_ids'].append(nd['id'])
                                    src_pin['conn_kind'] = pin['kind']
                                    matched = True
                                    break
                
                # ── 无法匹配时的处理 ──
                if not matched:
                    # GIA 文件中有些连接缺少必要信息，跳过这些连接而不是报错
                    print(f"警告: 跳过无法匹配的连接：目标节点 {nd['id']}.{pin_name} → 源节点 {src_id} (src_pin_index={src_pin_idx})")
                
                # 清除输入端口上的连接信息（无论匹配成功与否）
                pin['target_id'] = None
                pin['conn_kind'] = None

        # ── 计算 SVG 尺寸和偏移 ─────────────────────
        min_x = min(n['x'] for n in node_data) if node_data else 0
        min_y = min(n['y'] for n in node_data) if node_data else 0
        max_x = max(n['x'] + NODE_W for n in node_data) if node_data else 0
        max_y = max(n['y'] + n['h'] for n in node_data) if node_data else 0

        offset_x = 60 - min_x
        offset_y = 80 - min_y
        svg_w = max_x + offset_x + 120
        svg_h = max_y + offset_y + 80

        # ── 构建输入端口查找表 ───────────────────────
        input_lookup = build_input_pin_lookup(node_data)

        # ── 绘制连线 ────────────────────────────────
        lines_svg = []
        for nd in node_data:
            nx = nd['x'] + offset_x
            ny = nd['y'] + offset_y
            params_offset = 14 if nd.get('params_text') else 0
            for pi, pin in enumerate(nd['pins']):
                # 支持一对多：target_ids 是列表
                target_ids = pin.get('target_ids', [])
                if pin.get('target_id'):  # 兼容旧的单值格式
                    target_ids = [pin['target_id']]
                
                if not target_ids or pin['is_input']:
                    continue
                
                # 源端口 Y（节点内相对坐标，与渲染代码一致）
                src_pin_y_offset = PIN_START_Y + params_offset + pi * (PIN_H + PIN_GAP) + PIN_H / 2
                src_x = nx + NODE_W
                src_y = ny + src_pin_y_offset

                # 为每个目标节点生成连线
                for target_id in target_ids:
                    # 找目标节点
                    target = next((t for t in node_data if t['id'] == target_id), None)
                    if target:
                        tx = target['x'] + offset_x
                        ty_base = target['y'] + offset_y

                        # 按 kind 找最佳目标输入端口，优先匹配名称
                        conn_kind = pin['conn_kind']
                        # conn_kind 来自 GIA shell，OUT_PARAM(4) 需映射到 IN_PARAM(3)
                        lookup_kind = PIN_KIND_IN_PARAM if conn_kind == PIN_KIND_OUT_PARAM else conn_kind
                        tgt_y = ty_base + HEADER_H  # 默认：标题栏下方

                        result = find_best_input_pin(
                            input_lookup, target_id, lookup_kind,
                            pin_name=pin['kind_name'],
                        )
                        if result:
                            _, tgt_y_offset, _ = result
                            tgt_y = ty_base + tgt_y_offset

                        # 根据 kind 选择颜色和箭头
                        if conn_kind == PIN_KIND_IN_FLOW:
                            color = "#ff9800"  # flow: 橙色
                            arrow_id = f"arrow-{gi}"
                        else:
                            color = "#ce93d8"  # data: 紫色
                            arrow_id = f"arrow-data-{gi}"

                        # 画贝塞尔曲线
                        dx = abs(tx - src_x)
                        ctrl = max(dx * 0.5, 60)
                        lines_svg.append(
                            f'<path d="M{src_x:.1f},{src_y:.1f} '
                            f'C{src_x+ctrl:.1f},{src_y:.1f} '
                            f'{tx-ctrl:.1f},{tgt_y:.1f} '
                            f'{tx:.1f},{tgt_y:.1f}" '
                            f'stroke="{color}" stroke-width="2" fill="none" '
                            f'marker-end="url(#{arrow_id})"/>'
                        )

        # ── SVG 内容 ───────────────────────────────
        svg_id = f"svg-graph-{gi}"
        svg_ids.append(svg_id)

        svg_content = f'<defs>\n'
        # flow 箭头（橙色）
        svg_content += f'<marker id="arrow-{gi}" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">\n'
        svg_content += f'<path d="M0,0 L10,5 L0,10 z" fill="#ff9800"/></marker>\n'
        # data 箭头（紫色）
        svg_content += f'<marker id="arrow-data-{gi}" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">\n'
        svg_content += f'<path d="M0,0 L10,5 L0,10 z" fill="#ce93d8"/></marker>\n'
        svg_content += '</defs>\n'

        for line in lines_svg:
            svg_content += line + '\n'

        # 绘制节点
        for nd in node_data:
            nx = nd['x'] + offset_x
            ny = nd['y'] + offset_y

            # 节点背景
            svg_content += f'<rect x="{nx:.1f}" y="{ny:.1f}" width="{NODE_W}" height="{nd["h"]}" '
            svg_content += f'rx="6" fill="#1e1e2e" stroke="#444" stroke-width="1"/>\n'

            # 标题栏
            svg_content += f'<rect x="{nx:.1f}" y="{ny:.1f}" width="{NODE_W}" height="{HEADER_H}" rx="6" fill="#333" opacity="0.8"/>\n'
            svg_content += f'<rect x="{nx:.1f}" y="{ny+12:.1f}" width="{NODE_W}" height="10" fill="#333" opacity="0.8"/>\n'
            svg_content += f'<text x="{nx+8:.1f}" y="{ny+15:.1f}" fill="#ccc" font-size="11" font-family="monospace">{nd["label"]}</text>\n'

            # 节点参数行（如监听信号的「信号名:Str」）
            params_line_y = ny + HEADER_H
            if nd.get('params_text'):
                svg_content += f'<text x="{nx+8:.1f}" y="{ny+34:.1f}" fill="#888" font-size="9" font-family="monospace">⚙ {nd["params_text"]}</text>\n'
                params_line_y += 14  # 为参数行预留空间

            # 端口
            pin_y = ny + (PIN_START_Y if not nd.get('params_text') else PIN_START_Y + 14)
            for pi, pin in enumerate(nd['pins']):
                color = PIN_KIND_COLORS.get(pin['kind'], '#888')
                pcy = pin_y + PIN_H / 2
                is_flow = pin['kind'] in (PIN_KIND_IN_FLOW, PIN_KIND_OUT_FLOW)

                if is_flow:
                    # flow 引脚：三角形
                    if pin['is_input']:
                        svg_content += f'<polygon points="{nx+PIN_W:.1f},{pcy:.1f} {nx:.1f},{pcy-6:.1f} {nx:.1f},{pcy+6:.1f}" '
                    else:
                        svg_content += f'<polygon points="{nx+NODE_W:.1f},{pcy:.1f} {nx+NODE_W-PIN_W:.1f},{pcy-6:.1f} {nx+NODE_W-PIN_W:.1f},{pcy+6:.1f}" '
                    svg_content += f'fill="{color}" stroke="none"/>\n'
                else:
                    # data 引脚：圆形
                    if pin['is_input']:
                        cx = nx + PIN_W / 2
                    else:
                        cx = nx + NODE_W - PIN_W / 2
                    svg_content += f'<circle cx="{cx:.1f}" cy="{pcy:.1f}" r="5" fill="{color}" stroke="none"/>\n'

                # 端口标签
                label_text = pin['kind_name']
                is_cfg = pin.get('is_configurable')
                
                # 对于 configurable 引脚，取 GIA 中实际 var_type 来显示类型
                type_indicator = ""
                if is_cfg:
                    # 从 GIA 中读取实际 var_type
                    cfg_type = _cfg_type_name(pin.get('var_type', 0))
                    type_indicator = f" ({cfg_type})"
                    label_text = f"⚙ {pin['kind_name']}{type_indicator}"
                
                # 附加信息：branch value / 参数值等
                extra_text = None
                if is_cfg:
                    # configurable 引脚：优先显示 GIA 中的实际值(param)，否则显示默认值(pin_extra)
                    if pin.get('param') is not None:
                        extra_text = pin['param']
                    elif pin.get('pin_extra') is not None:
                        extra_text = pin['pin_extra']
                else:
                    if pin.get('param') is not None:
                        extra_text = f":{pin['param']}"
                    elif pin.get('pin_extra') is not None:
                        # 显示默认值（输入和输出都显示）
                        extra_text = f"={pin['pin_extra']}"

                text_x = nx + 20 if pin['is_input'] else nx + NODE_W - 20
                text_anchor = 'start' if pin['is_input'] else 'end'
                
                # configurable 引脚的颜色改暗金
                if is_cfg:
                    text_color = "#d4a574"
                else:
                    text_color = color
                
                # 参数值颜色（浅绿色，区分名称和值）
                VALUE_COLOR = "#7dcea0"
                
                # 渲染
                if not is_cfg and pin.get('pin_extra') is not None and not pin['is_input'] and pin.get('param') is None:
                    # 输出端口带默认值（如分支值=0）
                    main_label = pin['kind_name']
                    svg_content += f'<text x="{text_x:.1f}" y="{pcy+4:.1f}" fill="{color}" '
                    svg_content += f'font-size="9" font-family="monospace" text-anchor="{text_anchor}">{main_label}</text>\n'
                    svg_content += f'<text x="{text_x + (40 if text_anchor=="end" else len(main_label)*5+2):.1f}" y="{pcy+4:.1f}" fill="#888" '
                    svg_content += f'font-size="8" font-family="monospace" text-anchor="start">{extra_text}</text>\n'
                elif extra_text:
                    # 名称和值分开渲染，值用不同颜色
                    if is_cfg:
                        # configurable: "⚙ 名称 (类型): 值"
                        display_label = f"⚙ {pin['kind_name']}{type_indicator}"
                        svg_content += f'<text x="{text_x:.1f}" y="{pcy+4:.1f}" fill="{text_color}" '
                        svg_content += f'font-size="9" font-family="monospace" text-anchor="{text_anchor}">{display_label}</text>\n'
                        # 值紧随其后
                        val_offset = len(display_label) * 5 + 4 if text_anchor == 'start' else -(len(extra_text) * 5 + 4)
                        svg_content += f'<text x="{text_x + val_offset:.1f}" y="{pcy+4:.1f}" fill="{VALUE_COLOR}" '
                        svg_content += f'font-size="9" font-family="monospace" text-anchor="{text_anchor}">{extra_text}</text>\n'
                    else:
                        # 普通: 名称在上，值在下（灰色稍小，类似双分支的"是否"）
                        main_label = pin['kind_name']
                        # 名称
                        svg_content += f'<text x="{text_x:.1f}" y="{pcy:.1f}" fill="{text_color}" '
                        svg_content += f'font-size="9" font-family="monospace" text-anchor="{text_anchor}">{main_label}</text>\n'
                        # 值在下方（灰色，稍小）
                        svg_content += f'<text x="{text_x:.1f}" y="{pcy+10:.1f}" fill="#888" '
                        svg_content += f'font-size="8" font-family="monospace" text-anchor="{text_anchor}">{extra_text}</text>\n'
                else:
                    svg_content += f'<text x="{text_x:.1f}" y="{pcy+4:.1f}" fill="{text_color}" '
                    svg_content += f'font-size="9" font-family="monospace" text-anchor="{text_anchor}">{label_text}</text>\n'

                pin_y += PIN_H + PIN_GAP

        svg_parts.append(f'<h3 style="color:#ccc;font-family:monospace;">图: {graph["name"]} ({len(nodes)} 节点)</h3>')
        svg_parts.append(f'<div id="container-{gi}" style="width:100%;height:500px;border:1px solid #333;background:#1a1a2e;border-radius:8px;overflow:hidden;position:relative;margin-bottom:20px;">')
        svg_parts.append(f'<svg id="{svg_id}" width="{svg_w:.1f}" height="{svg_h:.1f}" '
                         f'style="cursor:grab;display:block;" '
                         f'onmousedown="startPan(event,\'{svg_id}\')">')
        svg_parts.append(svg_content)
        svg_parts.append('</svg>')

        # 控制按钮
        svg_parts.append(f'<div style="position:absolute;top:10px;right:10px;display:flex;gap:4px;">')
        svg_parts.append(f'<button onclick="zoomIn(\'{svg_id}\')" style="background:#333;color:#ccc;border:1px solid #555;padding:4px 8px;cursor:pointer;border-radius:4px;font-size:12px;">🔍+</button>')
        svg_parts.append(f'<button onclick="zoomOut(\'{svg_id}\')" style="background:#333;color:#ccc;border:1px solid #555;padding:4px 8px;cursor:pointer;border-radius:4px;font-size:12px;">🔍-</button>')
        svg_parts.append(f'<button onclick="resetView(\'{svg_id}\')" style="background:#333;color:#ccc;border:1px solid #555;padding:4px 8px;cursor:pointer;border-radius:4px;font-size:12px;">⟲</button>')
        svg_parts.append('</div>')

        # 节点信息悬浮提示区域
        svg_parts.append('</div>')

    # ── JavaScript 缩放/平移 ──────────────────────
    pan_js = '''
<script>
let svgState = {};

function initSVG(svgId) {
    svgState[svgId] = {scale: 1, tx: 0, ty: 0, dragging: false, startX: 0, startY: 0};
}
''' + '\n'.join(f'initSVG("{sid}");' for sid in svg_ids) + '''
</script>
<script>
function startPan(e, svgId) {
    const svg = document.getElementById(svgId);
    const state = svgState[svgId];
    if (!state) return;
    state.dragging = true;
    state.startX = e.clientX - state.tx;
    state.startY = e.clientY - state.ty;
    svg.style.cursor = 'grabbing';

    function onMove(ev) {
        if (!state.dragging) return;
        state.tx = ev.clientX - state.startX;
        state.ty = ev.clientY - state.startY;
        applyTransform(svgId);
    }
    function onUp() {
        state.dragging = false;
        svg.style.cursor = 'grab';
        window.removeEventListener('mousemove', onMove);
        window.removeEventListener('mouseup', onUp);
    }
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
}

function applyTransform(svgId) {
    const state = svgState[svgId];
    if (!state) return;
    const svg = document.getElementById(svgId);
    svg.style.transform = `translate(${state.tx}px, ${state.ty}px) scale(${state.scale})`;
    svg.style.transformOrigin = '0 0';
}

function zoomIn(svgId) {
    const state = svgState[svgId];
    if (!state) return;
    state.scale = Math.min(state.scale * 1.2, 5);
    applyTransform(svgId);
}

function zoomOut(svgId) {
    const state = svgState[svgId];
    if (!state) return;
    state.scale = Math.max(state.scale / 1.2, 0.1);
    applyTransform(svgId);
}

function resetView(svgId) {
    const state = svgState[svgId];
    if (!state) return;
    state.scale = 1;
    state.tx = 0;
    state.ty = 0;
    applyTransform(svgId);
}

// 滚轮缩放
''' + '\n'.join(f'''document.getElementById("{sid}").addEventListener('wheel', function(e) {{
    e.preventDefault();
    const state = svgState["{sid}"];
    if (!state) return;
    const factor = e.deltaY < 0 ? 1.1 : 0.9;
    state.scale = Math.max(0.1, Math.min(5, state.scale * factor));
    applyTransform("{sid}");
}});''' for sid in svg_ids) + '''
</script>
'''

    # 图例
    legend = '''
<div style="display:flex;gap:16px;margin-bottom:16px;font-family:monospace;font-size:12px;">
<span style="color:#4fc3f7;">▶ 流程引脚 (flow)</span>
<span style="color:#81c784;">● 数据引脚 (data)</span>
<span style="color:#d4a574;">⚙ 可配置引脚</span>
<span style="color:#ff9800;">━ 流程连线</span>
<span style="color:#ce93d8;">━ 数据连线</span>
</div>'''

    html = f'''<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<title>GIA 可视化 - {gia_path.name}</title>
<style>
body {{ background:#0d1117; margin:20px; font-family:monospace; color:#ccc; }}
h2 {{ color:#58a6ff; }}
h3 {{ color:#8b949e; margin-top:8px; }}
.info {{ color:#8b949e; font-size:13px; margin-bottom:15px; }}
</style>
</head>
<body>
<h2>📊 {gia_path.name}</h2>
<div class="info">文件: {gia_path} | 节点图数: {len(graphs)} | 生成时间: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
{legend}
{''.join(svg_parts)}
{pan_js}
</body>
</html>'''
    return html


def main():
    parser = argparse.ArgumentParser(description="GIA 节点图可视化工具（增强版）")
    parser.add_argument("gia_file", help="GIA 文件路径")
    parser.add_argument("--output", "-o", help="输出 HTML 路径（默认与 GIA 同名）")
    args = parser.parse_args()

    gia_path = Path(args.gia_file)
    if not gia_path.exists():
        print(f"❌ 文件不存在: {gia_path}")
        sys.exit(1)

    print(f"加载: {gia_path}")
    graphs = extract_graph(gia_path)

    if not graphs:
        print("⚠️ 未找到节点图")
        sys.exit(0)

    print(f"找到 {len(graphs)} 个节点图")
    for i, g in enumerate(graphs):
        nodes = g['nodes']
        print(f"  图[{i}]: {g['name']} - {len(nodes)} 节点")
        # 统计连线
        conn_count = 0
        for n in nodes:
            pins = parse_pins(n)
            conn_count += sum(1 for p in pins if p['target_id'])
        print(f"         连线: {conn_count}")

    html = generate_html(gia_path, graphs)

    output = Path(args.output) if args.output else gia_path.with_suffix('.html')
    output.write_text(html, encoding='utf-8')
    print(f"✅ 已生成: {output}")


if __name__ == "__main__":
    main()
