"""清理测试记忆数据

运行此脚本以清理之前测试创建的记忆,避免重复内容导致 Mem0 返回 NONE。

使用方法:
    cd tests/e2e
    python cleanup_test_memories.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from utils.mem0_client import get_sync_client

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))



def load_env_config() -> dict[str, str]:
    """从.env文件加载配置"""
    # .env 文件应该在 tests/.env，而不是 tests/e2e/.env
    env_file = Path(__file__).parent.parent / ".env"
    
    if not env_file.exists():
        print(f"❌ 未找到 .env 文件: {env_file}")
        print("请创建 tests/.env 文件并配置以下变量:")
        print("MEM0_LLM_CONFIG, MEM0_EMBEDDER_CONFIG, MEM0_VECTOR_DB_CONFIG")
        sys.exit(1)
    
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
    
    print(f"✓ 已加载环境变量: {env_file}")
    return env_vars


def cleanup_test_memories():
    """删除测试用户的所有记忆"""
    print("\n" + "="*80)
    print("清理测试记忆数据")
    print("="*80)
    
    # Load environment config
    env_config = load_env_config()
    
    # Build credentials from environment
    credentials = {
        "local_llm_json_secret": env_config.get("MEM0_LLM_CONFIG", ""),
        "local_embedder_json_secret": env_config.get("MEM0_EMBEDDER_CONFIG", ""),
        "local_vector_db_json_secret": env_config.get("MEM0_VECTOR_DB_CONFIG", ""),
        "local_graph_db_json_secret": env_config.get("MEM0_GRAPH_DB_CONFIG", ""),
        "local_reranker_json_secret": env_config.get("MEM0_RERANKER_CONFIG", ""),
    }
    
    # Validate required configs
    required_keys = ["MEM0_LLM_CONFIG", "MEM0_EMBEDDER_CONFIG", "MEM0_VECTOR_DB_CONFIG"]
    missing = [key for key in required_keys if not env_config.get(key)]
    if missing:
        print(f"❌ 缺少必需的配置: {missing}")
        sys.exit(1)
    
    # Build mem0 client
    try:
        client = get_sync_client(credentials)
        print("✓ Mem0 客户端已初始化")
    except Exception as e:
        print(f"❌ 无法初始化 Mem0 客户端: {e}")
        sys.exit(1)
    
    # Test user IDs
    test_users = ["real_user", "test_user"]
    
    total_deleted = 0
    for user_id in test_users:
        print(f"\n清理用户: {user_id}")
        try:
            # Use delete_all to delete all memories for this user
            result = client.delete_all({"user_id": user_id})
            
            # Extract deleted count from result if available
            deleted_count = 0
            if isinstance(result, dict):
                deleted_count = result.get("deleted_count", result.get("count", 0))
                if deleted_count == 0 and "message" in result:
                    # If no explicit count, check if operation succeeded
                    print(f"  ✓ {result.get('message', '删除操作已完成')}")
                else:
                    print(f"  ✓ 成功删除 {deleted_count} 条记忆")
            else:
                print("  ✓ 删除操作已完成")
            
            total_deleted += deleted_count
        
        except Exception as e:
            print(f"  ❌ 清理失败: {e}")
            import traceback
            traceback.print_exc()
    
    print(f"\n{'='*80}")
    if total_deleted > 0:
        print(f"清理完成! 总共删除 {total_deleted} 条记忆")
    else:
        print("清理完成! (未统计删除数量)")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    cleanup_test_memories()

