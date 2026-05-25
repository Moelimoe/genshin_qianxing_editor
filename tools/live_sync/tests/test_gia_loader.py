# -*- coding: utf-8 -*-
"""GIA 加载器模块的 TDD 测试

测试覆盖：
1. 加载 GIA 文件
2. 提取节点图
3. 节点转换
4. 连线重建
5. 参数提取
6. 多图支持
7. 修改后导出
8. 错误处理
9. 与 LevelExporter 集成
10. 端到端场景
"""
from __future__ import annotations

import struct
from pathlib import Path
from typing import Any, Dict

import pytest

from tools.live_sync.gia_loader import GIALoader, LoadedLevel, load_gia, load_graph
from tools.live_sync.level_builder import GraphBuilder, NodeCatalog, NodeDef, PinDef
from tools.live_sync.node_catalog import VarType
from tools.live_sync.gia_utils import (
    load_gia_numeric, get_entries, get_ng_graph, get_ng_nodes, save_gia_numeric,
    make_binary_name, get_entry_name,
)
from tools.live_sync.level_exporter import LevelExporter
from tools.live_sync.validator import GIAValidator


# ═══════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
def catalog() -> NodeCatalog:
    """创建测试用节点注册表"""
    cat = NodeCatalog()
    # 监听信号 (event, type_id=300001)
    cat.register(NodeDef(
        type_id=300001, name="监听信号", category="event",
        description="监听信号事件",
        inputs=(
            PinDef(name="信号名", direction="In", is_flow=False, type_expr="Str", var_type=VarType.Str, index=0),
        ),
        outputs=(
            PinDef(name="出", direction="Out", is_flow=True, type_expr="", var_type=0, index=0),
        ),
    ))
    # 发送信号 (action, type_id=300000)
    cat.register(NodeDef(
        type_id=300000, name="发送信号", category="action",
        description="发送信号",
        inputs=(
            PinDef(name="入", direction="In", is_flow=True, type_expr="", var_type=0, index=0),
            PinDef(name="目标实体", direction="In", is_flow=False, type_expr="Ety", var_type=VarType.Ety, index=1),
            PinDef(name="信号名", direction="In", is_flow=False, type_expr="Str", var_type=VarType.Str, index=2),
        ),
        outputs=(
            PinDef(name="出", direction="Out", is_flow=True, type_expr="", var_type=0, index=0),
        ),
    ))
    # 创建元件 (action, type_id=252)
    cat.register(NodeDef(
        type_id=252, name="创建元件", category="action",
        description="创建元件",
        inputs=(
            PinDef(name="入", direction="In", is_flow=True, type_expr="", var_type=0, index=0),
            PinDef(name="元件ID", direction="In", is_flow=False, type_expr="Prefab", var_type=VarType.Prefab, index=1),
            PinDef(name="位置", direction="In", is_flow=False, type_expr="Vec", var_type=VarType.Vec, index=2),
        ),
        outputs=(
            PinDef(name="出", direction="Out", is_flow=True, type_expr="", var_type=0, index=0),
            PinDef(name="实体", direction="Out", is_flow=False, type_expr="Ety", var_type=VarType.Ety, index=1),
        ),
    ))
    # 多分支 (condition, type_id=3)
    cat.register(NodeDef(
        type_id=3, name="多分支", category="condition",
        description="多分支",
        inputs=(
            PinDef(name="入", direction="In", is_flow=True, type_expr="", var_type=0, index=0),
            PinDef(name="条件", direction="In", is_flow=False, type_expr="Int", var_type=VarType.Int, index=1),
        ),
        outputs=(
            PinDef(name="默认", direction="Out", is_flow=True, type_expr="", var_type=0, index=0),
            PinDef(name="分支0", direction="Out", is_flow=True, type_expr="", var_type=0, index=1),
            PinDef(name="分支1", direction="Out", is_flow=True, type_expr="", var_type=0, index=2),
        ),
    ))
    # 获取局部变量 (variable, type_id=18)
    cat.register(NodeDef(
        type_id=18, name="获取局部变量", category="variable",
        description="获取局部变量",
        inputs=(
            PinDef(name="变量引用", direction="In", is_flow=False, type_expr="Loc", var_type=16, index=0),
        ),
        outputs=(
            PinDef(name="值", direction="Out", is_flow=False, type_expr="Int", var_type=VarType.Int, index=0),
        ),
    ))
    return cat


