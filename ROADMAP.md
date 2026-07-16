# AskYourDB — Roadmap

> **Vision:** Evolve from a single-Flask-app NL-to-SQL tool into a multi-agent, enterprise-grade natural language database interface that handles schemas of any size, connects to any database engine, and self-heals from errors.

---

## Current State (v1)

AskYourDB is a functional NL-to-SQL proof-of-concept:

| Capability | Status |
|---|---|
| NL queries → SQL via AI | ✅ |
| Rule-based SQL fallback | ✅ |
| Multi-AI provider support (Google, OpenRouter, Ollama) | ✅ |
| Schema discovery (tables, columns, FKs, samples) | ✅ |
| Relevance & data availability checks | ✅ |
| Follow-up question rewriting | ✅ |
| Database upload/select/delete | ✅ |
| Schema-RAG (vector-based table retrieval) | ✅ |
| Embedding cache (disk + memory) | ✅ |
| 69 unit tests | ✅ |

**Known limitations being addressed in this roadmap:**

- ❌ SQLite-only — no PostgreSQL, MySQL, Snowflake, etc.
- ~~❌ 3000-token schema cap breaks on databases with 50+ tables~~ ✅ **Schema-RAG implemented** — only relevant tables are sent
- ❌ No self-healing / query repair when SQL fails
- ❌ No streaming for large result sets
- ❌ Single-user — no sessions, authentication, or sharing
- ❌ No query caching or result caching
- ❌ No data visualization or export
- ❌ Rule-based NL-to-SQL is heavily Northwind-specific

---

## Phase 1: Foundation Improvements (v1.5)

### 1.1 Multi-Database Engine Support
- **Plugin architecture** to support PostgreSQL, MySQL, MariaDB, and Snowflake alongside SQLite
- Connection string management via environment variables or UI
- Database-agnostic schema introspection (each engine returns the same schema format)

**Why:** Most real-world databases are not SQLite. This unlocks enterprise adoption.

### 1.2 Schema Vector Search (Schema-RAG)
- Generate embeddings for each table/column description using a small embedding model (e.g., `text-embedding-3-small` or local `nomic-embed-text`)
- On query, retrieve only the **top-k relevant tables** instead of dumping the entire schema
- Store embeddings persistently (SQLite vector extension, Chroma, or a simple JSON cache)

**Why:** The current 3000-token limit breaks on databases with 50+ tables. Schema-RAG scales to hundreds of tables.

### 1.3 Self-Healing Query Execution
- When `execute_sql()` fails, feed the error back to the AI with the original question and the failed SQL
- The AI analyzes the error and proposes a corrected query
- Loop up to N times (default: 2) before falling back to the user

**Why:** A single failed query currently returns a 500 error with no recovery path. Self-healing dramatically improves the user experience.

### 1.4 Query Result Streaming
- For large result sets (>100 rows), stream results via Server-Sent Events (SSE) or paginated responses
- Show a progress indicator in the UI while the query runs

**Why:** Databases with millions of rows would currently time out or overwhelm the UI.

### 1.5 Configurable SQL Safety Gates
- Blocklist of dangerous SQL commands (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `TRUNCATE`)
- Mandatory `LIMIT` clause enforcement (configurable max, default 1000)
- Read-only database user recommendation for production deployments
- SQL validation pass before execution using `sqlglot` or similar

**Why:** Safety is critical before deploying to any shared or production environment.

---

## Phase 2: Multi-Agent Architecture with Botpress (v2)

### 2.1 Decompose into Specialized AI Agents

Instead of a single `ask_ai()` call that does everything, split into a **multi-agent workflow**:

```
User Query
    │
    ▼
┌─────────────────────┐
│ Router / Classifier │  ← Determines intent (query, viz, export, meta)         
│    (Small/cheap LLM)│
└─────────────────────┘
    │
    ▼
┌─────────────────────┐
│ Schema Linker       │  ← Vector search + LLM selection of relevant tables/cols
│    (Embedding + LLM)│      Returns only the schema context needed        
└─────────────────────┘
    │
    ▼
┌─────────────────────┐
│ SQL Generator       │  ← Generates SQL using the pruned schema                
│    (Powerful LLM)   │      Uses chain-of-thought
└─────────────────────┘
    │
    ▼
┌─────────────────────┐
│ SQL Critic          │  ← Validates SQL safety, syntax, and correctness       
│    (Small/cheap LLM)│      If invalid → sends back to Generator with error
└─────────────────────┘
    │
    ▼
┌─────────────────────┐
│ Executor + Formatter│  ← Runs SQL, formats results, handles pagination
└─────────────────────┘
    │
    ▼
   User
```

This is a natural fit for **Botpress**, which provides:
- Visual workflow builder for agent orchestration
- Built-in LLM nodes that support tool-calling
- Knowledge base integration for schema documentation
- Human-in-the-loop review gates
- Built-in session management and conversation history
- Webhook/integration cards for external API calls

### 2.2 Botpress Integration Strategy

| Component | Current (app.py) | Future (Botpress) |
|---|---|---|
| Workflow orchestration | Hardcoded pipeline | Visual flow builder |
| Schema retrieval | All tables at once | RAG-based vector search |
| SQL generation | Single LLM call | Multi-agent (Generator + Critic) |
| Error recovery | 500 error | Self-healing loop |
| UI | Custom HTML/CSS | Botpress webchat embed |
| User sessions | None | Built-in session management |
| Database connections | SQLite only | Plugin-based (any DB) |

### 2.3 Botpress Integration Flow

```
Botpress Webchat → Botpress AI Agent → AskYourDB API (Flask)
                                            │
                                            ▼
                                    Schema-RAG / DB Query
                                            │
                                            ▼
                                    Botpress receives results
                                            │
                                            ▼
                                    Formats & returns to user
```

