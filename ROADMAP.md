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
| SQL safety validation (destructive-keyword blocklist, read-only DB connection) | ✅ |
| Fallback-source transparency (`source: ai / fallback_rules` in responses) | ✅ |
| Cross-schema regression tests (Northwind + Sakila) | ✅ |
| Unit test suite (run `pytest --collect-only -q` for current count) | ✅ |

**Known limitations being addressed in this roadmap:**

- ❌ SQLite-only — no PostgreSQL, MySQL, Snowflake, etc.
- ~~❌ 3000-token schema cap breaks on databases with 50+ tables~~ ✅ **Schema-RAG implemented** — only relevant tables are sent
- ~~❌ No SQL safety gates~~ ✅ **Destructive-keyword blocklist + read-only connection implemented** — remaining work is enforced `LIMIT` caps and parser-based validation (see Phase 1.5)
- ❌ **Non-deterministic output** — the same question against the same database state can produce different SQL, different errors, or different classifications on repeated runs (see Phase 0 — this blocks everything else)
- ❌ Schema-token matching assumes flat, singular, CamelCase naming (breaks on pluralized table names and snake_case schemas)
- ❌ Geography/multi-hop JOIN building assumes a flat `City`/`Country` column on the anchor table; fails on normalized schemas with multi-hop FK chains
- ❌ No self-healing / query repair when SQL fails
- ❌ No streaming for large result sets
- ❌ Single-user — no sessions, authentication, or sharing
- ❌ No query caching or result caching
- ❌ No data visualization or export beyond CSV
- ❌ Rule-based NL-to-SQL is heavily Northwind-specific

---

## Phase 0: Reliability Hardening (do this before anything else)

The gaps below aren't scale limitations — they're correctness bugs in the pipeline that exists today. Building multi-agent orchestration, multi-database support, or caching on top of an unreliable core just propagates the same bugs into a fancier architecture (a Schema Linker agent inherits the same token-matching bug; a SQL Generator/Critic pair inherits the same wrong-column-guessing behavior). This phase is a gate, not an optional nice-to-have — nothing in Phase 1+ should start until it's done.

### 0.1 Deterministic Output Guarantee
- The same question, against the same database state, must produce identical SQL and identical classification results on every run — no exceptions.
- Audit Ollama request parameters: confirm `temperature=0.0` is actually respected by the installed Ollama version, and add an explicit `seed` parameter if supported.
- Audit `detect_table()` and any other `max(..., key=...)` tie-breaking logic for hidden non-determinism from dict ordering.
- Audit `_conversation_history` handling to confirm identical repeated questions aren't being silently treated as follow-ups based on unrelated prior state.
- Add a regression test that runs the same question 5+ times in a row and asserts identical output every time, for at least 10 representative questions across 2+ schemas.

**Why:** Nothing else on this roadmap matters if the system can't reliably reproduce its own output. This is a prerequisite for every other phase, especially self-healing (0.3) and multi-agent orchestration (Phase 2), both of which assume a deterministic base to reason about.

### 0.2 Schema-Agnostic Token Matching
- `check_relevance()`'s schema-token matching does exact string comparison with no plural/singular normalization, so "films" never matches the table `film`, "users" never matches `customer` without an explicit alias, etc.
- Add lightweight normalization (strip trailing "s", or a small stemming pass) before comparing question tokens to schema tokens.
- Extend `check_relevance()`'s question-word trigger list to include ranking/superlative language ("top," "highest," "most," "cheapest," etc.), which currently falls through to a false rejection.
- Replace `CLASSIFICATION_SYSTEM_PROMPT`'s synonym hints with schema-derived, domain-agnostic reasoning instructions rather than a hardcoded list tied to one schema's vocabulary (e.g. Northwind-specific "users ≈ Customers").

**Why:** Every non-Northwind schema tested so far (Sakila) surfaced false "irrelevant" rejections on completely reasonable questions. This isn't a multi-database-engine problem (Phase 1.1) — it's a naming-convention problem that exists purely within SQLite today, and it will get worse, not better, once Postgres/MySQL schemas (with their own varied naming conventions) are added.

### 0.3 Multi-Hop Join Construction
- The current geography-matching logic in `extract_text_conditions()` assumes a flat `City`/`Country` column exists directly on the anchor table (true for Northwind's `Customers`, false for normalized schemas like Sakila's `customer → address → city → country` chain).
- Walk the foreign-key graph (via `get_foreign_keys()`) to build correct multi-hop JOIN chains and aliases when the needed column isn't on the anchor table.
- If no FK path exists to a table containing the needed column, fail with a clear message instead of emitting SQL referencing a non-existent alias/column.
- Generalize this pattern beyond geography — any value-matching or column-matching logic that currently assumes a flat schema should be audited for the same assumption.

**Why:** This is the highest-severity class of bug found so far, because it produces a hard SQL execution error (not just a wrong answer) on any reasonably normalized schema — and most real-world production databases are more normalized than Northwind, not less.

### 0.4 Cross-Schema Regression Suite as a Merge Gate
- Maintain a fixed regression question set (15–20 questions) run against at least 2 structurally different schemas (e.g. Northwind — flat, CamelCase — and Sakila — normalized, snake_case, multi-hop joins).
- Require this suite to pass before merging any change to classification, relevance checking, or SQL generation logic.
- Include the determinism check from 0.1 as part of this suite (each question run multiple times, not just once).

**Why:** Every fix made so far during manual testing has had a tendency to fix the reported symptom while leaving the same class of bug live elsewhere, or introducing a new regression (e.g. a fix to classification accidentally causing "hello" to be rejected). A standing regression suite catches this before it reaches a demo.

---

## Phase 1: Foundation Improvements (v1.5)

