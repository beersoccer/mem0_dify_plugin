# 计划：checkpoint 统一使用字符串 "true"

- 调整 `checkpoint_metadata()` 写入 `__internal="true"`
- 简化 `checkpoint_filters()` 回到仅字符串过滤
- 移除本地二次过滤与相关兼容函数
- 同步修正同步/异步加载逻辑
- 更新单元测试断言以匹配字符串写入

文件清单：
- `utils/checkpoint.py`
- `tests/unit/utils/test_checkpoint.py`

