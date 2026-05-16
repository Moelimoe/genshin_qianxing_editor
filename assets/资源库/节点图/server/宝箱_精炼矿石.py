"""
graph_id: treasure_chest_refined_ore
graph_name: 宝箱_精炼矿石
graph_type: server
description: 宝箱打开后显示精炼矿石并允许拾取的节点图

节点图变量：
- 宝箱打开半径: 浮点数 = 3.0 [对外暴露]
- 精炼矿石元件ID: 元件ID = 0 [对外暴露]
- 矿石数量: 整数 = 3 [对外暴露]
- 拾取距离: 浮点数 = 2.0 [对外暴露]
- 是否已打开: 布尔值 = False
- 矿石实体列表: 实体列表 = []
"""

from __future__ import annotations

from runtime.engine.graph_prelude_server import *
from engine.graph.models.package_model import GraphVariableConfig


GRAPH_VARIABLES: list[GraphVariableConfig] = [
    GraphVariableConfig(
        name="宝箱打开半径",
        variable_type="浮点数",
        default_value=3.0,
        description="对外暴露：玩家与宝箱的距离小于此值时可以打开宝箱",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="精炼矿石元件ID",
        variable_type="元件ID",
        default_value=0,
        description="对外暴露：精炼矿石的元件ID",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="矿石数量",
        variable_type="整数",
        default_value=3,
        description="对外暴露：宝箱打开后生成的矿石数量",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="拾取距离",
        variable_type="浮点数",
        default_value=2.0,
        description="对外暴露：玩家与矿石的距离小于此值时可以拾取",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="是否已打开",
        variable_type="布尔值",
        default_value=False,
        description="记录宝箱是否已被打开",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="矿石实体列表",
        variable_type="实体列表",
        default_value=[],
        description="存储生成的矿石实体",
        is_exposed=False,
    )
]


