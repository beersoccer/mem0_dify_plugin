# 测试技术指南

## 概述

本文档详细说明测试过程中遇到的技术问题及其解决方案，特别是 gevent monkey patching 冲突问题和 fork 模式隔离方案。

## Gevent Monkey Patching 冲突问题

### 问题现象

**当前状态**：该问题已通过多层防护基本消除（见"实现细节"第3、4节）。以下描述的是未配置防护时会出现的原始症状，保留作为背景说明。

当测试文件导入 `tools/extract_long_term_memory.py`（该文件导入 `dify_plugin.Tool`）时，若不加防护会出现以下错误：

```
MonkeyPatchWarning: Monkey-patching ssl after ssl has already been imported...
RuntimeError: cannot release un-acquired lock
```

### 问题根本原因

#### Gevent Monkey Patching 的工作原理

Gevent 是一个基于协程的 Python 网络库，它通过 **monkey patching** 机制替换标准库中的阻塞 I/O 操作（如 `socket`、`ssl`、`select` 等），使其变成非阻塞的协程操作。

**关键要求**：Gevent 的 monkey patching **必须在导入标准库模块之前执行**，否则会导致冲突。

#### Dify Plugin SDK 的 Gevent 使用

`dify_plugin` SDK 内部使用了 gevent。当导入 `dify_plugin.Tool` 时，会触发以下导入链：

1. `dify_plugin.Tool` → 
2. `dify_plugin` 内部模块 → 
3. `dify_plugin.interfaces.model.ai_model` → 
4. `import gevent.socket` → 
5. **Gevent 自动执行 monkey patching**

#### 与 Pytest 的冲突

**冲突发生的原因**：

1. **Pytest 已导入标准库模块**：
   - Pytest 框架本身或测试加载过程中可能已经导入了 `ssl`、`socket` 等标准库模块
   - 这些模块在 gevent monkey patching 之前就已经被加载

2. **Gevent 尝试替换已导入的模块**：
   - Gevent 检测到 `ssl` 等模块已经被导入
   - 尝试进行 monkey patching 时产生警告和错误
   - 可能导致锁状态不一致，引发 `RuntimeError: cannot release un-acquired lock`

3. **时序问题**：
   - 测试框架的导入顺序与 gevent 的要求冲突
   - 无法控制 pytest 何时导入标准库模块

## 解决方案：Fork 模式隔离

### 方案概述

使用 `pytest-forked` 的 fork 模式在独立的子进程中运行测试，确保 gevent monkey patching 在标准库导入之前执行。

### 实施状态

✅ **已完成实施**

### 实现细节

#### 1. 依赖安装

`pytest-forked` 已添加到 `pyproject.toml` 的 dev 依赖中。

#### 2. 自动检测和标记机制

**文件**: `tests/conftest.py`

实现了自动检测和标记功能：
- 自动扫描测试文件，检测是否导入 `dify_plugin` 或相关工具模块
- 自动为需要隔离的测试添加 `@pytest.mark.dify_plugin` 标记
- 支持检测以下导入：
  - 直接导入 `dify_plugin`
  - 导入 `tools.extract_long_term_memory`（会触发 `dify_plugin.Tool` 导入）
  - 导入 `tools.check_extraction_status`

**检测机制**（优先级由高到低）：
1. **AST 解析**（主要方式）：使用 `ast` 模块解析测试文件，检查 import 语句是否包含 `dify_plugin` 或相关 tools 模块
2. **文件名 fallback**：AST 解析失败时，回退到硬编码文件名列表匹配：
   - `test_extraction_async.py`
   - `test_token_truncation.py`
   - `test_extraction_parameters.py`
   - `test_extract_long_term_memory.py`
   - `test_e2e_session_memory.py`

> **注意**：新增导入 `dify_plugin` 的测试文件会被 AST 自动检测，无需手动维护 fallback 列表。

#### 3. 测试标记配置与警告抑制

**文件**: `pyproject.toml`

已添加 `dify_plugin` 标记定义，并在配置层面抑制 gevent 警告：
```toml
[tool.pytest.ini_options]
addopts = "-p no:warnings -p no:langsmith --tb=short"
asyncio_mode = "auto"
filterwarnings = [
    "ignore::gevent.monkey.MonkeyPatchWarning",
    "ignore:.*gevent.*:UserWarning",
]
markers = [
    "slow: marks tests as slow (deselect with '-m \"not slow\"')",
    "dify_plugin: tests that import dify_plugin (requires fork isolation to avoid gevent monkey patching conflicts)",
]
```

> `-p no:warnings` 禁用了 pytest 的 warnings 插件，`filterwarnings` 在 warnings 插件启用时生效。此外 `conftest.py` 在 pytest 启动的最早阶段（`pytest_load_initial_conftests`）通过 `warnings.filterwarnings` 直接抑制 gevent 警告，以覆盖 `pyproject.toml` 配置尚未加载的窗口期。

