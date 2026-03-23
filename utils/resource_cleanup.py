"""Resource cleanup utilities for Mem0 AsyncMemory instances."""

import asyncio

from .logger import get_logger

logger = get_logger(__name__)


async def close_vector_store(
    memory: object, loop: asyncio.AbstractEventLoop, client: object | None = None
) -> None:
    """Close vector store connection pool.

    Args:
        memory: Memory instance containing vector store.
        loop: Event loop for running executor tasks.
        client: Unused; kept for API compatibility.

    """
    vs = getattr(memory, "vector_store", None)
    if not vs or not hasattr(vs, "connection_pool") or not vs.connection_pool:
        return

    try:
        pool = vs.connection_pool
        if hasattr(pool, "close"):
            await loop.run_in_executor(None, pool.close)
        elif hasattr(pool, "closeall"):
            await loop.run_in_executor(None, pool.closeall)
    except Exception:
        logger.exception("Error closing vector store connection pool")


async def close_graph_store(memory: object, loop: asyncio.AbstractEventLoop) -> None:
    """Close graph store connections.

    Args:
        memory: Memory instance containing graph store.
        loop: Event loop for running executor tasks.

    """
    graph = getattr(memory, "graph", None)
    if not graph:
        return

    try:
        if hasattr(graph, "close") and not asyncio.iscoroutinefunction(graph.close):
            await loop.run_in_executor(None, graph.close)
        elif hasattr(graph, "aclose"):
            await graph.aclose()
        elif hasattr(graph, "driver") and hasattr(graph.driver, "close"):
            await loop.run_in_executor(None, graph.driver.close)
    except Exception:
        logger.exception("Error closing graph store")


async def close_database(memory: object, loop: asyncio.AbstractEventLoop) -> None:
    """Close database connection.

    Args:
        memory: Memory instance containing database connection.
        loop: Event loop for running executor tasks.

    """
    db = getattr(memory, "db", None)
    if not db or not hasattr(db, "close"):
        return

    try:
        await loop.run_in_executor(None, db.close)
    except Exception:
        logger.exception("Error closing database connection")


async def close_memory_resources(
    memory: object, client: object | None = None
) -> None:
    """Close all critical resources held by AsyncMemory.

    This function explicitly closes critical resources (connection pools, database
    connections) to prevent resource leaks in long-running processes.

    Args:
        memory: Memory instance to cleanup.
        client: Optional client instance to check if sharing pool.

    """
    if memory is None:
        return

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No running event loop - this can happen during cleanup in certain contexts
        # In this case, we can't use run_in_executor, so we'll skip async cleanup
        # and rely on __del__ methods for resource cleanup
        logger.debug(
            "No running event loop during resource cleanup, "
            "relying on __del__ methods for cleanup"
        )
        return

    await close_vector_store(memory, loop, client)
    await close_graph_store(memory, loop)
    await close_database(memory, loop)
