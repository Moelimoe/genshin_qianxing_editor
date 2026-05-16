"""
graph_id: test_simple_graph
graph_name: 测试_简单节点图
graph_type: server
description: 一个简单的测试节点图

节点图变量：
- 测试变量: 整数 = 0
"""

from __future__ import annotations

from runtime.engine.graph_prelude_server import *
from engine.graph.models.package_model import GraphVariableConfig


GRAPH_VARIABLES: list[GraphVariableConfig] = [
    GraphVariableConfig(
        name="测试变量",
        variable_type="整数",
        default_value=0,
        description="一个测试变量",
        is_exposed=False,
    ),
]


class 测试_简单节点图:
    """一个简单的测试节点图"""
    
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

        from app.runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    # ---------------------------- 事件：实体创建时 ----------------------------
    def on_实体创建时(self, 事件源实体, 事件源GUID):
        """实体创建时初始化变量"""
        设置节点图变量(
            self.game,
            变量名="测试变量",
            变量值=0,
            是否触发事件=False,
        )
        
        打印字符串(self.game, 输入="测试节点图初始化成功")