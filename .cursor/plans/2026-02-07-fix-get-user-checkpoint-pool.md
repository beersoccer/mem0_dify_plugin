计划（修复 get_user_checkpoint 连接池关闭报错）

- 使用 build_local_mem0_config_without_pool 避免复用已关闭连接池
- 更新 get_user_checkpoint 工具调用路径
- 调整对应单元测试的 patch 入口

涉及文件：
- tools/get_user_checkpoint.py
- tests/unit/tools/test_get_user_checkpoint.py

