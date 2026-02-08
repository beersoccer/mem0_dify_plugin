# 计划：修复检查点过滤导致的回读失败

- 阅读 `utils/checkpoint.py` 中过滤与加载逻辑，定位过滤条件与测试不一致点
- 调整 `checkpoint_filters()`，避免对 `__internal` 进行过于严格的服务端过滤
- 在 `_load_items()` 中增加本地二次过滤，兼容 `True`/`"true"` 等格式
- 同步修改异步加载路径，确保行为一致
- 保持返回结构不变，只修复匹配逻辑以通过现有测试
- 完成后检查相关文件的 lint 提示

文件清单：
- `utils/checkpoint.py`

