# Live Sync — AI 工作索引

> **每次新对话开始时，请先读取本文件，再按需读取下方引用的文档。**

---

## 📋 必读文件

| 优先级 | 文件 | 用途 | 何时读 |
|--------|------|------|--------|
| ⭐⭐⭐⭐ | `WORK_SESSION.md` | 当前工作会话、进度追踪 | 每次对话开始 |
| ⭐⭐⭐ | `NODE_REFERENCE.md` | 官方节点参考手册（引脚定义权威） | 定义/修正节点时 |
| ⭐⭐ | `README.md` | 项目总览、开发环境、开发规则 | 配置环境、查规则时 |
| ⭐⭐ | `API_REFERENCE.md` | 编程接口文档 | 编写代码时 |
| ⭐ | `NOTE.md` | 开发笔记（GIA 结构知识、学习笔记、历史记忆） | 查找技术细节时 |
| ⭐ | `TODO.md` | 待办事项 | 安排工作时 |

---

## 📁 关键源码文件

| 文件 | 用途 |
|------|------|
| `node_catalog.py` | 节点定义注册表（**必须与 NODE_REFERENCE.md 一致**） |
| `level_builder.py` | GraphBuilder 节点图构建器 |
| `level_exporter.py` | GIA 导出器 |
| `gia_loader.py` | GIA 文件加载器 |
| `gia_utils.py` | GIA 编解码工具（Pin Kind 常量等） |
| `gia_viz.py` | GIA 可视化（解析→HTML） |
| `validator.py` | GIA 结构验证器 |
| `verified_type_ids.py` | 534 条 type_id ↔ 名称映射 |
| `asset_registry.py` | 资产对象注册表 |
| `tests/` | 测试模块 |
| `samples/level_demo/level_generator.py` | 宝藏房间关卡 demo |
| `_scratch/` | 临时脚本（**临时脚本放这里**） |

---

## 📁 外部参考资源

| 资源 | 路径/URL |
|------|---------|
| 节点库缓存（最高运行时权威） | `assets/资源库/app/runtime/cache/node_cache/node_library.json` |
| 官方节点介绍页 | `https://act.mihoyo.com/ys/ugc/tutorial/detail/mhsok60iqlxk` |
| 官方教程课程 | `https://act.mihoyo.com/ys/ugc/tutorial/course/home` |
| 游戏节点库（加密） | `...\Resource\Json\Beyond\Node\` |
| 游戏官方蓝图 | `...\Resource\Json\Beyond\Official\` |
