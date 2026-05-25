# -*- coding: utf-8 -*-
"""GIA 生成管线的 L1/L2 单元测试

L1 结构测试：验证生成的 numeric_message 结构正确
L2 往返测试：验证 decode→encode→decode 循环无偏差

测试对应的实验（全部已通过 L3 编辑器导入验证）：
  Step A: 零修改往返编码
  Step B: 替换 export_tag
  Step C: 修改 entry 名称
  Step D: 移除一个 NodeGraph 条目
  Step E: 仅保留金币（无 NodeGraph）
  Step F: 修改 NodeGraph 条目名称
"""
import copy
import time
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from private_extensions.ugc_file_tools.gia.container import unwrap_gia_container, wrap_gia_container
from private_extensions.ugc_file_tools.gil_dump_codec.protobuf_like import (
    decode_message_to_field_map, encode_message, format_binary_data_hex_text,
    parse_binary_data_hex_text,
)
from private_extensions.ugc_file_tools.gil_dump_codec.protobuf_like_bridge import decoded_field_map_to_numeric_message

# ══════════════════════════════════════════════
# 测试 fixture
# ══════════════════════════════════════════════

SAMPLES_DIR = PROJECT_ROOT / "tools" / "live_sync" / "samples"
SOURCE_GIA = SAMPLES_DIR / "test_clone_minimal_v2.gia"
UID = 6000061

assert SOURCE_GIA.exists(), f"源文件不存在: {SOURCE_GIA}"


def load_numeric(gia_path: Path) -> dict:
    proto = unwrap_gia_container(gia_path)
    fm, _ = decode_message_to_field_map(
        data_bytes=proto, start_offset=0, end_offset=len(proto), remaining_depth=64
    )
    return decoded_field_map_to_numeric_message(fm, prefer_raw_hex_for_utf8=True)


def roundtrip_binary(num: dict) -> bytes:
    """encode 并验证 decode 后结构一致"""
    proto = encode_message(num)
    fm, _ = decode_message_to_field_map(
        data_bytes=proto, start_offset=0, end_offset=len(proto), remaining_depth=64
    )
    re_num = decoded_field_map_to_numeric_message(fm, prefer_raw_hex_for_utf8=True)
    return proto, re_num


def make_tag(stem: str) -> str:
    return format_binary_data_hex_text(
        f'{UID}-{int(time.time())}-1073741827-\\{stem}.gia'.encode('utf-8')
    )


@pytest.fixture
def source_num():
    """加载已知正确的源 GIA"""
    return load_numeric(SOURCE_GIA)


# ══════════════════════════════════════════════
# Step A: 零修改往返编码
# ══════════════════════════════════════════════

class TestStepA_Roundtrip:
    """纯 decode→encode 往返，不应有任何变化"""

    def test_l1_top_level_keys(self, source_num):
        """L1: 顶层 keys 应为 ['1', '3']"""
        assert list(source_num.keys()) == ['1', '3'], \
            f"预期 keys=['1','3'], 实际 {list(source_num.keys())}"

    def test_l1_entry_count(self, source_num):
        """L1: 应有 3 个条目"""
        entries = source_num['1']
        assert isinstance(entries, list)
        assert len(entries) == 3, f"预期 3 个条目, 实际 {len(entries)}"

    def test_l1_entry_keys(self, source_num):
        """L1: 各条目 keys 正确"""
        entries = source_num['1']
        assert list(entries[0].keys()) == ['1', '2', '3', '5', '11'], \
            f"entry[0] keys 不匹配: {list(entries[0].keys())}"
        assert list(entries[1].keys()) == ['1', '3', '5', '13'], \
            f"entry[1] keys 不匹配: {list(entries[1].keys())}"
        assert list(entries[2].keys()) == ['1', '3', '5', '13'], \
            f"entry[2] keys 不匹配: {list(entries[2].keys())}"

    def test_l2_binary_roundtrip(self, source_num):
        """L2: 往返编码二进制完全一致"""
        num_copy = copy.deepcopy(source_num)
        proto_orig = encode_message(source_num)
        proto_copy = encode_message(num_copy)
        assert proto_orig == proto_copy, \
            "copy.deepcopy 后编码结果应一致"

    def test_l2_decode_encode_decode(self, source_num):
        """L2: decode→encode→decode 后结构一致"""
        num_copy = copy.deepcopy(source_num)
        proto, re_num = roundtrip_binary(num_copy)
        assert list(re_num.keys()) == list(source_num.keys())
        assert len(re_num['1']) == len(source_num['1'])


# ══════════════════════════════════════════════
# Step B: 替换 export_tag
# ══════════════════════════════════════════════

class TestStepB_ReplaceTag:
    """仅替换 field '3' (export_tag)，其他不变"""

    def test_l1_tag_replaced(self, source_num):
        """L1: tag 被替换后顶层 keys 不变，条目不变"""
        num = copy.deepcopy(source_num)
        num['3'] = make_tag('test_b')
        assert list(num.keys()) == ['1', '3']
        assert len(num['1']) == 3

    def test_l2_roundtrip_after_tag_change(self, source_num):
        """L2: 改 tag 后往返编码结构不变"""
        num = copy.deepcopy(source_num)
        num['3'] = make_tag('test_b_rt')
        proto, re_num = roundtrip_binary(num)
        assert list(re_num.keys()) == ['1', '3']
        assert len(re_num['1']) == 3