#### 4. OutputFilter 输出过滤

**文件**: `tests/conftest.py`

`conftest.py` 安装了 `OutputFilter` 类（替换 `sys.stdout`/`sys.stderr`），在输出层面过滤以下杂乱信息：
- gevent monkey patching 警告行
- langsmith 递归上传错误
- pytest session header 中的无关路径信息

这是对 `pyproject.toml` 警告抑制的补充，处理那些绕过 warnings 系统直接输出到 stderr 的信息。

#### 5. 运行脚本

**文件**: `tests/run_tests.sh`

统一的测试运行脚本，包含：
- 自动检查虚拟环境和 `pytest-forked` 安装状态
- `--e2e` 模式自动启用 `--forked`，并要求 `tests/.env` 存在
- macOS 下 fork 模式自动导出 `OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES`
- `--output-file` 参数将输出通过 `tee` 同时写入文件和终端

### 使用方法

#### 方法1: 手动运行 pytest（推荐）

```bash
source .venv/bin/activate
pytest --forked -m dify_plugin -v -s
```

#### 方法2: 使用脚本

```bash
# 使用统一脚本运行所有需要 dify_plugin 的测试
./tests/run_tests.sh --forked -m dify_plugin -v -s

# 运行特定的测试文件（使用 fork 模式）
./tests/run_tests.sh --forked tests/e2e/test_e2e_session_memory.py -v -s

# 或直接使用 pytest（推荐）
source .venv/bin/activate
pytest --forked -m dify_plugin -v -s
pytest --forked tests/e2e/test_e2e_session_memory.py -v -s

# 运行所有测试（包括需要隔离的，使用 fork 模式）
pytest --forked -v -s
```

#### 方法3: 手动标记测试

如果测试文件没有被自动检测，可以手动添加标记：

```python
import pytest

@pytest.mark.dify_plugin
def test_something():
    from dify_plugin import Tool
    # ... 测试代码
```

### 工作原理

1. **Fork 隔离**：
   - `pytest-forked` 的 `--forked` 选项会在独立的子进程中运行每个测试
   - 这确保了 gevent monkey patching 在标准库模块导入之前执行
   - 完全隔离，不会影响其他测试

2. **自动标记**：
   - `pytest_collection_modifyitems` hook 在测试收集阶段运行
   - 扫描每个测试文件，检查是否导入 `dify_plugin` 相关模块
   - 自动为需要隔离的测试添加标记

3. **并行执行**：
   - 注意：`--forked` 和 `-n auto`（pytest-xdist）通常不一起使用
   - `--forked` 本身已经在独立进程中运行，提供了隔离
   - 如果需要并行执行，可以考虑只使用 `-n auto`（不使用 `--forked`），但需要确保没有 gevent 冲突

### 优势对比

#### 之前（standalone 方案）
- ❌ 需要复制代码，违反 DRY 原则
- ❌ 维护成本高（两处代码需要同步）
- ❌ 无法直接测试 `dify_plugin.Tool` 的集成

#### 现在（fork 模式）
- ✅ 完全隔离，不影响其他测试
- ✅ 不需要修改测试代码
- ✅ 可以正常导入 `dify_plugin`
- ✅ 不需要复制代码
- ✅ 自动检测和标记
- ✅ 支持并行执行

### 注意事项

1. **性能影响**：
   - Fork 模式会在独立进程中运行测试，启动时间稍长
   - 但完全隔离，避免了 gevent 冲突问题

2. **依赖要求**：
   - 需要安装 `pytest-forked`
   - 已在 `pyproject.toml` 中配置

3. **迁移完成**：
   - `test_e2e_session_memory.py` 已使用 fork 模式，可以直接导入 `dify_plugin`
   - 不再需要 standalone 版本

4. **⚠️ 输出捕获限制**：
   - **Fork 模式下，所有输出（包括 stdout 和 stderr）都会被捕获**
   - 即使使用 `-s` 选项，测试通过时也不会显示输出
   - **解决方法**：
     - **查看失败测试的输出**：测试失败时会自动显示捕获的输出
     - **使用 `--tb=short` 查看简短输出**
     - **临时禁用 fork 模式调试**：去掉 `--forked` 参数（但会看到 gevent 警告）
     - **使用断言失败查看中间状态**：在需要查看输出的地方添加 `assert False, "调试点"`

## 其他解决方案（已废弃）

### 方案2：延迟导入 + 环境变量控制

**原理**：在测试中延迟导入 `dify_plugin`，并在导入前设置环境变量控制 gevent 行为。

**缺点**：
- ⚠️ 仍然可能在某些情况下冲突（如果 pytest 已经导入了 ssl）
- ⚠️ 需要修改测试代码

**状态**: 已废弃，使用 fork 模式替代

### 方案3：使用 subprocess 运行测试

**原理**：将需要导入 `dify_plugin` 的测试放在独立的子进程中运行。

