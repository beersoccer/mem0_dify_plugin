- 目标：将性能测试的 `DIFY_USER_ID` 更名为“用户数量”并由代码生成 `user1..userN`
- 修改 `performance/.env`：把 `DIFY_USER_COUNT` 设置为整数示例值
- 新增 `performance/user_ids.py`：解析 env 值并生成用户列表
- 更新 `performance/locustfile.py`：改用 `DIFY_USER_COUNT` 并保持随机选择用户
- 更新 `performance/README.md`：同步配置说明与示例
- 新增单元测试：覆盖数值与列表两种输入场景
- 影响文件：`performance/.env`, `performance/locustfile.py`, `performance/user_ids.py`, `performance/README.md`, `tests/unit/utils/test_performance_user_ids.py`

