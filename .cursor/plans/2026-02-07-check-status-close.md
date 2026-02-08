计划（check_extraction_status 使用独立池并显式关闭）

- 使用 build_local_mem0_config_without_pool 构建独立配置
- 改为 SyncMem0Client 创建 Memory
- 在工具执行完成时调用 close() 释放资源
- 更新单元测试 mock 与断言

涉及文件：
- tools/check_extraction_status.py
- tests/unit/tools/test_check_extraction_status.py
计划（check_extraction_status 使用独立池并显式关闭）

- 改为 build_local_mem0_config_without_pool 构建配置
- 使用 SyncMem0Client 获取 Memory 实例
- 在工具结束时显式 close() 释放资源
- 更新单元测试的 mock/断言

涉及文件：
- tools/check_extraction_status.py
- tests/unit/tools/test_check_extraction_status.py