**缺点**：
- ⚠️ 测试输出和调试困难
- ⚠️ 无法使用 pytest 的高级功能（fixtures、参数化等）

**状态**: 已废弃，使用 fork 模式替代

### 方案4：Mock dify_plugin 模块

**原理**：对于不需要真正 `dify_plugin` 功能的测试，使用 mock 替代。

**适用场景**：
- ✅ 单元测试（不需要真实 `dify_plugin` 行为）
- ❌ 集成测试（需要真实 `dify_plugin` 行为）

**状态**: 仍可用于单元测试

## 最佳实践建议

### 对于集成测试（需要真实 dify_plugin）

**推荐使用 fork 模式**：

1. 确保 `pytest-forked` 已安装
2. 测试会自动标记为 `dify_plugin`
3. 使用 `pytest --forked` 运行测试

### 对于单元测试（不需要真实 dify_plugin）

**推荐使用 Mock**：

```python
from unittest.mock import patch

@patch("dify_plugin.Tool")
def test_something(mock_tool):
    # 测试代码
    pass
```

### 混合方案

可以同时使用两种方案：
- 单元测试：使用 mock，快速且稳定
- 集成测试：使用 fork 模式，测试真实集成

## 故障排除

### 问题1: 仍然看到 gevent 警告

正常情况下警告已被抑制（`pyproject.toml` + `conftest.py` 双层防护）。若仍出现，按顺序检查：

1. 确认在项目根目录运行 pytest（需要 `pyproject.toml` 生效）：`cd /path/to/mem0_dify_plugin`
2. 确认 `pyproject.toml` 中 `addopts` 包含 `-p no:warnings`
3. 确认使用的是项目虚拟环境：`source .venv/bin/activate`
4. 如仍无法消除，使用 `--forked` 彻底隔离：
   ```bash
   export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES
   pytest --forked -m dify_plugin -v
   ```
5. 检查 `pytest-forked` 是否已安装：`pip list | grep pytest-forked`

### 问题2: 测试没有被自动标记

**解决方案**：
- 检查 `tests/conftest.py` 中的检测逻辑
- 手动添加 `@pytest.mark.dify_plugin` 标记
- 检查测试文件是否在 `_DIFY_PLUGIN_TEST_FILES` 列表中

### 问题3: Fork 模式运行很慢

**原因**：
- Fork 进程有启动开销
- 每个测试在独立进程中运行

**优化建议**：
- 使用 `-n auto` 并行执行（但注意 fork 模式本身已经隔离）
- 减少测试数量或优化测试代码

### 问题4: Fork 模式下看不到测试输出（重要！）

**现象**：
- 使用 `--forked` 运行测试时，即使使用 `-s` 选项，测试通过时也看不到 print 输出
- 去掉 `--forked` 后输出正常

**原因**：
- `pytest-forked` 在子进程中运行测试并捕获所有输出（stdout/stderr）
- 只有测试失败时才显示捕获的输出
- 这是 pytest-forked 的设计行为

**解决方法**：

1. **✅ 将输出保存到文件（推荐）**：
   ```bash
   # 方法1: 使用统一脚本的 --output-file 选项
   ./tests/run_tests.sh --e2e test_01_verify_dify_connectivity --output-file test_output.log
   
   # 方法2: 使用 shell 重定向（同时显示在终端和保存到文件）
   source .venv/bin/activate
   pytest --forked tests/e2e/test_e2e_session_memory.py::TestE2ESessionMemory::test_01_verify_dify_connectivity -v -s 2>&1 | tee test_output.log
   
   # 方法3: 在 .env 文件中设置 TEST_LOG_FILE 环境变量（自动保存）
   # 在 tests/.env 中添加: TEST_LOG_FILE=tests/test_output.log
   pytest --forked tests/test_e2e_session_memory.py -v -s
   ```

2. **调试时临时去掉 `--forked`**（快速查看输出）：
   ```bash
   # 会看到 gevent 警告，但能看到输出
   pytest tests/test_e2e_session_memory.py::TestE2ESessionMemory::test_01_verify_dify_connectivity -v -s
   ```

3. **使用断言查看中间状态**：
   ```python
   # 在需要查看输出的地方
   assert False, f"调试: user_ids = {test_user_ids}"
   ```

4. **让测试失败以查看输出**：
   ```python
   # 临时添加
   pytest.fail(f"调试输出: 处理了 {count} 个用户")
   ```

## 相关文档

- [TESTING_README.md](TESTING_README.md) — 测试运行方法、环境配置、E2E 测试详情、故障排除
- [TESTING_COVERAGE.md](TESTING_COVERAGE.md) — 模块级覆盖分析、测试文件速查表、覆盖缺口与优先级

## 外部参考资料

- [Gevent Monkey Patching 文档](http://www.gevent.org/api/gevent.monkey.html)
- [Pytest-forked 文档](https://pytest-forked.readthedocs.io/)
- [Gevent 与 Pytest 兼容性问题](https://github.com/gevent/gevent/issues/1016)

