"""
graph_id: test_basic_flow_control
graph_name: 测试_基础流程控制
graph_type: client
description: 演示基础的流程控制和数学运算节点

节点图变量：
- 测试数值1: 浮点数 = 10.0
- 测试数值2: 浮点数 = 5.0
- 比较阈值: 浮点数 = 100.0
- 结果变量名: 字符串 = "测试结果"
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
    GraphVariableConfig(
        name="比较阈值",
        variable_type="浮点数",
        default_value=100.0,
        description="比较结果的阈值",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="结果变量名",
        variable_type="字符串",
        default_value="测试结果",
        description="存储结果的变量名",
        is_exposed=True,
    ),
]


class 测试_基础流程控制:
    """演示基础的流程控制和数学运算：

    1. 在【节点图开始】事件中执行流程
    2. 执行加法运算和乘法运算
    3. 根据结果进行条件分支
    4. 设置自定义变量存储结果
    """

    def __init__(self, game):
        self.game = game

        from app.runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    # ---------------------------- 事件：节点图开始 ----------------------------
    def on_节点图开始(self):
        """节点图开始事件，执行基础流程控制演示"""
        # 获取节点图变量
        数值1: "浮点数" = 获取节点图变量(self.game, 变量名="测试数值1")
        数值2: "浮点数" = 获取节点图变量(self.game, 变量名="测试数值2")
        阈值: "浮点数" = 获取节点图变量(self.game, 变量名="比较阈值")
        结果变量名: "字符串" = 获取节点图变量(self.game, 变量名="结果变量名")

        # 执行加法运算
        加法结果: "浮点数" = 加法运算(
            self.game,
            左值=数值1,
            右值=数值2
        )

        # 执行乘法运算
        乘法结果: "浮点数" = 乘法运算(
            self.game,
            左值=数值1,
            右值=数值2
        )

        # 条件分支：比较乘法结果和阈值
        if 乘法结果 > 阈值:
            # 如果结果大于阈值，设置结果为乘法结果
            最终结果: "浮点数" = 乘法结果
        else:
            # 否则设置结果为加法结果
            最终结果: "浮点数" = 加法结果

        # 设置自定义变量，存储最终结果
        # 这里需要替换为实际的设置自定义变量节点
        # 设置自定义变量(
        #     self.game,
        #     目标实体=None,
        #     变量名=结果变量名,
        #     变量值=最终结果,
        #     是否触发事件=False
        # )

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
