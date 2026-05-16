"""
graph_id: activation_plate
graph_name: ActivationPlate
graph_type: server
description: Activation plate node graph for server-side control of plate activation functionality

节点图变量：
- is_activated: 布尔值 = False [对外暴露]
- target_entity_guid: 字符串 = "" [对外暴露]
- is_mover_active: 布尔值 = False [对外暴露]
- activation_radius: 浮点数 = 3.0 [对外暴露]
- activation_duration: 浮点数 = 10.0 [对外暴露]
- player_entity: 实体 = None [对外暴露]
"""

from runtime.engine.graph_prelude_server import *
from engine.graph.models.package_model import GraphVariableConfig


GRAPH_VARIABLES: list[GraphVariableConfig] = [
    GraphVariableConfig(
        name="is_activated",
        variable_type="布尔值",
        default_value=False,
        description="对外暴露：启动石板是否已激活",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="target_entity_guid",
        variable_type="字符串",
        default_value="",
        description="对外暴露：目标实体的GUID",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="is_mover_active",
        variable_type="布尔值",
        default_value=False,
        description="对外暴露：基础运动器是否激活",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="activation_radius",
        variable_type="浮点数",
        default_value=3.0,
        description="对外暴露：玩家可以激活石板的最大距离",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="activation_duration",
        variable_type="浮点数",
        default_value=10.0,
        description="对外暴露：激活持续时间（秒）",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="player_entity",
        variable_type="实体",
        default_value=None,
        description="对外暴露：当前交互的玩家实体",
        is_exposed=True,
    ),
]


