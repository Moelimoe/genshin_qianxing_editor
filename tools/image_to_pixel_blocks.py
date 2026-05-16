# 图像处理工具：将图片转换为像素块数据

from __future__ import annotations

import os
import sys
from pathlib import Path
from PIL import Image
import numpy as np


def image_to_pixel_blocks(image_path: str, block_size: int = 8) -> tuple[list[list[dict]], int, int]:
    """将图片转换为像素块数据
    
    Args:
        image_path: 图片路径
        block_size: 像素块大小，默认8x8
    
    Returns:
        tuple[list[list[dict]], int, int]: 
            - 像素块数据矩阵，每个元素包含颜色信息
            - 图片宽度（像素）
            - 图片高度（像素）
    """
    # 打开图片并转换为RGB
    img = Image.open(image_path).convert('RGB')
    width, height = img.size
    
    # 转换为numpy数组
    img_array = np.array(img)
    
    # 计算像素块数量
    blocks_x = (width + block_size - 1) // block_size
    blocks_y = (height + block_size - 1) // block_size
    
    # 初始化像素块矩阵
    pixel_blocks = []
    
    # 遍历每个像素块
    for y in range(blocks_y):
        row = []
        for x in range(blocks_x):
            # 计算当前像素块的区域
            x_start = x * block_size
            y_start = y * block_size
            x_end = min(x_start + block_size, width)
            y_end = min(y_start + block_size, height)
            
            # 提取像素块区域
            block_region = img_array[y_start:y_end, x_start:x_end]
            
            # 计算该像素块的平均颜色
            avg_color = block_region.mean(axis=(0, 1)).astype(int)
            
            # 创建像素块数据
            block_data = {
                'x': x,
                'y': y,
                'avg_color': tuple(avg_color),
                'width': x_end - x_start,
                'height': y_end - y_start,
                'block_size': block_size
            }
            
            row.append(block_data)
        pixel_blocks.append(row)
    
    return pixel_blocks, width, height


def generate_pixel_block_node_graph(pixel_blocks: list[list[dict]], output_path: str):
    """生成像素块节点图
    
    Args:
        pixel_blocks: 像素块数据矩阵
        output_path: 输出节点图文件路径
    """
    # 生成像素块数据字符串
    pixel_data_list = []
    for row in pixel_blocks:
        for block in row:
            pixel_data_list.append({
                'x': block['x'],
                'y': block['y'],
                'avg_color': block['avg_color'],
                'block_size': block['block_size']
            })
    
    # 转换为Python字符串表示
    pixel_data_str = str(pixel_data_list)
    
    # 生成节点图内容
    node_graph_content = '''
"""
graph_id: pixel_art_generator
graph_name: 像素块图像生成器
graph_type: client
description: 将图片转换为像素块的节点图

节点图变量:
- 图片路径: 字符串 = "assets/images/sss.png"
- 像素块大小: 整数 = 8
- 生成位置: 三维向量 = [0, 0, 0]
- 缩放比例: 浮点数 = 1.0
"""

from __future__ import annotations

import sys
import pathlib

脚本文件路径 = pathlib.Path(__file__).resolve()
节点图根目录 = 脚本文件路径.parents[2]  # 节点图根目录（.../节点图）
客户端节点图目录 = 节点图根目录 / "client"  # 包含 client 侧 `_prelude.py` 的目录
if str(客户端节点图目录) not in sys.path:
    sys.path.insert(0, str(客户端节点图目录))

from _prelude import *  # noqa: F401,F403
from engine.graph.models.package_model import GraphVariableConfig


GRAPH_VARIABLES: list[GraphVariableConfig] = [
    GraphVariableConfig(
        name="图片路径",
        variable_type="字符串",
        default_value="assets/images/sss.png",
        description="要转换的图片路径",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="像素块大小",
        variable_type="整数",
        default_value=8,
        description="像素块大小",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="生成位置",
        variable_type="三维向量",
        default_value=[0, 0, 0],
        description="像素块生成的起始位置",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="缩放比例",
        variable_type="浮点数",
        default_value=1.0,
        description="像素块缩放比例",
        is_exposed=True,
    ),
]


class 像素块图像生成器:
    """将图片转换为像素块的节点图
    
    1. 从图片路径加载图片
    2. 将图片转换为像素块数据
    3. 生成像素块实体
    4. 组合成完整图像
    """

    def __init__(self, game):
        self.game = game

        from app.runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    # ---------------------------- 事件：节点图开始 ----------------------------
    def on_节点图开始(self):
        """节点图开始事件，执行像素块生成逻辑"""
        图片路径: "字符串" = 获取节点图变量(self.game, 变量名="图片路径")
        像素块大小: "整数" = 获取节点图变量(self.game, 变量名="像素块大小")
        生成位置: "三维向量" = 获取节点图变量(self.game, 变量名="生成位置")
        缩放比例: "浮点数" = 获取节点图变量(self.game, 变量名="缩放比例")

        # 像素块数据（预生成）
        像素块数据 = " + pixel_data_str + "

        # 遍历生成每个像素块
        for 块数据 in 像素块数据:
            # 计算像素块位置
            块位置 = [
                生成位置[0] + 块数据['x'] * 块数据['block_size'] * 缩放比例,
                生成位置[1] - 块数据['y'] * 块数据['block_size'] * 缩放比例,
                生成位置[2]
            ]

            # 计算颜色值（归一化到0-1范围）
            颜色 = [c / 255.0 for c in 块数据['avg_color']]

            # 这里可以添加生成像素块实体的逻辑
            # 示例：创建一个立方体或平面作为像素块
            # 创建元件(
            #     self.game,
            #     元件ID="像素块元件",
            #     位置=块位置,
            #     旋转=[0, 0, 0],
            #     拥有者实体=None,
            #     是否覆写等级=False,
            #     等级=1,
            #     单位标签索引列表=[]
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
'''
    
    # 写入节点图文件
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(node_graph_content)


def main():
    """主函数"""
    # 图片路径
    image_path = r"H:\myprojects\genshin_qianxing_editor\assets\images\sss.png"
    # 像素块大小
    block_size = 8
    # 输出节点图路径
    output_dir = r"H:\myprojects\genshin_qianxing_editor\assets\资源库\节点图\client\像素艺术"
    output_path = os.path.join(output_dir, "像素块图像生成器.py")
    
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    
    # 将图片转换为像素块
    print(f"正在处理图片: {image_path}")
    pixel_blocks, width, height = image_to_pixel_blocks(image_path, block_size)
    print(f"图片尺寸: {width}x{height} 像素")
    print(f"生成像素块数量: {len(pixel_blocks)}x{len(pixel_blocks[0])} = {len(pixel_blocks) * len(pixel_blocks[0])} 块")
    
    # 生成节点图
    print(f"正在生成节点图: {output_path}")
    generate_pixel_block_node_graph(pixel_blocks, output_path)
    print("节点图生成完成！")


if __name__ == "__main__":
    main()