### 1.1 Multi-Database Engine Support
- **Plugin architecture** to support PostgreSQL, MySQL, MariaDB, and Snowflake alongside SQLite
- Connection string management via environment variables or UI
- Database-agnostic schema introspection (each engine returns the same schema format)

**Why:** Most real-world databases are not SQLite. This unlocks enterprise adoption. **Depends on Phase 0.2/0.3 being solid first** — new engines will surface even more varied naming conventions and deeper join graphs than Sakila did, and will expose the same class of bugs immediately if they aren't fixed at the SQLite level first.

### 1.2 Schema Vector Search (Schema-RAG) — ✅ Done
- Implemented: embeddings generated per table description, top-k relevant tables retrieved per question, disk-cached.
- Remaining follow-up: parallelize the embedding generation across tables (currently sequential, causing slow first-load/first-switch delays on local Ollama), and consider committing a precomputed cache for the default database so a fresh clone doesn't pay the cost on first run.

### 1.3 Self-Healing Query Execution
- When `execute_sql()` fails, feed the error back to the AI with the original question and the failed SQL
- The AI analyzes the error and proposes a corrected query
- Loop up to N times (default: 2) before falling back to the user

**Why:** A single failed query currently returns a 500 error with no recovery path. Self-healing dramatically improves the user experience. **Depends on Phase 0.1 (determinism)** — a self-healing loop built on top of non-deterministic SQL generation can't reliably tell whether a retry actually fixed the root cause or just got lucky.

### 1.4 Query Result Streaming
- For large result sets (>100 rows), stream results via Server-Sent Events (SSE) or paginated responses
- Show a progress indicator in the UI while the query runs

**Why:** Databases with millions of rows would currently time out or overwhelm the UI.

### 1.5 Configurable SQL Safety Gates
- ~~Blocklist of dangerous SQL commands~~ ✅ implemented (`is_safe_select()`)
- ~~Read-only database connection~~ ✅ implemented
- **Remaining:** mandatory `LIMIT` clause enforcement (configurable max, default 1000) for queries that don't already have one
- **Remaining:** replace regex/keyword-based validation with a proper SQL parser (`sqlglot` or similar) for more robust detection of disguised destructive statements (e.g. via CTEs or unusual formatting that a simple word-boundary regex might miss)

**Why:** The blocklist approach is a solid first line of defense but is inherently a denylist — a parser-based allowlist approach (confirm the parsed AST is a pure SELECT/WITH, nothing else) is more robust against creative bypasses.

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

**Depends on Phase 0 being complete.** Each box in this diagram is a thin wrapper around logic that already exists in `app.py` today (Router ≈ `ask_classification()`, Schema Linker ≈ `_build_schema_prompt_with_rag()`, SQL Generator ≈ `ask_ai()`). Splitting these into separate agent hops doesn't fix the underlying bugs in each — it just adds orchestration overhead around them. Do this once each component is independently reliable.

### 2.2 Botpress Integration Strategy

| Component | Current (app.py) | Future (Botpress) |
|---|---|---|
| Workflow orchestration | Hardcoded pipeline | Visual flow builder |
| Schema retrieval | Schema-RAG (top-k tables) | Same, exposed as a Botpress node |
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
- Cache schema embeddings (refresh on DB change) — partially done via `schema_embeddings.json`, extend to per-question result caching
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
| **Embeddings** | `nomic-embed-text` / `text-embedding-004` (implemented) | Same, or `text-embedding-3-small` if adding OpenAI |
| **Vector Store** | JSON file cache | Chroma (local) or pgvector (PostgreSQL) |
| **Result Cache** | None | Redis or in-memory LRU |
| **Frontend** | Vanilla HTML/CSS (light/dark themes) | Botpress Webchat + React dashboard |
| **Auth** | None | Auth0 / JWT |
| **Database Engines** | SQLite only | SQLite + PostgreSQL + MySQL |
| **Deployment** | `python app.py` | Docker + Docker Compose + Kubernetes |

---

## Priority Matrix

| Feature | Impact | Effort | Phase |
|---|---|---|---|
| Deterministic output guarantee | 🔥🔥🔥🔥 | Low–Medium | 0 |
| Schema-agnostic token matching | 🔥🔥🔥🔥 | Low | 0 |
| Multi-hop join construction | 🔥🔥🔥 | Medium | 0 |
| Cross-schema regression suite | 🔥🔥🔥 | Low | 0 |
| Self-healing SQL | 🔥🔥🔥 | Low | 1 |
| Multi-DB support (PostgreSQL) | 🔥🔥🔥 | Medium | 1 |
| Parser-based SQL safety validation | 🔥🔥 | Low | 1 |
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

1. **Fix determinism (0.1)** — Nothing else on this list is trustworthy to build on top of until identical input reliably produces identical output. This is the highest-priority item on the entire roadmap.
2. **Fix schema-token normalization and the classification synonym approach (0.2)** — Directly caused every false "irrelevant" rejection found during cross-schema testing so far.
3. **Fix multi-hop join construction (0.3)** — The only bug found so far that produces a hard execution error rather than just a wrong answer.
4. **Stand up the cross-schema regression suite (0.4)** as a standing gate, so future fixes stop reintroducing the same bugs in new forms.
5. **Then** — add PostgreSQL/MySQL support, Docker support, and SQL self-healing, in that order, now that the foundation underneath them is solid.
6. **Evaluate Botpress** — once Phase 0 and the highest-impact Phase 1 items are done, set up a proof-of-concept Botpress agent that calls AskYourDB via webhook, to evaluate the multi-agent workflow on top of a reliable base.

---

> **Want to contribute?** Pick any item from Phase 0 first, then Phase 1. See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.