The AskYourDB Flask app becomes a **backend API service** that Botpress calls via webhooks. Botpress handles:
- User interaction / chat UI
- Session management
- Multi-agent orchestration
- Human-in-the-loop gates
- Rich response formatting (tables, charts)

### 2.4 Additional Agents

| Agent | Role | Model |
|---|---|---|
| **Query Classifier** | Routes queries: data query, visualization, export, metadata info | Small/cheap LLM |
| **Schema Explorer** | "What tables do we have?" / "Describe the customers table" | Small LLM |
| **Data Visualizer** | Suggests and renders charts (bar, line, pie) from query results | Medium LLM |
| **Export Agent** | Exports results as CSV, JSON, or Excel | Lightweight |
| **SQL Explainer** | Explains generated SQL in plain English to the user | Small LLM |

---

## Phase 3: Enterprise Scaling (v3)

### 3.1 Query Cache & Materialized Results

- Cache frequent queries (hash of question + schema fingerprint)
- Cache schema embeddings (refresh on DB change)
- Optional materialized views for expensive aggregations

### 3.2 Authentication & Multi-Tenancy

- User authentication via OAuth2 / JWT
- Per-user query history and saved queries
- Per-tenant database connections
- Role-based access (admin, viewer, querier)

### 3.3 Dashboard & Visualization

- Auto-generate charts from query results (bar, line, pie using Chart.js or ECharts)
- Save queries as dashboard widgets
- Schedule recurring queries and email reports

### 3.4 Conversational Memory & Context

- Long-term conversation history (database-backed, not just in-memory)
- Cross-session context ("Remember my query from yesterday about...")
- Natural language query refinement ("Narrow that to only..." → auto-updates WHERE clause)

### 3.5 Self-Hosting & Deployment

- Docker container with all dependencies
- Docker Compose for AskYourDB + Ollama (full local AI stack)
- Helm chart for Kubernetes deployment
- One-click deploy to Railway / Render / Fly.io

---

## Phase 4: Advanced AI & Scale (v4)

### 4.1 Fine-Tuned Models

- Fine-tune a small model (e.g., `phi-3` or `qwen2.5-coder`) on the user's specific database schema and query patterns
- Dramatically reduces cost and latency for frequent query patterns

### 4.2 Natural Language ETL

- Allow users to describe data transformations: *"Merge the customers table with orders and compute average order value per region"*
- Generates and executes multi-step SQL pipelines (CTEs, temp tables)

### 4.3 Anomaly Detection Agent

- Proactively scans database for anomalies: *"Are there any orders with negative totals?"* / *"Show me outliers in product pricing"*
- Scheduled scans with email alerts

### 4.4 Collaborative Query Building

- Shared query sessions (multiple users building a query together)
- Comments and annotations on queries
- Fork / version history for complex queries

---

## Technology Stack Recommendations

| Layer | Current | Future Recommendation |
|---|---|---|
| **Orchestration** | Flask (hardcoded) | **Botpress** (visual agent builder) |
| **AI Providers** | Google / OpenRouter / Ollama | Same + Anthropic Claude |
| **LLM for SQL** | gemini-2.0-flash-lite / qwen2.5-coder | **Claude Sonnet** or **GPT-4o** for SQL gen; cheap model for classification |
| **Embeddings** | None | `text-embedding-3-small` or `nomic-embed-text` |
| **Vector Store** | None | Chroma (local) or pgvector (PostgreSQL) |
| **Result Cache** | None | Redis or in-memory LRU |
| **Frontend** | Vanilla HTML/CSS | Botpress Webchat + React dashboard |
| **Auth** | None | Auth0 / JWT |
| **Database Engines** | SQLite only | SQLite + PostgreSQL + MySQL |
| **Deployment** | `python app.py` | Docker + Docker Compose + Kubernetes |

---

## Priority Matrix

| Feature | Impact | Effort | Phase |
|---|---|---|---|
| Schema-RAG (vector search) | 🔥🔥🔥 | Medium | 1 |
| Self-healing SQL | 🔥🔥🔥 | Low | 1 |
| SQL safety gates | 🔥🔥🔥 | Low | 1 |
| Multi-DB support (PostgreSQL) | 🔥🔥🔥 | Medium | 1 |
| Multi-agent orchestration (Botpress) | 🔥🔥🔥 | High | 2 |
| Query streaming | 🔥🔥 | Medium | 1 |
| Docker deployment | 🔥🔥 | Low | 1 |
| Dashboard & visualization | 🔥🔥 | Medium | 3 |
| Fine-tuned models | 🔥🔥 | High | 4 |
| Auth & multi-tenancy | 🔥🔥 | Medium | 3 |
| Query caching | 🔥 | Low | 1 |
| Collaborative queries | 🔥 | High | 4 |

---

## Suggested Next Steps (What I'd Tackle First)

1. **Add PostgreSQL/MySQL support** — The schema introspection layer is already abstracted through `get_table_info()`. Adding a new engine just means implementing that interface.
2. **Add Docker support** — A `Dockerfile` and `docker-compose.yml` make deployment trivial.
3. **Implement SQL self-healing** — This is the highest-impact, lowest-effort feature. When SQL fails, feed the error + original question back to the AI for a correction attempt.
4. **Embed schema descriptions** — Generate embeddings for table/column descriptions and use vector similarity to retrieve only relevant schema context.
5. **Evaluate Botpress** — Set up a proof-of-concept Botpress agent that calls AskYourDB via webhook, to evaluate the multi-agent workflow.

---

> **Want to contribute?** Pick any item from Phase 1 and open a PR. See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.
