"""
graph_id: pixel_art_generator
graph_name: 像素块图像生成器
graph_type: client
description: 将图片转换为像素块的节点图
"""

# 最小化导入：直接从运行时模块导入
from runtime.engine.graph_prelude_client import *
from engine.validate.node_graph_validator import validate_node_graph

@validate_node_graph
class 像素块图像生成器:
    """节点图类：像素块图像生成器"""

    def __init__(self, game: GameRuntime, owner_entity):
        """初始化节点图
        
        Args:
            game: 游戏运行时
            owner_entity: 挂载的实体（自身实体）
        """
        self.game = game
        self.owner_entity = owner_entity

    def on_节点图开始(self):
        """事件处理器：节点图开始"""
        pass

    def register_handlers(self):
        """注册所有事件处理器"""
        self.game.register_event_handler(
            "节点图开始",
            self.on_节点图开始,
            owner=self.owner_entity
        )