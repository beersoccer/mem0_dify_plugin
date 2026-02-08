计划（update_memory 参数校验与 checkpoint 说明修正）

- 在 update_memory 工具中校验 memory_id 为 UUID
- 更新 update_memory.yaml 文案提示 UUID 要求
- 新增单元测试覆盖非法 memory_id
- 修正 checkpoint 头部注释与当前 app_id/agent_id 逻辑一致

涉及文件：
- tools/update_memory.py
- tools/update_memory.yaml
- tests/unit/tools/test_update_memory.py
- utils/checkpoint.py