@pytest.fixture
def sample_gia_path(tmp_path: Path) -> Path:
    """创建一个示例 GIA 文件用于测试"""
    # 构建一个简单的 GIA numeric dict
    # 包含一个 NG entry 和一个 entity entry
    
    # NG entry
    ng_entry = {
        '1': {'4': 1073741827},  # Location
        '3': make_binary_name("TestGraph"),
        '5': 0,
        '13': {
            '1': {
                '1': {
                    '3': [
                        # Node 0: 监听信号 (type_id=300001)
                        {
                            '1': 0,  # index
                            '2': 300001,  # type_id
                            '3': {},  # data_out
                            '4': [
                                # 信号名输入端口 (IN_PARAM)
                                {
                                    '1': {'1': 3, '2': 0},  # kind=3(IN_PARAM), index=0
                                    '2': {'1': 3, '2': 0},
                                    '3': {'1': VarType.Str, '2': {'1': make_binary_name("test_signal")}},
                                    '4': VarType.Str,
                                },
                                # 出输出端口 (OUT_FLOW)
                                {
                                    '1': {'1': 2, '2': 0},  # kind=2(OUT_FLOW), index=0
                                    '2': {'1': 2, '2': 0},
                                    '4': 0,
                                    '5': [
                                        # 连接到 node 1 的入端口
                                        {'1': 1, '2': {'1': 1, '2': 0}, '3': {'1': 1, '2': 0}},
                                    ],
                                },
                            ],
                            '5': 100,  # x
                            '6': 200,  # y
                        },
                        # Node 1: 发送信号 (type_id=300000)
                        {
                            '1': 1,  # index
                            '2': 300000,  # type_id
                            '3': {},
                            '4': [
                                # 入输入端口 (IN_FLOW)
                                {
                                    '1': {'1': 1, '2': 0},  # kind=1(IN_FLOW), index=0
                                    '2': {'1': 1, '2': 0},
                                    '4': 0,
                                },
                                # 目标实体输入端口 (IN_PARAM)
                                {
                                    '1': {'1': 3, '2': 1},  # kind=3(IN_PARAM), index=1
                                    '2': {'1': 3, '2': 1},
                                    '4': VarType.Ety,
                                },
                                # 信号名输入端口 (IN_PARAM)
                                {
                                    '1': {'1': 3, '2': 2},  # kind=3(IN_PARAM), index=2
                                    '2': {'1': 3, '2': 2},
                                    '3': {'1': VarType.Str, '2': {'1': make_binary_name("action_signal")}},
                                    '4': VarType.Str,
                                },
                                # 出输出端口 (OUT_FLOW)
                                {
                                    '1': {'1': 2, '2': 0},  # kind=2(OUT_FLOW), index=0
                                    '2': {'1': 2, '2': 0},
                                    '4': 0,
                                },
                            ],
                            '5': 400,  # x
                            '6': 200,  # y
                        },
                    ],
                },
            },
        },
    }
    
    # Entity entry (简化版)
    entity_entry = {
        '1': {'4': 1073741827},  # Location
        '3': make_binary_name("TestEntity"),
        '5': 0,
        '11': {'1': 12345},  # payload
    }
    
    msg = {
        '1': [entity_entry, ng_entry],
        '3': make_binary_name("test.gia"),
    }
    
    gia_path = tmp_path / "sample.gia"
    save_gia_numeric(msg, gia_path)
    return gia_path


@pytest.fixture
def loader(catalog: NodeCatalog) -> GIALoader:
    """创建 GIALoader 实例"""
    return GIALoader(catalog=catalog)


# ═══════════════════════════════════════════════════════════════
# 测试 1: 加载 GIA 文件
# ═══════════════════════════════════════════════════════════════

