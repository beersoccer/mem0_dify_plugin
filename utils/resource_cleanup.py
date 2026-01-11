"""Resource cleanup utilities for Mem0 AsyncMemory instances."""

import asyncio

from .logger import get_logger

logger = get_logger(__name__)


async def close_vector_store(memory: object, loop: asyncio.AbstractEventLoop) -> None:
    """Close vector store connection pool.

    Args:
        memory: Memory instance containing vector store.
        loop: Event loop for running executor tasks.

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


async def close_memory_resources(memory: object) -> None:
    """Close all critical resources held by AsyncMemory.

    This function explicitly closes critical resources (connection pools, database
    connections) to prevent resource leaks in long-running processes.

    Args:
        memory: Memory instance to cleanup.

    """
    if memory is None:
        return

    loop = asyncio.get_running_loop()
    await close_vector_store(memory, loop)
    await close_graph_store(memory, loop)
    await close_database(memory, loop)

