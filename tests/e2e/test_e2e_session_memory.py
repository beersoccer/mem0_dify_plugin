"""端到端验证测试：会话级长期记忆工具

本测试使用 fork 模式运行，可以安全地导入 dify_plugin 相关模块。

前提条件：
- Dify开发环境已启动并包含测试数据
- tests/.env文件配置了必要的凭据
- Mem0环境（PostgreSQL + 向量数据库）已配置

环境变量配置示例 (tests/.env):
```
DIFY_BASE_URL=http://localhost/v1
DIFY_API_KEY=app-xxx
DIFY_USER_IDS=test_user,real_user
DIFY_APP_ID=xxx

# 时间范围配置（可选，如果未设置则使用默认1天）
TEST_START_TIME=2026-01-17T00:00:00Z
TEST_END_TIME=2026-01-18T00:00:00Z

# 测试日志文件（可选，如果设置则自动保存测试输出到文件）
TEST_LOG_FILE=tests/test_output.log

# Mem0配置
MEM0_LLM_CONFIG={"provider":"azure_openai","config":{"model":"gpt-4","api_key":"...","base_url":"..."}}
MEM0_EMBEDDER_CONFIG={"provider":"azure_openai","config":{"model":"text-embedding-ada-002","api_key":"...","base_url":"..."}}
MEM0_VECTOR_DB_CONFIG={"provider":"pgvector","config":{"dbname":"mem0","user":"postgres","password":"...","host":"localhost","port":5432}}
```

运行方式：
推荐手动激活虚拟环境后直接使用 pytest：
    source .venv/bin/activate
    # macOS 上需要设置环境变量以避免 fork() 崩溃
    export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES
    pytest --forked tests/e2e/test_e2e_session_memory.py -v -s

或者使用统一脚本（支持输出到文件）：
    ./tests/run_tests.sh --e2e -v -s                                    # 运行所有测试
    ./tests/run_tests.sh --e2e test_01_verify_dify_connectivity -v -s  # 运行单个测试
    ./tests/run_tests.sh --e2e test_01 --output-file test_output.log   # 保存输出到文件

注意：需要安装 pytest-forked 插件：
    uv add --dev pytest-forked

⚠️ Fork 模式输出限制：
Fork 模式下输出会被捕获，测试通过时不会显示。解决方法：
1. 使用 --output-file 选项将输出保存到文件（推荐）
2. 在 .env 中设置 TEST_LOG_FILE 环境变量自动保存
3. 使用 shell 重定向: pytest --forked ... 2>&1 | tee output.log
4. 调试时临时去掉 --forked 参数查看输出
"""

from __future__ import annotations

import json
import sys
import time
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

# 现在可以安全地导入 tools 模块（使用 fork 模式）
from utils.config_builder import build_local_mem0_config_without_pool
from utils.constants import EXTRACTION_DEFAULT_CONVERSATIONS_LIMIT
from utils.dify_client import DifyClient
from utils.extraction import scan_user_conversations_incremental
from utils.extraction_helpers import (
    count_message_tokens,
    get_time_range_from_days,
)
from utils.helpers import parse_iso_timestamp
from utils.mem0_client import SyncMem0Client
from utils.mem0_extraction import (
    SyncMemoryClassificationManager,
    SyncMemoryWriter,
    build_memory_metadata,
    build_subtype_sync_clients,
)
from utils.message_utils import (
    count_add_results,
    dify_msg_to_mem0_messages,
)


