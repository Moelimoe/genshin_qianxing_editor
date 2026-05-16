# 简单的测试文件
print("Hello, World!")

# 定义一个简单的类
class TestClass:
    def __init__(self, name):
        self.name = name
    
    def say_hello(self):
        print(f"Hello, {self.name}!")

# 创建实例并调用方法
test = TestClass("Python")
test.say_hello()