class TestLoadGIA:
    """测试加载 GIA 文件"""

    def test_load_returns_loaded_level(self, loader: GIALoader, sample_gia_path: Path):
        """GIALoader.load 应返回 LoadedLevel 对象"""
        result = loader.load(sample_gia_path)
        assert isinstance(result, LoadedLevel)

    def test_loaded_level_has_gia_path(self, loader: GIALoader, sample_gia_path: Path):
        """LoadedLevel 应包含 gia_path"""
        result = loader.load(sample_gia_path)
        assert result.gia_path == sample_gia_path

    def test_loaded_level_has_entries(self, loader: GIALoader, sample_gia_path: Path):
        """LoadedLevel 应包含 entries"""
        result = loader.load(sample_gia_path)
        assert len(result.entries) == 2

    def test_loaded_level_has_entity_entries(self, loader: GIALoader, sample_gia_path: Path):
        """LoadedLevel 应分类 entity entries"""
        result = loader.load(sample_gia_path)
        assert len(result.entity_entries) == 1
        assert '11' in result.entity_entries[0] or '12' in result.entity_entries[0]

    def test_loaded_level_has_ng_entries(self, loader: GIALoader, sample_gia_path: Path):
        """LoadedLevel 应分类 NG entries"""
        result = loader.load(sample_gia_path)
        assert len(result.ng_entries) == 1
        assert '13' in result.ng_entries[0]

    def test_loaded_level_has_export_tag(self, loader: GIALoader, sample_gia_path: Path):
        """LoadedLevel 应包含 export_tag"""
        result = loader.load(sample_gia_path)
        assert result.export_tag is not None
        assert isinstance(result.export_tag, str)

    def test_load_nonexistent_file_raises_error(self, loader: GIALoader, tmp_path: Path):
        """加载不存在的文件应抛出有意义的错误"""
        nonexistent = tmp_path / "nonexistent.gia"
        with pytest.raises((FileNotFoundError, ValueError)) as exc_info:
            loader.load(nonexistent)
        error_msg = str(exc_info.value).lower()
        assert any(word in error_msg for word in ['not found', '不存在', 'file', '找不到'])


# ═══════════════════════════════════════════════════════════════
# 测试 2: 提取节点图
# ═══════════════════════════════════════════════════════════════

class TestExtractGraph:
    """测试提取节点图为 GraphBuilder"""

    def test_get_graph_returns_graph_builder(self, loader: GIALoader, sample_gia_path: Path):
        """get_graph 应返回 GraphBuilder"""
        loaded = loader.load(sample_gia_path)
        graph = loaded.get_graph(0)
        assert isinstance(graph, GraphBuilder)

    def test_get_graph_has_correct_name(self, loader: GIALoader, sample_gia_path: Path):
        """提取的图应有正确的名称"""
        loaded = loader.load(sample_gia_path)
        graph = loaded.get_graph(0)
        assert graph.name == "TestGraph"

    def test_get_graph_with_catalog(self, loader: GIALoader, sample_gia_path: Path):
        """使用 catalog 提取图应能识别节点类型"""
        loaded = loader.load(sample_gia_path)
        graph = loaded.get_graph(0, catalog=loader.catalog)
        assert graph._catalog is not None

    def test_get_graph_count(self, loader: GIALoader, sample_gia_path: Path):
        """get_graph_count 应返回正确的图数量"""
        loaded = loader.load(sample_gia_path)
        assert loaded.get_graph_count() == 1

    def test_get_graph_invalid_index_raises(self, loader: GIALoader, sample_gia_path: Path):
        """无效的图索引应抛出错误"""
        loaded = loader.load(sample_gia_path)
        with pytest.raises((IndexError, ValueError)):
            loaded.get_graph(99)


# ═══════════════════════════════════════════════════════════════
# 测试 3: 节点转换
# ═══════════════════════════════════════════════════════════════

