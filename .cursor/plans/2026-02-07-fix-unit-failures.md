## 计划

- 审核失败用例，确认是实现变更还是测试期望不一致
- 为状态查询测试添加稳健的文本提取辅助函数
- 修正对话数上限测试中的“正常用户”样例数据
- 将异步任务状态测试改为同步包装调用，避免事件循环冲突
- 复核相关断言与注释，确保与默认配置一致

## 影响文件

- `tests/unit/tools/test_check_extraction_status.py`
- `tests/unit/tools/test_extraction_parameters.py`
- `tests/unit/utils/test_task_status_async.py`

