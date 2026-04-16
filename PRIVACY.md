## Privacy Policy

Last updated: 2026-04-16

This privacy policy describes how the Mem0 Dify Plugin handles your information when you use it in **self-hosted mode**.

### Important: Self-Hosted Mode Operation

This plugin operates exclusively in **self-hosted mode**, which means:
- **All data is stored in your own infrastructure** - You configure and manage your own vector database and graph database
- **No data is sent to external servers** - All processing happens locally using your configured services
- **You control all data** - You have complete control over where and how your data is stored

### Information Processed by the Plugin

The plugin processes the following types of information:

1. **Conversation History**
   - Chat messages between users and AI assistants
   - Message content for semantic search functionality
   - Message metadata (timestamps, roles, user_id, agent_id, run_id)

2. **User Identification**
   - User IDs for partitioning and organizing data
   - Agent IDs and Run IDs for scoping memories
   - No personal identification information (PII) is required beyond these identifiers

3. **Internal Task Status Records**
   - Extraction task progress is stored as internal memory records
   - These records are isolated under a dedicated internal user id

### How Your Information is Used

The processed information is used for:
- Storing conversation history in your configured vector database
- Enabling semantic search across past conversations
- Maintaining user-specific memory partitions
- Providing memory management functionality (add, update, delete, retrieve)

### Data Storage and Security

**All data storage is your responsibility:**
- All data is stored in **your own vector database** (e.g., PostgreSQL with pgvector, MongoDB, etc.)
- Optional graph data is stored in **your own graph database** (e.g., Neo4j, Memgraph)
- **No data is stored on mem0's servers** or any external infrastructure
- Data is partitioned by user_id to ensure isolation within your database
- You are responsible for implementing security measures for your own databases
- Access control is managed through your database configuration and Dify plugin authentication

### Services Used

The plugin uses the following services that **you configure**:
- **LLM Provider**: Your configured LLM service (OpenAI, Azure OpenAI, Anthropic, etc.)
- **Embedding Model**: Your configured embedding service (OpenAI, Azure OpenAI, etc.)
- **Vector Database**: Your configured vector database (PostgreSQL/pgvector, MongoDB, etc.)
- **Graph Database** (optional): Your configured graph database (Neo4j, Memgraph, etc.)
- **Reranker** (optional): Your configured reranking service

**All API keys and credentials are stored in your Dify instance configuration and are not shared with any third parties.**

### Data Retention

- Conversation history is retained in your database until explicitly deleted by you
- You can delete memories using the plugin's delete tools (`delete_memory`, `delete_all_memories`)
- Data retention policies are determined by your database configuration and your own policies
- No automatic archiving or deletion is performed by the plugin

### Third-Party Access

- **No data is shared with mem0 or any third parties** - All processing is local
- The plugin only communicates with services you configure (your LLM, embedding, and database services)
- API keys and credentials are stored locally in your Dify instance
- You are responsible for managing access to your configured services

### Data Privacy and Compliance

Since all data is stored in your own infrastructure:
- You maintain full control over your data
- You are responsible for compliance with applicable data protection regulations (GDPR, CCPA, etc.)
- You can audit all data access through your database logs
- You can implement your own data retention and deletion policies

### Changes to Privacy Policy

We may update this privacy policy from time to time. Changes will be reflected in this document and in the plugin repository.

### Contact Us

If you have questions about this privacy policy or the plugin, please contact:
- Email: beersocccer@gmail.com

Last updated: 2026-04-16
