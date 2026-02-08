计划（checkpoint/version 调整）

- 移除 checkpoint/task_status metadata 中的 *_key，改为 version=v1
- checkpoint metadata 去掉 user_id，仅保留内部标记与 version
- task_status metadata 同步去掉 task_key，保留 version
- 更新 filters 与相关测试断言
- 保持 agent_id 作为 app_id 的作用域参数

涉及文件：
- utils/checkpoint.py
- utils/task_status.py
- tests/unit/utils/test_checkpoint.py