class TestNodeConversion:
    """测试 GIA node 转换为 GraphBuilder node"""

    def test_nodes_converted_correctly(self, loader: GIALoader, sample_gia_path: Path):
        """节点应被正确转换"""
        loaded = loader.load(sample_gia_path)
        graph = loaded.get_graph(0)
        assert graph.node_count() == 2

    def test_node_type_id_preserved(self, loader: GIALoader, sample_gia_path: Path):
        """节点 type_id 应被保留"""
        loaded = loader.load(sample_gia_path)
        graph = loaded.get_graph(0)
        node0 = graph.get_node(0)
        assert node0.type_id == 300001  # 监听信号

    def test_node_position_preserved(self, loader: GIALoader, sample_gia_path: Path):
        """节点坐标应被保留"""
        loaded = loader.load(sample_gia_path)
        graph = loaded.get_graph(0)
        node0 = graph.get_node(0)
        assert node0.x == 100
        assert node0.y == 200
        node1 = graph.get_node(1)
        assert node1.x == 400
        assert node1.y == 200

    def test_node_name_recognized_with_catalog(self, loader: GIALoader, sample_gia_path: Path):
        """使用 catalog 时应能识别节点名称"""
        loaded = loader.load(sample_gia_path)
        graph = loaded.get_graph(0, catalog=loader.catalog)
        node0 = graph.get_node(0)
        assert node0.name == "监听信号"


# ═══════════════════════════════════════════════════════════════
# 测试 4: 连线重建
# ═══════════════════════════════════════════════════════════════

class TestConnectionReconstruction:
    """测试连线重建"""

    def test_flow_connection_reconstructed(self, loader: GIALoader, sample_gia_path: Path):
        """流程连线应被正确重建（连接在源节点的 OUT_FLOW pin 上）"""
        loaded = loader.load(sample_gia_path)
        graph = loaded.get_graph(0, catalog=loader.catalog)
        
        # 导出 numeric 检查连线
        num = graph.to_numeric()
        # entry[0]=entity, entry[1]=NG
        entry = num['1'][1]
        nodes = entry['13']['1']['1']['3']
        
        # 连接在源节点的 OUT_FLOW pin 上，指向目标节点
        node0 = nodes[0]
        pins = node0['4']
        out_flow_pin = None
        for pin in pins:
            sig = pin.get('1', {})
            if sig.get('1') == 2:  # OUT_FLOW (flow pins 没有 '2')
                out_flow_pin = pin
                break
        
        assert out_flow_pin is not None
        assert '5' in out_flow_pin
        conn = out_flow_pin['5']
        assert conn['1'] == 2  # 目标节点 id=2 (从1开始)


# ═══════════════════════════════════════════════════════════════
# 测试 5: 参数提取
# ═══════════════════════════════════════════════════════════════

class TestParamExtraction:
    """测试参数提取"""

    def test_string_param_extracted(self, loader: GIALoader, sample_gia_path: Path):
        """字符串参数应被正确提取"""
        loaded = loader.load(sample_gia_path)
        graph = loaded.get_graph(0, catalog=loader.catalog)
        node0 = graph.get_node(0)
        
        # 监听信号的 "信号名" 参数应为 "test_signal"
        assert node0.get_param("信号名") == "test_signal"

    def test_param_preserved_in_export(self, loader: GIALoader, sample_gia_path: Path, tmp_path: Path):
        """参数应在重新导出后保留"""
        loaded = loader.load(sample_gia_path)
        graph = loaded.get_graph(0, catalog=loader.catalog)
        
        # 重新导出
        output = tmp_path / "reexport.gia"
        graph.to_gia(output)
        
        # 重新加载验证
        num = load_gia_numeric(output)
        entries = get_entries(num)
        # 找 NG entry（现在 entity 在 entries[0]）
        entry = next((e for e in entries if '13' in e), entries[0])
        nodes = entry['13']['1']['1']['3']
        node0 = nodes[0]
        pins = node0['4']
        
        # 找到信号名端口
        for pin in pins:
            sig = pin.get('1', {})
            if sig.get('2', 0) == 0 and sig.get('1') == 3:  # index=0, IN_PARAM
                var_base = pin.get('3', {})
                assert var_base.get('1') == VarType.Str
                break
        else:
            pytest.fail("未找到信号名端口")


# ═══════════════════════════════════════════════════════════════
# 测试 6: 多图支持
# ═══════════════════════════════════════════════════════════════

