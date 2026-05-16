"""
graph_id: treasure_chest_open_tab
graph_name: TreasureChestOpenTab
graph_type: server
description: Treasure chest open tab node graph for server-side control of chest opening functionality

节点图变量：
- is_openable: 布尔值 = False [对外暴露]
- is_unlocked: 布尔值 = False [对外暴露]
- player_has_key: 布尔值 = False [对外暴露]
- is_opened: 布尔值 = False [对外暴露]
- player_entity: 实体 = None [对外暴露]
- open_radius: 浮点数 = 3.0 [对外暴露]
"""

from runtime.engine.graph_prelude_server import *
from engine.graph.models.package_model import GraphVariableConfig


GRAPH_VARIABLES: list[GraphVariableConfig] = [
    GraphVariableConfig(
        name="is_openable",
        variable_type="布尔值",
        default_value=False,
        description="对外暴露：判定宝箱是否可以打开",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="is_unlocked",
        variable_type="布尔值",
        default_value=False,
        description="对外暴露：宝箱是否已解锁",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="player_has_key",
        variable_type="布尔值",
        default_value=False,
        description="对外暴露：玩家是否拥有打开宝箱的钥匙",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="is_opened",
        variable_type="布尔值",
        default_value=False,
        description="对外暴露：宝箱是否已被打开",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="player_entity",
        variable_type="实体",
        default_value=None,
        description="对外暴露：当前交互的玩家实体",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="open_radius",
        variable_type="浮点数",
        default_value=3.0,
        description="对外暴露：玩家可以打开宝箱的最大距离",
        is_exposed=True,
    ),
]


class TreasureChestOpenTab:
    """Treasure chest open tab node graph：

    Functions:
    1. Determine if the chest can be opened
    2. Check distance between player and chest
    3. Handle player's request to open chest
    4. Send chest opened signal broadcast
    """

    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

        from app.runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    # ---------------------------- 事件：进入碰撞触发器时 ----------------------------
    def on_进入碰撞触发器时(self, entering_entity, entering_entity_guid, trigger_entity, trigger_entity_guid, trigger_index):
        """玩家进入碰撞触发器时检查是否可以打开宝箱"""
        # Set current player entity
        设置节点图变量(
            self.game,
            变量名="player_entity",
            变量值=entering_entity,
            是否触发事件=False,
        )
        
        # Execute check
        self._check_openable()

    # ---------------------------- 事件：离开碰撞触发器时 ----------------------------
    def on_离开碰撞触发器时(self, leaving_entity, leaving_entity_guid, trigger_entity, trigger_entity_guid, trigger_index):
        """玩家离开碰撞触发器时重置玩家实体"""
        # Reset player entity
        设置节点图变量(
            self.game,
            变量名="player_entity",
            变量值=None,
            是否触发事件=False,
        )
        
        # Reset openable status
        设置节点图变量(
            self.game,
            变量名="is_openable",
            变量值=False,
            是否触发事件=False,
        )

    def _check_openable(self):
        """Check if the chest can be opened
        
        Conditions:
        1. Chest is unlocked OR player has key
        2. Chest is not yet opened
        3. Player is within open radius
        
        Returns:
            bool: Whether the chest can be opened
        """
        # Get configured variable values
        is_unlocked: "布尔值" = 获取节点图变量(
            self.game,
            变量名="is_unlocked",
        )
        
        player_has_key: "布尔值" = 获取节点图变量(
            self.game,
            变量名="player_has_key",
        )
        
        is_opened: "布尔值" = 获取节点图变量(
            self.game,
            变量名="is_opened",
        )
        
        player_entity: "实体" = 获取节点图变量(
            self.game,
            变量名="player_entity",
        )
        
        open_radius: "浮点数" = 获取节点图变量(
            self.game,
            变量名="open_radius",
        )
        
        # Check if player exists
        if player_entity is None:
            is_openable = False
        else:
            # Check distance condition
            chest_position: "三维向量"
            chest_rotation: "三维向量"
            chest_position, chest_rotation = 获取实体位置与旋转(self.game, 目标实体=获取自身实体(self.game))
            
            player_position: "三维向量"
            player_rotation: "三维向量"
            player_position, player_rotation = 获取实体位置与旋转(self.game, 目标实体=player_entity)
            
            distance_vector: "三维向量" = 三维向量减法(self.game, 三维向量1=player_position, 三维向量2=chest_position)
            distance: "浮点数" = 三维向量模运算(self.game, 三维向量=distance_vector)
            
            is_distance_enough: "布尔值" = 数值小于等于(self.game, 输入1=distance, 输入2=open_radius)
            
            # Comprehensive check
            is_openable: "布尔值" = 逻辑与(
                self.game,
                输入1=逻辑与(
                    self.game,
                    输入1=逻辑或(self.game, 输入1=is_unlocked, 输入2=player_has_key),
                    输入2=逻辑非(self.game, 输入=is_opened)
                ),
                输入2=is_distance_enough
            )
        
        # Update is_openable variable
        设置节点图变量(
            self.game,
            变量名="is_openable",
            变量值=is_openable,
            是否触发事件=True,
        )
        
        return is_openable

    def open_chest(self):
        """Logic to open the chest
        
        Includes:
        1. Set chest opened status
        2. Send chest opened signal broadcast
        3. Execute other open chest logic
        """
        # Check if chest is openable
        is_openable: "布尔值" = self._check_openable()
        
        if is_openable:
            # Set chest as opened
            设置节点图变量(
                self.game,
                变量名="is_opened",
                变量值=True,
                是否触发事件=True,
            )
            
            # Broadcast chest opened signal
            广播信号(
                self.game,
                信号名称="宝箱已打开",
                信号参数={"宝箱实体": 获取自身实体(self.game), "玩家实体": 获取节点图变量(self.game, 变量名="player_entity")},
            )
            
            # Reset openable status
            设置节点图变量(
                self.game,
                变量名="is_openable",
                变量值=False,
                是否触发事件=True,
            )
            
            # Add any additional open chest logic here, like spawning items
            打印字符串(self.game, 输入="Chest opened successfully")

    def register_handlers(self):
        """Register event handlers"""
        self.game.register_event_handler("进入碰撞触发器时", self.on_进入碰撞触发器时, owner=self.owner_entity)
        self.game.register_event_handler("离开碰撞触发器时", self.on_离开碰撞触发器时, owner=self.owner_entity)
