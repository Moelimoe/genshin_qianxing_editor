"""
graph_id: test_client_basic_flow
graph_name: 测试_客户端基础流程
graph_type: client
description: 演示客户端节点图的基础流程和数学运算

节点图变量：
- 测试数值1: 浮点数 = 10.0
- 测试数值2: 浮点数 = 5.0
"""

from __future__ import annotations

from runtime.engine.graph_prelude_client import *  # noqa: F401,F403
from engine.graph.models.package_model import GraphVariableConfig


GRAPH_VARIABLES: list[GraphVariableConfig] = [
    GraphVariableConfig(
        name="测试数值1",
        variable_type="浮点数",
        default_value=10.0,
        description="第一个测试数值",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="测试数值2",
        variable_type="浮点数",
        default_value=5.0,
        description="第二个测试数值",
        is_exposed=True,
    ),
]


class 测试_客户端基础流程:
    """演示客户端节点图的基础流程：

    1. 从节点图开始事件触发
    2. 执行基本的数学运算
    3. 演示流程控制
    """

    def __init__(self, game):
        self.game = game

        from app.runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    # ---------------------------- 事件：节点图开始 ----------------------------
    def on_节点图开始(self):
        """节点图开始事件，执行基础流程演示"""
        # 这里使用节点图变量直接作为常量，因为客户端节点图可能无法直接使用获取节点图变量节点
        测试数值1 = 10.0
        测试数值2 = 5.0

        # 执行加法运算
        加法结果 = 加法运算(
            self.game,
            左值=测试数值1,
            右值=测试数值2
        )

        # 执行乘法运算
        乘法结果 = 乘法运算(
            self.game,
            左值=测试数值1,
            右值=测试数值2
        )

        # 执行减法运算
        减法结果 = 减法运算(
            self.game,
            左值=测试数值1,
            右值=测试数值2
        )

        # 执行除法运算
        除法结果 = 除法运算(
            self.game,
            左值=测试数值1,
            右值=测试数值2
        )

        # 这里可以添加更多的节点调用和逻辑

    # ---------------------------- 注册事件处理器 ----------------------------
    def register_handlers(self):
        self.game.register_event_handler(
            "节点图开始",
            self.on_节点图开始,
        )


if __name__ == "__main__":
    from app.runtime.engine.node_graph_validator import validate_file
    import sys
    import pathlib

    自身文件路径 = pathlib.Path(__file__).resolve()
    是否通过, 错误列表, 警告列表 = validate_file(自身文件路径)
    print("=" * 80)
    print("节点图自检: " + 自身文件路径.name)
    print("文件: " + str(自身文件路径))
    if 是否通过:
        print("结果: 通过")
    else:
        print("结果: 未通过（错误: " + str(len(错误列表)) + ", 警告: " + str(len(警告列表)) + "）")
        if 错误列表:
            print("\n错误明细:")
            for 序号, 错误文本 in enumerate(错误列表, start=1):
                print("  [" + str(序号) + "] " + 错误文本)
        if 警告列表:
            print("\n警告明细:")
            for 序号, 警告文本 in enumerate(警告列表, start=1):
                print("  [" + str(序号) + "] " + 警告文本)
    print("=" * 80)
    if not 是否通过:
        sys.exit(1)