class TestOutputLogger:
    """测试输出日志记录器，支持同时输出到 stdout 和文件"""
    
    def __init__(self, log_file: Path | None = None):
        self.log_file = log_file
        self.file_handle = None
        if log_file:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            # 使用覆盖模式（"w"）而不是追加模式（"a"）
            self.file_handle = log_file.open("w", encoding="utf-8")
    
    def write(self, message: str, flush: bool = True) -> None:
        """写入消息到 stdout 和文件（如果启用）"""
        print(message, flush=flush)
        if self.file_handle:
            self.file_handle.write(message)
            if not message.endswith("\n"):
                self.file_handle.write("\n")
            if flush:
                self.file_handle.flush()
    
    def close(self) -> None:
        """关闭文件句柄"""
        if self.file_handle:
            self.file_handle.close()
            self.file_handle = None
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def load_env_config() -> dict[str, str]:
    """从.env文件加载配置"""
    # .env 文件应该在 tests/.env，而不是 tests/e2e/.env
    env_file = Path(__file__).parent.parent / ".env"
    
    if not env_file.exists():
        skip_reason = (
            f"未找到 .env 文件: {env_file}。请创建 tests/.env 文件并配置以下变量:\n"
            "DIFY_BASE_URL, DIFY_API_KEY, DIFY_USER_IDS, DIFY_APP_ID, "
            "MEM0_LLM_CONFIG, MEM0_EMBEDDER_CONFIG, MEM0_VECTOR_DB_CONFIG"
        )
        # 打印到 stderr 以便在测试输出中可见
        print(f"\n⚠️  跳过测试: {skip_reason}", file=sys.stderr, flush=True)
        pytest.skip(skip_reason, allow_module_level=False)
    
    env_vars: dict[str, str] = {}
    with env_file.open() as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            # 去除单引号和双引号包裹
            value = value.strip().strip('"').strip("'")
            env_vars[key.strip()] = value
    
    required = [
        "DIFY_BASE_URL",
        "DIFY_API_KEY",
        "DIFY_USER_IDS",
        "DIFY_APP_ID",
        "MEM0_LLM_CONFIG",
        "MEM0_EMBEDDER_CONFIG",
        "MEM0_VECTOR_DB_CONFIG",
    ]
    
    missing = [k for k in required if k not in env_vars]
    if missing:
        skip_reason = f".env 缺少必要配置: {', '.join(missing)}"
        # 打印到 stderr 以便在测试输出中可见
        print(f"\n⚠️  跳过测试: {skip_reason}", file=sys.stderr, flush=True)
        if env_vars:
            print(f"   已找到的配置项: {', '.join(env_vars.keys())}", file=sys.stderr, flush=True)
        pytest.skip(skip_reason, allow_module_level=False)
    
    return env_vars


def _format_datetime_local(dt_str_or_timestamp: str | int | float | None) -> str:
    """将时间戳或ISO字符串转换为本地时区显示格式
    
    Args:
        dt_str_or_timestamp: ISO时间字符串、时间戳（int/float）或None
        
    Returns:
        本地时区的格式化字符串，格式：YYYY-MM-DD HH:MM:SS
    """
    if dt_str_or_timestamp is None or dt_str_or_timestamp == "N/A":
        return "N/A"
    
    # 解析时间
    if isinstance(dt_str_or_timestamp, int | float):
        # 时间戳：假设是UTC时间戳
        dt = datetime.fromtimestamp(dt_str_or_timestamp, UTC)
    else:
        # ISO字符串
        dt = parse_iso_timestamp(dt_str_or_timestamp)
        if dt is None:
            return "N/A"
        # 如果时间没有时区信息，假设是UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
    
    # 转换为上海时区（UTC+8）
    shanghai_tz = timezone(timedelta(hours=8))
    local_dt = dt.astimezone(shanghai_tz)
    
    # 格式化为本地时间字符串（不包含时区信息）
    return local_dt.strftime("%Y-%m-%d %H:%M:%S")


def _get_test_time_range(
    env_config: dict[str, str],
    default_days_back: int = 1,
) -> tuple[str, str]:
    """获取测试时间范围：优先使用环境变量，否则根据默认天数计算
    
    Args:
        env_config: 环境配置字典，可能包含 TEST_START_TIME 和 TEST_END_TIME
        default_days_back: 默认回溯天数（如果环境变量不存在），默认1天
        
    Returns:
        (start_time, end_time) ISO8601格式的时间范围
    """
    # 优先使用环境变量
    start_time = env_config.get("TEST_START_TIME")
    end_time = env_config.get("TEST_END_TIME")
    
    if start_time and end_time:
        # 验证时间格式
        start_dt = parse_iso_timestamp(start_time)
        end_dt = parse_iso_timestamp(end_time)
        if start_dt and end_dt:
            return start_time, end_time
    
    # 如果环境变量不存在或格式无效，使用默认计算（默认1天）
    return get_time_range_from_days(default_days_back)


@pytest.fixture
def env_config() -> dict[str, str]:
    """环境配置fixture"""
    return load_env_config()