class 宝箱_精炼矿石:
    """宝箱打开后显示精炼矿石并允许拾取的节点图
    
    功能：
    1. 监听玩家进入碰撞触发器事件
    2. 检查玩家与宝箱的距离
    3. 如果宝箱未打开且玩家距离足够，打开宝箱
    4. 在宝箱位置附近生成指定数量的精炼矿石
    5. 监听矿石的碰撞触发器事件
    6. 检查玩家与矿石的距离
    7. 如果玩家距离足够，拾取矿石
    8. 移除被拾取的矿石实体
    """
    
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
            变量名="是否已打开",
            变量值=False,
            是否触发事件=False,
        )
        设置节点图变量(
            self.game,
            变量名="矿石实体列表",
            变量值=[],
            是否触发事件=False,
        )

    # ---------------------------- 事件：进入碰撞触发器时 ----------------------------
    def on_进入碰撞触发器时(self, 进入者实体, 进入者实体GUID, 触发器实体, 触发器实体GUID, 触发器序号):
        """玩家进入碰撞触发器时检查是否可以打开宝箱或拾取矿石"""
        # 获取当前实体（可能是宝箱或矿石）
        当前实体: "实体" = 获取自身实体(self.game)
        当前实体GUID: "GUID" = 以实体查询GUID(self.game, 目标实体=当前实体)
        触发器GUID: "GUID" = 以实体查询GUID(self.game, 目标实体=触发器实体)

        # 检查是否是宝箱的触发器
        if 是否相等(self.game, 输入1=当前实体GUID, 输入2=触发器GUID):
            # 处理宝箱打开
            self._处理宝箱打开(进入者实体)
        else:
            # 检查是否是矿石的触发器
            self._处理矿石拾取(进入者实体, 触发器实体)

    def _处理宝箱打开(self, 进入者实体):
        """处理宝箱打开逻辑"""
        # 检查宝箱是否已打开
        是否已打开: "布尔值" = 获取节点图变量(
            self.game,
            变量名="是否已打开",
        )
        if 是否已打开:
            return

        # 获取宝箱位置
        宝箱位置: "三维向量"
        宝箱旋转: "三维向量"
        宝箱位置, 宝箱旋转 = 获取实体位置与旋转(self.game, 目标实体=获取自身实体(self.game))
        玩家位置: "三维向量"
        玩家旋转: "三维向量"
        玩家位置, 玩家旋转 = 获取实体位置与旋转(self.game, 目标实体=进入者实体)

        # 计算玩家与宝箱的距离
        距离向量: "三维向量" = 三维向量减法(self.game, 三维向量1=玩家位置, 三维向量2=宝箱位置)
        距离: "浮点数" = 三维向量模运算(self.game, 三维向量=距离向量)
        宝箱打开半径: "浮点数" = 获取节点图变量(
            self.game,
            变量名="宝箱打开半径",
        )

        # 检查距离是否足够
        if 数值大于(self.game, 输入1=距离, 输入2=宝箱打开半径):
            return

        # 标记宝箱已打开
        设置节点图变量(
            self.game,
            变量名="是否已打开",
            变量值=True,
            是否触发事件=False,
        )

        # 生成精炼矿石
        self._生成精炼矿石(宝箱位置)

    def _生成精炼矿石(self, 宝箱位置):
        """在宝箱位置附近生成精炼矿石"""
        # 获取配置参数
        精炼矿石元件ID: "元件ID" = 获取节点图变量(
            self.game,
            变量名="精炼矿石元件ID",
        )
        矿石数量: "整数" = 获取节点图变量(
            self.game,
            变量名="矿石数量",
        )

        # 生成多个矿石
        生成的矿石列表: "实体列表" = []
        for i in range(矿石数量):
            # 计算矿石位置（在宝箱周围随机分布）
            随机偏移X: "浮点数" = 获取随机浮点数(self.game, 最小值=-2.0, 最大值=2.0)
            随机偏移Y: "浮点数" = 获取随机浮点数(self.game, 最小值=0.0, 最大值=1.0)
            随机偏移Z: "浮点数" = 获取随机浮点数(self.game, 最小值=-2.0, 最大值=2.0)

            偏移向量: "三维向量" = 创建三维向量(self.game, X=随机偏移X, Y=随机偏移Y, Z=随机偏移Z)
            矿石位置: "三维向量" = 三维向量加法(self.game, 三维向量1=宝箱位置, 三维向量2=偏移向量)

            # 创建矿石实体
            矿石实体: "实体" = 创建元件(
                self.game,
                元件ID=精炼矿石元件ID,
                位置=矿石位置,
                旋转=创建三维向量(self.game, X=0.0, Y=0.0, Z=0.0),
                拥有者实体=None,
                是否覆写等级=False,
                等级=0,
                单位标签索引列表=[],
            )

            # 将矿石实体添加到列表 - 使用对列表插入值函数
            生成的矿石列表 = 对列表插入值(
                self.game,
                列表=生成的矿石列表,
                插入序号=i,
                插入值=矿石实体
            )

        # 更新节点图变量
        设置节点图变量(
            self.game,
            变量名="矿石实体列表",
            变量值=生成的矿石列表,
            是否触发事件=False,
        )

    def _处理矿石拾取(self, 进入者实体, 矿石实体):
        """处理矿石拾取逻辑"""
        # 获取玩家和矿石的位置
        玩家位置: "三维向量"
        玩家旋转: "三维向量"
        玩家位置, 玩家旋转 = 获取实体位置与旋转(self.game, 目标实体=进入者实体)
        矿石位置: "三维向量"
        矿石旋转: "三维向量"
        矿石位置, 矿石旋转 = 获取实体位置与旋转(self.game, 目标实体=矿石实体)

        # 计算距离
        距离向量: "三维向量" = 三维向量减法(self.game, 三维向量1=玩家位置, 三维向量2=矿石位置)
        距离: "浮点数" = 三维向量模运算(self.game, 三维向量=距离向量)
        拾取距离: "浮点数" = 获取节点图变量(
            self.game,
            变量名="拾取距离",
        )

        # 检查距离是否足够
        if 数值大于(self.game, 输入1=距离, 输入2=拾取距离):
            return

        # 获取矿石实体列表
        矿石实体列表: "实体列表" = 获取节点图变量(
            self.game,
            变量名="矿石实体列表",
        )

        # 查找矿石在列表中的位置
        矿石索引: "整数" = 查找列表并返回值的序号(
            self.game,
            列表=矿石实体列表,
            查找值=矿石实体
        )

        # 检查矿石是否在列表中
        if 数值小于(self.game, 输入1=矿石索引, 输入2=0):
            return

        # 拾取矿石（这里可以添加具体的拾取逻辑，比如添加到背包）
        打印字符串(self.game, 输入="玩家拾取了精炼矿石")

        # 从列表中移除矿石
        新的矿石列表: "实体列表" = 对列表移除值(
            self.game,
            列表=矿石实体列表,
            移除序号=矿石索引
        )

        # 更新节点图变量
        设置节点图变量(
            self.game,
            变量名="矿石实体列表",
            变量值=新的矿石列表,
            是否触发事件=False,
        )

        # 移除矿石实体
        移除实体(self.game, 实体=矿石实体)

    # ---------------------------- 事件：离开碰撞触发器时 ----------------------------
    def on_离开碰撞触发器时(self, 离开者实体, 离开者实体GUID, 触发器实体, 触发器实体GUID, 触发器序号):
        """离开碰撞触发器时不做特殊处理"""
        pass