class ActivationPlate:
    """Activation plate node graph：

    Functions:
    1. Activate/deactivate plate tab
    2. Query entity by GUID
    3. Activate basic mover
    4. Handle player activation
    """

    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

        from app.runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    # ---------------------------- 事件：进入碰撞触发器时 ----------------------------
    def on_进入碰撞触发器时(self, entering_entity, entering_entity_guid, trigger_entity, trigger_entity_guid, trigger_index):
        """玩家进入碰撞触发器时检查是否可以激活石板"""
        # Set current player entity
        设置节点图变量(
            self.game,
            变量名="player_entity",
            变量值=entering_entity,
            是否触发事件=False,
        )
        
        # Execute activation check
        self._check_activation()

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
        
        # Reset activation status
        设置节点图变量(
            self.game,
            变量名="is_activated",
            变量值=False,
            是否触发事件=False,
        )

    def _check_activation(self):
        """Check if the plate can be activated
        
        Conditions:
        1. Player is within activation radius
        2. Target entity GUID is provided
        3. Plate is not yet activated
        
        Returns:
            bool: Whether the plate can be activated
        """
        # Get configured variable values
        activation_radius: "浮点数" = 获取节点图变量(
            self.game,
            变量名="activation_radius",
        )
        
        target_entity_guid: "字符串" = 获取节点图变量(
            self.game,
            变量名="target_entity_guid",
        )
        
        is_activated: "布尔值" = 获取节点图变量(
            self.game,
            变量名="is_activated",
        )
        
        player_entity: "实体" = 获取节点图变量(
            self.game,
            变量名="player_entity",
        )
        
        # Check if player exists and target GUID is provided
        if player_entity is None or not target_entity_guid:
            return False
        
        # Check distance condition
        plate_position: "三维向量"
        plate_rotation: "三维向量"
        plate_position, plate_rotation = 获取实体位置与旋转(self.game, 目标实体=获取自身实体(self.game))
        
        player_position: "三维向量"
        player_rotation: "三维向量"
        player_position, player_rotation = 获取实体位置与旋转(self.game, 目标实体=player_entity)
        
        distance_vector: "三维向量" = 三维向量减法(self.game, 三维向量1=player_position, 三维向量2=plate_position)
        distance: "浮点数" = 三维向量模运算(self.game, 三维向量=distance_vector)
        
        is_distance_enough: "布尔值" = 数值小于等于(self.game, 输入1=distance, 输入2=activation_radius)
        
        # Comprehensive check
        can_activate: "布尔值" = 逻辑与(
            self.game,
            输入1=is_distance_enough,
            输入2=逻辑非(self.game, 输入=is_activated)
        )
        
        if can_activate:
            self.activate_plate()
        
        return can_activate

    def activate_plate(self):
        """Logic to activate the plate
        
        Includes:
        1. Set plate activated status
        2. Query target entity by GUID
        3. Activate basic mover
        4. Activate plate tab
        5. Schedule deactivation
        """
        # Set plate as activated
        设置节点图变量(
            self.game,
            变量名="is_activated",
            变量值=True,
            是否触发事件=True,
        )
        
        # Get target entity GUID
        target_entity_guid: "字符串" = 获取节点图变量(
            self.game,
            变量名="target_entity_guid",
        )
        
        # Query entity by GUID
        target_entity = self.game.get_entity_by_guid(target_entity_guid)
        
        if target_entity:
            # Activate basic mover
            self.activate_basic_mover(target_entity)
            
            # Activate plate tab
            self.activate_tab()
            
            # Schedule deactivation
            activation_duration: "浮点数" = 获取节点图变量(
                self.game,
                变量名="activation_duration",
            )
            
            self.game.schedule_task(
                activation_duration,
                self.deactivate_plate,
                owner=self.owner_entity
            )
            
            打印字符串(self.game, 输入="Activation plate activated successfully")
        else:
            打印字符串(self.game, 输入=f"Failed to find entity with GUID: {target_entity_guid}")

    def deactivate_plate(self):
        """Logic to deactivate the plate
        
        Includes:
        1. Reset plate activated status
        2. Deactivate basic mover
        3. Close plate tab
        """
        # Reset plate activated status
        设置节点图变量(
            self.game,
            变量名="is_activated",
            变量值=False,
            是否触发事件=True,
        )
        
        # Reset mover active status
        设置节点图变量(
            self.game,
            变量名="is_mover_active",
            变量值=False,
            是否触发事件=True,
        )
        
        # Get target entity GUID
        target_entity_guid: "字符串" = 获取节点图变量(
            self.game,
            变量名="target_entity_guid",
        )
        
        # Query entity by GUID
        target_entity = self.game.get_entity_by_guid(target_entity_guid)
        
        if target_entity:
            # Deactivate basic mover
            self.deactivate_basic_mover(target_entity)
            
            # Close plate tab
            self.close_tab()
            
            打印字符串(self.game, 输入="Activation plate deactivated")

    def activate_basic_mover(self, target_entity):
        """Activate basic mover component on target entity"""
        try:
            # Get basic mover component
            mover_component = target_entity.get_component("基础运动器")
            
            if mover_component:
                # Activate mover
                mover_component.activate()
                
                # Update mover active status
                设置节点图变量(
                    self.game,
                    变量名="is_mover_active",
                    变量值=True,
                    是否触发事件=True,
                )
                
                打印字符串(self.game, 输入="Basic mover activated")
            else:
                打印字符串(self.game, 输入="Target entity does not have a basic mover component")
        except Exception as e:
            打印字符串(self.game, 输入=f"Error activating basic mover: {str(e)}")

    def deactivate_basic_mover(self, target_entity):
        """Deactivate basic mover component on target entity"""
        try:
            # Get basic mover component
            mover_component = target_entity.get_component("基础运动器")
            
            if mover_component:
                # Deactivate mover
                mover_component.deactivate()
                
                # Update mover active status
                设置节点图变量(
                    self.game,
                    变量名="is_mover_active",
                    变量值=False,
                    是否触发事件=True,
                )
                
                打印字符串(self.game, 输入="Basic mover deactivated")
        except Exception as e:
            打印字符串(self.game, 输入=f"Error deactivating basic mover: {str(e)}")

    def activate_tab(self):
        """Activate plate tab"""
        try:
            # Get plate tab component
            tab_component = self.owner_entity.get_component("选项卡")
            
            if tab_component:
                # Activate tab
                tab_component.activate()
                打印字符串(self.game, 输入="Plate tab activated")
            else:
                打印字符串(self.game, 输入="Plate does not have a tab component")
        except Exception as e:
            打印字符串(self.game, 输入=f"Error activating tab: {str(e)}")

    def close_tab(self):
        """Close plate tab"""
        try:
            # Get plate tab component
            tab_component = self.owner_entity.get_component("选项卡")
            
            if tab_component:
                # Close tab
                tab_component.deactivate()
                打印字符串(self.game, 输入="Plate tab closed")
        except Exception as e:
            打印字符串(self.game, 输入=f"Error closing tab: {str(e)}")

    def register_handlers(self):
        """Register event handlers"""
        self.game.register_event_handler("进入碰撞触发器时", self.on_进入碰撞触发器时, owner=self.owner_entity)
        self.game.register_event_handler("离开碰撞触发器时", self.on_离开碰撞触发器时, owner=self.owner_entity)