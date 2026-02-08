目标
- 将 checkpoint 相关的通用函数从工具文件移动到 helper 模块

计划
- 把三个函数移动到 utils/extraction_helpers.py
- 调整导入以避免循环依赖（使用 TYPE_CHECKING）
- 更新 tools/extract_long_term_memory.py 的引用

涉及文件
- utils/extraction_helpers.py
- tools/extract_long_term_memory.py

