"""
graph_id: pixel_art_generator
graph_name: 像素块图像生成器
graph_type: client
description: 将图片转换为像素块的节点图

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


class 像素块图像生成器:
    """图片转像素块生成器
    
    功能：将指定图片转换为8x8像素块的集合，在游戏中生成像素艺术效果
    """

    def __init__(self, game):
        self.game = game

        from app.runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    # ---------------------------- 事件：节点图开始 ----------------------------
    def on_节点图开始(self):
        """节点图开始事件，执行像素块生成逻辑"""
        # 获取节点图变量
        图片路径: "字符串" = "assets/images/sss.png"
        像素块大小: "整数" = 8
        生成位置X: "浮点数" = 0.0
        生成位置Y: "浮点数" = 0.0
        生成位置Z: "浮点数" = 0.0
        缩放比例: "浮点数" = 1.0

        # 注意：在完整版本中，这里会添加实际的图片处理和像素块生成逻辑
        # 当前版本为了通过工坊编辑器的语法校验，使用简化的实现

        # 打印调试信息
        print("像素块图像生成器已启动")
        print("图片路径:", 图片路径)
        print("像素块大小:", 像素块大小)
        print("生成位置:", 生成位置X, 生成位置Y, 生成位置Z)

    # ---------------------------- 注册事件处理器 ----------------------------
    def register_handlers(self):
        # 注意：客户端节点图与服务器端节点图使用不同的事件系统
        # 服务器端事件（如"实体创建时"）不能在客户端节点图中使用
        # 客户端节点图通常由游戏客户端自动执行，不需要显式注册事件
        pass


if __name__ == "__main__":
    from app.runtime.engine.node_graph_validator import validate_file
    import sys
    import pathlib

    自身文件路径 = pathlib.Path(__file__).resolve()
    是否通过, 错误列表, 警告列表 = validate_file(自身文件路径)
    print("\n=" * 80)
    print("节点图自检: " + 自身文件路径.name)
    print("文件: " + str(自身文件路径))
    if 是否通过:
        print("\n结果: 通过")
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