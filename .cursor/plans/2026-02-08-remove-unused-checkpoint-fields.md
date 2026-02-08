目标
- 删除checkpoint中未使用字段并简化逻辑

计划
- 移除UserCheckpoint的last_run_at字段及序列化读写
- 清理相关代码引用与输出
- 更新/移除依赖该字段的测试

涉及文件
- utils/extraction.py
- utils/checkpoint.py
- tools/get_user_checkpoint.py
- tests/unit/utils/test_idempotency.py
- tests/unit/tools/test_get_user_checkpoint.py
- tests/integration/test_dify_integration.py

