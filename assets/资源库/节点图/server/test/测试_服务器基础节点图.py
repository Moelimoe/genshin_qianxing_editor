"""
graph_id: test_server_basic_node_graph
graph_name: 测试_服务器基础节点图
graph_type: server
description: 演示服务器节点图的基础结构和节点调用

节点图变量：
- 测试数值1: 浮点数 = 10.0
- 测试数值2: 浮点数 = 5.0
- 结果变量名: 字符串 = "测试结果"
- 是否触发事件: 布尔值 = False
"""

from __future__ import annotations

from runtime.engine.graph_prelude_server import *  # noqa: F401,F403
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
    GraphVariableConfig(
        name="结果变量名",
        variable_type="字符串",
        default_value="测试结果",
        description="存储结果的变量名",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="是否触发事件",
        variable_type="布尔值",
        default_value=False,
        description="是否触发自定义变量事件",
        is_exposed=True,
    ),
]


class 测试_服务器基础节点图:
    """演示服务器节点图的基础结构：

    1. 在【实体创建时】事件中执行
    2. 读取节点图变量
    3. 执行数学运算
    4. 写入自定义变量
    """

    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

        from app.runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    # ---------------------------- 事件：实体创建时 ----------------------------
    def on_实体创建时(self, 事件源实体, 事件源GUID):
        """实体创建时事件，执行基础节点图逻辑"""
        # 获取节点图变量
        测试数值1: "浮点数" = 获取节点图变量(self.game, 变量名="测试数值1")
        测试数值2: "浮点数" = 获取节点图变量(self.game, 变量名="测试数值2")
        结果变量名: "字符串" = 获取节点图变量(self.game, 变量名="结果变量名")
        是否触发事件: "布尔值" = 获取节点图变量(self.game, 变量名="是否触发事件")

        # 执行加法运算
        加法结果: "浮点数" = 加法运算(
            self.game,
            左值=测试数值1,
            右值=测试数值2
        )

        # 执行乘法运算
        乘法结果: "浮点数" = 乘法运算(
            self.game,
            左值=测试数值1,
            右值=测试数值2
        )

        # 设置自定义变量，存储最终结果
        设置自定义变量(
            self.game,
            目标实体=self.owner_entity,
            变量名=结果变量名,
            变量值=加法结果,
            是否触发事件=是否触发事件
        )

    # ---------------------------- 注册事件处理器 ----------------------------
    def register_handlers(self):
        self.game.register_event_handler(
            "实体创建时",
            self.on_实体创建时,
            owner=self.owner_entity,
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
