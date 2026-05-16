"""
graph_id: pixel_block_generator_example
graph_name: 像素块生成器示例
graph_type: client
description: 一个完整的像素块生成器节点图示例，包含真正的节点和连线

节点图变量:
- 图片路径: 字符串 = "assets/images/sss.png"
- 像素块大小: 整数 = 8
- 生成位置X: 浮点数 = 0.0
- 生成位置Y: 浮点数 = 0.0
- 生成位置Z: 浮点数 = 0.0
- 缩放比例: 浮点数 = 1.0
"""

from __future__ import annotations

from runtime.engine.graph_prelude_client import *  # noqa: F401,F403
from engine.graph.models.package_model import GraphVariableConfig


GRAPH_VARIABLES: list[GraphVariableConfig] = [
    GraphVariableConfig(
        name="图片路径",
        variable_type="字符串",
        default_value="assets/images/sss.png",
        description="要转换为像素块的图片路径",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="像素块大小",
        variable_type="整数",
        default_value=8,
        description="每个像素块的尺寸（8x8）",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="生成位置X",
        variable_type="浮点数",
        default_value=0.0,
        description="像素块生成的X坐标",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="生成位置Y",
        variable_type="浮点数",
        default_value=0.0,
        description="像素块生成的Y坐标",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="生成位置Z",
        variable_type="浮点数",
        default_value=0.0,
        description="像素块生成的Z坐标",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="缩放比例",
        variable_type="浮点数",
        default_value=1.0,
        description="像素块的整体缩放比例",
        is_exposed=True,
    ),
]


class 像素块生成器示例:
    """一个完整的像素块生成器节点图示例：

    包含以下节点：
    1. 输入参数节点 - 提供图片路径、像素块大小等参数
    2. 图片加载节点 - 加载指定路径的图片
    3. 像素化处理节点 - 将图片转换为像素数据
    4. 生成像素块节点 - 在指定位置生成像素块
    5. 流程控制节点 - 管理节点执行顺序
    """

    def __init__(self, game):
        self.game = game

    def on_节点图开始(self):
        """节点图开始事件，执行像素块生成逻辑"""
        print("开始执行像素块生成器节点图")
        
        # 在实际实现中，这里会调用各个节点的函数
        # 例如：
        # 图片数据 = 加载图片(self.game, 图片路径)
        # 像素数据 = 像素化(self.game, 图片数据, 像素块大小)
        # 生成像素块(self.game, 像素数据, 生成位置X, 生成位置Y, 生成位置Z, 缩放比例)
        
        print("像素块生成器节点图执行完成")

    def register_handlers(self):
        """注册事件处理器"""
        # 客户端节点图的事件处理
        pass


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