class TestMultiGraphSupport:
    """测试多图支持"""

    def test_multiple_ng_entries(self, tmp_path: Path, catalog: NodeCatalog):
        """应支持多个 NG entries"""
        # 创建包含两个 NG entry 的 GIA
        ng_entry1 = {
            '1': {'4': 1073741827},
            '3': make_binary_name("Graph1"),
            '5': 0,
            '13': {
                '1': {
                    '1': {
                        '3': [
                            {'1': 0, '2': 300001, '3': {}, '4': [], '5': 0, '6': 0},
                        ],
                    },
                },
            },
        }
        ng_entry2 = {
            '1': {'4': 1073741828},
            '3': make_binary_name("Graph2"),
            '5': 0,
            '13': {
                '1': {
                    '1': {
                        '3': [
                            {'1': 0, '2': 300000, '3': {}, '4': [], '5': 100, '6': 100},
                        ],
                    },
                },
            },
        }
        entity_entry = {
            '1': {'4': 1073741827},
            '3': make_binary_name("TestEntity"),
            '5': 0,
            '11': {'1': 12345},
        }
        
        msg = {
            '1': [entity_entry, ng_entry1, ng_entry2],
            '3': make_binary_name("multi.gia"),
        }
        
        gia_path = tmp_path / "multi.gia"
        save_gia_numeric(msg, gia_path)
        
        # 加载
        loader = GIALoader(catalog=catalog)
        loaded = loader.load(gia_path)
        
        assert loaded.get_graph_count() == 2
        
        # 获取第一个图
        graph1 = loaded.get_graph(0)
        assert graph1.name == "Graph1"
        
        # 获取第二个图
        graph2 = loaded.get_graph(1)
        assert graph2.name == "Graph2"


# ═══════════════════════════════════════════════════════════════
# 测试 7: 修改后导出
# ═══════════════════════════════════════════════════════════════

class TestModifyAndReexport:
    """测试加载 -> 修改 -> 重新导出"""

    def test_add_node_and_reexport(self, loader: GIALoader, sample_gia_path: Path, tmp_path: Path, catalog: NodeCatalog):
        """添加节点后重新导出"""
        loaded = loader.load(sample_gia_path)
        graph = loaded.get_graph(0, catalog=catalog)
        
        # 添加新节点
        new_node = graph.add_node("多分支")
        new_node.x = 700
        new_node.y = 200
        
        # 连接
        node1 = graph.get_node(1)
        graph.connect_flow(node1, "出", new_node, "入")
        
        # 重新导出
        output = tmp_path / "modified.gia"
        graph.to_gia(output)
        
        # 验证
        num = load_gia_numeric(output)
        entries = get_entries(num)
        # 找 NG entry
        entry = next((e for e in entries if '13' in e), entries[0])
        nodes = entry['13']['1']['1']['3']
        assert len(nodes) == 3

    def test_modify_param_and_reexport(self, loader: GIALoader, sample_gia_path: Path, tmp_path: Path, catalog: NodeCatalog):
        """修改参数后重新导出"""
        loaded = loader.load(sample_gia_path)
        graph = loaded.get_graph(0, catalog=catalog)
        
        # 修改参数
        node0 = graph.get_node(0)
        node0.set_param("信号名", "modified_signal")
        
        # 重新导出
        output = tmp_path / "modified_param.gia"
        graph.to_gia(output)
        
        # 重新加载验证
        reloaded = loader.load(output)
        regraph = reloaded.get_graph(0, catalog=catalog)
        renode = regraph.get_node(0)
        assert renode.get_param("信号名") == "modified_signal"


# ═══════════════════════════════════════════════════════════════
# 测试 8: 错误处理
# ═══════════════════════════════════════════════════════════════

