"""
graph_id: server_template_add_one_plus_one_write_custom_variable
graph_name: 模板示例_计算1加1_写入自定义变量
graph_type: server
folder_path: 实体节点图/模板示例
description: 示例节点图（最小可复制模板）：在【实体创建时】计算 1+1 得到整数结果，并把结果写入挂载实体的指定自定义变量（变量名/是否触发事件由节点图变量控制）。
"""

from __future__ import annotations

# 让该文件可在任意工作目录下直接运行：推导 workspace_root 并注入 project_root/assets 到 sys.path（不要注入 app 目录）
import sys
from pathlib import Path

if getattr(sys, 'frozen', False):
    PROJECT_ROOT = Path(sys.executable).resolve().parent
else:
    PROJECT_ROOT = Path(__file__).resolve()
    for _ in range(12):
        _candidate = PROJECT_ROOT if PROJECT_ROOT.is_dir() else PROJECT_ROOT.parent
        # 便携版/资源库形态（assets/资源库 同级）
        if (_candidate / 'assets' / '资源库').is_dir():
            PROJECT_ROOT = _candidate
            break
        # 源码仓库形态（engine/ + app/）
        if (_candidate / 'engine').is_dir() and (_candidate / 'app').is_dir():
            PROJECT_ROOT = _candidate
            break
        PROJECT_ROOT = _candidate.parent
ASSETS_ROOT = PROJECT_ROOT / 'assets'
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(ASSETS_ROOT) not in sys.path:
    sys.path.insert(1, str(ASSETS_ROOT))

if __name__ == '__main__':
    from app.runtime.engine.node_graph_validator import validate_file_cli
    raise SystemExit(validate_file_cli(__file__))

from app.runtime.engine.graph_prelude_server import *  # noqa: F401,F403
from app.runtime.engine.graph_prelude_server import GameRuntime
from engine.validate.node_graph_validator import validate_node_graph

GRAPH_VARIABLES: list[GraphVariableConfig] = [
    GraphVariableConfig(
        name="输出自定义变量名",
        variable_type="字符串",
        default_value="示例_一加一结果",
        description="将 1+1 的结果写入该名称对应的自定义变量（目标为挂载实体）。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="是否触发自定义变量事件",
        variable_type="布尔值",
        default_value=False,
        description="是否在写入自定义变量时触发对应事件（示例默认关闭）。",
        is_exposed=False,
    ),
]

@validate_node_graph
class 模板示例计算1加1写入自定义变量:
    """节点图类：模板示例_计算1加1_写入自定义变量"""

    def __init__(self, game: GameRuntime, owner_entity):
        """初始化节点图
        
        Args:
            game: 游戏运行时
            owner_entity: 挂载的实体（自身实体）
        """
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        """事件处理器：实体创建时"""
        var_1: "实体" = 获取自身实体(self.game)
        var_2: "字符串" = 获取节点图变量(self.game, 变量名="输出自定义变量名")
        var_3: "整数" = 加法运算(self.game, 左值=1, 右值=1)
        var_4: "布尔值" = 获取节点图变量(self.game, 变量名="是否触发自定义变量事件")
        设置自定义变量(self.game, 目标实体=var_1, 变量名=var_2, 变量值=var_3, 是否触发事件=var_4)

    def register_handlers(self):
        """注册所有事件处理器"""
        self.game.register_event_handler(
            "实体创建时",
            self.on_实体创建时,
            owner=self.owner_entity
        )