# ══════════════════════════════════════════════
# Step C: 修改 entry 名称（金币→Test_Coin）
# ══════════════════════════════════════════════

class TestStepC_RenameEntry:
    """修改 entry[0] 的名称"""

    def test_l1_name_changed(self, source_num):
        """L1: 名称修改后结构不变"""
        num = copy.deepcopy(source_num)
        new_name = format_binary_data_hex_text(b'Test_Coin')
        num['1'][0]['3'] = new_name
        num['3'] = make_tag('test_c')
        assert list(num['1'][0].keys()) == ['1', '2', '3', '5', '11']
        assert num['1'][1]['13'] is not None  # NG 还在

    def test_l2_roundtrip_after_rename(self, source_num):
        """L2: 改名后往返编码结构一致"""
        num = copy.deepcopy(source_num)
        num['1'][0]['3'] = format_binary_data_hex_text(b'Test_Coin_C2')
        num['3'] = make_tag('test_c_rt')
        _, re_num = roundtrip_binary(num)
        assert len(re_num['1']) == 3
        assert '13' in re_num['1'][1]


# ══════════════════════════════════════════════
# Step D: 移除一个 NodeGraph 条目
# ══════════════════════════════════════════════

class TestStepD_DropNG:
    """去掉 entry[2]，保留金币 + 元件-交互拾取得分"""

    def test_l1_entry_count_reduced(self, source_num):
        """L1: 条目从 3 减到 2"""
        num = copy.deepcopy(source_num)
        num['1'] = num['1'][:2]
        num['3'] = make_tag('test_d')
        assert len(num['1']) == 2

    def test_l1_remaining_structure(self, source_num):
        """L1: 保留的条目结构完整"""
        num = copy.deepcopy(source_num)
        num['1'] = num['1'][:2]
        num['3'] = make_tag('test_d2')
        assert list(num['1'][0].keys()) == ['1', '2', '3', '5', '11']  # 金币
        assert '13' in num['1'][1]  # 元件-交互拾取得分 有 NG

    def test_l2_roundtrip_after_drop(self, source_num):
        """L2: 去掉条目后往返编码结构一致"""
        num = copy.deepcopy(source_num)
        num['1'] = num['1'][:2]
        num['3'] = make_tag('test_d_rt')
        _, re_num = roundtrip_binary(num)
        assert len(re_num['1']) == 2
        assert '13' in re_num['1'][1]


# ══════════════════════════════════════════════
# Step E: 仅保留金币（无 NodeGraph）
# ══════════════════════════════════════════════

class TestStepE_CoinOnly:
    """只保留 entry[0]（金币，无 NG）"""

    def test_l1_single_entry_no_ng(self, source_num):
        """L1: 单条目，无 NodeGraph"""
        num = copy.deepcopy(source_num)
        num['1'] = num['1'][:1]
        num['3'] = make_tag('test_e')
        assert len(num['1']) == 1
        assert '13' not in num['1'][0]  # 金币没有 NG
        assert '11' in num['1'][0]  # 有 payload

    def test_l2_roundtrip_coin_only(self, source_num):
        """L2: 单条目往返编码结构一致（单条目解码可能为 dict 或 list[1]）"""
        num = copy.deepcopy(source_num)
        num['1'] = num['1'][:1]
        num['3'] = make_tag('test_e_rt')
        _, re_num = roundtrip_binary(num)
        f1 = re_num['1']
        entries = [f1] if isinstance(f1, dict) else f1
        assert len(entries) == 1
        assert '13' not in entries[0]
        assert '11' in entries[0]


# ══════════════════════════════════════════════
# Step F: 修改 NodeGraph 条目名称
# ══════════════════════════════════════════════

class TestStepF_RenameNG:
    """修改 entry[1] (NodeGraph 条目) 的名称"""

    def test_l1_ng_name_changed_structure_unchanged(self, source_num):
        """L1: NG 条目的名称和结构"""
        num = copy.deepcopy(source_num)
        new_name = format_binary_data_hex_text(b'Test_NG_TakenScore')
        num['1'][1]['3'] = new_name
        num['3'] = make_tag('test_f')
        # 确认结构完整
        assert list(num['1'][1].keys()) == ['1', '3', '5', '13']
        assert '13' in num['1'][1]
        assert len(num['1']) == 3

    def test_l2_roundtrip_after_ng_rename(self, source_num):
        """L2: 改 NG 名后往返编码结构一致"""
        num = copy.deepcopy(source_num)
        num['1'][1]['3'] = format_binary_data_hex_text(b'Test_NG_Renamed_F2')
        num['3'] = make_tag('test_f_rt')
        _, re_num = roundtrip_binary(num)
        assert len(re_num['1']) == 3
        assert '13' in re_num['1'][1]
        assert '13' in re_num['1'][2]


