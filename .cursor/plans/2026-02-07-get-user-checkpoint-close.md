计划（get_user_checkpoint 使用 SyncMem0Client 并显式 close）

- 用 build_local_mem0_config_without_pool 构建独立配置
- 改为 SyncMem0Client(config_override=...) 创建 Memory
- 在工具执行完成时调用 close() 释放资源
- 更新单元测试 mock/pattern

涉及文件：
- tools/get_user_checkpoint.py
- tests/unit/tools/test_get_user_checkpoint.py

