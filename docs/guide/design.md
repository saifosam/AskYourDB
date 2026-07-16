# Design

## Design Rationale

AskYourDB is built around the principle that **querying databases should not require knowing SQL**. The entire architecture is shaped by this goal.

### Why a Multi-Stage Pipeline?

A single AI call for SQL generation is unreliable. By splitting the process into stages:

1. **Relevance filtering** prevents wasteful AI calls on non-database questions
2. **Classification** routes inputs appropriately (greetings, follow-ups, irrelevant queries)
3. **Schema-RAG** reduces token usage by only including relevant tables
4. **AI SQL generation** leverages LLM reasoning for complex queries
5. **Rule-based fallback** ensures the app works even without AI

This layered approach provides **graceful degradation** — the app remains functional even when AI providers are unavailable.

### Why Schema-RAG?

Many NL-to-SQL systems dump the entire schema into the prompt. This wastes tokens and confuses the model with irrelevant tables. Schema-RAG:

- Uses **vector embeddings** to find semantically relevant tables
- Cuts token usage by 60-80% on databases with many tables
- Improves accuracy by reducing noise
- Works **fully offline** with Ollama's embedding models

### Why Multi-Provider Support?

Locking into a single AI provider creates risk. AskYourDB supports **Google Gemini**, **OpenRouter**, and **Ollama** with **automatic fallback**:

- No API key required to get started (Ollama runs locally)
- Production deployments can use paid providers (Gemini, OpenRouter)
- If one provider fails, the app seamlessly switches to another

### Why a Rule-Based Fallback?

AI models can hallucinate SQL, fail to respond, or be unavailable. The rule-based NL-to-SQL engine (`generate_sql()`) handles:

- **Table detection** — schema-aware keyword matching
- **Column aliases** — maps common terms like "name" and "price" to actual column names
- **NUMERIC conditions** — parses phrases like "over 50", "at least 10", "under $100"
- **Text conditions** — handles "starts with", "contains", geography matching
- **Date conditions** — parses years, months, "last month", "recent 7 days"
- **Aggregations** — COUNT with GROUP BY, SUM, AVG
- **Sorting & limits** — "top 5", "most expensive", "cheapest", "most recent"

## Architecture Decisions

### Why Flask over FastAPI?

Flask was chosen for **simplicity**. This project is a single-file backend with a handful of routes. Flask's minimal footprint means:

- Zero configuration beyond adding routes
- Easy to understand and modify
- No async complexity needed for this use case

### Why Vanilla Frontend?

The chat UI uses **plain HTML + CSS** without any JavaScript framework. This keeps the frontend:

- **Lightweight** — no build step, no npm dependencies for the frontend
- **Self-contained** — everything lives in two files (index.html + style.css)
- **Easy to customize** — anyone can modify the UI without knowing React/Vue/etc.

### Why SQLite Only?

Focusing on SQLite keeps the setup **zero-config**. Users upload `.db` files and query them immediately. The SQL generation is SQLite-specific (no support for MySQL or PostgreSQL extensions), which avoids ambiguity in the generated queries.

## Future Directions

- **PostgreSQL/MySQL support** — add dialect-specific SQL generation
- **Query caching** — cache frequent queries and their results
- **Visual charting** — render results as bar charts, line graphs, etc.
- **Multi-turn conversations** — deeper context awareness for complex analytical workflows
- **Query export** — download generated SQL and results as CSV/JSON