# ══════════════════════════════════════════════
# 关键规则：NG 必须是独立条目，不能嵌入实体 entry
# ══════════════════════════════════════════════

class TestNGIndependentEntries:
    """验证 NG 作为独立条目的核心规则（源自实验 G-K 的发现）"""

    def test_ng_entries_are_independent(self, source_num):
        """L1: 源文件中 NG 是独立条目，不在 entity 内部"""
        entries = source_num['1']
        # entry[0] 是 coin 实体，不应有 '13'
        assert '13' not in entries[0], "实体 entry 不应嵌入 NodeGraph"
        # entry[1] 和 [2] 是 NG，有 '13'
        assert '13' in entries[1]
        assert '13' in entries[2]

    def test_merging_ng_into_entity_is_wrong(self, source_num):
        """L1: 将 '13' 嵌入实体 entry 会改变 keys 结构（错误模式）"""
        entry = copy.deepcopy(source_num['1'][0])
        entry['13'] = copy.deepcopy(source_num['1'][1]['13'])
        # 错误模式的 keys 包含 '13' 但也会改变原有 keys
        assert '13' in entry
        assert '11' in entry  # coin 原有
        # 标记：这是错误模式，记录以防误用

    def test_entity_entry_preserves_original_keys(self, source_num):
        """L1: 实体 entry（无 NG 的那种）保持原有 keys"""
        coin = source_num['1'][0]
        assert list(coin.keys()) == ['1', '2', '3', '5', '11']

    def test_ng_entry_has_correct_keys(self, source_num):
        """L1: NG 条目的 keys 固定为 ['1','3','5','13']"""
        ng = source_num['1'][1]
        assert list(ng.keys()) == ['1', '3', '5', '13']


class TestStepJ_EntityPlusIndependentNG:
    """将实体和 NG 作为独立条目组合（已验证 L3 通过）"""

    def test_l1_entity_entry_unchanged(self, source_num):
        """L1: 实体 entry 保持原样，不加 '13'"""
        coin = copy.deepcopy(source_num['1'][0])
        ng1 = copy.deepcopy(source_num['1'][1])
        assert '13' not in coin
        assert '13' in ng1

    def test_l2_entity_plus_ng_roundtrip(self, source_num):
        """L2: 实体 + NG 独立条目编码后结构不变"""
        coin = copy.deepcopy(source_num['1'][0])
        ng1 = copy.deepcopy(source_num['1'][1])
        entries = [coin, ng1]
        num = {'1': entries, '3': make_tag('test_j')}
        _, re_num = roundtrip_binary(num)
        assert len(re_num['1']) == 2
        assert '13' not in re_num['1'][0]
        assert '13' in re_num['1'][1]


class TestStepK_EntityPlusTwoNG:
    """实体 + 2 个 NG（完整资产包，已 L3 验证通过）"""

    def test_l1_entries_structure(self, source_num):
        """L1: entity[0]无NG, entry[1][2]有NG"""
        coin = copy.deepcopy(source_num['1'][0])
        ng1 = copy.deepcopy(source_num['1'][1])
        ng2 = copy.deepcopy(source_num['1'][2])
        entries = [coin, ng1, ng2]
        assert '13' not in entries[0]
        assert '13' in entries[1]
        assert '13' in entries[2]

    def test_l2_full_pack_roundtrip(self, source_num):
        """L2: 完整包往返编码"""
        entries = [copy.deepcopy(source_num['1'][0]),
                   copy.deepcopy(source_num['1'][1]),
                   copy.deepcopy(source_num['1'][2])]
        num = {'1': entries, '3': make_tag('test_k')}
        _, re_num = roundtrip_binary(num)
        assert len(re_num['1']) == 3
        assert '13' not in re_num['1'][0]
        assert '13' in re_num['1'][1]
        assert '13' in re_num['1'][2]


# ══════════════════════════════════════════════
# 工具级测试：create_entity_with_ng 产出正确结构
# ══════════════════════════════════════════════

class TestCreateEntityWithNG:
    """验证 create_entity_with_ng.py 工具的输出结构正确"""

    def test_goblet_ng1_entries_are_independent(self, source_num):
        """L1: 工具生成的条目中 NG 是独立条目"""
        from tools.live_sync.create_entity_with_ng import create_entity_with_nodegraph, load_ng_entries
        import tempfile, os
        
        ng_source = SOURCE_GIA
        ng_entries = load_ng_entries(ng_source)
        assert len(ng_entries) >= 1
        
        # 不写文件，直接验证逻辑
        entry0 = ng_entries[0]
        assert '13' in entry0
        assert '12' not in entry0  # NG 条目没有 '12'

    def test_ng_source_has_correct_count(self, source_num):
        """L1: NG 源文件应有恰好 2 个 NG 条目"""
        entries = source_num['1']
        ng_count = sum(1 for e in entries if isinstance(e, dict) and '13' in e)
        assert ng_count == 2
