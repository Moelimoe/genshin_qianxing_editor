# -*- coding: utf-8 -*-
"""批量处理器测试"""
import shutil
from pathlib import Path

import pytest

from tools.live_sync.gia_utils import save_gia_numeric, make_binary_name, load_gia_numeric
from tools.live_sync.node_catalog import NodeCatalog, NodeDef, PinDef, VarType
from tools.live_sync.gia_loader import GIALoader
from tools.live_sync.batch_processor import (
    BatchProcessor,
    BatchResult,
    ModifyRule,
    modify_param_rule,
    rename_signal_rule,
)


# ── 固件 ──────────────────────────────────────────────────

@pytest.fixture
def catalog():
    return NodeCatalog.default()


@pytest.fixture
def sample_gias(tmp_path):
    """创建3个测试GIA文件，每个包含一个监听信号节点"""
    files = []
    for i in range(3):
        ng_entry = {
            '1': {'2': 5, '4': 1073741820 + i},
            '3': make_binary_name(f"TestGraph{i}"),
            '5': 9,
            '13': {
                '1': {
                    '1': {
                        '1': {'1': 10000, '2': 20000, '3': 21001, '5': 1073741830 + i},
                        '2': make_binary_name(f"TestGraph{i}"),
                        '3': [
                            {
                                '1': 1,
                                '2': {'1': 10001, '2': 20000, '3': 22000, '5': 300001},
                                '3': {'1': 10001, '2': 20000, '3': 22000, '5': 300001},
                                '4': [
                                    {
                                        '1': {'1': 3, '2': 0},
                                        '2': {'1': 3, '2': 0},
                                        '3': {
                                            '1': VarType.Str,
                                            '2': {'1': make_binary_name(f"signal_{i}")}
                                        },
                                        '4': VarType.Str,
                                    },
                                    {
                                        '1': {'1': 2},
                                        '2': {'1': 2},
                                        '4': 0,
                                    },
                                ],
                                '5': 100,
                                '6': 200,
                            },
                        ],
                        '101': 0.3,
                    },
                },
            },
        }
        entity_entry = {
            '1': {'2': 1, '3': 1, '4': 1077936129},
            '3': make_binary_name(f"TestEntity{i}"),
            '5': 1,
            '11': {'1': {'1': 1077936129, '2': 1, '6': [], '7': [], '8': [], '10': 1}},
        }
        msg = {
            '1': [entity_entry, ng_entry],
            '3': make_binary_name(f"test_{i}.gia"),
        }
        gia_path = tmp_path / f"test_{i}.gia"
        save_gia_numeric(msg, gia_path)
        files.append(gia_path)
    return files


@pytest.fixture
def output_dir(tmp_path):
    d = tmp_path / "output"
    d.mkdir()
    return d


# ── BatchResult 测试 ──────────────────────────────────────

class TestBatchResult:
    def test_empty_result(self):
        r = BatchResult()
        assert r.total == 0
        assert r.success == 0
        assert r.failed == 0
        assert r.skipped == 0
        assert r.ok

    def test_all_success(self):
        r = BatchResult()
        r.total = 3
        r.success = 3
        assert r.ok
        assert r.failed == 0

    def test_has_failures(self):
        r = BatchResult()
        r.total = 3
        r.success = 2
        r.failed = 1
        assert not r.ok


# ── ModifyRule 工厂函数测试 ───────────────────────────────

class TestModifyRules:
    def test_modify_param_rule(self):
        rule = modify_param_rule("信号名", "new_signal")
        assert rule.param_name == "信号名"
        assert rule.new_value == "new_signal"

    def test_rename_signal_rule(self):
        rule = rename_signal_rule("old_signal", "new_signal")
        assert rule.param_name == "信号名"
        assert rule.old_value == "old_signal"
        assert rule.new_value == "new_signal"


# ── BatchProcessor 核心测试 ──────────────────────────────

