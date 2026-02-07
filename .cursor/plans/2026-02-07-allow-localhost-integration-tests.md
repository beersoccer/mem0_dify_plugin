## 计划

- 确认集成测试跳过条件与 localhost 逻辑
- 为 localhost 场景增加显式允许开关
- 将开关纳入 .env 读取范围
- 保持默认行为不变（仍默认跳过）
- 在代码中给出清晰的 skip 提示

## 影响文件

- `tests/integration/test_time_range_filtering.py`