class TestErrorHandling:
    """测试错误处理"""

    def test_invalid_gia_format(self, tmp_path: Path, loader: GIALoader):
        """无效的 GIA 格式应给出清晰的错误提示"""
        invalid_gia = tmp_path / "invalid.gia"
        # 写入无效数据
        invalid_gia.write_bytes(b"invalid data")
        
        with pytest.raises((ValueError, Exception)) as exc_info:
            loader.load(invalid_gia)
        
        error_msg = str(exc_info.value).lower()
        # 应该包含一些关于格式错误的提示
        assert any(word in error_msg for word in ['format', 'invalid', '格式', '无效', 'error'])

    def test_empty_entries_raises_error(self, tmp_path: Path, loader: GIALoader):
        """空的 entries 应给出错误提示"""
        empty_msg = {
            '1': [],
            '3': make_binary_name("empty.gia"),
        }
        empty_gia = tmp_path / "empty.gia"
        save_gia_numeric(empty_msg, empty_gia)
        
        # 应该能加载，但 get_graph 应该报错
        loaded = loader.load(empty_gia)
        assert loaded.get_graph_count() == 0
        
        with pytest.raises((IndexError, ValueError)):
            loaded.get_graph(0)


# ═══════════════════════════════════════════════════════════════
# 测试 9: 与 LevelExporter 集成
# ═══════════════════════════════════════════════════════════════

class TestLevelExporterIntegration:
    """测试与 LevelExporter 集成"""

    def test_loaded_graph_can_be_exported_via_exporter(
        self, loader: GIALoader, sample_gia_path: Path, tmp_path: Path, catalog: NodeCatalog
    ):
        """加载的图可以用 LevelExporter 重新导出"""
        loaded = loader.load(sample_gia_path)
        graph = loaded.get_graph(0, catalog=catalog)
        
        # 使用 LevelExporter 导出
        exporter = LevelExporter()
        output = tmp_path / "via_exporter.gia"
        result = exporter.export(graph, "goblet", output, validate=False)
        
        assert output.exists()
        assert result.ok

    def test_roundtrip_with_exporter(
        self, loader: GIALoader, sample_gia_path: Path, tmp_path: Path, catalog: NodeCatalog
    ):
        """使用 LevelExporter 进行完整往返测试"""
        # 1. 加载
        loaded = loader.load(sample_gia_path)
        graph = loaded.get_graph(0, catalog=catalog)
        
        # 2. 修改
        node0 = graph.get_node(0)
        original_signal = node0.get_param("信号名")
        node0.set_param("信号名", "roundtrip_test")
        
        # 3. 导出
        exporter = LevelExporter()
        output = tmp_path / "roundtrip.gia"
        exporter.export(graph, "goblet", output, validate=False)
        
        # 4. 重新加载
        reloaded = loader.load(output)
        regraph = reloaded.get_graph(0, catalog=catalog)  # NG entry 是第一个
        
        # 5. 验证
        renode = regraph.get_node(0)
        assert renode.get_param("信号名") == "roundtrip_test"


# ═══════════════════════════════════════════════════════════════
# 测试 10: 端到端场景
# ═══════════════════════════════════════════════════════════════

class TestEndToEnd:
    """端到端场景测试"""

    def test_load_modify_export_verify(self, loader: GIALoader, sample_gia_path: Path, tmp_path: Path, catalog: NodeCatalog):
        """完整工作流：加载 -> 修改 -> 导出 -> 验证"""
        # 1. 加载
        loaded = loader.load(sample_gia_path)
        graph = loaded.get_graph(0, catalog=catalog)
        
        original_count = graph.node_count()
        
        # 2. 修改：添加新节点
        new_node = graph.add_node("创建元件")
        new_node.set_param("元件ID", 12345)
        new_node.x = 700
        new_node.y = 300
        
        # 3. 连线
        node1 = graph.get_node(1)
        graph.connect_flow(node1, "出", new_node, "入")
        
        # 4. 导出
        output = tmp_path / "end_to_end.gia"
        graph.to_gia(output)
        
        # 5. 验证结构
        num = load_gia_numeric(output)
        validator = GIAValidator(catalog)
        report = validator.validate_numeric(num)
        assert report.ok, f"验证失败: {report.to_text()}"
        
        # 6. 验证节点数量
        entries = get_entries(num)
        # 找 NG entry
        entry = next((e for e in entries if '13' in e), entries[0])
        nodes = entry['13']['1']['1']['3']
        assert len(nodes) == original_count + 1

    def test_convenience_functions(self, sample_gia_path: Path, catalog: NodeCatalog):
        """测试便捷函数 load_gia 和 load_graph"""
        # load_gia
        loaded = load_gia(sample_gia_path, catalog=catalog)
        assert isinstance(loaded, LoadedLevel)
        assert loaded.get_graph_count() == 1
        
        # load_graph
        graph = load_graph(sample_gia_path, index=0, catalog=catalog)
        assert isinstance(graph, GraphBuilder)
        assert graph.node_count() == 2


