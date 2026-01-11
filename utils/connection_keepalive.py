"""Connection keep-alive manager for Mem0 services."""

import threading

from mem0 import Memory

from .constants import HEARTBEAT_INTERVAL
from .logger import get_logger

logger = get_logger(__name__)


class ConnectionKeepAlive:
    """Connection keep-alive manager for underlying services (LLM, Embedding, Vector Store).

    Prevents TCP connection silent timeout by periodically sending lightweight heartbeat
    requests to keep connections alive.
    """

    def __init__(self, memory: Memory, interval: int = HEARTBEAT_INTERVAL) -> None:
        """Initialize the connection keep-alive manager.

        Args:
            memory: Memory instance containing LLM, embedding, and vector store clients.
            interval: Heartbeat interval in seconds. Defaults to HEARTBEAT_INTERVAL.

        """
        self.memory = memory
        self.interval = interval
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._running = False

    def _heartbeat_llm(self) -> None:
        """Send heartbeat to LLM service.

        Uses the LLM's generate_response() method which is provider-agnostic.
        This ensures compatibility with all mem0-supported LLM providers:
        - OpenAI/Azure OpenAI: client.chat.completions.create()
        - Anthropic: client.messages.create()
        - Ollama: client.chat()
        - Gemini: client.models.generate_content()
        - Groq, Together, etc.: provider-specific APIs
        """
        if not hasattr(self.memory, "llm") or self.memory.llm is None:
            return

        try:
            llm = self.memory.llm
            # Use the abstract generate_response() method which works for all providers
            # This is more reliable than accessing provider-specific client APIs
            llm.generate_response(
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=1,
            )
        except Exception:
            logger.exception("LLM heartbeat failed (non-critical)")
            # Don't raise - heartbeat failures shouldn't interrupt the service

    def _heartbeat_embedding(self) -> None:
        """Send heartbeat to Embedding service.

        Uses the Embedding's embed() method which is provider-agnostic.
        This ensures compatibility with all mem0-supported embedding providers:
        - OpenAI/Azure OpenAI: client.embeddings.create()
        - Ollama: client.embeddings()
        - Gemini: client.models.embed_content()
        - HuggingFace: model.encode() or client.embeddings.create()
        - Vertex AI, Together, etc.: provider-specific APIs
        """
        if not hasattr(self.memory, "embedding_model") or self.memory.embedding_model is None:
            return

        try:
            embedding = self.memory.embedding_model
            # Use the abstract embed() method which works for all providers
            # This is more reliable than accessing provider-specific client APIs
            embedding.embed("ping")
        except Exception:
            logger.exception("Embedding heartbeat failed (non-critical)")

    def _heartbeat_vector_store(self) -> None:
        """Send heartbeat to Vector Store service.

        Uses the VectorStore's list_cols() method which is defined in VectorStoreBase.
        This ensures compatibility with all mem0-supported vector store providers:
        - Qdrant, ChromaDB, Pinecone, PGVector, MongoDB, Milvus, Weaviate, etc.
        - Azure AI Search, Elasticsearch, OpenSearch, etc.
        - All providers must implement list_cols() as it's an abstract method.

        Falls back to col_info() or list() if list_cols() is not available,
        and finally to a minimal search operation as last resort.
        """
        if not hasattr(self.memory, "vector_store") or self.memory.vector_store is None:
            return

        try:
            vs = self.memory.vector_store

            # Prefer list_cols() - it's an abstract method in VectorStoreBase,
            # so all providers should implement it
            if hasattr(vs, "list_cols"):
                vs.list_cols()
            elif hasattr(vs, "col_info"):
                # Fallback: Get collection info (lightweight)
                vs.col_info()
            elif hasattr(vs, "list"):
                # Fallback: List with minimal limit
                vs.list(limit=1)
            else:
                # Last resort: empty search with zero vector
                # Note: This requires knowing embedding dimensions
                dims = getattr(vs, "embedding_model_dims", 1536)
                zero_vector = [0.0] * dims
                vs.search(query="", vectors=zero_vector, limit=1)
        except Exception:
            logger.exception("Vector store heartbeat failed (non-critical)")

    def _heartbeat_all(self) -> None:
        """Execute heartbeat for all services."""
        self._heartbeat_llm()
        self._heartbeat_embedding()
        self._heartbeat_vector_store()

    def _run(self) -> None:
        """Heartbeat loop running in background thread."""
        while not self._stop_event.is_set():
            try:
                self._heartbeat_all()
                logger.debug("Executing heartbeat for all services completed successfully")
            except Exception as e:
                logger.warning("Error in heartbeat loop: %s", e)

            # Wait for interval, but can be interrupted by stop event
            self._stop_event.wait(self.interval)

    def start(self) -> None:
        """Start the heartbeat thread."""
        if self._running:
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="Mem0-ConnectionKeepAlive")
        self._thread.start()
        self._running = True
        logger.info("Connection keep-alive started (interval: %ds)", self.interval)

    def stop(self) -> None:
        """Stop the heartbeat thread."""
        if not self._running:
            return

        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5.0)
        self._running = False
        logger.info("Connection keep-alive stopped")

