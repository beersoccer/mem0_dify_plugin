计划（app_id 不再用 "*" 填充）

- checkpoint 读写不再把缺省 app_id 变成 "*"
- get_user_checkpoint 工具返回与日志中保留空 app_id
- 更新单元测试断言（agent_id 为空、返回字段为 None）

涉及文件：
- utils/checkpoint.py
- tools/get_user_checkpoint.py
- tests/unit/utils/test_checkpoint.py
- tests/unit/tools/test_get_user_checkpoint.py

