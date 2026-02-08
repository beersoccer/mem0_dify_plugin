计划（check_extraction_status 使用独立池并显式关闭）

- 通过 build_local_mem0_config_without_pool 构建独立配置
- 使用 SyncMem0Client 创建 Memory
- 工具结束时显式 close() 释放资源
- 更新单元测试的 mock 与断言

涉及文件：
- tools/check_extraction_status.py
- tests/unit/tools/test_check_extraction_status.py