# ═══════════════════════════════════════════════════════════════
# 测试: VarBase 解码
# ═══════════════════════════════════════════════════════════════

class TestVarBaseDecoding:
    """测试 VarBase 解码为 Python 值"""

    def test_decode_int(self, loader: GIALoader):
        """解码 Int 类型"""
        varbase = {'1': VarType.Int, '2': {'1': 42}}
        result = loader._varbase_to_value(varbase)
        assert result == 42

    def test_decode_str(self, loader: GIALoader):
        """解码 Str 类型"""
        varbase = {'1': VarType.Str, '2': {'1': make_binary_name("hello")}}
        result = loader._varbase_to_value(varbase)
        assert result == "hello"

    def test_decode_bool_true(self, loader: GIALoader):
        """解码 Bool 类型 (True)"""
        varbase = {'1': VarType.Bol, '2': {'1': 1}}
        result = loader._varbase_to_value(varbase)
        assert result is True

    def test_decode_bool_false(self, loader: GIALoader):
        """解码 Bool 类型 (False)"""
        varbase = {'1': VarType.Bol, '2': {'1': 0}}
        result = loader._varbase_to_value(varbase)
        assert result is False

    def test_decode_float(self, loader: GIALoader):
        """解码 Float 类型"""
        bits = struct.unpack('>I', struct.pack('>f', 3.14))[0]
        varbase = {'1': VarType.Flt, '2': {'1': bits}}
        result = loader._varbase_to_value(varbase)
        assert abs(result - 3.14) < 0.01

    def test_decode_unknown_type_returns_none(self, loader: GIALoader):
        """未知类型应返回 None"""
        varbase = {'1': 9999}
        result = loader._varbase_to_value(varbase)
        assert result is None


# ═══════════════════════════════════════════════════════════════
# 测试: load_graph_only 方法
# ═══════════════════════════════════════════════════════════════

class TestLoadGraphOnly:
    """测试 load_graph_only 方法"""

    def test_load_graph_only_returns_graph_builder(self, loader: GIALoader, sample_gia_path: Path):
        """load_graph_only 应直接返回 GraphBuilder"""
        graph = loader.load_graph_only(sample_gia_path, index=0)
        assert isinstance(graph, GraphBuilder)

    def test_load_graph_only_default_index(self, loader: GIALoader, sample_gia_path: Path):
        """load_graph_only 默认索引为 0"""
        graph = loader.load_graph_only(sample_gia_path)
        assert isinstance(graph, GraphBuilder)
        assert graph.node_count() == 2


# ═══════════════════════════════════════════════════════════════
# 测试: get_entity_asset_key
# ═══════════════════════════════════════════════════════════════

class TestGetEntityAssetKey:
    """测试 get_entity_asset_key 方法"""

    def test_get_entity_asset_key_from_goblet(self, tmp_path: Path, catalog: NodeCatalog):
        """从 goblet 类型的 GIA 推断 asset key"""
        # 创建模拟 goblet 的 entity entry
        entity_entry = {
            '1': {'4': 1073741827},  # goblet 的 loc_id
            '3': make_binary_name("GobletEntity"),
            '5': 0,
            '12': [1, 2, 3],  # goblet 有 related_ids
        }
        ng_entry = {
            '1': {'4': 1073741827},
            '3': make_binary_name("Graph"),
            '5': 0,
            '13': {'1': {'1': {'3': []}}},
        }
        msg = {'1': [entity_entry, ng_entry], '3': make_binary_name("test.gia")}
        gia_path = tmp_path / "goblet_test.gia"
        save_gia_numeric(msg, gia_path)
        
        loader = GIALoader(catalog=catalog)
        loaded = loader.load(gia_path)
        
        # 应该能推断出 asset_key
        asset_key = loaded.get_entity_asset_key()
        assert asset_key is not None


# ═══════════════════════════════════════════════════════════════
# 主程序入口
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
