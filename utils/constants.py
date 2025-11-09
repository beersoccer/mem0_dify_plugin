"""Project-wide constants for mem0 Dify plugin."""

# Standardized add-operation return shapes
ADD_SKIP_RESULT: dict[str, object] = {
    "results": [
        {
            "id": "",
            "memory": "",
            "event": "SKIP",
        }
    ]
}

ADD_ACCEPT_RESULT: dict[str, object] = {
    "results": [
        {
            "id": "",
            "memory": "",
            "event": "ACCEPT",
        }
    ]
}

# The maximum timeout (in seconds) for a single request, to avoid long waits or hanging connections.
MAX_REQUEST_TIMEOUT: int = 120

# Concurrency controls
# Maximum concurrent add() operations per process to avoid exhausting DB/vector store pools
MAX_CONCURRENT_MEM_ADDS: int = 5

# Default top_k for search
SEARCH_DEFAULT_TOP_K: int = 5

# Unified custom prompt used by both LocalClient and AsyncLocalClient
CUSTOM_PROMPT: str = """
**[核心约束]**
语言保持 (Language Preservation):
  - 提取出的记忆内容必须使用用户在原始输入中使用的语言.
  - 如果输入是中文, 记忆就是中文; 如果输入是英文, 记忆就是英文.

**[输出样例]**
* 输入: My order #12345 hasn't arrived yet.
  输出: {"facts": ["Order #12345 not received"]}
* 输入: 我喜欢踢足球和滑雪.
  输出: {"facts": ["喜欢踢足球", "喜欢滑雪"]}
"""