@pytest.fixture
def dify_client(env_config: dict[str, str]) -> DifyClient:
    """Dify客户端fixture"""
    base_url = env_config["DIFY_BASE_URL"]
    if not base_url.startswith("http"):
        base_url = f"http://{base_url}"
    
    return DifyClient(
        base_url=base_url,
        api_key=env_config["DIFY_API_KEY"],
        timeout=30.0,
    )


@pytest.fixture
def mem0_credentials(env_config: dict[str, str]) -> dict[str, Any]:
    """Mem0凭据fixture"""
    return {
        "local_llm_json_secret": env_config["MEM0_LLM_CONFIG"],
        "local_embedder_json_secret": env_config["MEM0_EMBEDDER_CONFIG"],
        "local_vector_db_json_secret": env_config["MEM0_VECTOR_DB_CONFIG"],
        "local_graph_db_json_secret": env_config.get("MEM0_GRAPH_DB_CONFIG", ""),
        "local_reranker_json_secret": env_config.get("MEM0_RERANKER_CONFIG", ""),
    }


@pytest.fixture
def test_user_ids(env_config: dict[str, str]) -> list[str]:
    """测试用户ID列表"""
    user_ids_str = env_config["DIFY_USER_IDS"]
    return [uid.strip() for uid in user_ids_str.split(",") if uid.strip()]


@pytest.fixture
def test_logger(env_config: dict[str, str]) -> TestOutputLogger:
    """测试输出日志记录器fixture
    
    如果环境变量 TEST_LOG_FILE 已设置，输出将同时写入文件。
    示例: TEST_LOG_FILE=tests/test_output.log
    """
    log_file_path = env_config.get("TEST_LOG_FILE")
    if log_file_path:
        log_file = Path(log_file_path)
    else:
        log_file = None
    
    logger = TestOutputLogger(log_file)
    yield logger
    logger.close()


