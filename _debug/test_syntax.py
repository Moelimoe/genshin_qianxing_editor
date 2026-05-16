import ast
import sys

if __name__ == "__main__":
    try:
        # Test activation plate node graph in test directory
        with open('h:/myprojects/genshin_qianxing_editor/assets/资源库/节点图/server/test/启动石板.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Parse the content using AST
        ast.parse(content)
        print('启动石板.py Syntax OK')
        
        # Also test the original chest open tab
        with open('h:/myprojects/genshin_qianxing_editor/assets/资源库/节点图/server/宝箱_打开选项卡.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Parse the content using AST
        ast.parse(content)
        print('宝箱_打开选项卡.py Syntax OK')
        
        sys.exit(0)
    except Exception as e:
        print(f'Syntax error: {e}')
        sys.exit(1)