class TestBatchProcessor:
    def test_process_empty_list(self, catalog, output_dir):
        """空文件列表应返回空结果"""
        bp = BatchProcessor(catalog=catalog)
        result = bp.process([], [modify_param_rule("信号名", "x")], output_dir)
        assert result.total == 0
        assert result.ok

    def test_process_single_file(self, catalog, sample_gias, output_dir):
        """处理单个文件"""
        bp = BatchProcessor(catalog=catalog)
        rule = modify_param_rule("信号名", "unified_signal")
        result = bp.process(sample_gias[:1], [rule], output_dir)
        
        assert result.total == 1
        assert result.success == 1
        assert result.ok

    def test_process_multiple_files(self, catalog, sample_gias, output_dir):
        """批量处理多个文件"""
        bp = BatchProcessor(catalog=catalog)
        rule = modify_param_rule("信号名", "unified_signal")
        result = bp.process(sample_gias, [rule], output_dir)
        
        assert result.total == 3
        assert result.success == 3
        assert result.ok

    def test_output_files_created(self, catalog, sample_gias, output_dir):
        """输出文件应被创建"""
        bp = BatchProcessor(catalog=catalog)
        rule = modify_param_rule("信号名", "unified_signal")
        bp.process(sample_gias, [rule], output_dir)
        
        for src in sample_gias:
            out = output_dir / src.name
            assert out.exists()

    def test_param_actually_modified(self, catalog, sample_gias, output_dir):
        """参数应被实际修改"""
        bp = BatchProcessor(catalog=catalog)
        rule = modify_param_rule("信号名", "unified_signal")
        bp.process(sample_gias, [rule], output_dir)
        
        # 验证输出文件中的参数已被修改
        for src in sample_gias:
            out = output_dir / src.name
            loader = GIALoader(catalog=catalog)
            loaded = loader.load(out)
            graph = loaded.get_graph(0)
            
            node = graph.get_node(0)
            assert node.get_param("信号名") == "unified_signal"

    def test_rename_signal_conditional(self, catalog, sample_gias, output_dir):
        """rename_signal_rule 只修改匹配的值"""
        bp = BatchProcessor(catalog=catalog)
        # 只修改 signal_0，不修改 signal_1 和 signal_2
        rule = rename_signal_rule("signal_0", "renamed_signal")
        result = bp.process(sample_gias, [rule], output_dir)
        
        assert result.success == 3
        
        # 验证：test_0.gia 被修改，其他不变
        loader = GIALoader(catalog=catalog)
        
        loaded0 = loader.load(output_dir / "test_0.gia")
        graph0 = loaded0.get_graph(0)
        assert graph0.get_node(0).get_param("信号名") == "renamed_signal"
        
        loaded1 = loader.load(output_dir / "test_1.gia")
        graph1 = loaded1.get_graph(0)
        assert graph1.get_node(0).get_param("信号名") == "signal_1"

    def test_dry_run_does_not_write(self, catalog, sample_gias, output_dir):
        """dry_run 模式不应写入文件"""
        bp = BatchProcessor(catalog=catalog)
        rule = modify_param_rule("信号名", "unified_signal")
        result = bp.process(sample_gias, [rule], output_dir, dry_run=True)
        
        assert result.total == 3
        assert result.success == 3
        # 输出目录应为空
        assert len(list(output_dir.iterdir())) == 0

    def test_nonexistent_input_skipped(self, catalog, output_dir):
        """不存在的输入文件应被跳过"""
        bp = BatchProcessor(catalog=catalog)
        fake_path = Path("/nonexistent/file.gia")
        rule = modify_param_rule("信号名", "x")
        result = bp.process([fake_path], [rule], output_dir)
        
        assert result.total == 1
        assert result.skipped == 1
        assert result.ok  # 跳过不算失败

    def test_validate_before_modify(self, catalog, sample_gias, output_dir):
        """验证失败的文件应被跳过"""
        bp = BatchProcessor(catalog=catalog)
        rule = modify_param_rule("信号名", "x")
        
        # 创建一个损坏的GIA文件
        bad_gia = sample_gias[0].parent / "bad.gia"
        bad_gia.write_bytes(b"not a valid gia file")
        
        result = bp.process([bad_gia] + sample_gias[:1], [rule], output_dir,
                           validate_before=True)
        
        assert result.total == 2
        assert result.skipped == 1  # 损坏的文件被跳过
        assert result.success == 1

    def test_multiple_rules_applied_sequentially(self, catalog, sample_gias, output_dir):
        """多条规则按顺序应用"""
        bp = BatchProcessor(catalog=catalog)
        rules = [
            modify_param_rule("信号名", "step1"),
            modify_param_rule("信号名", "step2"),
        ]
        result = bp.process(sample_gias[:1], rules, output_dir)
        
        # 最终值应该是 step2（后一条覆盖前一条）
        loader = GIALoader(catalog=catalog)
        loaded = loader.load(output_dir / sample_gias[0].name)
        graph = loaded.get_graph(0)
        assert graph.get_node(0).get_param("信号名") == "step2"

    def test_process_preserves_original(self, catalog, sample_gias, output_dir):
        """原始文件不应被修改"""
        bp = BatchProcessor(catalog=catalog)
        rule = modify_param_rule("信号名", "unified_signal")
        bp.process(sample_gias, [rule], output_dir)
        
        # 原始文件仍然存在且内容不变
        for src in sample_gias:
            assert src.exists()
            loader = GIALoader(catalog=catalog)
            loaded = loader.load(src)
            graph = loaded.get_graph(0)
            # 原始值未被修改
            val = graph.get_node(0).get_param("信号名")
            assert val != "unified_signal"