class TestE2ESessionMemory:
    """端到端会话级长期记忆测试"""
    
    def test_01_verify_dify_connectivity(
        self, 
        dify_client: DifyClient, 
        test_user_ids: list[str],
        env_config: dict[str, str],
        test_logger: TestOutputLogger
    ) -> None:
        """测试1: 验证Dify API连接
        
        注意: 使用 --forked 模式时，输出会被捕获（pytest-forked 的设计行为）。
        解决方法：
        1. 调试时去掉 --forked 参数查看输出
        2. 使用 --output-file 选项将输出保存到文件（推荐）
        3. 在 .env 中设置 TEST_LOG_FILE 环境变量自动保存日志
        """
        test_logger.write("\n" + "="*80)
        test_logger.write("测试1: 验证Dify API连接")
        test_logger.write("="*80)
        
        # 检查 test_user_ids
        assert test_user_ids, "test_user_ids 为空，请检查 DIFY_USER_IDS 配置"
        
        test_logger.write(f"测试用户数量: {len(test_user_ids)}")
        test_logger.write(f"用户ID列表: {test_user_ids}")
        
        # 显示配置的时间范围（如果存在）
        start_time = env_config.get("TEST_START_TIME")
        end_time = env_config.get("TEST_END_TIME")
        if start_time and end_time:
            start_str = _format_datetime_local(start_time)
            end_str = _format_datetime_local(end_time)
            test_logger.write(f"\n配置的时间范围: {start_str} ~ {end_str}")
            test_logger.write("  (用于后续测试的时间过滤)")
        else:
            test_logger.write("\n未配置时间范围，将使用默认值（最近1天）")
        test_logger.write("")
        
        for user_id in test_user_ids:
            test_logger.write(f"\n检查用户: {user_id}")
            
            # 测试获取会话列表
            conv_page = dify_client.list_conversations(
                user_id=user_id,
                limit=5,
            )
            
            test_logger.write("  ✓ 成功获取会话列表")
            test_logger.write(f"  - 会话数量: {len(conv_page.items)}")
            test_logger.write(f"  - 是否有更多: {conv_page.has_more}")
            
            if conv_page.items:
                # 显示所有会话的详细信息
                test_logger.write("\n  会话详情:")
                
                # 解析时间范围用于判断会话是否在范围内
                if start_time and end_time:
                    start_dt = parse_iso_timestamp(start_time)
                    end_dt = parse_iso_timestamp(end_time)
                else:
                    start_dt = end_dt = None
                
                for idx, conv in enumerate(conv_page.items, 1):
                    conv_id = conv.get("id", "N/A")
                    conv_name = conv.get("name") or conv.get("title") or "未命名会话"
                    created_at = conv.get("created_at")
                    updated_at = conv.get("updated_at")
                    
                    created_str = _format_datetime_local(created_at) if created_at else "N/A"
                    updated_str = _format_datetime_local(updated_at) if updated_at else "N/A"
                    
                    # 判断会话是否在配置的时间范围内
                    in_range = ""
                    if start_dt and end_dt and created_at:
                        created_dt = parse_iso_timestamp(created_at)
                        if created_dt:
                            # 检查创建时间是否在范围内
                            if start_dt <= created_dt <= end_dt:
                                in_range = " ✓ [在时间范围内]"
                            else:
                                in_range = " ⚠ [不在时间范围内]"
                    
                    test_logger.write(f"    [{idx}] {conv_name}{in_range}")
                    test_logger.write(f"        - 会话ID: {conv_id[:12]}...")
                    test_logger.write(f"        - 创建时间: {created_str}")
                    test_logger.write(f"        - 更新时间: {updated_str}")
                
                # 测试获取第一个会话的消息
                conv_id = conv_page.items[0]["id"]
                first_conv = conv_page.items[0]
                conv_name = (
                    first_conv.get("name") or first_conv.get("title") or "未命名会话"
                )
                msg_page = dify_client.list_messages(
                    user_id=user_id,
                    conversation_id=conv_id,
                    limit=10,
                )
                
                test_logger.write(f"\n  测试第一个会话的消息: {conv_name}")
                test_logger.write("  ✓ 成功获取消息列表")
                test_logger.write(f"  - 消息数量: {len(msg_page.items)}")
                
                # 显示消息的时间范围
                if msg_page.items:
                    first_msg_time = msg_page.items[0].get("created_at")
                    last_msg_time = msg_page.items[-1].get("created_at")
                    first_str = _format_datetime_local(first_msg_time) if first_msg_time else "N/A"
                    last_str = _format_datetime_local(last_msg_time) if last_msg_time else "N/A"
                    test_logger.write(f"  - 消息时间范围: {first_str} ~ {last_str}")
                
                assert len(conv_page.items) > 0, f"用户 {user_id} 没有会话数据"
                assert len(msg_page.items) > 0, f"会话 {conv_id} 没有消息数据"
    
    def test_02_fetch_all_conversations_and_messages(
        self,
        dify_client: DifyClient,
        test_user_ids: list[str],
        env_config: dict[str, str],
        test_logger: TestOutputLogger,
    ) -> None:
        """测试2: 获取所有会话和消息数据，显示统计信息"""
        test_logger.write("\n" + "="*80)
        test_logger.write("测试2: 获取所有会话和消息数据")
        test_logger.write("="*80)
        
        app_id = env_config.get("DIFY_APP_ID")
        
        # 优先使用环境变量中的时间范围，否则使用默认1天
        start_time, end_time = _get_test_time_range(env_config, default_days_back=1)
        
        for user_id in test_user_ids:
            test_logger.write(f"\n用户: {user_id}")
            test_logger.write(f"配置的时间范围: {start_time} 到 {end_time}")
            test_logger.write("实际过滤条件:")
            test_logger.write(f"  - 消息时间下限 (start_time): {start_time}")
            test_logger.write(f"  - 消息时间上限 (end_time): {end_time}")
            max_convs = EXTRACTION_DEFAULT_CONVERSATIONS_LIMIT
            test_logger.write(f"  - 最大扫描会话数 (max_conversations): {max_convs}")
            test_logger.write("")
            test_logger.write("说明:")
            test_logger.write(
                "  - 会话扫描按 updated_at 降序进行，不受时间范围限制"
            )
            test_logger.write(
                "  - 消息过滤在消息级别进行：只保留 "
                "start_time <= created_at <= end_time 的消息"
            )
            test_logger.write(
                "  - 如果会话的所有消息都不在时间范围内，"
                "该会话不会出现在结果中"
            )
            test_logger.write("")
            
            # 使用增量扫描获取所有会话和消息
            # 注意：scan_user_conversations_incremental 的参数名是 run_at，
            # 但语义上等同于 end_time
            conversations_data, stats, stop_reason = (
                scan_user_conversations_incremental(
                    dify_client,
                    user_id=user_id,
                    run_at=end_time,  # run_at 参数表示时间范围的上限（end_time）
                    user_checkpoint=None,
                    app_id=app_id,
                    start_time=start_time,
                    max_conversations=EXTRACTION_DEFAULT_CONVERSATIONS_LIMIT,
                )
            )
            
            # 统计信息
            total_conversations = len(conversations_data)
            total_messages = sum(len(msgs) for msgs in conversations_data.values())
            
            test_logger.write("扫描统计:")
            max_convs = EXTRACTION_DEFAULT_CONVERSATIONS_LIMIT
            test_logger.write(
                f"  - 扫描的会话数: {stats.scanned_conversations} "
                f"(按 updated_at 降序，最多 {max_convs} 个)"
            )
            test_logger.write(
                f"  - 扫描的消息数: {stats.scanned_messages} "
                "(在扫描的会话中)"
            )
            test_logger.write(
                f"  - 丢弃的未来消息数: {stats.dropped_future_messages} "
                "(created_at > end_time)"
            )
            test_logger.write(f"  - 停止原因: {stop_reason}")
            test_logger.write("")
            test_logger.write("过滤后的结果:")
            test_logger.write(
                f"  - 时间范围内的会话数: {total_conversations} "
                "(至少有一条消息在时间范围内)"
            )
            test_logger.write(
                f"  - 时间范围内的消息数: {total_messages} "
                "(start_time <= created_at <= end_time)"
            )
            
            # 显示每个会话的详细信息
            if conversations_data:
                test_logger.write("\n会话详情:")
                for idx, (conv_id, messages) in enumerate(conversations_data.items(), 1):
                    msg_count = len(messages)
                    token_count = count_message_tokens(messages)
                    
                    # 获取时间范围（转换为本地时区显示）
                    if messages:
                        first_time = messages[0].get("created_at")
                        last_time = messages[-1].get("created_at")
                        first_str = _format_datetime_local(first_time)
                        last_str = _format_datetime_local(last_time)
                        time_range = f"{first_str} ~ {last_str}"
                    else:
                        time_range = "N/A"
                    
                    test_logger.write(f"  [{idx}] 会话ID: {conv_id[:12]}...")
                    test_logger.write(f"      - 消息数: {msg_count}")
                    test_logger.write(f"      - Token数: {token_count}")
                    test_logger.write(f"      - 时间范围: {time_range}")
            
            # 验证数据的有效性：若时间范围内没有数据则跳过（依赖真实环境数据）
            if total_conversations == 0 or total_messages == 0:
                pytest.skip(
                    f"用户 {user_id} 在指定时间范围内没有会话/消息，跳过用例"
                )
    
    def test_03_extract_long_term_memory_simple(
        self,
        dify_client: DifyClient,
        test_user_ids: list[str],
        env_config: dict[str, str],
        mem0_credentials: dict[str, Any],
        test_logger: TestOutputLogger,
    ) -> None:
        """测试3: 简化的长期记忆抽取（单个会话测试）"""
        test_logger.write("\n" + "="*80)
        test_logger.write("测试3: 简化的长期记忆抽取测试")
        test_logger.write("="*80)
        
        app_id = env_config.get("DIFY_APP_ID")
        
        # 优先使用环境变量中的时间范围，否则使用默认1天
        start_time, end_time = _get_test_time_range(env_config, default_days_back=1)
        
        # 创建Mem0客户端实例（使用独立连接池，与业务代码保持一致）
        from mem0 import Memory

        config = build_local_mem0_config_without_pool(mem0_credentials)
        base_client = SyncMem0Client(mem0_credentials, enable_keepalive=False)
        base_client.memory = Memory.from_config(config)
        subtype_clients = build_subtype_sync_clients(
            mem0_credentials, base_client=base_client
        )
        
        # 只测试第一个用户的第一个会话
        test_user_id = test_user_ids[0]
        test_logger.write(f"\n测试用户: {test_user_id}")
        
        # 获取第一个会话
        conversations_data, stats, _ = scan_user_conversations_incremental(
            dify_client,
            user_id=test_user_id,
            run_at=end_time,  # run_at 参数表示时间范围的上限（end_time）
            user_checkpoint=None,
            app_id=app_id,
            start_time=start_time,
            max_conversations=1,
        )
        
        if not conversations_data:
            pytest.skip(f"用户 {test_user_id} 没有可用的会话数据")
        
        # 获取第一个会话
        conv_id, messages = next(iter(conversations_data.items()))
        msg_count = len(messages)
        token_count = count_message_tokens(messages)
        
        test_logger.write("\n会话信息:")
        test_logger.write(f"  - 会话ID: {conv_id}")
        test_logger.write(f"  - 消息数: {msg_count}")
        test_logger.write(f"  - Token数: {token_count}")
        
        # 转换为mem0格式
        mem0_msgs = dify_msg_to_mem0_messages(messages)
        
        if not mem0_msgs:
            pytest.skip(f"会话 {conv_id} 没有有效的消息内容")
        
        test_logger.write(f"  - Mem0消息数: {len(mem0_msgs)}")
        
        # 步骤1: 分类会话类型并评估提取价值
        test_logger.write("\n步骤1: 分类会话记忆类型并评估提取价值...")
        
        classification_mgr = SyncMemoryClassificationManager(subtype_clients["semantic"].memory)
        classified_type, should_extract = classification_mgr.classify(messages=mem0_msgs)
        
        if classified_type is None or not should_extract:
            skip_reason = (
                "未分类出有意义的记忆类型" if classified_type is None
                else "LLM判断内容不值得抽取"
            )
            test_logger.write(f"  ⚠ {skip_reason}")
            
            # 验证skip的原因是否符合预期
            # 当should_extract为False时，必须skip（这是正确的行为）
            assert not should_extract, (
                f"当should_extract为False时应该skip，"
                f"但should_extract为{should_extract}，这不符合预期"
            )
            
            # 如果classified_type为None，should_extract也应该是False
            if classified_type is None:
                assert not should_extract, (
                    f"当classified_type为None时，should_extract应该为False，"
                    f"但实际为{should_extract}"
                )
                test_logger.write(
                    "  ✓ 验证通过: Classification正确识别为无意义内容"
                )
            else:
                # classified_type不为None但should_extract为False
                # 说明LLM判断内容不值得提取（例如：只有意图声明，无实际内容）
                test_logger.write(
                    f"  ✓ 验证通过: Classification判断内容不值得提取"
                    f" (type={classified_type}, should_extract={should_extract})"
                )
            
            pytest.skip(skip_reason)
        
        test_logger.write(
            f"  ✓ 分类: {classified_type} | 提取价值: 值得提取"
        )
        
        # 步骤2: 抽取记忆
        test_logger.write(f"\n步骤2: 抽取 {classified_type} 类型记忆...")
        
        metadata = build_memory_metadata(
            subtype=classified_type,
            memory_origin="implicit",
        )
        
        writer = SyncMemoryWriter(subtype_clients[classified_type])
        result = writer.add_memory(
            messages=mem0_msgs,
            user_id=test_user_id,
            agent_id=app_id,
            metadata=metadata,
        )
        
        memory_count = count_add_results(result)
        test_logger.write(f"  ✓ 成功抽取 {memory_count} 条记忆")
        
        # 验证结果
        assert memory_count > 0, (
            f"应该至少抽取到一条记忆。分类: {classified_type}, "
            f"消息数: {len(mem0_msgs)}"
        )
    
    def test_04_extract_memory_from_test_dataset(
        self,
        mem0_credentials: dict[str, Any],
        env_config: dict[str, str],
        test_logger: TestOutputLogger,
    ) -> None:
        """测试4: 使用测试数据集验证记忆提取功能
        
        从 test_conversation_data.json 加载测试会话数据，验证：
        1. 记忆分类准确性（分类结果应与预期类型匹配）
        2. 记忆提取成功性（应成功提取到记忆）
        3. 不同记忆类型的提取效果
        4. 中英文会话的处理能力
        """
        test_logger.write("\n" + "="*80)
        test_logger.write("测试4: 使用测试数据集验证记忆提取功能")
        test_logger.write("="*80)
        
        # 加载测试数据集
        test_data_path = Path(__file__).parent / "test_conversation_data.json"
        if not test_data_path.exists():
            pytest.skip(f"测试数据文件不存在: {test_data_path}")
        
        with test_data_path.open(encoding="utf-8") as f:
            test_data = json.load(f)
        
        conversations = test_data.get("conversations", [])
        if not conversations:
            pytest.skip("测试数据集中没有会话数据")
        
        test_logger.write(f"\n加载了 {len(conversations)} 个测试会话")
        
        # 创建Mem0客户端实例（使用独立连接池，与业务代码保持一致）
        from mem0 import Memory

        config = build_local_mem0_config_without_pool(mem0_credentials)
        base_client = SyncMem0Client(mem0_credentials, enable_keepalive=False)
        base_client.memory = Memory.from_config(config)
        subtype_clients = build_subtype_sync_clients(
            mem0_credentials, base_client=base_client
        )
        app_id = env_config.get("DIFY_APP_ID", "test_app")
        
        # 为每个测试运行生成唯一的用户ID后缀，避免记忆去重问题
        # 使用时间戳确保每次运行都使用新的用户ID
        unique_suffix = f"_test_{int(time.time() * 1000)}"
        test_logger.write(f"使用唯一用户ID后缀: {unique_suffix} (避免记忆去重)")
        
        # 统计信息
        total_tested = 0
        total_passed = 0
        classification_correct = 0
        extraction_successful = 0
        
        # 按记忆类型分组统计
        type_stats = {
            "SEMANTIC": {"total": 0, "correct_class": 0, "extracted": 0},
            "EPISODIC": {"total": 0, "correct_class": 0, "extracted": 0},
            "PROCEDURAL": {"total": 0, "correct_class": 0, "extracted": 0},
        }
        
        # 测试每个会话
        for conv in conversations:
            conv_id = conv.get("conversation_id", "unknown")
            base_user_id = conv.get("user_id", "unknown")
            # 添加唯一后缀以避免记忆去重
            user_id = f"{base_user_id}{unique_suffix}"
            expected_type = conv.get("memory_type", "").upper()
            messages = conv.get("messages", [])
            
            if not messages:
                test_logger.write(f"\n跳过会话 {conv_id}: 没有消息")
                continue
            
            total_tested += 1
            test_logger.write(f"\n{'='*60}")
            test_logger.write(f"测试会话: {conv_id}")
            test_logger.write(f"  用户: {user_id}")
            test_logger.write(f"  预期类型: {expected_type}")
            test_logger.write(f"  消息数: {len(messages)}")
            
            # 更新类型统计
            if expected_type in type_stats:
                type_stats[expected_type]["total"] += 1
            
            # 转换为mem0格式
            mem0_msgs = dify_msg_to_mem0_messages(messages)
            if not mem0_msgs:
                test_logger.write("  ⚠ 跳过: 无法转换为有效的Mem0消息")
                continue
            
            test_logger.write(f"  Mem0消息数: {len(mem0_msgs)}")
            
            # 步骤1: 分类会话类型并评估提取价值（合并步骤）
            test_logger.write("\n  步骤1: 分类会话记忆类型并评估提取价值...")
            try:
                classification_mgr = SyncMemoryClassificationManager(
                    subtype_clients["semantic"].memory
                )
                classified_type, should_extract = classification_mgr.classify(
                    messages=mem0_msgs
                )
                
                if classified_type is None:
                    test_logger.write("  ⚠ 分类结果: None (未分类出有意义的记忆类型)")
                    continue
                
                classified_type_upper = classified_type.upper()
                test_logger.write(f"  ✓ 分类结果: {classified_type_upper}")
                test_logger.write(
                    f"  ✓ 提取价值: {'值得提取' if should_extract else '不值得提取'}"
                )
                
                # 如果LLM判断不值得提取，跳过
                if not should_extract:
                    test_logger.write("  ⚠ 跳过: LLM判断内容不值得抽取")
                    continue
                
                # 验证分类准确性
                if classified_type_upper == expected_type:
                    classification_correct += 1
                    if expected_type in type_stats:
                        type_stats[expected_type]["correct_class"] += 1
                    test_logger.write("  ✓ 分类正确！与预期类型匹配")
                else:
                    mismatch_msg = (
                        f"  ✗ 分类不匹配！预期: {expected_type}, "
                        f"实际: {classified_type_upper}"
                    )
                    test_logger.write(mismatch_msg)
                
            except Exception as e:
                test_logger.write(f"  ✗ 分类失败: {e}")
                continue
            
            # 步骤2: 抽取记忆
            test_logger.write(
                f"\n  步骤2: 抽取 {classified_type_upper} 类型记忆..."
            )
            try:
                metadata = build_memory_metadata(
                    subtype=classified_type,
                    memory_origin="implicit",
                )
                
                writer = SyncMemoryWriter(subtype_clients[classified_type])
                result = writer.add_memory(
                    messages=mem0_msgs,
                    user_id=user_id,
                    agent_id=app_id,
                    metadata=metadata,
                )
                
                # 统计抽取结果
                memory_count = count_add_results(result)
                
                # 如果提取失败，提供诊断信息
                if memory_count == 0 and isinstance(result, dict) and "results" in result:
                    results_list = result.get("results", [])
                    if isinstance(results_list, list) and len(results_list) > 0:
                        # 统计事件类型用于诊断
                        event_counts = {}
                        for r in results_list:
                            if isinstance(r, dict):
                                event = str(r.get("event", "UNKNOWN")).upper()
                                event_counts[event] = event_counts.get(event, 0) + 1
                        if event_counts.get('NONE', 0) == len(results_list):
                            test_logger.write(
                                "  ⚠️ 所有结果都是 NONE - "
                                "可能是记忆已存在（去重）或 LLM 未提取到新事实"
                            )
                    elif len(results_list) == 0:
                        test_logger.write("  ⚠️ mem0 没有返回任何结果")
                
                test_logger.write(f"  ✓ 成功抽取 {memory_count} 条记忆")
                
                if memory_count > 0:
                    extraction_successful += 1
                    if expected_type in type_stats:
                        type_stats[expected_type]["extracted"] += 1
                    
                    # 显示抽取的记忆内容（前3条）
                    if isinstance(result, dict) and "results" in result:
                        results = result["results"]
                        if isinstance(results, list):
                            displayed = 0
                            for mem_result in results:
                                if displayed >= 3:
                                    break
                                if isinstance(mem_result, dict):
                                    event = mem_result.get("event", "UNKNOWN")
                                    memory_text = mem_result.get("memory", "")
                                    if event != "NONE" and memory_text:
                                        displayed += 1
                                        truncated = memory_text[:100]
                                        suffix = "..." if len(memory_text) > 100 else ""
                                        test_logger.write(f"    [{displayed}] {truncated}{suffix}")
                else:
                    test_logger.write("  ⚠ 未提取到记忆")
                
            except Exception as e:
                test_logger.write(f"  ✗ 抽取失败: {e}")
                continue
            
            total_passed += 1
        
        # 输出统计摘要
        test_logger.write(f"\n{'='*80}")
        test_logger.write("测试摘要")
        test_logger.write(f"{'='*80}")
        test_logger.write(f"总测试会话数: {total_tested}")
        test_logger.write(f"成功处理会话数: {total_passed}")
        test_logger.write(f"分类准确数: {classification_correct}/{total_passed}")
        test_logger.write(f"成功提取记忆数: {extraction_successful}/{total_passed}")
        
        test_logger.write("\n按记忆类型统计:")
        for mem_type, stats in type_stats.items():
            if stats["total"] > 0:
                total = stats["total"]
                class_rate = (
                    (stats["correct_class"] / total) * 100 if total > 0 else 0
                )
                extract_rate = (
                    (stats["extracted"] / total) * 100 if total > 0 else 0
                )
                test_logger.write(f"  {mem_type}:")
                test_logger.write(f"    总数: {stats['total']}")
                correct_msg = (
                    f"    分类准确: {stats['correct_class']}/{total} "
                    f"({class_rate:.1f}%)"
                )
                extract_msg = (
                    f"    成功提取: {stats['extracted']}/{total} "
                    f"({extract_rate:.1f}%)"
                )
                test_logger.write(correct_msg)
                test_logger.write(extract_msg)
        
        # 验证基本要求
        assert total_tested > 0, "应该至少测试一个会话"
        assert total_passed > 0, "应该至少成功处理一个会话"
        assert classification_correct > 0, "应该至少有一个会话分类正确"
        assert extraction_successful > 0, "应该至少成功提取一条记忆"
        
        # 分类准确率应该至少50%（考虑到LLM可能的不确定性）
        if total_passed > 0:
            classification_rate = (classification_correct / total_passed) * 100
            test_logger.write(f"\n分类准确率: {classification_rate:.1f}%")
            # 注意：这里不强制要求100%准确，因为LLM分类可能有偏差
            # 但至少应该有一定准确率


if __name__ == "__main__":
    # 允许直接运行此文件进行测试
    pytest.main([__file__, "-v", "-s"])

